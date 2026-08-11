// Hardware abstraction interfaces.
//
// The state machine depends on these and never on a driver (spec §18). That is
// what allows scenarios 1 and 3–6 to run as native unit tests with fake
// implementations, and what would confine a future ESP32-S3 port to src/hw/.
//
// This header must stay free of Arduino.h.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace greenbin {

// ─── Distance ────────────────────────────────────────────────────────────────

// A reading that failed (echo timeout, out-of-range) reports valid=false rather
// than a sentinel number, so no bogus fill value can ever be derived (spec §19
// scenario 9).
struct DistanceReading {
    bool valid = false;
    float cm = 0.0f;

    // Explicit constructors rather than aggregate initialisation: the ESP32
    // Arduino core compiles at C++11, where a struct with default member
    // initialisers is not an aggregate and `DistanceReading{true, 5.0f}` fails.
    DistanceReading() = default;
    DistanceReading(bool isValid, float centimetres) : valid(isValid), cm(centimetres) {}
};

class DistanceSensor {
  public:
    virtual ~DistanceSensor() = default;
    virtual DistanceReading read() = 0;
};

// ─── Presence ────────────────────────────────────────────────────────────────

class PresenceSensor {
  public:
    virtual ~PresenceSensor() = default;
    // True while motion is asserted. Edge detection is the state machine's job.
    virtual bool motionDetected() = 0;
};

// ─── Camera ──────────────────────────────────────────────────────────────────

// Non-owning view of the driver's frame buffer. The buffer stays valid only
// until releaseFrame(); callers must not hold on to it (spec §7).
struct CameraFrame {
    const uint8_t* data = nullptr;
    size_t length = 0;
    bool valid = false;
};

class CameraService {
  public:
    virtual ~CameraService() = default;
    virtual bool initialize() = 0;
    virtual CameraFrame captureJpeg() = 0;
    virtual void releaseFrame() = 0;
};

// ─── Network ─────────────────────────────────────────────────────────────────

enum class NetResult {
    Ok,
    NoNetwork,
    Timeout,
    HttpError,
    ParseError,
    Unauthorized,
};

// Forward-declared; defined in classification.h.
struct ClassificationResult;

struct UploadOutcome {
    NetResult result = NetResult::NoNetwork;
    int httpStatus = 0;
};

class NetworkService {
  public:
    virtual ~NetworkService() = default;

    // Non-blocking: kicks off association and returns immediately. The state
    // machine polls isConnected() rather than blocking on a join, so a missing
    // access point can never freeze the device (spec §15).
    virtual void beginConnect() = 0;
    virtual bool isConnected() = 0;

    // Uploads the JPEG as multipart/form-data and parses the classification
    // response into `out`. `out` is only meaningful when the result is Ok.
    virtual UploadOutcome uploadCapture(const CameraFrame& frame,
                                        float fillPercent,
                                        bool fillValid,
                                        uint32_t uptimeSeconds,
                                        ClassificationResult& out) = 0;

    virtual NetResult sendBinReading(float fillPercent,
                                     bool isFull,
                                     uint32_t uptimeSeconds) = 0;
};

// ─── LED ─────────────────────────────────────────────────────────────────────

enum class LedPattern {
    Off,
    Idle,
    Booting,
    WifiConnecting,
    Processing,
    Ok,
    Warning,
    Hazard,
    NetworkError,
    BinFull,
};

class LedService {
  public:
    virtual ~LedService() = default;

    // The persistent state the device falls back to: Idle normally, BinFull
    // while the bin is full. Bin fullness is a background state and must not
    // interrupt the classification workflow (spec §16).
    virtual void setBackground(LedPattern pattern) = 0;

    // A time-boxed pattern that plays over the background and then expires.
    virtual void showTemporary(LedPattern pattern, uint32_t nowMs) = 0;

    // Drives blinking and expiry. Must be called every loop.
    virtual void tick(uint32_t nowMs) = 0;
};

}  // namespace greenbin
