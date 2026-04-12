# Connectar el Zowi per Bluetooth a Linux

## Requisits previs

- Portàtil amb Bluetooth i Linux
- Robot Zowi encès (LED del mòdul BT parpellejant ràpid = esperant connexió)
- `python3` i `pyserial` instal·lats (`pip install pyserial`)

---

## Pas 1 — Parear el Zowi

Obre el terminal i executa:

```bash
bluetoothctl
```

Dins de la consola interactiva:

```
[bluetooth]# scan on
```

Espera fins que aparegui un dispositiu anomenat **"Zowi"** o **"HC-05"** amb la seva adreça MAC (format `XX:XX:XX:XX:XX:XX`). Quan el vegis:

```
[bluetooth]# pair XX:XX:XX:XX:XX:XX
```

Et demanarà un PIN. Prova **`1234`** (per defecte del HC-05). Si no funciona, prova `0000`.

Un cop pareat:

```
[bluetooth]# trust XX:XX:XX:XX:XX:XX
[bluetooth]# quit
```

> **Nota:** El pareament només cal fer-lo una vegada. En connexions posteriors, salta directament al Pas 2.

---

## Pas 2 — Crear el port sèrie virtual

El mòdul Bluetooth del Zowi és un dispositiu sèrie. Cal crear un port virtual `rfcomm` per poder comunicar-s'hi:

```bash
sudo rfcomm bind /dev/rfcomm0 XX:XX:XX:XX:XX:XX 1
```

Dona permisos d'accés al port:

```bash
sudo chmod 666 /dev/rfcomm0
```

Verifica que el port existeix:

```bash
ls -l /dev/rfcomm0
```

> **Nota:** El binding `rfcomm` desapareix quan apagues l'ordinador. Cal repetir aquest pas a cada sessió.

### Fer el binding permanent (opcional)

Afegeix aquesta línia a `/etc/rc.local` (abans de `exit 0`):

```bash
rfcomm bind /dev/rfcomm0 XX:XX:XX:XX:XX:XX 1
```

---

## Pas 3 — Executar el controlador

```bash
# Especificant el port explícitament:
python zowi_cli.py /dev/rfcomm0

# O deixant que es detecti automàticament:
python zowi_cli.py
```

El CLI detecta automàticament ports `/dev/ttyUSB*`, `/dev/ttyACM*` i `/dev/rfcomm*`.

---

## Diferències respecte a la connexió USB

| | USB (`/dev/ttyACM0`) | Bluetooth (`/dev/rfcomm0`) |
|---|---|---|
| Cable | Sí | No |
| Reinici Arduino en connectar | Sí (2 s d'espera) | No (respon de seguida) |
| Velocitat | 115200 baud | 115200 baud |
| Codi Python | Idèntic | Idèntic |
| Abast | 0,5 m | ~10 m |

---

## Resolució de problemes

**El `scan on` no troba el Zowi**
- Comprova que el Zowi està encès i el LED del mòdul BT parpelleja ràpidament.
- Reinicia el Bluetooth del portàtil: `sudo systemctl restart bluetooth`

**Error `rfcomm bind: Address already in use`**
- El port ja està creat. Pots usar-lo directament o alliberar-lo amb:
  ```bash
  sudo rfcomm release /dev/rfcomm0
  ```

**El programa Python no es connecta o dona timeout**
- Comprova que el robot està encès i el LED del BT parpelleja lentament (connexió activa).
- Assegura't que no hi ha cap altra aplicació (ZowiPAD, etc.) connectada al mateix temps.
- Prova a rebind el port: allibera'l i torna a fer el `rfcomm bind`.

**PIN incorrecte**
- El PIN per defecte del HC-05 és `1234`. Alguns mòduls usen `0000`.
- Si el Zowi havia estat configurat prèviament, el PIN pot haver estat canviat.
