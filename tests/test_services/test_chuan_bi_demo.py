"""Test script chuẩn bị bối cảnh demo (gói P7).

Không dùng fixture API — dựng CSDL SQLite trong bộ nhớ rồi gọi thẳng hàm của
``scripts.chuan_bi_demo``, đúng kiểu ``tests/conftest.py`` và
``test_seed_nhan_vien_demo.py`` làm. Ba điều bị cấm được test xác nhận:

* ``kiem_tra`` chỉ đọc — không đổi bản ghi nào.
* báo cáo phản ánh đúng thùng mất kết nối (tính qua ``bins.trang_thai_thung``).
* ``lam_hoan_tat`` đưa yêu cầu về hoàn tất qua ``xac_nhan_khoi_luong`` (có
  ``weight_confirmed_kg`` và ``PickupEvent``), không gán thẳng trạng thái.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from scripts.chuan_bi_demo import kiem_tra, lam_hoan_tat
from src.config import reset_settings_cache
from src.db.models import Base, Bin, PickupEvent, PickupRequest, User
from src.services import pickup as pickup_service
from src.services import pickup_flow
from src.services.pickup_lifecycle import (
    DA_GIAO_DON_VI,
    DA_NHAN,
    DANG_VAN_CHUYEN,
    HOAN_TAT,
    chuan_hoa,
)


def _session_demo(*, demo: bool = True) -> Session:
    """CSDL SQLite trong bộ nhớ đã nạp dữ liệu.

    ``demo=True`` nạp cả dữ liệu mô phỏng (thùng, tuyến, yêu cầu) — dùng cho
    phần kiểm tra. ``demo=False`` chỉ nạp dữ liệu nền để cư dân demo bắt đầu
    với **0 yêu cầu** — dùng cho phần LÀM, để đúng nghĩa "N yêu cầu chuyển
    sang hoàn tất".
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()

    from scripts.seed import bootstrap

    bootstrap(session, demo=demo)
    session.commit()
    return session


def _cu_dan(session: Session) -> User:
    cu_dan = session.scalar(select(User).where(User.email == "resident@demo.vn"))
    assert cu_dan is not None
    return cu_dan


def _dem_bang(session: Session) -> dict[str, int]:
    """Số dòng từng bảng — dùng để khẳng định một lệnh không ghi gì."""
    ket_qua: dict[str, int] = {}
    for bang in Base.metadata.sorted_tables:
        ket_qua[bang.name] = session.scalar(select(func.count()).select_from(bang)) or 0
    return ket_qua


def _trang_thai_yeu_cau(session: Session) -> list[str]:
    """Trạng thái chuẩn hoá của mọi yêu cầu thu gom."""
    return sorted(chuan_hoa(r.status) for r in session.scalars(select(PickupRequest)).all())


def _muc(session: Session, now: datetime, ten: str):
    return next(m for m in kiem_tra(session, now) if m.ten == ten)


def _tao_yeu_cau_da_giao(session: Session, so_cai: int) -> list[PickupRequest]:
    """Tạo N yêu cầu của cư dân demo đang ở trạng thái đủ điều kiện xác nhận khối lượng.

    Đi qua máy trạng thái thật (cho_nhan → da_nhan → dang_van_chuyen →
    da_giao_don_vi) chứ không gán tay.
    """
    cu_dan = _cu_dan(session)
    danh_sach: list[PickupRequest] = []
    for index in range(so_cai):
        request = pickup_service.create_pickup_request(
            session,
            resident=cu_dan,
            items=[{"name": f"Thùng carton gom lại {index}", "category_code": "recyclable_paper", "qty": 2}],
            est_weight_kg=10.0 + index,
            preferred_window="08:00-10:00",
        )
        for den in (DA_NHAN, DANG_VAN_CHUYEN, DA_GIAO_DON_VI):
            pickup_flow.chuyen_trang_thai_yeu_cau(session, request, den, actor=cu_dan)
        danh_sach.append(request)
    session.commit()
    return danh_sach


def _so_hoan_tat(session: Session) -> int:
    """Số yêu cầu đã hoàn tất của cư dân demo."""
    cu_dan = _cu_dan(session)
    return session.scalar(
        select(func.count(PickupRequest.id)).where(
            PickupRequest.resident_id == cu_dan.id, PickupRequest.status == HOAN_TAT
        )
    ) or 0


# --- Kiểm tra không ghi gì -----------------------------------------------


