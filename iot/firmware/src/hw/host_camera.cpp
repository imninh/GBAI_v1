#include "hw/host_camera.h"

#include <HTTPClient.h>
#include <WiFi.h>

#include "core/logging.h"

namespace greenbin {

HostCameraService::HostCameraService(const char* url, size_t maxBytes, uint32_t timeoutMs)
    : url_(url), maxBytes_(maxBytes), timeoutMs_(timeoutMs) {}

HostCameraService::~HostCameraService() { releaseFrame(); }

bool HostCameraService::initialize() {
    GB_LOG("CAMERA", "host webcam at %s — NOT an on-board sensor", url_);

    if (WiFi.status() != WL_CONNECTED) {
        // Not fatal: Wi-Fi may still be associating at boot. Say so rather than
        // reporting a camera that has never been reached as working.
        GB_LOG_PLAIN("CAMERA", "no network yet; webcam not probed");
        return true;
    }

    HTTPClient http;
    http.setTimeout(timeoutMs_);
    http.setConnectTimeout(timeoutMs_);
    http.setReuse(false);
    if (!http.begin(url_)) {
        GB_LOG_PLAIN("CAMERA", "bad webcam URL");
        return false;
    }
    const int code = http.GET();
    http.end();

    if (code != HTTP_CODE_OK) {
        GB_LOG("CAMERA", "webcam probe failed code=%d", code);
        return false;
    }
    GB_LOG_PLAIN("CAMERA", "webcam reachable");
    return true;
}

CameraFrame HostCameraService::captureJpeg() {
    CameraFrame frame;
    releaseFrame();  // a previous frame must never outlive its capture

    HTTPClient http;
    http.setTimeout(timeoutMs_);
    http.setConnectTimeout(timeoutMs_);
    http.setReuse(false);
    if (!http.begin(url_)) {
        GB_LOG_PLAIN("CAMERA", "cannot open webcam connection");
        return frame;
    }

    const int code = http.GET();
    if (code != HTTP_CODE_OK) {
        // 503 from the service means the webcam itself failed. Either way this
        // is a capture failure and the state machine will refuse to sort.
        GB_LOG("CAMERA", "webcam returned code=%d", code);
        http.end();
        return frame;
    }

    const int contentLength = http.getSize();
    if (contentLength <= 0) {
        // The service always sends Content-Length; without it we cannot size a
        // buffer, and guessing risks exhausting the heap.
        GB_LOG("CAMERA", "webcam sent no usable Content-Length (%d)", contentLength);
        http.end();
        return frame;
    }
    if (static_cast<size_t>(contentLength) > maxBytes_) {
        GB_LOG("CAMERA", "frame %d bytes exceeds limit %u; lower the webcam quality",
               contentLength, static_cast<unsigned>(maxBytes_));
        http.end();
        return frame;
    }

    uint8_t* buffer = static_cast<uint8_t*>(malloc(static_cast<size_t>(contentLength)));
    if (buffer == nullptr) {
        GB_LOG("CAMERA", "cannot allocate %d bytes (free heap %u)", contentLength,
               static_cast<unsigned>(ESP.getFreeHeap()));
        http.end();
        return frame;
    }

    WiFiClient* stream = http.getStreamPtr();
    size_t received = 0;
    const uint32_t deadline = millis() + timeoutMs_;
    while (received < static_cast<size_t>(contentLength) &&
           static_cast<int32_t>(millis() - deadline) < 0) {
        const size_t available = stream->available();
        if (available == 0) {
            if (!stream->connected()) {
                break;
            }
            delay(1);
            continue;
        }
        const size_t want = static_cast<size_t>(contentLength) - received;
        const int read = stream->readBytes(buffer + received, available < want ? available : want);
        if (read <= 0) {
            break;
        }
        received += static_cast<size_t>(read);
    }
    http.end();

    if (received != static_cast<size_t>(contentLength)) {
        GB_LOG("CAMERA", "short read %u/%d bytes", static_cast<unsigned>(received),
               contentLength);
        free(buffer);
        return frame;
    }

    // Cheap sanity check: a JPEG starts FF D8. Uploading anything else would
    // waste a backend round trip and produce a 422 that looks like a classifier
    // problem rather than a camera one.
    if (received < 4 || buffer[0] != 0xFF || buffer[1] != 0xD8) {
        GB_LOG_PLAIN("CAMERA", "response is not a JPEG");
        free(buffer);
        return frame;
    }

    buffer_ = buffer;
    length_ = received;

    frame.data = buffer_;
    frame.length = length_;
    frame.valid = true;
    return frame;
}

void HostCameraService::releaseFrame() {
    if (buffer_ != nullptr) {
        free(buffer_);
        buffer_ = nullptr;
        length_ = 0;
    }
}

}  // namespace greenbin
