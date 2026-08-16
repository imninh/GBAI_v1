#include "hw/camera_service.h"

#include <esp_camera.h>

#include "config.h"
#include "core/logging.h"

namespace greenbin {

namespace {

// CAMERA_MODEL_AI_THINKER pin assignment. Reproduced explicitly rather than
// pulled from a board header so that the 15 GPIOs the camera consumes are
// visible in this repository and auditable against iot/docs/pin-map.md §1.
constexpr int kPwdnPin = 32;
constexpr int kResetPin = -1;  // tied to module reset, no GPIO used
constexpr int kXclkPin = 0;
constexpr int kSiodPin = 26;
constexpr int kSiocPin = 27;
constexpr int kY9Pin = 35;
constexpr int kY8Pin = 34;
constexpr int kY7Pin = 39;
constexpr int kY6Pin = 36;
constexpr int kY5Pin = 21;
constexpr int kY4Pin = 19;
constexpr int kY3Pin = 18;
constexpr int kY2Pin = 5;
constexpr int kVsyncPin = 25;
constexpr int kHrefPin = 23;
constexpr int kPclkPin = 22;

}  // namespace

Ov2640CameraService::Ov2640CameraService(uint8_t maxInitAttempts)
    : maxInitAttempts_(maxInitAttempts == 0 ? 1 : maxInitAttempts) {}

bool Ov2640CameraService::initialize() {
    if (initialized_) {
        return true;
    }

    camera_config_t config = {};
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = kY2Pin;
    config.pin_d1 = kY3Pin;
    config.pin_d2 = kY4Pin;
    config.pin_d3 = kY5Pin;
    config.pin_d4 = kY6Pin;
    config.pin_d5 = kY7Pin;
    config.pin_d6 = kY8Pin;
    config.pin_d7 = kY9Pin;
    config.pin_xclk = kXclkPin;
    config.pin_pclk = kPclkPin;
    config.pin_vsync = kVsyncPin;
    config.pin_href = kHrefPin;
    config.pin_sccb_sda = kSiodPin;
    config.pin_sccb_scl = kSiocPin;
    config.pin_pwdn = kPwdnPin;
    config.pin_reset = kResetPin;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;  // never raw RGB (spec §7)
    config.frame_size = CAMERA_FRAMESIZE;
    config.jpeg_quality = CAMERA_JPEG_QUALITY;
    config.fb_count = 1;
    config.grab_mode = CAMERA_GRAB_LATEST;

    if (psramFound()) {
        config.fb_location = CAMERA_FB_IN_PSRAM;
    } else {
        // Without PSRAM the framebuffer must fit in internal RAM, so drop the
        // frame size rather than failing outright.
        GB_LOG_PLAIN("CAMERA", "no PSRAM; falling back to smaller frame");
        config.fb_location = CAMERA_FB_IN_DRAM;
        config.frame_size = FRAMESIZE_QVGA;
        config.jpeg_quality = 15;
    }

    for (uint8_t attempt = 1; attempt <= maxInitAttempts_; ++attempt) {
        const esp_err_t err = esp_camera_init(&config);
        if (err == ESP_OK) {
            initialized_ = true;
            GB_LOG("CAMERA", "init ok psram=%d", psramFound() ? 1 : 0);
            return true;
        }
        GB_LOG("CAMERA", "init attempt %u failed err=0x%x", static_cast<unsigned>(attempt),
               static_cast<unsigned>(err));
        // De-init before retrying, otherwise the driver keeps half-claimed
        // resources and every retry fails the same way.
        esp_camera_deinit();
        delay(500);
    }

    // Bounded: we do NOT reboot and we do NOT loop forever (spec §7).
    return false;
}

CameraFrame Ov2640CameraService::captureJpeg() {
    CameraFrame frame;
    if (!initialized_) {
        return frame;
    }
    // A buffer still held from a previous capture would leak; take it back first.
    releaseFrame();

    camera_fb_t* fb = esp_camera_fb_get();
    if (fb == nullptr) {
        GB_LOG_PLAIN("CAMERA", "fb_get returned null");
        return frame;
    }
    if (fb->format != PIXFORMAT_JPEG || fb->len == 0) {
        GB_LOG_PLAIN("CAMERA", "frame is not usable JPEG");
        esp_camera_fb_return(fb);
        return frame;
    }

    frameBuffer_ = fb;
    frame.data = fb->buf;
    frame.length = fb->len;
    frame.valid = true;
    return frame;
}

void Ov2640CameraService::releaseFrame() {
    if (frameBuffer_ != nullptr) {
        esp_camera_fb_return(static_cast<camera_fb_t*>(frameBuffer_));
        frameBuffer_ = nullptr;
    }
}

}  // namespace greenbin
