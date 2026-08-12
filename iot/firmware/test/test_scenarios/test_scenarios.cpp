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
    const char* label = "plastic";
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
            strncpy(out.label, label, sizeof(out.label) - 1);
            strncpy(out.transactionId, "TX-001", sizeof(out.transactionId) - 1);
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

class FakeSorter : public SorterService {
  public:
    bool failMoves = false;
    BinTarget last = BinTarget::Home;
    int moves = 0;
    // Every position the flap was commanded to, in order. Scenario assertions
    // check the whole path, not just where it ended up.
    BinTarget history[16] = {BinTarget::Home};
    int historyCount = 0;

    bool moveTo(BinTarget target) override {
        ++moves;
        if (historyCount < 16) {
            history[historyCount++] = target;
        }
        if (failMoves) {
            return false;
        }
        last = target;
        return true;
    }
    BinTarget position() const override { return last; }
};

class FakeDisplay : public DisplayService {
  public:
    // Which screen was last painted. The state machine is the only caller, so
    // this is how the tests assert the user was told the truth.
    enum class Screen {
        None,
        Boot,
        Idle,
        UserDetected,
        Capturing,
        Analyzing,
        Sorting,
        Rejected,
        Complete,
        Error,
    };

    Screen screen = Screen::None;
    BinTarget sortingTarget = BinTarget::Home;
    WasteClass completeWaste = WasteClass::Unknown;
    bool completeSorted = false;
    bool completeFillValid = false;
    float completeFillPercent = -1.0f;
    bool idleBinFull = false;

    void showBoot(const char*) override { screen = Screen::Boot; }
    void showIdle(bool binFull) override {
        screen = Screen::Idle;
        idleBinFull = binFull;
    }
    void showUserDetected() override { screen = Screen::UserDetected; }
    void showCapturing() override { screen = Screen::Capturing; }
    void showAnalyzing() override { screen = Screen::Analyzing; }
    void showSorting(BinTarget target) override {
        screen = Screen::Sorting;
        sortingTarget = target;
    }
    void showRejected(const char*) override { screen = Screen::Rejected; }
    void showComplete(WasteClass waste, bool sorted, bool fillValid, float fillPercent) override {
        screen = Screen::Complete;
        completeWaste = waste;
        completeSorted = sorted;
        completeFillValid = fillValid;
        completeFillPercent = fillPercent;
    }
    void showError(const char*) override { screen = Screen::Error; }
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
    FakeSorter sorter;
    FakeDisplay display;
    StateMachine sm;
    uint32_t now = 1000;

