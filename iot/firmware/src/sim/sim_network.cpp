#include "sim/sim_network.h"

#include <stdio.h>
#include <string.h>

#include <cstdlib>

#include "sim/posix_http.h"

namespace greenbin {
namespace sim {

namespace {

const char* kBoundary = "----GreenBinBoundary7MA4YWxkTrZu0gW";

std::string field(const char* name, const std::string& value) {
    std::string part = "--";
    part += kBoundary;
    part += "\r\nContent-Disposition: form-data; name=\"";
    part += name;
    part += "\"\r\n\r\n";
    part += value;
    part += "\r\n";
    return part;
}

std::string number(float value, int decimals) {
    char buffer[32];
    snprintf(buffer, sizeof(buffer), "%.*f", decimals, static_cast<double>(value));
    return buffer;
}

// Deliberately tiny JSON scraping — enough for the flat response documented in
// api-contract.md, and nothing more. The firmware uses ArduinoJson.
std::string jsonString(const std::string& body, const char* key) {
    const std::string needle = std::string("\"") + key + "\"";
    size_t at = body.find(needle);
    if (at == std::string::npos) {
        return "";
    }
    at = body.find(':', at + needle.size());
    if (at == std::string::npos) {
        return "";
    }
    const size_t open = body.find('"', at);
    if (open == std::string::npos) {
        return "";
    }
    const size_t close = body.find('"', open + 1);
    if (close == std::string::npos) {
        return "";
    }
    return body.substr(open + 1, close - open - 1);
}

float jsonNumber(const std::string& body, const char* key) {
    const std::string needle = std::string("\"") + key + "\"";
    size_t at = body.find(needle);
    if (at == std::string::npos) {
        return 0.0f;
    }
    at = body.find(':', at + needle.size());
    if (at == std::string::npos) {
        return 0.0f;
    }
    return static_cast<float>(std::atof(body.c_str() + at + 1));
}

NetResult mapStatus(int status) {
    if (status == 200 || status == 201 || status == 202) {
        return NetResult::Ok;
    }
    if (status == 401 || status == 403) {
        return NetResult::Unauthorized;
    }
    if (status < 0) {
        return NetResult::Timeout;
    }
    return NetResult::HttpError;
}

}  // namespace

SimNetworkService::SimNetworkService(std::string baseUrl,
                                     std::string deviceId,
                                     std::string binCode,
                                     std::string deviceKey,
                                     uint32_t timeoutMs)
    : baseUrl_(std::move(baseUrl)),
      deviceId_(std::move(deviceId)),
      binCode_(std::move(binCode)),
      deviceKey_(std::move(deviceKey)),
      timeoutMs_(timeoutMs) {}

void SimNetworkService::beginConnect() {
    // The host is already on a network; association is instantaneous here.
    connected_ = true;
    printf("[WIFI] connecting\n");
}

bool SimNetworkService::isConnected() { return connected_; }

UploadOutcome SimNetworkService::uploadCapture(const CameraFrame& frame,
                                               float fillPercent,
                                               bool fillValid,
                                               uint32_t uptimeSeconds,
                                               ClassificationResult& out) {
    UploadOutcome outcome;
    if (!frame.valid || frame.data == nullptr || frame.length == 0) {
        outcome.result = NetResult::HttpError;
        return outcome;
    }
    ++uploads;

    std::string body;
    body += field("device_id", deviceId_);
    body += field("bin_code", binCode_);
    body += field("event_type", "waste_detected");
    body += field("uptime_s", std::to_string(uptimeSeconds));
    if (fillValid) {
        body += field("fill_percent", number(fillPercent, 1));
    }
    body += "--";
    body += kBoundary;
    body += "\r\nContent-Disposition: form-data; name=\"image\"; filename=\"capture.jpg\"\r\n";
    body += "Content-Type: image/jpeg\r\n\r\n";
    body.append(reinterpret_cast<const char*>(frame.data), frame.length);
    body += "\r\n--";
    body += kBoundary;
    body += "--\r\n";

    HttpRequest request;
    request.url = baseUrl_ + "/api/v1/iot/captures";
    request.contentType = std::string("multipart/form-data; boundary=") + kBoundary;
    request.deviceKey = deviceKey_;
    request.body = body;
    request.timeoutMs = timeoutMs_;

    const HttpResponse response = post(request);
    lastHttpStatus = response.status;
    lastBody = response.body;

    outcome.httpStatus = response.status;
    outcome.result = mapStatus(response.status);

    if (outcome.result == NetResult::Ok) {
        const std::string status = jsonString(response.body, "status");
        const std::string label = jsonString(response.body, "label");
        out.status = parseStatus(status.c_str());
        out.confidence = jsonNumber(response.body, "confidence");
        strncpy(out.label, label.c_str(), sizeof(out.label) - 1);
        out.label[sizeof(out.label) - 1] = '\0';

        // Evidence that the backend privacy pipeline actually ran.
        printf("[PRIVACY] phash=%s exif_stripped=%s faces_blurred=%s bytes=%d\n",
               jsonString(response.body, "phash").c_str(),
               response.body.find("\"exif_stripped\":true") != std::string::npos ? "true"
                                                                                : "false",
               response.body.find("\"faces_blurred\":null") != std::string::npos
                   ? "null(not checked)"
                   : number(jsonNumber(response.body, "faces_blurred"), 0).c_str(),
               static_cast<int>(jsonNumber(response.body, "image_bytes")));
    } else if (!response.error.empty()) {
        printf("[HTTP] transport error: %s\n", response.error.c_str());
    }

    return outcome;
}

NetResult SimNetworkService::sendBinReading(float fillPercent,
                                            bool isFull,
                                            uint32_t uptimeSeconds) {
    ++readings;

    std::string body = "{\"device_id\":\"" + deviceId_ + "\",";
    body += "\"fill_percent\":" + number(fillPercent, 2) + ",";
    body += std::string("\"is_full\":") + (isFull ? "true" : "false") + ",";
    body += "\"uptime_s\":" + std::to_string(uptimeSeconds) + "}";

    HttpRequest request;
    request.url = baseUrl_ + "/api/v1/bins/" + binCode_ + "/readings";
    request.contentType = "application/json";
    request.deviceKey = deviceKey_;
    request.body = body;
    request.timeoutMs = timeoutMs_;

    const HttpResponse response = post(request);
    lastHttpStatus = response.status;
    printf("[HTTP] reading status=%d\n", response.status);
    if (response.status < 0 && !response.error.empty()) {
        printf("[HTTP] transport error: %s\n", response.error.c_str());
    }
    return mapStatus(response.status);
}

}  // namespace sim
}  // namespace greenbin
