"""Test hệ điểm nhận thức hai tầng + nhiệm vụ ngày/tuần (P79).

Dùng ``db_session`` của ``tests/conftest.py`` (SQLite trong bộ nhớ, đã seed danh
mục rác). Mọi ngày/tuần đều TRUYỀN VÀO — không dùng ``date.today()`` trong service.

Điều quan trọng nhất của gói: sau mọi thao tác cộng điểm nhận thức, ``users.green_points``
KHÔNG đổi và ``diem_thuong_log`` KHÔNG có dòng mới — điểm nhận thức tách bạch.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.routers.classify import _run_pipeline
from src.db.models import (
    Bin,
    Classification,
    DiemNhanThucLog,
    DiemThuongLog,
    Media,
    User,
    WasteCategory,
)
from src.services import diem_nhan_thuc, phien_thung
from src.services.classifier_types import TIER_T1, ClassifyOutcome

NGAY = date(2026, 8, 20)  # thứ Năm
NGAY_MOI = date(2026, 8, 21)  # thứ Sáu — tuần ISO khác
TUAN_ISO = f"{NGAY.isocalendar().year}-W{NGAY.isocalendar().week:02d}"


def _nguoi(db_session: Session, email: str = "cu-dan-diem@demo.vn") -> User:
    nguoi = db_session.scalar(select(User).where(User.email == email))
    if nguoi is not None:
        return nguoi
    nguoi = User(email=email, full_name="Cư dân điểm", role="resident", password_hash="x")
    db_session.add(nguoi)
    db_session.flush()
    return nguoi


def _phan_loai(db_session: Session, user_id: int, created_at: datetime | None = None) -> Classification:
    phan_loai = Classification(asker_id=user_id, item_name="Món rác test")
    if created_at is not None:
        phan_loai.created_at = created_at
    db_session.add(phan_loai)
    db_session.flush()
    return phan_loai


def _thung(db_session: Session, code: str = "BIN-001") -> Bin:
    thung = db_session.scalar(select(Bin).where(Bin.code == code))
    if thung is not None:
        return thung
    thung = Bin(code=code, name=f"Thùng {code}")
    db_session.add(thung)
    db_session.flush()
    return thung


class _FakeAgent:
    """Đóng vai ``agent.invoke`` — trả về state đã có outcome, không chạy graph."""

    def __init__(self, outcome: ClassifyOutcome) -> None:
        self._outcome = outcome

    def invoke(self, state: dict) -> dict:
        return {
            "outcome": self._outcome,
            "advice": None,
            "nodes": [],
            "schedule_hint": {},
        }


# --- Trần chụp ảnh mỗi ngày -------------------------------------------------


def test_chup_anh_dau_tien_ghi_2_diem(db_session: Session) -> None:
    nguoi = _nguoi(db_session)
    ket = diem_nhan_thuc.ghi_diem_chup_anh(db_session, user=nguoi, classification_id=1, ngay=NGAY)

    assert ket["diem_da_ghi"] == 2
    assert ket["diem_con_lai_hom_nay"] == diem_nhan_thuc.TRAN_CHUP_ANH_MOI_NGAY - 2
    assert ket["ly_do"] == ""
    dong = db_session.scalar(select(DiemNhanThucLog))
    assert dong is not None
    assert dong.diem == 2
    assert dong.nguon == diem_nhan_thuc.NGUON_CHUP_ANH
    assert dong.ref_bang == "classifications"
    assert dong.ref_id == 1
    assert dong.ngay == NGAY


def test_chup_5_anh_trong_ngay_tong_dung_10(db_session: Session) -> None:
    nguoi = _nguoi(db_session)
    for i in range(5):
        ket = diem_nhan_thuc.ghi_diem_chup_anh(db_session, user=nguoi, classification_id=i + 1, ngay=NGAY)
        assert ket["diem_da_ghi"] == 2

    tong = db_session.scalar(select(func.sum(DiemNhanThucLog.diem)))
    assert tong == diem_nhan_thuc.TRAN_CHUP_ANH_MOI_NGAY


def test_anh_thu_6_cung_ngay_khong_ghi_khong_sinh_dong(db_session: Session) -> None:
    nguoi = _nguoi(db_session)
    for i in range(5):
        diem_nhan_thuc.ghi_diem_chup_anh(db_session, user=nguoi, classification_id=i + 1, ngay=NGAY)
    so_dong_truoc = db_session.scalar(select(func.count(DiemNhanThucLog.id)))

    ket = diem_nhan_thuc.ghi_diem_chup_anh(db_session, user=nguoi, classification_id=6, ngay=NGAY)

    assert ket["diem_da_ghi"] == 0
    assert ket["diem_con_lai_hom_nay"] == 0
    assert "trần" in ket["ly_do"].lower()
    so_dong_sau = db_session.scalar(select(func.count(DiemNhanThucLog.id)))
    assert so_dong_sau == so_dong_truoc, "Ảnh thứ 6 không được sinh dòng mới"


def test_con_1_diem_duoi_tran_ghi_dung_1(db_session: Session) -> None:
    """Còn đúng 1 điểm dưới trần → ghi đúng 1, không phải 2."""
    nguoi = _nguoi(db_session)
    db_session.add(
        DiemNhanThucLog(
            user_id=nguoi.id, nguon="chup_anh", diem=9, ngay=NGAY, ref_bang="classifications"
        )
    )
    db_session.flush()

    ket = diem_nhan_thuc.ghi_diem_chup_anh(db_session, user=nguoi, classification_id=99, ngay=NGAY)

    assert ket["diem_da_ghi"] == 1
    assert ket["diem_con_lai_hom_nay"] == 0
    assert ket["ly_do"] == ""
    tong = db_session.scalar(select(func.sum(DiemNhanThucLog.diem)))
    assert tong == diem_nhan_thuc.TRAN_CHUP_ANH_MOI_NGAY, "Không được vượt trần dù chỉ 1 điểm"


def test_sang_ngay_moi_tran_dat_lai(db_session: Session) -> None:
    nguoi = _nguoi(db_session)
    for i in range(5):
        diem_nhan_thuc.ghi_diem_chup_anh(db_session, user=nguoi, classification_id=i + 1, ngay=NGAY)
    da_khong_ghi = diem_nhan_thuc.ghi_diem_chup_anh(db_session, user=nguoi, classification_id=6, ngay=NGAY)
    assert da_khong_ghi["diem_da_ghi"] == 0

    ket = diem_nhan_thuc.ghi_diem_chup_anh(db_session, user=nguoi, classification_id=7, ngay=NGAY_MOI)
    assert ket["diem_da_ghi"] == 2, "Sang ngày mới trần phải đặt lại"
    tong_ngay_moi = db_session.scalar(
        select(func.sum(DiemNhanThucLog.diem)).where(DiemNhanThucLog.ngay == NGAY_MOI)
    )
    assert tong_ngay_moi == 2


# --- Nhiệm vụ ngày / tuần -----------------------------------------------------


def test_nhiem_vu_ngay_phan_loai_3_mon_duoc_5_khong_trao_hai_lan(db_session: Session) -> None:
    nguoi = _nguoi(db_session)
    for _ in range(3):
        _phan_loai(db_session, nguoi.id, created_at=datetime(NGAY.year, NGAY.month, NGAY.day, 8, 0))
    db_session.flush()

    ket = diem_nhan_thuc.kiem_va_trao_nhiem_vu(db_session, user=nguoi, ngay=NGAY)

    assert len(ket) == 1
    assert ket[0]["ma"] == "NGAY_PHAN_LOAI_3_MON"
    dong = db_session.scalar(
        select(DiemNhanThucLog).where(DiemNhanThucLog.nguon == diem_nhan_thuc.NGUON_NHIEM_VU_NGAY)
    )
    assert dong is not None
    assert dong.diem == diem_nhan_thuc.DIEM_NHIEM_VU_NGAY_PHAN_LOAI_3_MON
    assert dong.ref_bang == "nhiem_vu"
    assert dong.ngay == NGAY

    # Gọi lại lần nữa (có thêm 1 phân loại nữa) → không cộng thêm.
    _phan_loai(db_session, nguoi.id, created_at=datetime(NGAY.year, NGAY.month, NGAY.day, 9, 0))
    db_session.flush()
    ket_lan_2 = diem_nhan_thuc.kiem_va_trao_nhiem_vu(db_session, user=nguoi, ngay=NGAY)
    assert ket_lan_2 == []
    so_dong = db_session.scalar(
        select(func.count(DiemNhanThucLog.id)).where(
            DiemNhanThucLog.nguon == diem_nhan_thuc.NGUON_NHIEM_VU_NGAY
        )
    )
    assert so_dong == 1, "Nhiệm vụ ngày chỉ được trao một lần mỗi kỳ"


def test_nhiem_vu_tuan_4_ngay_chua_duoc_5_ngay_duoc_30(db_session: Session) -> None:
    nguoi = _nguoi(db_session)
    # 4 ngày khác nhau trong tuần ISO của NGAY.
    for ngay in (date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 19), date(2026, 8, 20)):
        _phan_loai(db_session, nguoi.id, created_at=datetime(ngay.year, ngay.month, ngay.day, 8, 0))
    db_session.flush()

    ket = diem_nhan_thuc.kiem_va_trao_nhiem_vu(db_session, user=nguoi, ngay=NGAY)
    assert ket == [], "4 ngày hoạt động chưa đủ điều kiện +30"

    # Ngày thứ 5 trong cùng tuần.
    _phan_loai(db_session, nguoi.id, created_at=datetime(2026, 8, 21, 9, 0))
    db_session.flush()
    ket_2 = diem_nhan_thuc.kiem_va_trao_nhiem_vu(db_session, user=nguoi, ngay=NGAY)
    assert len(ket_2) == 1
    assert ket_2[0]["ma"] == "TUAN_5_NGAY_HOAT_DONG"
    assert ket_2[0]["ky"] == TUAN_ISO
    dong = db_session.scalar(
        select(DiemNhanThucLog).where(DiemNhanThucLog.nguon == diem_nhan_thuc.NGUON_NHIEM_VU_TUAN)
    )
    assert dong is not None
    assert dong.diem == diem_nhan_thuc.DIEM_NHIEM_VU_TUAN_5_NGAY


def test_so_ngay_hoat_dong_tinh_ca_phien_thung(db_session: Session) -> None:
    """Hoạt động = phân loại HOẶC phiên bỏ rác tại thùng."""
    nguoi = _nguoi(db_session)
    _thung(db_session)
    db_session.commit()
    for ngay in (date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 19), date(2026, 8, 20)):
        _phan_loai(db_session, nguoi.id, created_at=datetime(ngay.year, ngay.month, ngay.day, 8, 0))
    phien = phien_thung.mo_phien(db_session, nguoi, "BIN-001")
    phien.bat_dau = datetime(2026, 8, 21, 8, 0)
    db_session.flush()

    ket = diem_nhan_thuc.kiem_va_trao_nhiem_vu(db_session, user=nguoi, ngay=NGAY)

    assert len(ket) == 1
    assert ket[0]["ma"] == "TUAN_5_NGAY_HOAT_DONG"


# --- Tổng điểm ------------------------------------------------------------------


def test_tong_diem_bang_tong_cac_dong_so_cai(db_session: Session) -> None:
    nguoi = _nguoi(db_session)
    diem_nhan_thuc.ghi_diem_chup_anh(db_session, user=nguoi, classification_id=1, ngay=NGAY)
    diem_nhan_thuc.ghi_diem_chup_anh(db_session, user=nguoi, classification_id=2, ngay=NGAY_MOI)
    for _ in range(3):
        _phan_loai(db_session, nguoi.id, created_at=datetime(NGAY.year, NGAY.month, NGAY.day, 8, 0))
    db_session.flush()
    diem_nhan_thuc.kiem_va_trao_nhiem_vu(db_session, user=nguoi, ngay=NGAY)

    tong_so_cai = db_session.scalar(select(func.sum(DiemNhanThucLog.diem)))
    assert diem_nhan_thuc.tong_diem_nhan_thuc(db_session, user_id=nguoi.id) == tong_so_cai
    assert tong_so_cai == 2 + 2 + diem_nhan_thuc.DIEM_NHIEM_VU_NGAY_PHAN_LOAI_3_MON


# --- ⛔ Luật cứng: không chạm điểm có giá trị -----------------------------------


def test_khong_cham_green_points_khong_ghi_diem_thuong_log(db_session: Session) -> None:
    """Sau mọi thao tác: green_points KHÔNG đổi, diem_thuong_log KHÔNG có dòng mới."""
    nguoi = _nguoi(db_session)
    nguoi.green_points = 100
    db_session.flush()

    for i in range(3):
        diem_nhan_thuc.ghi_diem_chup_anh(db_session, user=nguoi, classification_id=i + 1, ngay=NGAY)
    for _ in range(3):
        _phan_loai(db_session, nguoi.id, created_at=datetime(NGAY.year, NGAY.month, NGAY.day, 8, 0))
    db_session.flush()
    diem_nhan_thuc.kiem_va_trao_nhiem_vu(db_session, user=nguoi, ngay=NGAY)
    db_session.flush()

    db_session.refresh(nguoi)
    assert nguoi.green_points == 100, "green_points KHÔNG được đổi"
    so_dong_so_cai = db_session.scalar(select(func.count(DiemThuongLog.id)))
    assert so_dong_so_cai == 0, "diem_thuong_log KHÔNG được có dòng mới"
    so_dong_nhan_thuc = db_session.scalar(select(func.count(DiemNhanThucLog.id)))
    assert so_dong_nhan_thuc > 0, "Điểm nhận thức vẫn phải được ghi vào sổ cái riêng"


# --- Phiên bỏ rác tại thùng giữ nguyên ------------------------------------------


def test_phien_thung_van_tinh_diem_nhan_thuc_nhu_cu(db_session: Session) -> None:
    """Phiên bỏ rác không đổi cách tính: so_vat * DIEM_NHAN_THUC_MOI_VAT."""
    from src.services.classifier_types import ClassifyOutcome

    nguoi = _nguoi(db_session)
    _thung(db_session)
    db_session.commit()

    phien = phien_thung.mo_phien(db_session, nguoi, "BIN-001")
    danh_muc = db_session.scalar(select(WasteCategory).where(WasteCategory.code == "recyclable_plastic"))
    ket_qua_thuong = ClassifyOutcome(category=danh_muc, confidence=0.94, refused=False)
    phien_thung.ghi_nhan_vat(db_session, phien, ket_qua_thuong)
    phien_thung.ghi_nhan_vat(db_session, phien, ket_qua_thuong)
    da_dong = phien_thung.dong_phien(db_session, phien)

    assert da_dong.diem_nhan_thuc == 2 * phien_thung.DIEM_NHAN_THUC_MOI_VAT
    assert da_dong.trang_thai == phien_thung.DA_DONG
    db_session.refresh(nguoi)
    assert nguoi.green_points == 0, "Phiên thùng không được chạm green_points"


# --- Điểm hỏng không làm hỏng phản hồi phân loại ---------------------------------


def test_loi_cong_diem_khong_lam_hong_phan_hoi_phan_loai(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    nguoi = _nguoi(db_session)
    danh_muc = db_session.scalar(select(WasteCategory).where(WasteCategory.code == "recyclable_plastic"))
    outcome = ClassifyOutcome(
        item_name="Chai nhựa", category=danh_muc, confidence=0.91, tier=TIER_T1, refused=False
    )
    monkeypatch.setattr("src.api.routers.classify.agent", _FakeAgent(outcome))
    monkeypatch.setattr(
        "src.api.routers.classify.diem_nhan_thuc.kiem_va_trao_nhiem_vu",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("loi diem")),
    )

    with caplog.at_level(logging.WARNING, logger="src.api.routers.classify"):
        data = _run_pipeline(
            db_session, user=nguoi, image_bytes=None, media=None, text_query="chai nhựa", building_id=None
        )

    assert data["category"]["code"] == "recyclable_plastic", "Phản hồi phân loại phải vẫn bình thường"
    assert data["diem_nhan_thuc"]["diem_vua_duoc"] == 0
    assert data["diem_nhan_thuc"]["nhiem_vu_vua_xong"] == []
    ghi = db_session.scalar(select(Classification).where(Classification.asker_id == nguoi.id))
    assert ghi is not None, "Bản ghi phân loại vẫn phải được lưu"
    assert any(r.levelno == logging.WARNING for r in caplog.records), "Phải có log warning về lỗi điểm"


# --- Ảnh từ thiết bị không cộng điểm --------------------------------------------


def test_anh_thiet_bi_uploader_none_khong_sinh_dong_diem(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    nguoi = _nguoi(db_session)
    danh_muc = db_session.scalar(select(WasteCategory).where(WasteCategory.code == "recyclable_plastic"))
    outcome = ClassifyOutcome(
        item_name="Chai nhựa", category=danh_muc, confidence=0.91, tier=TIER_T1, refused=False
    )
    monkeypatch.setattr("src.api.routers.classify.agent", _FakeAgent(outcome))

    media = Media(uploader_id=None, stored_path="/tmp/anh-thiet-bi.jpg")
    db_session.add(media)
    db_session.flush()

    _run_pipeline(
        db_session, user=nguoi, image_bytes=b"anh", media=media, text_query="", building_id=None
    )

    so_dong = db_session.scalar(select(func.count(DiemNhanThucLog.id)))
    assert so_dong == 0, "Ảnh từ thiết bị (uploader_id = NULL) không được sinh dòng điểm nào"


# --- Không dùng date.today() trong service --------------------------------------


def test_service_khong_dung_date_today(db_session: Session) -> None:
    """Ngày phải là tham số truyền vào — service không tự gọi ``today()``."""
    import ast

    cay = ast.parse(Path(diem_nhan_thuc.__file__).read_text(encoding="utf-8"))
    loi_goi_today = []
    for nut in ast.walk(cay):
        if not isinstance(nut, ast.Call):
            continue
        if isinstance(nut.func, ast.Attribute) and nut.func.attr == "today":
            loi_goi_today.append(ast.unparse(nut))
    assert loi_goi_today == [], f"Service không được gọi today(): {loi_goi_today}"
