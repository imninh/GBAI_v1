// The nine required test scenarios from spec §19, driven against the real state
// machine with fake sensors, fake camera and fake network. No hardware, no
// network, no Arduino — this is what the hal.h abstraction buys.
//
//     pio test -e native
#include <string.h>
#include <unity.h>

#include "core/state_machine.h"

using namespace greenbin;

// ─── Fakes ───────────────────────────────────────────────────────────────────

class FakePresence : public PresenceSensor {
  public:
    bool motion = false;
    bool motionDetected() override { return motion; }
};

class FakeDistance : public DistanceSensor {
  public:
    DistanceReading next{true, 50.0f};
    int reads = 0;
    DistanceReading read() override {
        ++reads;
        return next;
    }
};

class FakeCamera : public CameraService {
  public:
    bool initOk = true;
    bool captureOk = true;
    int captures = 0;
    int releases = 0;
    uint8_t buffer[4] = {0xFF, 0xD8, 0xFF, 0xD9};  // minimal JPEG SOI/EOI

    bool initialize() override { return initOk; }
    CameraFrame captureJpeg() override {
        ++captures;
        CameraFrame frame;
        if (captureOk) {
            frame.data = buffer;
            frame.length = sizeof(buffer);
            frame.valid = true;
        }
        return frame;
    }
    void releaseFrame() override { ++releases; }
};

class FakeNetwork : public NetworkService {
  public:
    bool connected = true;
    NetResult uploadResult = NetResult::Ok;
    NetResult readingResult = NetResult::Ok;
    ClassificationStatus status = ClassificationStatus::Ok;
    float confidence = 0.91f;
    int uploads = 0;
    int readings = 0;
    float lastReadingPercent = -1.0f;
    bool lastReadingFull = false;

    void beginConnect() override {}
    bool isConnected() override { return connected; }

    UploadOutcome uploadCapture(const CameraFrame& frame,
                               float,
                               bool,
                               uint32_t,
                               ClassificationResult& out) override {
        ++uploads;
        // The state machine must never hand us an empty frame.
        TEST_ASSERT_TRUE(frame.valid);
        TEST_ASSERT_NOT_NULL(frame.data);

        UploadOutcome outcome;
        outcome.result = uploadResult;
        outcome.httpStatus = (uploadResult == NetResult::Ok) ? 200 : 0;
        if (uploadResult == NetResult::Ok) {
            out.status = status;
            out.confidence = confidence;
            strncpy(out.label, "plastic", sizeof(out.label) - 1);
        }
        return outcome;
    }

    NetResult sendBinReading(float fillPercent, bool isFull, uint32_t) override {
        ++readings;
        lastReadingPercent = fillPercent;
        lastReadingFull = isFull;
        return readingResult;
    }
};

class FakeLed : public LedService {
  public:
    LedPattern background = LedPattern::Off;
    LedPattern lastTemporary = LedPattern::Off;
    int temporaryCount = 0;

    void setBackground(LedPattern pattern) override { background = pattern; }
    void showTemporary(LedPattern pattern, uint32_t) override {
        lastTemporary = pattern;
        ++temporaryCount;
    }
    void tick(uint32_t) override {}
};

// ─── Harness ─────────────────────────────────────────────────────────────────

// Deliberately tiny timings: deployment timing must never be baked into logic
// (spec §13), so the same code runs in milliseconds here and minutes in the field.
static StateMachineConfig testConfig() {
    StateMachineConfig cfg;
    cfg.pirWaitMs = 100;
    cfg.objectDeltaCm = 4.0f;
    cfg.pirRearmMs = 50;
    cfg.fillIntervalMs = 1000;
    cfg.emptyDistanceCm = 60.0f;
    cfg.fullDistanceCm = 10.0f;
    cfg.fullThresholdPercent = 80.0f;
    cfg.fullClearPercent = 75.0f;
    cfg.maxRetry = 3;
    cfg.retryDelayMs = 10;
    cfg.retryMaxDelayMs = 100;
    cfg.wifiConnectTimeoutMs = 100;
    cfg.wifiRetryDelayMs = 50;
    cfg.errorDisplayMs = 100;
    cfg.resultDisplayMs = 100;
    return cfg;
}

struct Harness {
    FakePresence presence;
    FakeDistance distance;
    FakeCamera camera;
    FakeNetwork network;
    FakeLed led;
    StateMachine sm;
    uint32_t now = 1000;

