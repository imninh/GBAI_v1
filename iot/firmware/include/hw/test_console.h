// Serial hardware test mode (Checkpoint 1 §8, §20).
//
// Lets each peripheral be exercised on its own, without waiting for a PIR event
// and without reflashing. It is driven one character at a time from the Serial
// monitor and never blocks the main loop waiting for input.
//
// It reports what it observed, not what it hoped for: a self test that cannot
// confirm something says so (PIR needs a physical trigger) rather than printing
// OK (§20, §31).
#pragma once

#include <Arduino.h>

#include "core/state_machine.h"
#include "hw/mock_backend.h"
#include "hw/mock_camera.h"
#include "hw/oled_display.h"
#include "hw/sensors.h"
#include "hw/servo_sorter.h"

namespace greenbin {

#ifdef GREENBIN_ENABLE_WIFI
class WifiHeartbeat;
#endif

class TestConsole {
  public:
    struct Wiring {
        StateMachine* machine = nullptr;
        Hcsr501PresenceSensor* presence = nullptr;
        Hcsr04DistanceSensor* distance = nullptr;
        LedService* led = nullptr;
        // The camera this build actually uses — mock, host webcam or OV2640.
        CameraService* camera = nullptr;
        // Set only when `camera` is the mock, which is the one that can be told
        // to fail on demand. Null elsewhere, and the `c` command says so.
        MockCameraService* mockCamera = nullptr;
        MockBackendService* backend = nullptr;
        ServoSorter* sorter = nullptr;      // null when the build has no servo
        OledDisplay* display = nullptr;     // null when the build has no OLED
#ifdef GREENBIN_ENABLE_WIFI
        WifiHeartbeat* heartbeat = nullptr;
#endif
        float emptyDistanceCm = 60.0f;
        float fullDistanceCm = 10.0f;
        FillThresholds fillThresholds;
    };

    explicit TestConsole(const Wiring& wiring) : w_(wiring) {}

    void begin();
    // Consumes any pending Serial input. Call once per loop.
    void tick(uint32_t nowMs);

    // True once the PIR has been seen asserted at least once, which is the only
    // honest way to report it as working.
    bool pirObserved() const { return pirObserved_; }

  private:
    void printMenu() const;
    void handle(char command, uint32_t nowMs);

    bool testPir(uint32_t timeoutMs);
    bool testUltrasonic();
    bool testDisplay();
    bool testLed(uint32_t nowMs);
    bool testServo();
    bool testCamera();
    void runSelfTest(uint32_t nowMs);

    void printStatus() const;
    void printFill();

    Wiring w_;
    bool pirObserved_ = false;
};

}  // namespace greenbin
