#!/usr/bin/env python3
"""
zowi_llm_controller.py — Control de Zowi amb ordres en llenguatge natural via LLM.

Exemples d'ordres:
    - camina endavant durant 2 segons
    - gira cap a la dreta, para
    - salta, camina endavant 1 segon, para
    - walk forward 1s, turn left, stop

Les ordres separades per comes es divideixen localment i s'envien al model
una a una, en seqüència.

Variables d'entorn esperades:
    OLLAMA_MODEL      (defecte: tinyllama:latest)
Opcional:
    OLLAMA_URL        (defecte: http://localhost:11434/api/chat)

Execució standalone:
    python zowi_llm_controller.py /dev/ttyACM0
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
import requests
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from zowi import Zowi


@dataclass
class Action:
    intent: str
    direction: Optional[str] = None
    duration_s: Optional[float] = None
    steps: Optional[int] = None


class ZowiLLMController:
    """Tradueix text natural a accions segures del robot i les executa."""

    VALID_INTENTS = {"walk", "turn", "stop", "jump"}
    VALID_DIRECTIONS = {"forward", "backward", "left", "right"}

    def __init__(
        self,
        zowi: Optional[Zowi],
        model: Optional[str] = None,
        ollama_url: Optional[str] = None,
        system_prompt: Optional[str] = None,
        prompt_file: Optional[str] = None,
    ):
        self.zowi = zowi
        self.model = model or os.getenv("OLLAMA_MODEL", "tinyllama:latest")
        self.ollama_url = ollama_url or os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
        self.debug = os.getenv("ZOWI_LLM_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
        self.step_time_ms = 800
        self.system_prompt_override = system_prompt or os.getenv("ZOWI_LLM_SYSTEM_PROMPT")
        self.prompt_file = prompt_file or os.getenv("ZOWI_LLM_PROMPT_FILE")

    def _debug(self, msg: str):
        if self.debug:
            print(f"[LLM DEBUG] {msg}")

    def _split_user_text(self, user_text: str) -> List[str]:
        return [segment.strip() for segment in user_text.split(",") if segment.strip()]

    def _normalize_text_for_rules(self, text: str) -> str:
        normalized = unicodedata.normalize("NFD", text or "")
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        normalized = normalized.lower().strip()
        return normalized

    _STOP_PATTERNS = [
        r"\bstop\b",
        r"\bpara\b",
        r"\baturat\b",
        r"\batura\b",
        r"\baturi\b",
        r"\bdeten\b",
        r"\bdetente\b",
    ]

    def _segment_has_stop(self, segment: str) -> bool:
        normalized = self._normalize_text_for_rules(segment)
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return any(re.search(p, normalized) for p in self._STOP_PATTERNS)

    def _local_fallback_action(self, segment: str) -> Optional[Action]:
        if self._segment_has_stop(segment):
            self._debug(f"Fallback local STOP per segment: {segment!r}")
            return Action(intent="stop")
        return None

    def _system_prompt(self) -> str:
        if self.prompt_file:
            prompt_path = Path(self.prompt_file)
            prompt = prompt_path.read_text(encoding="utf-8")
            self._debug(f"Prompt carregat des de fitxer: {prompt_path}")
            return prompt.strip()

        if self.system_prompt_override:
            return self.system_prompt_override.strip()

        return (
            "Ets un parser d'ordres per a un robot. "
            "L'entrada de l'usuari és UN sol segment d'ordre, no una seqüència completa. "
            "Retorna exactament UN objecte JSON que descrigui només aquesta acció. "
            "L'objecte segueix l'esquema: "
            "{\"intent\":\"walk|turn|stop|jump\",\"direction\":\"forward|backward|left|right|null\","
            "\"duration_s\":number|null,\"steps\":number|null}. "
            "Regles: "
            "- intent=walk -> direction només forward/backward. "
            "- intent=turn -> direction només left/right. "
            "- stop i jump no necessiten direction (null). "
            "- 'para/stop/atura/aturat' -> stop. "
            "- Si falta informació, infereix valors raonables. "
            "No retornis llistes ni la clau 'actions'. "
            "Exemple: 'camina endavant 1 segon' -> "
            "{\"intent\":\"walk\",\"direction\":\"forward\",\"duration_s\":1.0,\"steps\":null}"
        )

    def _extract_action_payload(self, text: str) -> Dict[str, Any]:
        """Extreu una única acció de la resposta del model.

        Accepta també respostes antigues si només contenen una acció.
        """
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        match = re.search(r"([\[\{].*[\]\}])", cleaned, re.DOTALL)
        payload_str = match.group(1) if match else cleaned

        try:
            parsed = json.loads(payload_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Resposta JSON invàlida del model: {payload_str}") from exc

        if isinstance(parsed, list):
            if len(parsed) != 1 or not isinstance(parsed[0], dict):
                raise ValueError(f"S'esperava una sola acció i el model n'ha retornat {len(parsed)}")
            self._debug("Resposta antiga en format llista; s'usa la primera acció.")
            return parsed[0]
        if isinstance(parsed, dict):
            if "actions" in parsed and isinstance(parsed["actions"], list):
                if len(parsed["actions"]) != 1 or not isinstance(parsed["actions"][0], dict):
                    raise ValueError(
                        f"S'esperava una sola acció i el model n'ha retornat {len(parsed['actions'])}"
                    )
                self._debug("Resposta antiga amb clau 'actions'; s'usa la primera acció.")
                return parsed["actions"][0]
            return parsed
        raise ValueError(f"Format de resposta inesperat: {type(parsed)}: {parsed}")

    def parse_natural_command(self, user_text: str) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": user_text},
            ],
            "options": {
                "temperature": 0,
            },
            "format": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string"},
                    "direction": {"type": ["string", "null"]},
                    "duration_s": {"type": ["number", "null"]},
                    "steps": {"type": ["integer", "null"]},
                },
                "required": ["intent", "direction", "duration_s", "steps"],
            },
        }

        self._debug(f"Input usuari: {user_text!r}")
        self._debug(f"Crida Ollama -> url={self.ollama_url} model={self.model}")
        if self.debug:
            self._debug(f"Payload: {json.dumps(payload, ensure_ascii=False)}")

        try:
            response = requests.post(self.ollama_url, json=payload, timeout=60)
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"No s'ha pogut contactar amb Ollama a {self.ollama_url}. "
                "Assegura't que està actiu (ex: `ollama serve`)."
            ) from exc
        except requests.Timeout as exc:
            raise RuntimeError(
                f"Ollama no ha respost a temps (timeout=60s). Model: {self.model}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Error de xarxa inesperat: {exc}") from exc

        if response.status_code == 404:
            raise RuntimeError(
                f"Model '{self.model}' no trobat a Ollama. "
                f"Executa: ollama pull {self.model}"
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Error HTTP {response.status_code} d'Ollama: {exc}") from exc

        self._debug(f"Resposta HTTP Ollama: {response.status_code}")
        data = response.json()
        raw = data.get("message", {}).get("content", "") or "{}"
        self._debug(f"Resposta RAW model: {raw}")
        action_payload = self._extract_action_payload(raw)
        self._debug(f"Acció parsejada: {action_payload}")
        return action_payload

    def _normalize_direction(self, direction: Optional[str]) -> Optional[str]:
        if direction is None:
            return None
        direction = str(direction).strip().lower()

        aliases = {
            "endavant": "forward",
            "enrere": "backward",
            "esquerra": "left",
            "dreta": "right",
            "forward": "forward",
            "backward": "backward",
            "left": "left",
            "right": "right",
        }
        return aliases.get(direction, direction)

    def validate_action(self, payload: Dict[str, Any]) -> Action:  # noqa: D102
        self._debug(f"Validant acció: {payload}")
        intent = str(payload.get("intent", "")).strip().lower()
        if intent not in self.VALID_INTENTS:
            raise ValueError(f"Intent no suportat: {intent!r}")

        direction = self._normalize_direction(payload.get("direction"))

        duration_s = payload.get("duration_s")
        if duration_s is not None:
            duration_s = float(duration_s)
            duration_s = max(0.2, min(duration_s, 10.0))

        steps = payload.get("steps")
        if steps is not None:
            steps = int(steps)
            steps = max(1, min(steps, 20))

        if intent == "walk":
            if direction not in {"forward", "backward"}:
                direction = "forward"
            if steps is None:
                if duration_s is None:
                    duration_s = 1.6
                steps = max(1, min(20, math.ceil(duration_s * 1000 / self.step_time_ms)))

        if intent == "turn":
            if direction not in {"left", "right"}:
                direction = "left"
            if steps is None:
                if duration_s is None:
                    duration_s = 1.6
                steps = max(1, min(20, math.ceil(duration_s * 1000 / self.step_time_ms)))

        if intent in {"stop", "jump"}:
            direction = None
            if intent == "jump" and duration_s is None:
                duration_s = 0.8

        action = Action(intent=intent, direction=direction, duration_s=duration_s, steps=steps)
        self._debug(f"Acció validada: {action}")
        return action

    def execute_action(self, action: Action):
        if self.zowi is None:
            raise RuntimeError(
                "No hi ha instància de Zowi (zowi=None). "
                "Aquest controlador està en mode interpretació i no pot executar accions."
            )
        self._debug(f"Executant acció: {action}")
        if action.intent == "walk":
            self.zowi.walk(steps=action.steps or 2, T=self.step_time_ms, direction=action.direction or "forward")
            return

        if action.intent == "turn":
            self.zowi.turn(steps=action.steps or 2, T=self.step_time_ms, direction=action.direction or "left")
            return

        if action.intent == "jump":
            jump_ms = int((action.duration_s or 0.8) * 1000)
            self.zowi.jump(T=jump_ms)
            return

        if action.intent == "stop":
            self.zowi.stop()
            return

        raise ValueError(f"Intent no implementat: {action.intent}")

    def interpret_text_command(self, user_text: str) -> List[Action]:
        """Divideix per comes i interpreta cada segment com una ordre independent.

        No executa moviments físics; només retorna la seqüència d'accions validada.
        """
        segments = self._split_user_text(user_text)
        actions: List[Action] = []

        for index, segment in enumerate(segments, 1):
            self._debug(f"Segment [{index}/{len(segments)}]: {segment!r}")
            fallback_action = self._local_fallback_action(segment)
            if fallback_action is not None:
                action = fallback_action
            else:
                payload = self.parse_natural_command(segment)
                action = self.validate_action(payload)
            actions.append(action)
        return actions

    def process_text_command(self, user_text: str) -> List[Action]:
        """Interpreta i executa totes les accions d'un text natural."""
        actions = self.interpret_text_command(user_text)
        for action in actions:
            self.execute_action(action)
        return actions