    explicit Harness(const StateMachineConfig& cfg)
        : sm(presence, distance, camera, network, led, cfg) {}

    void tick() { sm.tick(now); }
    void advance(uint32_t ms) {
        now += ms;
        sm.tick(now);
    }
    void bootToIdle() {
        sm.begin(now);
        tick();       // BOOT -> WIFI_CONNECTING
        advance(10);  // WIFI_CONNECTING -> IDLE
        TEST_ASSERT_EQUAL(DeviceState::Idle, sm.state());
    }
    // Runs the confirmed-event path from IDLE up to the given distance delta.
    void triggerEvent(float baselineCm, float afterCm) {
        distance.next = DistanceReading{true, baselineCm};
        presence.motion = true;
        advance(10);  // IDLE: fill check + PIR -> PRESENCE_DETECTED
        // A real HC-SR501 pulses and drops. Leaving it asserted would (correctly)
        // make the device start a fresh detection cycle the moment it returns to
        // IDLE, which is not what these scenarios are measuring.
        presence.motion = false;
        distance.next = DistanceReading{true, afterCm};
        advance(150);  // PRESENCE_DETECTED -> VERIFY_OBJECT
        advance(1);    // VERIFY_OBJECT decides
    }
};

// ─── Scenario 1 — person walks past ──────────────────────────────────────────

void test_scenario1_false_trigger_captures_nothing(void) {
    Harness h(testConfig());
    h.bootToIdle();

    // PIR fires but the distance barely moves: someone walked by.
    h.triggerEvent(50.0f, 49.0f);

    TEST_ASSERT_EQUAL(DeviceState::Idle, h.sm.state());
    TEST_ASSERT_EQUAL_UINT32(0, h.sm.capturesTaken());   // NO image captured
    TEST_ASSERT_EQUAL_UINT32(0, h.sm.uploadsAttempted());  // NO vision request
    TEST_ASSERT_EQUAL_INT(0, h.camera.captures);
    TEST_ASSERT_EQUAL_INT(0, h.network.uploads);
}

// ─── Scenario 2 — valid waste event ──────────────────────────────────────────

void test_scenario2_valid_event_captures_and_uploads(void) {
    Harness h(testConfig());
    h.bootToIdle();

    h.triggerEvent(50.0f, 44.0f);  // 6 cm drop, threshold is 4 cm
    TEST_ASSERT_EQUAL(DeviceState::Capture, h.sm.state());

    h.advance(1);  // CAPTURE
    TEST_ASSERT_EQUAL(DeviceState::Upload, h.sm.state());
    TEST_ASSERT_EQUAL_UINT32(1, h.sm.capturesTaken());

    h.advance(1);  // UPLOAD
    TEST_ASSERT_EQUAL(DeviceState::WaitResult, h.sm.state());
    TEST_ASSERT_EQUAL_INT(1, h.network.uploads);
}

// ─── Scenario 3 — successful classification ──────────────────────────────────

void test_scenario3_ok_shows_green_and_returns_idle(void) {
    Harness h(testConfig());
    h.network.status = ClassificationStatus::Ok;
    h.bootToIdle();

    h.triggerEvent(50.0f, 44.0f);
    h.advance(1);  // CAPTURE
    h.advance(1);  // UPLOAD
    h.advance(1);  // WAIT_RESULT -> SHOW_RESULT

    TEST_ASSERT_EQUAL(DeviceState::ShowResult, h.sm.state());
    TEST_ASSERT_EQUAL(LedPattern::Ok, h.led.lastTemporary);
    TEST_ASSERT_EQUAL(ClassificationStatus::Ok, h.sm.lastResult().status);

    h.advance(150);  // result display expires
    TEST_ASSERT_EQUAL(DeviceState::Idle, h.sm.state());

    // Buffer released exactly once per capture (spec §7).
    TEST_ASSERT_EQUAL_INT(h.camera.captures, h.camera.releases);
}

// ─── Scenario 4 — low confidence ─────────────────────────────────────────────

void test_scenario4_warning_is_not_presented_as_success(void) {
    Harness h(testConfig());
    h.network.status = ClassificationStatus::Warning;
    h.network.confidence = 0.31f;
    h.bootToIdle();

    h.triggerEvent(50.0f, 44.0f);
    h.advance(1);
    h.advance(1);
    h.advance(1);

    TEST_ASSERT_EQUAL(LedPattern::Warning, h.led.lastTemporary);
    TEST_ASSERT_NOT_EQUAL(LedPattern::Ok, h.led.lastTemporary);
}

