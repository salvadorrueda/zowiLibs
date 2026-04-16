# Control IA (LLM) amb Ollama — Documentació tècnica detallada

Aquest document descriu **com està implementada** la funcionalitat de control en llenguatge natural a `zowilibs`, incloent arquitectura, validacions, execució de moviments i diagnòstic d'errors.

## 1) Fitxers implicats

- `zowi_cli.py`
  - Afegeix l'opció de menú `[7] Control IA (LLM) llenguatge natural`.
  - Crida `run_llm_control_menu(z)`.
- `zowi_llm_controller.py`
  - Conté la lògica principal de NLU (text -> acció estructurada -> execució).
- `zowi.py`
  - Biblioteca base que envia comandes sèrie al robot (`walk`, `turn`, `jump`, `stop`, etc.).
- `requirements.txt`
  - Dependències mínimes per aquesta part: `requests`, `pyserial`.

## 2) Arquitectura funcional

Pipeline intern de cada ordre de l'usuari:

1. Usuari escriu text lliure (`IA> ...`) al menú IA.
2. Si hi ha comes, `process_text_command()` divideix el text en segments locals.
3. Cada segment es processa de manera independent:
  - fallback local de `stop`, o bé
  - `parse_natural_command()` envia **només aquell segment** a Ollama (`POST /api/chat`) amb:
   - `system prompt` restrictiu
   - `format` JSON schema
4. La resposta del model es parseja com JSON (`_extract_action_payload`).
5. `validate_action()` normalitza i limita valors per seguretat.
6. `execute_action()` tradueix l'acció final a crides reals de `zowi.py`.

## 3) Integració al CLI

A `zowi_cli.py`:

- Import:
  - `from zowi_llm_controller import run_llm_control_menu`
- Menú principal:
  - opció `[7]` -> `run_llm_control_menu(z)`

Això reutilitza la mateixa connexió sèrie (`with Zowi(port) as z:`) ja oberta pel CLI.

## 4) Contracte de dades (Action)

A `zowi_llm_controller.py` s'utilitza:

```python
@dataclass
class Action:
    intent: str                   # walk | turn | stop | jump
    direction: Optional[str]      # forward | backward | left | right | None
    duration_s: Optional[float]
    steps: Optional[int]
```

Valors suportats:

- `VALID_INTENTS = {"walk", "turn", "stop", "jump"}`
- `VALID_DIRECTIONS = {"forward", "backward", "left", "right"}`

## 5) Crida HTTP a Ollama

Paràmetres de configuració:

- `OLLAMA_MODEL` (defecte: `tinyllama:latest`)
- `OLLAMA_URL` (defecte: `http://localhost:11434/api/chat`)
- `ZOWI_LLM_DEBUG` (`1/true/on/yes` per activar logs de depuració)
- `ZOWI_LLM_PROMPT_FILE` (fitxer opcional amb system prompt personalitzat)

Cos principal del `POST`:

- `model`: model Ollama actiu
- `stream: false`
- `messages`: system + user
- `options.temperature: 0`
- `format`: JSON schema amb camps obligatoris:
  - `intent`
  - `direction`
  - `duration_s`
  - `steps`

## 6) Prompt i objectiu del model

El `system prompt` demana explícitament:

- Retornar només JSON (sense text extra)
- Assumir que la petició és un únic segment, no una llista d'accions
- Intents limitats: `walk|turn|stop|jump`
- Regles de coherència:
  - `walk` només `forward/backward`
  - `turn` només `left/right`
  - `stop` i `jump` no necessiten direcció
- Inclou pista lingüística: `para/stop/aturat -> stop`

## 7) Parsing robust i neteja JSON

`_extract_action_payload(text)` aplica:

- Eliminació de blocs markdown ```json ... ``` si hi són
- Extracció del primer bloc JSON via regex
- `json.loads(...)`
- Compatibilitat amb respostes antigues com `{"actions": [...]}` si només contenen una acció

Si el model retorna text invàlid, es llença:

- `ValueError("Resposta JSON invàlida del model: ...")`

## 8) Validació i normalització (seguretat)

`validate_action(payload)` aplica controls abans d'executar res:

- `intent` ha de ser un dels suportats
- Àlies de direcció en català:
  - `endavant -> forward`
  - `enrere -> backward`
  - `esquerra -> left`
  - `dreta -> right`
- Clamps de valors:
  - `duration_s` entre `0.2` i `10.0`
  - `steps` entre `1` i `20`
- Defaults intel·ligents:
  - `walk/turn` sense passos: calcula a partir de `duration_s` (o 1.6s)
  - `step_time_ms = 800` (base del càlcul)
  - `jump` sense durada: `0.8s`
- `stop` i `jump` forcen `direction = None`

## 9) Execució física al robot

