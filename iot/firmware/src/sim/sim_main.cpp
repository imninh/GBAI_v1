// Host simulator — runs the REAL state machine against the REAL backend.
//
// The unit tests prove the logic with fakes; Wokwi proves the GPIO timing. This
// closes the remaining gap: it exercises the actual device↔backend contract —
// multipart framing, X-Device-Key auth, the privacy pipeline, the classification
// response shape and the bin-reading endpoint — over a real socket, with no
// hardware.
//
// Usage:
//     pio run -e sim
//     .pio/build/sim/program --base-url http://127.0.0.1:8000
//                            --device-id GBIN-001 --device-key <key>
#include <stdio.h>
#include <string.h>

#include <string>

#include "core/state_machine.h"
#include "sim/sim_devices.h"
#include "sim/sim_network.h"

using namespace greenbin;
using namespace greenbin::sim;

namespace {

int g_failures = 0;
int g_checks = 0;

void check(bool condition, const char* description) {
    ++g_checks;
    if (condition) {
        printf("  \033[32m[PASS]\033[0m %s\n", description);
    } else {
        ++g_failures;
        printf("  \033[31m[FAIL]\033[0m %s\n", description);
    }
}

void banner(const char* title) { printf("\n=== %s ===\n", title); }

StateMachineConfig simConfig() {
    StateMachineConfig cfg;
    cfg.pirWaitMs = 100;
    cfg.objectDeltaCm = 4.0f;
    cfg.pirRearmMs = 50;
    cfg.fillIntervalMs = 1000;
    cfg.emptyDistanceCm = 60.0f;
    cfg.fullDistanceCm = 10.0f;
    cfg.fullThresholdPercent = 80.0f;
    cfg.fullClearPercent = 75.0f;
    cfg.maxRetry = 3;
    cfg.retryDelayMs = 10;
    cfg.retryMaxDelayMs = 100;
    cfg.wifiConnectTimeoutMs = 100;
    cfg.wifiRetryDelayMs = 50;
    cfg.errorDisplayMs = 100;
    cfg.resultDisplayMs = 100;
    return cfg;
}

struct Rig {
    ScriptedPresenceSensor presence;
    ScriptedDistanceSensor distance;
    FileCameraService camera;
    SimNetworkService network;
    ConsoleLedService led;
    StateMachine machine;
    uint32_t now = 1000;

    Rig(const std::string& fixture,
        const std::string& baseUrl,
        const std::string& deviceId,
        const std::string& binCode,
        const std::string& deviceKey)
        : camera(fixture),
          network(baseUrl, deviceId, binCode, deviceKey, 5000),
          machine(presence, distance, camera, network, led, simConfig()) {}

    void advance(uint32_t ms) {
        now += ms;
        machine.tick(now);
    }

    void bootToIdle() {
        machine.begin(now);
        machine.tick(now);
        advance(10);
    }

    // Run until the device is back at rest. Scenarios run back to back against
    // one device, so each must start from a settled IDLE rather than mid-flow.
    void settleToIdle(int maxTicks = 60) {
        for (int i = 0; i < maxTicks && machine.state() != DeviceState::Idle; ++i) {
            advance(50);
        }
    }

    // Mirrors a real HC-SR501: pulses, then drops.
    void depositEvent(float baselineCm, float afterCm) {
        // Wait out any PIR re-arm cool-down left by a previous event. Unlike the
        // unit tests, which build a fresh harness per case, this rig runs
        // scenarios back to back against one device — exactly as a real bin does.
        advance(simConfig().pirRearmMs + 10);
        distance.set(baselineCm);
        presence.motion = true;
        advance(10);
        presence.motion = false;
        distance.set(afterCm);
        advance(150);
        advance(1);
    }
};

std::string argValue(int argc, char** argv, const char* flag, const std::string& fallback) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (strcmp(argv[i], flag) == 0) {
            return argv[i + 1];
        }
    }
    return fallback;
}

}  // namespace

