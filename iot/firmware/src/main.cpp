// GreenBinAI IoT — entry point.
//
// This file does one job: build the concrete drivers and hand them to the state
// machine. All behaviour lives in src/core/ (spec §26: never put all firmware
// code into main.cpp).
//
// Which drivers get built is a build-flag decision, not a runtime one:
//
//   GREENBIN_USE_MOCK_CAMERA  fixture JPEG instead of the OV2640
//   GREENBIN_HOST_CAMERA      JPEG fetched from the PC's webcam over HTTP
//   GREENBIN_MOCK_BACKEND     offline mock classifier instead of HTTP
//   GREENBIN_HAS_SORTER       servo present (Wokwi only — see config.h)
//   GREENBIN_HAS_DISPLAY      SSD1306 present (Wokwi only)
//   GREENBIN_ENABLE_WIFI      Wi-Fi + backend heartbeat (P1)
//   GREENBIN_TEST_CONSOLE     Serial hardware test menu
#include <Arduino.h>

#include "config.h"
#include "core/logging.h"
#include "core/null_devices.h"
#include "core/state_machine.h"
#include "hw/led_service.h"
#include "hw/sensors.h"

#if defined(GREENBIN_HOST_CAMERA)
#include "hw/host_camera.h"
#elif defined(GREENBIN_USE_MOCK_CAMERA)
#include "hw/mock_camera.h"
#else
#include "hw/camera_service.h"
#endif

#ifdef GREENBIN_MOCK_BACKEND
#include "hw/mock_backend.h"
#else
#include "hw/network_service.h"
#endif

#ifdef GREENBIN_HAS_SORTER
#include "hw/servo_sorter.h"
#endif

#ifdef GREENBIN_HAS_DISPLAY
#include "hw/oled_display.h"
#endif

#ifdef GREENBIN_ENABLE_WIFI
#include "hw/wifi_heartbeat.h"
#endif

#ifdef GREENBIN_TEST_CONSOLE
#include "hw/test_console.h"
#endif

using namespace greenbin;

// ─── Sensors ─────────────────────────────────────────────────────────────────

static Hcsr501PresenceSensor g_presence(PIN_PIR);
static Hcsr04DistanceSensor g_distance(PIN_ULTRASONIC_TRIG,
                                       PIN_ULTRASONIC_ECHO,
                                       ULTRASONIC_MIN_CM,
                                       ULTRASONIC_MAX_CM,
                                       ULTRASONIC_TIMEOUT_US,
                                       ULTRASONIC_SAMPLES);

// ─── Camera ──────────────────────────────────────────────────────────────────

#if defined(GREENBIN_HOST_CAMERA)
static HostCameraService g_camera(HOST_CAMERA_URL, HOST_CAMERA_MAX_BYTES, HTTP_TIMEOUT_MS);
#elif defined(GREENBIN_USE_MOCK_CAMERA)
static MockCameraService g_camera;
#else
static Ov2640CameraService g_camera(CAMERA_MAX_INIT_ATTEMPTS);
#endif

// ─── Backend ─────────────────────────────────────────────────────────────────

#ifdef GREENBIN_MOCK_BACKEND
static MockBackendService g_backend;
#else
static EspNetworkService g_backend(WIFI_SSID,
                                   WIFI_PASSWORD,
                                   BACKEND_BASE_URL,
                                   DEVICE_ID,
                                   BIN_CODE,
                                   DEVICE_KEY,
                                   HTTP_TIMEOUT_MS);
#endif

static Ws2812LedService g_led(PIN_LED, LED_COUNT, LED_MAX_BRIGHTNESS);

// ─── Sorter and display ──────────────────────────────────────────────────────
// The real ESP32-CAM has no free GPIO for either (pin-map.md §4), so that build
// gets no-ops. The flow is identical; the calls simply go nowhere.

#ifdef GREENBIN_HAS_SORTER
static const ServoSorter::Angles kSorterAngles = {SERVO_HOME_ANGLE, SERVO_PLASTIC_ANGLE,
                                                  SERVO_PAPER_ANGLE, SERVO_METAL_ANGLE};
static ServoSorter g_sorter(PIN_SERVO,
                            kSorterAngles,
                            SERVO_MIN_PULSE_US,
                            SERVO_MAX_PULSE_US,
                            SERVO_SETTLE_MS,
                            SERVO_PWM_CHANNEL);
#else
static NullSorter g_sorter;
#endif

