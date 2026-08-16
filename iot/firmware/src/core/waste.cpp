#include "core/waste.h"

#include <string.h>

namespace greenbin {

namespace {

// Case-insensitive compare. The backend emits lower case today, but a label is
// external input and a capitalisation change must not silently become Unknown.
bool equalsIgnoreCase(const char* a, const char* b) {
    while (*a != '\0' && *b != '\0') {
        char ca = *a;
        char cb = *b;
        if (ca >= 'A' && ca <= 'Z') {
            ca = static_cast<char>(ca - 'A' + 'a');
        }
        if (cb >= 'A' && cb <= 'Z') {
            cb = static_cast<char>(cb - 'A' + 'a');
        }
        if (ca != cb) {
            return false;
        }
        ++a;
        ++b;
    }
    return *a == *b;
}

}  // namespace

WasteClass wasteClassFromLabel(const char* label) {
    if (label == nullptr || label[0] == '\0') {
        return WasteClass::Unknown;
    }
    if (equalsIgnoreCase(label, "plastic")) {
        return WasteClass::Plastic;
    }
    if (equalsIgnoreCase(label, "paper") || equalsIgnoreCase(label, "cardboard")) {
        return WasteClass::Paper;
    }
    if (equalsIgnoreCase(label, "metal") || equalsIgnoreCase(label, "can")) {
        return WasteClass::Metal;
    }
    return WasteClass::Unknown;
}

const char* wasteClassName(WasteClass waste) {
    switch (waste) {
        case WasteClass::Plastic:
            return "plastic";
        case WasteClass::Paper:
            return "paper";
        case WasteClass::Metal:
            return "metal";
        case WasteClass::Unknown:
        default:
            return "unknown";
    }
}

const char* binTargetName(BinTarget target) {
    switch (target) {
        case BinTarget::Plastic:
            return "PLASTIC";
        case BinTarget::Paper:
            return "PAPER";
        case BinTarget::Metal:
            return "METAL";
        case BinTarget::Home:
        default:
            return "HOME";
    }
}

const char* sortActionName(SortAction action) {
    return action == SortAction::Sort ? "SORT" : "REJECT";
}

BinTarget binTargetFor(WasteClass waste) {
    switch (waste) {
        case WasteClass::Plastic:
            return BinTarget::Plastic;
        case WasteClass::Paper:
            return BinTarget::Paper;
        case WasteClass::Metal:
            return BinTarget::Metal;
        case WasteClass::Unknown:
        default:
            // No bin for an item we cannot name. HOME is the "not sorted"
            // position, never a guess (§16, §24).
            return BinTarget::Home;
    }
}

}  // namespace greenbin
