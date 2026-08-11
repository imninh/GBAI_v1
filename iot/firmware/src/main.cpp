// GreenBinAI IoT — Phase 1 entry point.
//
// This file does one job: build the concrete drivers and hand them to the state
// machine. All behaviour lives in src/core/ (spec §26: never put all firmware
// code into main.cpp).
#include <Arduino.h>

#include "config.h"
#include "core/logging.h"
#include "core/state_machine.h"
#include "hw/led_service.h"
#include "hw/network_service.h"
#include "hw/sensors.h"

#ifdef GREENBIN_USE_MOCK_CAMERA
#include "hw/mock_camera.h"
#else
#include "hw/camera_service.h"
#endif

using namespace greenbin;

static Hcsr501PresenceSensor g_presence(PIN_PIR);
static Hcsr04DistanceSensor g_distance(PIN_ULTRASONIC_TRIG,
                                       PIN_ULTRASONIC_ECHO,
                                       ULTRASONIC_MIN_CM,
                                       ULTRASONIC_MAX_CM,
                                       ULTRASONIC_TIMEOUT_US,
                                       ULTRASONIC_SAMPLES);

#ifdef GREENBIN_USE_MOCK_CAMERA
static MockCameraService g_camera;
#else
static Ov2640CameraService g_camera(CAMERA_MAX_INIT_ATTEMPTS);
#endif

static Ws2812LedService g_led(PIN_LED, LED_COUNT, LED_MAX_BRIGHTNESS);

static EspNetworkService g_network(WIFI_SSID,
                                   WIFI_PASSWORD,
                                   BACKEND_BASE_URL,
                                   DEVICE_ID,
                                   BIN_CODE,
                                   DEVICE_KEY,
                                   HTTP_TIMEOUT_MS);

// Every value comes from config.h; none is written twice.
static StateMachineConfig buildConfig() {
    StateMachineConfig cfg;
    cfg.pirWaitMs = PIR_WAIT_MS;
    cfg.objectDeltaCm = OBJECT_DELTA_CM;
    cfg.pirRearmMs = PIR_REARM_MS;
    cfg.fillIntervalMs = FILL_INTERVAL_MS;
    cfg.emptyDistanceCm = EMPTY_DISTANCE_CM;
    cfg.fullDistanceCm = FULL_DISTANCE_CM;
    cfg.fullThresholdPercent = FULL_THRESHOLD_PERCENT;
    cfg.fullClearPercent = FULL_CLEAR_PERCENT;
    cfg.maxRetry = MAX_RETRY;
    cfg.retryDelayMs = RETRY_DELAY_MS;
    cfg.retryMaxDelayMs = RETRY_MAX_DELAY_MS;
    cfg.wifiConnectTimeoutMs = WIFI_CONNECT_TIMEOUT_MS;
    cfg.wifiRetryDelayMs = WIFI_RETRY_DELAY_MS;
    cfg.errorDisplayMs = LED_NET_ERROR_MS;
    cfg.resultDisplayMs = LED_OK_MS;
    return cfg;
}

static StateMachine g_machine(g_presence, g_distance, g_camera, g_network, g_led, buildConfig());

void setup() {
    Serial.begin(115200);
    delay(200);  // let the USB-serial bridge settle before the first log line

    GB_LOG("BOOT", "firmware=%s device=%s bin=%s", FIRMWARE_VERSION, DEVICE_ID, BIN_CODE);
    GB_LOG("BOOT", "psram=%d heap=%u", psramFound() ? 1 : 0,
           static_cast<unsigned>(ESP.getFreeHeap()));

    g_presence.begin();
    g_distance.begin();
    g_led.begin();

    // The HC-SR501 self-calibrates for 30–60 s after power-up and reports
    // spurious motion during that window. Warn rather than silently produce
    // false events (see iot/docs/hardware-setup.md).
    GB_LOG_PLAIN("PIR", "settling; ignore triggers for the first ~60s");

    g_machine.begin(millis());
}

void loop() {
    g_machine.tick(millis());
    // 10 ms is fast enough for a PIR edge and slow enough to leave the radio
    // and the LED bus alone.
    delay(10);
}