int main(int argc, char** argv) {
    const std::string baseUrl =
        argValue(argc, argv, "--base-url", "http://127.0.0.1:8000");
    const std::string deviceId = argValue(argc, argv, "--device-id", "GBIN-001");
    const std::string binCode = argValue(argc, argv, "--bin-code", "BIN-001");
    const std::string deviceKey = argValue(argc, argv, "--device-key", "");
    const std::string fixture = argValue(argc, argv, "--fixture",
                                         "../simulation/fixtures/sample_waste.jpg");

    printf("GreenBinAI host simulator\n");
    printf("  backend : %s\n", baseUrl.c_str());
    printf("  device  : %s / bin %s\n", deviceId.c_str(), binCode.c_str());
    printf("  fixture : %s\n", fixture.c_str());
    if (deviceKey.empty()) {
        printf("\n  WARNING: no --device-key given; expect 401 from the backend.\n");
    }

    // ── Scenarios 1–2, 7–8 against the live backend ──────────────────────────
    Rig rig(fixture, baseUrl, deviceId, binCode, deviceKey);

    banner("Boot");
    rig.bootToIdle();
    check(rig.machine.state() == DeviceState::Idle, "reaches IDLE after boot");

    banner("Scenario 1 — person walks past (no deposit)");
    rig.depositEvent(50.0f, 49.0f);
    check(rig.machine.capturesTaken() == 0, "no image captured");
    check(rig.network.uploads == 0, "no vision request sent");
    check(rig.machine.state() == DeviceState::Idle, "returned to IDLE");

    banner("Scenario 2/3 — valid waste event, real upload");
    rig.depositEvent(50.0f, 44.0f);
    rig.advance(1);  // CAPTURE
    rig.advance(1);  // UPLOAD  (real HTTP happens here)
    rig.advance(1);  // WAIT_RESULT
    check(rig.machine.capturesTaken() == 1, "image captured");
    check(rig.network.uploads == 1, "exactly one upload attempt");
    check(rig.network.lastHttpStatus == 200, "backend returned HTTP 200");
    check(rig.camera.isHolding() == false, "camera buffer released");
    printf("  backend said: status=%s label=%s confidence=%.2f\n",
           statusName(rig.machine.lastResult().status), rig.machine.lastResult().label,
           static_cast<double>(rig.machine.lastResult().confidence));
    printf("  LED showed  : %s\n", ConsoleLedService::name(rig.led.lastTemporary));

    banner("Scenario 7 — bin full, real reading POST");
    rig.settleToIdle();
    rig.distance.set(12.0f);  // ~96 %
    rig.advance(1100);
    check(rig.machine.binFull(), "device considers the bin full");
    check(rig.network.readings >= 1, "reading POSTed to backend");
    check(rig.network.lastHttpStatus == 201, "backend returned HTTP 201");
    check(rig.led.background == LedPattern::BinFull, "LED background is solid BIN_FULL");

    const int readingsAfterFull = rig.network.readings;
    for (int i = 0; i < 3; ++i) {
        rig.advance(1100);
    }
    check(rig.network.readings == readingsAfterFull,
          "no repeated 'still full' events");

    banner("Scenario 8 — bin emptied");
    rig.distance.set(55.0f);  // ~10 %
    rig.advance(1100);
    check(!rig.machine.binFull(), "full state cleared");
    check(rig.network.readings == readingsAfterFull + 1, "one further reading sent");
    check(rig.led.background == LedPattern::Idle, "LED background back to IDLE");

    banner("Scenario 9 — invalid ultrasonic reading");
    rig.distance.setInvalid();
    const int readingsBeforeInvalid = rig.network.readings;
    rig.advance(1100);
    check(rig.network.readings == readingsBeforeInvalid,
          "no bogus fill value sent");
    check(rig.machine.state() == DeviceState::Idle, "device continues safely");

    // ── Scenario 6 against a closed port ─────────────────────────────────────
    banner("Scenario 6 — backend unreachable, bounded retry");
    Rig offline(fixture, "http://127.0.0.1:9", deviceId, binCode, deviceKey);
    offline.bootToIdle();
    offline.depositEvent(50.0f, 44.0f);
    offline.advance(1);  // CAPTURE
    for (int i = 0; i < 40; ++i) {
        offline.advance(20);
    }
    check(offline.network.uploads == 3, "retries bounded at MAX_RETRY (3)");
    check(offline.machine.state() == DeviceState::Idle, "recovered to IDLE, not frozen");
    check(offline.machine.lastError() == ErrorKind::Network, "network error recorded");
    check(offline.camera.isHolding() == false, "camera buffer released despite failure");

    printf("\n%s %d/%d checks passed\033[0m\n",
           g_failures == 0 ? "\033[32m" : "\033[31m", g_checks - g_failures, g_checks);
    return g_failures == 0 ? 0 : 1;
}
