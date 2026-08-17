// No-op sorter and display.
//
// The real ESP32-CAM has no GPIO left for a servo or an I2C display once the
// OV2640 is wired (see iot/docs/pin-map.md §4), so the `esp32cam` build has
// neither peripheral. Rather than litter the state machine with null checks,
// that build injects these: the flow runs unchanged, the calls go nowhere, and
// the sorter honestly reports that it never left HOME.
//
// Pure logic — no Arduino, so native tests and the desktop simulator can use
// them too.
#pragma once

#include "core/hal.h"

namespace greenbin {

class NullSorter : public SorterService {
  public:
    // Reports failure rather than pretending: a build with no servo has not
    // sorted anything, and the state machine must say so on screen (§24).
    bool moveTo(BinTarget) override { return false; }
    BinTarget position() const override { return BinTarget::Home; }
};

class NullDisplay : public DisplayService {
  public:
    void showBoot(const char*) override {}
    void showIdle(bool) override {}
    void showUserDetected() override {}
    void showCapturing() override {}
    void showAnalyzing() override {}
    void showSorting(BinTarget) override {}
    void showRejected(const char*) override {}
    void showComplete(WasteClass, bool, bool, float) override {}
    void showError(const char*) override {}
};

}  // namespace greenbin
