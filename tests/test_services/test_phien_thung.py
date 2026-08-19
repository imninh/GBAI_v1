"""Test luật phiên bỏ rác tại thùng (P63) — thuần, không API, không mạng.

Dùng ``db_session`` của ``tests/conftest.py`` (SQLite trong bộ nhớ). Các test phủ:
mở/đóng phiên, một phiên duy nhất mỗi thùng, quá hạn tự chuyển ``het_han``,
đếm vật đúng luật (từ chối/UNKNOWN/nguy hại không tính), điểm nhận thức tách
bạch (không chạm ``green_points``, không chạm ``diem_thuong_log``), thông báo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import Bin, DiemThuongLog, Notification, PhienThung, User
from src.services import phien_thung
from src.services.classifier_types import ClassifyOutcome

MAT_KHAU = "x"


def _nguoi(db_session: Session, email: str = "cu-dan-a@demo.vn") -> User:
    nguoi = db_session.scalar(select(User).where(User.email == email))
    if nguoi is not None:
        return nguoi
    nguoi = User(
        email=email,
        full_name="Cư dân phiên",
        role="resident",
        password_hash=MAT_KHAU,
    )
    db_session.add(nguoi)
    db_session.flush()
    return nguoi


def _thung(db_session: Session, code: str = "BIN-001") -> Bin:
    thung = db_session.scalar(select(Bin).where(Bin.code == code))
    if thung is not None:
        return thung
    thung = Bin(code=code, name=f"Thùng {code}")
    db_session.add(thung)
    db_session.flush()
    return thung


def _outcome_thuong() -> ClassifyOutcome:
    from src.db.models import WasteCategory

    return ClassifyOutcome(category=WasteCategory(code="recyclable_plastic"), confidence=0.94, refused=False)


def _outcome_tu_choi() -> ClassifyOutcome:
    return ClassifyOutcome(category=None, confidence=0.0, refused=True, refusal_reason="duoi_nguong")


def _outcome_nguy_hai() -> ClassifyOutcome:
    from src.db.models import WasteCategory

    return ClassifyOutcome(category=WasteCategory(code="hazardous", is_hazardous=True), confidence=0.99, refused=False)


def _mo(db_session: Session, email: str, bin_code: str = "BIN-001") -> PhienThung:
    return phien_thung.mo_phien(db_session, _nguoi(db_session, email), bin_code)


def _dem_notification(db_session: Session, user_id: int) -> int:
    return int(
        db_session.scalar(select(func.count(Notification.id)).where(Notification.user_id == user_id)) or 0
    )


# --- Mở phiên ----------------------------------------------------------------


def test_mo_phien_tra_ma_phien_dang_mo(db_session: Session) -> None:
    _thung(db_session)
    db_session.commit()
    nguoi = _nguoi(db_session)

    phien = phien_thung.mo_phien(db_session, nguoi, "BIN-001")

    assert phien.ma_phien, "Phải có ma_phien"
    assert phien.trang_thai == phien_thung.DANG_MO
    assert phien.bin_id == _thung(db_session).id
    assert phien.user_id == nguoi.id
    assert phien.so_vat == 0
    assert phien.diem_nhan_thuc == 0


def test_mot_thung_mot_phien_mo_thoi(db_session: Session) -> None:
    """Thùng chỉ có một phiên dang_mo — chủ gọi lại trả phiên cũ, không đẻ mới."""
    _thung(db_session)
    db_session.commit()
    nguoi = _nguoi(db_session)

    phien_1 = phien_thung.mo_phien(db_session, nguoi, "BIN-001")
    phien_2 = phien_thung.mo_phien(db_session, nguoi, "BIN-001")

    assert phien_1.id == phien_2.id, "Chủ gọi lại phải nhận lại đúng phiên cũ"
    so_phien = db_session.scalar(select(func.count(PhienThung.id)))
    assert so_phien == 1, "Không được đẻ phiên thứ hai"


def test_thung_dang_co_nguoi_khac_thi_tu_choi(db_session: Session) -> None:
    _thung(db_session)
    db_session.commit()
    _mo(db_session, "cu-dan-a@demo.vn")

    with pytest.raises(ValueError, match="đang có người sử dụng"):
        _mo(db_session, "cu-dan-b@demo.vn")


def test_thung_khong_ton_tai_thi_value_error(db_session: Session) -> None:
    nguoi = _nguoi(db_session)
    with pytest.raises(ValueError, match="Không tìm thấy thùng"):
        phien_thung.mo_phien(db_session, nguoi, "BIN-KHONG-CO")


# --- Hết hạn -----------------------------------------------------------------


def test_qua_10_phut_tu_danh_dau_het_han(db_session: Session) -> None:
    _thung(db_session)
    db_session.commit()
    nguoi = _nguoi(db_session)

    phien = phien_thung.mo_phien(db_session, nguoi, "BIN-001")
    phien.bat_dau = datetime.now(UTC) - timedelta(minutes=11)
    db_session.flush()

    tra_ve = phien_thung.phien_dang_mo_cua_thung(db_session, _thung(db_session).id)

    assert tra_ve is None, "Quá 10 phút phải trả None"
    db_session.refresh(phien)
    assert phien.trang_thai == phien_thung.HET_HAN


def test_chua_qua_10_phut_thi_van_mo(db_session: Session) -> None:
    _thung(db_session)
    db_session.commit()
    nguoi = _nguoi(db_session)

    phien = phien_thung.mo_phien(db_session, nguoi, "BIN-001")
    phien.bat_dau = datetime.now(UTC) - timedelta(minutes=5)
    db_session.flush()

    assert phien_thung.phien_dang_mo_cua_thung(db_session, _thung(db_session).id) is not None


def test_het_han_van_cong_diem_cho_phan_da_bo(db_session: Session) -> None:
    """Phiên đóng vì hết hạn mà đã có vật được chấp nhận → vẫn cộng điểm."""
    _thung(db_session)
    db_session.commit()
    nguoi = _nguoi(db_session)
    phien = phien_thung.mo_phien(db_session, nguoi, "BIN-001")
    phien_thung.ghi_nhan_vat(db_session, phien, _outcome_thuong())
    phien_thung.ghi_nhan_vat(db_session, phien, _outcome_thuong())
    phien.bat_dau = datetime.now(UTC) - timedelta(minutes=11)
    db_session.flush()

    # Khi mở lại (hoặc dọn) → phiên tự het_han nhưng số vật/điểm không mất.
    assert phien_thung.phien_dang_mo_cua_thung(db_session, _thung(db_session).id) is None
    db_session.refresh(phien)
    assert phien.trang_thai == phien_thung.HET_HAN
    assert phien.so_vat == 2

    phien_thung.dong_phien(db_session, phien, ly_do=phien_thung.HET_HAN)
    assert phien.diem_nhan_thuc == 2 * phien_thung.DIEM_NHAN_THUC_MOI_VAT


# --- Đếm vật -----------------------------------------------------------------


def test_vat_thuong_duoc_cong(db_session: Session) -> None:
    _thung(db_session)
    db_session.commit()
    phien = _mo(db_session, "cu-dan-a@demo.vn")

    phien_thung.ghi_nhan_vat(db_session, phien, _outcome_thuong())

    assert phien.so_vat == 1


def test_vat_tu_choi_khong_cong(db_session: Session) -> None:
    _thung(db_session)
    db_session.commit()
    phien = _mo(db_session, "cu-dan-a@demo.vn")

    phien_thung.ghi_nhan_vat(db_session, phien, _outcome_tu_choi())

    assert phien.so_vat == 0, "Ca bị từ chối không được tính"


def test_vat_unknown_khong_cong(db_session: Session) -> None:
    _thung(db_session)
    db_session.commit()
    phien = _mo(db_session, "cu-dan-a@demo.vn")

    phien_thung.ghi_nhan_vat(db_session, phien, _outcome_nguy_hai())

    assert phien.so_vat == 0, "Ca nguy hại cần người duyệt không được tính"


# --- Đóng phiên ---------------------------------------------------------------


def test_dong_phien_tinh_diem_va_sinh_thong_bao(db_session: Session) -> None:
    _thung(db_session)
    db_session.commit()
    nguoi = _nguoi(db_session)
    phien = _mo(db_session, "cu-dan-a@demo.vn")
    phien_thung.ghi_nhan_vat(db_session, phien, _outcome_thuong())
    phien_thung.ghi_nhan_vat(db_session, phien, _outcome_thuong())

    da_dong = phien_thung.dong_phien(db_session, phien)

    assert da_dong.trang_thai == phien_thung.DA_DONG
    assert da_dong.ket_thuc is not None
    assert da_dong.diem_nhan_thuc == 2 * phien_thung.DIEM_NHAN_THUC_MOI_VAT

    thong_bao = db_session.scalar(select(Notification).where(Notification.user_id == nguoi.id))
    assert thong_bao is not None, "Đóng phiên phải sinh thông báo trong app"
    assert str(da_dong.so_vat) in thong_bao.body
    assert "không đổi quà" in thong_bao.body, "Thông báo phải nói rõ là điểm nhận thức"
    assert "điểm nhận thức" in thong_bao.body.lower()


def test_dong_phien_khong_cham_green_points_khong_cham_so_cai(db_session: Session) -> None:
    """⛔ Không cộng green_points, không ghi diem_thuong_log — điểm nhận thức tách bạch."""
    _thung(db_session)
    db_session.commit()
    nguoi = _nguoi(db_session)
    nguoi.green_points = 100
    phien = _mo(db_session, "cu-dan-a@demo.vn")
    phien_thung.ghi_nhan_vat(db_session, phien, _outcome_thuong())

    phien_thung.dong_phien(db_session, phien)
    db_session.flush()

    db_session.refresh(nguoi)
    assert nguoi.green_points == 100, "green_points không được đổi"
    so_dong_so_cai = db_session.scalar(select(func.count(DiemThuongLog.id)))
    assert so_dong_so_cai == 0, "diem_thuong_log không được có dòng mới"


def test_dong_phien_hai_lan_bi_chan(db_session: Session) -> None:
    _thung(db_session)
    db_session.commit()
    phien = _mo(db_session, "cu-dan-a@demo.vn")
    phien_thung.dong_phien(db_session, phien)

    with pytest.raises(ValueError, match="đã đóng"):
        phien_thung.dong_phien(db_session, phien)
