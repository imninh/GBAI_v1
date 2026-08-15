"""Khoảng cách và lộ trình đường đi thật, lấy từ dịch vụ định tuyến ngoài (OSRM).

Hỗ trợ 3 giai đoạn của pipeline định tuyến:
1. **OSRM Table API** (`ma_tran_osrm`): Lấy đồng thời ma trận khoảng cách (km) và
   thời gian di chuyển (giây) cho PyVRP.
2. **OSRM Route API** (`lo_trinh`, `hinh_duong_di`): Lấy polyline tim đường và
   metadata lộ trình (tổng km, tổng phút, thông tin từng chặng).
3. **OSRM Match API** (`snap_gps`): Nắn các điểm toạ độ GPS thô vào tim đường thật
   cho tính năng tracking thời gian thực.

Quy tắc cốt lõi:
- **Mặc định TẮT** (``ROUTE_REAL_DISTANCE=false``). Không bật thì không có lệnh gọi mạng nào.
- **Hỏng thì rơi êm** (graceful fallback). Dịch vụ ngoài không được phép làm hỏng nghiệp vụ.
- **Toạ độ OSRM**: Nhận ``lng,lat`` — ngược với ``(lat, lng)`` của repo. Phải chuyển đổi chuẩn xác.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class MatranOSRM:
    """Ma trận khoảng cách và thời gian giữa mọi cặp điểm."""

    distances_km: list[list[float]] = field(default_factory=list)
    durations_s: list[list[float]] = field(default_factory=list)


@dataclass
class LegInfo:
    """Thông tin một chặng di chuyển giữa 2 điểm dừng liên tiếp."""

    distance_km: float
    duration_minutes: float


@dataclass
class LoTrinh:
    """Lộ trình chi tiết theo đường đi thật từ OSRM Route API."""

    polyline: list[tuple[float, float]] = field(default_factory=list)
    total_km: float = 0.0
    total_minutes: float = 0.0
    legs: list[LegInfo] = field(default_factory=list)


def ma_tran_osrm(toa_do: list[tuple[float, float]]) -> MatranOSRM | None:
    """Ma trận khoảng cách (km) và thời gian (giây) giữa mọi cặp điểm.

    Args:
        toa_do: danh sách ``(lat, lng)`` theo đúng thứ tự điểm dừng.

    Returns:
        MatranOSRM chứa 2 ma trận n×n, hoặc ``None`` khi tắt cờ / thiếu toạ độ / lỗi mạng.
    """
    settings = get_settings()
    if not settings.route_real_distance:
        return None
    if len(toa_do) < 2:
        return None

    diem = ";".join(f"{lng},{lat}" for lat, lng in toa_do)
    url = f"{settings.osrm_base_url}/table/v1/driving/{diem}?annotations=distance,duration"

    try:
        with httpx.Client(timeout=settings.osrm_timeout_seconds) as khach:
            phan_hoi = khach.get(url)
            phan_hoi.raise_for_status()
            du_lieu = phan_hoi.json()

        distances = du_lieu.get("distances")
        durations = du_lieu.get("durations")
        n = len(toa_do)

        if not _la_ma_tran_vuong(distances, n):
            return None

        dist_km = [[float(met) / 1000.0 for met in dong] for dong in distances]

        if _la_ma_tran_vuong(durations, n):
            dur_s = [[float(sec) for sec in dong] for dong in durations]
        else:
            # Nếu OSRM không trả duration thì ước lượng từ khoảng cách (30 km/h)
            dur_s = [[(d * 1000.0) / (30.0 / 3.6) for d in dong] for dong in dist_km]

        return MatranOSRM(distances_km=dist_km, durations_s=dur_s)
    except Exception as loi:
        logger.warning("Không lấy được ma trận OSRM, rơi về đường chim bay: %s", loi)
        return None


def ma_tran_km(toa_do: list[tuple[float, float]]) -> list[list[float]] | None:
    """Ma trận khoảng cách đường đi thật giữa mọi cặp điểm, đơn vị km (backward compatible)."""
    kq = ma_tran_osrm(toa_do)
    return kq.distances_km if kq is not None else None


def _la_ma_tran_vuong(gia_tri: object, n: int) -> bool:
    """Phản hồi có phải ma trận n×n toàn số không."""
    if not isinstance(gia_tri, list) or len(gia_tri) != n:
        return False
    for dong in gia_tri:
        if not isinstance(dong, list) or len(dong) != n:
            return False
        if not all(isinstance(m, (int, float)) for m in dong):
            return False
    return True


def lo_trinh(toa_do: list[tuple[float, float]]) -> LoTrinh | None:
    """Lộ trình chi tiết nối các điểm dừng theo đúng thứ tự ghé.

    Args:
        toa_do: danh sách ``(lat, lng)`` theo đúng thứ tự ghé.

    Returns:
        LoTrinh chứa polyline, total_km, total_minutes, legs; hoặc None khi lỗi/tắt cờ.
    """
    settings = get_settings()
    if not settings.route_real_distance:
        return None
    if len(toa_do) < 2:
        return None

    diem = ";".join(f"{lng},{lat}" for lat, lng in toa_do)
    url = f"{settings.osrm_base_url}/route/v1/driving/{diem}?overview=full&geometries=geojson&steps=true"

    try:
        with httpx.Client(timeout=settings.osrm_timeout_seconds) as khach:
            phan_hoi = khach.get(url)
            phan_hoi.raise_for_status()
            du_lieu = phan_hoi.json()

        if not isinstance(du_lieu, dict):
            return None
        routes = du_lieu.get("routes")
        if not isinstance(routes, list) or not routes:
            return None

        route_0 = routes[0]
        if not isinstance(route_0, dict):
            return None

        hinh = _hinh_tu_geojson(du_lieu)
        if hinh is None or len(hinh) < 2:
            return None

        total_km = round(float(route_0.get("distance", 0.0)) / 1000.0, 2)
        total_min = round(float(route_0.get("duration", 0.0)) / 60.0, 1)

        raw_legs = route_0.get("legs", [])
        legs: list[LegInfo] = []
        if isinstance(raw_legs, list):
            for l_item in raw_legs:
                if isinstance(l_item, dict):
                    l_dist = round(float(l_item.get("distance", 0.0)) / 1000.0, 2)
                    l_dur = round(float(l_item.get("duration", 0.0)) / 60.0, 1)
                    legs.append(LegInfo(distance_km=l_dist, duration_minutes=l_dur))

        return LoTrinh(
            polyline=hinh,
            total_km=total_km,
            total_minutes=total_min,
            legs=legs,
        )
    except Exception as loi:
        logger.warning("Không lấy được lộ trình thật từ OSRM: %s", loi)
        return None


def hinh_duong_di(toa_do: list[tuple[float, float]]) -> list[tuple[float, float]] | None:
    """Hình đường đi thật nối các điểm dừng theo đúng thứ tự (backward compatible)."""
    lt = lo_trinh(toa_do)
    return lt.polyline if lt is not None else None


def _hinh_tu_geojson(du_lieu: object) -> list[tuple[float, float]] | None:
    """Đọc ``routes[0].geometry.coordinates`` của OSRM và đảo [lng, lat] về (lat, lng)."""
    if not isinstance(du_lieu, dict):
        return None
    routes = du_lieu.get("routes")
    if not isinstance(routes, list) or not routes:
        return None
    geometry = routes[0].get("geometry") if isinstance(routes[0], dict) else None
    if not isinstance(geometry, dict):
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None

    ket_qua: list[tuple[float, float]] = []
    for diem in coordinates:
        if not isinstance(diem, list) or len(diem) < 2:
            return None
        try:
            lng, lat = float(diem[0]), float(diem[1])
        except (TypeError, ValueError):
            return None
        ket_qua.append((lat, lng))
    return ket_qua


def snap_gps(
    points: list[tuple[float, float]],
    timestamps: list[int] | None = None,
) -> list[tuple[float, float]] | None:
    """Snap danh sách toạ độ GPS thô vào tim đường thật bằng OSRM Match API.

    Args:
        points: Danh sách ``(lat, lng)`` thu thập từ thiết bị.
        timestamps: Danh sách unix epoch timestamps tương ứng (tuỳ chọn).

    Returns:
        Danh sách ``(lat, lng)`` đã snap vào đường, hoặc ``None`` nếu thất bại.
    """
    settings = get_settings()
    if not settings.route_real_distance:
        return None
    if len(points) < 2:
        return points if points else None

    diem = ";".join(f"{lng},{lat}" for lat, lng in points)
    url = f"{settings.osrm_base_url}/match/v1/driving/{diem}?overview=simplified&geometries=geojson"
    if timestamps and len(timestamps) == len(points):
        url += f"&timestamps={';'.join(str(int(t)) for t in timestamps)}"

    try:
        with httpx.Client(timeout=settings.osrm_timeout_seconds) as khach:
            phan_hoi = khach.get(url)
            phan_hoi.raise_for_status()
            du_lieu = phan_hoi.json()

        if not isinstance(du_lieu, dict):
            return None

        tracepoints = du_lieu.get("tracepoints")
        if isinstance(tracepoints, list) and len(tracepoints) == len(points):
            snapped: list[tuple[float, float]] = []
            for i, tp in enumerate(tracepoints):
                if isinstance(tp, dict) and "location" in tp:
                    loc = tp["location"]
                    if isinstance(loc, list) and len(loc) >= 2:
                        snapped.append((float(loc[1]), float(loc[0])))
                        continue
                snapped.append(points[i])
            return snapped

        # Fallback: đọc từ matchings[0].geometry nếu không có tracepoints
        matchings = du_lieu.get("matchings")
        if isinstance(matchings, list) and matchings:
            coords = matchings[0].get("geometry", {}).get("coordinates", [])
            if isinstance(coords, list) and len(coords) >= 2:
                return [(float(c[1]), float(c[0])) for c in coords if isinstance(c, list) and len(c) >= 2]

        return points
    except Exception as loi:
        logger.warning("Không snap được GPS bằng OSRM Match: %s", loi)
        return points


def ham_do_tu_ma_tran(
    ma_tran: list[list[float]], chi_so: dict[str, int]
) -> Callable[[Any, Any], float | None]:
    """Trả về hàm đo khoảng cách tra bảng theo km."""

    def _do(a: Any, b: Any) -> float | None:
        i = chi_so.get(a.diem_id)
        j = chi_so.get(b.diem_id)
        if i is None or j is None:
            return None
        return ma_tran[i][j]

    return _do


def ham_do_thoi_gian_tu_ma_tran(
    durations_s: list[list[float]], chi_so: dict[str, int]
) -> Callable[[Any, Any], float | None]:
    """Trả về hàm tra cứu thời gian di chuyển theo giây."""

    def _do(a: Any, b: Any) -> float | None:
        i = chi_so.get(a.diem_id)
        j = chi_so.get(b.diem_id)
        if i is None or j is None:
            return None
        return durations_s[i][j]

    return _do
