// Camera whose sensor lives on the host PC (simulation only).
//
// Wokwi does not simulate the OV2640, but a demo that classifies real objects
// needs a real image. This driver fetches one JPEG over HTTP from
// `iot/simulation/webcam_service.py` and presents it as a CameraFrame, so from
// the state machine's point of view it is indistinguishable from the on-board
// sensor: the device still holds the bytes in its own RAM and still uploads
// them itself.
//
// It implements the same CameraService interface as the OV2640 driver and the
// fixture mock, so swapping between the three is a build flag and nothing else.
//
// NOT FOR THE REAL BIN. On hardware the camera is Ov2640CameraService; this
// class exists so the classification path can be demonstrated end to end before
// that hardware is available.
#pragma once

#include <Arduino.h>

#include "core/hal.h"

namespace greenbin {

class HostCameraService : public CameraService {
  public:
    HostCameraService(const char* url, size_t maxBytes, uint32_t timeoutMs);
    ~HostCameraService() override;

    // Probes the service so a missing webcam is reported at boot rather than in
    // the middle of the first transaction.
    bool initialize() override;

    CameraFrame captureJpeg() override;
    void releaseFrame() override;

  private:
    const char* url_;
    size_t maxBytes_;
    uint32_t timeoutMs_;

    uint8_t* buffer_ = nullptr;
    size_t length_ = 0;
};

}  // namespace greenbin
