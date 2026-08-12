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
        case DeviceState::Sorting:
            return "SORTING";
        case DeviceState::UpdateFill:
            return "UPDATE_FILL";
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
                           SorterService& sorter,
                           DisplayService& display,
                           const StateMachineConfig& config)
    : presence_(presence),
      distance_(distance),
      camera_(camera),
      network_(network),
      led_(led),
      sorter_(sorter),
      display_(display),
      config_(config),
      fullTracker_(config.fullThresholdPercent, config.fullClearPercent),
      retry_(config.maxRetry, config.retryDelayMs, config.retryMaxDelayMs) {}

void StateMachine::transition(DeviceState next, uint32_t nowMs) {
    if (next == state_) {
        return;
    }
    // Logged as a transition, not a destination, so a Serial trace reads as the
    // flow of spec §18 rather than a list of unrelated states.
    GB_LOG("STATE", "%s -> %s", stateName(state_), stateName(next));
    state_ = next;
    stateEnteredMs_ = nowMs;
    applyScreenFor(next);
}

void StateMachine::applyScreenFor(DeviceState next) {
    switch (next) {
        case DeviceState::Boot:
            display_.showBoot(FIRMWARE_VERSION);
            break;
        case DeviceState::Idle:
            display_.showIdle(fullTracker_.isFull());
            break;
        case DeviceState::PresenceDetected:
            display_.showUserDetected();
            break;
        case DeviceState::Capture:
            display_.showCapturing();
            break;
        case DeviceState::Upload:
            display_.showAnalyzing();
            break;
        case DeviceState::Sorting:
            if (lastResult_.shouldSort()) {
                display_.showSorting(lastResult_.targetBin);
            } else {
                display_.showRejected("Item not recognised");
            }
            break;
        case DeviceState::ShowResult:
            display_.showComplete(lastResult_.waste, lastSorted_, lastFill_.valid,
                                  lastFill_.percent);
            break;
        case DeviceState::Error:
            display_.showError(lastErrorMessage_[0] != '\0' ? lastErrorMessage_ : "System error");
            break;
        // WifiConnecting, VerifyObject, WaitResult and UpdateFill deliberately
        // keep whatever screen is already up: they are sub-steps of a phase the
        // user has already been told about, and repainting would flicker.
        default:
            break;
    }
}

