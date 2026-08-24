"""Test P85 — mã QR đổi mỗi phiên: sinh, dùng, hết hạn, HTTP.

Tự dựng dữ liệu, không trông chờ vào seed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from src.config import reset_settings_cache
from src.db.models import Bin, Building, MaQrThung, PhienThung, Unit, User
from src.services import ma_qr_phien
from src.services.device_auth import reset_cache as reset_device_auth


@pytest.fixture(autouse=True)
def _reset():
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def bin_code(db_session):
    b = Building(code="B-QR", name="Toa QR", lat=21.0, lng=105.0)
    db_session.add(b)
    db_session.flush()
    u = Unit(building_id=b.id, code="U-QR-101")
    db_session.add(u)
    db_session.flush()
    thung = Bin(code="BIN-QR", name="Thung QR", lat=21.0, lng=105.0,
                category_codes=["recyclable"], building_id=b.id)
    db_session.add(thung)
    db_session.flush()
    return thung.code


@pytest.fixture
def user(db_session):
    u = User(email="qr_test@demo.vn", full_name="QR Tester", role="resident",
             password_hash="x")
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture
def user2(db_session):
    u = User(email="qr_test2@demo.vn", full_name="QR Tester 2", role="resident",
             password_hash="x")
    db_session.add(u)
    db_session.flush()
    return u


def test_sinh_ma_tra_ma_duy_nhat(db_session, bin_code):
    m1 = ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    m2 = ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    assert m1.ma != m2.ma


def test_sinh_ma_dat_han_120_giay(db_session, bin_code):
    m = ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    now = datetime.now(UTC)
    delta = (m.het_han_luc - now).total_seconds()
    assert 115 <= delta <= 125


def test_sinh_ma_moi_vo_hieu_ma_cu_cua_cung_thung(db_session, bin_code):
    m1 = ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    assert m1.da_dung is False
    ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    db_session.refresh(m1)
    assert m1.da_dung is True
    assert m1.da_dung_luc is not None


def test_sinh_ma_khong_dung_toi_ma_cua_thung_khac(db_session, bin_code):
    b2 = Building(code="B-QR2", name="Toa QR2", lat=21.0, lng=105.0)
    db_session.add(b2)
    db_session.flush()
    u2 = Unit(building_id=b2.id, code="U-QR2-101")
    db_session.add(u2)
    db_session.flush()
    thung2 = Bin(code="BIN-QR2", name="Thung QR2", lat=21.0, lng=105.0,
                 category_codes=["recyclable"], building_id=b2.id)
    db_session.add(thung2)
    db_session.flush()
    ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    m2 = ma_qr_phien.sinh_ma(db_session, bin_code=thung2.code)
    assert m2.da_dung is False
    ma_cu = db_session.scalars(
        select(MaQrThung).where(MaQrThung.bin_id == thung2.id, MaQrThung.da_dung.is_(False))
    ).all()
    assert len(ma_cu) == 1


def test_doi_ma_hop_le_mo_duoc_phien(db_session, bin_code, user):
    m = ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    phien = ma_qr_phien.doi_ma_lay_phien(db_session, user=user, ma=m.ma)
    assert isinstance(phien, PhienThung)
    assert phien.trang_thai == "dang_mo"
    db_session.refresh(m)
    assert m.da_dung is True
    assert m.phien_id == phien.id


def test_ma_dung_lan_hai_bi_tu_choi(db_session, bin_code, user, user2):
    m = ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    ma_qr_phien.doi_ma_lay_phien(db_session, user=user, ma=m.ma)
    with pytest.raises(ValueError, match="đã được sử dụng"):
        ma_qr_phien.doi_ma_lay_phien(db_session, user=user2, ma=m.ma)


def test_ma_het_han_bi_tu_choi(db_session, bin_code, user):
    m = ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    m.het_han_luc = datetime.now(UTC) - timedelta(seconds=10)
    db_session.flush()
    with pytest.raises(ValueError, match="hết hạn"):
        ma_qr_phien.doi_ma_lay_phien(db_session, user=user, ma=m.ma)


def test_ma_khong_ton_tai_bi_tu_choi(db_session, user):
    with pytest.raises(ValueError, match="không hợp lệ"):
        ma_qr_phien.doi_ma_lay_phien(db_session, user=user, ma="ma-khong-ton-tai")


def test_ba_ca_loi_nem_ba_thong_bao_khac_nhau(db_session, bin_code, user):
    with pytest.raises(ValueError, match="không hợp lệ"):
        ma_qr_phien.doi_ma_lay_phien(db_session, user=user, ma="ma-sai")
    m = ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    ma_qr_phien.doi_ma_lay_phien(db_session, user=user, ma=m.ma)
    with pytest.raises(ValueError, match="đã được sử dụng"):
        ma_qr_phien.doi_ma_lay_phien(db_session, user=user, ma=m.ma)
    m2 = ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    m2.het_han_luc = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()
    with pytest.raises(ValueError, match="hết hạn"):
        ma_qr_phien.doi_ma_lay_phien(db_session, user=user, ma=m2.ma)


def test_thung_dang_co_phien_mo_thi_khong_mo_them(db_session, bin_code, user, user2):
    m = ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    ma_qr_phien.doi_ma_lay_phien(db_session, user=user, ma=m.ma)
    m2 = ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    with pytest.raises(ValueError, match="đang có người sử dụng"):
        ma_qr_phien.doi_ma_lay_phien(db_session, user=user2, ma=m2.ma)


def test_don_ma_het_han_khong_xoa_dong(db_session, bin_code):
    ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    ma_qr_phien.sinh_ma(db_session, bin_code=bin_code)
    so_truoc = db_session.query(MaQrThung).count()
    for m in db_session.scalars(select(MaQrThung)).all():
        m.het_han_luc = datetime.now(UTC) - timedelta(seconds=10)
    db_session.flush()
    so_don = ma_qr_phien.don_ma_het_han(db_session)
    so_sau = db_session.query(MaQrThung).count()
    assert so_don >= 1
    assert so_sau == so_truoc


def test_ma_khong_dung_random():
    src = Path(__file__).resolve().parents[2] / "src" / "services" / "ma_qr_phien.py"
    noi_dung = src.read_text(encoding="utf-8")
    assert "random" not in noi_dung
    assert "secrets" in noi_dung


def test_hai_endpoint_qua_http_khong_bi_che(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("SEED_ON_START", "false")
    monkeypatch.setenv("LOCAL_MODEL_ENABLED", "false")
    monkeypatch.setenv("EMBED_KB_ON_START", "false")
    from src.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from src.main import app

    with TestClient(app) as c:
        r1 = c.post("/api/v1/phien/ma-qr", json={"bin_code": "BIN-QR"})
        assert r1.status_code != 422, f"POST /phien/ma-qr bi 422: {r1.text}"
        r2 = c.post("/api/v1/phien/bat-dau-bang-ma", json={"ma": "test"})
        assert r2.status_code != 422, f"POST /phien/bat-dau-bang-ma bi 422: {r2.text}"


def test_link_dung_query_string_tren_duong_goc(monkeypatch):
    monkeypatch.setenv("WEB_APP_BASE_URL", "https://gbai-v1.vercel.app")
    reset_settings_cache()
    link = ma_qr_phien.duong_link("ABC")
    assert re.fullmatch(r"^https?://[^/]+/\?ma=ABC$", link)
    assert "/phien/" not in link


def test_link_khong_lay_tu_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
    monkeypatch.setenv("WEB_APP_BASE_URL", "https://gbai-v1.vercel.app")
    reset_settings_cache()
    link = ma_qr_phien.duong_link("ABC")
    assert link.startswith("https://gbai-v1.vercel.app/")
    assert "localhost" not in link


def test_link_khong_bi_hai_dau_gach(monkeypatch):
    monkeypatch.setenv("WEB_APP_BASE_URL", "https://gbai-v1.vercel.app/")
    reset_settings_cache()
    link = ma_qr_phien.duong_link("ABC")
    assert "//?ma=" not in link
    assert link == "https://gbai-v1.vercel.app/?ma=ABC"


def test_thieu_dia_chi_web_thi_tra_503(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("SEED_ON_START", "false")
    monkeypatch.setenv("LOCAL_MODEL_ENABLED", "false")
    monkeypatch.setenv("EMBED_KB_ON_START", "false")
    monkeypatch.setenv("WEB_APP_BASE_URL", "")
    monkeypatch.setenv("IOT_DEVICE_KEYS", "GBIN-001:key-one")
    reset_settings_cache()
    reset_device_auth()
    from fastapi.testclient import TestClient

    from src.main import app

    with TestClient(app) as c:
        r = c.post(
            "/api/v1/phien/ma-qr",
            json={"bin_code": "BIN-QR"},
            headers={"X-Device-Key": "key-one"},
        )
    assert r.status_code == 503, r.text
    # 503 fires BEFORE sinh_ma is called → không có mã nào được tạo trong CSDL.
