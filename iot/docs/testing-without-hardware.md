# Testing without hardware

You do not need an ESP32-CAM to develop or verify most of this system. Three
layers are available, and together they cover everything except the physical
electronics.

| Layer | Proves | Needs | Runtime |
|---|---|---|---|
| **1. Native unit tests** | State machine, thresholds, retry bounds, LED mapping, fill maths | Nothing | ~1 s |
| **2. Host simulator** | The real device↔backend contract over a real socket | The backend running locally | ~2 s |
| **3. Wokwi** | GPIO timing, WS2812 waveform, real sensor parts, the ESP32 binary itself | A browser or the VS Code extension | interactive |

Nothing here validates the pin map, the level shifter, the OV2640, or power
behaviour. Those need a board — see [pin-map.md](pin-map.md) §7.

---

## Layer 1 — Native unit tests

The state machine never calls `millis()` or touches a pin; it depends on five
interfaces and receives time as a parameter. So the whole thing compiles and runs
on your laptop with fake sensors.

```bash
cd iot/firmware
pio test -e native
```

```
native   test_logic       PASSED
native   test_scenarios   PASSED
31 test cases: 31 succeeded
```

All nine specification scenarios are here, plus camera-failure recovery, Wi-Fi
non-blocking, and bin-reading retry. This is the layer to run constantly while
editing logic.

---

## Layer 2 — Host simulator (real backend, real HTTP)

This is the one that matters most when you have no hardware. It compiles the
**real** `src/core/state_machine.cpp` and drives it with:

- scripted PIR and ultrasonic values,
- a camera that serves a **real JPEG** from `iot/simulation/fixtures/`,
- a network layer that builds the **same multipart body and headers** as the
  firmware and posts them over a real POSIX socket.

So it exercises the actual contract: multipart framing, `X-Device-Key` auth, the
privacy pipeline, the classification response shape, and the bin-reading
endpoint. If the device and backend disagree about anything, this fails.

### Run it

Terminal 1 — the backend:

```bash
cd /home/TranPhuNghia_20233871/P-075
IOT_DEVICE_KEYS="GBIN-001:sim-test-key" \
VISION_PROVIDER=stub STUB_VISION_LABEL=plastic STUB_VISION_CONFIDENCE=0.94 \
  .venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8123
```

Terminal 2 — the device:

```bash
cd iot/firmware
pio run -e sim
./.pio/build/sim/program --base-url http://127.0.0.1:8123 --device-key sim-test-key
```

Real output:

```
=== Scenario 2/3 — valid waste event, real upload ===
[PIR] detected
[ULTRASONIC] before=50.0 after=44.0 delta=6.0
[EVENT] waste_confirmed
[CAMERA] jpeg_bytes=10223
[PRIVACY] phash=ffe7e7e7e7c3c3ff exif_stripped=true faces_blurred=0 bytes=6577
[HTTP] upload status=200
[AI] status=ok label=plastic confidence=0.94
[LED] OK
  22/22 checks passed
```

Note `bytes=6577` against `jpeg_bytes=10223` — that is the backend's resize and
re-encode, and `exif_stripped=true` is the privacy step reporting for itself.

### The stub Vision provider

`VISION_PROVIDER=stub` returns a canned label **without calling any model**, so
you can exercise the LED paths with no API key and no spend. It logs a warning on
every call and must be set explicitly — it will never activate by accident.

Drive the different device behaviours by changing the stub:

| Goal | Settings | Device shows |
|---|---|---|
| Scenario 3 — success | `STUB_VISION_LABEL=plastic STUB_VISION_CONFIDENCE=0.94` | Green, ~3 s |
| Scenario 4 — low confidence | `STUB_VISION_LABEL=paper STUB_VISION_CONFIDENCE=0.30` | Red, 2 fast blinks |
| Scenario 5 — hazard | `STUB_VISION_LABEL=battery STUB_VISION_CONFIDENCE=0.42` | Red, blinking ~5 s |
| Refused | `STUB_VISION_LABEL=""` | Warning pattern, no label |
| Error | omit `VISION_PROVIDER` and any API key | Orange, no label asserted |

The hazard case is worth running: at 0.42 the confidence is *below* the low-confidence
threshold, yet the result is `hazard`, not `warning`. That is
[safety.py](../../src/services/safety.py) deliberately letting hazard win — the
cost of a false positive is a human glance, the cost of a false negative is a fire.

With a real key instead, set `VISION_PROVIDER=openai` and `OPENAI_API_KEY=...`.

### What the simulator does **not** cover

It runs desktop code, not the ESP32 binary. It cannot catch a stack overflow, a
PSRAM allocation failure, an RMT timing problem on the WS2812, or anything about
GPIO. Use layer 3 for those.

---

## Layer 3 — Wokwi

Wokwi runs the **actual compiled ESP32 binary** against simulated peripherals, so
it catches things layers 1 and 2 cannot.

### Setup

```bash
cd iot/firmware
pio run -e wokwi             # mock camera + Wokwi network/timing settings
```