void test_scenario4_refused_is_not_presented_as_success(void) {
    Harness h(testConfig());
    h.network.status = ClassificationStatus::Refused;
    h.bootToIdle();

    h.triggerEvent(50.0f, 44.0f);
    h.advance(1);
    h.advance(1);
    h.advance(1);

    // A refusal must never render as the success pattern (spec §11).
    TEST_ASSERT_NOT_EQUAL(LedPattern::Ok, h.led.lastTemporary);
    TEST_ASSERT_FALSE(isConclusive(h.sm.lastResult().status));
}

// ─── Scenario 5 — hazardous waste ────────────────────────────────────────────

void test_scenario5_hazard_pattern(void) {
    Harness h(testConfig());
    h.network.status = ClassificationStatus::Hazard;
    h.bootToIdle();

    h.triggerEvent(50.0f, 44.0f);
    h.advance(1);
    h.advance(1);
    h.advance(1);

    TEST_ASSERT_EQUAL(LedPattern::Hazard, h.led.lastTemporary);
    TEST_ASSERT_EQUAL(ClassificationStatus::Hazard, h.sm.lastResult().status);
}

// ─── Scenario 6 — backend timeout ────────────────────────────────────────────

void test_scenario6_timeout_retries_bounded_then_recovers(void) {
    Harness h(testConfig());
    h.network.uploadResult = NetResult::Timeout;
    h.bootToIdle();

    h.triggerEvent(50.0f, 44.0f);
    h.advance(1);  // CAPTURE -> UPLOAD

    // Drive well past the point where an unbounded retry loop would still be
    // hammering the backend.
    for (int i = 0; i < 40; ++i) {
        h.advance(20);
    }

    // Bounded: never more attempts than MAX_RETRY.
    TEST_ASSERT_EQUAL_INT(3, h.network.uploads);
    // Recovered to a valid state rather than freezing or rebooting.
    TEST_ASSERT_EQUAL(DeviceState::Idle, h.sm.state());
    TEST_ASSERT_EQUAL(ErrorKind::Network, h.sm.lastError());
    // Camera buffer released despite the failure (spec §15).
    TEST_ASSERT_EQUAL_INT(h.camera.captures, h.camera.releases);
}

void test_camera_failure_recovers_without_reboot(void) {
    Harness h(testConfig());
    h.camera.captureOk = false;
    h.bootToIdle();

    h.triggerEvent(50.0f, 44.0f);
    h.advance(1);  // CAPTURE fails
    TEST_ASSERT_EQUAL(DeviceState::Error, h.sm.state());
    TEST_ASSERT_EQUAL(ErrorKind::Camera, h.sm.lastError());

    h.advance(150);  // error display expires
    TEST_ASSERT_EQUAL(DeviceState::Idle, h.sm.state());
    TEST_ASSERT_EQUAL_INT(0, h.network.uploads);  // nothing uploaded
}

// ─── Scenario 7 — bin full ───────────────────────────────────────────────────

void test_scenario7_bin_full_sends_reading_and_goes_solid(void) {
    Harness h(testConfig());
    h.bootToIdle();
    h.distance.next = DistanceReading{true, 12.0f};  // 96 %

    h.advance(10);  // first fill check

    TEST_ASSERT_TRUE(h.sm.binFull());
    TEST_ASSERT_EQUAL_UINT32(1, h.sm.readingsSent());
    TEST_ASSERT_TRUE(h.network.lastReadingFull);
    // Solid background, distinct from the blinking warning patterns (spec §12).
    TEST_ASSERT_EQUAL(LedPattern::BinFull, h.led.background);

    // Repeated full readings must NOT produce repeated events (spec §14).
    for (int i = 0; i < 5; ++i) {
        h.advance(1100);
    }
    TEST_ASSERT_EQUAL_UINT32(1, h.sm.readingsSent());
}

// ─── Scenario 8 — bin emptied ────────────────────────────────────────────────

