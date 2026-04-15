#!/usr/bin/env python3
"""
zowi.py — Biblioteca Python per controlar el robot Zowi per USB o Bluetooth.

Instal·lació:
    pip install pyserial

Ús com a biblioteca:
    from zowi import Zowi

    with Zowi('/dev/ttyUSB0') as z:
        print(z.get_name(), z.get_battery())
        z.walk(steps=2)
        z.jump()
        z.set_mouth('heart')

Ús com a demo:
    python zowi.py /dev/ttyUSB0

Protocol:
    - Comandes enviades al robot:  text pla  →  'M 1 1000 15\\r\\n'
    - Respostes del robot:  embolcallades  →  '&&A%%\\r\\n', '&&B 85.5%%\\r\\n'
    - El robot canvia automàticament a mode teleoperació en rebre dades.
    - L'Arduino es reinicia en obrir el port → esperar ~2 s abans d'enviar.
"""

import re
import sys
import time
import unicodedata

import serial
import serial.tools.list_ports


class Zowi:
    """Controlador del robot Zowi via port sèrie."""

    # ------------------------------------------------------------------
    # Cares predefinides (enters de 32 bits, d'acord amb Zowi_mouths.h)
    # L'ordre és el mateix que a getMouthShape(): ID 0='0', 1='1', ..., 10='smile', ...
    # ------------------------------------------------------------------
    FACES = {
        '0':             0b00001100010010010010010010001100,
        '1':             0b00000100001100000100000100001110,
        '2':             0b00001100010010000100001000011110,
        '3':             0b00001100010010000100010010001100,
        '4':             0b00010010010010011110000010000010,
        '5':             0b00011110010000011100000010011100,
        '6':             0b00000100001000011100010010001100,
        '7':             0b00011110000010000100001000010000,
        '8':             0b00001100010010001100010010001100,
        '9':             0b00001100010010001110000010001110,
        'smile':         0b00000000100001010010001100000000,
        'happyOpen':     0b00000000111111010010001100000000,
        'happyClosed':   0b00000000111111011110000000000000,
        'heart':         0b00010010101101100001010010001100,
        'bigSurprise':   0b00001100010010100001010010001100,
        'smallSurprise': 0b00000000000000001100001100000000,
        'tongueOut':     0b00111111001001001001000110000000,
        'vamp1':         0b00111111101101101101010010000000,
        'vamp2':         0b00111111101101010010000000000000,
        'lineMouth':     0b00000000000000111111000000000000,
        'confused':      0b00000000001000010101100010000000,
        'diagonal':      0b00100000010000001000000100000010,
        'sad':           0b00000000001100010010100001000000,
        'sadOpen':       0b00000000001100010010111111000000,
        'sadClosed':     0b00000000001100011110110011000000,
        'okMouth':       0b00000001000010010100001000000000,
        'xMouth':        0b00100001010010001100010010100001,
        'interrogation': 0b00001100010010000100000100000100,
        'thunder':       0b00000100001000011100001000010000,
        'culito':        0b00000000100001101101010010000000,
        'angry':         0b00000000011110100001100001000000,
    }

    # Llista de valors de cares en ordre d'ID (0-30), per lookup per índex numèric
    _FACE_BY_ID = list(FACES.values())

    # ------------------------------------------------------------------
    # Font 5×5 (files) per generar scroll en matriu real 5×6 (cols)
    # Cada caràcter: tuple de 5 strings (files), cada string té 5 columns.
    # ------------------------------------------------------------------
    CHAR_FONT = {
        ' ': ("00000", "00000", "00000", "00000", "00000"),
        'A': ("01110", "10001", "11111", "10001", "10001"),
        'B': ("11110", "10001", "11110", "10001", "11110"),
        'C': ("01110", "10001", "10000", "10001", "01110"),
        'D': ("11110", "10001", "10001", "10001", "11110"),
        'E': ("11111", "10000", "11110", "10000", "11111"),
        'F': ("11111", "10000", "11110", "10000", "10000"),
        'G': ("01110", "10000", "10111", "10001", "01110"),
        'H': ("10001", "10001", "11111", "10001", "10001"),
        'I': ("11111", "00100", "00100", "00100", "11111"),
        'J': ("00001", "00001", "00001", "10001", "01110"),
        'K': ("10001", "10010", "11100", "10010", "10001"),
        'L': ("10000", "10000", "10000", "10000", "11111"),
        'M': ("10001", "11011", "10101", "10001", "10001"),
        'N': ("10001", "11001", "10101", "10011", "10001"),
        'O': ("01110", "10001", "10001", "10001", "01110"),
        'P': ("11110", "10001", "11110", "10000", "10000"),
        'Q': ("01110", "10001", "10001", "10011", "01111"),
        'R': ("11110", "10001", "11110", "10010", "10001"),
        'S': ("01111", "10000", "01110", "00001", "11110"),
        'T': ("11111", "00100", "00100", "00100", "00100"),
        'U': ("10001", "10001", "10001", "10001", "01110"),
        'V': ("10001", "10001", "10001", "01010", "00100"),
        'W': ("10001", "10001", "10101", "11011", "10001"),
        'X': ("10001", "01010", "00100", "01010", "10001"),
        'Y': ("10001", "01010", "00100", "00100", "00100"),
        'Z': ("11111", "00010", "00100", "01000", "11111"),
        '0': ("01110", "10011", "10101", "11001", "01110"),
        '1': ("00100", "01100", "00100", "00100", "01110"),
        '2': ("01110", "10001", "00010", "00100", "11111"),
        '3': ("11110", "00001", "00110", "00001", "11110"),
        '4': ("10010", "10010", "11111", "00010", "00010"),
        '5': ("11111", "10000", "11110", "00001", "11110"),
        '6': ("01110", "10000", "11110", "10001", "01110"),
        '7': ("11111", "00010", "00100", "01000", "01000"),
        '8': ("01110", "10001", "01110", "10001", "01110"),
        '9': ("01110", "10001", "01111", "00001", "01110"),
        '.': ("00000", "00000", "00000", "00110", "00110"),
        ',': ("00000", "00000", "00000", "00110", "00100"),
        ':': ("00000", "00110", "00000", "00110", "00000"),
        '!': ("00100", "00100", "00100", "00000", "00100"),
        '?': ("01110", "00001", "00110", "00000", "00100"),
        '-': ("00000", "00000", "01110", "00000", "00000"),
    }

    # Animació littleUuh (8 frames)
    ANIM_LITTLE_UUH = [
        0b00000000000000001100001100000000,
        0b00000000000000000110000110000000,
        0b00000000000000000011000011000000,
        0b00000000000000000110000110000000,
        0b00000000000000001100001100000000,
        0b00000000000000011000011000000000,
        0b00000000000000110000110000000000,
        0b00000000000000011000011000000000,
    ]

    # Sons predefinits
    SONGS = {
        'connection': 1, 'disconnection': 2, 'buttonPushed': 3,
        'mode1': 4, 'mode2': 5, 'mode3': 6,
        'surprise': 7, 'OhOoh': 8, 'OhOoh2': 9,
        'cuddly': 10, 'sleeping': 11,
        'happy': 12, 'superHappy': 13, 'happy_short': 14,
        'sad': 15, 'confused': 16,
        'fart1': 17, 'fart2': 18, 'fart3': 19,
    }

    # Gestos predefinits
    GESTURES = {
        'happy': 1, 'superHappy': 2, 'sad': 3, 'sleeping': 4,
        'fart': 5, 'confused': 6, 'love': 7, 'angry': 8,
        'fretful': 9, 'magic': 10, 'wave': 11, 'victory': 12, 'fail': 13,
    }

    # ------------------------------------------------------------------
    # La Marxa Imperial (Star Wars) — llista de (freq_hz, durada_ms)
    # Tempo: 100 BPM  →  Q=600ms  E=300ms  S=150ms  DE=450ms  H=1200ms
    # freq=0 indica silenci/pausa
    # ------------------------------------------------------------------
    IMPERIAL_MARCH = [
        # Frase 1: G G G  Eb(.) Bb  G  Eb(.) Bb  G(mitja)
        (392, 600),   # G4  Q
        (392, 600),   # G4  Q
        (392, 600),   # G4  Q
        (311, 450),   # Eb4 DE
        (466, 150),   # Bb4 S
        (392, 600),   # G4  Q
        (311, 450),   # Eb4 DE
        (466, 150),   # Bb4 S
        (392, 1200),  # G4  H

        # Frase 2: D5 D5 D5  Eb5(.) Bb4  Gb4  Eb4(.) Bb4  G4(mitja)
        (587, 600),   # D5  Q
        (587, 600),   # D5  Q
        (587, 600),   # D5  Q
        (622, 450),   # Eb5 DE
        (466, 150),   # Bb4 S
        (370, 600),   # Gb4 Q
        (311, 450),   # Eb4 DE
        (466, 150),   # Bb4 S
        (392, 1200),  # G4  H

        # Frase 3 — pujada: G5  G4(.) G4  G5  Gb5(.) F5  E5 Eb5 E5 silenci Ab4 Db5
        (784, 600),   # G5  Q
        (392, 450),   # G4  DE
        (392, 150),   # G4  S
        (784, 600),   # G5  Q
        (740, 450),   # Gb5 DE
        (698, 150),   # F5  S
        (659, 150),   # E5  S
        (622, 150),   # Eb5 S
        (659, 300),   # E5  E
        (0,   300),   # silenci E
        (415, 300),   # Ab4 E
        (554, 600),   # Db5 Q

        # Frase 4 — baixada: C5(.) B4 Bb4 A4 Bb4 silenci Eb4 Gb4 Eb4(.) Gb4 Bb4 G4(.) Bb4 D5(mitja)
        (523, 450),   # C5  DE
        (494, 150),   # B4  S
        (466, 150),   # Bb4 S
        (440, 150),   # A4  S
        (466, 300),   # Bb4 E
        (0,   300),   # silenci E
        (311, 300),   # Eb4 E
        (370, 600),   # Gb4 Q
        (311, 450),   # Eb4 DE
        (370, 150),   # Gb4 S
        (466, 600),   # Bb4 Q
        (392, 450),   # G4  DE
        (466, 150),   # Bb4 S
        (587, 1200),  # D5  H
    ]

    # IDs de moviment (per usar amb move())
    STOP          = 0
    WALK_FORWARD  = 1
    WALK_BACKWARD = 2
    TURN_LEFT     = 3
    TURN_RIGHT    = 4
    UPDOWN        = 5
    MOONWALK_L    = 6
    MOONWALK_R    = 7
    SWING         = 8
    CRUSAITO_FWD  = 9
    CRUSAITO_BWD  = 10
    JUMP          = 11
    FLAPPING_FWD  = 12
    FLAPPING_BWD  = 13
    TIPTOE_SWING  = 14
    BEND_LEFT     = 15
    BEND_RIGHT    = 16
    SHAKE_LEG_R   = 17
    SHAKE_LEG_L   = 18
    JITTER        = 19
    ASCENDING_TURN = 20

    # ------------------------------------------------------------------
    # Cicle de vida
    # ------------------------------------------------------------------

    def __init__(self, port: str = '/dev/ttyUSB0', baud: int = 115200,
                 timeout: float = 10.0):
        """
        Obre la connexió sèrie amb el Zowi.

        Args:
            port:    Port sèrie (ex: '/dev/ttyUSB0', '/dev/ttyACM0').
            baud:    Velocitat (115200 per defecte, no cal canviar).
            timeout: Timeout en segons per esperar respostes del robot.
        """
        self._timeout = timeout
        print(f"Connectant a {port}...", end=' ', flush=True)
        self._ser = serial.Serial(port, baud, timeout=1)
        # L'Arduino es reinicia en obrir el port; espera obligatòria.
        time.sleep(2)
        self._ser.reset_input_buffer()
        print("llest.")

    def close(self):
        """Tanca la connexió sèrie."""
        if self._ser and self._ser.is_open:
            self._ser.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------
    # Comunicació interna
    # ------------------------------------------------------------------

    def _send(self, cmd: str):
        """Envia una comanda (el robot espera \\r\\n com a terminador)."""
        self._ser.write((cmd + '\r\n').encode('ascii'))

    def _read_response(self, timeout: float = 2.0) -> str:
        """
        Llegeix del port fins trobar la trama '&&...%%'.
        Retorna el contingut interior, o '' si s'esgota el timeout.
        """
        deadline = time.time() + timeout
        buf = ''
        while time.time() < deadline:
            waiting = self._ser.in_waiting
            chunk = self._ser.read(waiting if waiting else 1)
            buf += chunk.decode('ascii', errors='ignore')
            m = re.search(r'&&(.+?)%%', buf)
            if m:
                return m.group(1).strip()
        return ''

    def _wait_ack(self, timeout: float = 3.0) -> bool:
        """Espera l'ACK inicial '&&A%%'. Retorna True si arriba."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self._read_response(timeout=0.5)
            if r == 'A':
                return True
        return False

    def _wait_final_ack(self, timeout: float = None) -> bool:
        """Espera l'ACK final '&&F%%'. Retorna True si arriba."""
        if timeout is None:
            timeout = self._timeout
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self._read_response(timeout=0.5)
            if r == 'F':
                return True
        return False

    def _query(self, cmd: str, timeout: float = 3.0) -> str:
        """Envia una consulta i retorna el valor de la resposta (sense el prefix)."""
        self._ser.reset_input_buffer()
        self._send(cmd)
        raw = self._read_response(timeout)
        # La resposta és "X valor" (ex: "B 85.5"). Elimina el prefix de lletra.
        parts = raw.split(None, 1)
        return parts[1] if len(parts) > 1 else raw

    # ------------------------------------------------------------------
    # Moviment
    # ------------------------------------------------------------------

    def move(self, move_id: int, T: int = 1000, h: int = 15):
        """
        Executa un moviment per ID. Retorna quan el robot ha rebut la comanda.

        Args:
            move_id: ID 0-20. Usa les constants (ex: Zowi.JUMP, Zowi.WALK_FORWARD).
            T:       Durada d'un cicle en ms (típic: 800-2000).
            h:       Amplitud/alçada en graus (típic: 5-30).
        """
        self._send(f'M {move_id} {T} {h}')
        self._wait_ack()

    def walk(self, steps: int = 2, T: int = 1000, direction: str = 'forward'):
        """
        Fa caminar el robot.

        Args:
            steps:     Nombre de passos.
            T:         Durada de cada pas en ms (recomanat: 800-1200).
            direction: 'forward' o 'backward'.
        """
        move_id = self.WALK_FORWARD if direction == 'forward' else self.WALK_BACKWARD
        for _ in range(steps):
            self.move(move_id, T)
            time.sleep(T / 1000.0)

    def turn(self, steps: int = 2, T: int = 1000, direction: str = 'left'):
        """
        Fa girar el robot.

        Args:
            steps:     Nombre de passos de gir.
            T:         Durada en ms.
            direction: 'left' o 'right'.
        """
        move_id = self.TURN_LEFT if direction == 'left' else self.TURN_RIGHT
        for _ in range(steps):
            self.move(move_id, T)
            time.sleep(T / 1000.0)

    def jump(self, T: int = 1000):
        """Fa saltar el robot."""
        self.move(self.JUMP, T)
        time.sleep(T / 1000.0 * 2)

    def swing(self, steps: int = 1, T: int = 1000, h: int = 20):
        """Balanceig lateral."""
        for _ in range(steps):
            self.move(self.SWING, T, h)
            time.sleep(T / 1000.0)

    def stop(self):
        """Para el robot i el porta a la posició de repòs (tots els servos a 90°)."""
        self._send('S')
        self._wait_ack()

    def set_servos(self, YL: int, YR: int, RL: int, RR: int):
        """
        Mou els 4 servos a posicions absolutes en 200 ms.

        Args:
            YL, YR: Malucs esquerre i dret (0-180°). Repòs = 90.
            RL, RR: Peus esquerre i dret (0-180°). Repòs = 90.
        """
        self._send(f'G {YL} {YR} {RL} {RR}')
        self._wait_ack()

    # ------------------------------------------------------------------
    # Cara LED
    # ------------------------------------------------------------------

    def set_mouth(self, face):
        """
        Mostra una cara a la matriu LED 5×6.

        Args:
            face: - Nom de string: 'smile', 'heart', 'sad', 'angry', '0'..'9', etc.
                  - ID numèric (int 0-30): el mateix ordre que al firmware.
                  - Enter de 32 bits: cara personalitzada.

        Exemples:
            z.set_mouth('smile')
            z.set_mouth(10)        # equivalent a 'smile'
            z.set_mouth(0b00000000100001010010001100000000)  # bitmap propi
        """
        if isinstance(face, str):
            value = self.FACES.get(face)
            if value is None:
                available = ', '.join(f"'{k}'" for k in self.FACES)
                raise ValueError(f"Cara desconeguda: '{face}'.\nDisponibles: {available}")
        elif isinstance(face, int) and 0 <= face <= 30:
            value = self._FACE_BY_ID[face]
        elif isinstance(face, int):
            value = face  # bitmap personalitzat
        else:
            raise TypeError("face ha de ser str, int (ID 0-30) o int (bitmap 32 bits)")

        self._send(f'L {value:032b}')
        self._wait_ack()

    def clear_mouth(self):
        """Apaga tots els LEDs de la cara."""
        self._send('L ' + '0' * 32)
        self._wait_ack()

    def animate_mouth(self, frames: list, delay: float = 0.15, repeat: int = 1):
        """
        Reprodueix una animació de múltiples frames a la cara.

        Args:
            frames: Llista d'enters de 32 bits (ex: Zowi.ANIM_LITTLE_UUH).
            delay:  Temps en segons entre frames.
            repeat: Nombre de vegades que es repeteix l'animació.
        """
        for _ in range(repeat):
            for frame in frames:
                self._send(f'L {frame:032b}')
                self._wait_ack()
                time.sleep(delay)

    def scroll_text(self, text: str, delay: float = 0.3, repeat: int = 1):
        """
        Fa scroll de text a la matriu LED 5×6.

        Args:
            text:   Text a mostrar (es converteix a majúscules).
            delay:  Temps en segons per cada frame del scroll.
            repeat: Nombre de vegades que es repeteix el scroll.
        """
        normalized = unicodedata.normalize('NFD', text.upper())
        normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')

        # Construeix stream de columnes (cada columna = 5 files)
        columns = [[0, 0, 0, 0, 0] for _ in range(6)]  # espai d'entrada

        for char in normalized:
            glyph = self.CHAR_FONT.get(char, self.CHAR_FONT[' '])
            for col_idx in range(5):
                column = [1 if glyph[row_idx][col_idx] == '1' else 0 for row_idx in range(5)]
                columns.append(column)
            columns.append([0, 0, 0, 0, 0])  # separació entre lletres

        columns.extend([[0, 0, 0, 0, 0] for _ in range(6)])  # espai de sortida

        # Finestra visible: 6 columnes (matriu 5x6)
        for _ in range(repeat):
            for offset in range(len(columns) - 5):
                window = columns[offset:offset + 6]

                bitmap = 0
                for row in range(5):
                    for col in range(6):
                        if window[col][row]:
                            linear_index = row * 6 + col  # row-major
                            bit_index = 29 - linear_index
                            bitmap |= (1 << bit_index)

                self._send(f'L {bitmap:032b}')
                self._wait_ack()
                time.sleep(delay)

    # ------------------------------------------------------------------
    # Sons
    # ------------------------------------------------------------------

    def sing(self, song):
        """
        Reprodueix un so predefinit.

        Args:
            song: Nom del so (str) o ID numèric (int 1-19).
                  Noms: 'happy', 'sad', 'connection', 'surprise', 'fart1', etc.
        """
        if isinstance(song, str):
            song_id = self.SONGS.get(song)
            if song_id is None:
                available = ', '.join(f"'{k}'" for k in self.SONGS)
                raise ValueError(f"So desconegut: '{song}'.\nDisponibles: {available}")
        else:
            song_id = int(song)
        self._send(f'K {song_id}')
        self._wait_ack()

    def tone(self, freq_hz: int, duration_ms: int):
        """
        Toca una nota amb el brunzidor.

        Args:
            freq_hz:     Freqüència en Hz (ex: 440=La4, 523=Do5, 880=La5).
            duration_ms: Durada en mil·lisegons.
        """
        self._send(f'T {freq_hz} {duration_ms}')
        self._wait_ack()

    def play_notes(self, notes: list, gap_ms: int = 25):
        """
        Reprodueix una seqüència de notes.

        Cada nota és una tupla (freq_hz, duration_ms).
        freq_hz = 0 indica un silenci de duration_ms mil·lisegons.

        Args:
            notes:  Llista de tuples (freq_hz, duration_ms).
            gap_ms: Silenci entre notes en ms (per separació musical natural).

        Exemple:
            z.play_notes(Zowi.IMPERIAL_MARCH)
            z.play_notes([(440, 500), (0, 200), (523, 500)])
        """
        for freq, duration in notes:
            if freq == 0:
                time.sleep(duration / 1000.0)
            else:
                # Envia la nota amb durada lleugerament escurçada per crear
                # una separació natural entre notes consecutives.
                play_dur = max(30, duration - gap_ms)
                self._send(f'T {freq} {play_dur}')
                self._wait_ack()
                time.sleep(duration / 1000.0)

    # ------------------------------------------------------------------
    # Gestos (moviment + so + cara combinats)
    # ------------------------------------------------------------------

    def gesture(self, gest):
        """
        Executa un gest predefinit (moviment + so + cara coordinats).

        Args:
            gest: Nom del gest (str) o ID numèric (int 1-13).
                  Noms: 'happy', 'sad', 'love', 'angry', 'confused', 'victory', etc.
        """
        if isinstance(gest, str):
            gest_id = self.GESTURES.get(gest)
            if gest_id is None:
                available = ', '.join(f"'{k}'" for k in self.GESTURES)
                raise ValueError(f"Gest desconegut: '{gest}'.\nDisponibles: {available}")
        else:
            gest_id = int(gest)
        self._send(f'H {gest_id}')
        self._wait_ack()

    # ------------------------------------------------------------------
    # Sensors i informació
    # ------------------------------------------------------------------

    def get_name(self) -> str:
        """Retorna el nom del robot (guardat a EEPROM)."""
        return self._query('E')

    def get_battery(self) -> float:
        """Retorna el nivell de bateria en percentatge (0.0–100.0)."""
        try:
            return float(self._query('B'))
        except ValueError:
            return -1.0

    def get_distance(self) -> float:
        """Retorna la distància mesurada per l'ultrasònic en cm."""
        try:
            return float(self._query('D'))
        except ValueError:
            return -1.0

    def get_noise(self) -> int:
        """Retorna el nivell de soroll (0–1023). El llindar de detecció del firmware és ≥ 650."""
        try:
            return int(self._query('N'))
        except ValueError:
            return -1

    def get_program_id(self) -> str:
        """Retorna l'identificador del firmware que executa el robot (ex: 'ZOWI_BASE_v2')."""
        return self._query('I')

    # ------------------------------------------------------------------
    # Configuració persistent (EEPROM)
    # ------------------------------------------------------------------

    def set_name(self, name: str):
        """
        Canvia el nom del robot (màxim 10 caràcters). Es guarda a EEPROM.
        """
        if len(name) > 10:
            raise ValueError("El nom no pot tenir més de 10 caràcters")
        self._send(f'R {name}')
        self._wait_ack()

    def set_trims(self, YL: int, YR: int, RL: int, RR: int):
        """
        Calibra els servos amb valors de correcció en graus (positiu o negatiu).
        Es guarda a EEPROM i es carrega automàticament a cada arrenç.

        Args:
            YL, YR: Correcció dels malucs esquerre i dret.
            RL, RR: Correcció dels peus esquerre i dret.

        Exemple: z.set_trims(5, -3, 0, 2)
        """
        self._send(f'C {YL} {YR} {RL} {RR}')
        self._wait_ack()


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo(port: str):
    """Demostració completa: connexió → cara → caminar → saltar → animació."""

    print("\n╔══════════════════════════╗")
    print("║     DEMO ZOWI  (Python)  ║")
    print("╚══════════════════════════╝\n")

    with Zowi(port) as z:

        # Informació inicial
        name    = z.get_name()
        battery = z.get_battery()
        fw      = z.get_program_id()
        print(f"Robot:    {name!r}")
        print(f"Firmware: {fw}")
        print(f"Bateria:  {battery:.1f}%")
        if 0 < battery < 45:
            print("AVÍS: bateria baixa, considera carregar el robot.")
        print()

        # 1. Salutació
        print("[1/5] Salutació...")
        z.set_mouth('happyOpen')
        z.sing('connection')
        time.sleep(0.5)

        # 2. Animació de sorpresa
        print("[2/5] Animació littleUuh...")
        z.animate_mouth(Zowi.ANIM_LITTLE_UUH, delay=0.12, repeat=2)

        # 3. Caminar endavant
        print("[3/5] Caminant endavant (2 passos)...")
        z.set_mouth('smile')
        z.walk(steps=2, T=1000, direction='forward')
        time.sleep(0.3)

        # 4. Salt
        print("[4/5] Saltant!")
        z.set_mouth('bigSurprise')
        z.jump(T=800)
        time.sleep(0.3)

        # 5. Cara de cor i so feliç
        print("[5/5] Content!")
        z.set_mouth('heart')
        z.sing('happy_short')
        time.sleep(1.0)

        # Repòs
        print("\nTornant a posició de repòs...")
        z.set_mouth('happyOpen')
        z.stop()

    print("\nFet! Connexió tancada.\n")


# ---------------------------------------------------------------------------
# Punt d'entrada
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        print("Ports sèrie detectats:")
        ports = serial.tools.list_ports.comports()
        if ports:
            for p in ports:
                print(f"  {p.device:<20} {p.description}")
        else:
            print("  (cap port detectat)")
        print("\nUsa: python zowi.py <port>")
        print("Ex:  python zowi.py /dev/ttyUSB0")
        sys.exit(1)

    demo(sys.argv[1])
