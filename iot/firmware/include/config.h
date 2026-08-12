// GreenBinAI IoT — Phase 1 configuration.
//
// Every tunable lives here. No magic numbers in application code (spec §6, §17).
//
// Secrets are NOT in this file. Copy `secrets.example.h` to `secrets.h` and fill
// it in; `secrets.h` is gitignored. If it is absent the placeholders below keep
// the firmware compiling (so `pio run` works on a fresh clone) but it will not
// connect to anything.
#pragma once

#if __has_include("secrets.h")
#include "secrets.h"
#endif

// ─── Identity & backend ──────────────────────────────────────────────────────
#ifndef DEVICE_ID
#define DEVICE_ID "GBIN-001"
#endif
#ifndef BIN_CODE
#define BIN_CODE "BIN-001"
#endif
#ifndef BACKEND_BASE_URL
#define BACKEND_BASE_URL "http://192.168.1.100:8000"
#endif
#ifndef DEVICE_KEY
#define DEVICE_KEY "CHANGEME-device-key"
#endif

// ─── Wi-Fi ───────────────────────────────────────────────────────────────────
#ifndef WIFI_SSID
#define WIFI_SSID "CHANGEME-ssid"
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "CHANGEME-password"
#endif

// ─── Pin map ─────────────────────────────────────────────────────────────────
// Derived in iot/docs/pin-map.md. These four are the ONLY GPIOs left once the
// OV2640 (15 pins), UART logging (2) and PSRAM chip-select (GPIO16) are spoken
// for, and they are available only because microSD is disabled. Do not change
// one without re-reading pin-map.md §4 — GPIO12 in particular is the MTDI
// strapping pin and must never be pulled high at reset.
#define PIN_PIR 13              // HC-SR501 OUT — no strapping role
#define PIN_ULTRASONIC_TRIG 14  // HC-SR04 TRIG — output only
#define PIN_ULTRASONIC_ECHO 12  // HC-SR04 ECHO — via 1k/2k divider, idles LOW
#define PIN_LED 15              // WS2812 DIN — pixel powered from 3.3 V

// Simulation-only peripherals. On the ESP32 DevKit-C used in Wokwi these pins
// are free; on the real AI-Thinker ESP32-CAM they are camera data lines
// (GPIO18=Y3, GPIO21=Y4, GPIO22=PCLK), so the `esp32cam` build must NOT drive
// them. That build compiles without GREENBIN_HAS_SORTER / GREENBIN_HAS_DISPLAY
// and injects the null devices instead — see pin-map.md §4 and main.cpp.
#define PIN_SERVO 18      // sorter servo signal
#define PIN_OLED_SDA 21   // SSD1306 I2C data
#define PIN_OLED_SCL 22   // SSD1306 I2C clock

#define LED_COUNT 1
#define LED_MAX_BRIGHTNESS 64  // caps current so the pixel cannot brown out Wi-Fi TX

// ─── Sorter servo (Checkpoint 1 §9) ──────────────────────────────────────────
// Simulation angles, not a mechanical calibration. All four are distinct on
// purpose: HOME is the centred, closed position and the three outlets sit either
// side of it, so "did the flap return HOME?" is observable rather than inferred.
// Recalibrating the real chute means changing these four numbers and nothing else.
#define SERVO_HOME_ANGLE 90
#define SERVO_PLASTIC_ANGLE 30
#define SERVO_PAPER_ANGLE 120
#define SERVO_METAL_ANGLE 160

// SG90-class pulse envelope. 500–2500 µs is the usual 0–180° range; a narrower
// pulse than the servo supports would silently clip the travel.
#define SERVO_MIN_PULSE_US 500
#define SERVO_MAX_PULSE_US 2500
#define SERVO_PWM_FREQ_HZ 50
#define SERVO_PWM_CHANNEL 4  // LEDC channel; the WS2812 uses RMT, so no clash
// Time allowed for the horn to physically reach the commanded angle. A cheap
// servo sweeps ~60°/0.1 s unloaded, so 400 ms covers the widest move here.
#define SERVO_SETTLE_MS 400

// ─── OLED (Checkpoint 1 §10) ─────────────────────────────────────────────────
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_I2C_ADDRESS 0x3C
#define OLED_I2C_FREQ_HZ 400000UL

// ─── Waste-event detection (spec §6) ─────────────────────────────────────────
#ifndef PIR_WAIT_MS
#define PIR_WAIT_MS 2500UL      // settle time between baseline and confirm reading
#endif
#define OBJECT_DELTA_CM 4.0f    // distance must DROP by at least this to confirm
#define PIR_REARM_MS 5000UL     // ignore PIR for this long after an event completes

