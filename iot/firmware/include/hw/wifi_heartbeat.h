// Wi-Fi association + backend liveness check (Checkpoint 1 §21).
//
// Deliberately separate from EspNetworkService: this is a P1 "can the device
// reach the backend at all" probe, not part of the sorting flow. The state
// machine never calls it and never waits on it, so a missing access point or a
// backend that is not running cannot affect a transaction.
//
// It is only ticked while the device is IDLE, and its HTTP timeout is a few
// seconds rather than HTTP_TIMEOUT_MS, for the same reason.
#pragma once

#include <Arduino.h>

namespace greenbin {

class WifiHeartbeat {
  public:
    WifiHeartbeat(const char* ssid,
                  const char* password,
                  const char* baseUrl,
                  const char* deviceId,
                  const char* deviceKey,
                  uint32_t timeoutMs,
                  uint32_t intervalMs);

    // Starts association and returns immediately.
    void begin();

    // Sends a heartbeat when one is due and the link is up. Safe to call every
    // loop; does nothing most of the time.
    void tick(uint32_t nowMs);

    // Sends one now regardless of the schedule (Serial command `w`).
    bool sendNow();

    bool connected() const;

  private:
    bool post();

    const char* ssid_;
    const char* password_;
    const char* baseUrl_;
    const char* deviceId_;
    const char* deviceKey_;
    uint32_t timeoutMs_;
    uint32_t intervalMs_;

    bool started_ = false;
    bool announced_ = false;  // so "Connected / IP=" is logged once, not per loop
    uint32_t nextSendMs_ = 0;
};

}  // namespace greenbin
