# Hardware setup guide

> **Read [pin-map.md](pin-map.md) first.** It explains why each GPIO was chosen and
> which two connections can damage the board if wired naively.

## Bill of materials

| Part | Notes |
|---|---|
| AI Thinker ESP32-CAM | With OV2640 and PSRAM |
| USB-TTL adapter (CP2102/FTDI) | For flashing — 3.3 V logic |
| HC-SR501 PIR sensor | |
| **HC-SR04P** or RCWL-1601 ultrasonic | The **-P** variant runs at 3.3 V and needs no divider. Strongly preferred |
| WS2812 / NeoPixel — one pixel | |
| 5 V power supply, **≥ 2 A** | Not the USB-TTL adapter's 5 V pin |
| 1 kΩ + 2 kΩ resistors | Only if using a plain 5 V HC-SR04 |
| 470–1000 µF electrolytic capacitor | Across the 5 V rail, near the module |

## Wiring

| Signal | ESP32-CAM pin | Notes |
|---|---|---|
| HC-SR501 `VCC` | 5V | |
| HC-SR501 `GND` | GND | |
| HC-SR501 `OUT` | **GPIO13** | Direct — output is 3.3 V logic |
| HC-SR04 `VCC` | 5V (or 3V3 for the -P variant) | |
| HC-SR04 `GND` | GND | |
| HC-SR04 `TRIG` | **GPIO14** | Direct |
| HC-SR04 `ECHO` | **GPIO12** | ⚠️ **Via divider** unless using HC-SR04P |
| WS2812 `VDD` | **3V3** | ⚠️ **Not 5 V** — see below |
| WS2812 `GND` | GND | |
| WS2812 `DIN` | **GPIO15** | Direct |

All grounds must be common.

### ⚠️ The two connections that matter

**1. `ECHO` is 5 V and the ESP32 is not 5 V tolerant.**

A plain HC-SR04 drives `ECHO` push-pull at 5 V. Connecting it straight to GPIO12
risks permanent damage. Either use the HC-SR04P (3.3 V, no divider), or:

```
ECHO ──┬── 1kΩ ──┬── GPIO12
       │         │
       │        2kΩ
       │         │
      GND ───────┴── GND

5.0 V × 2/(1+2) = 3.33 V  ✅
```

**2. The WS2812 must run from 3.3 V, not 5 V.**

A WS2812 needs `DIN` high at ≥ 0.7 × VDD. At 5 V that is 3.5 V, which a 3.3 V GPIO
cannot guarantee — it often works on the bench and fails later. Powering the pixel
from 3.3 V drops the threshold to 2.31 V, with margin. (A 74AHCT125 level shifter
is the alternative if 5 V is unavoidable.)

## Flashing

The AI Thinker board has no USB. To flash:

1. `GPIO0` → `GND` (jumper).
2. USB-TTL: `U0T`→RX, `U0R`→TX, `GND`→GND. Power the board from its own 5 V supply.
3. Press reset.
4. Upload, then **remove the GPIO0 jumper** and reset again.

```bash
cd iot/firmware
cp include/secrets.example.h include/secrets.h   # then edit it
pio run -e esp32cam
pio run -e esp32cam -t upload
pio device monitor -b 115200
```

## Sensor configuration

**HC-SR501** has two potentiometers and a jumper:

- Jumper → **H (repeat)** mode, so `OUT` follows motion rather than latching.
- Delay (`Tx`) → **minimum**.
- Sensitivity (`Sx`) → start mid-range and tune so the bin's approach zone triggers
  but passers-by mostly do not. The ultrasonic check catches the rest.

**It self-calibrates for 30–60 s after power-up** and emits spurious HIGH during
that window. The firmware logs a warning at boot. Ignore triggers for the first
minute.

## Calibration

Measure your bin and set these in `config.h`:

```c
#define EMPTY_DISTANCE_CM 60.0f   // sensor to floor, bin empty
#define FULL_DISTANCE_CM  10.0f   // sensor to waste, bin full
#define OBJECT_DELTA_CM    4.0f   // start at 4; tune against real deposits
```

Mount the ultrasonic sensor in the lid pointing straight down, away from the walls
— an angled beam reflects off the side and reads short.

`OBJECT_DELTA_CM` is the value to tune first. Too low and people leaning over the
bin trigger captures; too high and small items are missed. Watch the
`[HC-SR04] before=… after=… delta=…` log lines during real use and pick a
threshold above the noise floor.

## Expected boot output

```
[BOOT] firmware=0.1.0 device=GBIN-001 bin=BIN-001
[BOOT] psram=1 heap=213456
[PIR] settling; ignore triggers for the first ~60s
[STATE] BOOT
[CAMERA] init ok psram=1
[STATE] WIFI_CONNECTING
[WIFI] connecting
[WIFI] connected
[STATE] IDLE
```

`psram=0` means the camera falls back to QVGA. If you expected PSRAM, the module
is not the one you think it is.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Board will not boot with sensors attached | Something is pulling **GPIO12** high at reset. Disconnect the `ECHO` line and retry — see [pin-map.md](pin-map.md) §4 |
| Random resets during Wi-Fi or capture | Brownout. Supply cannot deliver peak current — use a real 5 V/2 A source and add the capacitor |
| `[CAMERA] init failed` | Ribbon cable not seated, or insufficient power |
| Distance always invalid | Wrong pins, missing common ground, or a 5 V `ECHO` that the divider is not attenuating |
| LED does nothing or flickers | Pixel powered from 5 V — move it to 3.3 V |
| No serial output | Baud rate, or `GPIO15` pulled low at boot |
| `401` from the backend | `DEVICE_KEY` does not match the backend's `IOT_DEVICE_KEYS` entry for this `DEVICE_ID` |
