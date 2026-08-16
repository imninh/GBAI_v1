"""Test lịch sử theo vật liệu — R-04, và ranh giới dữ liệu cá nhân."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base, Classification, PickupRequest, User, WasteCategory
from src.main import app

MAT_KHAU = "demo1234"


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
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


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _nguoi(session: Session, email: str) -> User:
    user = session.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


def _hai_ma_nhom(session: Session) -> tuple[WasteCategory, WasteCategory]:
    """Hai nhóm rác bất kỳ, lấy từ CSDL thay vì chép cứng mã vào test."""
    rows = session.scalars(select(WasteCategory).order_by(WasteCategory.code)).all()
    assert len(rows) >= 2
    return rows[0], rows[1]


def _them_yeu_cau(
    session: Session, user: User, items: list[dict], *, status: str = "done", min_kg: float = 2.0, max_kg: float = 4.0
) -> PickupRequest:
    yeu_cau = PickupRequest(
        resident_id=user.id,
        unit_id=user.unit_id,
        items=items,
        weight_min_kg=min_kg,
        weight_max_kg=max_kg,
        est_weight_kg=(min_kg + max_kg) / 2,
        status=status,
    )
    session.add(yeu_cau)
    session.flush()
    return yeu_cau


# --- Lịch sử theo vật liệu -------------------------------------------------


@pytest.mark.asyncio
async def test_chua_co_gi_thi_tra_ve_rong_chu_khong_no(api: AsyncClient, api_session: Session) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.get("/api/v1/auth/me/history", headers=_bearer(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["theo_vat_lieu"] == []
    assert body["tong"]["so_yeu_cau"] == 0
    assert body["tong"]["khoi_luong_min_kg"] == 0
    assert body["ghi_chu"]


@pytest.mark.asyncio
async def test_dem_dung_so_mon_va_so_yeu_cau_theo_vat_lieu(api: AsyncClient, api_session: Session) -> None:
    """Hai yêu cầu cùng chạm một nhóm thì nhóm đó có 2 yêu cầu, số món cộng dồn."""
    cu_dan = _nguoi(api_session, "resident@demo.vn")
    a, b = _hai_ma_nhom(api_session)
    _them_yeu_cau(api_session, cu_dan, [{"name": "x", "category_code": a.code, "qty": 2}])
    _them_yeu_cau(
        api_session,
        cu_dan,
        [{"name": "y", "category_code": a.code, "qty": 1}, {"name": "z", "category_code": b.code, "qty": 3}],
    )
    api_session.commit()
    token = await _dang_nhap(api, "resident@demo.vn")

    body = (await api.get("/api/v1/auth/me/history", headers=_bearer(token))).json()
    theo = {r["category_code"]: r for r in body["theo_vat_lieu"]}

    assert theo[a.code]["so_mon"] == 3
    assert theo[a.code]["so_yeu_cau"] == 2
    assert theo[b.code]["so_mon"] == 3
    assert theo[b.code]["so_yeu_cau"] == 1
    assert body["tong"]["so_yeu_cau"] == 2


@pytest.mark.asyncio
async def test_yeu_cau_bi_huy_va_bi_tu_choi_khong_tinh(api: AsyncClient, api_session: Session) -> None:
    cu_dan = _nguoi(api_session, "resident@demo.vn")
    a, _ = _hai_ma_nhom(api_session)
    _them_yeu_cau(api_session, cu_dan, [{"name": "x", "category_code": a.code, "qty": 1}], status="cancelled")
    _them_yeu_cau(api_session, cu_dan, [{"name": "y", "category_code": a.code, "qty": 1}], status="rejected")
    api_session.commit()
    token = await _dang_nhap(api, "resident@demo.vn")

    body = (await api.get("/api/v1/auth/me/history", headers=_bearer(token))).json()

    assert body["tong"]["so_yeu_cau"] == 0
    assert body["theo_vat_lieu"] == []


@pytest.mark.asyncio
async def test_khoi_luong_la_khoang_va_khong_chia_theo_vat_lieu(api: AsyncClient, api_session: Session) -> None:
    """Quyết định đã chốt: kg chỉ tổng ở mức toàn bộ, không có kg trong từng dòng vật liệu."""
    cu_dan = _nguoi(api_session, "resident@demo.vn")
    a, _ = _hai_ma_nhom(api_session)
    _them_yeu_cau(api_session, cu_dan, [{"name": "x", "category_code": a.code, "qty": 1}], min_kg=1.5, max_kg=3.0)
    _them_yeu_cau(api_session, cu_dan, [{"name": "y", "category_code": a.code, "qty": 1}], min_kg=2.5, max_kg=5.0)
    api_session.commit()
    token = await _dang_nhap(api, "resident@demo.vn")

    body = (await api.get("/api/v1/auth/me/history", headers=_bearer(token))).json()

    assert body["tong"]["khoi_luong_min_kg"] == 4.0
    assert body["tong"]["khoi_luong_max_kg"] == 8.0
    for dong in body["theo_vat_lieu"]:
        assert not any("kg" in khoa for khoa in dong)


@pytest.mark.asyncio
async def test_chi_dem_cau_hoi_cua_chinh_minh(api: AsyncClient, api_session: Session) -> None:
    """Màn cá nhân KHÔNG được đếm lẫn câu hỏi của người khác — đó là rò rỉ dữ liệu."""
    cu_dan = _nguoi(api_session, "resident@demo.vn")
    nguoi_khac = _nguoi(api_session, "manager@demo.vn")
    a, _ = _hai_ma_nhom(api_session)
    for _ in range(2):
        api_session.add(Classification(asker_id=cu_dan.id, predicted_category_id=a.id, input_type="text"))
    for _ in range(3):
        api_session.add(Classification(asker_id=nguoi_khac.id, predicted_category_id=a.id, input_type="text"))
    api_session.commit()
    token = await _dang_nhap(api, "resident@demo.vn")

    body = (await api.get("/api/v1/auth/me/history", headers=_bearer(token))).json()
    theo = {r["category_code"]: r for r in body["theo_vat_lieu"]}

    assert theo[a.code]["so_lan_hoi"] == 2, "đang đếm cả câu hỏi của người khác"


@pytest.mark.asyncio
async def test_moi_nguoi_chi_thay_yeu_cau_cua_minh(api: AsyncClient, api_session: Session) -> None:
    cu_dan = _nguoi(api_session, "resident@demo.vn")
    a, _ = _hai_ma_nhom(api_session)
    _them_yeu_cau(api_session, cu_dan, [{"name": "x", "category_code": a.code, "qty": 5}])
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    body = (await api.get("/api/v1/auth/me/history", headers=_bearer(token))).json()

    assert body["tong"]["so_yeu_cau"] == 0
    assert body["theo_vat_lieu"] == []


@pytest.mark.asyncio
async def test_khong_dang_nhap_thi_401(api: AsyncClient, api_session: Session) -> None:
    response = await api.get("/api/v1/auth/me/history")

    assert response.status_code == 401
