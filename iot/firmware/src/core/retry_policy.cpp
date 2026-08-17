#include "core/retry_policy.h"

namespace greenbin {

RetryPolicy::RetryPolicy(uint8_t maxRetries, uint32_t baseDelayMs, uint32_t maxDelayMs)
    : maxRetries_(maxRetries), baseDelayMs_(baseDelayMs), maxDelayMs_(maxDelayMs) {}

bool RetryPolicy::shouldRetry() const { return failures_ < maxRetries_; }

uint32_t RetryPolicy::nextDelayMs() const {
    uint32_t delay = baseDelayMs_;
    // Shift rather than pow(); also guards against overflow on long outages.
    for (uint8_t i = 0; i < failures_; ++i) {
        if (delay >= maxDelayMs_ / 2) {
            return maxDelayMs_;
        }
        delay *= 2;
    }
    return delay > maxDelayMs_ ? maxDelayMs_ : delay;
}

void RetryPolicy::recordFailure() {
    if (failures_ < 255) {
        ++failures_;
    }
}

void RetryPolicy::reset() { failures_ = 0; }

}  // namespace greenbin
