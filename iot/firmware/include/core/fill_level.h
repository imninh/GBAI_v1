// Fill-level maths and bin-full hysteresis (spec §13, §14).
//
// Pure logic — no Arduino, no sensor access. Takes a distance, returns a
// percentage. This is the single place fill level is computed.
#pragma once

#include <stdint.h>

#include "core/hal.h"

namespace greenbin {

struct FillResult {
    bool valid = false;
    float percent = 0.0f;

    // See the note on DistanceReading in hal.h — C++11 aggregate rules.
    FillResult() = default;
    FillResult(bool isValid, float pct) : valid(isValid), percent(pct) {}
};

// Converts a sensor-to-surface distance into a 0–100 fill percentage.
//
// The sensor sits at the top of the bin looking down, so distance DECREASES as
// the bin fills: emptyDistanceCm maps to 0%, fullDistanceCm to 100%.
//
// Returns valid=false — never a fabricated number — when the reading is
// invalid or the calibration is nonsensical (spec §19 scenario 9).
FillResult computeFillPercent(const DistanceReading& reading,
                              float emptyDistanceCm,
                              float fullDistanceCm);

// Tracks the full/not-full state with hysteresis so a bin hovering at the
// threshold does not emit an endless stream of transition events (spec §14).
class BinFullTracker {
  public:
    BinFullTracker(float fullThresholdPercent, float clearThresholdPercent);

    // Feeds a new fill percentage. Returns true when the state CHANGED, which
    // is the only time a reading should be pushed to the backend.
    bool update(const FillResult& fill);

    bool isFull() const { return isFull_; }

  private:
    float fullThreshold_;
    float clearThreshold_;
    bool isFull_ = false;
};

}  // namespace greenbin