Install the **Wokwi for VS Code** extension, then open
`iot/simulation/diagram.json` and press ▶. It reads `wokwi.toml`, which points at
the `wokwi` build artifacts. This environment keeps real-hardware credentials and
timings untouched while selecting `Wokwi-GUEST`, a 1-second PIR wait, and a
5-second fill interval.

### Networking in Wokwi

Wokwi provides the open `Wokwi-GUEST` access point. The `wokwi` PlatformIO
environment configures it at compile time, so do not create or edit `secrets.h`
for simulation.

Outbound internet works through Wokwi's public gateway, but **it cannot reach
`localhost`** — the simulator runs in the cloud. Two options:

- **Wokwi Private Gateway** — lets the simulated ESP32 reach your own network
  directly. The committed Wokwi build uses
  `http://host.wokwi.internal:8123`, the documented hostname for the host machine.
- **Expose your backend publicly**, e.g. `ngrok http 8000` or
  `cloudflared tunnel --url http://localhost:8000`, then set `BACKEND_BASE_URL`
  to the public HTTPS URL. Note the firmware uses plain `HTTPClient`; for an
  HTTPS URL you will need `WiFiClientSecure` with `setInsecure()` or a CA bundle.

If you skip networking entirely, every upload fails — which is a perfectly valid
run of scenario 6.

### Building the diagram by hand

`iot/simulation/diagram.json` is committed and should just work, but if you want
to build or repair it yourself:

1. Go to [wokwi.com](https://wokwi.com) → **New Project** → **ESP32**.
2. Click the **＋** button in the diagram editor and add:
   `PIR Motion Sensor`, `HC-SR04 Ultrasonic Distance Sensor`, `NeoPixel`.
3. Drag from a component pin to a board pin to wire it. **Hover any pin to see
   its exact name** — that is the authoritative source, and how you resolve any
   mismatch with the JSON below.
4. Switch to the **diagram.json** tab to see or paste the text form.

The wiring, matching [pin-map.md](pin-map.md):

| From | To |
|---|---|
| `pir:OUT` | `esp:13` |
| `ultrasonic:TRIG` | `esp:14` |
| `ultrasonic:ECHO` | 1 kΩ series → `esp:12`, with 2 kΩ from GPIO12 to GND |
| `led:DIN` | `esp:15` |
| `pir:VCC` | `esp:5V` |
| `ultrasonic:VCC` | `esp:5V` |
| `led:VDD` | `esp:3V3` |
| all `GND` / `VSS` | `esp:GND.1`, `esp:GND.2`, `esp:GND.3` |

The part types and pin names above are taken from the Wokwi docs
([hc-sr04](https://docs.wokwi.com/parts/wokwi-hc-sr04),
[pir](https://docs.wokwi.com/parts/wokwi-pir-motion-sensor),
[neopixel](https://docs.wokwi.com/parts/wokwi-neopixel)) and the GPIO/ground
naming from Wokwi's own
[esp32-http-server example](https://github.com/wokwi/esp32-http-server/blob/main/diagram.json),
which uses `board-esp32-devkit-c-v4` with bare pin numbers (`esp:26`) and
`esp:GND.1`.

The diagram was checked with `wokwi-cli lint` v0.26.1 on 2026-08-11: **zero
errors**. The linter validates current part IDs and pin connections. It emits one
informational message because `board-esp32-devkit-c-v4` is a supported but
undocumented part definition.

Two caveats remain:

- **The full hardware simulation has not been executed here** — the Wokwi CLI
  requires `WOKWI_CLI_TOKEN`, which is not present. The diagram and firmware are
  validated separately, but the final interactive run still needs your Wokwi
  account/license and, for the local backend, the Private IoT Gateway.
- **Wokwi has no ESP32-CAM part.** The diagram uses an ESP32 DevKit with the
  identical GPIO assignment, so it validates the *firmware's* pin usage but not
  the real board's camera wiring.

### Driving the scenarios

Click a part in the running simulation to interact with it:

- **PIR** — click to trigger motion.
- **HC-SR04** — drag its distance slider. Set 50 cm, trigger the PIR, then drop
  to 44 cm within 1 s for a confirmed deposit; leave it at 50 cm for a false
  trigger.
- **NeoPixel** — watch the colour and blink pattern.

---

## Options considered and not used

- **QEMU** (`qemu-system-xtensa` with Espressif's ESP32 patches) boots the real
  firmware image but simulates no PIR, ultrasonic or WS2812. It would tell you
  the binary boots and nothing about this application. Layer 3 strictly dominates.
- **Renode** supports ESP32 but needs a hand-written platform description for
  every peripheral — a lot of work for what Wokwi gives for free.
- **`wokwi-cli`** would let layer 3 run headless in CI, which is the natural next
  step, but it needs a token from wokwi.com.

## Suggested loop

```bash
# while editing logic — instant
pio test -e native

# after touching anything device↔backend — needs the backend running
pio run -e sim && ./.pio/build/sim/program --base-url http://127.0.0.1:8123 --device-key <key>

# before believing anything about GPIO or the LED
pio run -e wokwi           # then open diagram.json in Wokwi

# backend
pytest tests/ -q && ruff check src/ tests/
```