def test_kiem_tra_khong_ghi_gi() -> None:
    session = _session_demo()
    try:
        so_dong_truoc = _dem_bang(session)
        trang_thai_truoc = _trang_thai_yeu_cau(session)

        bao_cao = kiem_tra(session, datetime.now(UTC))
        session.rollback()

        assert bao_cao, "Báo cáo phải có nội dung"
        assert _dem_bang(session) == so_dong_truoc, "Kiểm tra không được thêm/bớt bản ghi"
        assert _trang_thai_yeu_cau(session) == trang_thai_truoc, "Kiểm tra không được đổi trạng thái yêu cầu"
    finally:
        session.close()


# --- Báo cáo mục "thùng còn sống" ----------------------------------------


def test_bao_thung_chet_khi_qua_han() -> None:
    session = _session_demo()
    try:
        now = datetime.now(UTC)
        for thung in session.scalars(select(Bin)).all():
            thung.last_seen_at = now
        session.commit()
        assert _muc(session, now, "Thùng còn sống").da_dat is True

        thung = session.scalar(select(Bin).where(Bin.is_active.is_(True)))
        assert thung is not None
        thung.last_seen_at = now - timedelta(minutes=31)
        session.commit()
        assert _muc(session, now, "Thùng còn sống").da_dat is False
    finally:
        session.close()


def test_bao_du_khi_thung_con_song() -> None:
    session = _session_demo()
    try:
        now = datetime.now(UTC)
        for thung in session.scalars(select(Bin)).all():
            thung.last_seen_at = now
            thung.battery_percent = 90.0
            thung.fill_percent = 40.0
        session.commit()

        assert _muc(session, now, "Thùng còn sống").da_dat is True
    finally:
        session.close()


# --- Phần LÀM: đưa yêu cầu về hoàn tất ------------------------------------


def test_lam_dua_yeu_cau_ve_hoan_tat() -> None:
    session = _session_demo(demo=False)
    try:
        da_tao = _tao_yeu_cau_da_giao(session, 3)

        ket_qua = lam_hoan_tat(session, 2)
        session.commit()

        assert len(ket_qua) == 2, "Phải xử lý đúng số yêu cầu yêu cầu"
        for request in da_tao[:2]:
            assert chuan_hoa(request.status) == HOAN_TAT
            assert request.weight_confirmed_kg is not None
            assert request.weight_min_kg <= request.weight_confirmed_kg <= request.weight_max_kg, (
                "Khối lượng xác nhận phải nằm trong khoảng ước lượng của chính yêu cầu"
            )
        assert chuan_hoa(da_tao[2].status) == DA_GIAO_DON_VI, "Yêu cầu thừa phải giữ nguyên trạng thái"
    finally:
        session.close()


def test_lam_khong_gan_thang_trang_thai() -> None:
    session = _session_demo(demo=False)
    try:
        da_tao = _tao_yeu_cau_da_giao(session, 2)

        lam_hoan_tat(session, 2)
        session.commit()

        for request in da_tao:
            assert request.status == HOAN_TAT
            assert request.weight_confirmed_kg is not None, (
                "Yêu cầu hoàn tất phải có khối lượng thật — bằng chứng đi qua xác nhận thật"
            )
            moc = session.scalar(
                select(PickupEvent).where(
                    PickupEvent.request_id == request.id, PickupEvent.kind == "confirmed"
                )
            )
            assert moc is not None, "Phải có PickupEvent loại 'confirmed' — không phải gán tay"
    finally:
        session.close()


def test_chay_lai_khong_lam_them() -> None:
    session = _session_demo(demo=False)
    try:
        _tao_yeu_cau_da_giao(session, 2)

        lan_1 = lam_hoan_tat(session, 2)
        session.commit()
        trang_thai_truoc = _trang_thai_yeu_cau(session)
        so_truoc = _so_hoan_tat(session)

        lan_2 = lam_hoan_tat(session, 2)
        session.commit()

        assert len(lan_1) == 2, "Lần đầu phải làm việc"
        assert _trang_thai_yeu_cau(session) == trang_thai_truoc, "Lần hai không được đổi trạng thái yêu cầu nào"
        assert _so_hoan_tat(session) == so_truoc, "Số yêu cầu hoàn tất không được đổi ở lần hai"
        assert lan_2 and lan_2[0].startswith("Không có yêu cầu nào"), (
            "Lần hai phải nói thẳng lý do chứ không im lặng bỏ qua"
        )
    finally:
        session.close()


