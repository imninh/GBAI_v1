"""Kiểm thử gói P78: dựng cảnh thùng demo + thùng thật VinUni.

Không đụng mạng, không chạy script lên CSDL thật — mọi thứ chạy trên CSDL
trong bộ nhớ hoặc session tạm do test cấp. Gọi trực tiếp hàm của hai script
thay vì chạy CLI.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base, Bin, User
from src.db.seed_data import seed_bins
from src.services.bins import trang_thai_thung


def _nap_script(ten: str, tep: Path):
    spec = importlib.util.spec_from_file_location(ten, tep)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
dung_canh_demo = _nap_script("dung_canh_demo_p78", _SCRIPTS / "dung_canh_demo.py")
them_thung_vinuni = _nap_script("them_thung_vinuni_p78", _SCRIPTS / "them_thung_vinuni.py")

_GOC = Path(__file__).resolve().parents[1]


def _session_trong_nho():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seed_bin(session) -> None:
    seed_bins(session)
    session.commit()


def _trang_thai(session, now):
    return [trang_thai_thung(t, now) for t in session.scalars(select(Bin)).all()]


def _dem(session, now):
    d: dict[str, int] = {}
    for tt in _trang_thai(session, now):
        d[tt] = d.get(tt, 0) + 1
    return d


def _tao_manager(session) -> None:
    if session.scalar(select(User).where(User.email == "manager@demo.vn")) is None:
        session.add(User(email="manager@demo.vn", full_name="Qly", role="manager", password_hash="x"))
        session.commit()


# 1. Tập trạng thái ĐÚNG BẰNG bốn loại.
def test_seed_dung_bon_trang_thai(db_session) -> None:
    _seed_bin(db_session)
    now = datetime.now(UTC)
    assert set(_trang_thai(db_session, now)) == {"binh_thuong", "can_gom", "het_pin", "mat_ket_noi"}


# 2. Đếm đúng bảng §6 (5 · 3 · 1 · 1).
def test_seed_dem_dung_so_luong(db_session) -> None:
    _seed_bin(db_session)
    now = datetime.now(UTC)
    assert _dem(db_session, now) == {"binh_thuong": 5, "can_gom": 3, "het_pin": 1, "mat_ket_noi": 1}


# 3. Tất định: hai CSDL riêng → bảng đếm giống hệt nhau.
def test_seed_tat_dinh_hai_csd_giong_nhau() -> None:
    s1 = _session_trong_nho()
    _seed_bin(s1)
    s2 = _session_trong_nho()
    _seed_bin(s2)
    now = datetime.now(UTC)
    assert _dem(s1, now) == _dem(s2, now)


# 4. Chạy khô → không dòng nào đổi.
def test_dung_canh_demo_kho_khong_doi(db_session) -> None:
    _seed_bin(db_session)
    truoc = {
        t.code: (t.fill_percent, t.battery_percent, t.last_seen_at)
        for t in db_session.scalars(select(Bin)).all()
    }
    dung_canh_demo.tinh_canh_demo(db_session, write=False)
    for t in db_session.scalars(select(Bin)).all():
        assert (t.fill_percent, t.battery_percent, t.last_seen_at) == truoc[t.code], t.code


# 5. Chạy thật → đủ bốn loại, giữ nguyên deployment_status/is_active/is_seed/lat/lng.
def test_dung_canh_demo_that_giu_nguyen_truong_khac(db_session) -> None:
    _seed_bin(db_session)
    now = datetime.now(UTC)
    dung_canh_demo.tinh_canh_demo(db_session, write=True)
    db_session.commit()
    bins = db_session.scalars(select(Bin)).all()
    assert set(trang_thai_thung(t, now) for t in bins) == {
        "binh_thuong",
        "can_gom",
        "het_pin",
        "mat_ket_noi",
    }
    for t in bins:
        assert t.deployment_status == ""
        assert t.is_active is True
        assert t.is_seed is True
        assert t.lat is not None and t.lng is not None


# 6. Bỏ qua thùng is_seed = False.
def test_dung_canh_demo_bo_qua_is_seed_false(db_session) -> None:
    _seed_bin(db_session)
    that = Bin(
        code="BIN_THAT_01",
        name="Thùng thật",
        lat=21.0,
        lng=105.8,
        category_codes=["recyclable"],
        is_seed=False,
        fill_percent=12.0,
        battery_percent=9.0,
        last_seen_at=datetime.now(UTC),
    )
    db_session.add(that)
    db_session.commit()
    dung_canh_demo.tinh_canh_demo(db_session, write=True)
    db_session.commit()
    lai = db_session.get(Bin, that.id)
    assert (lai.fill_percent, lai.battery_percent, lai.last_seen_at) == (
        12.0,
        9.0,
        that.last_seen_at,
    )


# 7. VinUni chạy khô → không tạo thùng.
def test_them_vinuni_kho_khong_tao(db_session) -> None:
    _tao_manager(db_session)
    n_truoc = len(db_session.scalars(select(Bin)).all())
    them_thung_vinuni.tao_vinuni(db_session, write=False)
    assert len(db_session.scalars(select(Bin)).all()) == n_truoc


# 8. VinUni chạy thật → tạo được, is_seed False, toạ độ trong hộp HN, không chua_trien_khai.
def test_them_vinuni_that_tao_duoc(db_session) -> None:
    _tao_manager(db_session)
    thung = them_thung_vinuni.tao_vinuni(db_session, write=True)
    db_session.commit()
    assert thung is not None
    assert thung.is_seed is False
    assert 20.5 <= thung.lat <= 21.5
    assert 105.0 <= thung.lng <= 106.5
    assert trang_thai_thung(thung, datetime.now(UTC)) != "chua_trien_khai"


# 9. VinUni chạy thật hai lần → vẫn đúng một thùng, lần hai không ném lỗi.
def test_them_vinuni_hai_lan_van_mot(db_session) -> None:
    _tao_manager(db_session)
    t1 = them_thung_vinuni.tao_vinuni(db_session, write=True)
    db_session.commit()
    assert t1 is not None
    t2 = them_thung_vinuni.tao_vinuni(db_session, write=True)
    db_session.commit()
    assert t2 is None
    ma = [b.code for b in db_session.scalars(select(Bin)).all()]
    assert ma.count("BIN_HN_VINUNI_01") == 1


# 10. Quét chống mã cứng trong mã nghiệp vụ.
def test_khong_co_ma_cung_trong_nghiep_vu() -> None:
    for duong in ("src/services/bins.py", "src/services/chatbot_tools.py"):
        noi_dung = (_GOC / duong).read_text(encoding="utf-8")
        assert "BIN-04" not in noi_dung
        assert "BIN-08" not in noi_dung
        assert "BIN_HN_VINUNI_01" not in noi_dung