    explicit Harness(const StateMachineConfig& cfg)
        : sm(presence, distance, camera, network, led, sorter, display, cfg) {}

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
    // From CAPTURE through to SHOW_RESULT: capture, upload, result, sort,
    // fill. One tick per state, so a new state in the middle of the flow shows
    // up here rather than silently changing what every scenario asserts.
    void runToShowResult() {
        advance(1);  // CAPTURE      -> UPLOAD
        advance(1);  // UPLOAD       -> WAIT_RESULT
        advance(1);  // WAIT_RESULT  -> SORTING
        advance(1);  // SORTING      -> UPDATE_FILL
        advance(1);  // UPDATE_FILL  -> SHOW_RESULT
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
    h.runToShowResult();

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
    h.runToShowResult();

    TEST_ASSERT_EQUAL(LedPattern::Warning, h.led.lastTemporary);
    TEST_ASSERT_NOT_EQUAL(LedPattern::Ok, h.led.lastTemporary);
    // A warning is never sorted, whatever label came with it (§24).
    TEST_ASSERT_FALSE(h.sm.lastResult().shouldSort());
    TEST_ASSERT_EQUAL(BinTarget::Home, h.sorter.position());
    TEST_ASSERT_EQUAL_UINT32(0, h.sm.sortsPerformed());
}

void test_scenario4_refused_is_not_presented_as_success(void) {
    Harness h(testConfig());
    h.network.status = ClassificationStatus::Refused;
    h.bootToIdle();

    h.triggerEvent(50.0f, 44.0f);
    h.runToShowResult();

    // A refusal must never render as the success pattern (spec §11).
    TEST_ASSERT_NOT_EQUAL(LedPattern::Ok, h.led.lastTemporary);
    TEST_ASSERT_FALSE(isConclusive(h.sm.lastResult().status));
    TEST_ASSERT_FALSE(h.sm.lastResult().shouldSort());
}

// ─── Scenario 5 — hazardous waste ────────────────────────────────────────────

void test_scenario5_hazard_pattern(void) {
    Harness h(testConfig());
    h.network.status = ClassificationStatus::Hazard;
    h.bootToIdle();

    h.triggerEvent(50.0f, 44.0f);
    h.runToShowResult();

    TEST_ASSERT_EQUAL(LedPattern::Hazard, h.led.lastTemporary);
    TEST_ASSERT_EQUAL(ClassificationStatus::Hazard, h.sm.lastResult().status);
    // Hazardous waste is conclusive but must not be routed into a recycling
    // stream, so the flap stays HOME (§24).
    TEST_ASSERT_FALSE(h.sm.lastResult().shouldSort());
    TEST_ASSERT_EQUAL(BinTarget::Home, h.sorter.position());
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

// ─── Checkpoint 1 — sorting flow ─────────────────────────────────────────────

// Drives one full transaction and returns the harness, so the three material
// flows differ only in the label the backend returns.
static void runSortFlow(Harness& h, const char* label) {
    h.network.status = ClassificationStatus::Ok;
    h.network.label = label;
    h.network.confidence = 0.93f;
    h.bootToIdle();
    h.triggerEvent(50.0f, 44.0f);
    h.runToShowResult();
}

void test_plastic_flow_moves_sorter_then_returns_home(void) {
    Harness h(testConfig());
    runSortFlow(h, "plastic");

    TEST_ASSERT_EQUAL(DeviceState::ShowResult, h.sm.state());
    TEST_ASSERT_EQUAL(WasteClass::Plastic, h.sm.lastResult().waste);
    TEST_ASSERT_EQUAL(SortAction::Sort, h.sm.lastResult().action);
    TEST_ASSERT_EQUAL(BinTarget::Plastic, h.sm.lastResult().targetBin);
    TEST_ASSERT_EQUAL_UINT32(1, h.sm.sortsPerformed());

    // Commanded to PLASTIC and then parked back at HOME (§24).
    TEST_ASSERT_EQUAL(BinTarget::Plastic, h.sorter.history[0]);
    TEST_ASSERT_EQUAL(BinTarget::Home, h.sorter.position());

    // The screen names the material and reports a fill level (§10).
    TEST_ASSERT_EQUAL(FakeDisplay::Screen::Complete, h.display.screen);
    TEST_ASSERT_TRUE(h.display.completeSorted);
    TEST_ASSERT_TRUE(h.display.completeFillValid);
    TEST_ASSERT_EQUAL(WasteClass::Plastic, h.display.completeWaste);
}

void test_paper_flow_targets_paper_bin(void) {
    Harness h(testConfig());
    runSortFlow(h, "paper");

    TEST_ASSERT_EQUAL(BinTarget::Paper, h.sm.lastResult().targetBin);
    TEST_ASSERT_EQUAL(BinTarget::Paper, h.sorter.history[0]);
    TEST_ASSERT_EQUAL(BinTarget::Home, h.sorter.position());
}

void test_metal_flow_targets_metal_bin(void) {
    Harness h(testConfig());
    runSortFlow(h, "metal");

    TEST_ASSERT_EQUAL(BinTarget::Metal, h.sm.lastResult().targetBin);
    TEST_ASSERT_EQUAL(BinTarget::Metal, h.sorter.history[0]);
    TEST_ASSERT_EQUAL(BinTarget::Home, h.sorter.position());
}

// The rule the whole checkpoint hangs on: an item the device cannot name is
// never routed anywhere (§16, §24, §26).
void test_unknown_label_never_moves_the_sorter(void) {
    Harness h(testConfig());
    runSortFlow(h, "something-we-have-never-seen");

    TEST_ASSERT_EQUAL(WasteClass::Unknown, h.sm.lastResult().waste);
    TEST_ASSERT_EQUAL(SortAction::Reject, h.sm.lastResult().action);
    TEST_ASSERT_EQUAL(BinTarget::Home, h.sm.lastResult().targetBin);
    TEST_ASSERT_EQUAL_UINT32(0, h.sm.sortsPerformed());
    TEST_ASSERT_EQUAL(BinTarget::Home, h.sorter.position());
    // Never claims an item was accepted when it was not.
    TEST_ASSERT_FALSE(h.display.completeSorted);
}

void test_low_confidence_is_not_sorted(void) {
    Harness h(testConfig());
    h.network.status = ClassificationStatus::Ok;
    h.network.label = "plastic";
    h.network.confidence = 0.41f;  // below cfg.minSortConfidence
    h.bootToIdle();
    h.triggerEvent(50.0f, 44.0f);
    h.runToShowResult();

    // The label is recognised, but the device is not confident enough to act.
    TEST_ASSERT_EQUAL(WasteClass::Plastic, h.sm.lastResult().waste);
    TEST_ASSERT_EQUAL(SortAction::Reject, h.sm.lastResult().action);
    TEST_ASSERT_EQUAL_UINT32(0, h.sm.sortsPerformed());
}

void test_sorter_failure_is_reported_not_hidden(void) {
    Harness h(testConfig());
    h.sorter.failMoves = true;
    runSortFlow(h, "plastic");

    // The mechanism refused, so nothing is counted as sorted and the completion
    // screen says the item was not sorted.
    TEST_ASSERT_EQUAL_UINT32(0, h.sm.sortsPerformed());
    TEST_ASSERT_FALSE(h.display.completeSorted);
    TEST_ASSERT_EQUAL(ErrorKind::Sorter, h.sm.lastError());
    // Still recovers to IDLE — a stuck flap does not wedge the device.
    h.advance(150);
    TEST_ASSERT_EQUAL(DeviceState::Idle, h.sm.state());
}

void test_invalid_fill_after_sorting_shows_no_percentage(void) {
    Harness h(testConfig());
    h.network.status = ClassificationStatus::Ok;
    h.network.label = "plastic";
    h.network.confidence = 0.93f;
    h.bootToIdle();
    h.triggerEvent(50.0f, 44.0f);

    h.advance(1);  // CAPTURE     -> UPLOAD
    h.advance(1);  // UPLOAD      -> WAIT_RESULT
    h.advance(1);  // WAIT_RESULT -> SORTING
    h.advance(1);  // SORTING     -> UPDATE_FILL
    h.distance.next = DistanceReading{};  // sensor fails at exactly this point
    h.advance(1);  // UPDATE_FILL -> SHOW_RESULT

    // Classification completed and the item was sorted...
    TEST_ASSERT_EQUAL_UINT32(1, h.sm.sortsPerformed());
    TEST_ASSERT_TRUE(h.display.completeSorted);
    // ...but no fill number is invented for the screen (§11, §24).
    TEST_ASSERT_FALSE(h.display.completeFillValid);
    TEST_ASSERT_EQUAL(ErrorKind::Sensor, h.sm.lastError());
}

void test_display_follows_the_flow(void) {
    Harness h(testConfig());
    h.network.status = ClassificationStatus::Ok;
    h.network.label = "plastic";
    h.network.confidence = 0.93f;
    h.bootToIdle();
    TEST_ASSERT_EQUAL(FakeDisplay::Screen::Idle, h.display.screen);

    h.triggerEvent(50.0f, 44.0f);
    TEST_ASSERT_EQUAL(FakeDisplay::Screen::Capturing, h.display.screen);

    h.advance(1);  // CAPTURE -> UPLOAD
    TEST_ASSERT_EQUAL(FakeDisplay::Screen::Analyzing, h.display.screen);

    h.advance(1);  // UPLOAD -> WAIT_RESULT
    h.advance(1);  // WAIT_RESULT -> SORTING
    TEST_ASSERT_EQUAL(FakeDisplay::Screen::Sorting, h.display.screen);
    TEST_ASSERT_EQUAL(BinTarget::Plastic, h.display.sortingTarget);

    h.advance(1);  // SORTING -> UPDATE_FILL
    h.advance(1);  // UPDATE_FILL -> SHOW_RESULT
    TEST_ASSERT_EQUAL(FakeDisplay::Screen::Complete, h.display.screen);

    h.advance(150);  // back to idle
    TEST_ASSERT_EQUAL(FakeDisplay::Screen::Idle, h.display.screen);
}

// ─── Checkpoint 1 — console-triggered run ────────────────────────────────────

void test_manual_trigger_runs_the_same_flow(void) {
    Harness h(testConfig());
    h.network.status = ClassificationStatus::Ok;
    h.network.label = "metal";
    h.network.confidence = 0.9f;
    h.bootToIdle();

    TEST_ASSERT_TRUE(h.sm.startManualEvent(h.now));
    TEST_ASSERT_EQUAL(DeviceState::PresenceDetected, h.sm.state());

    h.advance(150);  // PRESENCE_DETECTED -> VERIFY_OBJECT
    // No distance drop is staged, yet the manual run still reaches CAPTURE: the
    // operator asserted the item, so there is nothing to confirm.
    h.advance(1);
    TEST_ASSERT_EQUAL(DeviceState::Capture, h.sm.state());

    h.runToShowResult();
    TEST_ASSERT_EQUAL_UINT32(1, h.sm.sortsPerformed());
    TEST_ASSERT_EQUAL(BinTarget::Metal, h.sorter.history[0]);
}

void test_manual_trigger_is_refused_while_busy(void) {
    Harness h(testConfig());
    h.bootToIdle();

    TEST_ASSERT_TRUE(h.sm.startManualEvent(h.now));
    // One trigger, one transaction: a second request mid-flow is rejected
    // rather than starting a parallel run (§14).
    TEST_ASSERT_FALSE(h.sm.startManualEvent(h.now));
    TEST_ASSERT_FALSE(h.sm.startManualEvent(h.now));
}

void test_pir_held_high_does_not_start_a_second_transaction(void) {
    Harness h(testConfig());
    h.network.status = ClassificationStatus::Ok;
    h.bootToIdle();

    // PIR stays asserted for the whole transaction, as a real HC-SR501 does
    // while someone stands at the bin.
    h.distance.next = DistanceReading{true, 50.0f};
    h.presence.motion = true;
    h.advance(10);  // IDLE -> PRESENCE_DETECTED
    h.distance.next = DistanceReading{true, 44.0f};
    h.advance(150);
    h.advance(1);  // VERIFY_OBJECT -> CAPTURE
    h.runToShowResult();
    h.advance(150);  // SHOW_RESULT -> IDLE

    // Still exactly one capture: the post-event cool-down suppresses the
    // still-asserted PIR line (§14).
    TEST_ASSERT_EQUAL_UINT32(1, h.sm.capturesTaken());
    h.advance(10);
    TEST_ASSERT_EQUAL_UINT32(1, h.sm.capturesTaken());
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

    RUN_TEST(test_plastic_flow_moves_sorter_then_returns_home);
    RUN_TEST(test_paper_flow_targets_paper_bin);
    RUN_TEST(test_metal_flow_targets_metal_bin);
    RUN_TEST(test_unknown_label_never_moves_the_sorter);
    RUN_TEST(test_low_confidence_is_not_sorted);
    RUN_TEST(test_sorter_failure_is_reported_not_hidden);
    RUN_TEST(test_invalid_fill_after_sorting_shows_no_percentage);
    RUN_TEST(test_display_follows_the_flow);
    RUN_TEST(test_manual_trigger_runs_the_same_flow);
    RUN_TEST(test_manual_trigger_is_refused_while_busy);
    RUN_TEST(test_pir_held_high_does_not_start_a_second_transaction);

    return UNITY_END();
}
