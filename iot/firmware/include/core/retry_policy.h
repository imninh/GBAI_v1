// Bounded retry with exponential backoff (spec §15).
//
// The device must not spam a failing backend and must not retry forever. This
// is pure logic so the bound can actually be unit tested.
#pragma once

#include <stdint.h>

namespace greenbin {

class RetryPolicy {
  public:
    RetryPolicy(uint8_t maxRetries, uint32_t baseDelayMs, uint32_t maxDelayMs);

    // True while attempts remain. Once exhausted the caller must give up and
    // return to a valid state rather than looping.
    bool shouldRetry() const;

    // Delay before the next attempt: base * 2^failures, capped at maxDelayMs.
    uint32_t nextDelayMs() const;

    void recordFailure();
    void reset();

    uint8_t failures() const { return failures_; }

  private:
    uint8_t maxRetries_;
    uint32_t baseDelayMs_;
    uint32_t maxDelayMs_;
    uint8_t failures_ = 0;
};

}  // namespace greenbin
