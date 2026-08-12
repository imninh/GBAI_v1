# Handoff — GreenBinAI IoT Phase 1

**For the next agent (Codex) picking this up.**
Written 2026-08-11, revised 2026-08-12 after Checkpoint 1.
Read this first, then [iot-checkpoint-1.md](iot-checkpoint-1.md) for the
simulated-hardware flow, then [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md).

---

## 1. Where things stand

Phase 1 is **functionally complete in software** and verified at three layers.
Checkpoint 1 added the simulated-hardware layer: OLED, servo sorter, WiFi
heartbeat and a serial test console, all driven through the existing HAL.
**Nothing has run on physical hardware.**

| Check | Command | Last result |
|---|---|---|
| Backend tests | `pytest tests/ -q` | **56 passed** |
| Backend lint | `ruff check src/ tests/` | **clean** |
| Firmware logic | `cd iot/firmware && pio test -e native` | **51/51 passed** |
| Firmware build | `pio run -e esp32cam` | **SUCCESS** (RAM 15.9 %, Flash 32.8 %) |
| Mock build | `pio run -e esp32cam_mock` | **SUCCESS** (RAM 14.5 %, Flash 30.6 %) |
| Wokwi build | `pio run -e wokwi` | **SUCCESS** (RAM 14.7 %, Flash 31.8 %) |
| Wokwi + webcam build | `pio run -e wokwi_camera` | **SUCCESS** (RAM 14.7 %, Flash 32.2 %) |
| End-to-end | `pio run -e sim` + backend (see §3) | **27/27 checks** |
| Wokwi diagram | `wokwi-cli lint` v0.26.1 | **0 errors** — *last run 2026-08-11* |

Every row except the last was re-executed on 2026-08-12 against the current
tree. `wokwi-cli` is **not installed in this environment** and is not on npm
under `wokwi-cli` or `@wokwi/cli`, so the diagram lint could not be repeated —
and `diagram.json` has changed since that result. Re-lint before trusting it.

### The one thing you must know about this repo

The specification (`~/Downloads/guide_greenbinAI.md`) instructs *"REUSE existing
services, do not duplicate classifier.py"*. **That premise was false.** `P-075` was
the unmodified AI20K starter template — no classifier, no privacy pipeline, no bin
readings, no vision routing, nothing. The user was consulted and chose to build a
minimal backend slice in-repo. So when the spec says "reuse", read "the thing that
was built here in M6". Details: [milestone-0-repo-map.md](milestone-0-repo-map.md) §1.

---

## 2. Layout

```
iot/
├── firmware/
│   ├── platformio.ini          # 6 envs: esp32cam, esp32cam_mock, wokwi,
│   │                           #         wokwi_camera, sim, native
│   ├── include/
│   │   ├── config.h            # ALL tunables. No magic numbers elsewhere
│   │   ├── secrets.example.h   # copy → secrets.h (gitignored)
│   │   ├── core/               # pure logic headers — NO Arduino.h allowed
│   │   │   ├── hal.h           # device interfaces (display, sorter, camera…)
│   │   │   ├── null_devices.h  # no-op HAL impls for builds without the part
│   │   │   ├── waste.h         # label → bin mapping, sortability
│   │   │   └── {state_machine,classification,fill_level,retry_policy,logging}.h
│   │   └── hw/                 # driver headers
│   │       ├── oled_display.h  # SSD1306 (I2C)
│   │       ├── servo_sorter.h  # sorting flap
│   │       ├── host_camera.h   # pulls JPEG from webcam_service.py
│   │       ├── mock_camera.h   # fixture JPEG, no OV2640
│   │       ├── mock_backend.h  # offline classifier — no HTTP
│   │       ├── wifi_heartbeat.h# P1, idle-only
│   │       └── test_console.h  # serial hardware test menu
│   ├── src/                    # mirrors include/ one-for-one
│   │   ├── core/               # state machine, fill maths, retry, waste
│   │   ├── hw/                 # sensors, camera, LED, OLED, servo, network
│   │   ├── sim/                # desktop simulator (NOT compiled into firmware)
│   │   └── main.cpp            # wiring only
│   └── test/{test_logic,test_scenarios}/
├── simulation/
│   ├── diagram.json            # Wokwi circuit
│   ├── wokwi.toml              # per-env firmware paths
│   ├── webcam_service.py       # serves real webcam frames to wokwi_camera
│   ├── check_vision.py         # runs the device's exact vision path, offline
│   ├── fixtures/               # fixture JPEG for the mock camera
│   └── scenarios/              # checkpoint1-flow.yaml, checkpoint1-selftest.yaml
└── docs/                       # you are here

src/                            # backend additions
├── api/iot.py                  # router — HTTP concerns only
├── services/{image_privacy,classification,vision,safety,device_auth,bin_readings}.py
└── agents/{classify_graph.py,nodes/classify_nodes.py}
```

