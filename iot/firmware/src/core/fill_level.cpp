#include "core/fill_level.h"

namespace greenbin {

FillResult computeFillPercent(const DistanceReading& reading,
                              float emptyDistanceCm,
                              float fullDistanceCm) {
    FillResult result;

    // A failed reading yields no fill value at all.
    if (!reading.valid) {
        return result;
    }

    // Nonsensical calibration: "empty" must be further away than "full".
    // Returning invalid beats dividing by zero or inverting the scale silently.
    if (emptyDistanceCm <= fullDistanceCm) {
        return result;
    }

    const float span = emptyDistanceCm - fullDistanceCm;
    float percent = ((emptyDistanceCm - reading.cm) / span) * 100.0f;

    // Clamp: a reading beyond either calibration point is plausible (waste
    // piled above the "full" mark, or a bin deeper than calibrated) and should
    // saturate rather than report >100% or <0% (spec §13).
    if (percent < 0.0f) {
        percent = 0.0f;
    } else if (percent > 100.0f) {
        percent = 100.0f;
    }

    result.valid = true;
    result.percent = percent;
    return result;
}

BinFullTracker::BinFullTracker(float fullThresholdPercent, float clearThresholdPercent)
    : fullThreshold_(fullThresholdPercent), clearThreshold_(clearThresholdPercent) {}

bool BinFullTracker::update(const FillResult& fill) {
    // An invalid reading tells us nothing; hold the previous state rather than
    // guessing the bin was emptied.
    if (!fill.valid) {
        return false;
    }

    if (!isFull_ && fill.percent >= fullThreshold_) {
        isFull_ = true;
        return true;
    }
    if (isFull_ && fill.percent < clearThreshold_) {
        isFull_ = false;
        return true;
    }
    return false;
}

}  // namespace greenbin
