# GreenBinAI IoT Phase 1 — Implementation Report

**For review by: Codex**
**Last updated:** 2026-08-11
**Status:** Milestones 0–9 complete. Firmware builds, 31 native tests pass, 48 backend tests pass, 22/22 host-simulator checks pass against the live backend, Wokwi diagram lint has 0 errors, ruff clean.
**Nothing has been tested on physical hardware** — see [Items not physically verified](#items-not-physically-verified).

---

## Summary

Phase 1 of the GreenBinAI IoT subsystem is implemented end to end in software: an
ESP32-CAM firmware that detects waste deposits using PIR + ultrasonic
corroboration, captures a JPEG, uploads it to the backend, and reflects the
classification on a WS2812 — plus the backend slice that authenticates the device,
runs an image-privacy pipeline, classifies through a LangGraph workflow, applies
safety/HITL rules, and records bin fill readings.

### The finding that reshaped the work

The specification (§1, §9) instructs reuse of an existing GreenBinAI backend —
classifier, privacy pipeline, vision routing, bin readings, HITL, SQLAlchemy
persistence, PWA. **None of it existed.** `P-075` was the unmodified AI20K starter
template: one content commit, a stub LangGraph graph whose nodes interpolate
strings, two example endpoints, five passing tests. Verified by `git log` and by
grepping the tree for `greenbin|classifier|preprocess_image|bin_code|device_key`
— zero matches outside `docs/guide/`.

This was raised before implementation. The user chose to **build the minimal
backend slice in-repo**, designed so it is the thing future code reuses rather
than a parallel IoT-only path. Full analysis in
[milestone-0-repo-map.md](milestone-0-repo-map.md).

### What was built

**Firmware** (`iot/firmware/`) — Arduino/PlatformIO, split into a hardware-free
logic core and thin drivers:

- Explicit 10-state machine implementing the §6 flow; PIR alone never triggers a
  capture — an ultrasonic delta must corroborate it.
- Fill-level calculation with clamping, invalid-reading rejection, and bin-full
  hysteresis so a bin hovering at threshold cannot emit an event stream.
- `LedService` centralising all WS2812 behaviour, with a two-layer
  background/temporary model so persistent bin-full (solid) never reads as a
  transient classification warning (blinking).
- `CameraService` abstraction over the OV2640, plus `MockCameraService` returning
  a fixture JPEG for simulation.
- `NetworkService` doing multipart upload with `X-Device-Key`, bounded retry with
  exponential backoff, and non-blocking Wi-Fi association.

**Backend** (`src/`) — extends the existing FastAPI app; the existing `/chat`
route and graph are untouched:

- `POST /api/v1/iot/captures`, `POST|GET /api/v1/bins/{code}/readings`.
- `preprocess_image()`: validate → strip EXIF → blur faces → resize → pHash.
- LangGraph `vision → safety → END` classification graph with provider routing.
- Safety/HITL rules: hazard labels beat low confidence; unknown is never coerced
  into a class.
- Device authentication with device-bound keys and constant-time comparison.

**Host simulator** (`iot/firmware/src/sim/`) — added after the initial milestones
to close the device↔backend gap without hardware. It compiles the *real* state
machine, serves a *real* JPEG, and posts the *same* multipart body and headers as
the firmware over a real POSIX socket to the running FastAPI backend. Documented
in [testing-without-hardware.md](testing-without-hardware.md).

---

## Files changed

### Added — firmware

| File | Purpose |
|---|---|
| `iot/firmware/platformio.ini` | Five envs: `esp32cam`, `esp32cam_mock`, `wokwi`, `native`, `sim` |
| `iot/firmware/include/config.h` | Every tunable; no magic numbers in logic |
| `iot/firmware/include/secrets.example.h` | Credential template (`secrets.h` is gitignored) |
| `iot/firmware/include/core/hal.h` | The five hardware interfaces |
| `iot/firmware/include/core/{classification,fill_level,retry_policy,state_machine,logging}.h` | Pure-logic headers |
| `iot/firmware/src/core/{classification,fill_level,retry_policy,state_machine}.cpp` | Pure logic |
| `iot/firmware/include/hw/{sensors,camera_service,led_service,network_service,mock_camera}.h` | Driver headers |
| `iot/firmware/src/hw/{sensors,camera_service,led_service,network_service}.cpp` | Drivers |
| `iot/firmware/src/main.cpp` | Wiring only |
| `iot/firmware/test/test_logic/test_logic.cpp` | 17 unit tests |
| `iot/firmware/test/test_scenarios/test_scenarios.cpp` | 14 scenario tests |

### Added — backend

| File | Purpose |
|---|---|
| `src/api/iot.py` | IoT router — HTTP concerns only |
| `src/services/image_privacy.py` | Validation + privacy pipeline |
| `src/services/classification.py` | Classification entry point |
| `src/services/vision.py` | Vision provider routing |
| `src/services/safety.py` | Safety / HITL rules |
| `src/services/device_auth.py` | `X-Device-Key` verification |
| `src/services/bin_readings.py` | Reading validation + repository |
| `src/agents/classify_graph.py` | LangGraph classification workflow |
| `src/agents/nodes/classify_nodes.py` | Vision + safety nodes |
| `tests/test_api/test_iot.py` | 16 endpoint tests |
| `tests/test_services/test_image_privacy.py` | 14 privacy-pipeline tests, including the embedded Wokwi JPEG |
| `tests/test_services/test_safety.py` | 13 safety-rule tests |

### Added — docs & simulation

`iot/docs/{milestone-0-repo-map,pin-map,architecture,api-contract,state-machine,hardware-setup,IMPLEMENTATION_REPORT}.md`,
`iot/simulation/{diagram.json,wokwi.toml,scenarios/README.md}`

### Modified — existing files

| File | Change |
|---|---|
| `src/main.py` | Mount the IoT router (2 lines) |
| `src/config.py` | IoT/vision settings block |
| `src/models/schemas.py` | `ClassifyOutcome`, `IoTCaptureResponse`, `BinReading*` |
| `src/agents/state.py` | Added `ClassifyState` |
| `requirements.txt` | `pillow`, `python-multipart`, `opencv-python-headless<5` |
| `.gitignore` | `iot/firmware/.pio/`, `iot/firmware/include/secrets.h` |

`scripts/_pyrun.sh` was already modified in the working tree before this work
began and was not touched.

---

## Architecture decisions

### D1 — Pin selection: PIR→13, TRIG→14, ECHO→12, LED→15

The OV2640 consumes 15 GPIOs, UART logging 2, PSRAM chip-select 1. With microSD
disabled, exactly four clean GPIOs remain for exactly four signals — **zero
spare**.

Assignment was driven by strapping constraints, not convenience. GPIO12 (MTDI)
must read LOW at reset or a 3.3 V-flash module will not boot, so it went to
`ECHO`, whose idle-low state before the first trigger is *guaranteed*. GPIO13 has
no strapping role, so it took the PIR, whose output can float high during the
HC-SR501's 30–60 s power-up calibration. GPIO15's strapping role affects only
boot-log verbosity, making it safe for the LED. Full rationale in
[pin-map.md](pin-map.md) §4.

### D2 — Hardware behind interfaces; `src/core` cannot include Arduino.h

The state machine depends on five interfaces and takes time as a parameter. The
`native` PlatformIO env compiles `src/core/` alone, so a stray `#include
<Arduino.h>` in core code breaks the test build immediately. This is what makes
all nine §19 scenarios runnable as sub-second desktop tests, and what would
confine an ESP32-S3 port to `src/hw/`.

### D3 — Privacy bypass made a type error

`classify_processed_image()` accepts a `ProcessedImage`, not `bytes`. There is no
overload taking raw data. Handing an unprocessed device image to a model provider
does not compile, rather than depending on a reviewer noticing. This is the
mechanism behind spec §10's "do not create an IoT bypass".

### D4 — `faces_blurred` is three-valued

`0` = detection ran, none found. `n` = faces blurred. **`null` = detection could
not run.** Collapsing the last two into `0` would let a silently-disabled privacy
step look like a clean result.

### D5 — HTTP architecture

Synchronous `HTTPClient`. `UPLOAD` and `WAIT_RESULT` are separate states as the
spec requires, but the request blocks up to `HTTP_TIMEOUT_MS`. Chosen for Phase 1
simplicity; the cost is that the device ignores PIR during an upload. Listed under
Known issues.

### D6 — Bin-full hysteresis

Spec §14 gives one threshold (80 %). One threshold makes a bin sitting at exactly
80 % flap between states and emit endless transitions. A separate
`FULL_CLEAR_PERCENT` (75 %) was added; the full→normal transition needs the level
to drop below it.

### D7 — Multipart omits `fill_percent` when the reading is invalid

Rather than sending `0.0`, the field is left out entirely. A missing field is
honest; a zero would be indistinguishable from a genuinely empty bin.

### D8 — `secrets.example.h`, not `config.example.h`

Spec §17 names `config.example.h`. Splitting secrets from tunables is safer:
`config.h` stays committed and reviewable while only the small credential file is
sensitive. `config.h` falls back to placeholders via `__has_include`, so a fresh
clone builds. Name adapted as permitted by spec §5.

---

## Test evidence

All output below is real, captured from this environment.

### Firmware build — ESP32 target

```console
$ cd iot/firmware && pio run -e esp32cam
RAM:   [==        ]  15.8% (used 51872 bytes from 327680 bytes)
Flash: [===       ]  32.7% (used 1028361 bytes from 3145728 bytes)
========================= [SUCCESS] Took 2.45 seconds =========================

Environment    Status    Duration
-------------  --------  ------------
esp32cam       SUCCESS   00:00:02.451
========================= 1 succeeded in 00:00:02.451 =========================
```

`pio run -e esp32cam_mock` also succeeds. The dedicated `pio run -e wokwi`
environment adds Wokwi network/timing settings and succeeds at 14.5% RAM / 30.5%
flash.

### Wokwi static validation

```console
$ cd iot/simulation && wokwi-cli lint
Wokwi CLI v0.26.1
Found 1 info
```

There are **zero errors**. The one informational message notes that
`board-esp32-devkit-c-v4` uses an undocumented part definition. The full timed
simulation still needs a Wokwi token or an activated editor extension.

### Firmware unit + scenario tests

```console
$ cd iot/firmware && pio test -e native
=================================== SUMMARY ===================================
Environment    Test            Status    Duration
-------------  --------------  --------  ------------
native         test_logic      PASSED    00:00:00.533
native         test_scenarios  PASSED    00:00:00.609
================= 31 test cases: 31 succeeded in 00:00:01.142 =================
```

Scenario coverage (spec §19), all passing:

| # | Scenario | Test |
|---|---|---|
| 1 | Person walks past → no capture, no vision call | `test_scenario1_false_trigger_captures_nothing` |
| 2 | Valid event → capture + upload | `test_scenario2_valid_event_captures_and_uploads` |
| 3 | `ok` → green, return to IDLE | `test_scenario3_ok_shows_green_and_returns_idle` |
| 4 | Low confidence / refused → not success | `test_scenario4_warning_...`, `test_scenario4_refused_...` |
| 5 | Hazard → hazard pattern | `test_scenario5_hazard_pattern` |
| 6 | Timeout → bounded retry, recovery | `test_scenario6_timeout_retries_bounded_then_recovers` |
| 7 | Bin full → reading sent, solid red, no repeats | `test_scenario7_bin_full_sends_reading_and_goes_solid` |
| 8 | Bin emptied → changed reading | `test_scenario8_bin_emptied_sends_changed_reading` |
| 9 | Invalid reading → no bogus fill | `test_scenario9_...`, `test_invalid_baseline_blocks_capture` |

Plus: camera failure recovers without reboot, Wi-Fi never blocks forever, failed
bin readings are retried rather than lost.

### End-to-end: host simulator against the live backend

```console
$ pio run -e sim
$ ./.pio/build/sim/program --base-url http://127.0.0.1:8123 --device-key sim-test-key

=== Scenario 2/3 — valid waste event, real upload ===
[ULTRASONIC] before=50.0 after=44.0 delta=6.0
[EVENT] waste_confirmed
[CAMERA] jpeg_bytes=10223
[PRIVACY] phash=ffe7e7e7e7c3c3ff exif_stripped=true faces_blurred=0 bytes=6577
[HTTP] upload status=200
[AI] status=ok label=plastic confidence=0.94
[LED] OK
 22/22 checks passed
```

Hazard path, same harness, `STUB_VISION_LABEL=battery STUB_VISION_CONFIDENCE=0.42`:

```console
[AI] status=hazard label=battery confidence=0.42
  LED showed  : HAZARD
 22/22 checks passed
```

Confidence 0.42 is *below* the 0.6 low-confidence threshold, yet the result is
`hazard` rather than `warning` — confirming the safety-rule ordering end to end.

Two bugs were found here that the unit tests could not see, both in the harness
rather than the firmware: back-to-back events were suppressed by the PIR re-arm
cool-down, and `SHOW_RESULT` had to expire before a fill check could run. Each
unit test builds a fresh state machine, so neither cross-scenario interaction was
reachable there. This is the value of the layer.

### Backend tests

```console
$ pytest tests/ -q
................................................                         [100%]
48 passed in 1.54s

$ ruff check src/ tests/
All checks passed!
```

48 = 5 pre-existing (still passing, no regression) + 43 new.

Spec §21 checklist: valid device key ✅ · invalid device key ✅ · missing device
key ✅ · image upload ✅ · invalid image ✅ · classifier service reuse ✅ ·
low-confidence/refused response ✅ · sensor reading validation ✅ · fill percent
range ✅.

### A failure found and fixed during testing

`test_scenario6` initially failed: expected `IDLE`, got `PRESENCE_DETECTED`. The
firmware was correct — the fake PIR stayed HIGH forever, so after recovering the
device correctly began a new detection cycle. The *test* was unrealistic; the fake
now drops the line after triggering, as an HC-SR501 does. Recorded because the
distinction between a firmware bug and a test bug matters to a reviewer.

---

## Known issues

1. **Bin readings are in-memory only.** They do not survive a restart. The
   repository interface is the swappable seam; a SQLAlchemy implementation is the
   intended follow-up. SQLAlchemy 2.0.51 is already installed but unused.
2. **Uploads block.** Synchronous `HTTPClient` means the device ignores PIR for up
   to `HTTP_TIMEOUT_MS` during an upload (D5).
3. **`Hcsr04DistanceSensor::read()` blocks** up to ~270 ms (3 samples).
4. **Only OpenAI is wired as a Vision provider.** `langchain-gemini` 0.1.1 is
   installed but is an empty stub exposing no chat class — verified by
   introspection, not assumed.
5. **Face blurring requires OpenCV < 5.** OpenCV 5.0 removed `CascadeClassifier`
   and ships no bundled model (its `cv2/data/` contains only `__init__.py`).
   `requirements.txt` pins `<5.0.0`. Without OpenCV, `faces_blurred` is `null`.
6. **The full Wokwi simulation has not been executed.** The CLI was downloaded
   temporarily and `wokwi-cli lint` reports zero diagram errors; `pio run -e wokwi`
   also succeeds. Running the binary still requires a `WOKWI_CLI_TOKEN` or an
   activated editor extension, plus the Private IoT Gateway for localhost access.
7. **`.venv` is Python 3.12.3; CI pins 3.11.** Code is 3.11-compatible and ruff
   targets py311, but local green does not prove CI green.
8. **Zero spare GPIOs.** No Phase 2 headroom on this board ([pin-map.md](pin-map.md) §6).
9. **The classification prompt is untuned.** The label set in
   `classify_nodes.py` is a first draft, never run against a real vision model
   here (no API key). Expect prompt iteration once a key is available.
10. ~~No end-to-end run.~~ **CLOSED.** The host simulator (`env:sim`) now drives the
    real state machine against the live backend over a real socket: 22/22 checks
    pass, including a real multipart upload returning HTTP 200 with privacy-pipeline
    evidence. Still not run on the ESP32 binary itself — that is Wokwi's job (#6)
    and hardware's (below).
11. **A stub Vision provider exists.** `VISION_PROVIDER=stub` returns a canned label
    without calling any model, so the LED paths can be tested without an API key.
    It logs a warning on every call and requires explicit opt-in, but it is
    production code and should be reviewed as such
    ([vision.py](../../src/services/vision.py)).

---

## Hardware assumptions

- **Board:** AI Thinker ESP32-CAM, ESP32-S module, OV2640, 4 MB PSRAM. Not
  confirmed against a physical unit.
- **Camera model:** `CAMERA_MODEL_AI_THINKER`; `RESET` not connected.
- **PSRAM present and enabled** — required for JPEG framebuffers and the reason
  GPIO16 is unavailable. Firmware falls back to QVGA if absent.
- **microSD not used.** Load-bearing for the entire pin map.
- **PIR:** HC-SR501, 3.3 V output, repeat/H jumper, minimum delay.
- **Ultrasonic:** HC-SR04 assumed 5 V → divider mandatory. **HC-SR04P recommended.**
- **LED:** one WS2812 powered from **3.3 V** for logic-level compatibility.
- **Supply:** external 5 V ≥ 2 A. Not a USB-TTL adapter's 5 V pin.
- Spec's "HCSR401" read as **HC-SR04** per §2.

---

## Items not physically verified

| Evidence level | Items |
|---|---|
| ✅ **Backend tested** (real code, real HTTP, mocked model) | Device auth (valid/invalid/missing/impersonation), multipart upload, image validation and rejection, EXIF stripping, resize, pHash, classifier reuse through the shared graph, safety rules, bin reading validation and range enforcement, listing |
| ✅ **Unit tested** (native, fakes) | State transitions, PIR+ultrasonic corroboration, false-trigger rejection, fill maths, clamping, bin-full hysteresis, retry bounds and backoff, LED mapping, framebuffer release, all nine §19 scenarios |
| ✅ **End-to-end tested** (real socket, real backend, desktop build) | Multipart framing, `X-Device-Key` on the wire, privacy pipeline over a real JPEG, classification response parsing, LED mapping for ok/hazard/error, bin-reading POST, bounded retry against a closed port |
| ✅ **Compiled** | ESP32 firmware for `esp32cam`, `esp32cam_mock`, and the dedicated `wokwi` environment |
| ✅ **Statically validated** | Wokwi diagram: current CLI reports zero invalid parts/pins/connections; embedded mock JPEG passes the backend privacy pipeline |
| ⚠️ **Built but not executed** | Full Wokwi hardware simulation — no token/license available in this session (Known issue 6) |
| ❌ **NOT physically tested** | **Everything hardware.** No board was powered. The pin map, the ECHO divider, WS2812 logic levels at 3.3 V, OV2640 initialisation, real JPEG capture, PSRAM allocation of the multipart buffer, HC-SR501 timing, HC-SR04 accuracy, Wi-Fi association, and any real HTTP request from a device — all unverified |
| ❌ **NOT tested against a real model** | No API key; every classification test mocks the provider (Known issue 9) |

**No hardware functionality is claimed.** Everything above the hardware line is
software behaviour demonstrated by tests; everything at or below it is design.

---

## Commands to run everything

```bash
# Backend
pip install -r requirements.txt
pytest tests/ -q
ruff check src/ tests/
uvicorn src.main:app --reload --port 8000     # docs at /docs

# Firmware
cd iot/firmware
cp include/secrets.example.h include/secrets.h   # then edit
pio test -e native            # 31 tests, no hardware needed
pio run  -e esp32cam          # real build
pio run  -e esp32cam_mock     # generic mock-camera build
pio run  -e wokwi             # Wokwi-GUEST + local gateway URL + short timings
pio run  -e esp32cam -t upload
pio device monitor -b 115200
```

Backend `.env` additions:

```
IOT_DEVICE_KEYS=GBIN-001:choose-a-long-random-key
VISION_PROVIDER=openai
VISION_MODEL_NAME=gpt-4o-mini
LOW_CONFIDENCE_THRESHOLD=0.6
```

---

## Follow-up for reviewer (Codex)

Ranked by how much a wrong answer costs:

1. **GPIO12 = `ECHO`** — the riskiest decision. Is "guaranteed LOW at reset before
   the first trigger" sound reasoning for the MTDI strapping pin, and is `ECHO`
   genuinely safer there than the WS2812 line? A wrong call here bricks boot in a
   way students will struggle to diagnose.
2. **Privacy pipeline completeness** — is validate → EXIF strip → face blur →
   resize → pHash sufficient before an external provider? Note face blurring is
   frontal-only Haar and will miss profiles.
3. **Is the type-level bypass prevention real?** `classify_processed_image` takes
   `ProcessedImage`. Is there a path that reaches a provider with raw bytes?
4. **Safety rule ordering** — hazard is checked before the confidence threshold, so
   a low-confidence "battery" is reported as `hazard`. Is that the right bias?
5. **The `refused`/`Unknown` → warning-LED mapping** — the device shows the same
   pattern for "low confidence" and "backend refused". Should these be visually
   distinct?
6. **Bin-full hysteresis at 75/80** — reasonable, or should the gap be wider?
7. **In-memory bin readings** — acceptable for Phase 1, or should SQLAlchemy land
   now given it is already a dependency?
8. ~~**Wokwi diagram correctness**~~ — **CLOSED for static validation.** Wokwi CLI
   v0.26.1 reports zero errors. Interactive/timed behaviour still needs the
   user's Wokwi account and Private IoT Gateway.
9. **`FILL_INTERVAL_MS` blocking cost** — 3 ultrasonic samples every 5 minutes
   blocks ~270 ms. Acceptable, or should sampling be non-blocking?
