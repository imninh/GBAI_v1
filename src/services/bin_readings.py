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

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Bin, utcnow
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
    session: Session | None = None,
) -> BinReading:
    """Validate and store a reading from a device.

    Có truyền ``session`` thì ghi xuống **CSDL thật** qua
    :func:`src.services.bins.ghi_nhan_reading` (bảng ``bin_readings``), kèm pin và
    nguồn mặc định; trả về cùng khuôn :class:`BinReading` như đường cũ. Không có
    ``session`` thì giữ hành vi cũ — ghi vào kho trong bộ nhớ tiến trình.

    Args:
        session: phiên CSDL. ``None`` = dùng kho in-memory (đường cũ, test cũ
            không đổi hành vi).

    Raises:
        ValueError: khi mức rác ngoài 0–100, hoặc (với ``session``) thùng theo
            ``bin_code`` không tồn tại — chỗ gọi phải nuốt để không làm hỏng
            luồng chính (xem ``create_capture`` trong ``iot.py``).
    """
    # Defence in depth: the schema bounds this too, but a fill percentage
    # outside 0–100 must never reach storage (spec §13).
    if not 0.0 <= fill_percent <= 100.0:
        raise ValueError(f"fill_percent out of range: {fill_percent}")

    if session is not None:
        thung = session.scalar(select(Bin).where(Bin.code == bin_code))
        if thung is None:
            raise ValueError(f"bin not found: {bin_code}")

        from src.services.bins import ghi_nhan_reading

        now = utcnow()
        ghi_nhan_reading(
            session,
            thung,
            fill_percent=fill_percent,
            battery_percent=100.0,
            source="device",
            now=now,
        )
        return BinReading(
            reading_id=str(uuid.uuid4()),
            bin_code=bin_code,
            device_id=device_id,
            fill_percent=fill_percent,
            is_full=is_full,
            uptime_s=uptime_s,
            recorded_at=now,
        )

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
