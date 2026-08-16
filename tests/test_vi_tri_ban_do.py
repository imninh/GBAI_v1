"""Khoá cửa cho icon "vị trí của bạn" + đường tới thùng đang chọn (gói P43c).

Quét file `.tsx` dưới dạng văn bản (đúng khuôn ``test_di_tru_trang_thai.py``):
không chạy JS, không chạm mạng. Giữ ba thứ: BinMap import ``Polyline``, hai prop
mới tuỳ chọn ``null`` (nên màn quản lý không đổi), và thứ tự ``[lat, lng]`` của
Leaflet ở cả Marker lẫn Polyline.
"""

from __future__ import annotations

from pathlib import Path

GOC_DU_AN = Path(__file__).resolve().parents[1]

BIN_MAP = GOC_DU_AN / "frontend" / "src" / "components" / "bins" / "bin-map.tsx"
NEARBY = GOC_DU_AN / "frontend" / "src" / "components" / "resident" / "nearby-bins.tsx"
DIEU_PHOI = GOC_DU_AN / "frontend" / "src" / "app" / "dieu-phoi" / "page.tsx"
CONSOLE = GOC_DU_AN / "frontend" / "src" / "components" / "manager" / "console.tsx"


def test_bin_map_import_polyline() -> None:
    """Dòng import từ "react-leaflet" phải có `Polyline`."""
    noi_dung = BIN_MAP.read_text(encoding="utf-8")
    dong_import = next(d for d in noi_dung.splitlines() if "react-leaflet" in d and "import" in d)
    assert "Polyline" in dong_import


def test_bin_map_co_hai_prop() -> None:
    """BinMap khai đủ `viTriNguoiDung` và `tuMoc`."""
    noi_dung = BIN_MAP.read_text(encoding="utf-8")
    assert "viTriNguoiDung" in noi_dung
    assert "tuMoc" in noi_dung


def test_marker_dung_thu_tu_lat_lng() -> None:
    """Marker "bạn ở đây" phải dùng `[lat, lng]` — đảo thành `[lng, lat]` là
    marker rơi ra giữa biển. (Polyline cũng phải theo thứ tự này — xem REPORT.)"""
    noi_dung = BIN_MAP.read_text(encoding="utf-8")
    assert "[viTriNguoiDung.lat, viTriNguoiDung.lng]" in noi_dung
    assert "[viTriNguoiDung.lng, viTriNguoiDung.lat]" not in noi_dung
    # Đường nối từ mốc tới thùng cũng phải theo đúng thứ tự lat, lng.
    assert "[tuMoc.lat, tuMoc.lng]" in noi_dung


def test_nearby_truyen_prop() -> None:
    """Màn cư dân truyền `viTriGps` và `mocToaDo` vào BinMap."""
    noi_dung = NEARBY.read_text(encoding="utf-8")
    assert "viTriNguoiDung={viTriGps}" in noi_dung
    assert "tuMoc={mocToaDo}" in noi_dung


def test_dieu_phoi_khong_doi() -> None:
    """Bản đồ quản lý không được đổi hành vi — không chứa prop mới."""
    for tep in (DIEU_PHOI, CONSOLE):
        noi_dung = tep.read_text(encoding="utf-8")
        assert "viTriNguoiDung" not in noi_dung, f"{tep.relative_to(GOC_DU_AN)} không được dùng prop mới"
