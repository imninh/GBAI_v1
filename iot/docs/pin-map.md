# GPIO Pin Map — AI Thinker ESP32-CAM (Phase 1)

Status: **proposed, not physically verified**
Board assumed: **AI Thinker ESP32-CAM**, ESP32-S module, OV2640, 4 MB external PSRAM
Camera driver model: `CAMERA_MODEL_AI_THINKER`

Per spec §3, no pin was copied from prior project documentation. Every assignment below is derived
from the camera driver's own pin table plus the ESP32 strapping-pin rules, and every choice states
**why**.

> ⚠️ **Verify before wiring.** These assignments are derived from the AI Thinker reference design and
> the `esp32-camera` driver. They have **not** been checked against a physical board or a schematic in
> hand. §7 lists the exact checks to perform first.

---

## 1. Pins consumed by the OV2640 camera

From `camera_pins.h` for `CAMERA_MODEL_AI_THINKER`:

| Camera signal | GPIO | | Camera signal | GPIO |
|---|---|---|---|---|
| PWDN  | 32 | | Y7 (D5) | 39 *(input-only)* |
| RESET | –  *(not connected)* | | Y6 (D4) | 36 *(input-only)* |
| XCLK  | 0  *(also boot strap)* | | Y5 (D3) | 21 |
| SIOD (SCCB SDA) | 26 | | Y4 (D2) | 19 |
| SIOC (SCCB SCL) | 27 | | Y3 (D1) | 18 |
| Y9 (D7) | 35 *(input-only)* | | Y2 (D0) | 5 *(also boot strap)* |
| Y8 (D6) | 34 *(input-only)* | | VSYNC | 25 |
| | | | HREF | 23 |
| | | | PCLK | 22 |

**Occupied by camera (15 GPIOs):** `0, 5, 18, 19, 21, 22, 23, 25, 26, 27, 32, 34, 35, 36, 39`

`RESET` is tied to the module's own reset, so no GPIO is spent on it.

## 2. Pins otherwise reserved on this board

| GPIO | Reserved for | Can Phase 1 reclaim it? |
|---|---|---|
| 1 (U0TXD) | Serial log + flashing | **No** — §20 requires serial logging |
| 3 (U0RXD) | Serial console + flashing | **No** — same |
| 16 | **PSRAM chip-select** on ESP32-CAM | **No** — PSRAM is needed for JPEG framebuffers; freeing 16 means disabling PSRAM and dropping to small frame sizes |
| 4 | Bright white **flash LED** (via driver transistor); also SD `D1` | Electrically free once SD is unused, but any use lights the flash LED. Kept in reserve for future night capture |
| 33 | Onboard **red status LED** (active LOW) | Usable in software, but **not broken out to a header** — no external wiring possible |
| 2 | SD `D0`; **boot strapping pin** (must be LOW/floating for download mode) | Free if SD unused, but strapping-encumbered — held as last-resort spare |
| 14, 15 | SD `CLK`, `CMD` (1-bit and 4-bit modes) | **Yes** — SD unused |
| 12, 13 | SD `D2`, `D3` (4-bit mode only) | **Yes** — SD unused |

**Phase 1 assumption (permitted by spec §3 item 4): microSD is NOT used.** This is what makes the
single-board design viable. The cost is that SD logging is permanently unavailable in Phase 1.

## 3. Availability arithmetic

```
ESP32 GPIOs usable on this board ....... 0,1,2,3,4,5,12,13,14,15,16,18,19,21,22,23,25,26,27,32,33,34,35,36,39
  − camera (15) ........................ 1,2,3,4,12,13,14,15,16,33
  − UART logging + flashing (2) ........ 2,4,12,13,14,15,16,33
  − PSRAM CS (1) ....................... 2,4,12,13,14,15,33
  − flash LED (1), not-broken-out (1) .. 2,12,13,14,15
  − strapping-encumbered GPIO2 ......... 12,13,14,15      ← 4 clean pins

Phase 1 signal count: PIR, TRIG, ECHO, WS2812 DIN = 4
```

**4 available, 4 required → feasible, with zero margin.**

## 4. Proposed assignment

