"""Khoảng cách đường đi thật, lấy từ dịch vụ định tuyến ngoài (OSRM).

Bài toán thứ tự ghé điểm dừng vốn chạy trên **đường chim bay** (``haversine_km``).
Module này là bản nâng **tuỳ chọn**: hỏi một dịch vụ định tuyến xem đi thật hết
bao nhiêu ki-lô-mét, rồi đưa con số đó cho cùng thuật toán nearest-neighbour +
2-opt đang dùng.

Ba ràng buộc, đừng nới:

- **Mặc định TẮT** (``ROUTE_REAL_DISTANCE=false``). Không bật thì không có lệnh
  gọi mạng nào, sản phẩm chạy y như trước.
- **Một lệnh gọi cho cả tuyến.** Lấy nguyên ma trận n×n một lần. Gọi mạng bên
  trong vòng lặp 2-opt (``O(n³)``) là treo máy chủ.
- **Hỏng thì rơi êm về haversine.** Dịch vụ ngoài không phải thứ được phép làm
  hỏng màn duyệt tuyến.

⚠️ OSRM nhận toạ độ theo thứ tự **kinh độ trước, vĩ độ sau** (``lng,lat``) —
ngược với thứ tự ``(lat, lng)`` mà cả repo này đang dùng. Đổi nhầm thì mọi điểm
rơi xuống biển và ma trận trả về vẫn "hợp lệ", chỉ là sai hoàn toàn.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)


def ma_tran_km(toa_do: list[tuple[float, float]]) -> list[list[float]] | None:
    """Ma trận khoảng cách đường đi thật giữa mọi cặp điểm, đơn vị ki-lô-mét.

    Args:
        toa_do: danh sách ``(lat, lng)`` theo đúng thứ tự điểm dừng.

    Returns:
        Ma trận n×n, hoặc ``None`` khi tắt cờ / thiếu toạ độ / gọi hỏng / dữ liệu
        trả về không đúng hình dạng. ``None`` là tín hiệu "hãy dùng haversine".
    """
    settings = get_settings()
    if not settings.route_real_distance:
        return None
    if len(toa_do) < 2:
        return None

    # OSRM nhận toạ độ theo thứ tự lng,lat — ngược với (lat, lng) của repo.
    diem = ";".join(f"{lng},{lat}" for lat, lng in toa_do)
    url = f"{settings.osrm_base_url}/table/v1/driving/{diem}?annotations=distance"

    try:
        with httpx.Client(timeout=settings.osrm_timeout_seconds) as khach:
            phan_hoi = khach.get(url)
            phan_hoi.raise_for_status()
            du_lieu = phan_hoi.json()
        distances = du_lieu.get("distances")
        if not _la_ma_tran_vuong(distances, len(toa_do)):
            return None
        return [[met / 1000.0 for met in dong] for dong in distances]
    except Exception as loi:
        logger.warning("Không lấy được ma trận đường đi thật, dùng đường chim bay: %s", loi)
        return None


def _la_ma_tran_vuong(gia_tri: object, n: int) -> bool:
    """Phản hồi có phải ma trận n×n toàn số không (OSRM trả bằng mét)."""
    if not isinstance(gia_tri, list) or len(gia_tri) != n:
        return False
    for dong in gia_tri:
        if not isinstance(dong, list) or len(dong) != n:
            return False
        if not all(isinstance(m, (int, float)) for m in dong):
            return False
    return True


def hinh_duong_di(toa_do: list[tuple[float, float]]) -> list[tuple[float, float]] | None:
    """Hình đường đi thật nối các điểm dừng theo đúng thứ tự đã xếp.

    Args:
        toa_do: danh sách ``(lat, lng)`` theo đúng thứ tự ghé.

    Returns:
        Danh sách ``(lat, lng)`` dày hơn đầu vào — là các đoạn đường thật để vẽ
        lên bản đồ. ``None`` khi tắt cờ / dưới 2 điểm / gọi hỏng / dữ liệu trả về
        sai hình dạng. ``None`` là tín hiệu "vẽ nét đứt thẳng như cũ".
    """
    settings = get_settings()
    if not settings.route_real_distance:
        return None
    if len(toa_do) < 2:
        return None

    # OSRM nhận toạ độ theo thứ tự lng,lat — ngược với (lat, lng) của repo.
    diem = ";".join(f"{lng},{lat}" for lat, lng in toa_do)
    url = f"{settings.osrm_base_url}/route/v1/driving/{diem}?overview=full&geometries=geojson"

    try:
        with httpx.Client(timeout=settings.osrm_timeout_seconds) as khach:
            phan_hoi = khach.get(url)
            phan_hoi.raise_for_status()
            du_lieu = phan_hoi.json()
        hinh = _hinh_tu_geojson(du_lieu)
        if hinh is None or len(hinh) < 2:
            return None
        return hinh
    except Exception as loi:
        logger.warning("Không lấy được hình đường đi thật, vẽ đường chim bay: %s", loi)
        return None


def _hinh_tu_geojson(du_lieu: object) -> list[tuple[float, float]] | None:
    """Đọc ``routes[0].geometry.coordinates`` của OSRM.

    GeoJSON trả ``[lng, lat]`` — phải đảo về ``(lat, lng)`` cho khớp quy ước của
    cả repo. Sai chiều thì đường vẽ ra nằm ở Somalia mà không có lỗi nào.
    """
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


def ham_do_tu_ma_tran(
    ma_tran: list[list[float]], chi_so: dict[str, int]
) -> Callable[[Any, Any], float | None]:
    """Trả về một hàm đo khoảng cách tra bảng, đúng khuôn ``sap_thu_tu`` cần.

    Cặp điểm không có trong bảng thì hàm trả về ``None`` để chỗ gọi tự quyết —
    KHÔNG tự bịa một con số.
    """

    def _do(a: Any, b: Any) -> float | None:
        i = chi_so.get(a.diem_id)
        j = chi_so.get(b.diem_id)
        if i is None or j is None:
            return None
        return ma_tran[i][j]

    return _do