#ifdef GREENBIN_HAS_DISPLAY
static OledDisplay g_display(PIN_OLED_SDA, PIN_OLED_SCL, OLED_I2C_ADDRESS, OLED_I2C_FREQ_HZ);
#else
static NullDisplay g_display;
#endif

#ifdef GREENBIN_ENABLE_WIFI
static WifiHeartbeat g_heartbeat(WIFI_SSID,
                                 WIFI_PASSWORD,
                                 BACKEND_BASE_URL,
                                 DEVICE_ID,
                                 DEVICE_KEY,
                                 HEARTBEAT_TIMEOUT_MS,
                                 HEARTBEAT_INTERVAL_MS);
#endif

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
    cfg.minSortConfidence = MIN_SORT_CONFIDENCE;
    cfg.fillThresholds =
        FillThresholds(FILL_MEDIUM_PERCENT, FILL_NEAR_FULL_PERCENT, FILL_FULL_PERCENT);
    return cfg;
}

static StateMachine g_machine(g_presence,
                              g_distance,
                              g_camera,
                              g_backend,
                              g_led,
                              g_sorter,
                              g_display,
                              buildConfig());

#ifdef GREENBIN_TEST_CONSOLE
static TestConsole::Wiring buildConsoleWiring() {
    TestConsole::Wiring wiring;
    wiring.machine = &g_machine;
    wiring.presence = &g_presence;
    wiring.distance = &g_distance;
    wiring.led = &g_led;
    // Whatever camera this build has, the self test uses it.
    wiring.camera = &g_camera;
#ifdef GREENBIN_USE_MOCK_CAMERA
    // Only the mock can be told to fail on demand (console command `c`).
    wiring.mockCamera = &g_camera;
#endif
#ifdef GREENBIN_MOCK_BACKEND
    wiring.backend = &g_backend;
#endif
#ifdef GREENBIN_HAS_SORTER
    wiring.sorter = &g_sorter;
#endif
#ifdef GREENBIN_HAS_DISPLAY
    wiring.display = &g_display;
#endif
#ifdef GREENBIN_ENABLE_WIFI
    wiring.heartbeat = &g_heartbeat;
#endif
    wiring.emptyDistanceCm = EMPTY_DISTANCE_CM;
    wiring.fullDistanceCm = FULL_DISTANCE_CM;
    wiring.fillThresholds =
        FillThresholds(FILL_MEDIUM_PERCENT, FILL_NEAR_FULL_PERCENT, FILL_FULL_PERCENT);
    return wiring;
}

static TestConsole g_console(buildConsoleWiring());
#endif

void setup() {
    Serial.begin(115200);
    delay(200);  // let the USB-serial bridge settle before the first log line

    GB_LOG("BOOT", "firmware=%s device=%s bin=%s", FIRMWARE_VERSION, DEVICE_ID, BIN_CODE);
    GB_LOG("BOOT", "psram=%d heap=%u", psramFound() ? 1 : 0,
           static_cast<unsigned>(ESP.getFreeHeap()));

    g_presence.begin();
    g_distance.begin();
    g_led.begin();

#ifdef GREENBIN_HAS_DISPLAY
    g_display.begin();
#endif
#ifdef GREENBIN_HAS_SORTER
    g_sorter.begin();  // parks the flap at HOME before anything else runs
#endif
#ifdef GREENBIN_ENABLE_WIFI
    g_heartbeat.begin();
#endif

    // The HC-SR501 self-calibrates for 30–60 s after power-up and reports
    // spurious motion during that window. Warn rather than silently produce
    // false events (see iot/docs/hardware-setup.md).
    GB_LOG_PLAIN("PIR", "settling; ignore triggers for the first ~60s");

    g_machine.begin(millis());

#ifdef GREENBIN_TEST_CONSOLE
    g_console.begin();
#endif
}

void loop() {
    const uint32_t now = millis();
    g_machine.tick(now);

#ifdef GREENBIN_TEST_CONSOLE
    g_console.tick(now);
#endif

#ifdef GREENBIN_ENABLE_WIFI
    // Only while idle: a slow or absent backend must never stall a transaction
    // mid-sort (§21, §23).
    if (g_machine.idle()) {
        g_heartbeat.tick(now);
    }
#endif

    // 10 ms is fast enough for a PIR edge and slow enough to leave the radio
    // and the LED bus alone.
    delay(10);
}
