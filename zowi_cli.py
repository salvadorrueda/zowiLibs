#!/usr/bin/env python3
"""
zowi_cli.py — Interfície interactiva per controlar el robot Zowi per teclat.

Ús:
    python zowi_cli.py /dev/ttyACM0
    python zowi_cli.py               (detecta el port automàticament)
"""

import sys
import time

import serial.tools.list_ports

from zowi import Zowi


# ---------------------------------------------------------------------------
# Helpers de presentació
# ---------------------------------------------------------------------------

def _header(z: Zowi):
    name    = z.get_name()
    battery = z.get_battery()
    dist    = z.get_distance()
    bar     = ('█' * int(battery / 10)).ljust(10)
    print(f"\n  Robot: {name:<12}  Bateria: [{bar}] {battery:.0f}%  Distància: {dist:.0f} cm")

def _sep():
    print("  " + "─" * 54)

def _title(text):
    print(f"\n  ┌─ {text} " + "─" * max(0, 50 - len(text)) + "┐")

def _opt(key, desc):
    print(f"  │  [{key}] {desc}")

def _end():
    print("  └" + "─" * 54 + "┘")


# ---------------------------------------------------------------------------
# Submenús
# ---------------------------------------------------------------------------

def menu_moviment(z: Zowi):
    while True:
        _title("MOVIMENT")
        _opt('w', 'Caminar endavant')
        _opt('s', 'Caminar enrere')
        _opt('a', 'Girar esquerra')
        _opt('d', 'Girar dreta')
        _opt('j', 'Saltar')
        _opt('u', 'Pujar i baixar (updown)')
        _opt('x', 'Swing (balanceig)')
        _opt('m', 'Moonwalk esquerra')
        _opt('M', 'Moonwalk dreta')
        _opt('t', 'Tremolor (jitter)')
        _opt('0', 'STOP / posició de repòs')
        _opt('q', 'Tornar al menú principal')
        _end()
        op = input("  Tria: ").strip()

        if op == 'w':
            n = _ask_int("Quants passos?", 2)
            t = _ask_int("Durada de cada pas (ms)?", 1000)
            print(f"  → Caminant endavant {n} passos...")
            z.walk(steps=n, T=t, direction='forward')
        elif op == 's':
            n = _ask_int("Quants passos?", 2)
            t = _ask_int("Durada de cada pas (ms)?", 1000)
            print(f"  → Caminant enrere {n} passos...")
            z.walk(steps=n, T=t, direction='backward')
        elif op == 'a':
            n = _ask_int("Quants passos de gir?", 2)
            print(f"  → Girant esquerra {n} passos...")
            z.turn(steps=n, direction='left')
        elif op == 'd':
            n = _ask_int("Quants passos de gir?", 2)
            print(f"  → Girant dreta {n} passos...")
            z.turn(steps=n, direction='right')
        elif op == 'j':
            t = _ask_int("Durada del salt (ms)?", 800)
            print("  → Saltant!")
            z.jump(T=t)
        elif op == 'u':
            n = _ask_int("Quants cicles?", 2)
            h = _ask_int("Alçada (5-30)?", 20)
            for _ in range(n):
                z.move(Zowi.UPDOWN, T=1000, h=h)
                time.sleep(1.0)
        elif op == 'x':
            n = _ask_int("Quants cicles?", 2)
            z.swing(steps=n, T=1000, h=20)
        elif op == 'm':
            n = _ask_int("Quants passos?", 2)
            for _ in range(n):
                z.move(Zowi.MOONWALK_L, T=900, h=20)
                time.sleep(0.9)
        elif op == 'M':
            n = _ask_int("Quants passos?", 2)
            for _ in range(n):
                z.move(Zowi.MOONWALK_R, T=900, h=20)
                time.sleep(0.9)
        elif op == 't':
            z.move(Zowi.JITTER, T=500, h=20)
            time.sleep(0.5)
        elif op == '0':
            print("  → Stop.")
            z.stop()
        elif op == 'q':
            break
        else:
            print("  Opció no reconeguda.")