**Which build gets which parts.** `GREENBIN_HAS_SORTER` / `GREENBIN_HAS_DISPLAY`
compile the servo and OLED in; when they are absent, `main.cpp` injects
`NullSorter` / `NullDisplay` from `core/null_devices.h` instead. This is why the
`esp32cam` build drops both — on the AI-Thinker board GPIO18/21/22 are camera
data lines. The flow is identical in every build and the null sorter honestly
reports that it never moved. Full flag table: [iot-checkpoint-1.md](iot-checkpoint-1.md) §Wokwi.

**The layering rule that everything depends on:** `src/core/` must never include
`Arduino.h`. The `native` env compiles `src/core/` alone, so a violation breaks
`pio test` immediately. This is what makes the state machine testable and a future
ESP32-S3 port cheap. Do not weaken it.

---

## 3. Running it

```bash
# Backend
cd /home/TranPhuNghia_20233871/P-075
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src/ tests/

# Firmware
cd iot/firmware
/home/TranPhuNghia_20233871/P-075/.venv/bin/pio test -e native    # logic, ~1s
/home/TranPhuNghia_20233871/P-075/.venv/bin/pio run  -e esp32cam  # real build
```

**End-to-end** (this is the highest-value loop with no hardware):

```bash
# Terminal 1
cd /home/TranPhuNghia_20233871/P-075
IOT_DEVICE_KEYS="GBIN-001:sim-test-key" \
VISION_PROVIDER=stub STUB_VISION_LABEL=plastic STUB_VISION_CONFIDENCE=0.94 \
  .venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8123

# Terminal 2
cd iot/firmware
pio run -e sim
./.pio/build/sim/program --base-url http://127.0.0.1:8123 --device-key sim-test-key
```

**Wokwi** (simulated hardware — OLED, servo, NeoPixel, PIR, HC-SR04):

```bash
cd iot/firmware
pio run -e wokwi     # then open iot/simulation/diagram.json in the
                     # Wokwi VS Code extension and press ▶
```

This build needs no backend and no network: the camera is a fixture JPEG and the
classifier is `MockBackendService`. The serial test console and the expected
demo flow are documented step by step in
**[iot-checkpoint-1.md](iot-checkpoint-1.md)** — read that before running the
simulation, not after.

`pio` is **not** on PATH — it lives in `.venv/bin/pio`.
Full guide: [testing-without-hardware.md](testing-without-hardware.md).

**Debugging a `refused` result** — `check_vision.py` runs the device's exact
vision path (same preprocessing, same prompt, same model) and prints the raw
reply, so you can tell "model never ran" from "model refused" without a Wokwi
round trip:

```bash
.venv/bin/python iot/simulation/check_vision.py --image photo.jpg
```

---

## 4. Gotchas that cost time — do not rediscover these

1. **ESP32 Arduino core compiles at C++11.** A struct with default member
   initialisers is not an aggregate there, so `Foo{true, 1.0f}` fails to compile
   even though it works in the C++17 `native` env. `DistanceReading` and
   `FillResult` therefore have explicit constructors. Add them to any new POD you
   brace-initialise in `hw/` code.
2. **`test_build_src = yes`** is required in `[env:native]`, or PlatformIO does not
   link `src/` into tests and you get a wall of undefined references.
3. **`build_src_filter` must exclude `sim/`** from `esp32cam` and `esp32cam_mock`,
   or the POSIX socket code goes into the firmware build and fails.
4. **OpenCV must be `<5`.** OpenCV 5 removed `CascadeClassifier` and ships an empty
   `cv2/data/`, silently disabling face blurring. Pinned in `requirements.txt`.
5. **`langchain_gemini` 0.1.1 is an empty stub** — imports fine, exposes no chat
   class. Do not route to it without checking `dir(module)` first.
