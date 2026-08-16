// Minimal blocking HTTP/1.1 client for the desktop simulator.
//
// Exists so the host simulator can speak to the real FastAPI backend over a
// real socket, rather than mocking the network as the unit tests do.
//
// SIMULATOR ONLY. Never compiled into firmware — the device uses
// src/hw/network_service.cpp (Arduino HTTPClient). Deliberately small: plain
// HTTP, no TLS, no chunked encoding, no redirects.
#pragma once

#include <stdint.h>

#include <string>

namespace greenbin {
namespace sim {

struct HttpResponse {
    // -1 = transport failure (DNS, connect, timeout). Otherwise the HTTP status.
    int status = -1;
    std::string body;
    std::string error;
};

struct HttpRequest {
    std::string url;  // http://host[:port]/path — https is not supported
    std::string contentType;
    std::string deviceKey;  // sent as X-Device-Key; never logged
    std::string body;
    uint32_t timeoutMs = 10000;
};

HttpResponse post(const HttpRequest& request);

}  // namespace sim
}  // namespace greenbin
