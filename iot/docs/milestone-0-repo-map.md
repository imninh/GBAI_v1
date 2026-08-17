# Milestone 0 — Repository Map, Gap Analysis & Milestone Plan

Status: **complete**
Date: 2026-08-11
Branch inspected: `nghiatran0106/empty-commit` (4 commits, template + 3 empty/test commits)

This document is the output of the mandatory pre-implementation inspection required by
`guide_greenbinAI.md` §27 Milestone 0. **No firmware or backend code has been written yet.**

---

## 1. Headline finding — the specification's core premise does not hold

The specification states (§1, §9):

> Existing software architecture includes: FastAPI backend, LangGraph agent workflow,
> SQLAlchemy/PostgreSQL, Vision model routing, Image preprocessing/privacy pipeline,
> Bin monitoring APIs, Web/PWA frontend, HITL safety mechanisms.
>
> REUSE existing services. Do not duplicate `classifier.py` logic.

**None of that exists in this repository.**

`P-075` is the **unmodified AI20K Build Phase starter template**
(`AI20K-Build-Cohort-2/starter-code-template`). Verification:

```
$ git log --oneline
7926600 test
b5dd330 chore: empty commit to test AI log
cebe20e chore: empty commit
a12045d feat: khởi tạo dự án từ template   # <- the only commit with content

$ grep -rniE "greenbin|classifier|preprocess_image|bin_code|device_key|esp32" \
    --include=*.py --include=*.md --include=*.toml . | grep -v ./docs/guide/
(no matches)
```

The only GreenBinAI artefacts that exist anywhere on this machine are **documents**, not code
(`~/Downloads/GreenBinAI_*.docx|pdf|pptx` and the `GreenBin_Ops_Gate01_2026-08-02` bundle, which
contains a PRD, a research report and a static HTML prototype — no backend service code).

**Consequence:** spec sections §9, §10, §11 and §14 instruct reuse of services that must first be
*created*. Milestone 6 therefore changes character: from *"integrate with the existing classifier"*
to *"build the minimal backend slice, designed so that it is the thing future code reuses."*
This is flagged for decision rather than silently assumed — see §5 below.

---

## 2. What actually exists

### 2.1 Source tree

| Path | Contents | Relevance to IoT Phase 1 |
|---|---|---|
| [src/main.py](../../src/main.py) | FastAPI app; CORS middleware; `GET /health`; mounts `router` at `/api/v1`; `lifespan` prints startup banner | **Extension point** — IoT router mounts here |
| [src/api/routes.py](../../src/api/routes.py) | `POST /api/v1/chat`, `GET /api/v1/status`. Thin: delegates to `agent.ainvoke`, wraps errors in `HTTPException(500, str(e))` | Convention source for the IoT router |
| [src/models/schemas.py](../../src/models/schemas.py) | `ChatRequest`, `ChatResponse` — Pydantic v2, `Field(...)` with `description=` | Convention source for IoT schemas |
| [src/agents/graph.py](../../src/agents/graph.py) | LangGraph `StateGraph`: `analyze` → conditional → `respond` → `END`. Compiled at import time as module-level `agent` | The agent the classifier would route through |
| [src/agents/state.py](../../src/agents/state.py) | `AgentState(TypedDict, total=False)`: `query, context, analysis, response, error, metadata` | Would need image/classification fields |
| [src/agents/nodes/example_node.py](../../src/agents/nodes/example_node.py) | `analyze_node`, `respond_node` — **pure stubs**, string interpolation only, `# TODO` markers, no LLM call | Not a classifier |
| [src/agents/tools/example_tool.py](../../src/agents/tools/example_tool.py) | `search_knowledge` (stub), `calculate` (real, AST-based safe evaluator) | Not relevant |
| [src/services/llm.py](../../src/services/llm.py) | `get_llm() -> ChatOpenAI` from settings | Text LLM only — **no vision model routing** |
| [src/config.py](../../src/config.py) | `Settings(BaseSettings)`, `env_file=".env"`, `extra="ignore"`, `@lru_cache get_settings()` | **Extension point** — IoT settings go here |
| [tests/conftest.py](../../tests/conftest.py) | `client` fixture (httpx `ASGITransport` against `app`), `mock_llm` fixture (`AsyncMock`) | Test harness to reuse |
| [tests/test_api/test_routes.py](../../tests/test_api/test_routes.py) | 3 tests: health, 422 validation, status | Convention source |
| [tests/test_agents/test_graph.py](../../tests/test_agents/test_graph.py) | 2 tests over `agent.ainvoke` | — |

### 2.2 Conventions to follow

