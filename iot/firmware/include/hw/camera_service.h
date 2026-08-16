// OV2640 camera driver wrapper (spec §7).
//
// Camera logic is deliberately not coupled to HTTP: this class knows how to
// produce a JPEG and how to give the buffer back, nothing more. The state
// machine decides when, and NetworkService decides where it goes.
#pragma once

#include <Arduino.h>

#include "core/hal.h"

namespace greenbin {

class Ov2640CameraService : public CameraService {
  public:
    explicit Ov2640CameraService(uint8_t maxInitAttempts);

    bool initialize() override;
    CameraFrame captureJpeg() override;
    void releaseFrame() override;

    bool isReady() const { return initialized_; }

  private:
    uint8_t maxInitAttempts_;
    bool initialized_ = false;
    void* frameBuffer_ = nullptr;  // camera_fb_t*, kept opaque to avoid leaking
                                   // esp_camera.h into every translation unit
};

}  // namespace greenbin
