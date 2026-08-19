"""Test API phiên bỏ rác tại thùng (P63) — cư dân mở/xem/đóng phiên.

Không gọi mạng; dùng SQLite trong bộ nhớ (fixture ``api_session``). Kiểm:
mở phiên → ma_phien + dang_mo; thùng bị chiếm → từ chối; chủ gọi lại → phiên cũ;
người lạ xem/đóng → 404; đóng → notifications, không chạm green_points /
diem_thuong_log.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base, Bin, DiemThuongLog, Notification, PhienThung, User
from src.main import app

MAT_KHAU = "demo1234"


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """CSDL trong bộ nhớ đã seed dữ liệu nền, gắn vào dependency của app."""
    from scripts.seed import seed_buildings, seed_categories, seed_knowledge, seed_schedules, seed_units, seed_users

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()

    seed_categories(session)
    buildings = seed_buildings(session)
    units = seed_units(session, buildings)
    seed_users(session, units)
    seed_schedules(session, buildings)
    seed_knowledge(session, buildings)
    session.commit()

    def _override() -> Iterator[Session]:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_db] = _override

    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()


@pytest_asyncio.fixture
async def api(api_session: Session) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _dang_nhap(api: AsyncClient, email: str) -> str:
    response = await api.post("/api/v1/auth/login", json={"email": email, "password": MAT_KHAU})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _them_cu_dan(api_session: Session, email: str) -> User:
    from src.services.security import hash_password

    nguoi = User(
        email=email,
        full_name=f"Cư dân {email}",
        role="resident",
        password_hash=hash_password(MAT_KHAU),
    )
    api_session.add(nguoi)
    api_session.flush()
    return nguoi


def _them_thung(api_session: Session, code: str = "BIN-001") -> Bin:
    thung = Bin(code=code, name=f"Thùng {code}")
    api_session.add(thung)
    api_session.flush()
    return thung


@pytest.mark.asyncio
async def test_mo_phien_tra_ma_phien_dang_mo(
    api: AsyncClient, api_session: Session
) -> None:
    _them_thung(api_session)
    cu_dan = _them_cu_dan(api_session, "cu-dan-mo@demo.vn")
    api_session.commit()
    token = await _dang_nhap(api, "cu-dan-mo@demo.vn")

    response = await api.post(
        "/api/v1/phien/bat-dau",
        json={"bin_code": "BIN-001"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ma_phien"], "Phải có ma_phien"
    assert body["trang_thai"] == "dang_mo"
    assert body["so_vat"] == 0
    phien = api_session.scalar(select(PhienThung).where(PhienThung.ma_phien == body["ma_phien"]))
    assert phien is not None and phien.user_id == cu_dan.id


@pytest.mark.asyncio
async def test_mo_lai_phien_cua_minh_tra_phien_cu(
    api: AsyncClient, api_session: Session
) -> None:
    _them_thung(api_session)
    _them_cu_dan(api_session, "cu-dan-mo-lai@demo.vn")
    api_session.commit()
    token = await _dang_nhap(api, "cu-dan-mo-lai@demo.vn")

    lan_1 = await api.post("/api/v1/phien/bat-dau", json={"bin_code": "BIN-001"}, headers=_auth(token))
    lan_2 = await api.post("/api/v1/phien/bat-dau", json={"bin_code": "BIN-001"}, headers=_auth(token))

    assert lan_1.json()["ma_phien"] == lan_2.json()["ma_phien"], "Chủ gọi lại phải nhận phiên cũ"
    so_phien = api_session.scalar(select(func.count(PhienThung.id)))
    assert so_phien == 1, "Không được đẻ phiên thứ hai"


@pytest.mark.asyncio
async def test_thung_bi_nguoi_khac_chiem_thi_tu_choi(
    api: AsyncClient, api_session: Session
) -> None:
    _them_thung(api_session)
    _them_cu_dan(api_session, "cu-dan-a@demo.vn")
    _them_cu_dan(api_session, "cu-dan-b@demo.vn")
    api_session.commit()
    token_a = await _dang_nhap(api, "cu-dan-a@demo.vn")
    token_b = await _dang_nhap(api, "cu-dan-b@demo.vn")

    dau = await api.post("/api/v1/phien/bat-dau", json={"bin_code": "BIN-001"}, headers=_auth(token_a))
    assert dau.status_code == 200, dau.text

    sau = await api.post("/api/v1/phien/bat-dau", json={"bin_code": "BIN-001"}, headers=_auth(token_b))

    assert sau.status_code == 400, sau.text
    assert "đang có người sử dụng" in sau.json()["error"]["message_vi"]


@pytest.mark.asyncio
async def test_thung_khong_ton_tai_tra_loi_khuon_repo(
    api: AsyncClient, api_session: Session
) -> None:
    _them_cu_dan(api_session, "cu-dan-404@demo.vn")
    api_session.commit()
    token = await _dang_nhap(api, "cu-dan-404@demo.vn")

    response = await api.post(
        "/api/v1/phien/bat-dau", json={"bin_code": "BIN-KHONG-CO"}, headers=_auth(token)
    )

    assert response.status_code == 400, response.text
    loi = response.json()["error"]
    assert "Không tìm thấy thùng" in loi["message_vi"]


@pytest.mark.asyncio
async def test_nguoi_khac_xem_phien_tra_404(
    api: AsyncClient, api_session: Session
) -> None:
    _them_thung(api_session)
    _them_cu_dan(api_session, "chu-phien@demo.vn")
    _them_cu_dan(api_session, "nguoi-la@demo.vn")
    api_session.commit()
    token_chu = await _dang_nhap(api, "chu-phien@demo.vn")
    token_la = await _dang_nhap(api, "nguoi-la@demo.vn")

    mo = await api.post("/api/v1/phien/bat-dau", json={"bin_code": "BIN-001"}, headers=_auth(token_chu))
    ma_phien = mo.json()["ma_phien"]

    response = await api.get(f"/api/v1/phien/{ma_phien}", headers=_auth(token_la))

    assert response.status_code == 404, "Người lạ xem phiên phải nhận 404, không phải 403"


@pytest.mark.asyncio
async def test_nguoi_khac_dong_phien_tra_404(
    api: AsyncClient, api_session: Session
) -> None:
    _them_thung(api_session)
    _them_cu_dan(api_session, "chu-phien-2@demo.vn")
    _them_cu_dan(api_session, "nguoi-la-2@demo.vn")
    api_session.commit()
    token_chu = await _dang_nhap(api, "chu-phien-2@demo.vn")
    token_la = await _dang_nhap(api, "nguoi-la-2@demo.vn")

    mo = await api.post("/api/v1/phien/bat-dau", json={"bin_code": "BIN-001"}, headers=_auth(token_chu))
    ma_phien = mo.json()["ma_phien"]

    response = await api.post(f"/api/v1/phien/{ma_phien}/dong", headers=_auth(token_la))

    assert response.status_code == 404, "Người lạ đóng phiên phải nhận 404, không phải 403"


@pytest.mark.asyncio
async def test_chu_phien_xem_va_dong_duoc(
    api: AsyncClient, api_session: Session
) -> None:
    _them_thung(api_session)
    _them_cu_dan(api_session, "chu-phien-3@demo.vn")
    api_session.commit()
    token = await _dang_nhap(api, "chu-phien-3@demo.vn")

    mo = await api.post("/api/v1/phien/bat-dau", json={"bin_code": "BIN-001"}, headers=_auth(token))
    ma_phien = mo.json()["ma_phien"]

    xem = await api.get(f"/api/v1/phien/{ma_phien}", headers=_auth(token))
    assert xem.status_code == 200, xem.text
    assert xem.json()["trang_thai"] == "dang_mo"

    dong = await api.post(f"/api/v1/phien/{ma_phien}/dong", headers=_auth(token))
    assert dong.status_code == 200, dong.text
    assert dong.json()["trang_thai"] == "da_dong"


@pytest.mark.asyncio
async def test_dong_phien_tao_thong_bao_khong_cham_diem(
    api: AsyncClient, api_session: Session
) -> None:
    _them_thung(api_session)
    cu_dan = _them_cu_dan(api_session, "chu-phien-4@demo.vn")
    cu_dan.green_points = 50
    api_session.commit()
    token = await _dang_nhap(api, "chu-phien-4@demo.vn")

    mo = await api.post("/api/v1/phien/bat-dau", json={"bin_code": "BIN-001"}, headers=_auth(token))
    ma_phien = mo.json()["ma_phien"]
    await api.post(f"/api/v1/phien/{ma_phien}/dong", headers=_auth(token))

    thong_bao = api_session.scalar(select(Notification).where(Notification.user_id == cu_dan.id))
    assert thong_bao is not None, "Đóng phiên phải sinh thông báo trong app"
    api_session.refresh(cu_dan)
    assert cu_dan.green_points == 50, "green_points không được đổi"
    so_so_cai = api_session.scalar(select(func.count(DiemThuongLog.id)))
    assert so_so_cai == 0, "diem_thuong_log không được có dòng mới"
