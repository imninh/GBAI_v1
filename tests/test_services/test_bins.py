"""Test lớp nghiệp vụ thùng thu gom thông minh: trạng thái, thống kê, danh sách."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from src.db.models import Bin, BinReading
from src.services import bins

NOW = datetime(2026, 8, 6, 8, 0)

_so_thung = itertools.count(1)


def _tao_thung(db_session: Session, **fields: object) -> Bin:
    """Tạo thùng kiểm thử; mã thùng tự sinh nếu không truyền."""
    defaults: dict[str, object] = {
        "code": f"BIN-T{next(_so_thung):03d}",
        "name": "Thùng kiểm thử",
        "fill_percent": 10.0,
        "battery_percent": 100.0,
        "last_seen_at": NOW,
        "is_active": True,
    }
    defaults.update(fields)
    thung = Bin(**defaults)
    db_session.add(thung)
    db_session.flush()
    return thung


# --- Bốn trạng thái -------------------------------------------------------


def test_trang_thai_binh_thuong(db_session: Session) -> None:
    thung = _tao_thung(db_session)

    assert bins.trang_thai_thung(thung, NOW) == "binh_thuong"


def test_trang_thai_can_gom(db_session: Session) -> None:
    thung = _tao_thung(db_session, fill_percent=85.0)

    assert bins.trang_thai_thung(thung, NOW) == "can_gom"


def test_trang_thai_mat_ket_noi_khi_chua_bao_gio_bao_ve(db_session: Session) -> None:
    thung = _tao_thung(db_session, last_seen_at=None)

    assert bins.trang_thai_thung(thung, NOW) == "mat_ket_noi"


def test_trang_thai_het_pin(db_session: Session) -> None:
    thung = _tao_thung(db_session, battery_percent=10.0)

    assert bins.trang_thai_thung(thung, NOW) == "het_pin"


# --- Thứ tự ưu tiên -------------------------------------------------------


def test_u_tien_mat_ket_noi_thang_can_gom(db_session: Session) -> None:
    # Đầy 96% nhưng offline 3 ngày — con số 96% là của lần báo cuối, không còn
    # tin được, nên phải ra "mất kết nối" chứ không phải "cần gom".
    thung = _tao_thung(db_session, fill_percent=96.0, last_seen_at=NOW - timedelta(days=3))

    assert bins.trang_thai_thung(thung, NOW) == "mat_ket_noi"


def test_u_tien_het_pin_thang_can_gom(db_session: Session) -> None:
    thung = _tao_thung(db_session, fill_percent=96.0, battery_percent=5.0)

    assert bins.trang_thai_thung(thung, NOW) == "het_pin"


# --- Biên của ngưỡng ------------------------------------------------------


def test_bien_nguong_do_day_dung_80_la_can_gom(db_session: Session) -> None:
    dung_nguong = _tao_thung(db_session, code="BIN-80", fill_percent=80.0)
    duoi_nguong = _tao_thung(db_session, code="BIN-79", fill_percent=79.0)

    assert bins.trang_thai_thung(dung_nguong, NOW) == "can_gom"
    assert bins.trang_thai_thung(duoi_nguong, NOW) != "can_gom"


def test_bien_nguong_offline_dung_30_phut_van_con_ket_noi(db_session: Session) -> None:
    # "Cũ hơn BIN_OFFLINE_MINUTES" nghĩa là > 30 phút; đúng 30 phút vẫn còn nối.
    thung = _tao_thung(db_session, fill_percent=85.0, last_seen_at=NOW - timedelta(minutes=30))

    assert bins.trang_thai_thung(thung, NOW) == "can_gom"


def test_bien_nguong_offline_qua_mot_giay_thi_mat_ket_noi(db_session: Session) -> None:
    thung = _tao_thung(db_session, fill_percent=85.0, last_seen_at=NOW - timedelta(minutes=30, seconds=1))

    assert bins.trang_thai_thung(thung, NOW) == "mat_ket_noi"


# --- Nhất quán giữa aware và naive ----------------------------------------
# SQLite đọc datetime về naive còn quy ước của dự án là aware (utcnow()), nên
# cả bốn tổ hợp aware/naive của (now, last_seen_at) phải cho cùng một kết quả.

NOW_AWARE = datetime(2026, 8, 6, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize("now_value", [NOW, NOW_AWARE])
@pytest.mark.parametrize("last_seen_value", [NOW, NOW_AWARE])
def test_trang_thai_giong_nhau_giua_aware_va_naive(
    db_session: Session, now_value: datetime, last_seen_value: datetime
) -> None:
    thung = _tao_thung(db_session, fill_percent=85.0, last_seen_at=last_seen_value)

    assert bins.trang_thai_thung(thung, now_value) == "can_gom"


@pytest.mark.parametrize("now_value", [NOW, NOW_AWARE])
@pytest.mark.parametrize("last_seen_value", [NOW - timedelta(minutes=31), NOW_AWARE - timedelta(minutes=31)])
def test_offline_giong_nhau_giua_aware_va_naive(
    db_session: Session, now_value: datetime, last_seen_value: datetime
) -> None:
    """Biên offline là ca thực sự trừ hai mốc thời gian — phải không đổi kết quả."""
    thung = _tao_thung(db_session, fill_percent=96.0, last_seen_at=last_seen_value)

    assert bins.trang_thai_thung(thung, now_value) == "mat_ket_noi"


@pytest.mark.parametrize("now_value", [NOW, NOW_AWARE])
@pytest.mark.parametrize("last_seen_value", [NOW - timedelta(minutes=30), NOW_AWARE - timedelta(minutes=30)])
def test_bien_offline_dung_30_phut_giong_nhau_giua_aware_va_naive(
    db_session: Session, now_value: datetime, last_seen_value: datetime
) -> None:
    thung = _tao_thung(db_session, fill_percent=85.0, last_seen_at=last_seen_value)

    assert bins.trang_thai_thung(thung, now_value) == "can_gom"


# --- Ghi nhận reading -----------------------------------------------------


def test_ghi_nhan_reading_tu_choi_muc_rac_ngoai_khoang(db_session: Session) -> None:
    thung = _tao_thung(db_session)

    with pytest.raises(ValueError, match="Mức rác"):
        bins.ghi_nhan_reading(db_session, thung, -1.0, 50.0, "device", NOW)
    with pytest.raises(ValueError, match="Mức rác"):
        bins.ghi_nhan_reading(db_session, thung, 101.0, 50.0, "device", NOW)


def test_ghi_nhan_reading_tu_choi_muc_pin_ngoai_khoang(db_session: Session) -> None:
    thung = _tao_thung(db_session)

    with pytest.raises(ValueError, match="Mức pin"):
        bins.ghi_nhan_reading(db_session, thung, 50.0, -5.0, "device", NOW)
    with pytest.raises(ValueError, match="Mức pin"):
        bins.ghi_nhan_reading(db_session, thung, 50.0, 150.0, "device", NOW)


def test_ghi_nhan_reading_cap_nhat_ca_ba_truong_cua_thung(db_session: Session) -> None:
    thung = _tao_thung(db_session, fill_percent=5.0, battery_percent=90.0)

    reading = bins.ghi_nhan_reading(db_session, thung, 70.0, 40.0, "device", NOW)
    db_session.commit()

    assert thung.fill_percent == 70.0
    assert thung.battery_percent == 40.0
    assert thung.last_seen_at == NOW
    assert reading.bin_id == thung.id
    assert reading.source == "device"
    assert reading.created_at == NOW
    assert db_session.query(BinReading).count() == 1


# --- Thống kê và danh sách ------------------------------------------------


def test_thong_ke_thung_dem_du_bon_loai(db_session: Session) -> None:
    _tao_thung(db_session, fill_percent=85.0)  # can_gom
    _tao_thung(db_session, last_seen_at=None)  # mat_ket_noi
    _tao_thung(db_session, battery_percent=10.0)  # het_pin
    _tao_thung(db_session, fill_percent=10.0)  # binh_thuong

    ket_qua = bins.thong_ke_thung(db_session, NOW)

    assert ket_qua == {"tong": 4, "can_gom": 1, "mat_ket_noi": 1, "het_pin": 1}


def test_danh_sach_chi_can_gom_loc_va_sap_xep_giam_dan(db_session: Session) -> None:
    _tao_thung(db_session, code="BIN-A", fill_percent=82.0)
    _tao_thung(db_session, code="BIN-B", fill_percent=90.0)
    _tao_thung(db_session, code="BIN-C", fill_percent=50.0)

    danh_sach = bins.danh_sach_thung(db_session, NOW, chi_can_gom=True)

    assert [dong["code"] for dong in danh_sach] == ["BIN-B", "BIN-A"]


def test_thung_da_ngung_khong_vao_thong_ke(db_session: Session) -> None:
    _tao_thung(db_session, fill_percent=85.0, is_active=False)
    _tao_thung(db_session, fill_percent=85.0)

    assert bins.thong_ke_thung(db_session, NOW)["tong"] == 1
