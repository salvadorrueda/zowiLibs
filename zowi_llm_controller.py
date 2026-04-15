#!/usr/bin/env python3
"""
zowi_llm_controller.py — Control de Zowi amb ordres en llenguatge natural via LLM.

Exemples d'ordres:
    - camina endavant durant 2 segons
    - gira cap a la dreta, para
    - salta, camina endavant 1 segon, para
    - walk forward 1s, turn left, stop

Les ordres separades per comes s'executen en seqüència.

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

    def __init__(self, zowi: Zowi, model: Optional[str] = None):
        self.zowi = zowi
        self.model = model or os.getenv("OLLAMA_MODEL", "tinyllama:latest")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
        self.debug = os.getenv("ZOWI_LLM_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
        self.step_time_ms = 800

    def _debug(self, msg: str):
        if self.debug:
            print(f"[LLM DEBUG] {msg}")

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

    def _local_fallback_sequence(self, user_text: str) -> Optional[List[Action]]:
        """Retorna llista d'accions si TOTA la frase es pot resoldre localment.

        Ara mateix el fallback local només reconeix ordres de stop.
        Si algun segment no és stop, retornem None per passar a Ollama.
        """
        segments = [s.strip() for s in user_text.split(",") if s.strip()]
        actions: List[Action] = []
        for seg in segments:
            if self._segment_has_stop(seg):
                self._debug(f"Fallback local STOP per segment: {seg!r}")
                actions.append(Action(intent="stop"))
            else:
                # Segment no resolt localment → passa tot a Ollama
                return None
        if actions:
            return actions
        return None

    def _system_prompt(self) -> str:
        return (
            "Ets un parser d'ordres per a un robot. "
            "L'usuari pot donar UNA o MÚLTIPLES ordres separades per comes. "
            "Retorna un JSON estricte amb la clau 'actions' que conté una llista d'accions. "
            "Cada acció segueix l'esquema: "
            "{\"intent\":\"walk|turn|stop|jump\",\"direction\":\"forward|backward|left|right|null\","
            "\"duration_s\":number|null,\"steps\":number|null}. "
            "Regles: "
            "- intent=walk -> direction només forward/backward. "
            "- intent=turn -> direction només left/right. "
            "- stop i jump no necessiten direction (null). "
            "- 'para/stop/atura/aturat' -> stop. "
            "- Respecta l'ordre de les ordres de l'usuari. "
            "- Si falta informació, infereix valors raonables. "
            "Exemple: 'camina endavant 1 segon, para' -> "
            "{\"actions\":[{\"intent\":\"walk\",\"direction\":\"forward\",\"duration_s\":1.0,\"steps\":null},"
            "{\"intent\":\"stop\",\"direction\":null,\"duration_s\":null,\"steps\":null}]}"
        )

    def _extract_action_list(self, text: str) -> List[Dict[str, Any]]:
        """Extreu la llista d'accions de la resposta del model.

        Accepta:
          - {"actions": [{...}, ...]}
          - [{...}, ...]   (llista directa)
          - {...}           (acció única, per compatibilitat)
        """
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        # Intenta extreure primer { o [
        match = re.search(r"([\[\{].*[\]\}])", cleaned, re.DOTALL)
        payload_str = match.group(1) if match else cleaned

        try:
            parsed = json.loads(payload_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Resposta JSON invàlida del model: {payload_str}") from exc

        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            if "actions" in parsed and isinstance(parsed["actions"], list):
                return parsed["actions"]
            # Acció única sense embolcall
            return [parsed]
        raise ValueError(f"Format de resposta inesperat: {type(parsed)}: {parsed}")

    def parse_natural_command(self, user_text: str) -> List[Dict[str, Any]]:
        action_schema = {
            "type": "object",
            "properties": {
                "intent":    {"type": "string"},
                "direction": {"type": ["string", "null"]},
                "duration_s":{"type": ["number", "null"]},
                "steps":     {"type": ["integer", "null"]},
            },
            "required": ["intent", "direction", "duration_s", "steps"],
        }
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
                    "actions": {
                        "type": "array",
                        "items": action_schema,
                    },
                },
                "required": ["actions"],
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
        actions = self._extract_action_list(raw)
        self._debug(f"Llista d'accions parsejaes: {actions}")
        return actions

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

    def process_text_command(self, user_text: str) -> List[Action]:
        """Parseja i executa en seqüència totes les accions del text."""
        # Primer: fallback local (si TOTA la frase és resolta localment)
        fallback_seq = self._local_fallback_sequence(user_text)
        if fallback_seq is not None:
            for action in fallback_seq:
                self.execute_action(action)
            return fallback_seq

        # Segon: Ollama
        raw_list = self.parse_natural_command(user_text)
        actions = [self.validate_action(item) for item in raw_list]
        for action in actions:
            self.execute_action(action)
        return actions



def run_llm_control_menu(z: Zowi):
    """Bucle interactiu de control en llenguatge natural."""
    controller = ZowiLLMController(z)

    print("\n  ┌─ CONTROL IA (LLM)" + "─" * 33 + "┐")
    print("  │  Escriu ordres naturals (separades per comes):    │")
    print("  │   - camina endavant 2 segons, para               │")
    print("  │   - gira a la dreta, camina endavant, para        │")
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
    args = parser.parse_args()

    if args.llm_debug:
        os.environ["ZOWI_LLM_DEBUG"] = "1"

    port = args.port
    with Zowi(port) as z:
        run_llm_control_menu(z)


if __name__ == "__main__":
    main()
