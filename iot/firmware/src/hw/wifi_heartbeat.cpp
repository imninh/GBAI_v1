#include "hw/wifi_heartbeat.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>

#include "config.h"
#include "core/logging.h"

namespace greenbin {

WifiHeartbeat::WifiHeartbeat(const char* ssid,
                             const char* password,
                             const char* baseUrl,
                             const char* deviceId,
                             const char* deviceKey,
                             uint32_t timeoutMs,
                             uint32_t intervalMs)
    : ssid_(ssid),
      password_(password),
      baseUrl_(baseUrl),
      deviceId_(deviceId),
      deviceKey_(deviceKey),
      timeoutMs_(timeoutMs),
      intervalMs_(intervalMs) {}

void WifiHeartbeat::begin() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid_, password_);
    started_ = true;
    // The SSID is logged; the password never is (spec §20).
    GB_LOG("WIFI", "Connecting... ssid=%s", ssid_);
}

bool WifiHeartbeat::connected() const { return WiFi.status() == WL_CONNECTED; }

void WifiHeartbeat::tick(uint32_t nowMs) {
    if (!started_) {
        return;
    }
    if (!connected()) {
        announced_ = false;
        return;
    }

    if (!announced_) {
        announced_ = true;
        GB_LOG_PLAIN("WIFI", "Connected");
        GB_LOG("WIFI", "IP=%s", WiFi.localIP().toString().c_str());
        nextSendMs_ = nowMs;  // first heartbeat as soon as the link is up
    }

    if (static_cast<int32_t>(nowMs - nextSendMs_) < 0) {
        return;
    }
    nextSendMs_ = nowMs + intervalMs_;
    post();
}

bool WifiHeartbeat::sendNow() {
    if (!started_) {
        GB_LOG_PLAIN("WIFI", "not started in this build");
        return false;
    }
    if (!connected()) {
        GB_LOG("WIFI", "not connected (status=%d)", static_cast<int>(WiFi.status()));
        return false;
    }
    GB_LOG("WIFI", "IP=%s", WiFi.localIP().toString().c_str());
    return post();
}

bool WifiHeartbeat::post() {
    JsonDocument doc;
    doc["device_id"] = deviceId_;
    doc["status"] = "online";

    String payload;
    serializeJson(doc, payload);

    String url = baseUrl_;
    url += API_HEARTBEAT_PATH;

    HTTPClient http;
    http.setTimeout(timeoutMs_);
    http.setConnectTimeout(timeoutMs_);
    http.setReuse(false);
    if (!http.begin(url)) {
        GB_LOG_PLAIN("API", "heartbeat: cannot open connection");
        return false;
    }
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Device-Key", deviceKey_);  // value is never logged

    GB_LOG("API", "POST %s", API_HEARTBEAT_PATH);
    const int code = http.POST(payload);
    http.end();

    if (code == 200) {
        GB_LOG_PLAIN("API", "HTTP 200");
        GB_LOG_PLAIN("API", "Backend reachable");
        return true;
    }
    // A negative code is a transport failure (refused, timeout); a positive one
    // is a real HTTP status. Both are reported as-is rather than as "offline".
    GB_LOG("API", "heartbeat failed code=%d — backend NOT confirmed", code);
    return false;
}

}  // namespace greenbin
