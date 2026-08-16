#include "core/classification.h"

#include <string.h>

namespace greenbin {

ClassificationStatus parseStatus(const char* status) {
    if (status == nullptr) {
        return ClassificationStatus::Unknown;
    }
    if (strcmp(status, "ok") == 0) {
        return ClassificationStatus::Ok;
    }
    if (strcmp(status, "warning") == 0) {
        return ClassificationStatus::Warning;
    }
    if (strcmp(status, "hazard") == 0) {
        return ClassificationStatus::Hazard;
    }
    if (strcmp(status, "refused") == 0) {
        return ClassificationStatus::Refused;
    }
    if (strcmp(status, "error") == 0) {
        return ClassificationStatus::Error;
    }
    return ClassificationStatus::Unknown;
}

const char* statusName(ClassificationStatus status) {
    switch (status) {
        case ClassificationStatus::Ok:
            return "ok";
        case ClassificationStatus::Warning:
            return "warning";
        case ClassificationStatus::Hazard:
            return "hazard";
        case ClassificationStatus::Refused:
            return "refused";
        case ClassificationStatus::Error:
            return "error";
        case ClassificationStatus::Unknown:
        default:
            return "unknown";
    }
}

LedPattern ledPatternFor(ClassificationStatus status) {
    switch (status) {
        case ClassificationStatus::Ok:
            return LedPattern::Ok;
        case ClassificationStatus::Hazard:
            return LedPattern::Hazard;
        case ClassificationStatus::Warning:
        case ClassificationStatus::Refused:
        case ClassificationStatus::Unknown:
            // Refused and Unknown deliberately share the warning pattern: the
            // device does not know the answer, and must not imply that it does.
            return LedPattern::Warning;
        case ClassificationStatus::Error:
        default:
            return LedPattern::NetworkError;
    }
}

bool isConclusive(ClassificationStatus status) {
    return status == ClassificationStatus::Ok || status == ClassificationStatus::Warning ||
           status == ClassificationStatus::Hazard;
}

void resolveSorting(ClassificationResult& result, float minConfidence) {
    result.waste = wasteClassFromLabel(result.label);

    // Only a confident "ok" earns a bin. A hazard is conclusive but must never
    // be routed into a recycling stream, so it is deliberately not sortable.
    const bool sortable = result.status == ClassificationStatus::Ok &&
                          result.waste != WasteClass::Unknown &&
                          result.confidence >= minConfidence;

    if (!sortable) {
        result.action = SortAction::Reject;
        result.targetBin = BinTarget::Home;
        return;
    }

    result.action = SortAction::Sort;
    result.targetBin = binTargetFor(result.waste);
}

}  // namespace greenbin
