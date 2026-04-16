# zowiLibs
Repository that will store the production zowiLibs used in bitbloq

## Control LLM (llenguatge natural)

S'ha afegit un mode de control amb IA que permet ordres com:

- `camina endavant durant 2 segons`
- `gira cap a la dreta`
- `para`
- `camina endavant 1 segon, gira a la dreta, para`

Quan escrius diverses accions separades per comes, el controlador les divideix
localment i envia **cada segment per separat** al model Ollama.

### Requisits

Instal·la dependències:

```bash
pip install -r requirements.txt
```

Arrenca Ollama local i descarrega un model:

```bash
ollama serve
ollama pull tinyllama:latest
```

Opcional:

```bash
export OLLAMA_MODEL="tinyllama:latest"
export OLLAMA_URL="http://localhost:11434/api/chat"
export ZOWI_LLM_DEBUG="1"
export ZOWI_LLM_PROMPT_FILE="/ruta/al/meu_prompt.txt"
```

Si `ZOWI_LLM_DEBUG=1`, el controlador mostra traça detallada del flux:

- text d'entrada
- petició a Ollama (URL, model i payload)
- resposta RAW del model
- JSON parsejat
- acció validada i executada
- activació del fallback local de seguretat per ordres de parada (`stop`, `para`, `atura`, `aturat`, ...)

### Ús des del CLI principal

Executa `zowi_cli.py` i entra a l'opció:

- `[7] Control IA (LLM) llenguatge natural`

### Ús standalone

```bash
python zowi_llm_controller.py /dev/ttyACM0
python zowi_llm_controller.py /dev/ttyACM0 --llm-debug
python zowi_llm_controller.py /dev/ttyACM0 --ollama-model mistral:7b
python zowi_llm_controller.py /dev/ttyACM0 --llm-prompt-file ./prompt_zowi.txt
```

El flag `--llm-debug` activa el mateix mode de traça que `ZOWI_LLM_DEBUG=1`.
`--ollama-model` permet provar models diferents ràpidament i `--llm-prompt-file`
carrega un prompt personalitzat des d'un fitxer de text.
