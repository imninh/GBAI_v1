#include "core/state_machine.h"

#include <string.h>

#include "core/logging.h"

namespace greenbin {

const char* stateName(DeviceState state) {
    switch (state) {
        case DeviceState::Boot:
            return "BOOT";
        case DeviceState::WifiConnecting:
            return "WIFI_CONNECTING";
        case DeviceState::Idle:
            return "IDLE";
        case DeviceState::PresenceDetected:
            return "PRESENCE_DETECTED";
        case DeviceState::VerifyObject:
            return "VERIFY_OBJECT";
        case DeviceState::Capture:
            return "CAPTURE";
        case DeviceState::Upload:
            return "UPLOAD";
        case DeviceState::WaitResult:
            return "WAIT_RESULT";
        case DeviceState::ShowResult:
            return "SHOW_RESULT";
        case DeviceState::Error:
        default:
            return "ERROR";
    }
}

StateMachine::StateMachine(PresenceSensor& presence,
                           DistanceSensor& distance,
                           CameraService& camera,
                           NetworkService& network,
                           LedService& led,
                           const StateMachineConfig& config)
    : presence_(presence),
      distance_(distance),
      camera_(camera),
      network_(network),
      led_(led),
      config_(config),
      fullTracker_(config.fullThresholdPercent, config.fullClearPercent),
      retry_(config.maxRetry, config.retryDelayMs, config.retryMaxDelayMs) {}

void StateMachine::transition(DeviceState next, uint32_t nowMs) {
    if (next == state_) {
        return;
    }
    state_ = next;
    stateEnteredMs_ = nowMs;
    GB_LOG("STATE", "%s", stateName(next));
}

void StateMachine::releaseFrameIfHeld() {
    // Every exit from Capture/Upload/WaitResult routes through here. Leaking a
    // framebuffer starves the next capture (spec §7, §15).
    if (frameHeld_) {
        camera_.releaseFrame();
        frameHeld_ = false;
        frame_ = CameraFrame{};
    }
}

void StateMachine::updateBackgroundLed() {
    // Bin-full is a persistent background state; classification results play
    // over it and then fall back to it (spec §12, §16).
    led_.setBackground(fullTracker_.isFull() ? LedPattern::BinFull : LedPattern::Idle);
}

void StateMachine::failInto(ErrorKind kind, LedPattern pattern, uint32_t nowMs) {
    lastError_ = kind;
    releaseFrameIfHeld();
    led_.showTemporary(pattern, nowMs);
    transition(DeviceState::Error, nowMs);
}

void StateMachine::begin(uint32_t nowMs) {
    state_ = DeviceState::Boot;
    stateEnteredMs_ = nowMs;
    nextFillCheckMs_ = nowMs;  // take a first reading immediately
    GB_LOG("BOOT", "firmware=%s", FIRMWARE_VERSION);
    GB_LOG("STATE", "%s", stateName(state_));
}

void StateMachine::serviceFillLevel(uint32_t nowMs) {
    if (static_cast<int32_t>(nowMs - nextFillCheckMs_) < 0) {
        return;
    }
    nextFillCheckMs_ = nowMs + config_.fillIntervalMs;

    const DistanceReading reading = distance_.read();
    const FillResult fill =
        computeFillPercent(reading, config_.emptyDistanceCm, config_.fullDistanceCm);

    if (!fill.valid) {
        // Scenario 9: an unusable reading produces no fill value at all. The
        // previous known state is held rather than replaced with a guess.
        lastError_ = ErrorKind::Sensor;
        GB_LOG_PLAIN("ULTRASONIC", "invalid reading; fill level not updated");
        return;
    }

    lastFill_ = fill;
    GB_LOG("FILL", "distance=%.1f percent=%.1f", static_cast<double>(reading.cm),
           static_cast<double>(fill.percent));

    if (fullTracker_.update(fill)) {
        // Only transitions are reported, never a repeating "still full" stream.
        GB_LOG("BIN", "state_changed full=%d", fullTracker_.isFull() ? 1 : 0);
        pendingReading_ = true;
        updateBackgroundLed();
    }

    if (pendingReading_) {
        const NetResult result =
            network_.sendBinReading(fill.percent, fullTracker_.isFull(), nowMs / 1000);
        if (result == NetResult::Ok) {
            ++readingsSent_;
            pendingReading_ = false;
            GB_LOG_PLAIN("HTTP", "bin reading accepted");
        } else {
            // Keep it pending; the next fill interval retries. No tight loop.
            GB_LOG("HTTP", "bin reading failed result=%d, will retry",
                   static_cast<int>(result));
        }
    }
}

void StateMachine::tick(uint32_t nowMs) {
    led_.tick(nowMs);

    switch (state_) {
        case DeviceState::Boot: {
            led_.showTemporary(LedPattern::Booting, nowMs);
            if (!camera_.initialize()) {
                // Camera failure must not spin the board in a reboot loop
                // (spec §7). Report it and continue: fill-level monitoring is
                // still useful without a camera.
                GB_LOG_PLAIN("CAMERA", "init failed");
                lastError_ = ErrorKind::Camera;
            } else {
                GB_LOG_PLAIN("CAMERA", "init ok");
            }
            network_.beginConnect();
            wifiAttemptMs_ = nowMs;
            wifiBackoff_ = false;
            transition(DeviceState::WifiConnecting, nowMs);
            break;
        }

        case DeviceState::WifiConnecting: {
            led_.showTemporary(LedPattern::WifiConnecting, nowMs);
            if (network_.isConnected()) {
                GB_LOG_PLAIN("WIFI", "connected");
                updateBackgroundLed();
                transition(DeviceState::Idle, nowMs);
                break;
            }
            const uint32_t elapsed = nowMs - wifiAttemptMs_;
            if (!wifiBackoff_ && elapsed >= config_.wifiConnectTimeoutMs) {
                GB_LOG_PLAIN("WIFI", "connect timeout");
                led_.showTemporary(LedPattern::NetworkError, nowMs);
                wifiBackoff_ = true;
                wifiAttemptMs_ = nowMs;
            } else if (wifiBackoff_ && elapsed >= config_.wifiRetryDelayMs) {
                GB_LOG_PLAIN("WIFI", "retrying");
                network_.beginConnect();
                wifiBackoff_ = false;
                wifiAttemptMs_ = nowMs;
            }
            break;
        }

        case DeviceState::Idle: {
            serviceFillLevel(nowMs);

            if (!presence_.motionDetected()) {
                break;
            }
            if (static_cast<int32_t>(nowMs - rearmAtMs_) < 0) {
                break;  // still within the post-event cool-down
            }

            GB_LOG_PLAIN("PIR", "detected");
            const DistanceReading baseline = distance_.read();
            if (!baseline.valid) {
                // Without a baseline there is nothing to compare against, so no
                // event can be confirmed. Back off briefly instead of retrying
                // every loop.
                lastError_ = ErrorKind::Sensor;
                GB_LOG_PLAIN("ULTRASONIC", "baseline invalid; ignoring trigger");
                rearmAtMs_ = nowMs + config_.pirRearmMs;
                break;
            }
            baselineCm_ = baseline.cm;
            presenceAtMs_ = nowMs;
            transition(DeviceState::PresenceDetected, nowMs);
            break;
        }

        case DeviceState::PresenceDetected: {
            // Settle window: someone reaching over the bin has not yet let go
            // of anything (spec §6).
            if (nowMs - presenceAtMs_ >= config_.pirWaitMs) {
                transition(DeviceState::VerifyObject, nowMs);
            }
            break;
        }

        case DeviceState::VerifyObject: {
            const DistanceReading after = distance_.read();
            if (!after.valid) {
                lastError_ = ErrorKind::Sensor;
                GB_LOG_PLAIN("ULTRASONIC", "confirm reading invalid; treating as no event");
                rearmAtMs_ = nowMs + config_.pirRearmMs;
                transition(DeviceState::Idle, nowMs);
                break;
            }

            // Waste deposited into a top-down bin makes the surface closer, so
            // a genuine event is a DROP in distance.
            const float delta = baselineCm_ - after.cm;
            GB_LOG("ULTRASONIC", "before=%.1f after=%.1f delta=%.1f",
                   static_cast<double>(baselineCm_), static_cast<double>(after.cm),
                   static_cast<double>(delta));

            if (delta < config_.objectDeltaCm) {
                // Scenario 1: someone walked past. No capture, no vision call.
                GB_LOG_PLAIN("EVENT", "false_trigger");
                rearmAtMs_ = nowMs + config_.pirRearmMs;
                transition(DeviceState::Idle, nowMs);
                break;
            }

            GB_LOG_PLAIN("EVENT", "waste_confirmed");
            // Keep the confirmed distance: it is the freshest fill evidence and
            // rides along with the capture upload.
            lastFill_ = computeFillPercent(after, config_.emptyDistanceCm, config_.fullDistanceCm);
            transition(DeviceState::Capture, nowMs);
            break;
        }

        case DeviceState::Capture: {
            led_.showTemporary(LedPattern::Processing, nowMs);
            frame_ = camera_.captureJpeg();
            if (!frame_.valid || frame_.data == nullptr || frame_.length == 0) {
                GB_LOG_PLAIN("CAMERA", "capture failed");
                camera_.releaseFrame();  // driver may hold a partial buffer
                frameHeld_ = false;
                rearmAtMs_ = nowMs + config_.pirRearmMs;
                failInto(ErrorKind::Camera, LedPattern::NetworkError, nowMs);
                break;
            }
            frameHeld_ = true;
            ++capturesTaken_;
            GB_LOG("CAMERA", "jpeg_bytes=%u", static_cast<unsigned>(frame_.length));
            retry_.reset();
            transition(DeviceState::Upload, nowMs);
            break;
        }

        case DeviceState::Upload: {
            if (static_cast<int32_t>(nowMs - retryAtMs_) < 0) {
                break;  // serving a backoff delay
            }
            ++uploadsAttempted_;
            lastResult_ = ClassificationResult{};
            lastUpload_ = network_.uploadCapture(frame_, lastFill_.percent, lastFill_.valid,
                                                 nowMs / 1000, lastResult_);
            GB_LOG("HTTP", "upload status=%d", lastUpload_.httpStatus);
            transition(DeviceState::WaitResult, nowMs);
            break;
        }

        case DeviceState::WaitResult: {
            if (lastUpload_.result == NetResult::Ok) {
                retry_.reset();
                GB_LOG("AI", "status=%s label=%s confidence=%.2f",
                       statusName(lastResult_.status), lastResult_.label,
                       static_cast<double>(lastResult_.confidence));
                if (!isConclusive(lastResult_.status)) {
                    // The backend refused or errored. The device says so; it
                    // does not invent a label (spec §11, §26).
                    GB_LOG_PLAIN("AI", "inconclusive; no label asserted");
                }
                releaseFrameIfHeld();
                led_.showTemporary(ledPatternFor(lastResult_.status), nowMs);
                GB_LOG("LED", "%s", statusName(lastResult_.status));
                transition(DeviceState::ShowResult, nowMs);
                break;
            }

            // Anything else is a failed delivery. Bounded retry, then give up.
            retry_.recordFailure();
            if (retry_.shouldRetry()) {
                const uint32_t delay = retry_.nextDelayMs();
                GB_LOG("HTTP", "retry %u in %ums", static_cast<unsigned>(retry_.failures()),
                       static_cast<unsigned>(delay));
                retryAtMs_ = nowMs + delay;
                transition(DeviceState::Upload, nowMs);
                break;
            }

            GB_LOG_PLAIN("HTTP", "giving up after max retries");
            rearmAtMs_ = nowMs + config_.pirRearmMs;
            failInto(ErrorKind::Network, LedPattern::NetworkError, nowMs);
            break;
        }

        case DeviceState::ShowResult: {
            if (nowMs - stateEnteredMs_ >= config_.resultDisplayMs) {
                rearmAtMs_ = nowMs + config_.pirRearmMs;
                updateBackgroundLed();
                transition(DeviceState::Idle, nowMs);
            }
            break;
        }

        case DeviceState::Error: {
            // Always recovers: an error is displayed, then the device returns to
            // a valid state. It never reboots and never wedges (spec §15).
            if (nowMs - stateEnteredMs_ >= config_.errorDisplayMs) {
                updateBackgroundLed();
                transition(DeviceState::Idle, nowMs);
            }
            break;
        }
    }
}

}  // namespace greenbin