| Signal | GPIO | Dir | Why this pin |
|---|---|---|---|
| `PIR_PIN` — HC-SR501 `OUT` | **13** | input | GPIO13 (MTCK) carries **no boot-critical strapping role**, making it the only safe home for a signal that may be HIGH at power-on. The HC-SR501 self-calibrates for 30–60 s after power-up and can assert `OUT` spuriously during that window; on a strapping pin that would change boot behaviour. |
| `ULTRASONIC_TRIG_PIN` | **14** | output | GPIO14 (MTMS) has no boot-critical strapping role. The line is driven only by us, and HC-SR04's `TRIG` is a high-impedance input on the sensor side, so nothing back-drives the pin at reset. |
| `ULTRASONIC_ECHO_PIN` | **12** | input **via divider** | GPIO12 (MTDI) **must be LOW at reset** — a HIGH selects 1.8 V `VDD_SDIO` and a 3.3 V-flash module then fails to boot. `ECHO` idles LOW and only pulses after a trigger, which cannot occur before firmware runs, so the line is *guaranteed* LOW at reset. That guarantee is stronger than "probably floating", which is why ECHO — not the LED — gets the dangerous pin. **Requires a level shifter, see §5.1.** |
| `LED_PIN` — WS2812 `DIN` | **15** | output | GPIO15 (MTDO) strapping only affects *boot-log verbosity*: LOW at boot silences the ROM messages on U0TXD. Worst case is cosmetic, never a boot failure. WS2812 `DIN` is high-impedance and GPIO15's internal pull-up is enabled at reset, so the boot log is preserved anyway. |

**Why not swap the LED onto 12 and ECHO onto 15?** Some WS2812 breakout boards fit a pull-up on `DIN`.
On GPIO12 that pull-up would hold MTDI high at reset and prevent the board from booting — a failure
mode that is hard to diagnose and easy to avoid. ECHO's idle-low behaviour has no such variant risk.

### Resulting map

```
GPIO 12 ── HC-SR04 ECHO   (through 1k/2k divider — NOT direct)
GPIO 13 ── HC-SR501 OUT   (direct, 3.3 V logic)
GPIO 14 ── HC-SR04 TRIG   (direct)
GPIO 15 ── WS2812 DIN     (pixel powered from 3.3 V)
```

## 5. Voltage compatibility — required by spec §3

### 5.1 HC-SR04 `ECHO` is 5 V. ESP32 GPIOs are not 5 V tolerant.

The ESP32 absolute-maximum input is roughly `VDD + 0.3 V ≈ 3.6 V`. The HC-SR04 needs a 5 V supply to
operate reliably and drives `ECHO` as a **push-pull 5 V** output. **Connecting `ECHO` directly to any
ESP32 GPIO risks permanent pin damage or latch-up.** A direct connection is not acceptable.

**Chosen mitigation — resistive divider:**

```
HC-SR04 ECHO ──┬── R1 = 1 kΩ ──┬── GPIO 12
               │               │
               │             R2 = 2 kΩ
               │               │
              GND ────────────┴── GND      (common ground required)

V_gpio = 5.0 × R2/(R1+R2) = 5.0 × 2/3 = 3.33 V   ✅ within spec
```

If 2 kΩ is unavailable, `1 kΩ / 1.8 kΩ` gives 3.21 V, also fine. Avoid values above ~10 kΩ total: the
divider's output impedance combined with pin capacitance slows the edge, and `ECHO` pulse-width timing
is what the distance measurement depends on.

**Preferred alternative for a student build:** use an **HC-SR04P** or **RCWL-1601**, which operate from
3.3 V and output 3.3 V logic — no divider, no risk, same code, roughly the same price. This is the
recommended part.

`TRIG` in the other direction is safe unshifted: 3.3 V comfortably exceeds the HC-SR04's ~2.0 V input
threshold. A minority of clone modules are marginal here; if triggering proves unreliable, a level
shifter or the -P variant resolves it.

### 5.2 HC-SR501 `OUT` — safe direct

The HC-SR501 regulates internally and its `OUT` stage swings **3.3 V** even when the module is powered
from 5 V. Direct connection to GPIO13 is correct. Set the module's jumper to **repeat/H mode** and turn
the on-board delay potentiometer to minimum, so the output follows motion rather than latching.

