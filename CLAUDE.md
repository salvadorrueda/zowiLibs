# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository contains Arduino firmware and libraries for the **Zowi** biped robot (by BQ). It targets the Arduino Uno/Nano (ATmega328P) platform.

## Building and Uploading

There is no Makefile or build system in the repo. Compilation is done via:

**Arduino IDE:** Install all libraries from `arduino libraries/` into your Arduino sketchbook library folder, then open any `.ino` sketch and use Sketch → Upload.

**arduino-cli:**
```bash
# Install libraries (run from repo root)
arduino-cli lib install --zip-path "arduino libraries/Zowi"
# Or copy library folders into ~/Arduino/libraries/

# Compile a sketch
arduino-cli compile --fqbn arduino:avr:uno "code .ino/ZOWI_BASE_v2"

# Upload (replace /dev/ttyUSB0 with the actual port)
arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:uno "code .ino/ZOWI_BASE_v2"

# Monitor serial output at 115200 baud
arduino-cli monitor -p /dev/ttyUSB0 --config baudrate=115200
```

Pre-compiled `.hex` files are in `code .hex/` and can be flashed directly with `avrdude`.

## Library Installation

All libraries in `arduino libraries/` must be present in the Arduino libraries path. The libraries are interdependent — `Zowi` depends on `Oscillator`, `US`, `LedMatrix`, `BatReader`, and `EnableInterrupt`.

## Architecture

### Library layer (`arduino libraries/`)

| Library | Role |
|---|---|
| `Zowi` | Top-level robot API — motion, sensors, sounds, LED face |
| `Oscillator` | Generates sinusoidal PWM for servo motors (amplitude, offset, period, phase) |
| `LedMatrix` | Drives the 5×6 shift-register LED matrix via SPI-like bit-banging (pins 11/12/13) |
| `US` | HC-SR04 ultrasonic distance sensor |
| `BatReader` | Reads battery voltage via analog pin and maps to percentage |
| `ZowiSerialCommand` | Parses serial commands; a stripped-down SerialCommand with SoftwareSerial removed to avoid interrupt conflicts |
| `EnableInterrupt` | Third-party library for pin-change interrupts on all Arduino pins |

`Zowi.h` aggregates all the above and exposes the full robot API. Motion is produced by calling `oscillateServos()` which drives 4 `Oscillator` instances (YL, YR, RL, RR servos) with sinusoidal signals at configured amplitude/offset/phase.

Static data (mouth bitmaps, sound sequences, gesture definitions) lives in the companion headers `Zowi_mouths.h`, `Zowi_sounds.h`, and `Zowi_gestures.h`.

### Firmware layer (`code .ino/`)

**`ZOWI_BASE_v2/ZOWI_BASE_v2.ino`** — Main production firmware. Implements a 5-mode state machine:

| MODE | Description |
|---|---|
| 0 | Idle / awaiting — sleeps after 80 s of inactivity |
| 1 | Dance — random movements in a loop |
| 2 | Obstacle detector — walks forward, backs up on detection |
| 3 | Noise detector — dances when noise threshold (≥650) is exceeded |
| 4 | Teleoperation — reads serial commands from ZowiPAD or any controller |

Mode switches via physical buttons (pins 6 and 7, using `EnableInterrupt`). Serial input automatically forces MODE 4.

### Serial protocol

Commands and responses are framed as `&&<DATA>%%\r\n` at 115200 baud.

**Commands (host → robot):**

| Code | Action |
|---|---|
| `S` | Stop / home |
| `L <bits>` | Set LED matrix (33-bit binary string) |
| `T <freq> <ms>` | Play tone |
| `M <id> <T> <size>` | Execute movement (IDs 0–20) |
| `H <id>` | Play gesture (IDs 1–13) |
| `K <id>` | Sing sound (IDs 1–19) |
| `C <YL> <YR> <RL> <RR>` | Set and save servo trims to EEPROM |
| `G <YL> <YR> <RL> <RR>` | Move servos to absolute positions |
| `R <name>` | Set robot name (stored in EEPROM at address 5) |

**Responses (robot → host):** `E` (name), `D` (distance cm), `N` (noise), `B` (battery %), `I` (program ID), `A` (ack), `F` (final ack).

### Servo pinout

```
PIN_YL = 2  (left hip)
PIN_YR = 3  (right hip)
PIN_RL = 4  (left foot)
PIN_RR = 5  (right foot)
```

Trims are calibrated once and persisted to EEPROM. Robot name is stored at EEPROM address 5 (max 10 chars).


### Actualitzant amb línia de comandes

Connectat per USB. 
Comprovar al journaclt -f que apareix /dev/ttyUSB0

Executar avrdude i després de 3 attempts 
Click al botó power de Zowi


root@d00:/home/salvadorrueda/Developer/GitHub/zowilibs/code .hex# avrdude -c arduino -p m328p -P /dev/ttyUSB0 -b 115200 -U flash:w:./ZOWI_BASE_v2.hex 
avrdude error: programmer is not responding
avrdude warning: attempt 1 of 10: not in sync: resp=0x00
avrdude error: programmer is not responding
avrdude warning: attempt 2 of 10: not in sync: resp=0x00
avrdude warning: attempt 3 of 10: not in sync: resp=0x26

avrdude: AVR device initialized and ready to accept instructions
avrdude: device signature = 0x1e950f (probably m328p)
avrdude: Note: flash memory has been specified, an erase cycle will be performed.
         To disable this feature, specify the -D option.
avrdude: erasing chip
avrdude: reading input file ./ZOWI_BASE_v2.hex for flash
         with 30446 bytes in 1 section within [0, 0x76ed]
         using 238 pages and 18 pad bytes
avrdude: writing 30446 bytes flash ...

Writing | ################################################## | 100% 4.23 s 

avrdude: 30446 bytes of flash written
avrdude: verifying flash memory against ./ZOWI_BASE_v2.hex

Reading | ################################################## | 100% 3.09 s 

avrdude: 30446 bytes of flash verified

avrdude done.  Thank you.

root@d00:/home/salvadorrueda/Developer/GitHub/zowilibs/code .hex#



