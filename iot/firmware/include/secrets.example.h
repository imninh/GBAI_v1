// GreenBinAI IoT — credentials template.
//
// Copy this file to `secrets.h` in the same directory and fill in real values:
//
//     cp iot/firmware/include/secrets.example.h iot/firmware/include/secrets.h
//
// `secrets.h` is gitignored. NEVER commit real credentials (spec §17, §26).
//
// Note on naming: the specification (§17) calls for `config.example.h`. Splitting
// secrets out from tunables is strictly safer — `config.h` stays committed and
// reviewable while only this small file carries anything sensitive — so the name
// was adapted, as permitted by spec §5.
//
// The device stores ONLY these four things. It never holds a cloud Vision API
// key of any kind; all model access happens on the backend (spec §8, §26).
#pragma once

#define WIFI_SSID "your-wifi-ssid"
#define WIFI_PASSWORD "your-wifi-password"

#define DEVICE_ID "GBIN-001"
#define BIN_CODE "BIN-001"

// No trailing slash. Use the LAN IP of the machine running the FastAPI backend.
#define BACKEND_BASE_URL "http://192.168.1.100:8000"

// Must match an entry in the backend's IOT_DEVICE_KEYS setting.
#define DEVICE_KEY "replace-with-the-key-issued-by-the-backend"