6. **Backend settings are `lru_cache`d.** Tests must call `get_settings.cache_clear()`
   *and* `device_auth.reset_cache()` after `monkeypatch.setenv`. See the
   `device_keys` fixture in `tests/test_api/test_iot.py`.
7. **A real `.env` exists** with live values. Env vars override it; tests rely on that.
8. **PIR re-arm and `SHOW_RESULT` interact across scenarios.** Back-to-back events
   against one device need `settleToIdle()` and a wait past `PIR_REARM_MS`. Unit
   tests build a fresh machine each time and never hit this; the simulator does.
   Both simulator failures found so far were harness bugs, not firmware bugs — check
   which before "fixing" the state machine.
9. **`webcam_service.py` binds `0.0.0.0`, not localhost** — it has to, because the
   simulated ESP32 sits on the Wokwi gateway's virtual network. Anyone on your LAN
   who finds port 8124 can pull a frame, and the camera indicator light stays on
   the whole time. Stop it when the demo ends.
10. **`SERVO_SETTLE_MS` blocks for 400 ms.** It is the only blocking call left in
    the flow, and it is deliberate: a hobby servo has no position feedback, so
    there is nothing to poll. Do not "fix" it with a shorter wait.
11. **`pkill -f "uvicorn src.main:app"` kills your own shell** when you are an
    agent whose command string contains that literal text — the pattern matches
    the wrapper process too. Bracket a character (`src[.]main`) and it *still*
    matches, because the bracketed pattern itself is in the command line. Kill by
    port or by PID instead. This costs ten minutes and looks like a crash.

---

## 5. What to do next, in priority order

### ~~P0 — Run the Wokwi simulation interactively~~ — done in Checkpoint 1
The circuit now carries an SSD1306 OLED and a servo alongside the PIR, HC-SR04
and NeoPixel, and the whole flow runs in the VS Code extension. Documented in
[iot-checkpoint-1.md](iot-checkpoint-1.md): pin map, serial commands, expected
demo flow, and an optional real-webcam path (`wokwi_camera` + `webcam_service.py`).

**What is still not done here:** the two scenario files
(`simulation/scenarios/checkpoint1-{flow,selftest}.yaml`) have **never been
executed** — running them needs a `WOKWI_CLI_TOKEN`. They are written, not
verified. Same for the diagram lint (see §1).

### P1 — Physical hardware validation
Nothing electrical is verified. Work through
[pin-map.md](pin-map.md) §7 before powering anything. The two connections that can
destroy a board:
- **HC-SR04 `ECHO` is 5 V into a non-5V-tolerant GPIO12** → divider required, or use
  the HC-SR04**P** (3.3 V) which is the recommended part.
- **GPIO12 is the MTDI strapping pin** → anything holding it high at reset prevents
  boot on a 3.3 V-flash module. If the board boots without the ECHO wire but not
  with it, that is the cause.

### P2 — Persist bin readings
`src/services/bin_readings.py` is in-memory and dies with the process. The
`BinReadingRepository` ABC is the seam; SQLAlchemy 2.0.51 is already installed and
unused. Add a `SqlAlchemyBinReadingRepository` and swap `get_repository()`.

### P3 — Real Vision provider — *plumbing done, verification still open*
The routing is finished: `VISION_PROVIDER=openai` plus an optional
`VISION_BASE_URL` reaches any OpenAI-compatible endpoint — plain OpenAI, Google
AI Studio (`gemini-2.5-flash`), OpenRouter. Only the host and model name change;
see [.env.example](../../.env.example). `base_url` is passed only when
configured, so the default path is byte-for-byte the old plain-OpenAI one.
Covered by `tests/test_services/test_vision.py`.

**What is still open:** the label set has **never been checked against a real
model's output** in a recorded run. A live key is present in `.env` and
`VISION_PROVIDER=openai` is set there, but no result was captured, so treat the
vocabulary as unverified. Confirm the JSON-only reply survives —
`_parse_model_reply()` deliberately returns an empty label (→ `refused`) rather
than guessing when parsing fails, so a chatty model degrades to a refusal rather
than a wrong bin. Use `check_vision.py` (§3) to see the raw reply.

Note the label set is deliberately wider than the hardware: the backend can
return `glass, organic, battery, chemical, medical, sharps, e-waste, paint,
aerosol`, and a three-bin device **cannot sort those** — they take the refusal
path by design. That is a demo feature, not a gap.