FillState StateMachine::fillState() const {
    return fillStateFor(lastFill_.percent, config_.fillThresholds);
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

void StateMachine::returnSorterHome() {
    // Called on every exit from a transaction, successful or not, so the flap is
    // never left pointing at a bin (§24).
    if (!sorter_.moveTo(BinTarget::Home)) {
        GB_LOG_PLAIN("SERVO", "could not return to HOME");
        lastError_ = ErrorKind::Sorter;
    }
}

void StateMachine::failInto(ErrorKind kind,
                            LedPattern pattern,
                            const char* message,
                            uint32_t nowMs) {
    lastError_ = kind;
    manualEvent_ = false;
    releaseFrameIfHeld();
    strncpy(lastErrorMessage_, message, sizeof(lastErrorMessage_) - 1);
    lastErrorMessage_[sizeof(lastErrorMessage_) - 1] = '\0';
    led_.showTemporary(pattern, nowMs);
    transition(DeviceState::Error, nowMs);
    // Safe state before anything else happens: an error must never leave the
    // mechanism mid-travel (§24).
    returnSorterHome();
}

void StateMachine::begin(uint32_t nowMs) {
    state_ = DeviceState::Boot;
    stateEnteredMs_ = nowMs;
    nextFillCheckMs_ = nowMs;  // take a first reading immediately
    GB_LOG("BOOT", "firmware=%s", FIRMWARE_VERSION);
    GB_LOG("STATE", "%s", stateName(state_));
    applyScreenFor(state_);
}

bool StateMachine::startManualEvent(uint32_t nowMs) {
    if (state_ != DeviceState::Idle) {
        GB_LOG("EVENT", "manual trigger ignored; busy in %s", stateName(state_));
        return false;
    }

    GB_LOG_PLAIN("EVENT", "manual trigger from serial console");
    const DistanceReading baseline = distance_.read();
    baselineCm_ = baseline.valid ? baseline.cm : 0.0f;
    // Freshest fill evidence to ride along with the upload, exactly as the
    // sensor-driven path does. Invalid stays invalid — never a guess.
    lastFill_ = computeFillPercent(baseline, config_.emptyDistanceCm, config_.fullDistanceCm);
    // The operator has asserted that an item went in, so the confirmation step
    // has nothing left to verify.
    manualEvent_ = true;
    presenceAtMs_ = nowMs;
    transition(DeviceState::PresenceDetected, nowMs);
    return true;
}

FillResult StateMachine::measureFill(uint32_t nowMs, bool publish) {
    const DistanceReading reading = distance_.read();
    const FillResult fill =
        computeFillPercent(reading, config_.emptyDistanceCm, config_.fullDistanceCm);

    if (!fill.valid) {
        // Scenario 9: an unusable reading produces no fill value at all. The
        // previous known state is held rather than replaced with a guess.
        lastError_ = ErrorKind::Sensor;
        GB_LOG_PLAIN("HC-SR04", "invalid reading; fill level not updated");
        return fill;
    }

    lastFill_ = fill;
    GB_LOG("HC-SR04", "distance=%.1fcm fill=%.1f%% state=%s", static_cast<double>(reading.cm),
           static_cast<double>(fill.percent),
           fillStateName(fillStateFor(fill.percent, config_.fillThresholds)));

    if (fullTracker_.update(fill)) {
        // Only transitions are reported, never a repeating "still full" stream.
        GB_LOG("BIN", "state_changed full=%d", fullTracker_.isFull() ? 1 : 0);
        pendingReading_ = true;
        updateBackgroundLed();
    }

    if (publish && pendingReading_) {
        const NetResult result =
            network_.sendBinReading(fill.percent, fullTracker_.isFull(), nowMs / 1000);
        if (result == NetResult::Ok) {
            ++readingsSent_;
            pendingReading_ = false;
            GB_LOG_PLAIN("API", "bin reading accepted");
        } else {
            // Keep it pending; the next fill interval retries. No tight loop.
            GB_LOG("API", "bin reading failed result=%d, will retry",
                   static_cast<int>(result));
        }
    }
    return fill;
}

void StateMachine::serviceFillLevel(uint32_t nowMs) {
    if (static_cast<int32_t>(nowMs - nextFillCheckMs_) < 0) {
        return;
    }
    nextFillCheckMs_ = nowMs + config_.fillIntervalMs;
    measureFill(nowMs, true);
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

            GB_LOG_PLAIN("PIR", "User detected");
            const DistanceReading baseline = distance_.read();
            if (!baseline.valid) {
                // Without a baseline there is nothing to compare against, so no
                // event can be confirmed. Back off briefly instead of retrying
                // every loop.
                lastError_ = ErrorKind::Sensor;
                GB_LOG_PLAIN("HC-SR04", "baseline invalid; ignoring trigger");
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
            if (manualEvent_) {
                // Console-triggered run: nothing to confirm, go straight to
                // capture so the demo does not depend on slider timing.
                manualEvent_ = false;
                GB_LOG_PLAIN("EVENT", "waste_confirmed (manual trigger)");
                transition(DeviceState::Capture, nowMs);
                break;
            }

            const DistanceReading after = distance_.read();
            if (!after.valid) {
                lastError_ = ErrorKind::Sensor;
                GB_LOG_PLAIN("HC-SR04", "confirm reading invalid; treating as no event");
                rearmAtMs_ = nowMs + config_.pirRearmMs;
                transition(DeviceState::Idle, nowMs);
                break;
            }

            // Waste deposited into a top-down bin makes the surface closer, so
            // a genuine event is a DROP in distance.
            const float delta = baselineCm_ - after.cm;
            GB_LOG("HC-SR04", "before=%.1f after=%.1f delta=%.1f",
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
                // No image means no classification, so nothing may be sorted.
                failInto(ErrorKind::Camera, LedPattern::NetworkError, "Camera failed", nowMs);
                break;
            }
            frameHeld_ = true;
            ++capturesTaken_;
            GB_LOG("CAMERA", "Image captured successfully bytes=%u",
                   static_cast<unsigned>(frame_.length));
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
                // One place decides whether this item may be sorted, shared by
                // the mock and the real backend (§16, §25).
                resolveSorting(lastResult_, config_.minSortConfidence);
                GB_LOG("AI", "transaction=%s status=%s label=%s confidence=%.2f action=%s target=%s",
                       lastResult_.transactionId[0] != '\0' ? lastResult_.transactionId : "none",
                       statusName(lastResult_.status),
                       lastResult_.label[0] != '\0' ? lastResult_.label : "null",
                       static_cast<double>(lastResult_.confidence),
                       sortActionName(lastResult_.action), binTargetName(lastResult_.targetBin));
                if (!isConclusive(lastResult_.status)) {
                    // The backend refused or errored. The device says so; it
                    // does not invent a label (spec §11, §26).
                    GB_LOG_PLAIN("AI", "inconclusive; no label asserted");
                }
                releaseFrameIfHeld();
                led_.showTemporary(ledPatternFor(lastResult_.status), nowMs);
                GB_LOG("LED", "%s", statusName(lastResult_.status));
                transition(DeviceState::Sorting, nowMs);
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
            failInto(ErrorKind::Network, LedPattern::NetworkError, "Backend unreachable", nowMs);
            break;
        }

        case DeviceState::Sorting: {
            lastSorted_ = false;

            if (!lastResult_.shouldSort()) {
                // Unknown, low confidence, hazard or warning: the flap does not
                // move and the item is not directed into any bin (§16, §24).
                GB_LOG("SERVO", "action=REJECT target=HOME reason=%s",
                       statusName(lastResult_.status));
                returnSorterHome();
                transition(DeviceState::UpdateFill, nowMs);
                break;
            }

            if (sorter_.moveTo(lastResult_.targetBin)) {
                lastSorted_ = true;
                ++sortsPerformed_;
            } else {
                // The mechanism did not move. The transaction still completes —
                // the item is already in the bin — but nothing claims it was
                // sorted, and the completion screen says so.
                lastError_ = ErrorKind::Sorter;
                GB_LOG("SERVO", "move to %s failed; item NOT sorted",
                       binTargetName(lastResult_.targetBin));
            }
            transition(DeviceState::UpdateFill, nowMs);
            break;
        }

        case DeviceState::UpdateFill: {
            // Measure after sorting, so the reading reflects the item that was
            // just deposited.
            if (!measureFill(nowMs, true).valid) {
                // Drop the previous reading rather than let the completion
                // screen present a stale percentage as this transaction's
                // result. Background monitoring keeps its last known value;
                // a user-facing claim does not (§24).
                lastFill_ = FillResult();
                GB_LOG_PLAIN("HC-SR04", "post-sort reading failed; fill reported as unavailable");
            }
            transition(DeviceState::ShowResult, nowMs);
            // Screen first, then park the flap: the user sees the outcome while
            // the mechanism resets (§18 demo order).
            returnSorterHome();
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
