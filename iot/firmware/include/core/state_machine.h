// The Phase 1 waste-detection state machine (spec §6, §16).
//
// Pure logic: it talks only to the interfaces in hal.h and receives time as a
// parameter, so every scenario in spec §19 can be driven from a native unit
// test with fake sensors and a fake network. Documented in
// iot/docs/state-machine.md.
#pragma once

#include <stdint.h>

#include "core/classification.h"
#include "core/fill_level.h"
#include "core/hal.h"
#include "core/retry_policy.h"

namespace greenbin {

enum class DeviceState {
    Boot,
    WifiConnecting,
    Idle,
    PresenceDetected,
    VerifyObject,
    Capture,
    Upload,
    WaitResult,
    ShowResult,
    Error,
};

const char* stateName(DeviceState state);

enum class ErrorKind {
    None,
    Camera,
    Network,
    Sensor,
};

// All timings and thresholds injected, so tests can run a 2.5 s wait in
// simulated microseconds and deployment timing never leaks into logic (spec §13).
struct StateMachineConfig {
    uint32_t pirWaitMs = 2500;
    float objectDeltaCm = 4.0f;
    uint32_t pirRearmMs = 5000;

    uint32_t fillIntervalMs = 300000;
    float emptyDistanceCm = 60.0f;
    float fullDistanceCm = 10.0f;
    float fullThresholdPercent = 80.0f;
    float fullClearPercent = 75.0f;

    uint8_t maxRetry = 3;
    uint32_t retryDelayMs = 2000;
    uint32_t retryMaxDelayMs = 30000;

    uint32_t wifiConnectTimeoutMs = 20000;
    uint32_t wifiRetryDelayMs = 15000;

    uint32_t errorDisplayMs = 2000;
    uint32_t resultDisplayMs = 3000;
};

class StateMachine {
  public:
    StateMachine(PresenceSensor& presence,
                 DistanceSensor& distance,
                 CameraService& camera,
                 NetworkService& network,
                 LedService& led,
                 const StateMachineConfig& config);

    void begin(uint32_t nowMs);
    void tick(uint32_t nowMs);

    DeviceState state() const { return state_; }
    bool binFull() const { return fullTracker_.isFull(); }
    ErrorKind lastError() const { return lastError_; }
    const ClassificationResult& lastResult() const { return lastResult_; }

    // Test observability. Scenario 1 asserts these stay at zero when a person
    // merely walks past.
    uint32_t capturesTaken() const { return capturesTaken_; }
    uint32_t uploadsAttempted() const { return uploadsAttempted_; }
    uint32_t readingsSent() const { return readingsSent_; }

  private:
    void transition(DeviceState next, uint32_t nowMs);
    void releaseFrameIfHeld();
    void updateBackgroundLed();
    void serviceFillLevel(uint32_t nowMs);
    void failInto(ErrorKind kind, LedPattern pattern, uint32_t nowMs);

    PresenceSensor& presence_;
    DistanceSensor& distance_;
    CameraService& camera_;
    NetworkService& network_;
    LedService& led_;
    StateMachineConfig config_;

    DeviceState state_ = DeviceState::Boot;
    ErrorKind lastError_ = ErrorKind::None;

    BinFullTracker fullTracker_;
    RetryPolicy retry_;

    uint32_t stateEnteredMs_ = 0;
    uint32_t presenceAtMs_ = 0;
    uint32_t rearmAtMs_ = 0;
    uint32_t nextFillCheckMs_ = 0;
    uint32_t retryAtMs_ = 0;
    uint32_t wifiAttemptMs_ = 0;
    bool wifiBackoff_ = false;

    UploadOutcome lastUpload_;
    // Set when a full/normal transition still needs delivering. Survives a
    // failed send so the change is not lost, and is retried on the next fill
    // interval rather than in a tight loop (spec §14, §15).
    bool pendingReading_ = false;

    float baselineCm_ = 0.0f;
    FillResult lastFill_;
    CameraFrame frame_;
    bool frameHeld_ = false;
    ClassificationResult lastResult_;

    uint32_t capturesTaken_ = 0;
    uint32_t uploadsAttempted_ = 0;
    uint32_t readingsSent_ = 0;
};

}  // namespace greenbin
