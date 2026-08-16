// Servo-driven sorting flap (Checkpoint 1 §9).
//
// Driven straight off the ESP32 LEDC peripheral rather than through a servo
// library: a 50 Hz hobby-servo pulse is a dozen lines of PWM setup, and this way
// the firmware picks up no dependency whose ESP32-core compatibility we would
// have to track.
//
// The angle for each bin lives in config.h. Nothing outside this class knows
// that a BinTarget is a number of degrees.
#pragma once

#include <Arduino.h>

#include "core/hal.h"

namespace greenbin {

class ServoSorter : public SorterService {
  public:
    struct Angles {
        int home;
        int plastic;
        int paper;
        int metal;
    };

    ServoSorter(uint8_t pin,
                const Angles& angles,
                uint16_t minPulseUs,
                uint16_t maxPulseUs,
                uint32_t settleMs,
                uint8_t channel);

    // Attaches the PWM channel and parks the flap at HOME, so the mechanism is
    // in a known position before any transaction can start (§24).
    void begin();

    bool moveTo(BinTarget target) override;
    BinTarget position() const override { return position_; }

    int angleFor(BinTarget target) const;
    int currentAngle() const { return currentAngle_; }

  private:
    void writeAngle(int angle);

    uint8_t pin_;
    Angles angles_;
    uint16_t minPulseUs_;
    uint16_t maxPulseUs_;
    uint32_t settleMs_;
    uint8_t channel_;

    BinTarget position_ = BinTarget::Home;
    int currentAngle_ = -1;  // -1 until begin() writes the first pulse
    bool attached_ = false;
};

}  // namespace greenbin
