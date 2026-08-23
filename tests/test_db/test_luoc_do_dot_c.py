"""Gói P76 — khai lược đồ cho đợt C: điểm nhận thức, nhiệm vụ, kíp thu gom.

Thuần khai báo: chỉ dựng 4 bảng mới trên SQLite trong bộ nhớ và khẳng định
chúng đúng như đặc tả (giá trị mặc định, ràng buộc duy nhất, không cột tổng
điểm nhận thức trên ``users``). Không đụng cơ sở dữ liệu thật, không viết logic.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models import Base
from src.db.models_diem import DiemNhanThucLog, NhiemVu, NhiemVuHoanThanh
from src.db.models_pickup import RouteThanhVien
from src.db.models_users import User


def _make_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_tao_duoc_ca_bon_bang():
    _make_engine()
    ten_bang = set(Base.metadata.tables.keys())
    for bang in (
        "diem_nhan_thuc_log",
        "nhiem_vu",
        "nhiem_vu_hoan_thanh",
        "route_thanh_vien",
    ):
        assert bang in ten_bang, f"thiếu bảng {bang}"
    # Không thêm cột/cột tổng vào users.
    cols_user = [c.name for c in Base.metadata.tables["users"].columns]
    assert not any("nhan_thuc" in c for c in cols_user)


def test_mac_dinh_dung_theo_spec():
    engine = _make_engine()
    with Session(engine) as s:
        user = User(email="t@example.com", full_name="test", role="resident", password_hash="w")
        s.add(user)
        s.flush()

        nguon = "chup_anh"
        d = DiemNhanThucLog(user_id=user.id, nguon=nguon, ngay=date(2026, 8, 21))
        s.add(d)
        s.flush()
        s.refresh(d)
        assert d.diem == 0
        assert d.ref_bang == ""
        assert d.ref_id is None
        assert d.ghi_chu == ""

        nv = NhiemVu(ma="NGAY_PHAN_LOAI_3_MON", ten="Phân loại 3 món", chu_ky="ngay", dieu_kien_ma="so_lan_phan_loai", dieu_kien_nguong=3)
        s.add(nv)
        s.flush()
        s.refresh(nv)
        assert nv.is_active is True
        assert nv.diem == 0
        assert nv.dieu_kien_nguong == 3

        ht = NhiemVuHoanThanh(user_id=user.id, nhiem_vu_id=nv.id, ky="2026-08-21")
        s.add(ht)
        s.flush()
        s.refresh(ht)
        assert ht.diem_da_trao == 0

        rtv = RouteThanhVien(route_id=1, user_id=user.id)
        s.add(rtv)
        s.flush()
        s.refresh(rtv)
        assert rtv.vai_tro == "thanh_vien"


def test_unique_nhiem_vu_hoan_thanh_chan_trung():
    engine = _make_engine()
    with Session(engine) as s:
        user = User(email="u@example.com", full_name="u", role="resident", password_hash="x")
        s.add(user)
        s.flush()
        nv = NhiemVu(ma="NV_UNIQUE", ten="x", chu_ky="ngay", dieu_kien_ma="y")
        s.add(nv)
        s.flush()
        s.add(NhiemVuHoanThanh(user_id=user.id, nhiem_vu_id=nv.id, ky="2026-08-21"))
        s.flush()
        s.add(NhiemVuHoanThanh(user_id=user.id, nhiem_vu_id=nv.id, ky="2026-08-21"))
        with pytest.raises(IntegrityError):
            s.flush()


def test_unique_route_thanh_vien_chan_trung():
    engine = _make_engine()
    with Session(engine) as s:
        user = User(email="r@example.com", full_name="r", role="resident", password_hash="y")
        s.add(user)
        s.flush()
        s.add(RouteThanhVien(route_id=1, user_id=user.id))
        s.flush()
        s.add(RouteThanhVien(route_id=1, user_id=user.id))
        with pytest.raises(IntegrityError):
            s.flush()


def test_diem_nhan_thuc_ghi_du_4_nguon():
    engine = _make_engine()
    with Session(engine) as s:
        user = User(email="s@example.com", full_name="s", role="resident", password_hash="z")
        s.add(user)
        s.flush()
        ngay = date(2026, 8, 21)
        for nguon in ("chup_anh", "phien_thung", "nhiem_vu_ngay", "nhiem_vu_tuan"):
            s.add(DiemNhanThucLog(user_id=user.id, nguon=nguon, ngay=ngay))
        s.flush()
        count = s.query(DiemNhanThucLog).count()
        assert count == 4
        nguon_thuc = {r.nguon for r in s.query(DiemNhanThucLog).all()}
        assert nguon_thuc == {"chup_anh", "phien_thung", "nhiem_vu_ngay", "nhiem_vu_tuan"}


def test_users_khong_co_cot_tong_nhan_thuc():
    _make_engine()
    cols = [c.name for c in Base.metadata.tables["users"].columns]
    assert not any("nhan_thuc" in c for c in cols)