- **Style:** `ruff.toml` — `target-version = "py311"`, `line-length = 120`, `select = ["E","F","I","N","W","UP"]`, `ignore = ["E501"]`, double quotes.
- **Config:** all settings via `pydantic-settings` on the single `Settings` class; never `os.getenv` at call sites.
- **Routers:** thin. HTTP concern in `src/api/`, business logic in `src/services/`. The spec (§9) repeats this rule, so it aligns.
- **Errors:** `raise HTTPException(status_code=..., detail=str(e))`. There is no structured error envelope yet, so "follow existing error-response conventions" (§21) means plain `{"detail": "..."}`.
- **Tests:** `pytest` + `pytest-asyncio`, `@pytest.mark.asyncio`, async `client` fixture.
- **Language:** README and code docstrings are **Vietnamese**; identifiers are English.
  *Decision:* new IoT firmware/backend code uses **English** identifiers, comments and docs, because
  the specification, the Wokwi/PlatformIO ecosystem and the reviewing agent (Codex) are all English.
  Existing Python files are left untouched in their current language.

### 2.3 Environment (measured, not assumed)

| Item | Value | Note |
|---|---|---|
| `.venv` Python | **3.12.3** | CI pins **3.11**, ruff targets **py311** — mismatch; keep code 3.11-compatible |
| Baseline test suite | `pytest tests/ -q` → **5 passed in 0.03s** | Green before any change |
| `fastapi` | 0.139.2 | |
| `langgraph` / `langchain` | 1.2.9 / 1.3.14 | v1 APIs, not 0.x |
| `SQLAlchemy` | 2.0.51 **installed but unused**; commented out in `requirements.txt` | |
| `langchain-gemini` | 0.1.1 installed | A vision-capable provider is reachable |
| `python-multipart` | **NOT installed** | **Required** for `multipart/form-data` upload (§8) |
| `Pillow` | **NOT installed** | **Required** for image validation / EXIF strip / resize (§10) |
| PlatformIO | **NOT installed** (`which pio` → not found) | Installable; network to PyPI confirmed reachable |
| Network | PyPI reachable (HTTP 200) | First `pio run` must download the `espressif32` toolchain (~200 MB) |

### 2.4 Missing versus the specification's assumptions

| §  | Spec assumes exists | Reality |
|----|---------------------|---------|
| 9  | `classifier.py` / classification service | ❌ absent |
| 9  | Vision model routing | ❌ absent (`llm.py` is text-only `ChatOpenAI`) |
| 10 | `preprocess_image()`, EXIF strip, face blur, resize, pHash | ❌ absent entirely |
| 11 | `ClassifyOutcome` structure | ❌ absent |
| 11 | HITL / safety mechanism | ❌ absent |
| 14 | `/api/v1/bins/{code}/readings` + bin-readings concept | ❌ absent |
| 14 | "existing device authentication conventions" | ❌ absent (no auth of any kind) |
| 9  | Image/media persistence | ❌ absent (no DB models, no migrations, no storage) |
| 1  | SQLAlchemy/PostgreSQL layer | ❌ absent (dependency installed, zero usage) |
| 1  | Web/PWA frontend | ❌ absent |

Nothing in the repo needs to be *avoided* to prevent duplication — there is nothing to duplicate.
The engineering rule from §26 ("never bypass image privacy preprocessing") still binds, but it must
be satisfied by **building** the preprocessing step, not by calling an existing one.

---

## 3. Pin feasibility — summary

Full analysis with rationale: **[pin-map.md](pin-map.md)**.

**Verdict: a single AI Thinker ESP32-CAM is feasible for Phase 1 — with exactly zero spare GPIOs.**

- The OV2640 consumes 15 GPIOs: `0, 5, 18, 19, 21, 22, 23, 25, 26, 27, 32, 34, 35, 36, 39`.
- `GPIO1/3` reserved for UART serial logging (required by §20) and flashing.
- `GPIO16` reserved for **PSRAM chip-select** — PSRAM is required for JPEG framebuffers, so 16 is unavailable.
- `GPIO4` is the bright white flash LED (and SD D1); `GPIO33` is the onboard red LED, not broken out.
- Assuming microSD is unused (permitted by §3 item 4), exactly four clean GPIOs remain: **12, 13, 14, 15**.
- Phase 1 needs exactly four signals: PIR, HC-SR04 TRIG, HC-SR04 ECHO, WS2812 DIN. **4 available, 4 needed.**

Two electrical hazards are documented and mitigated rather than assumed away:
HC-SR04 `ECHO` emits **5 V** into a **non-5V-tolerant** ESP32 pin (divider required), and a 5 V-powered
WS2812 needs 3.5 V logic-high which 3.3 V GPIO cannot guarantee (run the pixel at 3.3 V). Details in
[pin-map.md](pin-map.md) §5.

Because there is no headroom, Phase 2 hardware (servo, ToF, load cell, display) **will not fit** on this
board; the recommended fallback is ESP32-S3 for Phase 2, per spec §3 option C. Recorded, not acted on.

---

