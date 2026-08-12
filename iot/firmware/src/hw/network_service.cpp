#include "hw/network_service.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>

#include "config.h"
#include "core/logging.h"

namespace greenbin {

namespace {

constexpr char kBoundary[] = "----GreenBinBoundary7MA4YWxkTrZu0gW";

// Builds one multipart field. Kept out of the request assembly below so the
// body layout stays readable.
String multipartField(const char* name, const String& value) {
    String part = "--";
    part += kBoundary;
    part += "\r\nContent-Disposition: form-data; name=\"";
    part += name;
    part += "\"\r\n\r\n";
    part += value;
    part += "\r\n";
    return part;
}

}  // namespace

EspNetworkService::EspNetworkService(const char* ssid,
                                     const char* password,
                                     const char* baseUrl,
                                     const char* deviceId,
                                     const char* binCode,
                                     const char* deviceKey,
                                     uint32_t timeoutMs)
    : ssid_(ssid),
      password_(password),
      baseUrl_(baseUrl),
      deviceId_(deviceId),
      binCode_(binCode),
      deviceKey_(deviceKey),
      timeoutMs_(timeoutMs) {}

void EspNetworkService::beginConnect() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid_, password_);
    // Deliberately no WiFi.waitForConnectResult(): blocking here is exactly the
    // freeze spec §15 forbids. The state machine polls isConnected() instead.
    GB_LOG_PLAIN("WIFI", "connecting");  // never logs the SSID password
}

bool EspNetworkService::isConnected() { return WiFi.status() == WL_CONNECTED; }

NetResult EspNetworkService::mapHttpCode(int code) const {
    if (code == 200 || code == 201 || code == 202) {
        return NetResult::Ok;
    }
    if (code == 401 || code == 403) {
        return NetResult::Unauthorized;
    }
    if (code < 0) {
        // HTTPClient returns negative constants for transport failures,
        // including connection refused and read timeout.
        return NetResult::Timeout;
    }
    return NetResult::HttpError;
}

bool EspNetworkService::parseClassification(const String& payload,
                                            ClassificationResult& out) const {
    JsonDocument doc;
    const DeserializationError err = deserializeJson(doc, payload);
    if (err) {
        GB_LOG("HTTP", "json parse failed: %s", err.c_str());
        return false;
    }

    const char* status = doc["status"] | "";
    const char* label = doc["label"] | "";
    const char* transactionId = doc["transaction_id"] | "";
    // Anything unrecognised lands on Unknown, never on Ok (spec §11).
    out.status = parseStatus(status);
    out.confidence = doc["confidence"] | 0.0f;
    strncpy(out.label, label, sizeof(out.label) - 1);
    out.label[sizeof(out.label) - 1] = '\0';
    // Optional today; the response contract of Checkpoint 1 §25 carries it, and
    // an absent field simply leaves the id empty rather than failing the parse.
    strncpy(out.transactionId, transactionId, sizeof(out.transactionId) - 1);
    out.transactionId[sizeof(out.transactionId) - 1] = '\0';
    // `action` and `target_bin` from the response are deliberately ignored:
    // resolveSorting() derives them locally so the device's own confidence floor
    // and refusal rules always apply, whatever the backend says (§24).
    return true;
}

UploadOutcome EspNetworkService::uploadCapture(const CameraFrame& frame,
                                               float fillPercent,
                                               bool fillValid,
                                               uint32_t uptimeSeconds,
                                               ClassificationResult& out) {
    UploadOutcome outcome;

    if (!isConnected()) {
        outcome.result = NetResult::NoNetwork;
        return outcome;
    }
    if (!frame.valid || frame.data == nullptr || frame.length == 0) {
        outcome.result = NetResult::HttpError;
        return outcome;
    }

    String head;
    head.reserve(512);
    head += multipartField("device_id", deviceId_);
    head += multipartField("bin_code", binCode_);
    head += multipartField("event_type", "waste_detected");
    head += multipartField("uptime_s", String(uptimeSeconds));
    if (fillValid) {
        // Omitted entirely when invalid — better a missing field than a
        // fabricated fill level (spec §19 scenario 9).
        head += multipartField("fill_percent", String(fillPercent, 1));
    }
    head += "--";
    head += kBoundary;
    head += "\r\nContent-Disposition: form-data; name=\"image\"; filename=\"capture.jpg\"\r\n";
    head += "Content-Type: image/jpeg\r\n\r\n";

    String tail = "\r\n--";
    tail += kBoundary;
    tail += "--\r\n";

    const size_t totalLength = head.length() + frame.length + tail.length();

    // JPEG at SVGA is tens of kilobytes, so assemble in PSRAM when available
    // rather than fragmenting internal DRAM.
    uint8_t* body = static_cast<uint8_t*>(
        psramFound() ? ps_malloc(totalLength) : malloc(totalLength));
    if (body == nullptr) {
        GB_LOG("HTTP", "cannot allocate %u bytes for upload",
               static_cast<unsigned>(totalLength));
        outcome.result = NetResult::HttpError;
        return outcome;
    }

    memcpy(body, head.c_str(), head.length());
    memcpy(body + head.length(), frame.data, frame.length);
    memcpy(body + head.length() + frame.length, tail.c_str(), tail.length());

    String url = baseUrl_;
    url += API_CAPTURES_PATH;

    HTTPClient http;
    http.setTimeout(timeoutMs_);
    http.setConnectTimeout(timeoutMs_);
    http.setReuse(false);
    if (!http.begin(url)) {
        free(body);
        outcome.result = NetResult::HttpError;
        return outcome;
    }

    String contentType = "multipart/form-data; boundary=";
    contentType += kBoundary;
    http.addHeader("Content-Type", contentType);
    http.addHeader("X-Device-Key", deviceKey_);  // value is never logged

    const int code = http.POST(body, totalLength);
    outcome.httpStatus = code;
    outcome.result = mapHttpCode(code);

    if (outcome.result == NetResult::Ok) {
        const String payload = http.getString();
        if (!parseClassification(payload, out)) {
            outcome.result = NetResult::ParseError;
        }
    } else if (outcome.result == NetResult::Unauthorized) {
        GB_LOG_PLAIN("HTTP", "device key rejected");
    }

    http.end();
    free(body);
    return outcome;
}

NetResult EspNetworkService::sendBinReading(float fillPercent,
                                            bool isFull,
                                            uint32_t uptimeSeconds) {
    if (!isConnected()) {
        return NetResult::NoNetwork;
    }

    JsonDocument doc;
    doc["device_id"] = deviceId_;
    doc["fill_percent"] = fillPercent;
    doc["is_full"] = isFull;
    doc["uptime_s"] = uptimeSeconds;

    String payload;
    serializeJson(doc, payload);

    String url = baseUrl_;
    url += API_READINGS_PATH;

    HTTPClient http;
    http.setTimeout(timeoutMs_);
    http.setConnectTimeout(timeoutMs_);
    http.setReuse(false);
    if (!http.begin(url)) {
        return NetResult::HttpError;
    }
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Device-Key", deviceKey_);

    const int code = http.POST(payload);
    const NetResult result = mapHttpCode(code);
    GB_LOG("HTTP", "reading status=%d", code);
    http.end();
    return result;
}

}  // namespace greenbin
