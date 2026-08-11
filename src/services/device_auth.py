"""Device authentication via the ``X-Device-Key`` header (spec §8).

Keys are configured as ``device_id:key`` pairs so a stolen key cannot be used to
impersonate a different bin:

    IOT_DEVICE_KEYS=GBIN-001:key-one,GBIN-002:key-two
"""

from __future__ import annotations

import secrets
from functools import lru_cache

from src.config import get_settings


class DeviceAuthError(Exception):
    """Raised when a device presents no key or a bad one."""


@lru_cache
def _key_table() -> dict[str, str]:
    settings = get_settings()
    table: dict[str, str] = {}
    for entry in settings.iot_device_keys.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        device_id, _, key = entry.partition(":")
        device_id, key = device_id.strip(), key.strip()
        if device_id and key:
            table[device_id] = key
    return table


def reset_cache() -> None:
    """Test hook: re-read settings after they are patched."""
    _key_table.cache_clear()


def authenticate(device_key: str | None, device_id: str | None = None) -> str:
    """Verify a device key and return the authenticated device id.

    Raises :class:`DeviceAuthError` on any failure. Callers must not distinguish
    "unknown device" from "wrong key" in their response — that difference tells
    an attacker which half they got right.
    """
    if not device_key:
        raise DeviceAuthError("Missing X-Device-Key header")

    table = _key_table()
    if not table:
        raise DeviceAuthError("No device keys configured on the server")

    if device_id:
        expected = table.get(device_id)
        # compare_digest even on the miss path, so the timing of a wrong device
        # id matches the timing of a wrong key.
        if expected is None or not secrets.compare_digest(expected, device_key):
            raise DeviceAuthError("Invalid device credentials")
        return device_id

    # No device id claimed: accept any configured key and report whose it was.
    for known_id, known_key in table.items():
        if secrets.compare_digest(known_key, device_key):
            return known_id

    raise DeviceAuthError("Invalid device credentials")