# --- Bốn mục kiểm mới (gói P17) -------------------------------------------


def test_bao_dong_khi_chi_mot_phan_thung_duoc_cap_khoa() -> None:
    """Chốt chặn của EDIT 1a: cấp khoá một phần phải báo động, kèm danh sách thùng đã cấp."""
    session = _session_demo()
    try:
        cac_thung = session.scalars(select(Bin).where(Bin.is_active.is_(True))).all()
        assert len(cac_thung) >= 5
        for thung in cac_thung:
            thung.device_key_hash = ""
        cac_thung[0].device_key_hash = "a" * 64
        cac_thung[1].device_key_hash = "b" * 64
        session.commit()

        muc = _muc(session, datetime.now(UTC), "Khoá thiết bị thùng")
        assert muc.da_dat is False, "Cấp khoá một phần phải báo động"
        assert "khoá" in muc.dong

        cac_muc_khoa = [m for m in kiem_tra(session, datetime.now(UTC)) if m.ten == "Khoá thiết bị thùng"]
        assert len(cac_muc_khoa) == 1, "Phải có đúng một mục kiểm khoá thiết bị"
        assert cac_muc_khoa[0].da_dat is False, "Mục khoá thiết bị phải là ⚠️ khi cấp một phần"
    finally:
        session.close()


def test_moi_thung_dung_khoa_chung_thi_khong_bao_dong() -> None:
    session = _session_demo()
    try:
        for thung in session.scalars(select(Bin).where(Bin.is_active.is_(True))).all():
            thung.device_key_hash = ""
        session.commit()

        muc = _muc(session, datetime.now(UTC), "Khoá thiết bị thùng")
        assert muc.da_dat is True, "Không thùng nào có khoá riêng thì không được báo động"
        assert "khoá chung" in muc.dong, "Phải nói rõ mọi thùng đang dùng khoá chung"
    finally:
        session.close()


def test_bao_dong_khi_quan_ly_khong_co_thung_nao_cung_don_vi() -> None:
    session = _session_demo()
    try:
        quan_ly = session.scalar(select(User).where(User.email == "manager@demo.vn"))
        assert quan_ly is not None
        quan_ly.organization_id = 1
        for thung in session.scalars(select(Bin)).all():
            thung.organization_id = 2
        session.commit()

        muc = _muc(session, datetime.now(UTC), "Đơn vị thu gom")
        assert muc.da_dat is False, "Quản lý không thấy thùng nào cùng đơn vị phải báo động nặng"
        assert "trống" in muc.dong.lower(), "Phải nói rõ danh sách thùng của quản lý sẽ trống"
    finally:
        session.close()


def test_bao_dong_khi_hang_doi_can_rong() -> None:
    session = _session_demo(demo=False)
    try:
        muc = _muc(session, datetime.now(UTC), "Hàng đợi chờ xác nhận khối lượng")
        assert muc.da_dat is False, "Không có yêu cầu nào ở da_giao_don_vi phải báo động"

        _tao_yeu_cau_da_giao(session, 1)
        muc = _muc(session, datetime.now(UTC), "Hàng đợi chờ xác nhận khối lượng")
        assert muc.da_dat is True, "Có một yêu cầu thì mục phải đạt"
        assert "1 yêu cầu" in muc.dong
    finally:
        session.close()


def test_bao_rate_limit_dang_tat(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session_demo(demo=False)
    try:
        monkeypatch.setenv("REGISTER_RATE_LIMIT", "0")
        reset_settings_cache()
        try:
            muc = _muc(session, datetime.now(UTC), "Giới hạn tần suất đăng ký")
            assert muc.da_dat is False, "Rate limit tắt phải báo động"
            assert "TẮT" in muc.dong
        finally:
            reset_settings_cache()
    finally:
        session.close()


def test_kiem_tra_khong_ghi_gi_vao_csdl() -> None:
    """Bốn mục kiểm mới không được phá hợp đồng "chỉ đọc" của ``kiem_tra``."""
    session = _session_demo()
    try:
        so_dong_truoc = _dem_bang(session)

        kiem_tra(session, datetime.now(UTC))
        session.rollback()

        assert _dem_bang(session) == so_dong_truoc, "Bốn mục kiểm mới không được thêm/bớt bản ghi"
    finally:
        session.close()
