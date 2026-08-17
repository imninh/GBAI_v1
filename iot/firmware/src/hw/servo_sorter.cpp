#include "hw/servo_sorter.h"

#include "core/logging.h"

namespace greenbin {

namespace {

constexpr uint32_t kFrequencyHz = 50;      // standard hobby-servo frame rate
constexpr uint8_t kResolutionBits = 16;    // 65535 steps over a 20 ms frame
constexpr uint32_t kFramePeriodUs = 20000;

int clampAngle(int angle) {
    if (angle < 0) {
        return 0;
    }
    if (angle > 180) {
        return 180;
    }
    return angle;
}

}  // namespace

ServoSorter::ServoSorter(uint8_t pin,
                         const Angles& angles,
                         uint16_t minPulseUs,
                         uint16_t maxPulseUs,
                         uint32_t settleMs,
                         uint8_t channel)
    : pin_(pin),
      angles_(angles),
      minPulseUs_(minPulseUs),
      maxPulseUs_(maxPulseUs),
      settleMs_(settleMs),
      channel_(channel) {}

void ServoSorter::begin() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    attached_ = ledcAttach(pin_, kFrequencyHz, kResolutionBits);
#else
    ledcSetup(channel_, kFrequencyHz, kResolutionBits);
    ledcAttachPin(pin_, channel_);
    attached_ = true;
#endif
    if (!attached_) {
        GB_LOG("SERVO", "attach failed on pin %u", static_cast<unsigned>(pin_));
        return;
    }

    // Park at HOME before anything else can command a move, so the flap is never
    // left wherever the last power cycle happened to leave it.
    position_ = BinTarget::Home;
    writeAngle(angles_.home);
    delay(settleMs_);
    GB_LOG("SERVO", "ready pin=%u home=%ddeg", static_cast<unsigned>(pin_), angles_.home);
}

int ServoSorter::angleFor(BinTarget target) const {
    switch (target) {
        case BinTarget::Plastic:
            return angles_.plastic;
        case BinTarget::Paper:
            return angles_.paper;
        case BinTarget::Metal:
            return angles_.metal;
        case BinTarget::Home:
        default:
            return angles_.home;
    }
}

void ServoSorter::writeAngle(int angle) {
    const int safe = clampAngle(angle);
    const uint32_t span = static_cast<uint32_t>(maxPulseUs_ - minPulseUs_);
    const uint32_t pulseUs = minPulseUs_ + (span * static_cast<uint32_t>(safe)) / 180UL;
    // 16-bit duty over a 20 ms frame: duty = pulse / period * 65535.
    const uint32_t duty = (pulseUs * 65535UL) / kFramePeriodUs;

#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcWrite(pin_, duty);
#else
    ledcWrite(channel_, duty);
#endif
    currentAngle_ = safe;
}

bool ServoSorter::moveTo(BinTarget target) {
    if (!attached_) {
        // Never report a move that did not happen — the caller must be able to
        // tell the user the item was not sorted (§24).
        GB_LOG_PLAIN("SERVO", "not attached; move refused");
        return false;
    }

    const int angle = angleFor(target);
    if (position_ == target && currentAngle_ == angle) {
        GB_LOG("SERVO", "target=%s already at %ddeg", binTargetName(target), angle);
        return true;
    }

    GB_LOG("SERVO", "target=%s angle=%ddeg moving", binTargetName(target), angle);
    writeAngle(angle);
    // The servo has no position feedback, so the only way to know the move
    // finished is to allow the worst-case sweep time. This is the one place the
    // firmware blocks on the mechanism, and it is bounded by SERVO_SETTLE_MS.
    delay(settleMs_);
    position_ = target;
    GB_LOG("SERVO", "target=%s done", binTargetName(target));
    return true;
}

}  // namespace greenbin