`execute_action(action)` mapeja a API real de `zowi.py`:

- `walk` -> `zowi.walk(steps=..., T=800, direction=forward|backward)`
- `turn` -> `zowi.turn(steps=..., T=800, direction=left|right)`
- `jump` -> `zowi.jump(T=duration_ms)`
- `stop` -> `zowi.stop()`

A `zowi.py`, `stop()` envia comanda sèrie `S` i espera ACK.

## 10) Gestió d'errors de xarxa/model

`parse_natural_command()` diferencia casos:

- `ConnectionError`:
  - Ollama no accessible a `OLLAMA_URL`
- `Timeout`:
  - Ollama no respon dins 60s
- HTTP `404`:
  - model no instal·lat (`ollama pull <model>`)
- Altres HTTP:
  - missatge amb codi concret

Exemple típic:

```bash
export OLLAMA_MODEL="tinyllama:latest"
export OLLAMA_URL="http://localhost:11434/api/chat"
```

## 11) Diagnòstic del cas reportat: "no s'atura amb stop/atura"

### Què hem observat

- El moviment (`walk`) s'està executant correctament.
- El problema és semàntic (NLU), no de connexió sèrie.

### Causes probables

1. **Model massa petit / inestable en JSON semàntic**
   - `tinyllama:latest` pot retornar valors incorrectes d'`intent`.
2. **Paraula fora del patró fort del model**
   - El prompt inclou `stop/para/aturat`, però `atura` pot no mapar sempre a `stop`.
3. **Resposta aparentment vàlida però errònia**
   - Pot retornar `walk` quan l'usuari demana parar.

### Com comprovar-ho ràpid

1) Arrencar servei:

```bash
ollama serve
```

2) Provar model:

```bash
ollama pull tinyllama:latest
```

3) Llançar CLI i provar ordres simples:

- `para`
- `stop`
- `atura`

Si `para/stop` funcionen però `atura` no, el problema és de mapping lingüístic del model.

### Recomanacions pràctiques

- Preferir un model més robust per instruccions estructurades (`llama3.1:8b` o superior).
- Afegir fallback local (regles) **abans** de cridar LLM per ordres crítiques:
  - si text conté `stop|para|atura|aturat` -> executar `stop` directament.
- Loguejar temporalment el JSON retornat pel model per veure l'`intent` real.

### Estat actual de la implementació (fallback)

Actualment ja existeix un **fallback local de seguretat** a `process_text_command()`:

1. Es normalitza el text (minúscules, sense accents, neteja de puntuació).
2. Es busca patró de parada (`stop`, `para`, `atura`, `aturat`, `aturi`, `deten`, `detente`).
3. Si hi ha match, es crea directament `Action(intent="stop")` i s'executa `zowi.stop()`.
4. En aquest cas **no es fa cap crida a Ollama**.

Això garanteix que l'ordre d'aturada no depèn del model.

## 11.1) Mode debug detallat

Per veure exactament què està passant al pipeline, activa:

```bash
export ZOWI_LLM_DEBUG="1"
export ZOWI_LLM_PROMPT_FILE="./prompt_zowi.txt"
```

Alternativament, en mode standalone:

```bash
python zowi_llm_controller.py /dev/ttyACM0 --llm-debug
python zowi_llm_controller.py /dev/ttyACM0 --ollama-model mistral:7b
python zowi_llm_controller.py /dev/ttyACM0 --llm-prompt-file ./prompt_zowi.txt
```

Amb debug actiu, es mostren traces amb prefix `[LLM DEBUG]`:

- entrada d'usuari
- URL/model de la crida a Ollama
- payload enviat
- codi HTTP de resposta
- resposta RAW del model
- JSON parsejat
- acció validada
- acció executada
- avís explícit quan s'activa el fallback local

## 12) Flux d'ús complet

```bash
pip install -r requirements.txt
ollama serve
ollama pull tinyllama:latest
export OLLAMA_MODEL="tinyllama:latest"
export OLLAMA_URL="http://localhost:11434/api/chat"
export ZOWI_LLM_DEBUG="1"
python zowi_cli.py
```

Després, al menú principal, entrar a `[7]` i escriure ordres naturals.

## 13) Limitacions actuals

- No hi ha memòria de context entre ordres (cada comanda és independent).
- No hi ha control de cancel·lació en mig d'una acció en curs (p. ex. durant un `walk` ja iniciat).
- La qualitat depèn molt del model Ollama seleccionat.

## 14) Millora recomanada (curta)

Per robustesa en robot físic, implementar prioritat de seguretat:

1. Regles locals per ordres crítiques (`stop`)  
2. Si no fa match, llavors LLM  
3. Validació actual + execució

Això manté flexibilitat de llenguatge natural i millora fiabilitat operativa.
