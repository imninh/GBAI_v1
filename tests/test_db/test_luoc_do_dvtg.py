"""Kiểm thử lược đồ ĐVTG (gói P71): 6 cột thêm vào + 2 bảng mới.

Chạy trên SQLite trong bộ nhớ — không đụng CSDL thật.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base, BatchGanNhan, Bin, Media, PickupRoute, SuCoThuGom
from src.db.schema_patch import COT_CAN_VA


def _make_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


# --- 1. Cả hai bảng mới dựng được từ metadata ---


def test_hai_bang_moi_tao_duoc() -> None:
    session = _make_session()
    try:
        assert "su_co_thu_gom" in Base.metadata.tables
        assert "batch_gan_nhan" in Base.metadata.tables
    finally:
        session.close()


# --- 2. SuCoThuGom ghi/đọc, mặc định trang_thai == "cho_xu_ly" ---


def test_su_co_thu_gom_mac_dinh() -> None:
    session = _make_session()
    try:
        sc = SuCoThuGom(route_id=1, nguoi_bao_id=2, loai="phan_loai_sai", mo_ta="Rác không đúng nhóm")
        session.add(sc)
        session.commit()

        doc = session.get(SuCoThuGom, sc.id)
        assert doc is not None
        assert doc.trang_thai == "cho_xu_ly"
        assert doc.loai == "phan_loai_sai"
        assert doc.mo_ta == "Rác không đúng nhóm"
        assert doc.stop_id is None
        assert doc.anh_media_id is None
        assert doc.nguoi_xu_ly_id is None
    finally:
        session.close()


# --- 3. BatchGanNhan ghi/đọc, mặc định trang_thai == "mo", so_anh == 0 ---


def test_batch_gan_nhan_mac_dinh() -> None:
    session = _make_session()
    try:
        batch = BatchGanNhan(ma="BATCH-2026-08-20-01", nguon="app")
        session.add(batch)
        session.commit()

        doc = session.get(BatchGanNhan, batch.id)
        assert doc is not None
        assert doc.trang_thai == "mo"
        assert doc.so_anh == 0
        assert doc.nguon == "app"
    finally:
        session.close()


# --- 4. Sáu cột mới có mặt trong model, đúng giá trị mặc định ---


def test_sau_cot_moi_co_gia_tri_mac_dinh() -> None:
    session = _make_session()
    try:
        route = PickupRoute(service_date=date.today())
        session.add(route)
        session.commit()
        assert route.nguon_tao == "thu_cong"
        assert route.xac_nhan_boi is None
        assert route.xac_nhan_luc is None

        bin_obj = Bin(code="BIN-TEST", name="Thùng test")
        session.add(bin_obj)
        session.commit()
        assert bin_obj.dat_day_thu_cong is False

        media = Media(stored_path="/tmp/x.jpg")
        session.add(media)
        session.commit()
        assert media.batch_id is None
        assert media.can_gan_nhan is False
    finally:
        session.close()


# --- 5. Mỗi cột COT_CAN_VA có cột cùng tên trong model ---


def test_cot_can_va_khop_model() -> None:
    """Chống bẫy media.uploader_id: cột trong COT_CAN_VA phải có trong model."""
    six_new = {
        ("pickup_routes", "nguon_tao"),
        ("pickup_routes", "xac_nhan_boi"),
        ("pickup_routes", "xac_nhan_luc"),
        ("bins", "dat_day_thu_cong"),
        ("media", "batch_id"),
        ("media", "can_gan_nhan"),
    }
    # Chỉ xét 6 dòng mới thêm vào COT_CAN_VA
    cot_moi = [(b, c) for (b, c, _k) in COT_CAN_VA if (b, c) in six_new]
    assert len(cot_moi) == 6, f"Thiếu dòng trong COT_CAN_VA: {six_new - set(cot_moi)}"

    tables = Base.metadata.tables
    for bang, cot in cot_moi:
        assert bang in tables, f"Bảng {bang} không có trong model"
        assert cot in tables[bang].columns, (
            f"Cột {bang}.{cot} có trong COT_CAN_VA nhưng KHÔNG có trong model"
        )


# --- 6. media.batch_id tham chiếu được BatchGanNhan ---


def test_media_batch_id_tham_chieu_batch() -> None:
    session = _make_session()
    try:
        batch = BatchGanNhan(ma="BATCH-2026-08-20-02", nguon="thiet_bi")
        session.add(batch)
        session.commit()

        media = Media(stored_path="/tmp/y.jpg", batch_id=batch.id)
        session.add(media)
        session.commit()

        doc = session.get(Media, media.id)
        assert doc.batch_id == batch.id
        batch_doc = session.get(BatchGanNhan, doc.batch_id)
        assert batch_doc.trang_thai == "mo"
    finally:
        session.close()
