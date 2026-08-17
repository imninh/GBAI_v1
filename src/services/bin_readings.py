"""Bin fill-level readings.

Storage sits behind a repository interface so the in-memory implementation can
be swapped for SQLAlchemy without touching the router or the device contract.

KNOWN LIMITATION (Phase 1): the default repository is in-memory and does not
survive a restart. The repository interface — not a database — is the part that
matters for the device contract; persistence is tracked in
iot/docs/IMPLEMENTATION_REPORT.md under "Known issues".
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from src.models.schemas import BinReading


class BinReadingRepository(ABC):
    @abstractmethod
    def add(self, reading: BinReading) -> None: ...

    @abstractmethod
    def list_for_bin(self, bin_code: str, limit: int = 50) -> list[BinReading]: ...

    @abstractmethod
    def latest(self, bin_code: str) -> BinReading | None: ...


class InMemoryBinReadingRepository(BinReadingRepository):
    def __init__(self) -> None:
        self._readings: dict[str, list[BinReading]] = {}

    def add(self, reading: BinReading) -> None:
        self._readings.setdefault(reading.bin_code, []).append(reading)

    def list_for_bin(self, bin_code: str, limit: int = 50) -> list[BinReading]:
        return self._readings.get(bin_code, [])[-limit:]

    def latest(self, bin_code: str) -> BinReading | None:
        readings = self._readings.get(bin_code)
        return readings[-1] if readings else None

    def clear(self) -> None:
        """Test hook — keeps state from leaking between test cases."""
        self._readings.clear()


_repository = InMemoryBinReadingRepository()


def get_repository() -> BinReadingRepository:
    return _repository


def record_reading(
    bin_code: str,
    device_id: str,
    fill_percent: float,
    is_full: bool,
    uptime_s: int = 0,
) -> BinReading:
    """Validate and store a reading from a device."""
    # Defence in depth: the schema bounds this too, but a fill percentage
    # outside 0–100 must never reach storage (spec §13).
    if not 0.0 <= fill_percent <= 100.0:
        raise ValueError(f"fill_percent out of range: {fill_percent}")

    reading = BinReading(
        reading_id=str(uuid.uuid4()),
        bin_code=bin_code,
        device_id=device_id,
        fill_percent=fill_percent,
        is_full=is_full,
        uptime_s=uptime_s,
        recorded_at=datetime.now(UTC),
    )
    _repository.add(reading)
    return reading
