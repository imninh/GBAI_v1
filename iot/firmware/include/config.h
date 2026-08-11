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

#define LED_COUNT 1
#define LED_MAX_BRIGHTNESS 64  // caps current so the pixel cannot brown out Wi-Fi TX

// ─── Waste-event detection (spec §6) ─────────────────────────────────────────
#ifndef PIR_WAIT_MS
#define PIR_WAIT_MS 2500UL      // settle time between baseline and confirm reading
#endif
#define OBJECT_DELTA_CM 4.0f    // distance must DROP by at least this to confirm
#define PIR_REARM_MS 5000UL     // ignore PIR for this long after an event completes

// ─── Fill level (spec §13) ───────────────────────────────────────────────────
#define EMPTY_DISTANCE_CM 60.0f  // sensor-to-floor with bin empty
#define FULL_DISTANCE_CM 10.0f   // sensor-to-waste with bin full
#ifndef FILL_INTERVAL_MS
#define FILL_INTERVAL_MS 300000UL  // 5 min in the field; override for simulation
#endif

// ─── Bin-full state (spec §14) ───────────────────────────────────────────────
#define FULL_THRESHOLD_PERCENT 80.0f
// Hysteresis: once full, stay full until fill drops below this. Prevents a bin
// hovering at 80% from emitting an endless normal/full/normal event stream.
#define FULL_CLEAR_PERCENT 75.0f

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
