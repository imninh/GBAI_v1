// Desktop implementations of the five hardware interfaces.
//
// Sensors are scripted, the camera reads a real JPEG from disk, and the LED
// prints. The network implementation is the interesting one — it is NOT a fake:
// it builds the same multipart body as the firmware and posts it over a real
// socket (see sim_network.h).
//
// SIMULATOR ONLY.
#pragma once

#include <stdio.h>

#include <string>
#include <vector>

#include "core/hal.h"

namespace greenbin {
namespace sim {

class ScriptedPresenceSensor : public PresenceSensor {
  public:
    bool motion = false;
    bool motionDetected() override { return motion; }
};

class ScriptedDistanceSensor : public DistanceSensor {
  public:
    DistanceReading next{true, 50.0f};
    int reads = 0;

    void set(float cm) { next = DistanceReading(true, cm); }
    void setInvalid() { next = DistanceReading(); }

    DistanceReading read() override {
        ++reads;
        return next;
    }
};

// Serves a real JPEG from disk so the backend's validation, EXIF stripping,
// resize and pHash all run against genuine image data.
class FileCameraService : public CameraService {
  public:
    explicit FileCameraService(std::string path) : path_(std::move(path)) {}

    bool initialize() override {
        FILE* file = fopen(path_.c_str(), "rb");
        if (file == nullptr) {
            printf("[CAMERA] cannot open fixture: %s\n", path_.c_str());
            return false;
        }
        fseek(file, 0, SEEK_END);
        const long size = ftell(file);
        fseek(file, 0, SEEK_SET);
        bytes_.resize(static_cast<size_t>(size));
        const size_t read = fread(bytes_.data(), 1, bytes_.size(), file);
        fclose(file);
        if (read != bytes_.size()) {
            printf("[CAMERA] short read on fixture\n");
            return false;
        }
        printf("[CAMERA] fixture loaded bytes=%zu\n", bytes_.size());
        return true;
    }

    CameraFrame captureJpeg() override {
        CameraFrame frame;
        if (bytes_.empty()) {
            return frame;
        }
        frame.data = bytes_.data();
        frame.length = bytes_.size();
        frame.valid = true;
        held_ = true;
        return frame;
    }

    void releaseFrame() override { held_ = false; }

    bool isHolding() const { return held_; }
    int captures() const { return captures_; }

  private:
    std::string path_;
    std::vector<uint8_t> bytes_;
    bool held_ = false;
    int captures_ = 0;
};

class ConsoleLedService : public LedService {
  public:
    LedPattern background = LedPattern::Off;
    LedPattern lastTemporary = LedPattern::Off;

    void setBackground(LedPattern pattern) override {
        if (pattern != background) {
            background = pattern;
            printf("[LED] background=%s\n", name(pattern));
        }
    }

    void showTemporary(LedPattern pattern, uint32_t) override {
        if (pattern != lastTemporary) {
            lastTemporary = pattern;
            printf("[LED] %s\n", name(pattern));
        }
    }

    void tick(uint32_t) override {}

    static const char* name(LedPattern pattern) {
        switch (pattern) {
            case LedPattern::Off: return "OFF";
            case LedPattern::Idle: return "IDLE";
            case LedPattern::Booting: return "BOOTING";
            case LedPattern::WifiConnecting: return "WIFI_CONNECTING";
            case LedPattern::Processing: return "PROCESSING";
            case LedPattern::Ok: return "OK";
            case LedPattern::Warning: return "WARNING";
            case LedPattern::Hazard: return "HAZARD";
            case LedPattern::NetworkError: return "NETWORK_ERROR";
            case LedPattern::BinFull: return "BIN_FULL";
            default: return "?";
        }
    }
};

// Prints every commanded position, so the simulator transcript shows the flap
// path — including the return to HOME — without any hardware attached.
class ConsoleSorter : public SorterService {
  public:
    BinTarget last = BinTarget::Home;
    int moves = 0;

    bool moveTo(BinTarget target) override {
        ++moves;
        last = target;
        printf("[SERVO] target=%s\n", binTargetName(target));
        return true;
    }
    BinTarget position() const override { return last; }
};

// Prints what the OLED would show. Same call sequence the real panel receives.
class ConsoleDisplay : public DisplayService {
  public:
    void showBoot(const char* version) override { printf("[OLED] Booting %s\n", version); }
    void showIdle(bool binFull) override {
        printf("[OLED] %s\n", binFull ? "BIN FULL" : "Ready");
    }
    void showUserDetected() override { printf("[OLED] User detected\n"); }
    void showCapturing() override { printf("[OLED] Capturing...\n"); }
    void showAnalyzing() override { printf("[OLED] Analyzing...\n"); }
    void showSorting(BinTarget target) override {
        printf("[OLED] %s / Sorting...\n", binTargetName(target));
    }
    void showRejected(const char* reason) override {
        printf("[OLED] NOT SORTED / %s\n", reason);
    }
    void showComplete(WasteClass waste, bool sorted, bool fillValid, float fillPercent) override {
        if (fillValid) {
            printf("[OLED] %s %s / Fill: %.0f%%\n", wasteClassName(waste),
                   sorted ? "accepted" : "NOT sorted", static_cast<double>(fillPercent));
        } else {
            printf("[OLED] %s %s / Fill: unavailable\n", wasteClassName(waste),
                   sorted ? "accepted" : "NOT sorted");
        }
    }
    void showError(const char* message) override { printf("[OLED] ERROR / %s\n", message); }
};

}  // namespace sim
}  // namespace greenbin
