// Unit tests for the pure-logic core: fill-level maths, bin-full hysteresis,
// retry policy and classification mapping. Runs on the desktop, no hardware.
//
//     pio test -e native
#include <unity.h>

#include "core/classification.h"
#include "core/fill_level.h"
#include "core/retry_policy.h"

using namespace greenbin;

static DistanceReading ok(float cm) { return DistanceReading{true, cm}; }
static DistanceReading bad() { return DistanceReading{false, 0.0f}; }

// ─── Fill level (spec §13) ───────────────────────────────────────────────────

void test_fill_empty_bin_is_zero_percent(void) {
    const FillResult r = computeFillPercent(ok(60.0f), 60.0f, 10.0f);
    TEST_ASSERT_TRUE(r.valid);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, r.percent);
}

void test_fill_full_bin_is_hundred_percent(void) {
    const FillResult r = computeFillPercent(ok(10.0f), 60.0f, 10.0f);
    TEST_ASSERT_TRUE(r.valid);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 100.0f, r.percent);
}

void test_fill_midpoint(void) {
    const FillResult r = computeFillPercent(ok(35.0f), 60.0f, 10.0f);
    TEST_ASSERT_TRUE(r.valid);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 50.0f, r.percent);
}

void test_fill_clamps_above_hundred(void) {
    // Waste piled above the "full" calibration point.
    const FillResult r = computeFillPercent(ok(2.0f), 60.0f, 10.0f);
    TEST_ASSERT_TRUE(r.valid);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 100.0f, r.percent);
}

void test_fill_clamps_below_zero(void) {
    const FillResult r = computeFillPercent(ok(95.0f), 60.0f, 10.0f);
    TEST_ASSERT_TRUE(r.valid);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, r.percent);
}

void test_fill_rejects_invalid_reading(void) {
    // Scenario 9: no bogus value may be produced from a failed measurement.
    const FillResult r = computeFillPercent(bad(), 60.0f, 10.0f);
    TEST_ASSERT_FALSE(r.valid);
}

void test_fill_rejects_bad_calibration(void) {
    const FillResult r = computeFillPercent(ok(30.0f), 10.0f, 60.0f);
    TEST_ASSERT_FALSE(r.valid);
    const FillResult same = computeFillPercent(ok(30.0f), 30.0f, 30.0f);
    TEST_ASSERT_FALSE(same.valid);
}

// ─── Bin-full hysteresis (spec §14) ──────────────────────────────────────────

void test_bin_full_transition_reported_once(void) {
    BinFullTracker tracker(80.0f, 75.0f);
    TEST_ASSERT_FALSE(tracker.isFull());

    TEST_ASSERT_FALSE(tracker.update(FillResult{true, 50.0f}));
    TEST_ASSERT_TRUE(tracker.update(FillResult{true, 85.0f}));
    TEST_ASSERT_TRUE(tracker.isFull());

    // Still full — must NOT re-report (spec §14 forbids a repeating stream).
    TEST_ASSERT_FALSE(tracker.update(FillResult{true, 90.0f}));
    TEST_ASSERT_FALSE(tracker.update(FillResult{true, 99.0f}));
}

void test_bin_full_hysteresis_band_does_not_flap(void) {
    BinFullTracker tracker(80.0f, 75.0f);
    tracker.update(FillResult{true, 85.0f});
    TEST_ASSERT_TRUE(tracker.isFull());

    // Inside the 75–80 band: still full, no event.
    TEST_ASSERT_FALSE(tracker.update(FillResult{true, 78.0f}));
    TEST_ASSERT_TRUE(tracker.isFull());

    // Below the clear threshold: emptied.
    TEST_ASSERT_TRUE(tracker.update(FillResult{true, 70.0f}));
    TEST_ASSERT_FALSE(tracker.isFull());
}

void test_bin_full_ignores_invalid_reading(void) {
    BinFullTracker tracker(80.0f, 75.0f);
    tracker.update(FillResult{true, 85.0f});
    TEST_ASSERT_FALSE(tracker.update(FillResult{false, 0.0f}));
    TEST_ASSERT_TRUE(tracker.isFull());  // held, not assumed emptied
}

// ─── Retry policy (spec §15) ─────────────────────────────────────────────────

void test_retry_is_bounded(void) {
    RetryPolicy policy(3, 100, 5000);
    TEST_ASSERT_TRUE(policy.shouldRetry());
    policy.recordFailure();
    policy.recordFailure();
    TEST_ASSERT_TRUE(policy.shouldRetry());
    policy.recordFailure();
    TEST_ASSERT_FALSE(policy.shouldRetry());  // never retries forever
}

