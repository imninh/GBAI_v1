#!/usr/bin/env python3
"""Webcam frame server — a stand-in for the OV2640 during simulation.

Wokwi cannot simulate a camera, so for a demo that classifies *real* items the
image has to come from somewhere real. This serves one JPEG per request from the
PC's webcam; the simulated ESP32 fetches it and then uploads it to the backend
exactly as it would upload a frame from its own sensor.

    Webcam → this service → ESP32 (Wokwi) → POST /api/v1/iot/captures → classifier

The ESP32 leg is deliberately kept: the device still holds the JPEG in its own
RAM and still builds the multipart request itself, so nothing about the
device↔backend contract is skipped. Only the image *sensor* has moved.

Run it:

    .venv/bin/python iot/simulation/webcam_service.py

PRIVACY: the ESP32 lives on the Wokwi gateway's virtual network, not on
localhost, so this binds to 0.0.0.0 by default — anyone on your LAN who guesses
the port can pull a webcam frame. Run it only for the length of the demo, or
pass --host to bind somewhere narrower.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import cv2
except ImportError:  # pragma: no cover - environment problem, not a code path
    sys.exit("opencv-python is required:  .venv/bin/pip install opencv-python")


class Camera:
    """One webcam, opened once and shared under a lock.

    Opening a V4L2 device costs about a second and re-running auto-exposure, so
    the device is held open for the life of the demo. That does mean the camera
    indicator light stays on.
    """

    def __init__(
        self,
        index: int,
        capture_width: int,
        capture_height: int,
        width: int,
        height: int,
        quality: int,
        max_bytes: int,
    ) -> None:
        self._index = index
        self._capture_width = capture_width
        self._capture_height = capture_height
        self._width = width
        self._height = height
        self._quality = quality
        self._max_bytes = max_bytes
        self._lock = threading.Lock()
        self._capture: cv2.VideoCapture | None = None

    def _open(self) -> cv2.VideoCapture:
        capture = cv2.VideoCapture(self._index, cv2.CAP_V4L2)
        if not capture.isOpened():
            raise RuntimeError(f"cannot open camera index {self._index}")
        # Grab at the sensor's best mode and downscale afterwards: a 1280x720
        # frame reduced to 1024x576 carries far more usable detail than asking
        # the sensor for 640x360 directly, and detail is exactly what the
        # classifier needs.
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._capture_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._capture_height)
        # First frames come out black or badly exposed while auto-exposure
        # settles; throwing them away is cheaper than shipping a useless image.
        for _ in range(5):
            capture.read()
        return capture

    def actual_size(self) -> tuple[int, int]:
        """What the driver actually gave us.

        A webcam silently snaps to its nearest supported mode, so asking for
        480x360 can yield 640x360. Reporting the request rather than the result
        would understate the bytes the ESP32 has to hold.
        """
        with self._lock:
            if self._capture is None:
                return (0, 0)
            return (
                int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )

    def grab_jpeg(self) -> bytes:
        with self._lock:
            if self._capture is None:
                self._capture = self._open()

            ok, frame = self._capture.read()
            if not ok or frame is None:
                # Reopen once: a USB webcam that was unplugged and replugged
                # comes back on the same index.
                self._capture.release()
                self._capture = self._open()
                ok, frame = self._capture.read()
                if not ok or frame is None:
                    raise RuntimeError("camera returned no frame")

            if frame.shape[1] != self._width or frame.shape[0] != self._height:
                frame = cv2.resize(
                    frame, (self._width, self._height), interpolation=cv2.INTER_AREA
                )

            # A busy scene compresses worse than a plain one, so a fixed quality
            # can overflow the device's buffer on exactly the interesting frames.
            # Step the quality down rather than fail the capture.
            for quality in range(self._quality, 24, -10):
                ok, buffer = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality]
                )
                if not ok:
                    raise RuntimeError("JPEG encoding failed")
                if len(buffer) <= self._max_bytes:
                    if quality != self._quality:
                        print(
                            f"[WEBCAM] busy scene: dropped quality to {quality} "
                            f"to fit {self._max_bytes} bytes",
                            flush=True,
                        )
                    return buffer.tobytes()

            # Still too big at the lowest quality we are willing to use. Report
            # it instead of sending something the device will refuse.
            raise RuntimeError(
                f"frame will not fit in {self._max_bytes} bytes; lower --width"
            )

    def close(self) -> None:
        with self._lock:
            if self._capture is not None:
                self._capture.release()
                self._capture = None


def make_handler(camera: Camera, max_bytes: int):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            # The ESP32 sizes its buffer from Content-Length before reading, so
            # this must be exact and the response must not be chunked.
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = self.path.split("?", 1)[0]

            if path in ("/health", "/"):
                self._send(200, b'{"status":"ok"}\n', "application/json")
                return

            if path != "/frame.jpg":
                self._send(404, b"not found\n", "text/plain")
                return

            started = time.monotonic()
            try:
                jpeg = camera.grab_jpeg()
            except Exception as exc:  # noqa: BLE001 - report, never fake a frame
                print(f"[WEBCAM] capture failed: {exc}", flush=True)
                # 503, not an empty 200: the device must be able to tell a
                # failure from a picture of a dark room.
                self._send(503, f"capture failed: {exc}\n".encode(), "text/plain")
                return

            if len(jpeg) > max_bytes:
                print(
                    f"[WEBCAM] frame {len(jpeg)}B exceeds --max-bytes {max_bytes}; "
                    "lower --quality or --width",
                    flush=True,
                )
                self._send(507, b"frame too large for the device\n", "text/plain")
                return

            elapsed = (time.monotonic() - started) * 1000
            print(f"[WEBCAM] served {len(jpeg)} bytes in {elapsed:.0f} ms", flush=True)
            self._send(200, jpeg, "image/jpeg")

        def log_message(self, *_args) -> None:
            """Silence the default per-request logging; we print our own."""

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - see module docstring
    parser.add_argument("--port", type=int, default=8124)
    parser.add_argument("--device", type=int, default=0, help="/dev/videoN index")
    parser.add_argument("--capture-width", type=int, default=1280, help="sensor mode")
    parser.add_argument("--capture-height", type=int, default=720, help="sensor mode")
    # 1024 is exactly what the backend keeps (TARGET_MAX_EDGE in
    # services/image_privacy.py), so sending more would be discarded anyway.
    parser.add_argument("--width", type=int, default=1024, help="encoded width")
    parser.add_argument("--height", type=int, default=576, help="encoded height")
    parser.add_argument("--quality", type=int, default=65, help="JPEG quality 1-100")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=48 * 1024,
        help="refuse to serve frames larger than this; the ESP32 has ~200 KB of heap",
    )
    args = parser.parse_args()

    # Python block-buffers stdout when it is not a terminal, which would hide
    # every line until exit if the demo pipes this into a log file.
    sys.stdout.reconfigure(line_buffering=True)

    camera = Camera(
        args.device,
        args.capture_width,
        args.capture_height,
        args.width,
        args.height,
        args.quality,
        args.max_bytes,
    )

    # Fail at startup rather than on the first PIR trigger in front of an
    # audience.
    try:
        first = camera.grab_jpeg()
    except Exception as exc:  # noqa: BLE001
        print(f"[WEBCAM] cannot start: {exc}", file=sys.stderr)
        return 1
    width, height = camera.actual_size()
    print(f"[WEBCAM] camera {args.device} ok, first frame {len(first)} bytes")

    server = ThreadingHTTPServer(
        (args.host, args.port), make_handler(camera, args.max_bytes)
    )
    print(f"[WEBCAM] serving http://{args.host}:{args.port}/frame.jpg")
    print(
        f"[WEBCAM] sensor {width}x{height} -> sending {args.width}x{args.height} "
        f"quality={args.quality}"
    )
    print(f"[WEBCAM] device buffer limit {args.max_bytes} bytes")
    if args.host == "0.0.0.0":  # noqa: S104
        print("[WEBCAM] WARNING: bound to all interfaces — anyone on this LAN can")
        print("[WEBCAM]          fetch a webcam frame. Stop it after the demo.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[WEBCAM] stopping")
    finally:
        server.server_close()
        camera.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
