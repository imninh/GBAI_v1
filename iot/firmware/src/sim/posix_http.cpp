#include "sim/posix_http.h"

#include <netdb.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#include <cstdlib>

namespace greenbin {
namespace sim {

namespace {

struct ParsedUrl {
    bool ok = false;
    std::string host;
    std::string port = "80";
    std::string path = "/";
};

ParsedUrl parseUrl(const std::string& url) {
    ParsedUrl parsed;
    const std::string prefix = "http://";
    if (url.rfind(prefix, 0) != 0) {
        return parsed;  // https and other schemes are out of scope
    }

    const std::string rest = url.substr(prefix.size());
    const size_t slash = rest.find('/');
    std::string authority = (slash == std::string::npos) ? rest : rest.substr(0, slash);
    if (slash != std::string::npos) {
        parsed.path = rest.substr(slash);
    }

    const size_t colon = authority.find(':');
    if (colon == std::string::npos) {
        parsed.host = authority;
    } else {
        parsed.host = authority.substr(0, colon);
        parsed.port = authority.substr(colon + 1);
    }

    parsed.ok = !parsed.host.empty();
    return parsed;
}

void setTimeout(int fd, uint32_t timeoutMs) {
    timeval tv;
    tv.tv_sec = static_cast<time_t>(timeoutMs / 1000);
    tv.tv_usec = static_cast<suseconds_t>((timeoutMs % 1000) * 1000);
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
}

}  // namespace

HttpResponse post(const HttpRequest& request) {
    HttpResponse response;

    const ParsedUrl url = parseUrl(request.url);
    if (!url.ok) {
        response.error = "Unsupported or malformed URL: " + request.url;
        return response;
    }

    addrinfo hints{};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    addrinfo* addresses = nullptr;
    if (getaddrinfo(url.host.c_str(), url.port.c_str(), &hints, &addresses) != 0) {
        response.error = "DNS resolution failed for " + url.host;
        return response;
    }

    int fd = -1;
    for (addrinfo* candidate = addresses; candidate != nullptr;
         candidate = candidate->ai_next) {
        fd = socket(candidate->ai_family, candidate->ai_socktype, candidate->ai_protocol);
        if (fd < 0) {
            continue;
        }
        setTimeout(fd, request.timeoutMs);
        if (connect(fd, candidate->ai_addr, candidate->ai_addrlen) == 0) {
            break;
        }
        close(fd);
        fd = -1;
    }
    freeaddrinfo(addresses);

    if (fd < 0) {
        // This is the path scenario 6 exercises: backend down.
        response.error = "Connection refused or timed out";
        return response;
    }

    std::string head = "POST " + url.path + " HTTP/1.1\r\n";
    head += "Host: " + url.host + ":" + url.port + "\r\n";
    head += "Content-Type: " + request.contentType + "\r\n";
    head += "Content-Length: " + std::to_string(request.body.size()) + "\r\n";
    if (!request.deviceKey.empty()) {
        head += "X-Device-Key: " + request.deviceKey + "\r\n";
    }
    head += "Connection: close\r\n\r\n";

    const std::string wire = head + request.body;
    size_t sent = 0;
    while (sent < wire.size()) {
        const ssize_t n = send(fd, wire.data() + sent, wire.size() - sent, 0);
        if (n <= 0) {
            close(fd);
            response.error = "Send failed";
            return response;
        }
        sent += static_cast<size_t>(n);
    }

    std::string raw;
    char buffer[4096];
    for (;;) {
        const ssize_t n = recv(fd, buffer, sizeof(buffer), 0);
        if (n > 0) {
            raw.append(buffer, static_cast<size_t>(n));
            continue;
        }
        if (n == 0) {
            break;  // peer closed — expected with Connection: close
        }
        close(fd);
        response.error = raw.empty() ? "Read timed out" : "Read failed mid-response";
        return response;
    }
    close(fd);

    if (raw.rfind("HTTP/", 0) != 0) {
        response.error = "Malformed response";
        return response;
    }
    const size_t firstSpace = raw.find(' ');
    if (firstSpace == std::string::npos) {
        response.error = "Malformed status line";
        return response;
    }
    response.status = std::atoi(raw.c_str() + firstSpace + 1);

    const size_t split = raw.find("\r\n\r\n");
    if (split != std::string::npos) {
        response.body = raw.substr(split + 4);
    }
    return response;
}

}  // namespace sim
}  // namespace greenbin
