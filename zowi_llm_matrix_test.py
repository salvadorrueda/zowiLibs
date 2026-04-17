#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Tuple

from zowi_llm_controller import ZowiLLMController

DEFAULT_TEST_PHRASES = [
    "Camina endevant durant un segon, aturat un segon, i camina enrere un altre segon",
    "camina endavant 1 segon, para",
    "gira a la dreta",
    "stop",
]


def parse_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def load_inputs(inputs_csv: Optional[str], input_file: Optional[str]) -> List[str]:
    phrases = parse_csv(inputs_csv)

    if input_file:
        path = Path(input_file)
        if not path.exists():
            raise FileNotFoundError(f"No existeix el fitxer d'inputs: {path}")
        file_phrases = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        phrases.extend(file_phrases)

    if not phrases:
        phrases = DEFAULT_TEST_PHRASES.copy()

    return phrases


def resolve_prompts(prompts_csv: Optional[str]) -> List[Tuple[str, Optional[str]]]:
    prompt_paths = parse_csv(prompts_csv)
    if not prompt_paths:
        return [("<built-in>", None)]

    resolved: List[Tuple[str, Optional[str]]] = []
    for raw_path in prompt_paths:
        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"No existeix el fitxer de prompt: {path}")
        resolved.append((str(path), str(path)))
    return resolved


def run_matrix(
    models: List[str],
    prompts: List[Tuple[str, Optional[str]]],
    phrases: List[str],
    ollama_url: Optional[str],
):
    for model in models:
        for prompt_label, prompt_path in prompts:
            for phrase in phrases:
                controller = ZowiLLMController(
                    zowi=None,
                    model=model,
                    ollama_url=ollama_url,
                    prompt_file=prompt_path,
                )

                try:
                    actions = controller.interpret_text_command(phrase)
                    print(
                        json.dumps(
                            {
                                "status": "OK",
                                "model": model,
                                "prompt": prompt_label,
                                "input": phrase,
                                "actions": [asdict(action) for action in actions],
                            },
                            ensure_ascii=False,
                        )
                    )
                except Exception as exc:
                    print(
                        json.dumps(
                            {
                                "status": "ERROR",
                                "model": model,
                                "prompt": prompt_label,
                                "input": phrase,
                                "error": str(exc),
                            },
                            ensure_ascii=False,
                        )
                    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Matrix test d'interpretació LLM per Zowi (sense execució física)."
    )
    parser.add_argument(
        "--models",
        required=True,
        help="Models separats per comes (ex: tinyllama:latest,mistral:7b)",
    )
    parser.add_argument(
        "--prompts",
        help="Fitxers de prompt separats per comes (si no s'indica, usa prompt intern)",
    )
    parser.add_argument(
        "--inputs",
        help="Frases de prova separades per comes",
    )
    parser.add_argument(
        "--input-file",
        help="Fitxer amb frases (una per línia)",
    )
    parser.add_argument(
        "--ollama-url",
        help="URL d'Ollama (sobrescriu OLLAMA_URL)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Activa logs detallats (equivalent a ZOWI_LLM_DEBUG=1)",
    )
    args = parser.parse_args()

    if args.debug:
        os.environ["ZOWI_LLM_DEBUG"] = "1"

    models = parse_csv(args.models)
    if not models:
        parser.error("Cal indicar almenys un model a --models")

    prompts = resolve_prompts(args.prompts)
    phrases = load_inputs(args.inputs, args.input_file)

    print(
        json.dumps(
            {
                "status": "INFO",
                "models": models,
                "prompts": [label for label, _ in prompts],
                "inputs": len(phrases),
            },
            ensure_ascii=False,
        )
    )

    run_matrix(models=models, prompts=prompts, phrases=phrases, ollama_url=args.ollama_url)


if __name__ == "__main__":
    main()