## 4. Milestone plan

Ordering follows spec §27. Each milestone must build before the next begins.
"Blocked by decision" marks work that depends on the §5 checkpoint.

| # | Deliverable | Key files | Gate |
|---|---|---|---|
| **M0** | ✅ Repo map, gap analysis, pin feasibility | this file, `pin-map.md`, `IMPLEMENTATION_REPORT.md` | Docs exist |
| **M1** | PlatformIO project boots; camera init; serial logging | `iot/firmware/platformio.ini`, `include/config.h`, `config.example.h`, `src/main.cpp` | `pio run` succeeds |
| **M2** | PIR + HC-SR04 drivers behind `PresenceSensor`/`DistanceSensor` interfaces; fill-percent maths | `sensors.h/.cpp`, `fill_level.h/.cpp` | Native unit tests pass |
| **M3** | Explicit state machine (BOOT→…→ERROR) + `LedService`; hardware-free | `state_machine.h/.cpp`, `led_service.h/.cpp` | Transition tests pass |
| **M4** | `CameraService` abstraction, JPEG capture, buffer release, `MockCameraService` w/ fixture JPEG | `camera_service.h/.cpp`, `mock_camera.h` | `pio run` + mock returns frame |
| **M5** | `NetworkService`: multipart upload, `X-Device-Key`, bin-reading POST | `network_service.h/.cpp` | Builds; contract documented |
| **M6** | Backend: `POST /api/v1/iot/captures`, device auth, privacy preprocessing, classification, bin readings | `src/api/iot.py`, `src/services/*` | **Blocked by decision** |
| **M7** | Bounded retry/backoff, `HTTP_TIMEOUT_MS`, camera-error recovery, ultrasonic timeout handling | across firmware | No unbounded loops |
| **M8** | Wokwi diagram + 9 scenarios; backend pytest suite; firmware build evidence | `iot/simulation/`, `tests/test_api/test_iot.py` | Real captured output |
| **M9** | `architecture.md`, `api-contract.md`, `state-machine.md`, `hardware-setup.md`, final report | `iot/docs/` | Report complete & honest |

Scenarios 1–9 from §19 map onto M8; scenarios 1, 3–6 are exercised as native unit tests over the state
machine (no hardware), scenarios 2, 7, 8 additionally as backend integration tests, and the LED/GPIO
behaviour in Wokwi.

---

## 5. Open decision — backend scope (blocks M6 only)

Because no GreenBinAI backend exists, "integrate with the existing backend" has no referent. Three
readings, materially different in scope:

- **(A) Build the minimal backend slice here.** Create in `P-075` exactly what Phase 1 needs and nothing
  more: `POST /api/v1/iot/captures`, `X-Device-Key` auth, `preprocess_image()` (validate → EXIF strip →
  resize/compress → pHash), a `classification` service routing through the LangGraph agent to a vision
  model, and `POST /api/v1/bins/{code}/readings`. Written so it is the pipeline future web/PWA code reuses
  — satisfying §10's "never bypass preprocessing" by construction. Adds `Pillow` + `python-multipart`.
- **(B) The real backend lives elsewhere.** If a GreenBinAI backend repo exists that was not shared, point
  to it; firmware M1–M5, M7 proceed unchanged in the meantime and M6 targets that codebase instead.
- **(C) Firmware only this phase.** Freeze the HTTP contract in `api-contract.md`, run firmware against a
  local mock server, defer all backend work.

**Recommendation: (A).** It is the only option that satisfies the Definition of Done in §29
("JPEG can reach GreenBin backend", "bin fill reading reaches backend", "backend reuses existing
privacy/classification pipeline") within this repository, and the privacy pipeline is a safety
requirement that should not be deferred behind a mock.

M1–M5 and M7 are unaffected by this choice and can proceed immediately under any reading.

---

## 6. Risks logged at M0

| Risk | Impact | Mitigation |
|---|---|---|
| PlatformIO absent; toolchain ~200 MB | M1 gate `pio run` may be slow/fail offline | Install early, capture real output; report honestly if it fails |
| `.venv` is 3.12, CI is 3.11 | Code that passes locally may fail CI | Keep to 3.11-compatible syntax; ruff already targets py311 |
| Zero spare GPIOs | No room for error or Phase 2 | Documented fallbacks in `pin-map.md` §6 |
| `GPIO12` is the MTDI strapping pin | A pull-up at boot bricks startup on 3.3 V-flash modules | Assigned to `ECHO`, which is guaranteed LOW at reset; rationale in `pin-map.md` §4 |
| No physical hardware available in this environment | Nothing can be hardware-verified | Every claim tagged simulated / unit-tested / backend-tested / **not** physically tested, per §28 |
| OV2640 is not simulated by Wokwi | Camera path unverifiable in simulation | `MockCameraService` returning a fixture JPEG (§18) |
