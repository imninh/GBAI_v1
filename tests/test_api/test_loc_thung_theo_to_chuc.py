"""Gói A1b — lọc dữ liệu thùng theo đơn vị thu gom.

Hai lớp lọc cộng dồn, đúng thứ tự trong LUẬT LỌC:

1. Lớp tổ chức: người có ``organization_id`` chỉ thấy thùng của đơn vị mình,
   **cộng với** thùng chưa gắn đơn vị nào (``organization_id IS NULL``).
2. Lớp nhân viên: vai ``cleaner`` chỉ thấy thùng được giao cho chính mình.

Thùng ``IS NULL`` phải hiện với MỌI người xem — đó là ràng buộc quan trọng nhất
và cũng là test chốt chặn của gói này. Cư dân không dính lớp nào: ``diem-gui``
giữ nguyên từng dòng.

Khuôn dựng dữ liệu mượn nguyên văn từ ``test_loc_thung_theo_nhan_vien.py``.
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
from src.db.models import Base, Bin, Organization, User
from src.main import app
from src.services.security import hash_password

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


@pytest_asyncio.fixture
async def boi_canh(api: AsyncClient, api_session: Session) -> dict[str, object]:
    """Hai đơn vị A/B, mỗi đơn vị hai thùng, cộng một thùng chưa gắn đơn vị nào.

    Quản lý A và B mỗi người một đơn vị; một nhân viên của A giữ đúng 1 thùng
    của A để test lớp lọc thứ hai. Kèm token của quản lý A/B, quản lý chưa gắn
    đơn vị, nhân viên A và cư dân.
    """
    to_chuc_a = Organization(code="TO-A", name="Đơn vị A")
    to_chuc_b = Organization(code="TO-B", name="Đơn vị B")
    api_session.add_all([to_chuc_a, to_chuc_b])
    api_session.flush()

    manager_a = api_session.scalar(select(User).where(User.email == "manager@demo.vn"))
    cleaner_a = api_session.scalar(select(User).where(User.email == "cleaner@demo.vn"))
    manager_b = User(
        email="manager-b@demo.vn",
        full_name="Quản lý đơn vị B",
        role="manager",
        password_hash=hash_password(MAT_KHAU),
    )
    manager_tu_do = User(
        email="manager-tu-do@demo.vn",
        full_name="Quản lý chưa gắn đơn vị",
        role="manager",
        password_hash=hash_password(MAT_KHAU),
    )
    manager_a.organization_id = to_chuc_a.id
    manager_b.organization_id = to_chuc_b.id
    cleaner_a.organization_id = to_chuc_a.id
    api_session.add_all([manager_b, manager_tu_do])
    api_session.flush()

    thung_a1 = _tao_thung(api_session, code="BIN-A1", organization_id=to_chuc_a.id)
    _tao_thung(api_session, code="BIN-A2", organization_id=to_chuc_a.id)
    _tao_thung(api_session, code="BIN-B1", organization_id=to_chuc_b.id)
    _tao_thung(api_session, code="BIN-B2", organization_id=to_chuc_b.id)
    _tao_thung(api_session, code="BIN-CHUA-DON-VI")  # organization_id = None
    thung_a1.assigned_cleaner_id = cleaner_a.id
    api_session.commit()

    return {
        "token_a": await _dang_nhap(api, "manager@demo.vn"),
        "token_b": await _dang_nhap(api, "manager-b@demo.vn"),
        "token_tu_do": await _dang_nhap(api, "manager-tu-do@demo.vn"),
        "token_cleaner_a": await _dang_nhap(api, "cleaner@demo.vn"),
        "token_resident": await _dang_nhap(api, "resident@demo.vn"),
    }


@pytest.mark.asyncio
async def test_quan_ly_chi_thay_thung_cua_don_vi_minh(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins", headers=_auth(boi_canh["token_a"]))

    assert response.status_code == 200, response.text
    codes = [i["code"] for i in response.json()["items"]]
    assert sorted(codes) == ["BIN-A1", "BIN-A2", "BIN-CHUA-DON-VI"]
    assert not any(c.startswith("BIN-B") for c in codes), "Không được lọt thùng của đơn vị B vào danh sách của A"


@pytest.mark.asyncio
async def test_thung_chua_gan_don_vi_thi_moi_don_vi_deu_thay(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    """Chốt chặn quan trọng nhất: thùng ``organization_id IS NULL`` phải hiện cho mọi đơn vị."""
    for token in (boi_canh["token_a"], boi_canh["token_b"]):
        response = await api.get("/api/v1/bins", headers=_auth(token))
        assert response.status_code == 200, response.text
        codes = [i["code"] for i in response.json()["items"]]
        assert "BIN-CHUA-DON-VI" in codes, "Thùng chưa gắn đơn vị là việc phải xử, không được giấu đi"


@pytest.mark.asyncio
async def test_thong_ke_khop_voi_danh_sach(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    for token in (boi_canh["token_a"], boi_canh["token_b"]):
        danh_sach = await api.get("/api/v1/bins", headers=_auth(token))
        thong_ke = await api.get("/api/v1/bins/stats", headers=_auth(token))

        assert thong_ke.status_code == 200, thong_ke.text
        assert thong_ke.json()["tong"] == len(danh_sach.json()["items"]), (
            "Thẻ tổng trên dashboard phải khớp đúng số dòng trong danh sách"
        )


@pytest.mark.asyncio
async def test_mo_thung_cua_don_vi_khac_thi_404(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    """Thùng ngoài đơn vị và thùng không tồn tại phải không phân biệt được."""
    cua_don_vi_khac = await api.get("/api/v1/bins/BIN-B1", headers=_auth(boi_canh["token_a"]))
    khong_ton_tai = await api.get("/api/v1/bins/BIN-KHONG-CO-THAT", headers=_auth(boi_canh["token_a"]))

    assert cua_don_vi_khac.status_code == 404
    assert khong_ton_tai.status_code == 404
    loi_khac = cua_don_vi_khac.json()["error"]["message_vi"]
    loi_khong = khong_ton_tai.json()["error"]["message_vi"]
    loi_khong_doi_ma = loi_khong.replace("BIN-KHONG-CO-THAT", "BIN-B1")
    assert loi_khac == loi_khong_doi_ma, "Chỉ khác mỗi mã thùng trong câu, nếu không thì lộ mã có thật"


@pytest.mark.asyncio
async def test_nguoi_chua_gan_don_vi_thi_khong_bi_loc(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins", headers=_auth(boi_canh["token_tu_do"]))

    assert response.status_code == 200, response.text
    codes = [i["code"] for i in response.json()["items"]]
    assert sorted(codes) == ["BIN-A1", "BIN-A2", "BIN-B1", "BIN-B2", "BIN-CHUA-DON-VI"], (
        "Người chưa gắn đơn vị không bị lọc lớp tổ chức — đúng hành vi trước gói"
    )


@pytest.mark.asyncio
async def test_hai_lop_loc_cong_don(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    """Cleaner thuộc đơn vị A, được giao 1 thùng của A → chỉ thấy đúng thùng đó."""
    response = await api.get("/api/v1/bins", headers=_auth(boi_canh["token_cleaner_a"]))

    assert response.status_code == 200, response.text
    codes = [i["code"] for i in response.json()["items"]]
    assert sorted(codes) == ["BIN-A1"], (
        "Không thấy thùng khác của đơn vị A (chưa giao cho mình), cũng không thấy thùng của B"
    )


@pytest.mark.asyncio
async def test_cu_dan_van_thay_du_diem_gui(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins/diem-gui", headers=_auth(boi_canh["token_resident"]))

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 5, (
        "Cư dân phải thấy mọi điểm gửi — không lọc lây theo đơn vị"
    )
