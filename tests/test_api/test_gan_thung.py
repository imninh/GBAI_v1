"""Test gán thùng cho nhân viên vệ sinh — nửa GHI của gói A2a.

Nửa ĐỌC (lọc ``GET /bins`` theo người đang đăng nhập) là gói A2b, không nằm
trong file này — mọi endpoint đọc vẫn trả đúng như cũ cho cả ``cleaner`` lẫn
``manager``.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import AuditLog, Base, Bin, Organization, User
from src.db.seed_data import gan_thung_demo
from src.main import app
from src.services.bins import gan_thung_cho_nhan_vien

MAT_KHAU = "demo1234"

_so_thung = itertools.count(1)


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    """Cấu hình đọc qua ``lru_cache`` nên phải xoá cache quanh mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """CSDL trong bộ nhớ đã seed dữ liệu nền, gắn vào dependency của app."""
    from scripts.seed import seed_buildings, seed_categories, seed_knowledge, seed_schedules, seed_units, seed_users

    # StaticPool là bắt buộc: FastAPI chạy endpoint đồng bộ ở threadpool, mà
    # SQLite in-memory mặc định cấp cho mỗi thread một CSDL rỗng riêng.
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


def _tao_thung(session: Session, **fields: object) -> Bin:
    """Tạo một thùng cho test; mã tự sinh nếu không truyền."""
    defaults: dict[str, object] = {
        "code": f"BIN-{next(_so_thung):03d}",
        "name": "Thùng Bờ Hồ",
        "address": "Phố Đinh Tiên Hoàng, Hoàn Kiếm, Hà Nội",
        "lat": 21.0285,
        "lng": 105.8542,
        "fill_percent": 10.0,
        "battery_percent": 100.0,
        "last_seen_at": datetime.now(UTC),
        "is_active": True,
        "is_seed": False,
    }
    defaults.update(fields)
    thung = Bin(**defaults)
    session.add(thung)
    session.flush()
    return thung


def test_thung_moi_mac_dinh_chua_gan_ai(api_session: Session) -> None:
    thung = _tao_thung(api_session)
    api_session.commit()
    assert thung.assigned_cleaner_id is None


def test_cot_duoc_khai_trong_cot_can_va() -> None:
    """Tấm chắn cho bẫy hạ tầng: cột mới phải được khai để vá CSDL đã tồn tại."""
    from src.db.schema_patch import COT_CAN_VA

    cac_cot = {(bang, cot) for bang, cot, _ in COT_CAN_VA}
    assert ("bins", "assigned_cleaner_id") in cac_cot


