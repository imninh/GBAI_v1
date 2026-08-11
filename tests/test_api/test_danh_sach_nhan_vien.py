"""GET /bins/nhan-vien — danh sách nhân viên vệ sinh kèm số thùng được giao.

Dùng cho màn giao thùng của ban quản lý (gói A2c). Quyền ``assign_bin`` chứ
không phải ``view_bins`` — chỉ người giao được thùng mới cần biết danh sách
người nhận. Chỉ trả bốn trường, không lọ thông tin nhạy cảm.
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
    """Ba nhân viên: A (2 thùng), B (1 thùng), C (0 thùng) — kèm token các vai."""
    nhan_vien_a = api_session.scalar(select(User).where(User.email == "cleaner@demo.vn"))
    nhan_vien_b = User(
        email="cleaner-b@demo.vn",
        full_name="Nhân viên vệ sinh B",
        role="cleaner",
        password_hash="x",
    )
    nhan_vien_c = User(
        email="cleaner-c@demo.vn",
        full_name="Nhân viên vệ sinh C",
        role="cleaner",
        password_hash="x",
    )
    api_session.add_all([nhan_vien_b, nhan_vien_c])
    api_session.flush()

    bin_a1 = _tao_thung(api_session, code="BIN-NV-A1")
    bin_a2 = _tao_thung(api_session, code="BIN-NV-A2")
    bin_b1 = _tao_thung(api_session, code="BIN-NV-B1")
    bin_a1.assigned_cleaner_id = nhan_vien_a.id
    bin_a2.assigned_cleaner_id = nhan_vien_a.id
    bin_b1.assigned_cleaner_id = nhan_vien_b.id
    api_session.commit()

    return {
        "token_manager": await _dang_nhap(api, "manager@demo.vn"),
        "token_cleaner": await _dang_nhap(api, "cleaner@demo.vn"),
        "token_resident": await _dang_nhap(api, "resident@demo.vn"),
        "id_a": nhan_vien_a.id,
        "id_b": nhan_vien_b.id,
        "id_c": nhan_vien_c.id,
    }


@pytest.mark.asyncio
async def test_chi_tra_ve_nhan_vien_ve_sinh(
    api: AsyncClient, api_session: Session, boi_canh: dict[str, object]
) -> None:
    """Danh sách chỉ gồm vai `cleaner` — không lẫn cư dân hay quản lý.

    Khẳng định theo **vai trò của từng người trả về**, không đếm cứng số lượng:
    seed có thể thêm tài khoản nhân viên demo bất cứ lúc nào, mà điều test này
    muốn nói không phải là "có mấy người".
    """
    response = await api.get("/api/v1/bins/nhan-vien", headers=_auth(boi_canh["token_manager"]))

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    ids = {i["id"] for i in items}

    assert {boi_canh["id_a"], boi_canh["id_b"], boi_canh["id_c"]} <= ids, "Thiếu nhân viên của bối cảnh"

    vai_theo_id = {u.id: u.role for u in api_session.scalars(select(User)).all()}
    assert all(vai_theo_id[i] == "cleaner" for i in ids), "Lọt vai khác vào danh sách nhân viên"

    ma_quan_ly = api_session.scalar(select(User).where(User.email == "manager@demo.vn"))
    ma_cu_dan = api_session.scalar(select(User).where(User.email == "resident@demo.vn"))
    assert ma_quan_ly.id not in ids and ma_cu_dan.id not in ids


@pytest.mark.asyncio
async def test_dem_dung_so_thung_duoc_giao(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins/nhan-vien", headers=_auth(boi_canh["token_manager"]))

    assert response.status_code == 200, response.text
    theo_id = {i["id"]: i for i in response.json()["items"]}
    assert theo_id[boi_canh["id_a"]]["so_thung_duoc_giao"] == 2
    assert theo_id[boi_canh["id_b"]]["so_thung_duoc_giao"] == 1
    assert theo_id[boi_canh["id_c"]]["so_thung_duoc_giao"] == 0


@pytest.mark.asyncio
async def test_thung_ngung_dung_khong_duoc_tinh(
    api: AsyncClient, api_session: Session, boi_canh: dict[str, object]
) -> None:
    thung = api_session.scalar(select(Bin).where(Bin.code == "BIN-NV-A2"))
    thung.is_active = False
    api_session.commit()

    response = await api.get("/api/v1/bins/nhan-vien", headers=_auth(boi_canh["token_manager"]))

    assert response.status_code == 200, response.text
    theo_id = {i["id"]: i for i in response.json()["items"]}
    assert theo_id[boi_canh["id_a"]]["so_thung_duoc_giao"] == 1, "Thùng đã ngừng dùng không phải việc của ai"


@pytest.mark.asyncio
async def test_nhan_vien_khong_goi_duoc(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins/nhan-vien", headers=_auth(boi_canh["token_cleaner"]))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERM-403"


@pytest.mark.asyncio
async def test_cu_dan_khong_goi_duoc(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins/nhan-vien", headers=_auth(boi_canh["token_resident"]))

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_khong_lo_du_lieu_nhay_cam(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins/nhan-vien", headers=_auth(boi_canh["token_manager"]))

    assert response.status_code == 200, response.text
    for item in response.json()["items"]:
        assert set(item) == {"id", "full_name", "phone", "so_thung_duoc_giao"}, item


@pytest.mark.asyncio
async def test_route_khong_bi_nuot_boi_ma_thung(
    api: AsyncClient, api_session: Session, boi_canh: dict[str, object]
) -> None:
    """Có một thùng tên đúng bằng 'nhan-vien' nhưng request này phải về danh sách."""
    _tao_thung(api_session, code="nhan-vien")
    api_session.commit()

    response = await api.get("/api/v1/bins/nhan-vien", headers=_auth(boi_canh["token_manager"]))

    assert response.status_code == 200, response.text
    data = response.json()
    assert "items" in data, "Phải là danh sách nhân viên, không phải chi tiết thùng"
    assert "code" not in data, "Phải không phải phản hồi chi tiết một thùng"
    # KHÔNG đếm cứng: test này nói về thứ tự khai báo route, không nói về số
    # lượng nhân viên — mà số đó đổi mỗi lần seed thêm tài khoản demo.
    ids = {i["id"] for i in data["items"]}
    assert {boi_canh["id_a"], boi_canh["id_b"], boi_canh["id_c"]} <= ids


@pytest.mark.asyncio
async def test_thu_tu_xac_dinh(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    lan_dau = await api.get("/api/v1/bins/nhan-vien", headers=_auth(boi_canh["token_manager"]))
    lan_sau = await api.get("/api/v1/bins/nhan-vien", headers=_auth(boi_canh["token_manager"]))

    assert lan_dau.status_code == 200, lan_dau.text
    ids_dau = [i["id"] for i in lan_dau.json()["items"]]
    ids_sau = [i["id"] for i in lan_sau.json()["items"]]
    assert ids_dau == ids_sau, "Hai lần gọi phải trả cùng một thứ tự"

    ten = [i["full_name"] for i in lan_dau.json()["items"]]
    assert ten == sorted(ten), "Danh sách phải sắp theo full_name tăng dần"


# --- Gói P15: danh sách nhân viên theo đơn vị thu gom ------------------------


@pytest_asyncio.fixture
async def boi_canh_don_vi(api: AsyncClient, api_session: Session) -> dict[str, object]:
    """Hai đơn vị A/B cho phần lọc tổ chức của danh sách nhân viên.

    - manager@demo.vn gắn đơn vị A, manager-b@demo.vn gắn đơn vị B;
    - nhan_vien_a (cleaner@demo.vn) thuộc A, giữ 1 thùng của A và 1 thùng của B
      (dữ liệu cũ giao chéo — để test con số đếm không cộng thùng ngoài phạm vi);
    - nhan_vien_b (cleaner-b) thuộc B, giữ 1 thùng của B;
    - nhan_vien_tu_do chưa gắn đơn vị — phải hiện với quản lý của MỌI đơn vị.
    """
    to_chuc_a = Organization(code="TO-NV-A", name="Đơn vị A")
    to_chuc_b = Organization(code="TO-NV-B", name="Đơn vị B")
    api_session.add_all([to_chuc_a, to_chuc_b])
    api_session.flush()

    manager_a = api_session.scalar(select(User).where(User.email == "manager@demo.vn"))
    manager_b = User(
        email="manager-b-dv@demo.vn",
        full_name="Quản lý đơn vị B",
        role="manager",
        password_hash=hash_password(MAT_KHAU),
    )
    nhan_vien_a = api_session.scalar(select(User).where(User.email == "cleaner@demo.vn"))
    nhan_vien_b = User(
        email="cleaner-b-dv@demo.vn",
        full_name="Nhân viên đơn vị B",
        role="cleaner",
        password_hash="x",
    )
    nhan_vien_tu_do = User(
        email="cleaner-tu-do@demo.vn",
        full_name="Nhân viên chưa gắn đơn vị",
        role="cleaner",
        password_hash="x",
    )
    manager_a.organization_id = to_chuc_a.id
    manager_b.organization_id = to_chuc_b.id
    nhan_vien_a.organization_id = to_chuc_a.id
    nhan_vien_b.organization_id = to_chuc_b.id
    api_session.add_all([manager_b, nhan_vien_b, nhan_vien_tu_do])
    api_session.flush()

    bin_a1 = _tao_thung(api_session, code="BIN-DV-A1", organization_id=to_chuc_a.id)
    bin_b1 = _tao_thung(api_session, code="BIN-DV-B1", organization_id=to_chuc_b.id)
    bin_cheo = _tao_thung(api_session, code="BIN-DV-CHEO", organization_id=to_chuc_b.id)
    bin_a1.assigned_cleaner_id = nhan_vien_a.id
    bin_cheo.assigned_cleaner_id = nhan_vien_a.id
    bin_b1.assigned_cleaner_id = nhan_vien_b.id
    api_session.commit()

    return {
        "token_a": await _dang_nhap(api, "manager@demo.vn"),
        "token_b": await _dang_nhap(api, "manager-b-dv@demo.vn"),
        "id_a": nhan_vien_a.id,
        "id_b": nhan_vien_b.id,
        "id_tu_do": nhan_vien_tu_do.id,
    }


@pytest.mark.asyncio
async def test_quan_ly_chi_thay_nhan_vien_cua_don_vi_minh(
    api: AsyncClient, boi_canh_don_vi: dict[str, object]
) -> None:
    response = await api.get("/api/v1/bins/nhan-vien", headers=_auth(boi_canh_don_vi["token_a"]))

    assert response.status_code == 200, response.text
    ids = {i["id"] for i in response.json()["items"]}
    assert boi_canh_don_vi["id_a"] in ids
    assert boi_canh_don_vi["id_tu_do"] in ids
    assert boi_canh_don_vi["id_b"] not in ids, "Không được lọt nhân viên của đơn vị B vào danh sách của A"


@pytest.mark.asyncio
async def test_nhan_vien_chua_gan_don_vi_thi_van_hien(
    api: AsyncClient, boi_canh_don_vi: dict[str, object]
) -> None:
    """Nhân viên ``organization_id IS NULL`` hiện với quản lý của mọi đơn vị — luật NULL của P12."""
    for token in (boi_canh_don_vi["token_a"], boi_canh_don_vi["token_b"]):
        response = await api.get("/api/v1/bins/nhan-vien", headers=_auth(token))
        assert response.status_code == 200, response.text
        ids = {i["id"] for i in response.json()["items"]}
        assert boi_canh_don_vi["id_tu_do"] in ids, (
            "Nhân viên chưa gắn đơn vị là việc phải xử, không được giấu đi"
        )


@pytest.mark.asyncio
async def test_so_thung_dem_dung_pham_vi_don_vi(
    api: AsyncClient, boi_canh_don_vi: dict[str, object]
) -> None:
    """Con số ``so_thung_duoc_giao`` phải đếm đúng phạm vi đơn vị của người xem.

    Nhân viên A giữ 1 thùng của A + 1 thùng của B (dữ liệu cũ giao chéo); quản lý
    A phải thấy con số 1, không được cộng thêm thùng của B vào.
    """
    response = await api.get("/api/v1/bins/nhan-vien", headers=_auth(boi_canh_don_vi["token_a"]))

    assert response.status_code == 200, response.text
    theo_id = {i["id"]: i for i in response.json()["items"]}
    assert theo_id[boi_canh_don_vi["id_a"]]["so_thung_duoc_giao"] == 1, (
        "Chỉ đếm thùng trong phạm vi đơn vị A — thùng của B không được tính"
    )
