#include "hw/test_console.h"

#include "core/logging.h"

#ifdef GREENBIN_ENABLE_WIFI
#include "hw/wifi_heartbeat.h"
#endif

namespace greenbin {

namespace {

const char* verdict(bool ok) { return ok ? "OK" : "FAIL"; }

}  // namespace

void TestConsole::begin() { printMenu(); }

void TestConsole::printMenu() const {
    Serial.println();
    Serial.println(F("========== GREENBINAI =========="));
    Serial.println(F("      HARDWARE TEST MODE"));
    Serial.println();
    Serial.println(F("1 - Test PIR"));
    Serial.println(F("2 - Test HC-SR04"));
    Serial.println(F("3 - Test OLED"));
    Serial.println(F("4 - Test NeoPixel"));
    Serial.println(F("5 - Test Servo"));
    Serial.println(F("6 - Run all tests (Checkpoint 1 self test)"));
    Serial.println();
    Serial.println(F("p - Servo -> PLASTIC"));
    Serial.println(F("a - Servo -> PAPER"));
    Serial.println(F("m - Servo -> METAL"));
    Serial.println(F("h - Servo -> HOME"));
    Serial.println();
    Serial.println(F("7 - Mock AI next result = PLASTIC"));
    Serial.println(F("8 - Mock AI next result = PAPER"));
    Serial.println(F("9 - Mock AI next result = METAL"));
    Serial.println(F("0 - Mock AI next result = UNKNOWN (must not sort)"));
    Serial.println(F("c - Force next camera capture to fail"));
    Serial.println(F("x - Force next upload to fail"));
    Serial.println();
    Serial.println(F("f - Show fill level"));
    Serial.println(F("s - Show system status"));
    Serial.println(F("r - Run simulated waste flow"));
#ifdef GREENBIN_ENABLE_WIFI
    Serial.println(F("w - Wi-Fi status + send heartbeat now"));
#endif
    Serial.println();
    Serial.println(F("? - Show help"));
    Serial.println(F("================================"));
}

void TestConsole::tick(uint32_t nowMs) {
    // Latch the PIR whenever it fires, whoever caused it. This is what lets the
    // self test distinguish "never seen" from "seen working".
    if (w_.presence != nullptr && w_.presence->motionDetected()) {
        pirObserved_ = true;
    }

    while (Serial.available() > 0) {
        const int c = Serial.read();
        if (c < 0 || c == '\r' || c == '\n' || c == ' ') {
            continue;
        }
        handle(static_cast<char>(c), nowMs);
    }
}

void TestConsole::handle(char command, uint32_t nowMs) {
    switch (command) {
        case '1':
            Serial.println(F("[TEST] PIR — wave in front of the sensor (8 s window)"));
            Serial.printf("[TEST] PIR : %s\n", verdict(testPir(8000)));
            break;
        case '2':
            Serial.printf("[TEST] HC-SR04 : %s\n", verdict(testUltrasonic()));
            break;
        case '3':
            Serial.printf("[TEST] OLED : %s\n", verdict(testDisplay()));
            break;
        case '4':
            Serial.printf("[TEST] NEOPIXEL : %s\n", verdict(testLed(nowMs)));
            break;
        case '5':
            Serial.printf("[TEST] SERVO : %s\n", verdict(testServo()));
            break;
        case '6':
            runSelfTest(nowMs);
            break;

        case 'p':
        case 'a':
        case 'm':
        case 'h': {
            if (w_.sorter == nullptr) {
                Serial.println(F("[SERVO] not present in this build"));
                break;
            }
            // Refused mid-transaction: moving the flap by hand while the device
            // is sorting would send the item into the wrong bin.
            if (w_.machine != nullptr && !w_.machine->idle()) {
                Serial.printf("[SERVO] refused — device is busy in %s\n",
                              stateName(w_.machine->state()));
                break;
            }
            const BinTarget target = command == 'p'   ? BinTarget::Plastic
                                     : command == 'a' ? BinTarget::Paper
                                     : command == 'm' ? BinTarget::Metal
                                                      : BinTarget::Home;
            w_.sorter->moveTo(target);
            break;
        }

        case '7':
        case '8':
        case '9':
        case '0': {
            if (w_.backend == nullptr) {
                Serial.println(F("[TEST] no mock backend in this build"));
                break;
            }
            const WasteClass next = command == '7'   ? WasteClass::Plastic
                                    : command == '8' ? WasteClass::Paper
                                    : command == '9' ? WasteClass::Metal
                                                     : WasteClass::Unknown;
            w_.backend->setNextClass(next);
            Serial.printf("[TEST] mock AI will return label=%s\n", wasteClassName(next));
            break;
        }

        case 'c':
            if (w_.mockCamera == nullptr) {
                Serial.println(F("[TEST] this build has a real camera; unplug it to test failure"));
                break;
            }
            w_.mockCamera->setNextCaptureFails();
            Serial.println(F("[TEST] next camera capture will fail"));
            break;
        case 'x':
            if (w_.backend != nullptr) {
                w_.backend->setNextUploadResult(NetResult::Timeout);
                Serial.println(F("[TEST] next upload will time out"));
            }
            break;

        case 'f':
            printFill();
            break;
        case 's':
            printStatus();
            break;
        case 'r':
            if (w_.machine != nullptr && !w_.machine->startManualEvent(nowMs)) {
                Serial.println(F("[TEST] busy — a transaction is already running"));
            }
            break;
#ifdef GREENBIN_ENABLE_WIFI
        case 'w':
            if (w_.heartbeat != nullptr) {
                w_.heartbeat->sendNow();
            }
            break;
#endif
        case '?':
            printMenu();
            break;
        default:
            Serial.printf("[TEST] unknown command '%c' — press ? for help\n", command);
            break;
    }
}

bool TestConsole::testPir(uint32_t timeoutMs) {
    if (w_.presence == nullptr) {
        return false;
    }
    const uint32_t start = millis();
    bool sawHigh = w_.presence->motionDetected();
    bool sawLow = !sawHigh;

    while (millis() - start < timeoutMs) {
        const bool level = w_.presence->motionDetected();
        if (level) {
            sawHigh = true;
        } else {
            sawLow = true;
        }
        // A PIR that only ever reads HIGH is as suspicious as one stuck LOW, so
        // both levels are reported rather than just "motion seen".
        if (sawHigh && sawLow) {
            break;
        }
        delay(20);
    }

    if (sawHigh) {
        pirObserved_ = true;
    }
    Serial.printf("[PIR] observed high=%d low=%d\n", sawHigh ? 1 : 0, sawLow ? 1 : 0);
    return sawHigh;
}

bool TestConsole::testUltrasonic() {
    if (w_.distance == nullptr) {
        return false;
    }
    int valid = 0;
    for (int i = 0; i < 3; ++i) {
        const DistanceReading reading = w_.distance->read();
        if (!reading.valid) {
            Serial.println(F("[HC-SR04] reading invalid (timeout or out of range)"));
            continue;
        }
        ++valid;
        const FillResult fill =
            computeFillPercent(reading, w_.emptyDistanceCm, w_.fullDistanceCm);
        Serial.printf("[HC-SR04] distance=%.1fcm fill=%.1f%% state=%s\n",
                      static_cast<double>(reading.cm), static_cast<double>(fill.percent),
                      fillStateName(fillStateFor(fill.percent, w_.fillThresholds)));
    }
    return valid > 0;
}

bool TestConsole::testDisplay() {
    if (w_.display == nullptr) {
        Serial.println(F("[OLED] not present in this build"));
        return false;
    }
    if (!w_.display->isReady()) {
        Serial.println(F("[OLED] panel did not answer on I2C"));
        return false;
    }
    // Walks every screen the state machine can request, so a layout regression
    // is visible without having to reproduce a whole transaction.
    w_.display->showRaw("GreenBinAI", "OLED TEST", "128x64 SSD1306", "I2C ok");
    delay(700);
    w_.display->showIdle(false);
    delay(500);
    w_.display->showUserDetected();
    delay(500);
    w_.display->showCapturing();
    delay(500);
    w_.display->showAnalyzing();
    delay(500);
    w_.display->showSorting(BinTarget::Plastic);
    delay(500);
    w_.display->showComplete(WasteClass::Plastic, true, true, 53.0f);
    delay(700);
    w_.display->showError("Self test");
    delay(500);
    w_.display->showIdle(false);
    return true;
}

bool TestConsole::testLed(uint32_t nowMs) {
    if (w_.led == nullptr) {
        return false;
    }
    const LedPattern patterns[] = {LedPattern::Idle,    LedPattern::Processing,
                                   LedPattern::Ok,      LedPattern::Warning,
                                   LedPattern::Hazard,  LedPattern::BinFull};
    for (LedPattern pattern : patterns) {
        w_.led->showTemporary(pattern, nowMs);
        // The pattern engine is time-driven, so it has to be ticked for blinking
        // patterns to actually reach the pixel.
        for (int i = 0; i < 40; ++i) {
            nowMs += 20;
            w_.led->tick(nowMs);
            delay(20);
        }
    }
    w_.led->tick(nowMs);
    // Write-only device: there is no readback, so this reports that the driver
    // accepted every pattern, not that the pixel lit up. Confirm visually.
    return true;
}

bool TestConsole::testServo() {
    if (w_.sorter == nullptr) {
        Serial.println(F("[SERVO] not present in this build"));
        return false;
    }
    const BinTarget sequence[] = {BinTarget::Home,  BinTarget::Plastic, BinTarget::Home,
                                  BinTarget::Paper, BinTarget::Home,    BinTarget::Metal,
                                  BinTarget::Home};
    for (BinTarget target : sequence) {
        if (!w_.sorter->moveTo(target) || w_.sorter->position() != target) {
            Serial.printf("[SERVO] failed to reach %s\n", binTargetName(target));
            return false;
        }
    }
    return true;
}

bool TestConsole::testCamera() {
    if (w_.camera == nullptr) {
        return false;
    }
    const CameraFrame frame = w_.camera->captureJpeg();
    const bool ok = frame.valid && frame.data != nullptr && frame.length > 0;
    if (ok) {
        Serial.printf("[CAMERA] frame bytes=%u\n", static_cast<unsigned>(frame.length));
    } else {
        Serial.println(F("[CAMERA] capture returned no frame"));
    }
    w_.camera->releaseFrame();
    return ok;
}

void TestConsole::runSelfTest(uint32_t nowMs) {
    Serial.println();
    Serial.println(F("=== GREENBINAI HARDWARE SELF TEST ==="));
    Serial.println();

    // The MCU is running this code, so it is the one thing that needs no probe.
    const bool esp32 = true;
    const bool oled = testDisplay();
    const bool servo = testServo();
    const bool ultrasonic = testUltrasonic();
    const bool led = testLed(nowMs);
    const bool camera = testCamera();
    // Short passive window: a PIR cannot be asserted from software, so this only
    // catches a sensor that is already high or fires during the window.
    const bool pir = testPir(1500);

    Serial.println();
    Serial.printf("ESP32         : %s\n", verdict(esp32));
    Serial.printf("PIR           : %s\n",
                  pir ? "OK - motion observed" : "READY - waiting manual trigger");
    Serial.printf("OLED          : %s\n", verdict(oled));
    Serial.printf("SERVO         : %s\n", verdict(servo));
    Serial.printf("HC-SR04       : %s\n", verdict(ultrasonic));
    Serial.printf("NEOPIXEL      : %s\n", verdict(led));
    // Names which camera was actually exercised: a green row must not let a
    // fixture JPEG be mistaken for a working sensor.
    if (w_.mockCamera != nullptr) {
        Serial.printf("CAMERA MOCK   : %s\n", verdict(camera));
    } else {
        Serial.printf("CAMERA        : %s\n", verdict(camera));
    }

    const bool hardFail = !(oled && servo && ultrasonic && led && camera);
    Serial.println(F("------------------------------------"));
    if (hardFail) {
        Serial.println(F("CHECKPOINT 1  : FAIL"));
    } else if (!pir) {
        // Not called PASS outright: one device has not been proven (§20, §31).
        Serial.println(F("CHECKPOINT 1  : PASS (PIR not yet triggered)"));
    } else {
        Serial.println(F("CHECKPOINT 1  : PASS"));
    }
    Serial.println(F("------------------------------------"));
    Serial.println(F("NEOPIXEL and SERVO have no position feedback: OK means the"));
    Serial.println(F("driver accepted every command. Confirm both visually."));
    Serial.println();
}

void TestConsole::printFill() {
    if (w_.distance == nullptr) {
        return;
    }
    const DistanceReading reading = w_.distance->read();
    if (!reading.valid) {
        // No number is printed for a failed reading (§11, §24).
        Serial.println(F("[HC-SR04] reading invalid — no fill level available"));
        return;
    }
    const FillResult fill = computeFillPercent(reading, w_.emptyDistanceCm, w_.fullDistanceCm);
    Serial.printf("[HC-SR04] distance=%.1fcm fill=%.1f%% state=%s (empty=%.0fcm full=%.0fcm)\n",
                  static_cast<double>(reading.cm), static_cast<double>(fill.percent),
                  fillStateName(fillStateFor(fill.percent, w_.fillThresholds)),
                  static_cast<double>(w_.emptyDistanceCm),
                  static_cast<double>(w_.fullDistanceCm));
}

void TestConsole::printStatus() const {
    if (w_.machine == nullptr) {
        return;
    }
    const ClassificationResult& result = w_.machine->lastResult();
    const FillResult& fill = w_.machine->lastFill();

    Serial.println();
    Serial.println(F("---------- SYSTEM STATUS ----------"));
    Serial.printf("state         : %s\n", stateName(w_.machine->state()));
    Serial.printf("uptime        : %lu s\n", static_cast<unsigned long>(millis() / 1000));
    Serial.printf("free heap     : %u bytes\n", static_cast<unsigned>(ESP.getFreeHeap()));
    Serial.printf("bin full      : %s\n", w_.machine->binFull() ? "yes" : "no");
    if (fill.valid) {
        Serial.printf("fill          : %.1f%% (%s)\n", static_cast<double>(fill.percent),
                      fillStateName(w_.machine->fillState()));
    } else {
        Serial.println(F("fill          : unavailable (last reading invalid)"));
    }
    Serial.printf("last result   : %s label=%s confidence=%.2f action=%s\n",
                  statusName(result.status), result.label[0] != '\0' ? result.label : "null",
                  static_cast<double>(result.confidence), sortActionName(result.action));
    Serial.printf("sorter at     : %s\n",
                  w_.sorter != nullptr ? binTargetName(w_.sorter->position()) : "n/a");
    Serial.printf("captures=%lu uploads=%lu sorts=%lu readings=%lu\n",
                  static_cast<unsigned long>(w_.machine->capturesTaken()),
                  static_cast<unsigned long>(w_.machine->uploadsAttempted()),
                  static_cast<unsigned long>(w_.machine->sortsPerformed()),
                  static_cast<unsigned long>(w_.machine->readingsSent()));
    Serial.printf("PIR observed  : %s\n", pirObserved_ ? "yes" : "not yet");
    Serial.println(F("-----------------------------------"));
}

}  // namespace greenbin
