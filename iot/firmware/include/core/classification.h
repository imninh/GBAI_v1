// Classification result types, the status → LED mapping, and the decision of
// whether an item may be sorted at all.
//
// Pure logic: no Arduino, no HTTP. Parsing JSON is the network driver's job;
// interpreting the parsed status is this module's job (spec §11).
//
// The struct mirrors the backend response contract (Checkpoint 1 §25) field for
// field, so swapping the mock for a real HTTP response is a parse change and
// nothing more:
//
//     { "transaction_id": "TX-001", "status": "ok", "label": "plastic",
//       "confidence": 0.93, "action": "SORT", "target_bin": "PLASTIC" }
#pragma once

#include <stdint.h>

#include "core/hal.h"
#include "core/waste.h"

namespace greenbin {

enum class ClassificationStatus {
    Ok,
    Warning,
    Hazard,
    Refused,
    Error,
    Unknown,  // backend sent something we do not recognise
};

constexpr size_t kMaxLabelLength = 32;
constexpr size_t kMaxTransactionIdLength = 20;

struct ClassificationResult {
    ClassificationStatus status = ClassificationStatus::Unknown;
    char label[kMaxLabelLength] = {0};
    float confidence = 0.0f;
    char transactionId[kMaxTransactionIdLength] = {0};

    // Derived by resolveSorting(). Never set by a driver directly — that is what
    // guarantees the mock and the real backend reach the same decision.
    WasteClass waste = WasteClass::Unknown;
    BinTarget targetBin = BinTarget::Home;
    SortAction action = SortAction::Reject;

    bool shouldSort() const { return action == SortAction::Sort; }
};

// Maps a backend status string to the enum. Anything unrecognised becomes
// Unknown — never silently coerced into Ok (spec §11, §26).
ClassificationStatus parseStatus(const char* status);

const char* statusName(ClassificationStatus status);

// The device must not present an uncertain result as a confident one. Ok is the
// only status that earns the green pattern; Refused, Error and Unknown are all
// treated as "we do not know", not as success.
LedPattern ledPatternFor(ClassificationStatus status);

// True when the device may state a label to the user. False for Refused,
// Error and Unknown.
bool isConclusive(ClassificationStatus status);

// Fills in `waste`, `targetBin` and `action` from the status, label and
// confidence already present in `result`.
//
// Sorting is the exception, not the default: it requires status=ok, a label the
// firmware recognises, AND confidence at or above minConfidence. Everything else
// — a warning, a hazard, an unreadable label, a low-confidence guess — rejects
// to HOME. A wrongly sorted item contaminates a recycling stream, so a refusal
// is always the cheaper mistake (§16, §24).
void resolveSorting(ClassificationResult& result, float minConfidence);

}  // namespace greenbin
