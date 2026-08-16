// Wi-Fi + HTTP client (spec §8, §15).
//
// The device holds only a Wi-Fi credential, a backend URL, an identifier and a
// device key. It never holds a Vision provider key and never calls a model
// provider directly — everything goes to the GreenBin backend (spec §8, §26).
#pragma once

#include <Arduino.h>

#include "core/classification.h"
#include "core/hal.h"

namespace greenbin {

class EspNetworkService : public NetworkService {
  public:
    EspNetworkService(const char* ssid,
                      const char* password,
                      const char* baseUrl,
                      const char* deviceId,
                      const char* binCode,
                      const char* deviceKey,
                      uint32_t timeoutMs);

    void beginConnect() override;
    bool isConnected() override;

    UploadOutcome uploadCapture(const CameraFrame& frame,
                                float fillPercent,
                                bool fillValid,
                                uint32_t uptimeSeconds,
                                ClassificationResult& out) override;

    NetResult sendBinReading(float fillPercent, bool isFull, uint32_t uptimeSeconds) override;

  private:
    NetResult mapHttpCode(int code) const;
    bool parseClassification(const String& payload, ClassificationResult& out) const;

    const char* ssid_;
    const char* password_;
    const char* baseUrl_;
    const char* deviceId_;
    const char* binCode_;
    const char* deviceKey_;
    uint32_t timeoutMs_;
};

}  // namespace greenbin
