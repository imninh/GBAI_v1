// WS2812 status LED (spec §12).
//
// Every LED decision in the firmware goes through this class. Nothing else
// calls NeoPixel directly — that is the rule spec §12 ends on.
//
// Two layers:
//   background — persistent device state (Idle, or BinFull while the bin is full)
//   temporary  — a time-boxed pattern that plays over it and then expires
//
// This is why "bin full" (solid red, persistent) never gets confused with a
// classification warning (blinking red, transient).
#pragma once

#include <Adafruit_NeoPixel.h>
#include <Arduino.h>

#include "core/hal.h"

namespace greenbin {

class Ws2812LedService : public LedService {
  public:
    Ws2812LedService(uint8_t pin, uint16_t count, uint8_t maxBrightness);
    void begin();

    void setBackground(LedPattern pattern) override;
    void showTemporary(LedPattern pattern, uint32_t nowMs) override;
    void tick(uint32_t nowMs) override;

  private:
    void render(LedPattern pattern, uint32_t elapsedMs);

    Adafruit_NeoPixel strip_;
    uint8_t maxBrightness_;

    LedPattern background_ = LedPattern::Idle;
    LedPattern temporary_ = LedPattern::Off;
    bool temporaryActive_ = false;
    uint32_t temporaryStartMs_ = 0;
    uint32_t temporaryDurationMs_ = 0;
    LedPattern lastRendered_ = LedPattern::Off;
    bool lastOn_ = false;
};

}  // namespace greenbin
