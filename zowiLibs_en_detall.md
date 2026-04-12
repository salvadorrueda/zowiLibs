# zowiLibs explicat en detall

Aquest document explica de forma exhaustiva el contingut d'aquest repositori: com funciona el codi del robot Zowi, com s'estructura, i com es pot modificar i actualitzar.

---

## Taula de continguts

1. [Visió general del repositori](#1-visió-general-del-repositori)
2. [El maquinari del Zowi](#2-el-maquinari-del-zowi)
3. [Com funciona el moviment: l'oscil·lador](#3-com-funciona-el-moviment-loscillador)
4. [La biblioteca principal: Zowi](#4-la-biblioteca-principal-zowi)
5. [La cara LED: LedMatrix](#5-la-cara-led-ledmatrix)
6. [Els sensors](#6-els-sensors)
7. [Els sons](#7-els-sons)
8. [Els gestos](#8-els-gestos)
9. [La comunicació sèrie: ZowiSerialCommand](#9-la-comunicació-sèrie-zowiserialcommand)
10. [El firmware principal: ZOWI_BASE_v2](#10-el-firmware-principal-zowi_base_v2)
11. [La màquina d'estats: els 5 modes de Zowi](#11-la-màquina-destats-els-5-modes-de-zowi)
12. [L'EEPROM: memòria persistent](#12-leeprom-memòria-persistent)
13. [Com actualitzar el robot](#13-com-actualitzar-el-robot)
14. [Com modificar el comportament](#14-com-modificar-el-comportament)
15. [Els fitxers de jocs](#15-els-fitxers-de-jocs)
16. [El sketch de fàbrica](#16-el-sketch-de-fàbrica)

---

## 1. Visió general del repositori

```
zowiLibs/
├── arduino libraries/       ← Les biblioteques que s'instal·len a l'Arduino IDE
│   ├── Zowi/                ← Biblioteca principal del robot
│   ├── Oscillator/          ← Motor del moviment sinusoidal
│   ├── LedMatrix/           ← Control de la cara LED
│   ├── US/                  ← Sensor d'ultrasons
│   ├── BatReader/           ← Lectura de bateria
│   ├── ZowiSerialCommand/   ← Parser de comandes sèrie (Bluetooth/USB)
│   └── EnableInterrupt/     ← Gestió d'interrupcions de botons
├── code .ino/               ← Sketches (programes) Arduino
│   ├── ZOWI_BASE_v2/        ← Firmware de producció
│   └── games/               ← Jocs opcionals
├── code .hex/               ← Fitxers binaris precompilats (es poden pujar directament)
└── factoryZowi/             ← Sketch de calibratge de fàbrica
```

Tot el codi és **C++ per a Arduino** (plataforma ATmega328P: Arduino Uno, Nano o el propi controlador del Zowi). No hi ha sistema de compilació propi; s'usa l'Arduino IDE o `arduino-cli`.

---

## 2. El maquinari del Zowi

El Zowi té 4 servomotors distribuïts en 2 articulacions per cama:

```
         ┌───────────────┐
         │    cara LED   │
         │   O       O   │
 YR ───► │               │ ◄─── YL      (malucs: girar cap als costats)
         └───────────────┘
              │       │
 RR ───►  ──────   ──────  ◄─── RL      (peus: girar cap a endavant/enrere)
          ──────   ──────
```

| Variable | Pin | Articulació |
|---|---|---|
| `PIN_YL` | 2 | Maluc esquerre (Yaw Left) |
| `PIN_YR` | 3 | Maluc dret (Yaw Right) |
| `PIN_RL` | 4 | Peu esquerre (Roll Left) |
| `PIN_RR` | 5 | Peu dret (Roll Right) |

Altres pins fixos:

| Funció | Pin |
|---|---|
| Brunzidor (buzzer) | 10 |
| Trigger ultrasons | 8 |
| Echo ultrasons | 9 |
| Sensor de soroll | A6 |
| Bateria | A7 |
| Botó 2 | 6 |
| Botó 3 | 7 |
| Cara LED (SER) | 11 |
| Cara LED (RCK) | 12 |
| Cara LED (CLK) | 13 |

---

## 3. Com funciona el moviment: l'oscil·lador

La biblioteca `Oscillator` és el cor del moviment. En lloc de programar posicions concretes per a cada pas, **cada servomotor segueix una ona sinusoidal**:

```
posició(t) = A · sin(ωt + φ₀) + O
```

On:
- **A** = amplitud en graus (quant es mou)
- **O** = offset en graus (posició central de l'oscil·lació)
- **T** = període en mil·lisegons (quant triga un cicle complet)
- **φ₀** = fase inicial en radians (quan dins del cicle comença)

El mètode `refresh()` de cada oscil·lador es crida contínuament al bucle principal. Cada **30 ms** (`_TS = 30`) calcula la nova posició del servo:

```cpp
// Oscillator.cpp:116-117
_pos = round(_A * sin(_phase + _phase0) + _O);
_servo.write(_pos + 90 + _trim);
```

La posició de repòs és 90°. El trim és una correcció per calibrar el servo físic.

### Com es combinen els 4 oscil·ladors per caminar

El mètode `walk()` defineix els paràmetres de tots 4 servos alhora:

```cpp
// Zowi.cpp:209-214
int A[4]= {30, 30, 20, 20};              // amplituds
int O[4] = {0, 0, 4, -4};               // offsets (lleugera punta de peu)
double phase_diff[4] = {0, 0, DEG2RAD(dir * -90), DEG2RAD(dir * -90)};
```

- Els **malucs** (YL, YR) oscil·len en fase (0°) amb amplitud 30°: fan el balanceig lateral.
- Els **peus** (RL, RR) van 90° desfasats respecte als malucs: quan el maluc arriba al punt extrem, el peu avança.
- Per caminar **enrere**, el desfasament és +90° en lloc de -90°.

Per **girar**, s'aplica el mateix principi però amb amplituds asimètriques entre maluc esquerre i dret:

```cpp
// Per girar a l'esquerra: el maluc esquerre va més lluny
A[0] = 30; // maluc esquerre: passos grans
A[1] = 10; // maluc dret: passos petits → l'arc descriu cap a l'esquerra
```

---

## 4. La biblioteca principal: Zowi

`arduino libraries/Zowi/Zowi.h` i `Zowi.cpp` exposen tota l'API del robot.

### Inicialització

```cpp
zowi.init(PIN_YL, PIN_YR, PIN_RL, PIN_RR, true);
//                                          ↑ carregar calibratge des de EEPROM
```

En la inicialització:
1. S'assignen els pins dels 4 servos.
2. Es carreguen els **trims** de calibratge de l'EEPROM (bytes 0–3).
3. Es posicionen tots els servos a 90° (posició de repòs).
4. S'inicialitza el sensor d'ultrasons.
5. Es configuren els pins del brunzidor i del micròfon.

### Repòs: `home()`

```cpp
zowi.home();
```

Mou tots els servos suaument a 90° en 500 ms i després els **desconnecta** (`detach`). Desconnectar els servos evita que consumeixin corrent i que vibrin en posició de repòs. La variable `isZowiResting` evita repetir el moviment si ja és a la posició de repòs.

### Moviments disponibles

Tots accepten `steps` (nombre de cicles) i `T` (durada d'un cicle en ms):

| Mètode | Descripció |
|---|---|
| `walk(steps, T, dir)` | Caminar endavant (`FORWARD=1`) o enrere (`BACKWARD=-1`) |
| `turn(steps, T, dir)` | Girar a l'esquerra (`LEFT=1`) o dreta (`RIGHT=-1`) |
| `bend(steps, T, dir)` | Inclinar-se lateralment |
| `shakeLeg(steps, T, dir)` | Sacsejar una cama |
| `updown(steps, T, h)` | Pujar i baixar (salt in situ) |
| `swing(steps, T, h)` | Balanceig lateral |
| `tiptoeSwing(steps, T, h)` | Balanceig de puntetes |
| `jitter(steps, T, h)` | Tremolor ràpid dels malucs |
| `ascendingTurn(steps, T, h)` | Gir amb pujada progressiva |
| `moonwalker(steps, T, h, dir)` | Desplaçament lateral (moonwalk) |
| `crusaito(steps, T, h, dir)` | Combinació moonwalk + marxa |
| `flapping(steps, T, h, dir)` | Moviment de braços (ales) |
| `jump(steps, T)` | Salt simple |

El paràmetre `h` (height) mesura l'amplitud del moviment en graus (5=SMALL, 15=MEDIUM, 30=BIG).

---

## 5. La cara LED: LedMatrix

La cara del Zowi és una matriu LED de **5 files × 6 columnes = 30 LEDs**. Es controla amb un registre de desplaçament (**shift register**) connectat als pins SER(11), CLK(13), RCK(12).

El valor de cada cara és un **enter de 32 bits** (un `unsigned long`) on cada bit representa un LED. Les definicions estan a `Zowi_mouths.h`:

```
// Exemple: smile_code
0b00000000100001010010001100000000
   ││││││││││││││││││││││││││││││
   ││││││││ ... cada bit = 1 LED encès/apagat
```

Per visualitzar la cara, es crida:
```cpp
zowi.putMouth(smile);           // cara predefinida per número
zowi.putMouth(0b0101..., false); // cara personalitzada en binari
zowi.putAnimationMouth(littleUuh, i); // frame i d'una animació
zowi.clearMouth();              // apagar tots els LEDs
```

### Cares disponibles (IDs 0–30)

| ID | Nom | Descripció |
|---|---|---|
| 0–9 | `zero`...`nine` | Dígits numèrics |
| 10 | `smile` | Somriure |
| 11 | `happyOpen` | Content (boca oberta) |
| 12 | `happyClosed` | Content (boca tancada) |
| 13 | `heart` | Cor |
| 14 | `bigSurprise` | Gran sorpresa |
| 15 | `smallSurprise` | Petita sorpresa |
| 16 | `tongueOut` | Treient la llengua |
| 17–18 | `vamp1`, `vamp2` | Vampir |
| 19 | `lineMouth` | Línia horitzontal |
| 20 | `confused` | Confós |
| 21 | `diagonal` | Diagonal |
| 22–24 | `sad`, `sadOpen`, `sadClosed` | Trist (3 variants) |
| 25 | `okMouth` | OK |
| 26 | `xMouth` | Cara d'error (X) |
| 27 | `interrogation` | Interrogació |
| 28 | `thunder` | Llamp (bateria baixa) |
| 29 | `culito` | ... |
| 30 | `angry` | Enfadat |

### Animacions

Hi ha 4 animacions de múltiples frames definides a `Zowi.cpp`:

| Nom | Frames | Ús |
|---|---|---|
| `littleUuh` | 8 | Salutació inicial |
| `dreamMouth` | 4 | Mode adormit |
| `adivinawi` | 6 | Joc d'endevinar |
| `wave` | 10 | Ona |

---

## 6. Els sensors

### Ultrasons (US)

Mesura la distància a obstacles. Usa el protocol HC-SR04: envia un pols de 10 µs per Trigger i mesura el temps de retorn per Echo. La distància es calcula com `microsegons / 29 / 2` (velocitat del so).

```cpp
float dist = zowi.getDistance(); // en centímetres
```

El firmware considera **obstacle si `dist < 15 cm`**.

### Micròfon / sensor de soroll

Fa la mitjana de 2 lectures analògiques del pin A6. El **llindar de detecció de soroll és 650** (escala 0–1023):

```cpp
int noise = zowi.getNoise();
if (noise >= 650) { /* soroll detectat */ }
```

### Bateria

Llegeix la tensió del pin A7. La bateria és LiPo: **màxim 4,2 V, mínim 3,25 V**. El percentatge s'interpola entre aquests dos valors. Es fan 10 lectures i se'n calcula la mitjana per filtrar soroll.

```cpp
double pct = zowi.getBatteryLevel();   // 0.0 – 100.0
double v   = zowi.getBatteryVoltage(); // en Volts
```

L'alarma de bateria baixa s'activa per sota del **45%**: el Zowi fa un so de llamp i no avança fins que es prem un botó o es connecta el carregador.

---

## 7. Els sons

El brunzidor (pin 10) es controla amb la funció `tone()` d'Arduino. Dos mètodes bàsics:

```cpp
zowi._tone(frequència_Hz, durada_ms, silenci_ms);
zowi.bendTones(freq_inici, freq_fi, factor_multiplicatiu, durada_nota, silenci);
```

`bendTones` fa un **glissando**: va multiplicant (o dividint) la freqüència pel factor en cada pas, creant l'efecte de portamento. Per exemple:

```cpp
bendTones(880, 2000, 1.04, 8, 3); // puja de La5 (880 Hz) a ~2 kHz
```

### Sons predefinits (IDs 0–18)

| ID | Constant | Quan sona |
|---|---|---|
| 0 | `S_connection` | Connexió Bluetooth |
| 1 | `S_disconnection` | Desconnexió |
| 2 | `S_buttonPushed` | Botó premut |
| 3–5 | `S_mode1/2/3` | Canvi de mode |
| 6 | `S_surprise` | Sorpresa |
| 7–8 | `S_OhOoh`, `S_OhOoh2` | Reacció a soroll |
| 9 | `S_cuddly` | Mim |
| 10 | `S_sleeping` | Adormint-se |
| 11–13 | `S_happy`, `S_superHappy`, `S_happy_short` | Content |
| 14 | `S_sad` | Trist |
| 15 | `S_confused` | Confós |
| 16–18 | `S_fart1/2/3` | Pets (per entreteniment) |

Tots els sons es defineixen directament al `switch` de `Zowi::sing()` a `Zowi.cpp:739`.

---

## 8. Els gestos

Un gest combina moviment + so + expressions facials en una seqüència coordinada. S'invoquen amb:

```cpp
zowi.playGesture(ZowiHappy);
```

13 gestos disponibles:

| ID | Constant | Descripció |
|---|---|---|
| 0 | `ZowiHappy` | Balanceig content + so feliç |
| 1 | `ZowiSuperHappy` | Puntetes + so molt feliç |
| 2 | `ZowiSad` | Postura trista + so trist |
| 3 | `ZowiSleeping` | Ronca + animació de somni |
| 4 | `ZowiFart` | Inclina el cos + pet |
| 5 | `ZowiConfused` | Cap inclinat + so confós |
| 6 | `ZowiLove` | Cara de cor + so |
| 7 | `ZowiAngry` | Postura enfadada + so |
| 8 | `ZowiFretful` | Preocupat |
| 9 | `ZowiMagic` | Màgic |
| 10 | `ZowiWave` | Animació d'ona a la cara |
| 11 | `ZowiVictory` | Victòria |
| 12 | `ZowiFail` | Fallada |

---

## 9. La comunicació sèrie: ZowiSerialCommand

El Zowi es pot controlar a distància per **USB** (cable) o per **Bluetooth** (si té mòdul BT connectat al port sèrie). A 115200 bauds.

### Protocol de missatges

Totes les trames van **encapsulades** entre `&&` i `%%`:

```
&&<DADES>%%\r\n
```

### Comandes del controlador cap al robot

| Codi | Format | Acció |
|---|---|---|
| `S` | `S` | Parar (anar a posició de repòs) |
| `L` | `L 001111...1` | Mostrar cara (33 bits en binari) |
| `T` | `T 440 500` | Tocar nota (freqüència Hz, durada ms) |
| `M` | `M 1 1000 15` | Executar moviment (ID, T, mida) |
| `H` | `H 1` | Executar gest (ID 1–13) |
| `K` | `K 1` | Cantar so (ID 1–19) |
| `C` | `C 5 -3 0 2` | Calibrar servos (trims YL YR RL RR) i guardar a EEPROM |
| `G` | `G 90 85 96 78` | Moure servos a posicions absolutes |
| `R` | `R MiZowi` | Posar nom (guardat a EEPROM) |

### Peticions d'informació del robot

| Codi | Resposta |
|---|---|
| `E` | `&&E NomDelRobot%%` |
| `D` | `&&D 23%%` (distància en cm) |
| `N` | `&&N 512%%` (nivell de soroll 0–1023) |
| `B` | `&&B 78.5%%` (percentatge de bateria) |
| `I` | `&&I ZOWI_BASE_v2%%` (ID del programa) |

### Respostes d'ACK

El robot confirma cada comanda rebuda:
- `&&A%%` → ACK inicial (ha rebut la comanda)
- `&&F%%` → ACK final (ha acabat d'executar)

### IDs de moviment (comanda `M`)

| ID | Moviment |
|---|---|
| 0 | Stop / home |
| 1 | Caminar endavant |
| 2 | Caminar enrere |
| 3 | Girar esquerra |
| 4 | Girar dreta |
| 5 | Pujar i baixar |
| 6 | Moonwalk esquerra |
| 7 | Moonwalk dreta |
| 8 | Swing |
| 9 | Crusaito endavant |
| 10 | Crusaito enrere |
| 11 | Salt |
| 12 | Flapping endavant |
| 13 | Flapping enrere |
| 14 | Tiptoe swing |
| 15 | Inclinar esquerra |
| 16 | Inclinar dreta |
| 17 | Sacsejar cama dreta |
| 18 | Sacsejar cama esquerra |
| 19 | Tremolor |
| 20 | Gir ascendent |

---

## 10. El firmware principal: ZOWI_BASE_v2

El fitxer `code .ino/ZOWI_BASE_v2/ZOWI_BASE_v2.ino` és el programa que s'executa al robot.

### Setup (execució única a l'arrencar)

1. Inicia la comunicació sèrie a 115200 bauds.
2. Configura els pins dels botons.
3. Inicialitza el robot (`zowi.init`), carregant els trims de l'EEPROM.
4. Estableix una llavor aleatòria amb `analogRead(A6)`.
5. Registra les interrupcions dels botons (pins 6 i 7).
6. Registra tots els handlers de comandes sèrie.
7. Sona (`S_connection`) i va a posició de repòs.
8. **Comprova el nom a l'EEPROM** (adreça 5):
   - Si és `'$'` (nom de fàbrica): canvia a `'#'`, mostra `culito` i es queda en bucle (mode de producció inicial, no hauria d'arribar a l'usuari final).
   - Si és `'#'` (primer arrencat per l'usuari): fa una salutació llarga (salt, sacsejar cama, swing).
   - Si ja té nom: continua normalment.
9. Envia nom, ID de programa i nivell de bateria per sèrie.
10. Comprova la bateria i mostra alarma si cal.
11. Executa l'animació inicial `littleUuh` i canta `S_happy`.

### Loop (bucle infinit)

1. Si arriben dades per sèrie i no és ja en MODE 4: canvia a MODE 4 (teleoperació).
2. Si s'ha premut un botó: canvia de mode:
   - Botó A sol → MODE 1 (ball)
   - Botó B sol → MODE 2 (detector d'obstacles)
   - Botons A+B → MODE 3 (detector de soroll)
3. Executa la màquina d'estats (veure secció 11).

---

## 11. La màquina d'estats: els 5 modes de Zowi

### MODE 0 – En espera

El Zowi no fa res. Cada **80 segons** d'inactivitat executa `ZowiSleeping_withInterrupts()`: una seqüència d'animació de somni amb roncs (`bendTones` de freqüències baixes).

### MODE 1 – Ball

Escull un moviment a l'atzar entre els IDs 5 i 20 i el repeteix entre 3 i 5 vegades. Si el moviment és del 15 al 18 (inclinacions i sacsejos), només fa 1 repetició i és més lent (T=1600 ms).

### MODE 2 – Detector d'obstacles

Camina endavant fins que detecta un obstacle a menys de 15 cm. Quan el detecta:
1. Mostra `bigSurprise` i canta `S_surprise`.
2. Fa 5 salts.
3. Mostra `confused` i canta `S_cuddly`.
4. Recua 3 passos.
5. Intenta girar a l'esquerra fins que el camí quedi lliure.
6. Si el camí és lliure, somriu i reprèn la marxa.

### MODE 3 – Detector de soroll

Quan el sensor de soroll supera **650** (escala 0–1023), el Zowi es sorprèn, canta `S_OhOoh` i executa un ball aleatori. Després torna a la cara feliç.

### MODE 4 – Teleoperació

Llegeix contínuament el port sèrie amb `SCmd.readSerial()`. Executa les comandes que arribin (de l'aplicació ZowiPAD, de l'ordinador, etc.). Si el robot estava en moviment (`getRestState() == false`), continua executant el moviment actual (`moveId`).

---

## 12. L'EEPROM: memòria persistent

L'EEPROM de l'Arduino guarda dades que es conserven entre reinicis:

| Adreça | Contingut | Mida |
|---|---|---|
| 0 | Trim servo YL | 1 byte |
| 1 | Trim servo YR | 1 byte |
| 2 | Trim servo RL | 1 byte |
| 3 | Trim servo RR | 1 byte |
| 5–15 | Nom del Zowi (string de 10 caràcters + null) | 11 bytes |

El **primer caràcter del nom** (`adreça 5`) té un significat especial:
- `'$'` → Nom de fàbrica (el robot acaba de sortir de producció)
- `'#'` → Primer arrencat per l'usuari (no té nom propi yet)
- Qualsevol altra cosa → El robot ja té nom

---

## 13. Com actualitzar el robot

### Via Arduino IDE

1. Instal·la l'Arduino IDE.
2. Copia totes les carpetes de `arduino libraries/` a la carpeta de biblioteques de l'Arduino IDE (normalment `~/Arduino/libraries/` o `Documentos/Arduino/libraries/`).
3. Obre el fitxer `code .ino/ZOWI_BASE_v2/ZOWI_BASE_v2.ino`.
4. Selecciona la placa correcta: `Eines > Placa > Arduino Uno` (o Nano, segons el model).
5. Selecciona el port sèrie: `Eines > Port > /dev/ttyUSB0` (Linux) o `COM3` (Windows).
6. Prem `Puja` (→).

### Via arduino-cli

```bash
# Compilar
arduino-cli compile --fqbn arduino:avr:uno "code .ino/ZOWI_BASE_v2"

# Compilar i pujar
arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:uno "code .ino/ZOWI_BASE_v2"
```

### Via fitxer .hex (sense compilar)

Els fitxers `.hex` de `code .hex/` ja estan compilats i es poden pujar directament amb `avrdude`:

```bash
avrdude -c arduino -p atmega328p -P /dev/ttyUSB0 -b 115200 \
        -U flash:w:"code .hex/ZOWI_BASE_v2.hex":i
```

### Calibratge dels servos

Cada servo físic pot estar lleugerament desviat. El **calibratge** (trim) corregeix aquesta desviació. S'indica en graus (positiu o negatiu). Per calibrar:

**Opció 1 – Via comanda sèrie** (mentre el robot funciona):
```
C 5 -3 0 2      ← trims per YL, YR, RL, RR en graus
```
Això guarda els valors a l'EEPROM immediatament.

**Opció 2 – Al codi** (per valors fixos):
```cpp
// A ZOWI_BASE_v2.ino, descomenta aquestes línies al setup():
zowi.setTrims(5, -3, 0, 2);     // YL, YR, RL, RR
zowi.saveTrimsOnEEPROM();        // guarda (descomenta NOMÉS per una pujada)
```
Puja el codi, torna a comentar `saveTrimsOnEEPROM()`, i torna a pujar. Si no, guardarà els trims cada vegada que arrenci.

---

## 14. Com modificar el comportament

### Afegir un moviment nou

1. Afegeix la funció a `Zowi.cpp` i la declaració a `Zowi.h`.
2. Assigna-li un ID > 20 al `switch` de `move()` al firmware.
3. Si vols que sigui accessible per Bluetooth, afegeix l'ID a la documentació interna.

Exemple de moviment nou (servo oscillant a la cadència d'un vals):

```cpp
void Zowi::vals(float steps, int T) {
    int A[4] = {30, 30, 15, 15};
    int O[4] = {0, 0, 0, 0};
    double phase_diff[4] = {0, DEG2RAD(60), DEG2RAD(-90), DEG2RAD(30)};
    _execute(A, O, T, phase_diff, steps);
}
```

### Afegir una cara nova

Les cares es defineixen com a nombres de 32 bits. Cada bit és un LED. La matriu és de 5 files × 6 columnes. Pots dissenyar la teva cara:

```
Files (de dalt a baix):   bit 29..24 | bit 23..18 | bit 17..12 | bit 11..6 | bit 5..0
```

O usar una eina visual com [Zowi Face Designer](https://github.com/bqlabs/zowi) si n'hi ha disponible.

```cpp
// Defineix la nova cara a Zowi_mouths.h:
#define myCoolFace_code   0b00011000100101010010100100011000
#define myCoolFace        31   // nou ID

// Usa-la:
zowi.putMouth(myCoolFace);
```

### Afegir un so nou

Afegeix un `case` nou al `switch` de `Zowi::sing()` a `Zowi.cpp`:

```cpp
case S_mySound:  // defineix S_mySound = 19 a Zowi_sounds.h
    _tone(note_C5, 200, 50);
    _tone(note_E5, 200, 50);
    _tone(note_G5, 400, 0);
break;
```

### Afegir un gest nou

Afegeix un `case` al `switch` de `Zowi::playGesture()` a `Zowi.cpp`:

```cpp
case ZowiMyGesture:  // defineix ZowiMyGesture = 13 a Zowi_gestures.h
    putMouth(smile);
    sing(S_happy_short);
    walk(2, 800, FORWARD);
    home();
    putMouth(happyOpen);
break;
```

### Modificar els llindars dels modes

- **Llindar d'obstacle**: `if(distance < 15)` a `obstacleDetector()` (línia ~458 del firmware). Augmenta el número per fer-lo més sensible.
- **Llindar de soroll**: `if (zowi.getNoise() >= 650)` al `case 3`. Baixa el número per fer-lo més sensible.
- **Temps fins adormir-se**: `if (millis()-previousMillis >= 80000)` al `case 0`. Valor en mil·lisegons.

### Canviar el nom del robot via codi

```cpp
// Al setup del firmware, afegeix:
char newName[] = "ElMeuZowi";
EEPROM.put(5, newName);
```

O envia la comanda per sèrie:
```
R ElMeuZowi
```

---

## 15. Els fitxers de jocs

A `code .ino/games/` hi ha sketches alternatius:

### ZOWI_Adivinawi_v2

Un joc en què el Zowi "llegeix la ment". Usa l'animació `adivinawi` de la cara. El nom ve de "adivina" + "wi" (de Wifi o Zowi).

### ZOWI_Alarm_v2

El Zowi funciona com a alarma de proximitat. Quan detecta quelcom amb l'ultrasònic, activa una seqüència d'alerta.

Per pujar qualsevol d'aquests jocs, simplement puja el fitxer `.ino` corresponent (en lloc del `ZOWI_BASE_v2`). Per tornar al comportament normal, torna a pujar `ZOWI_BASE_v2`.

---

## 16. El sketch de fàbrica

`factoryZowi/factoryZowi.ino` és el programa que BQ usava a la línia de producció per verificar el robot recé muntat. No és útil per a l'ús normal, però és interessant com a referència:

1. Espera que **tots dos botons** estiguin premuts alhora.
2. Comprova el sensor d'ultrasons en temps real: si hi ha alguna cosa a menys de 15 cm, mostra `heart`; si no, encén tots els LEDs.
3. Quan es deixa de prémer el botó, mou els servos a `checkPosition` (70, 110, 60, 120) per verificar el rang de moviment.
4. Quan es deixa de prémer el botó B, torna a posició de repòs i mostra `okMouth`.
5. Escriu `'$'` a l'EEPROM (adreça 5) com a "nom de fàbrica".

---

*Document elaborat a partir de la lectura directa del codi font del repositori zowiLibs, abril 2026.*


Desenvolupament de zowi.py

 ---
  Instal·lació                                                                  
                                                            
  pip install pyserial                                                        
                                                                                
  Permisos del port USB (una sola vegada)                                       
  
  sudo usermod -a -G dialout $USER   # cal tancar sessió i tornar a entrar      
  # o temporalment:                                                             
  sudo chmod 666 /dev/ttyUSB0                                                   
                                                                                
  Demo automàtic                                                                
                                                                              
  python zowi.py /dev/ttyUSB0                                                 
  Executa: connexió → animació → caminar 2 passos → salt → cara de cor → repòs. 
                                                                                
  ---                                                                           
  Ús com a biblioteca                                                           
                                                                                
  from zowi import Zowi                                                       
                                                                                
  with Zowi('/dev/ttyUSB0') as z:                           
      # Informació                                                            
      print(z.get_name(), f"{z.get_battery():.0f}%")
                                                                                
      # Moviment                                                                
      z.walk(steps=3)          # caminar endavant                               
      z.walk(direction='backward')                                              
      z.turn(direction='left')                                                  
      z.jump()                                                                
      z.stop()                                                                  
                                                            
      # Cara LED (nom, ID o bitmap)                                             
      z.set_mouth('heart')
      z.set_mouth('sad')                                                        
      z.set_mouth(0)           # cara '0'                   
      z.clear_mouth()                                                           
                                                            
      # Animació                                                                
      z.animate_mouth(Zowi.ANIM_LITTLE_UUH, delay=0.12, repeat=2)
                                                                                
      # Sons i gestos
      z.sing('happy')                                                           
      z.tone(440, 300)         # La4, 300 ms                
      z.gesture('love')                                                         
                                                                                
      # Sensors                                                                 
      print(z.get_distance())  # cm                                             
      print(z.get_noise())     # 0-1023                                       
                                            