void test_retry_backoff_is_exponential_and_capped(void) {
    RetryPolicy policy(10, 100, 500);
    TEST_ASSERT_EQUAL_UINT32(100, policy.nextDelayMs());
    policy.recordFailure();
    TEST_ASSERT_EQUAL_UINT32(200, policy.nextDelayMs());
    policy.recordFailure();
    TEST_ASSERT_EQUAL_UINT32(400, policy.nextDelayMs());
    policy.recordFailure();
    TEST_ASSERT_EQUAL_UINT32(500, policy.nextDelayMs());  // capped
    policy.recordFailure();
    policy.recordFailure();
    TEST_ASSERT_EQUAL_UINT32(500, policy.nextDelayMs());  // stays capped
}

void test_retry_reset(void) {
    RetryPolicy policy(2, 100, 500);
    policy.recordFailure();
    policy.recordFailure();
    TEST_ASSERT_FALSE(policy.shouldRetry());
    policy.reset();
    TEST_ASSERT_TRUE(policy.shouldRetry());
    TEST_ASSERT_EQUAL_UINT32(100, policy.nextDelayMs());
}

// ─── Classification mapping (spec §11) ───────────────────────────────────────

void test_parse_known_statuses(void) {
    TEST_ASSERT_EQUAL(ClassificationStatus::Ok, parseStatus("ok"));
    TEST_ASSERT_EQUAL(ClassificationStatus::Warning, parseStatus("warning"));
    TEST_ASSERT_EQUAL(ClassificationStatus::Hazard, parseStatus("hazard"));
    TEST_ASSERT_EQUAL(ClassificationStatus::Refused, parseStatus("refused"));
    TEST_ASSERT_EQUAL(ClassificationStatus::Error, parseStatus("error"));
}

void test_unknown_status_never_becomes_ok(void) {
    // The core safety rule of spec §11/§26: uncertainty is never coerced into
    // a confident class.
    TEST_ASSERT_EQUAL(ClassificationStatus::Unknown, parseStatus("banana"));
    TEST_ASSERT_EQUAL(ClassificationStatus::Unknown, parseStatus(""));
    TEST_ASSERT_EQUAL(ClassificationStatus::Unknown, parseStatus(nullptr));
    TEST_ASSERT_NOT_EQUAL(LedPattern::Ok, ledPatternFor(ClassificationStatus::Unknown));
}

void test_led_mapping(void) {
    TEST_ASSERT_EQUAL(LedPattern::Ok, ledPatternFor(ClassificationStatus::Ok));
    TEST_ASSERT_EQUAL(LedPattern::Hazard, ledPatternFor(ClassificationStatus::Hazard));
    TEST_ASSERT_EQUAL(LedPattern::Warning, ledPatternFor(ClassificationStatus::Warning));
    // Refused shares the warning pattern — the device does not know the answer.
    TEST_ASSERT_EQUAL(LedPattern::Warning, ledPatternFor(ClassificationStatus::Refused));
}

void test_conclusiveness(void) {
    TEST_ASSERT_TRUE(isConclusive(ClassificationStatus::Ok));
    TEST_ASSERT_TRUE(isConclusive(ClassificationStatus::Warning));
    TEST_ASSERT_TRUE(isConclusive(ClassificationStatus::Hazard));
    TEST_ASSERT_FALSE(isConclusive(ClassificationStatus::Refused));
    TEST_ASSERT_FALSE(isConclusive(ClassificationStatus::Error));
    TEST_ASSERT_FALSE(isConclusive(ClassificationStatus::Unknown));
}

void setUp(void) {}
void tearDown(void) {}

int main(int, char**) {
    UNITY_BEGIN();

    RUN_TEST(test_fill_empty_bin_is_zero_percent);
    RUN_TEST(test_fill_full_bin_is_hundred_percent);
    RUN_TEST(test_fill_midpoint);
    RUN_TEST(test_fill_clamps_above_hundred);
    RUN_TEST(test_fill_clamps_below_zero);
    RUN_TEST(test_fill_rejects_invalid_reading);
    RUN_TEST(test_fill_rejects_bad_calibration);

    RUN_TEST(test_bin_full_transition_reported_once);
    RUN_TEST(test_bin_full_hysteresis_band_does_not_flap);
    RUN_TEST(test_bin_full_ignores_invalid_reading);

    RUN_TEST(test_retry_is_bounded);
    RUN_TEST(test_retry_backoff_is_exponential_and_capped);
    RUN_TEST(test_retry_reset);

    RUN_TEST(test_parse_known_statuses);
    RUN_TEST(test_unknown_status_never_becomes_ok);
    RUN_TEST(test_led_mapping);
    RUN_TEST(test_conclusiveness);

    return UNITY_END();
}
