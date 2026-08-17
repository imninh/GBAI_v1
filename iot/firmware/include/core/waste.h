// Waste material classes and the physical bin they map to (Checkpoint 1 §9, §16).
//
// Pure logic: no Arduino, no HTTP. The backend speaks in label strings
// ("plastic", "paper", "metal"); the sorter speaks in angles. This module is the
// single translation layer between the two, so no business logic anywhere else
// ever mentions an angle or parses a label.
#pragma once

#include <stdint.h>

namespace greenbin {

enum class WasteClass {
    Plastic,
    Paper,
    Metal,
    Unknown,
};

// The physical positions the sorting flap can hold. HOME is the rest position
// the flap must return to after every transaction (§24).
enum class BinTarget {
    Home,
    Plastic,
    Paper,
    Metal,
};

// What the device is allowed to do with an item. REJECT means "do not sort":
// the flap stays HOME and the item is not directed anywhere (§16, §24).
enum class SortAction {
    Sort,
    Reject,
};

// Maps a backend label to a material. Unrecognised, empty or null labels become
// Unknown — never silently coerced into a real material, because that would put
// an unidentified item into a recycling stream.
WasteClass wasteClassFromLabel(const char* label);

// Lower-case, matching the backend's own vocabulary, so the same names appear in
// the firmware log and the API payload.
const char* wasteClassName(WasteClass waste);

// Upper-case, for OLED headlines and the [SERVO] log.
const char* binTargetName(BinTarget target);

const char* sortActionName(SortAction action);

// Unknown has no bin: it maps to Home, which is the "did not sort" position.
BinTarget binTargetFor(WasteClass waste);

}  // namespace greenbin
