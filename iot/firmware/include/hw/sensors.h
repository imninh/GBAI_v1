// Thin hardware wrappers for the HC-SR501 (presence) and HC-SR04 (distance).
//
// Deliberately thin: all decision-making lives in src/core/. These classes do
// nothing but talk to pins (spec §22).
#pragma once

#include <Arduino.h>

#include "core/hal.h"

namespace greenbin {

class Hcsr501PresenceSensor : public PresenceSensor {
  public:
    explicit Hcsr501PresenceSensor(uint8_t pin);
    void begin();
    bool motionDetected() override;

  private:
    uint8_t pin_;
};

// Reads the HC-SR04 several times and takes the median, which rejects the
// single spurious echo that soft or angled surfaces routinely produce.
//
// NOTE: read() blocks. Worst case is roughly
// samples × (timeout + settle) ≈ 3 × (30 ms + 60 ms) ≈ 270 ms. That is
// acceptable because distance is only read on a fill interval or a PIR trigger,
// never in the hot loop. See iot/docs/architecture.md "Known limitations".
class Hcsr04DistanceSensor : public DistanceSensor {
  public:
    Hcsr04DistanceSensor(uint8_t trigPin,
                         uint8_t echoPin,
                         float minCm,
                         float maxCm,
                         uint32_t timeoutUs,
                         uint8_t samples);
    void begin();
    DistanceReading read() override;

  private:
    DistanceReading readOnce();

    uint8_t trigPin_;
    uint8_t echoPin_;
    float minCm_;
    float maxCm_;
    uint32_t timeoutUs_;
    uint8_t samples_;
};

}  // namespace greenbin
