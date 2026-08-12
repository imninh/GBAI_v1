# Checkpoint 1 — Hardware Simulation

Everything in this document runs in **Wokwi**, on an ESP32 DevKit-C V4. No
physical hardware, no camera, no real AI model, no backend required.

## Hardware

| Part | Wokwi type | Role |
|---|---|---|
| ESP32 DevKit-C V4 | `board-esp32-devkit-c-v4` | MCU |
| PIR motion sensor | `wokwi-pir-motion-sensor` | user-present trigger |
| HC-SR04 | `wokwi-hc-sr04` | fill level (distance → %) |
| WS2812 NeoPixel | `wokwi-neopixel` | system-state indicator |
| SSD1306 128x64 | `wokwi-ssd1306` | user-facing screen (I2C) |
| Servo | `wokwi-servo` | sorting flap |
| 1 kΩ + 2 kΩ | `wokwi-resistor` | ECHO divider → 3.3 V |

The camera and the classifier are **mocks** in this checkpoint. They are real
objects behind the real interfaces, not stubs sprinkled through the flow — see
[Known limitations](#known-limitations).

## Pin map

Defined once, in [`firmware/include/config.h`](../firmware/include/config.h). No
GPIO number appears anywhere else in the firmware.

| Signal | GPIO | Notes |
|---|---|---|
| `PIN_PIR` | 13 | PIR OUT |
| `PIN_ULTRASONIC_TRIG` | 14 | HC-SR04 TRIG |
| `PIN_ULTRASONIC_ECHO` | 12 | HC-SR04 ECHO via 1k/2k divider |
| `PIN_LED` | 15 | WS2812 DIN |
| `PIN_SERVO` | 18 | servo PWM (LEDC ch. 4, 50 Hz) |
| `PIN_OLED_SDA` | 21 | SSD1306 DATA |
| `PIN_OLED_SCL` | 22 | SSD1306 CLK |

Power: PIR and HC-SR04 and servo on 5 V, NeoPixel and OLED on 3.3 V, common GND.

> **This is the simulation pin map, not the ESP32-CAM pin map.** On the real
> AI-Thinker board GPIO18/21/22 are camera data lines (Y3, Y4, PCLK), so the
> `esp32cam` build compiles **without** the servo and the OLED and injects
> `NullSorter` / `NullDisplay` instead. The flow is identical; the calls go
> nowhere and the sorter honestly reports that it never moved. See
> [pin-map.md](pin-map.md) §4.

## Wokwi

```bash
cd iot/firmware
pio run -e wokwi                    # builds .pio/build/wokwi/firmware.{bin,elf}
```

Then open [`iot/simulation/diagram.json`](../simulation/diagram.json) in the
Wokwi VS Code extension and press ▶.

The `wokwi` environment differs from the field build in exactly these ways, all
of them build flags in [`platformio.ini`](../firmware/platformio.ini):

| Flag | Effect |
|---|---|
| `GREENBIN_USE_MOCK_CAMERA` | fixture JPEG instead of the OV2640 |
| `GREENBIN_MOCK_BACKEND` | offline mock classifier instead of HTTP |
| `GREENBIN_HAS_SORTER` / `GREENBIN_HAS_DISPLAY` | servo and OLED compiled in |
| `GREENBIN_TEST_CONSOLE` | Serial hardware test menu |
| `GREENBIN_ENABLE_WIFI` | Wi-Fi + heartbeat (P1, idle-only) |
| `EMPTY_DISTANCE_CM=50` / `FULL_DISTANCE_CM=5` | simulation fill calibration |
| `PIR_WAIT_MS=5000` | 5 s to move the HC-SR04 slider after a PIR trigger |

## Serial commands

115200 baud. Press `?` for the menu.

| Key | Action |
|---|---|
| `1` | Test PIR (8 s watch window) |
| `2` | Test HC-SR04 — prints distance, fill %, fill state |
| `3` | Test OLED — walks every screen |
| `4` | Test NeoPixel — walks every pattern |
| `5` | Test servo — HOME→PLASTIC→HOME→PAPER→HOME→METAL→HOME |
| `6` | **Checkpoint 1 self test** (all of the above + camera mock) |
| `p` `a` `m` `h` | Move the flap to PLASTIC / PAPER / METAL / HOME |
| `7` `8` `9` `0` | Mock AI returns PLASTIC / PAPER / METAL / UNKNOWN next |
| `c` | Force the next camera capture to fail |
| `x` | Force the next upload to fail |
| `f` | Show fill level |
| `s` | Show system status |
| `r` | Run a full transaction without touching the PIR |
| `w` | Wi-Fi status + send a heartbeat now |
| `?` | Show the menu |

## State machine

```text
BOOT → WIFI_CONNECTING → IDLE
                          │  PIR + distance drop ≥ 4 cm   (or `r`)
                          ▼
                  PRESENCE_DETECTED → VERIFY_OBJECT
                                            │
              false trigger ────────────────┤
                          ┌─────────────────┘
                          ▼
                       CAPTURE → UPLOAD → WAIT_RESULT
                                                │
                                                ▼
                                            SORTING → UPDATE_FILL → SHOW_RESULT → IDLE

any failure → ERROR → flap HOME → IDLE
```

Screens and LED patterns are driven from the state transition itself
(`applyScreenFor`), so there is exactly one place that decides what the user
sees. `VERIFY_OBJECT` is the false-trigger guard: a PIR event with no drop in
distance is somebody walking past, and it costs no capture and no classification.

**The sorting rule.** `resolveSorting()` in
[`core/classification.cpp`](../firmware/src/core/classification.cpp) is the only
code that decides whether an item may be sorted. It requires *all* of:

- `status == ok`,
- a label the firmware recognises (plastic / paper / cardboard / metal / can),
- `confidence >= MIN_SORT_CONFIDENCE` (0.60).

Anything else — unknown label, low confidence, warning, hazard, refusal, parse
error — is `REJECT`, the flap stays at HOME, and the screen says the item was not
sorted. The mock and the real HTTP client both go through this function, so they
cannot drift apart.

## How to run

```bash
# 1. Unit tests (no hardware, no network)
cd iot/firmware && pio test -e native

# 2. Firmware for the simulator
pio run -e wokwi

# 3. Wokwi: open iot/simulation/diagram.json in VS Code, press ▶
```

Optional — the desktop simulator, which drives the real state machine against
the real backend over a real socket:

```bash
# terminal 1
IOT_DEVICE_KEYS="GBIN-001:sim-test-key" VISION_PROVIDER=stub \
STUB_VISION_LABEL=plastic STUB_VISION_CONFIDENCE=0.94 \
  .venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8123

# terminal 2
cd iot/firmware && pio run -e sim
./.pio/build/sim/program --base-url http://127.0.0.1:8123 --device-key sim-test-key
```

## Expected demo flow

Press ▶ in Wokwi, wait for `HARDWARE TEST MODE`, then either:

**A — the sensor path (what the real bin does).** Click the PIR to trigger it,
then within 5 seconds drag the HC-SR04 distance slider down by at least 4 cm
(e.g. 50 → 26). The drop is what confirms an item was actually deposited.

**B — the deterministic path.** Type `r` in the Serial monitor.

Either way the Serial monitor prints:

```text
[STATE] IDLE -> PRESENCE_DETECTED
[OLED]  User detected
[STATE] PRESENCE_DETECTED -> VERIFY_OBJECT
[HC-SR04] before=50.0 after=26.2 delta=23.8
[EVENT] waste_confirmed
[STATE] VERIFY_OBJECT -> CAPTURE
[CAMERA] Image captured successfully bytes=1052
[STATE] CAPTURE -> UPLOAD
[AI MOCK] transaction=TX-001 status=ok label=plastic confidence=0.93
[STATE] UPLOAD -> WAIT_RESULT
[AI] transaction=TX-001 status=ok label=plastic confidence=0.93 action=SORT target=PLASTIC
[STATE] WAIT_RESULT -> SORTING
[SERVO] target=PLASTIC angle=30deg moving
[SERVO] target=PLASTIC done
[STATE] SORTING -> UPDATE_FILL
[HC-SR04] distance=26.2cm fill=52.9% state=NORMAL
[STATE] UPDATE_FILL -> SHOW_RESULT
[SERVO] target=HOME done
[STATE] SHOW_RESULT -> IDLE
```

The OLED follows: `Ready` → `Hello! / User detected` → `Capturing` →
`Analyzing` → `PLASTIC / Sorting...` → `PLASTIC / Accepted / Fill: 53%` →
`Ready`. The servo visibly swings to 30° and back to 90°.

Press `0` then `r` for the rejection path: `action=REJECT target=HOME`, the flap
never moves, and the screen says `NOT SORTED`.

## Demo with a real webcam (`wokwi_camera`)

The default build classifies nothing real. For a demo that photographs an actual
object, the `wokwi_camera` build replaces **two** pieces — and only two:

| | default `wokwi` | `wokwi_camera` |
|---|---|---|
| Image | fixture JPEG in flash | **PC webcam over HTTP** |
| Classifier | `MockBackendService` | **real backend → real classifier** |
| Everything else | — | identical code |

```text
Webcam → webcam_service.py :8124 → [Wokwi gateway] → ESP32
                                                       │  holds the JPEG in its own RAM
                                                       ▼
                              POST /api/v1/iot/captures on :8123
                                                       │  EXIF strip → face blur → resize → pHash → classifier
                                                       ▼
                              {status, label, confidence} → resolveSorting() → servo → OLED
```

The ESP32 leg is deliberately kept. The device still buffers the JPEG and still
builds the multipart request itself, so nothing about the device↔backend contract
is skipped — **only the image sensor has moved off the board.** Replacing
`HostCameraService` with `Ov2640CameraService` later is a one-line change in
`main.cpp` and touches no flow code.

### Running it

Four terminals:

```bash
# 1 — Wokwi Private IoT Gateway (lets the simulated ESP32 reach this machine)
~/.local/bin/wokwigw

# 2 — backend
cd /home/TranPhuNghia_20233871/P-075
IOT_DEVICE_KEYS="GBIN-001:sim-test-key" VISION_PROVIDER=stub \
  .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8123

# 3 — webcam
.venv/bin/python iot/simulation/webcam_service.py

# 4 — firmware
cd iot/firmware && pio run -e wokwi_camera
```

Then point [`wokwi.toml`](../simulation/wokwi.toml) at the `wokwi_camera` build
(swap the commented block) and press ▶.

### Check the framing before you demo

The classifier is instructed not to guess: shown an image with no clearly
identifiable waste item it returns an empty label, which the safety layer turns
into `refused` and the device correctly declines to sort. That is the single
most common surprise in this demo, and the device log cannot tell it apart from
a broken key.

```bash
.venv/bin/python iot/simulation/check_vision.py
```

It captures one frame, **saves it to `/tmp/greenbin-check.jpg` so you can look at
it**, runs the identical pipeline, and prints the raw model reply. Adjust the
object, run again — a two-second loop instead of a Wokwi round trip. Aim for the
object filling at least a third of the frame, on a plain background, well lit.
A blank sheet of white paper is the hardest case there is; a labelled bottle or
a drinks can is the easiest.

The service sends 1024x576 (captured at 1280x720), which is exactly what the
backend keeps — `TARGET_MAX_EDGE` in `services/image_privacy.py`. Anything
larger would be discarded, and the frame must also fit the device's 48 KB
buffer, so quality steps down automatically on a busy scene.

Hold an object in front of the webcam, type `r` (or trigger the PIR), and the
Serial monitor shows the real numbers:

```text
[CAMERA] Image captured successfully bytes=21172
[HTTP] upload status=200
[AI] transaction=... status=ok label=plastic confidence=0.91 action=SORT target=PLASTIC
[SERVO] target=PLASTIC angle=30deg moving
```

### Real AI vs. stub

`VISION_PROVIDER=stub` returns a canned label — the *image path* is real, the
recognition is not. For genuine recognition, put a working key in `.env`
(`OPENAI_API_KEY` is currently the placeholder `sk-your-key-here`) and start the
backend with `VISION_PROVIDER=openai`. No firmware change: the device already
sends a real photo and already obeys whatever the backend answers.

The backend's label vocabulary is `plastic, paper, metal, glass, organic,
battery, chemical, medical, sharps, e-waste, paint, aerosol, other`. The firmware
maps only plastic / paper / cardboard / metal / can to bins; **glass, organic and
the hazardous classes are deliberately not sortable** by a three-bin device, so
holding up a glass bottle is a good way to demonstrate the refusal path.

### Two things to be aware of

- **Privacy.** `webcam_service.py` binds `0.0.0.0` because the ESP32 is on the
  gateway's virtual network, not on localhost. Anyone on your LAN who finds port
  8124 can pull a frame. Stop it after the demo. The camera indicator light also
  stays on for as long as the service runs.
- **The backend really does blur faces.** A test upload from this webcam came
  back `faces_blurred: 1` — if you stand in shot, your face is blurred before the
  classifier ever sees it. That is worth showing rather than hiding.

## Known limitations

These are real gaps, stated so nobody mistakes a green run for more than it is.

- **The AI is a mock.** `MockBackendService` returns whichever class the console
  last selected. It proves the contract and the flow, not recognition.
- **The camera is a mock.** Wokwi does not simulate the OV2640;
  `MockCameraService` serves a 1052-byte fixture JPEG.
- **NeoPixel and servo have no readback.** The self test reports OK when the
  driver accepted every command. Whether the pixel lit and the horn turned has to
  be confirmed by eye — the self-test output says this explicitly.
- **The PIR cannot be asserted from software.** The self test reports
  `READY - waiting manual trigger` rather than a fake OK, and the verdict line
  reads `PASS (PIR not yet triggered)` until someone clicks it.
- **This is not the ESP32-CAM pin map.** See the note above.
- **`SERVO_SETTLE_MS` blocks.** A move costs 400 ms of blocking wait, because a
  hobby servo has no position feedback. It is the only blocking call in the flow.
- **The heartbeat is P1 and idle-only.** It never runs during a transaction, and
  a failure is logged as a failure, not retried into the sorting path.
- **The Wokwi scenarios in `simulation/scenarios/*.yaml` have not been executed**
  — running them needs a `WOKWI_CLI_TOKEN`. The diagram itself passes
  `wokwi-cli lint` with zero errors.
