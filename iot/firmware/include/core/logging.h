// Serial logging in the machine-readable format of spec §20:
//
//     [STATE] IDLE
//     [ULTRASONIC] before=52.3 after=46.8 delta=5.5
//
// Compiles against Serial on the ESP32 and stdout in native unit tests, so core
// logic can log without pulling in Arduino.h.
//
// NEVER log Wi-Fi passwords, device keys or API secrets (spec §20).
#pragma once

#ifdef GREENBIN_NATIVE
#include <stdio.h>
#define GB_LOG(tag, fmt, ...) printf("[" tag "] " fmt "\n", ##__VA_ARGS__)
#define GB_LOG_PLAIN(tag, msg) printf("[" tag "] " msg "\n")
#else
#include <Arduino.h>
#define GB_LOG(tag, fmt, ...) Serial.printf("[" tag "] " fmt "\n", ##__VA_ARGS__)
#define GB_LOG_PLAIN(tag, msg) Serial.println(F("[" tag "] " msg))
#endif
