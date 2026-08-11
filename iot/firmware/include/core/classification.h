// Classification result types and the status → LED mapping.
//
// Pure logic: no Arduino, no HTTP. Parsing JSON is the network driver's job;
// interpreting the parsed status is this module's job (spec §11).
#pragma once

#include <stdint.h>

#include "core/hal.h"

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

struct ClassificationResult {
    ClassificationStatus status = ClassificationStatus::Unknown;
    char label[kMaxLabelLength] = {0};
    float confidence = 0.0f;
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

}  // namespace greenbin
