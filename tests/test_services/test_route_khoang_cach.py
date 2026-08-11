"""``_khoang_cach`` phải giữ đúng ba ca của bản tính theo toà nhà trước đây."""

from __future__ import annotations

from src.db.models import Building, PickupRequest
from src.services.route_planner import Candidate, _khoang_cach


def _ung_vien(toa: Building | None) -> Candidate:
    return Candidate(request=PickupRequest(weight_max_kg=10.0), building=toa, unit_code="A101")


def test_chua_gan_cho_dung_thi_khong_tinh_quang_duong() -> None:
    assert _khoang_cach(_ung_vien(None), _ung_vien(None)) == 0.0


def test_cung_mot_toa_thi_bang_khong() -> None:
    toa = Building(id=1, code="B1", lat=21.0285, lng=105.8542)
    assert _khoang_cach(_ung_vien(toa), _ung_vien(toa)) == 0.0


def test_hai_toa_thieu_toa_do_thi_uoc_luong_toi_thieu() -> None:
    """Thà đoán thấp còn hơn để một toà chưa có toạ độ đá cả cụm ra ngoài."""
    a, b = Building(id=1, code="B1"), Building(id=2, code="B2")
    assert _khoang_cach(_ung_vien(a), _ung_vien(b)) == 0.3


def test_du_toa_do_thi_tinh_duong_chim_bay() -> None:
    a = Building(id=1, code="B1", lat=21.0285, lng=105.8542)
    b = Building(id=2, code="B2", lat=21.0350, lng=105.8600)
    assert 0.5 < _khoang_cach(_ung_vien(a), _ung_vien(b)) < 1.5


def test_mot_ben_chua_gan_cho_dung_thi_van_bang_khong() -> None:
    """Ca biên của bản cũ: một vế là None thì trả 0.0, không phải 0.3."""
    toa = Building(id=1, code="B1", lat=21.0285, lng=105.8542)
    assert _khoang_cach(_ung_vien(None), _ung_vien(toa)) == 0.0