@pytest.mark.asyncio
async def test_manager_gan_duoc_thung_cho_nhan_vien(api: AsyncClient, api_session: Session) -> None:
    thung = _tao_thung(api_session, code="BIN-GAN-01")
    api_session.commit()
    nhan_vien = api_session.scalar(select(User).where(User.email == "cleaner@demo.vn"))
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.patch(
        f"/api/v1/bins/{thung.code}/nhan-vien",
        json={"cleaner_id": nhan_vien.id},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["assigned_cleaner_id"] == nhan_vien.id
    assert response.json()["assigned_cleaner_name"] == nhan_vien.full_name
    api_session.refresh(thung)
    assert thung.assigned_cleaner_id == nhan_vien.id


@pytest.mark.asyncio
async def test_bo_gan_bang_cleaner_id_null(api: AsyncClient, api_session: Session) -> None:
    thung = _tao_thung(api_session, code="BIN-BO-GAN")
    api_session.commit()
    nhan_vien = api_session.scalar(select(User).where(User.email == "cleaner@demo.vn"))
    thung.assigned_cleaner_id = nhan_vien.id
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.patch(
        f"/api/v1/bins/{thung.code}/nhan-vien",
        json={"cleaner_id": None},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["assigned_cleaner_id"] is None
    assert response.json()["assigned_cleaner_name"] == ""
    api_session.refresh(thung)
    assert thung.assigned_cleaner_id is None


@pytest.mark.asyncio
async def test_khong_gan_duoc_cho_cu_dan(api: AsyncClient, api_session: Session) -> None:
    thung = _tao_thung(api_session, code="BIN-CU-DAN")
    api_session.commit()
    cu_dan = api_session.scalar(select(User).where(User.email == "resident@demo.vn"))
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.patch(
        f"/api/v1/bins/{thung.code}/nhan-vien",
        json={"cleaner_id": cu_dan.id},
        headers=_auth(token),
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "BIN-400"
    api_session.refresh(thung)
    assert thung.assigned_cleaner_id is None


@pytest.mark.asyncio
async def test_nhan_vien_khong_duoc_tu_gan_thung(api: AsyncClient, api_session: Session) -> None:
    thung = _tao_thung(api_session, code="BIN-KHONG-TU-GAN")
    api_session.commit()
    nhan_vien = api_session.scalar(select(User).where(User.email == "cleaner@demo.vn"))
    token = await _dang_nhap(api, "cleaner@demo.vn")

    response = await api.patch(
        f"/api/v1/bins/{thung.code}/nhan-vien",
        json={"cleaner_id": nhan_vien.id},
        headers=_auth(token),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_ma_thung_khong_ton_tai_thi_404(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.patch(
        "/api/v1/bins/BIN-KHONG-CO/nhan-vien",
        json={"cleaner_id": 1},
        headers=_auth(token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NF-404"


@pytest.mark.asyncio
async def test_id_nhan_vien_khong_ton_tai_thi_404(api: AsyncClient, api_session: Session) -> None:
    thung = _tao_thung(api_session, code="BIN-NV-KHONG-CO")
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.patch(
        f"/api/v1/bins/{thung.code}/nhan-vien",
        json={"cleaner_id": 999999},
        headers=_auth(token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ghi_audit_log_moi_lan_gan(api: AsyncClient, api_session: Session) -> None:
    thung = _tao_thung(api_session, code="BIN-AUDIT")
    api_session.commit()
    nhan_vien = api_session.scalar(select(User).where(User.email == "cleaner@demo.vn"))
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.patch(
        f"/api/v1/bins/{thung.code}/nhan-vien",
        json={"cleaner_id": nhan_vien.id},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text

    dong = api_session.scalar(select(AuditLog).where(AuditLog.action == "assign_bin"))
    assert dong is not None
    assert dong.entity == "bin"
    assert dong.entity_id == thung.code
    assert dong.detail["truoc"] != dong.detail["sau"]
    assert dong.detail["sau"] == nhan_vien.id


def test_gan_thung_demo_khong_ghi_de_gan_thu_cong(api_session: Session) -> None:
    for ma in ("BIN-01", "BIN-02", "BIN-03"):
        _tao_thung(api_session, code=ma)
    # KHÔNG dùng `cleaner2@demo.vn`: đó là tài khoản demo có thật trong seed
    # (gói P1), trùng email là `UNIQUE constraint failed` ngay lúc flush.
    nhan_vien_khac = User(
        email="cleaner-rieng-cua-test@demo.vn",
        full_name="Nhân viên do test tự tạo",
        role="cleaner",
        password_hash="x",
    )
    api_session.add(nhan_vien_khac)
    api_session.flush()
    thung_01 = api_session.scalar(select(Bin).where(Bin.code == "BIN-01"))
    gan_thung_cho_nhan_vien(api_session, thung_01, nhan_vien_khac)
    api_session.commit()

    lan_dau = gan_thung_demo(api_session)
    lan_hai = gan_thung_demo(api_session)
    api_session.commit()

    assert lan_dau == 2, "BIN-01 đã có người, BIN-02/BIN-03 về cleaner@demo.vn, BIN-04..06 chưa tồn tại"
    assert lan_hai == 0, "Gọi lần hai phải không ghi đè gì nữa"
    assert thung_01.assigned_cleaner_id == nhan_vien_khac.id
    for ma in ("BIN-02", "BIN-03"):
        thung = api_session.scalar(select(Bin).where(Bin.code == ma))
        assert thung.assigned_cleaner_id is not None


# --- Gói P15: chặn giao chéo đơn vị ------------------------------------------


@pytest_asyncio.fixture
async def boi_canh_don_vi(api: AsyncClient, api_session: Session) -> dict[str, object]:
    """Hai đơn vị A/B cho phần gán thùng theo tổ chức.

    - manager@demo.vn gắn đơn vị A;
    - nhan_vien_a (cleaner@demo.vn) thuộc A; nhan_vien_b thuộc B;
    - nhan_vien_tu_do chưa gắn đơn vị;
    - bin_a1 thuộc A; bin_tu_do chưa gắn đơn vị.
    """
    to_chuc_a = Organization(code="TO-GAN-A", name="Đơn vị A")
    to_chuc_b = Organization(code="TO-GAN-B", name="Đơn vị B")
    api_session.add_all([to_chuc_a, to_chuc_b])
    api_session.flush()

    manager = api_session.scalar(select(User).where(User.email == "manager@demo.vn"))
    manager.organization_id = to_chuc_a.id
    nhan_vien_a = api_session.scalar(select(User).where(User.email == "cleaner@demo.vn"))
    nhan_vien_a.organization_id = to_chuc_a.id
    nhan_vien_b = User(
        email="cleaner-b-gan@demo.vn",
        full_name="Nhân viên đơn vị B",
        role="cleaner",
        password_hash="x",
        organization_id=to_chuc_b.id,
    )
    nhan_vien_tu_do = User(
        email="cleaner-tu-do-gan@demo.vn",
        full_name="Nhân viên chưa gắn đơn vị",
        role="cleaner",
        password_hash="x",
    )
    api_session.add_all([nhan_vien_b, nhan_vien_tu_do])
    api_session.flush()

    bin_a1 = _tao_thung(api_session, code="BIN-GAN-A1", organization_id=to_chuc_a.id)
    bin_tu_do = _tao_thung(api_session, code="BIN-GAN-TU-DO")  # organization_id = None
    api_session.commit()

    return {
        "token_manager": await _dang_nhap(api, "manager@demo.vn"),
        "id_a": nhan_vien_a.id,
        "id_b": nhan_vien_b.id,
        "id_tu_do": nhan_vien_tu_do.id,
        "bin_a1": bin_a1.code,
        "bin_tu_do": bin_tu_do.code,
    }


@pytest.mark.asyncio
async def test_khong_giao_duoc_thung_cho_nhan_vien_khac_don_vi(
    api: AsyncClient, api_session: Session, boi_canh_don_vi: dict[str, object]
) -> None:
    response = await api.patch(
        f"/api/v1/bins/{boi_canh_don_vi['bin_a1']}/nhan-vien",
        json={"cleaner_id": boi_canh_don_vi["id_b"]},
        headers=_auth(boi_canh_don_vi["token_manager"]),
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "BIN-400"
    thung = api_session.scalar(select(Bin).where(Bin.code == boi_canh_don_vi["bin_a1"]))
    assert thung.assigned_cleaner_id is None, "Giao chéo đơn vị bị chặn, thùng không được đổi người"


@pytest.mark.asyncio
async def test_van_giao_duoc_trong_cung_don_vi(
    api: AsyncClient, api_session: Session, boi_canh_don_vi: dict[str, object]
) -> None:
    response = await api.patch(
        f"/api/v1/bins/{boi_canh_don_vi['bin_a1']}/nhan-vien",
        json={"cleaner_id": boi_canh_don_vi["id_a"]},
        headers=_auth(boi_canh_don_vi["token_manager"]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["assigned_cleaner_id"] == boi_canh_don_vi["id_a"]


@pytest.mark.asyncio
async def test_van_bo_gan_duoc(
    api: AsyncClient, api_session: Session, boi_canh_don_vi: dict[str, object]
) -> None:
    thung = api_session.scalar(select(Bin).where(Bin.code == boi_canh_don_vi["bin_a1"]))
    thung.assigned_cleaner_id = boi_canh_don_vi["id_a"]
    api_session.commit()

    response = await api.patch(
        f"/api/v1/bins/{boi_canh_don_vi['bin_a1']}/nhan-vien",
        json={"cleaner_id": None},
        headers=_auth(boi_canh_don_vi["token_manager"]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["assigned_cleaner_id"] is None
    assert response.json()["assigned_cleaner_name"] == ""


@pytest.mark.asyncio
async def test_van_giao_duoc_khi_ca_hai_chua_co_don_vi(
    api: AsyncClient, api_session: Session, boi_canh_don_vi: dict[str, object]
) -> None:
    """Thùng và nhân viên đều chưa gắn đơn vị thì vẫn phải giao được — luật NULL của P12."""
    response = await api.patch(
        f"/api/v1/bins/{boi_canh_don_vi['bin_tu_do']}/nhan-vien",
        json={"cleaner_id": boi_canh_don_vi["id_tu_do"]},
        headers=_auth(boi_canh_don_vi["token_manager"]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["assigned_cleaner_id"] == boi_canh_don_vi["id_tu_do"]


@pytest.mark.asyncio
async def test_van_giao_duoc_thung_chua_gan_don_vi_cho_nhan_vien_da_co_don_vi(
    api: AsyncClient, api_session: Session, boi_canh_don_vi: dict[str, object]
) -> None:
    """Thùng chưa gắn đơn vị vẫn giao được cho nhân viên đã gắn đơn vị.

    Đây là test CHẶN LỖI GÀI của gói P15: so sánh ``organization_id`` bằng ``!=``
    mà không bảo vệ NULL thì ``A != None`` = True, chặn nhầm ca này.
    """
    response = await api.patch(
        f"/api/v1/bins/{boi_canh_don_vi['bin_tu_do']}/nhan-vien",
        json={"cleaner_id": boi_canh_don_vi["id_a"]},
        headers=_auth(boi_canh_don_vi["token_manager"]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["assigned_cleaner_id"] == boi_canh_don_vi["id_a"]
