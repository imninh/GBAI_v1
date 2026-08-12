// SSD1306 128x64 I2C status screen (Checkpoint 1 §10).
//
// Every screen the device can show is a method here. No caller formats display
// text or positions pixels — that is what keeps display logic out of the state
// machine and lets the panel be replaced without touching any flow code.
#pragma once

#include <Adafruit_SSD1306.h>
#include <Arduino.h>

#include "core/hal.h"

namespace greenbin {

class OledDisplay : public DisplayService {
  public:
    OledDisplay(uint8_t sdaPin, uint8_t sclPin, uint8_t i2cAddress, uint32_t i2cFrequency);

    // Returns false if the panel does not answer on I2C. The caller keeps
    // running: a missing screen must not stop the bin from sorting.
    bool begin();
    bool isReady() const { return ready_; }

    void showBoot(const char* version) override;
    void showIdle(bool binFull) override;
    void showUserDetected() override;
    void showCapturing() override;
    void showAnalyzing() override;
    void showSorting(BinTarget target) override;
    void showRejected(const char* reason) override;
    void showComplete(WasteClass waste, bool sorted, bool fillValid, float fillPercent) override;
    void showError(const char* message) override;

    // Test-mode helper: draws an arbitrary three-line frame. Used by the
    // hardware self-test, not by the state machine.
    void showRaw(const char* header, const char* headline, const char* line1, const char* line2);

  private:
    // The single drawing primitive. `headline` is rendered large when it fits;
    // nullptr lines are simply skipped.
    void draw(const char* header, const char* headline, const char* line1, const char* line2);

    Adafruit_SSD1306 panel_;
    uint8_t sdaPin_;
    uint8_t sclPin_;
    uint8_t address_;
    uint32_t frequency_;
    bool ready_ = false;
};

}  // namespace greenbin
