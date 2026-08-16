#include "hw/led_service.h"

#include "config.h"

namespace greenbin {

namespace {

struct PatternSpec {
    uint8_t r, g, b;
    uint32_t durationMs;  // 0 = persistent (background patterns)
    uint32_t blinkPeriodMs;  // 0 = solid
};

// The single source of truth for what every state looks like (spec §12).
// Blinking = transient classification feedback. Solid = persistent device state.
PatternSpec specFor(LedPattern pattern) {
    switch (pattern) {
        case LedPattern::Idle:
            // Low-brightness green: "alive, waiting". Dimmed further by the
            // global brightness cap.
            return {0, 24, 0, 0, 0};
        case LedPattern::Booting:
            return {40, 0, 40, 1000, 0};
        case LedPattern::WifiConnecting:
            return {0, 0, 255, 0, 600};
        case LedPattern::Processing:
            return {0, 0, 255, 0, 0};
        case LedPattern::Ok:
            return {0, 255, 0, LED_OK_MS, 0};
        case LedPattern::Warning:
            return {255, 0, 0, LED_WARNING_BLINKS * LED_WARNING_PERIOD_MS,
                    LED_WARNING_PERIOD_MS};
        case LedPattern::Hazard:
            return {255, 0, 0, LED_HAZARD_MS, LED_HAZARD_PERIOD_MS};
        case LedPattern::NetworkError:
            return {255, 140, 0, LED_NET_ERROR_MS, 0};
        case LedPattern::BinFull:
            return {255, 0, 0, 0, 0};  // solid, persistent
        case LedPattern::Off:
        default:
            return {0, 0, 0, 0, 0};
    }
}

}  // namespace

Ws2812LedService::Ws2812LedService(uint8_t pin, uint16_t count, uint8_t maxBrightness)
    : strip_(count, pin, NEO_GRB + NEO_KHZ800), maxBrightness_(maxBrightness) {}

void Ws2812LedService::begin() {
    strip_.begin();
    // Brightness cap is a power decision, not an aesthetic one: the pixel must
    // never compete with the Wi-Fi radio for current (pin-map.md §5.4).
    strip_.setBrightness(maxBrightness_);
    strip_.clear();
    strip_.show();
}

void Ws2812LedService::setBackground(LedPattern pattern) { background_ = pattern; }

void Ws2812LedService::showTemporary(LedPattern pattern, uint32_t nowMs) {
    const PatternSpec spec = specFor(pattern);
    if (spec.durationMs == 0) {
        // A persistent pattern asked for as a temporary one: show it until
        // something else replaces it (used for Booting/WifiConnecting).
        temporary_ = pattern;
        temporaryActive_ = true;
        temporaryStartMs_ = nowMs;
        temporaryDurationMs_ = 0;
        return;
    }
    // Re-showing the pattern already running must not restart it every loop.
    if (temporaryActive_ && temporary_ == pattern) {
        return;
    }
    temporary_ = pattern;
    temporaryActive_ = true;
    temporaryStartMs_ = nowMs;
    temporaryDurationMs_ = spec.durationMs;
}

void Ws2812LedService::tick(uint32_t nowMs) {
    if (temporaryActive_ && temporaryDurationMs_ > 0 &&
        (nowMs - temporaryStartMs_) >= temporaryDurationMs_) {
        // Expired: fall back to whatever the device's background state is —
        // which is BinFull if the bin is still full (spec §12).
        temporaryActive_ = false;
    }

    const LedPattern active = temporaryActive_ ? temporary_ : background_;
    const uint32_t elapsed = temporaryActive_ ? (nowMs - temporaryStartMs_) : nowMs;
    render(active, elapsed);
}

void Ws2812LedService::render(LedPattern pattern, uint32_t elapsedMs) {
    const PatternSpec spec = specFor(pattern);

    bool on = true;
    if (spec.blinkPeriodMs > 0) {
        on = ((elapsedMs / (spec.blinkPeriodMs / 2)) % 2) == 0;
    }

    // Only touch the bus when something actually changed; WS2812 updates are
    // interrupt-sensitive and pointless writes cost time.
    if (pattern == lastRendered_ && on == lastOn_) {
        return;
    }
    lastRendered_ = pattern;
    lastOn_ = on;

    if (on) {
        strip_.setPixelColor(0, strip_.Color(spec.r, spec.g, spec.b));
    } else {
        strip_.setPixelColor(0, 0);
    }
    strip_.show();
}

}  // namespace greenbin
