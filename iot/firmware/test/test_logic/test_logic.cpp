// Unit tests for the pure-logic core: fill-level maths, bin-full hysteresis,
// retry policy and classification mapping. Runs on the desktop, no hardware.
//
//     pio test -e native
#include <string.h>
#include <unity.h>

#include "core/classification.h"
#include "core/fill_level.h"
#include "core/retry_policy.h"
#include "core/waste.h"

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

// ─── Fill state buckets (Checkpoint 1 §12) ───────────────────────────────────

void test_fill_state_buckets(void) {
    const FillThresholds t;  // 60 / 80 / 95

    TEST_ASSERT_EQUAL(FillState::Normal, fillStateFor(0.0f, t));
    TEST_ASSERT_EQUAL(FillState::Normal, fillStateFor(59.9f, t));
    // Boundaries belong to the higher bucket, so 60% is already MEDIUM.
    TEST_ASSERT_EQUAL(FillState::Medium, fillStateFor(60.0f, t));
    TEST_ASSERT_EQUAL(FillState::Medium, fillStateFor(79.9f, t));
    TEST_ASSERT_EQUAL(FillState::NearFull, fillStateFor(80.0f, t));
    TEST_ASSERT_EQUAL(FillState::NearFull, fillStateFor(94.9f, t));
    TEST_ASSERT_EQUAL(FillState::Full, fillStateFor(95.0f, t));
    TEST_ASSERT_EQUAL(FillState::Full, fillStateFor(100.0f, t));
}

void test_fill_state_thresholds_are_configurable(void) {
    const FillThresholds t(40.0f, 70.0f, 90.0f);
    TEST_ASSERT_EQUAL(FillState::Medium, fillStateFor(45.0f, t));
    TEST_ASSERT_EQUAL(FillState::NearFull, fillStateFor(70.0f, t));
    TEST_ASSERT_EQUAL(FillState::Full, fillStateFor(91.0f, t));
}

// ─── Waste class ↔ bin mapping (Checkpoint 1 §9, §16) ────────────────────────

void test_labels_map_to_waste_classes(void) {
    TEST_ASSERT_EQUAL(WasteClass::Plastic, wasteClassFromLabel("plastic"));
    TEST_ASSERT_EQUAL(WasteClass::Paper, wasteClassFromLabel("paper"));
    TEST_ASSERT_EQUAL(WasteClass::Metal, wasteClassFromLabel("metal"));
    // Case is not the backend's contract to break us with.
    TEST_ASSERT_EQUAL(WasteClass::Plastic, wasteClassFromLabel("PLASTIC"));
    TEST_ASSERT_EQUAL(WasteClass::Paper, wasteClassFromLabel("Cardboard"));
}

void test_unrecognised_label_is_unknown_not_a_guess(void) {
    TEST_ASSERT_EQUAL(WasteClass::Unknown, wasteClassFromLabel("plastique"));
    TEST_ASSERT_EQUAL(WasteClass::Unknown, wasteClassFromLabel(""));
    TEST_ASSERT_EQUAL(WasteClass::Unknown, wasteClassFromLabel(nullptr));
}

void test_unknown_waste_has_no_bin(void) {
    TEST_ASSERT_EQUAL(BinTarget::Plastic, binTargetFor(WasteClass::Plastic));
    TEST_ASSERT_EQUAL(BinTarget::Paper, binTargetFor(WasteClass::Paper));
    TEST_ASSERT_EQUAL(BinTarget::Metal, binTargetFor(WasteClass::Metal));
    // The one that matters: Unknown parks at HOME rather than picking a bin.
    TEST_ASSERT_EQUAL(BinTarget::Home, binTargetFor(WasteClass::Unknown));
}

// ─── Sorting decision (Checkpoint 1 §16, §24) ────────────────────────────────

static ClassificationResult make(ClassificationStatus status,
                                 const char* label,
                                 float confidence) {
    ClassificationResult r;
    r.status = status;
    r.confidence = confidence;
    strncpy(r.label, label, sizeof(r.label) - 1);
    return r;
}

void test_confident_ok_result_is_sorted(void) {
    ClassificationResult r = make(ClassificationStatus::Ok, "plastic", 0.93f);
    resolveSorting(r, 0.60f);

    TEST_ASSERT_EQUAL(SortAction::Sort, r.action);
    TEST_ASSERT_EQUAL(BinTarget::Plastic, r.targetBin);
    TEST_ASSERT_TRUE(r.shouldSort());
}

void test_low_confidence_is_rejected(void) {
    ClassificationResult r = make(ClassificationStatus::Ok, "plastic", 0.59f);
    resolveSorting(r, 0.60f);

    TEST_ASSERT_EQUAL(SortAction::Reject, r.action);
    TEST_ASSERT_EQUAL(BinTarget::Home, r.targetBin);
    TEST_ASSERT_FALSE(r.shouldSort());
}

void test_non_ok_statuses_are_never_sorted(void) {
    const ClassificationStatus statuses[] = {
        ClassificationStatus::Warning, ClassificationStatus::Hazard,
        ClassificationStatus::Refused, ClassificationStatus::Error,
        ClassificationStatus::Unknown};

    for (ClassificationStatus status : statuses) {
        // High confidence and a perfectly good label — still not sorted,
        // because the status did not say "ok".
        ClassificationResult r = make(status, "metal", 0.99f);
        resolveSorting(r, 0.60f);
        TEST_ASSERT_EQUAL(SortAction::Reject, r.action);
        TEST_ASSERT_EQUAL(BinTarget::Home, r.targetBin);
    }
}

void test_unknown_label_is_never_sorted(void) {
    ClassificationResult r = make(ClassificationStatus::Ok, "banana peel", 0.99f);
    resolveSorting(r, 0.60f);

    TEST_ASSERT_EQUAL(WasteClass::Unknown, r.waste);
    TEST_ASSERT_EQUAL(SortAction::Reject, r.action);
    TEST_ASSERT_EQUAL(BinTarget::Home, r.targetBin);
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

    RUN_TEST(test_fill_state_buckets);
    RUN_TEST(test_fill_state_thresholds_are_configurable);

    RUN_TEST(test_labels_map_to_waste_classes);
    RUN_TEST(test_unrecognised_label_is_unknown_not_a_guess);
    RUN_TEST(test_unknown_waste_has_no_bin);

    RUN_TEST(test_confident_ok_result_is_sorted);
    RUN_TEST(test_low_confidence_is_rejected);
    RUN_TEST(test_non_ok_statuses_are_never_sorted);
    RUN_TEST(test_unknown_label_is_never_sorted);

    return UNITY_END();
}
