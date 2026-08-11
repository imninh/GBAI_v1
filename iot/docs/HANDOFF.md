# Handoff — GreenBinAI IoT Phase 1

**For the next agent (Codex) picking this up.**
Written 2026-08-11. Read this first, then [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md).

---

## 1. Where things stand

Phase 1 is **functionally complete in software** and verified at three layers.
Nothing has run on physical hardware.

| Check | Command | Last result |
|---|---|---|
| Backend tests | `pytest tests/ -q` | **48 passed** |
| Backend lint | `ruff check src/ tests/` | **clean** |
| Firmware logic | `cd iot/firmware && pio test -e native` | **31/31 passed** |
| Firmware build | `pio run -e esp32cam` | **SUCCESS** (RAM 15.8 %, Flash 32.7 %) |
| Mock build | `pio run -e esp32cam_mock` | **SUCCESS** |
| Wokwi build | `pio run -e wokwi` | **SUCCESS** |
| Wokwi diagram | `wokwi-cli lint` v0.26.1 | **0 errors** (1 informational message) |
| End-to-end | `pio run -e sim` + backend (see §3) | **22/22 checks** |

Everything above was actually executed, not assumed.

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
│   ├── platformio.ini          # 5 envs: esp32cam, esp32cam_mock, wokwi, native, sim
│   ├── include/
│   │   ├── config.h            # ALL tunables. No magic numbers elsewhere
│   │   ├── secrets.example.h   # copy → secrets.h (gitignored)
│   │   ├── core/               # pure logic headers — NO Arduino.h allowed
│   │   └── hw/                 # driver headers
│   ├── src/
│   │   ├── core/               # state machine, fill maths, retry, classification
│   │   ├── hw/                 # sensors, camera, LED, network drivers
│   │   ├── sim/                # desktop simulator (NOT compiled into firmware)
│   │   └── main.cpp            # wiring only
│   └── test/{test_logic,test_scenarios}/
├── simulation/                 # Wokwi diagram, wokwi.toml, fixture JPEG
└── docs/                       # you are here

src/                            # backend additions
├── api/iot.py                  # router — HTTP concerns only
├── services/{image_privacy,classification,vision,safety,device_auth,bin_readings}.py
└── agents/{classify_graph.py,nodes/classify_nodes.py}
```

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

`pio` is **not** on PATH — it lives in `.venv/bin/pio`.
Full guide: [testing-without-hardware.md](testing-without-hardware.md).

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

---

## 5. What to do next, in priority order

### P0 — Run the Wokwi simulation interactively
The diagram now passes `wokwi-cli lint` v0.26.1 with zero errors and the dedicated
`wokwi` firmware environment builds. Three blockers were repaired: serial pins
`TX0/RX0` were changed to valid `TX/RX`, the mock camera now returns a real
decodable 160×120 JPEG, and Wokwi gets its own Wi-Fi/backend/timing configuration.
The diagram also models the required 1 kΩ/2 kΩ HC-SR04 ECHO divider.

The remaining step needs the user's Wokwi account: install/activate the VS Code
extension (or set `WOKWI_CLI_TOKEN`), enable the Private IoT Gateway, then run the
scenarios in [simulation/scenarios/README.md](../simulation/scenarios/README.md).

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

### P3 — Real Vision provider
Set `VISION_PROVIDER=openai` + `OPENAI_API_KEY` and tune the prompt in
`src/agents/nodes/classify_nodes.py`. The label set is a first draft that has
**never been run against a real model**. Verify the JSON-only reply survives, since
`_parse_model_reply()` deliberately returns an empty label (→ `refused`) rather than
guessing when parsing fails.

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

- Nothing has been committed. `git status` shows the full working tree; `iot/` is
  untracked, seven existing files modified.
- `scripts/_pyrun.sh` was already dirty **before** this work began — not ours.
- Background `uvicorn` processes may still be running on ports 8123–8125 from
  simulator runs: `pkill -f "uvicorn src.main:app"`.
- `.gitignore` already covers `iot/firmware/.pio/` and `iot/firmware/include/secrets.h`.
- Do not commit `secrets.h`, and do not put real device keys in `config.h`.
