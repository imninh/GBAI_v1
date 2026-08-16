#include "hw/oled_display.h"

#include <Wire.h>
#include <stdio.h>
#include <string.h>

#include "config.h"
#include "core/logging.h"

namespace greenbin {

namespace {

// At text size 2 a character is 12 px wide, so 10 characters is the most that
// fits across a 128 px panel. Longer headlines drop to size 1 rather than being
// silently cut off mid-word.
constexpr size_t kMaxLargeChars = 10;

const char* wasteHeadline(WasteClass waste) {
    switch (waste) {
        case WasteClass::Plastic:
            return "PLASTIC";
        case WasteClass::Paper:
            return "PAPER";
        case WasteClass::Metal:
            return "METAL";
        case WasteClass::Unknown:
        default:
            return "UNKNOWN";
    }
}

}  // namespace

OledDisplay::OledDisplay(uint8_t sdaPin, uint8_t sclPin, uint8_t i2cAddress, uint32_t i2cFrequency)
    : panel_(OLED_WIDTH, OLED_HEIGHT, &Wire, -1),
      sdaPin_(sdaPin),
      sclPin_(sclPin),
      address_(i2cAddress),
      frequency_(i2cFrequency) {}

bool OledDisplay::begin() {
    Wire.begin(sdaPin_, sclPin_, frequency_);
    ready_ = panel_.begin(SSD1306_SWITCHCAPVCC, address_);
    if (!ready_) {
        GB_LOG("OLED", "not found at 0x%02X", address_);
        return false;
    }
    panel_.setTextColor(SSD1306_WHITE);
    panel_.clearDisplay();
    panel_.display();
    GB_LOG("OLED", "ready %dx%d addr=0x%02X", OLED_WIDTH, OLED_HEIGHT, address_);
    return true;
}

void OledDisplay::draw(const char* header,
                       const char* headline,
                       const char* line1,
                       const char* line2) {
    if (!ready_) {
        return;
    }

    panel_.clearDisplay();

    if (header != nullptr) {
        panel_.setTextSize(1);
        panel_.setCursor(0, 0);
        panel_.print(header);
        panel_.drawFastHLine(0, 11, OLED_WIDTH, SSD1306_WHITE);
    }

    if (headline != nullptr) {
        const bool large = strlen(headline) <= kMaxLargeChars;
        panel_.setTextSize(large ? 2 : 1);
        panel_.setCursor(0, large ? 20 : 24);
        panel_.print(headline);
    }

    panel_.setTextSize(1);
    if (line1 != nullptr) {
        panel_.setCursor(0, 44);
        panel_.print(line1);
    }
    if (line2 != nullptr) {
        panel_.setCursor(0, 55);
        panel_.print(line2);
    }

    panel_.display();
}

void OledDisplay::showBoot(const char* version) {
    draw("GreenBinAI", "Booting", version, nullptr);
}

void OledDisplay::showIdle(bool binFull) {
    if (binFull) {
        // The bin being full is the most important thing a passer-by can know,
        // so it replaces "Ready" rather than sitting underneath it.
        draw("GreenBinAI", "BIN FULL", "Please use another bin", nullptr);
        return;
    }
    draw("GreenBinAI", "Ready", "Insert an item", nullptr);
}

void OledDisplay::showUserDetected() {
    draw("GreenBinAI", "Hello!", "User detected", nullptr);
}

void OledDisplay::showCapturing() {
    draw("GreenBinAI", "Capturing", "Hold still...", nullptr);
}

void OledDisplay::showAnalyzing() {
    draw("GreenBinAI", "Analyzing", "Classifying item...", nullptr);
}

void OledDisplay::showSorting(BinTarget target) {
    draw("GreenBinAI", binTargetName(target), "Sorting...", nullptr);
}

void OledDisplay::showRejected(const char* reason) {
    draw("GreenBinAI", "NOT SORTED", reason, "Please retry");
}

void OledDisplay::showComplete(WasteClass waste,
                               bool sorted,
                               bool fillValid,
                               float fillPercent) {
    char fillLine[24];
    if (fillValid) {
        snprintf(fillLine, sizeof(fillLine), "Fill: %d%%", static_cast<int>(fillPercent + 0.5f));
    } else {
        // No number is shown when the sensor failed. A fabricated fill level is
        // worse than an honest gap (§24).
        snprintf(fillLine, sizeof(fillLine), "Fill: unavailable");
    }
    draw("GreenBinAI",
         sorted ? wasteHeadline(waste) : "NOT SORTED",
         sorted ? "Accepted" : "Returned to user",
         fillLine);
}

void OledDisplay::showError(const char* message) {
    draw("GreenBinAI", "ERROR", message, "Please retry");
}

void OledDisplay::showRaw(const char* header,
                          const char* headline,
                          const char* line1,
                          const char* line2) {
    draw(header, headline, line1, line2);
}

}  // namespace greenbin
