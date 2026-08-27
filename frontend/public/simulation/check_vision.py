#!/usr/bin/env python3
"""See what the camera sees, and what the model says about it.

When a capture comes back `refused`, there are three very different causes and
the device log cannot tell them apart:

  * the model never ran (bad key, wrong provider)
  * the model ran and answered, but the answer did not parse
  * the model ran and honestly said "I cannot identify a waste item here"

This runs the exact same path the device triggers — same preprocessing, same
prompt, same model — and prints the raw reply, so the cause is visible in one
command instead of a Wokwi round trip.

It also saves the frame to disk. Most `refused` results are a framing problem,
and you cannot fix framing you have not looked at.

    # what the webcam is showing right now
    .venv/bin/python iot/simulation/check_vision.py

    # a specific file
    .venv/bin/python iot/simulation/check_vision.py --image photo.jpg
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import sys
import urllib.request
from pathlib import Path

from src.agents.nodes.classify_nodes import CLASSIFY_PROMPT, _parse_model_reply
from src.config import get_settings
from src.services.classification import classify_processed_image
from src.services.image_privacy import ImageValidationError, preprocess_image
from src.services.vision import VisionProviderError, get_vision_model


def fetch(url: str, timeout: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return response.read()


async def run(raw: bytes, save_to: Path) -> int:
    settings = get_settings()

    print("── configuration ──")
    print(f"  provider   : {settings.vision_provider}")
    print(f"  model      : {settings.vision_model_name}")
    print(f"  endpoint   : {settings.vision_base_url or '(provider default)'}")
    # Never print the key itself — the length is enough to tell "filled in" from
    # "still the placeholder".
    print(f"  key length : {len(settings.openai_api_key)}")
    if settings.vision_provider.strip().lower() == "stub":
        print("\n  STUB PROVIDER: no image is analysed and the label is canned.")
        print("  Set VISION_PROVIDER=openai in .env for real classification.")

    save_to.write_bytes(raw)
    print(f"\n── image ──\n  captured   : {len(raw)} bytes")
    print(f"  saved to   : {save_to}  <- open it and look at it")

    try:
        processed = preprocess_image(raw)
    except ImageValidationError as exc:
        print(f"\n  REJECTED BY THE PRIVACY PIPELINE: {exc}")
        return 1

    print(f"  after prep : {processed.width}x{processed.height}, "
          f"{processed.size_bytes} bytes")
    print(f"  faces blurred: {processed.faces_blurred}   exif stripped: "
          f"{processed.exif_stripped}")

    try:
        model = get_vision_model()
    except VisionProviderError as exc:
        print(f"\n  NO USABLE PROVIDER: {exc}")
        return 1

    message = {
        "role": "user",
        "content": [
            {"type": "text", "text": CLASSIFY_PROMPT},
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,"
                    + base64.b64encode(processed.content).decode("ascii")
                },
            },
        ],
    }

    print("\n── raw model reply ──")
    try:
        reply = await model.ainvoke([message])
    except Exception as exc:  # noqa: BLE001 - provider SDKs raise many types
        print(f"  CALL FAILED: {type(exc).__name__}: {str(exc)[:400]}")
        return 1

    text = str(reply.content)
    print(f"  {text!r}")

    label, confidence = _parse_model_reply(text)
    print(f"\n── parsed ──\n  label={label!r} confidence={confidence}")

    outcome = await classify_processed_image(processed, source="check")
    print("\n── final outcome (what the device receives) ──")
    print(f"  status     : {outcome.status}")
    print(f"  label      : {outcome.label!r}")
    print(f"  confidence : {outcome.confidence}")
    print(f"  message    : {outcome.message}")

    print("\n── verdict ──")
    if outcome.status == "ok":
        print("  The device would SORT this item.")
        return 0
    if not label:
        print("  The model looked at the image and could not name a waste item.")
        print("  That is a framing problem, not a bug: fill more of the frame with")
        print("  the object, improve the lighting, and use a plain background.")
        print(f"  Look at {save_to} — if you cannot tell what it is, neither can the model.")
    else:
        print(f"  The model said {label!r} but the safety layer returned "
              f"{outcome.status!r}.")
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8124/frame.jpg",
        help="webcam service frame endpoint",
    )
    parser.add_argument("--image", help="use this file instead of the webcam")
    parser.add_argument("--save-to", default="/tmp/greenbin-check.jpg")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    if args.image:
        raw = Path(args.image).read_bytes()
    else:
        try:
            raw = fetch(args.url, args.timeout)
        except Exception as exc:  # noqa: BLE001
            print(f"cannot reach the webcam service at {args.url}: {exc}")
            print("start it with:  .venv/bin/python iot/simulation/webcam_service.py")
            return 1

    return asyncio.run(run(raw, Path(args.save_to)))


if __name__ == "__main__":
    sys.exit(main())
