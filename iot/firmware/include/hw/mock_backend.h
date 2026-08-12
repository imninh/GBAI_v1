// Offline stand-in for the GreenBin backend (Checkpoint 1 §16, §25).
//
// It implements NetworkService, the same interface the real Wi-Fi client
// implements, so the state machine cannot tell the difference and none of the
// flow code changes when the real backend arrives. What it returns is exactly
// the contract of §25:
//
//     { "transaction_id": "TX-001", "status": "ok", "label": "plastic",
//       "confidence": 0.93, "action": "SORT", "target_bin": "PLASTIC" }
//
// `action` and `target_bin` are deliberately NOT set here: resolveSorting() in
// core/classification.cpp derives them, so the mock and the real HTTP response
// are forced through the same decision logic.
//
// THIS IS NOT AN AI. It returns whatever class the Serial test console last
// selected. Every log line it emits is tagged [AI MOCK] so no one can mistake a
// simulated result for a real classification.
#pragma once

#include <Arduino.h>
#include <stdio.h>
#include <string.h>

#include "core/classification.h"
#include "core/hal.h"
#include "core/logging.h"

namespace greenbin {

class MockBackendService : public NetworkService {
  public:
    // Simulated round-trip time. Without it the "Analyzing..." screen would be
    // replaced within one 10 ms loop and the demo would be unreadable.
    explicit MockBackendService(uint32_t latencyMs = 600) : latencyMs_(latencyMs) {}

    // Chooses what the next classification will return. Driven from the Serial
    // test console (commands p / a / m / u).
    void setNextClass(WasteClass waste) { next_ = waste; }
    WasteClass nextClass() const { return next_; }

    // Forces the next upload to fail, so the retry/ERROR path can be exercised
    // on demand instead of only when something genuinely breaks.
    void setNextUploadResult(NetResult result) { forcedResult_ = result; }

    void beginConnect() override {
        connected_ = true;
        GB_LOG_PLAIN("AI MOCK", "offline backend attached — no network in use");
    }

    bool isConnected() override { return connected_; }

    UploadOutcome uploadCapture(const CameraFrame& frame,
                                float fillPercent,
                                bool fillValid,
                                uint32_t uptimeSeconds,
                                ClassificationResult& out) override {
        (void)uptimeSeconds;
        UploadOutcome outcome;

        if (!frame.valid || frame.data == nullptr || frame.length == 0) {
            // The same guard the real client applies: never post an empty body.
            outcome.result = NetResult::HttpError;
            return outcome;
        }

        GB_LOG("AI MOCK", "upload bytes=%u fill=%s%.1f",
               static_cast<unsigned>(frame.length), fillValid ? "" : "invalid:",
               static_cast<double>(fillPercent));

        delay(latencyMs_);  // simulated backend round-trip

        if (forcedResult_ != NetResult::Ok) {
            outcome.result = forcedResult_;
            outcome.httpStatus = 0;
            forcedResult_ = NetResult::Ok;  // one-shot
            GB_LOG("AI MOCK", "forced failure result=%d", static_cast<int>(outcome.result));
            return outcome;
        }

        outcome.result = NetResult::Ok;
        outcome.httpStatus = 200;
        fill(out);

        GB_LOG("AI MOCK", "transaction=%s status=%s label=%s confidence=%.2f",
               out.transactionId, statusName(out.status),
               out.label[0] != '\0' ? out.label : "null",
               static_cast<double>(out.confidence));
        return outcome;
    }

    NetResult sendBinReading(float fillPercent, bool isFull, uint32_t uptimeSeconds) override {
        (void)uptimeSeconds;
        // Tagged API MOCK, not AI MOCK: this is the fill-level endpoint, and a
        // log reader must be able to tell the two apart at a glance.
        GB_LOG("API MOCK", "bin reading accepted fill=%.1f full=%d",
               static_cast<double>(fillPercent), isFull ? 1 : 0);
        return NetResult::Ok;
    }

  private:
    void fill(ClassificationResult& out) {
        snprintf(out.transactionId, sizeof(out.transactionId), "TX-%03u",
                 static_cast<unsigned>(++transactionCount_));

        switch (next_) {
            case WasteClass::Plastic:
                set(out, ClassificationStatus::Ok, "plastic", 0.93f);
                break;
            case WasteClass::Paper:
                set(out, ClassificationStatus::Ok, "paper", 0.88f);
                break;
            case WasteClass::Metal:
                set(out, ClassificationStatus::Ok, "metal", 0.91f);
                break;
            case WasteClass::Unknown:
            default:
                // Mirrors the §25 "uncertain" response: no label, low
                // confidence. parseStatus() maps "uncertain" to Unknown, and
                // resolveSorting() therefore refuses to sort it.
                set(out, ClassificationStatus::Unknown, "", 0.46f);
                break;
        }
    }

    static void set(ClassificationResult& out,
                    ClassificationStatus status,
                    const char* label,
                    float confidence) {
        out.status = status;
        out.confidence = confidence;
        strncpy(out.label, label, sizeof(out.label) - 1);
        out.label[sizeof(out.label) - 1] = '\0';
    }

    uint32_t latencyMs_;
    WasteClass next_ = WasteClass::Plastic;
    NetResult forcedResult_ = NetResult::Ok;
    bool connected_ = false;
    uint32_t transactionCount_ = 0;
};

}  // namespace greenbin
