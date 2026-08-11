#include "hw/sensors.h"

#include "core/logging.h"

namespace greenbin {

namespace {
constexpr uint8_t kMaxSamples = 9;
constexpr uint32_t kSettleMs = 60;  // HC-SR04 needs ~60 ms between pings
constexpr float kSpeedOfSoundCmPerUs = 0.0343f;
}  // namespace

// ─── HC-SR501 ────────────────────────────────────────────────────────────────

Hcsr501PresenceSensor::Hcsr501PresenceSensor(uint8_t pin) : pin_(pin) {}

void Hcsr501PresenceSensor::begin() {
    // No pull-up: the HC-SR501 drives the line push-pull at 3.3 V.
    pinMode(pin_, INPUT);
}

bool Hcsr501PresenceSensor::motionDetected() { return digitalRead(pin_) == HIGH; }

// ─── HC-SR04 ─────────────────────────────────────────────────────────────────

Hcsr04DistanceSensor::Hcsr04DistanceSensor(uint8_t trigPin,
                                           uint8_t echoPin,
                                           float minCm,
                                           float maxCm,
                                           uint32_t timeoutUs,
                                           uint8_t samples)
    : trigPin_(trigPin),
      echoPin_(echoPin),
      minCm_(minCm),
      maxCm_(maxCm),
      timeoutUs_(timeoutUs),
      samples_(samples > kMaxSamples ? kMaxSamples : (samples == 0 ? 1 : samples)) {}

void Hcsr04DistanceSensor::begin() {
    pinMode(trigPin_, OUTPUT);
    digitalWrite(trigPin_, LOW);
    // INPUT, not INPUT_PULLUP: the divider (see pin-map.md §5.1) sets the level,
    // and a pull-up would fight it.
    pinMode(echoPin_, INPUT);
}

DistanceReading Hcsr04DistanceSensor::readOnce() {
    digitalWrite(trigPin_, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin_, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin_, LOW);

    const unsigned long duration = pulseIn(echoPin_, HIGH, timeoutUs_);
    if (duration == 0) {
        return DistanceReading{};  // echo timeout — invalid, not zero distance
    }

    const float cm = (static_cast<float>(duration) * kSpeedOfSoundCmPerUs) / 2.0f;
    if (cm < minCm_ || cm > maxCm_) {
        return DistanceReading{};  // out of the sensor's credible range
    }
    return DistanceReading{true, cm};
}

DistanceReading Hcsr04DistanceSensor::read() {
    float values[kMaxSamples];
    uint8_t valid = 0;

    for (uint8_t i = 0; i < samples_; ++i) {
        const DistanceReading sample = readOnce();
        if (sample.valid) {
            values[valid++] = sample.cm;
        }
        if (i + 1 < samples_) {
            delay(kSettleMs);
        }
    }

    // Require a majority of good samples. Anything less and we report failure
    // rather than a median of noise (spec §19 scenario 9).
    if (valid == 0 || valid * 2 <= samples_) {
        GB_LOG("ULTRASONIC", "no valid samples (%u/%u)", static_cast<unsigned>(valid),
               static_cast<unsigned>(samples_));
        return DistanceReading{};
    }

    // Insertion sort — at most 9 elements.
    for (uint8_t i = 1; i < valid; ++i) {
        const float key = values[i];
        int8_t j = static_cast<int8_t>(i) - 1;
        while (j >= 0 && values[j] > key) {
            values[j + 1] = values[j];
            --j;
        }
        values[j + 1] = key;
    }

    return DistanceReading{true, values[valid / 2]};
}

}  // namespace greenbin