def menu_cara(z: Zowi):
    face_list = list(Zowi.FACES.keys())
    while True:
        _title("CARA LED")
        _opt('l', 'Llistat de totes les cares')
        _opt('n', 'Triar cara per nom')
        _opt('a', 'Animació littleUuh')
        _opt('c', 'Netejar cara (tot apagat)')
        _opt('b', 'Bitmap personalitzat (32 bits)')
        _opt('q', 'Tornar al menú principal')
        _end()
        op = input("  Tria: ").strip()

        if op == 'l':
            print()
            for i, name in enumerate(face_list):
                print(f"    {i:>2}. {name}")
            print()
            idx = _ask_int(f"Número de cara (0-{len(face_list)-1})?", None)
            if idx is not None and 0 <= idx < len(face_list):
                print(f"  → Mostrant '{face_list[idx]}'...")
                z.set_mouth(face_list[idx])
            else:
                print("  Número no vàlid.")
        elif op == 'n':
            nom = input("  Nom de la cara: ").strip()
            try:
                z.set_mouth(nom)
                print(f"  → Cara '{nom}' mostrada.")
            except ValueError as e:
                print(f"  Error: {e}")
        elif op == 'a':
            r = _ask_int("Quantes vegades repetir?", 2)
            print("  → Animació littleUuh...")
            z.animate_mouth(Zowi.ANIM_LITTLE_UUH, delay=0.12, repeat=r)
        elif op == 'c':
            z.clear_mouth()
            print("  → Cara apagada.")
        elif op == 'b':
            bits = input("  Introdueix 32 bits (0 i 1): ").strip()
            if len(bits) == 32 and all(c in '01' for c in bits):
                value = int(bits, 2)
                z.set_mouth(value)
                print(f"  → Bitmap enviat.")
            else:
                print("  Ha de ser exactament 32 caràcters '0' o '1'.")
        elif op == 'q':
            break
        else:
            print("  Opció no reconeguda.")


def menu_sons(z: Zowi):
    song_list = list(Zowi.SONGS.items())   # [(nom, id), ...]
    gest_list = list(Zowi.GESTURES.items())
    while True:
        _title("SONS I GESTOS")
        _opt('s', 'Triar so predefinit')
        _opt('t', 'Tocar nota (freqüència + durada)')
        _opt('g', 'Triar gest predefinit')
        _opt('i', 'Marxa Imperial (Star Wars)')
        _opt('q', 'Tornar al menú principal')
        _end()
        op = input("  Tria: ").strip()

        if op == 'i':
            print("  → Que la Força t'acompanyi...")
            z.set_mouth('angry')
            z.play_notes(Zowi.IMPERIAL_MARCH)
            z.set_mouth('happyOpen')
        elif op == 's':
            print()
            for i, (nom, sid) in enumerate(song_list):
                print(f"    {i:>2}. {nom:<20} (ID {sid})")
            print()
            idx = _ask_int(f"Número de so (0-{len(song_list)-1})?", None)
            if idx is not None and 0 <= idx < len(song_list):
                nom = song_list[idx][0]
                print(f"  → Cantant '{nom}'...")
                z.sing(nom)
            else:
                print("  Número no vàlid.")
        elif op == 't':
            freq = _ask_int("Freqüència (Hz)?", 440)
            dur  = _ask_int("Durada (ms)?", 500)
            print(f"  → Nota {freq} Hz, {dur} ms...")
            z.tone(freq, dur)
        elif op == 'g':
            print()
            for i, (nom, gid) in enumerate(gest_list):
                print(f"    {i:>2}. {nom:<20} (ID {gid})")
            print()
            idx = _ask_int(f"Número de gest (0-{len(gest_list)-1})?", None)
            if idx is not None and 0 <= idx < len(gest_list):
                nom = gest_list[idx][0]
                print(f"  → Executant gest '{nom}'...")
                z.gesture(nom)
            else:
                print("  Número no vàlid.")
        elif op == 'q':
            break
        else:
            print("  Opció no reconeguda.")