def run_llm_control_menu(
    z: Zowi,
    model: Optional[str] = None,
    ollama_url: Optional[str] = None,
    system_prompt: Optional[str] = None,
    prompt_file: Optional[str] = None,
):
    """Bucle interactiu de control en llenguatge natural."""
    controller = ZowiLLMController(
        z,
        model=model,
        ollama_url=ollama_url,
        system_prompt=system_prompt,
        prompt_file=prompt_file,
    )

    print("\n  ┌─ CONTROL IA (LLM)" + "─" * 33 + "┐")
    print("  │  Separa accions amb comes; cada segment s'envia   │")
    print("  │  al model per separat.                            │")
    print("  │   - camina endavant 2 segons, para                │")
    print("  │   - walk forward 1s, turn left, stop              │")
    print("  │  Escriu 'q' per tornar al menú principal.         │")
    print("  └" + "─" * 54 + "┘")

    while True:
        text = input("  IA> ").strip()
        if text.lower() in {"q", "quit", "exit"}:
            print("  → Sortint del mode IA.")
            break
        if not text:
            continue

        try:
            actions = controller.process_text_command(text)
            for i, action in enumerate(actions, 1):
                prefix = f"  → [{i}/{len(actions)}]"
                if action.intent in {"walk", "turn"}:
                    print(f"{prefix} {action.intent} {action.direction} ({action.steps} passos)")
                else:
                    print(f"{prefix} {action.intent}")
        except Exception as exc:
            print(f"  Error IA: {exc}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Control de Zowi amb ordres en llenguatge natural via LLM"
    )
    parser.add_argument("port", help="Port sèrie (ex: /dev/ttyACM0)")
    parser.add_argument(
        "--llm-debug",
        action="store_true",
        help="Activa logs detallats del pipeline LLM (equivalent a ZOWI_LLM_DEBUG=1)",
    )
    parser.add_argument(
        "--ollama-model",
        help="Model d'Ollama a usar (sobrescriu OLLAMA_MODEL)",
    )
    parser.add_argument(
        "--ollama-url",
        help="URL de l'API d'Ollama (sobrescriu OLLAMA_URL)",
    )
    parser.add_argument(
        "--llm-prompt-file",
        help="Fitxer de text amb el system prompt personalitzat",
    )
    args = parser.parse_args()

    if args.llm_debug:
        os.environ["ZOWI_LLM_DEBUG"] = "1"

    port = args.port
    with Zowi(port) as z:
        run_llm_control_menu(
            z,
            model=args.ollama_model,
            ollama_url=args.ollama_url,
            prompt_file=args.llm_prompt_file,
        )


if __name__ == "__main__":
    main()