### P4 — Non-blocking upload
`HTTPClient` is synchronous: the device ignores PIR for up to `HTTP_TIMEOUT_MS`
during an upload. `UPLOAD`/`WAIT_RESULT` are already separate states, so an async
client or a FreeRTOS task can slot in without reshaping the state machine.

### P5 — CI
`.github/workflows/ci.yml` runs ruff + pytest only. Add `pio test -e native` and
the `sim` end-to-end run (backend on localhost with `VISION_PROVIDER=stub`). Both
are fast and need no secrets. `wokwi-cli` would add layer 3 but needs a token.

---

## 6. Design decisions worth preserving

Do not "simplify" these away — each exists for a stated reason:

- **`classify_processed_image()` takes `ProcessedImage`, never `bytes`.** This makes
  bypassing the privacy pipeline a *type error*. Spec §26 forbids an IoT bypass;
  this is how that is enforced rather than merely documented.
- **`faces_blurred` is three-valued** — `0` (checked, none), `n` (blurred),
  `null` (**could not check**). Collapsing null into 0 would let a silently
  disabled privacy step look clean.
- **Hazard beats low confidence** in `safety.py`. A possible battery at 0.42
  confidence reports `hazard`, not `warning`.
- **`refused`/`Unknown` map to the warning LED, never green.** `parseStatus()` sends
  unrecognised statuses to `Unknown`; `isConclusive()` gates label display.
- **Bin-full uses hysteresis** (80 % set / 75 % clear) and emits on *transitions
  only*. The spec gives one threshold; one threshold flaps.
- **`fill_percent` is omitted from the multipart body when the reading is invalid**,
  not sent as `0.0`. A missing field is honest; a zero is indistinguishable from an
  empty bin.
- **Every exit from CAPTURE/UPLOAD/WAIT_RESULT calls `releaseFrameIfHeld()`.** A
  leaked framebuffer starves the next capture and looks like a broken camera three
  events later.

---

## 7. Open questions for review

Ranked by cost of being wrong. Fuller list at the end of
[IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md).

1. **GPIO12 = `ECHO`** — is "guaranteed LOW at reset before the first trigger" sound
   reasoning for the MTDI strapping pin? Wrong here bricks boot confusingly.
2. **Is the type-level privacy bypass actually airtight?** Is there any path
   reaching a provider with raw bytes?
3. **The stub Vision provider is production code.** `VISION_PROVIDER=stub` returns a
   canned label. It warns loudly and needs explicit opt-in, but should it be
   guarded harder (e.g. refuse unless `APP_ENV != production`)?
4. **Should `refused` and low-confidence `warning` be visually distinct** on the LED?
   They currently share a pattern.
5. **Is disabling microSD acceptable** as the price of a single-board Phase 1? It
   leaves zero spare GPIOs and no on-device logging.

---

## 8. Housekeeping

- **Committed and pushed.** Phase 1 is already **merged into `main`** (PR #7,
  `3556ba7`). Checkpoint 1 is `ea22cf0` + `638f6b8` on `codex/iot-checkpoint-1`,
  branched from `main`. Not yet merged.
- **Do not use `codex/iot-wokwi-simulation`.** That branch was started from a
  fresh `git init` of the template (the README literally tells you to delete the
  history and re-init), so it has **no common ancestor with `main`** and GitHub
  refuses to diff it: *"entirely different commit histories"*. Its Phase 1 tree
  is byte-identical to `main`'s, so nothing was lost — the two Checkpoint 1
  commits were replayed onto a `main`-based branch and it is now dead weight.
  If you branch from anything, branch from `main`.
- `scripts/_pyrun.sh` was already dirty **before** this work began — not ours.
- Background `uvicorn` processes may still be running on ports 8123–8125 from
  simulator runs: `pkill -f "uvicorn src[.]main:app"`.
- `.gitignore` already covers `iot/firmware/.pio/` and `iot/firmware/include/secrets.h`.
- Do not commit `secrets.h`, and do not put real device keys in `config.h`.
- Nine empty files named after state-machine states (`CAPTURE`, `IDLE`,
  `SORTING`, …) are sitting untracked in the repo root — shell-redirect debris
  from a serial-log session. Deliberately left out of both commits. Delete them.
