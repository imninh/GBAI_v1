# Simulation scenarios

> **IoT Checkpoint 1** (servo sorter, OLED, mock AI, hardware test menu) is
> documented separately in [iot-checkpoint-1.md](../../docs/iot-checkpoint-1.md).
> `checkpoint1-flow.yaml` and `checkpoint1-selftest.yaml` in this directory drive
> it headlessly — they need a `WOKWI_CLI_TOKEN` and **have not been executed
> yet**, so treat their step names as unverified until someone runs them.

Two layers of testing cover the nine scenarios in the specification (§19).

| Layer | What it proves | How to run |
|---|---|---|
| **Native unit tests** | State-machine logic, thresholds, retry bounds, LED mapping — with fake sensors, camera and network | `cd iot/firmware && pio test -e native` |
| **Wokwi simulation** | The same firmware binary driving real GPIO timing, a real WS2812 waveform and real sensor parts | Open `iot/simulation/diagram.json` in the Wokwi VS Code extension |

The native tests are the authority for logic — they are deterministic, fast and
run in CI. Wokwi adds confidence that the drivers and pin assignment behave, which
unit tests cannot show.

## Scenario coverage

| # | Scenario | Native test | Wokwi steps |
|---|---|---|---|
| 1 | Person walks past | `test_scenario1_false_trigger_captures_nothing` | Set HC-SR04 to 50 cm, trigger PIR, leave distance at 50 cm. Expect `[EVENT] false_trigger`, no `[CAMERA]` line |
| 2 | Valid waste event | `test_scenario2_valid_event_captures_and_uploads` | Set 50 cm, trigger PIR, then set 44 cm within 1 s. Expect `[EVENT] waste_confirmed` then `[CAMERA] jpeg_bytes=…` |
| 3 | Successful classification | `test_scenario3_ok_shows_green_and_returns_idle` | Requires a reachable backend returning `status=ok`. Expect green LED ~3 s |
| 4 | Low confidence | `test_scenario4_warning_is_not_presented_as_success`, `..._refused_...` | Backend returns `status=warning`. Expect red, 2 fast blinks |
| 5 | Hazardous waste | `test_scenario5_hazard_pattern` | Backend returns `status=hazard`. Expect red blinking ~5 s |
| 6 | Backend timeout | `test_scenario6_timeout_retries_bounded_then_recovers` | Leave the backend unreachable — the default in Wokwi. Expect 3 upload attempts with growing gaps, orange LED, return to IDLE |
| 7 | Bin full | `test_scenario7_bin_full_sends_reading_and_goes_solid` | Set HC-SR04 to 12 cm (96 %). Expect `[BIN] state_changed full=1` and **solid** red |
| 8 | Bin emptied | `test_scenario8_bin_emptied_sends_changed_reading` | Then set 55 cm (10 %). Expect one further reading and the solid red clearing |
| 9 | Invalid sensor reading | `test_scenario9_invalid_reading_produces_no_fill_value`, `test_invalid_baseline_blocks_capture` | Set HC-SR04 beyond 400 cm. Expect `[HC-SR04] invalid reading` and no fill value |

## Preparing a Wokwi run

```bash
cd iot/firmware
pio run -e wokwi                  # mock camera + Wokwi network/timing settings
```

The `wokwi` environment already selects `Wokwi-GUEST`, points the backend at
`http://host.wokwi.internal:8123`, shortens `PIR_WAIT_MS` to 1 second, and checks
fill level every 5 seconds. Start the backend with:

```bash
cd /home/TranPhuNghia_20233871/P-075
IOT_DEVICE_KEYS="GBIN-001:sim-test-key" \
VISION_PROVIDER=stub STUB_VISION_LABEL=plastic STUB_VISION_CONFIDENCE=0.94 \
  .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8123
```

Enable Wokwi's Private IoT Gateway so `host.wokwi.internal` reaches that local
server. Without the gateway, the hardware simulation still exercises the bounded
network-failure path.

## Limitations of the Wokwi layer

These are real gaps, not oversights:

- **The OV2640 is not simulated.** `MockCameraService` returns a fixture JPEG, so
  the capture *path* is exercised but the camera is not. Only physical hardware
  can validate the sensor, framebuffer and PSRAM behaviour.
- **There is no ESP32-CAM part in Wokwi.** The diagram uses an ESP32 DevKit with
  the identical GPIO assignment. It therefore does **not** validate the pin map
  against the real board's camera wiring — that is what
  [pin-map.md](../../docs/pin-map.md) §7 is for.
- **Outbound HTTP needs Wokwi's network gateway.** Without it every upload fails,
  which exercises scenario 6 but not 3, 4, 5 or 7's delivery leg.
- **Wokwi cannot validate real voltage levels.** The diagram includes the required
  1 kΩ/2 kΩ `ECHO` divider, but only a meter on physical hardware can prove it is
  wired correctly and keeping GPIO12 below 3.4 V.
