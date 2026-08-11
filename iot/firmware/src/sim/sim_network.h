// A real NetworkService for the desktop simulator.
//
// This is the point of the whole simulator: it builds the SAME multipart body
// and the SAME headers as src/hw/network_service.cpp and posts them to the real
// FastAPI backend. If the device/backend contract is wrong, this fails.
//
// SIMULATOR ONLY.
#pragma once

#include <string>

#include "core/classification.h"
#include "core/hal.h"

namespace greenbin {
namespace sim {

class SimNetworkService : public NetworkService {
  public:
    SimNetworkService(std::string baseUrl,
                      std::string deviceId,
                      std::string binCode,
                      std::string deviceKey,
                      uint32_t timeoutMs);

    void beginConnect() override;
    bool isConnected() override;

    UploadOutcome uploadCapture(const CameraFrame& frame,
                                float fillPercent,
                                bool fillValid,
                                uint32_t uptimeSeconds,
                                ClassificationResult& out) override;

    NetResult sendBinReading(float fillPercent, bool isFull, uint32_t uptimeSeconds) override;

    int uploads = 0;
    int readings = 0;
    int lastHttpStatus = 0;
    std::string lastBody;

  private:
    std::string baseUrl_;
    std::string deviceId_;
    std::string binCode_;
    std::string deviceKey_;
    uint32_t timeoutMs_;
    bool connected_ = false;
};

}  // namespace sim
}  // namespace greenbin