def menu_sensors(z: Zowi):
    while True:
        _title("SENSORS I INFORMACIÓ")
        _opt('b', 'Nivell de bateria')
        _opt('d', 'Distància (ultrasònic)')
        _opt('n', 'Nivell de soroll')
        _opt('i', 'Nom del robot i firmware')
        _opt('r', 'Canviar nom del robot')
        _opt('q', 'Tornar al menú principal')
        _end()
        op = input("  Tria: ").strip()

        if op == 'b':
            v = z.get_battery()
            bar = ('█' * int(v / 10)).ljust(10)
            print(f"  Bateria: [{bar}] {v:.1f}%")
            if 0 < v < 45:
                print("  AVÍS: bateria baixa!")
        elif op == 'd':
            d = z.get_distance()
            print(f"  Distància: {d:.1f} cm", end='')
            if d < 15:
                print("  ← OBSTACLE PROPER!", end='')
            print()
        elif op == 'n':
            noise = z.get_noise()
            bar = ('█' * int(noise / 102)).ljust(10)
            print(f"  Soroll: [{bar}] {noise}/1023", end='')
            if noise >= 650:
                print("  ← SOROLL DETECTAT!", end='')
            print()
        elif op == 'i':
            name = z.get_name()
            fw   = z.get_program_id()
            print(f"  Nom:      {name!r}")
            print(f"  Firmware: {fw}")
        elif op == 'r':
            nou_nom = input("  Nou nom (màx 10 caràcters): ").strip()
            try:
                z.set_name(nou_nom)
                print(f"  → Nom canviat a {nou_nom!r}.")
            except ValueError as e:
                print(f"  Error: {e}")
        elif op == 'q':
            break
        else:
            print("  Opció no reconeguda.")


def menu_raw(z: Zowi):
    """Envia comandes en brut al robot i mostra la resposta."""
    _title("COMANDA EN BRUT")
    print("  │  Escriu la comanda directament (sense && ni %%).")
    print("  │  Exemples:  M 1 1000 15   |   L 00000000100001010010001100000000")
    print("  │  Escriu 'q' per tornar.")
    _end()
    while True:
        cmd = input("  Comanda: ").strip()
        if cmd.lower() == 'q':
            break
        if not cmd:
            continue
        z._ser.reset_input_buffer()
        z._send(cmd)
        # Llegeix fins a 3 respostes (ACK inicial, dades, ACK final)
        for _ in range(3):
            r = z._read_response(timeout=1.5)
            if r:
                print(f"  ← {r}")
            else:
                break


# ---------------------------------------------------------------------------
# Helper d'entrada numèrica
# ---------------------------------------------------------------------------

def _ask_int(prompt: str, default):
    try:
        raw = input(f"  {prompt}" + (f" [{default}]" if default is not None else "") + ": ").strip()
        return int(raw) if raw else default
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Menú principal
# ---------------------------------------------------------------------------

def main(port: str):
    print("\n╔══════════════════════════════════════╗")
    print("║      ZOWI  INTERACTIVE  CONTROLLER   ║")
    print("╚══════════════════════════════════════╝")

    with Zowi(port) as z:
        while True:
            _header(z)
            _sep()
            _title("MENÚ PRINCIPAL")
            _opt('1', 'Moviment  (caminar, girar, saltar...)')
            _opt('2', 'Cara LED  (cares, animacions...)')
            _opt('3', 'Sons i gestos')
            _opt('4', 'Sensors i informació')
            _opt('5', 'Comanda en brut')
            _opt('q', 'Sortir')
            _end()

            op = input("  Tria: ").strip()

            if op == '1':
                menu_moviment(z)
            elif op == '2':
                menu_cara(z)
            elif op == '3':
                menu_sons(z)
            elif op == '4':
                menu_sensors(z)
            elif op == '5':
                menu_raw(z)
            elif op == 'q':
                print("\n  Tornant a posició de repòs...")
                z.stop()
                z.set_mouth('happyOpen')
                break
            else:
                print("  Opció no reconeguda.")

    print("  Fins aviat!\n")


# ---------------------------------------------------------------------------
# Punt d'entrada
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) >= 2:
        port = sys.argv[1]
    else:
        ports = serial.tools.list_ports.comports()
        usable = [p for p in ports if 'USB' in p.device or 'ACM' in p.device]
        if len(usable) == 1:
            port = usable[0].device
            print(f"Port detectat automàticament: {port}")
        elif len(usable) > 1:
            print("Ports disponibles:")
            for i, p in enumerate(usable):
                print(f"  [{i}] {p.device}  ({p.description})")
            try:
                idx = int(input("Tria un número: ").strip())
                port = usable[idx].device
            except (ValueError, IndexError):
                print("Selecció no vàlida.")
                sys.exit(1)
        else:
            print("No s'ha trobat cap port sèrie USB.")
            print("Comprova que el cable està connectat i que tens permisos:")
            print("  sudo chmod 666 /dev/ttyACM0   (o el port corresponent)")
            sys.exit(1)

    main(port)