// ─── Fill level (spec §13) ───────────────────────────────────────────────────
// Field calibration. The Wokwi build overrides both (50/5) so that the HC-SR04
// slider range maps cleanly onto 0–100% in simulation.
#ifndef EMPTY_DISTANCE_CM
#define EMPTY_DISTANCE_CM 60.0f  // sensor-to-floor with bin empty
#endif
#ifndef FULL_DISTANCE_CM
#define FULL_DISTANCE_CM 10.0f  // sensor-to-waste with bin full
#endif
#ifndef FILL_INTERVAL_MS
#define FILL_INTERVAL_MS 300000UL  // 5 min in the field; override for simulation
#endif

// ─── Bin-full state (spec §14) ───────────────────────────────────────────────
#define FULL_THRESHOLD_PERCENT 80.0f
// Hysteresis: once full, stay full until fill drops below this. Prevents a bin
// hovering at 80% from emitting an endless normal/full/normal event stream.
#define FULL_CLEAR_PERCENT 75.0f

// ─── Fill display buckets (Checkpoint 1 §12) ─────────────────────────────────
// What the user sees, as opposed to FULL_THRESHOLD_PERCENT above, which decides
// when the operations backend is told to schedule a collection.
#define FILL_MEDIUM_PERCENT 60.0f
#define FILL_NEAR_FULL_PERCENT 80.0f
#define FILL_FULL_PERCENT 95.0f

// ─── Sorting decision (Checkpoint 1 §16, §24) ────────────────────────────────
// Below this confidence the item is not sorted, whatever label came back. The
// backend also filters, but the device must be able to refuse on its own.
#define MIN_SORT_CONFIDENCE 0.60f

// ─── Ultrasonic sensor limits ────────────────────────────────────────────────
#define ULTRASONIC_MIN_CM 2.0f
#define ULTRASONIC_MAX_CM 400.0f
#define ULTRASONIC_TIMEOUT_US 30000UL  // ~5 m round trip; beyond this = no echo
// Median filter width; must be odd. Each extra sample costs ~60 ms of blocking
// settle time, so 3 is the compromise between noise rejection and loop latency.
#define ULTRASONIC_SAMPLES 3

// ─── Network (spec §15) ──────────────────────────────────────────────────────
#define HTTP_TIMEOUT_MS 10000UL
#define MAX_RETRY 3
#define RETRY_DELAY_MS 2000UL
#define RETRY_MAX_DELAY_MS 30000UL  // ceiling for exponential backoff
#define WIFI_CONNECT_TIMEOUT_MS 20000UL
#define WIFI_RETRY_DELAY_MS 15000UL

// ─── Camera (spec §7) ────────────────────────────────────────────────────────
#define CAMERA_JPEG_QUALITY 12   // 10–63; lower is better quality, larger file
#define CAMERA_FRAMESIZE FRAMESIZE_SVGA  // 800x600 — enough for classification
#define CAMERA_MAX_INIT_ATTEMPTS 3

// ─── Host webcam (simulation only) ───────────────────────────────────────────
// Used by the wokwi_camera build, where the image comes from the PC's webcam
// instead of an OV2640. See iot/simulation/webcam_service.py.
#ifndef HOST_CAMERA_URL
#define HOST_CAMERA_URL "http://host.wokwi.internal:8124/frame.jpg"
#endif
// The Wokwi DevKit-C has no PSRAM, so the frame and the multipart copy of it
// both live in ~200 KB of DRAM. 48 KB leaves comfortable headroom; the webcam
// service refuses to serve anything larger.
#ifndef HOST_CAMERA_MAX_BYTES
#define HOST_CAMERA_MAX_BYTES (48 * 1024)
#endif

// ─── LED timings (spec §12) ──────────────────────────────────────────────────
#define LED_OK_MS 3000UL
#define LED_WARNING_BLINKS 2
#define LED_WARNING_PERIOD_MS 250UL
#define LED_HAZARD_MS 5000UL
#define LED_HAZARD_PERIOD_MS 400UL
#define LED_NET_ERROR_MS 2000UL

// ─── API paths (spec §8, §14) ────────────────────────────────────────────────
#define API_CAPTURES_PATH "/api/v1/iot/captures"
#define API_READINGS_PATH "/api/v1/bins/" BIN_CODE "/readings"
#define API_HEARTBEAT_PATH "/api/v1/iot/heartbeat"

// ─── Heartbeat (Checkpoint 1 §21) ────────────────────────────────────────────
// Only sent while the device is IDLE, so a backend that is slow or absent can
// never stall a sorting transaction. The timeout is deliberately much shorter
// than HTTP_TIMEOUT_MS for the same reason.
#define HEARTBEAT_INTERVAL_MS 60000UL
#define HEARTBEAT_TIMEOUT_MS 3000UL