void test_scenario8_bin_emptied_sends_changed_reading(void) {
    Harness h(testConfig());
    h.bootToIdle();

    h.distance.next = DistanceReading{true, 12.0f};
    h.advance(10);
    TEST_ASSERT_TRUE(h.sm.binFull());
    TEST_ASSERT_EQUAL_UINT32(1, h.sm.readingsSent());

    h.distance.next = DistanceReading{true, 55.0f};  // 10 %
    h.advance(1100);

    TEST_ASSERT_FALSE(h.sm.binFull());
    TEST_ASSERT_EQUAL_UINT32(2, h.sm.readingsSent());
    TEST_ASSERT_FALSE(h.network.lastReadingFull);
    TEST_ASSERT_EQUAL(LedPattern::Idle, h.led.background);
}

// ─── Scenario 9 — sensor invalid reading ─────────────────────────────────────

void test_scenario9_invalid_reading_produces_no_fill_value(void) {
    Harness h(testConfig());
    h.bootToIdle();
    h.distance.next = DistanceReading{false, 0.0f};

    h.advance(10);

    TEST_ASSERT_EQUAL_UINT32(0, h.sm.readingsSent());  // no bogus reading sent
    TEST_ASSERT_FALSE(h.sm.binFull());
    TEST_ASSERT_EQUAL(ErrorKind::Sensor, h.sm.lastError());
    TEST_ASSERT_EQUAL(DeviceState::Idle, h.sm.state());  // continues safely
}

void test_invalid_baseline_blocks_capture(void) {
    Harness h(testConfig());
    h.bootToIdle();
    h.distance.next = DistanceReading{false, 0.0f};
    h.presence.motion = true;

    h.advance(10);

    // Without a baseline there is nothing to compare, so no event is confirmed.
    TEST_ASSERT_EQUAL(DeviceState::Idle, h.sm.state());
    TEST_ASSERT_EQUAL_UINT32(0, h.sm.capturesTaken());
}

// ─── Network-failure behaviour (spec §15) ────────────────────────────────────

void test_wifi_never_blocks_forever(void) {
    Harness h(testConfig());
    h.network.connected = false;
    h.sm.begin(h.now);
    h.tick();  // BOOT -> WIFI_CONNECTING

    for (int i = 0; i < 20; ++i) {
        h.advance(30);
    }
    // Still trying, but the device is alive and cycling rather than wedged.
    TEST_ASSERT_EQUAL(DeviceState::WifiConnecting, h.sm.state());

    h.network.connected = true;
    h.advance(30);
    TEST_ASSERT_EQUAL(DeviceState::Idle, h.sm.state());
}

void test_failed_bin_reading_is_retried_not_lost(void) {
    Harness h(testConfig());
    h.network.readingResult = NetResult::Timeout;
    h.bootToIdle();
    h.distance.next = DistanceReading{true, 12.0f};

    h.advance(10);
    TEST_ASSERT_TRUE(h.sm.binFull());
    TEST_ASSERT_EQUAL_UINT32(0, h.sm.readingsSent());  // send failed
    TEST_ASSERT_EQUAL_INT(1, h.network.readings);      // but was attempted

    h.network.readingResult = NetResult::Ok;
    h.advance(1100);  // next fill interval retries the pending transition
    TEST_ASSERT_EQUAL_UINT32(1, h.sm.readingsSent());
}

void setUp(void) {}
void tearDown(void) {}

int main(int, char**) {
    UNITY_BEGIN();

    RUN_TEST(test_scenario1_false_trigger_captures_nothing);
    RUN_TEST(test_scenario2_valid_event_captures_and_uploads);
    RUN_TEST(test_scenario3_ok_shows_green_and_returns_idle);
    RUN_TEST(test_scenario4_warning_is_not_presented_as_success);
    RUN_TEST(test_scenario4_refused_is_not_presented_as_success);
    RUN_TEST(test_scenario5_hazard_pattern);
    RUN_TEST(test_scenario6_timeout_retries_bounded_then_recovers);
    RUN_TEST(test_camera_failure_recovers_without_reboot);
    RUN_TEST(test_scenario7_bin_full_sends_reading_and_goes_solid);
    RUN_TEST(test_scenario8_bin_emptied_sends_changed_reading);
    RUN_TEST(test_scenario9_invalid_reading_produces_no_fill_value);
    RUN_TEST(test_invalid_baseline_blocks_capture);
    RUN_TEST(test_wifi_never_blocks_forever);
    RUN_TEST(test_failed_bin_reading_is_retried_not_lost);

    return UNITY_END();
}