### 5.3 WS2812 logic level — the quiet failure

A WS2812/WS2812B requires `DIN` high ≥ `0.7 × VDD`. Powered at 5 V that is **3.5 V**, which a 3.3 V ESP32
GPIO **cannot** guarantee. This often "works on the bench" and then fails intermittently on another
board or at temperature — precisely the kind of silent unreliability to design out.

**Chosen mitigation:** power the single status pixel from **3.3 V**, dropping the threshold to 2.31 V,
which 3.3 V logic satisfies with margin. One pixel at capped brightness draws well under the AI Thinker
regulator's budget.

Alternatives if a 5 V pixel is mandatory: a 74AHCT125 level shifter (correct fix), or a sacrificial
first pixel, or dropping the strip supply to ~4.3 V through a series diode.

### 5.4 Power — the most common ESP32-CAM failure

The ESP32-CAM needs a solid **5 V supply capable of ≥ 2 A peaks**. Camera initialisation coinciding with
Wi-Fi TX causes brownout resets that masquerade as firmware bugs. Do **not** power the board from a
USB-TTL adapter's 5 V pin. Add a 470–1000 µF electrolytic across the 5 V rail near the module. Firmware
caps LED brightness (`LED_MAX_BRIGHTNESS`) so the pixel cannot compete with the Wi-Fi radio for current.

## 6. Conflict statement and fallback options (spec §3)

**There is no conflict for Phase 1** — the four required signals fit on the four clean GPIOs. But the
margin is zero, and that must be stated plainly rather than presented as comfortable headroom:

- Remaining spares are `GPIO2` (strapping-encumbered), `GPIO4` (flash LED), `GPIO33` (not broken out).
- Adding **any** Phase 2 peripheral (servo, ToF, load cell, display, buzzer) requires giving up serial
  logging, PSRAM, or the flash LED.
- Re-enabling microSD in a later phase reclaims 12/13/14/15 and **breaks this pin map entirely**.

Fallbacks, in the order recommended:

| | Option | When to take it |
|---|---|---|
| **A** | Keep SD disabled (**current choice**) | Phase 1. Sufficient, single board, lowest cost — matches the spec's stated preference |
| **C** | Move to **ESP32-S3** (e.g. ESP32-S3-CAM / XIAO ESP32S3 Sense) | **Recommended for Phase 2.** More GPIOs, more PSRAM, native USB. Because the firmware keeps hardware behind `PresenceSensor` / `DistanceSensor` / `CameraService` / `LedService` / `NetworkService` interfaces (§18), this port touches drivers only, not state-machine logic |
| **B** | Second cheap MCU for sensor I/O | Only if the ESP32-CAM must be kept *and* more I/O is needed. Adds an inter-MCU link and its own failure modes — least attractive |

## 7. Verification checklist before powering hardware

Nothing below has been performed — no physical board exists in this environment.

1. Confirm the module is genuinely AI Thinker (`ESP32-S` + OV2640 + PSRAM), not a look-alike with a
   different camera pinout.
2. Meter `GPIO12` to ground **before** first boot with the sensor wired: it must not be pulled high.
   If the board boots without the divider attached but not with it, GPIO12 is the culprit.
3. Confirm the board actually has PSRAM (`ESP.getPsramSize()` at boot) — a few clones are advertised
   with PSRAM and ship without it.
4. Verify the HC-SR04 variant. A `-P` suffix (or "3.3 V" silkscreen) means the divider is unnecessary.
5. Measure the divider output with `ECHO` asserted; it must read ≤ 3.4 V.
6. Confirm common ground between the ESP32-CAM, both sensors and the pixel.
7. Confirm the boot log appears on serial at 115200 — if silent, check GPIO15 wiring (§4).

## 8. Firmware constants

These become `config.h` values in M1 — never magic numbers in application code (spec §6, §17):

```cpp
#define PIR_PIN               13
#define ULTRASONIC_TRIG_PIN   14
#define ULTRASONIC_ECHO_PIN   12
#define LED_PIN               15
#define LED_COUNT              1
#define LED_MAX_BRIGHTNESS    64   // cap current draw; protects the 3.3 V rail
```
