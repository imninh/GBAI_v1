"""Test đẩy yêu cầu thu gom dọc máy trạng thái — luồng của đội vệ sinh.

Endpoint ``POST /pickups/{id}/chuyen-trang-thai`` cho phép đội vệ sinh đẩy một
yêu cầu theo đúng máy trạng thái :mod:`src.services.pickup_lifecycle`: bước đi
không hợp lệ phải trả 400, id không tồn tại phải trả 404, và mỗi bước thành
công phải ghi một mốc ``PickupEvent`` lên timeline.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.api.serializers import pickup_dict
from src.config import reset_settings_cache
from src.db.models import Base, PickupEvent, PickupRequest, User
from src.main import app
from src.services.security import hash_password

MAT_KHAU = "demo1234"


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


async def _tao_yeu_cau(api: AsyncClient, token: str) -> dict:
    """Tạo một yêu cầu trong ngưỡng tự động → trạng thái ``cho_nhan``."""
    response = await api.post(
        "/api/v1/pickups",
        json=_payload_yeu_cau(),
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _payload_yeu_cau(**sua) -> dict:
    """Payload hợp lệ để tạo yêu cầu thu gom; ``sua`` ghi đè từng trường."""
    payload = {
        "items": [{"name": "Thùng carton", "category_code": "recyclable_paper", "qty": 2}],
        "est_weight_kg": 8,
        "preferred_date": (date.today() + timedelta(days=3)).isoformat(),
        "preferred_window": "08:00-10:00",
        "confirmed_no_hazardous": True,
    }
    payload.update(sua)
    return payload


def _them_cu_dan_khong_can_ho(
    session: Session,
    *,
    dia_chi: str,
    lat: float | None = None,
    lng: float | None = None,
) -> User:
    """Cư dân hộ dân lẻ (không thuộc căn hộ nào) để test nhánh unit_id = None."""
    cu_dan = User(
        email="dan_pho@demo.vn",
        phone="0901112222",
        full_name="Dân phố không căn hộ",
        role="resident",
        password_hash=hash_password(MAT_KHAU),
        unit_id=None,
        address=dia_chi,
        lat=lat,
        lng=lng,
    )
    session.add(cu_dan)
    session.flush()
    return cu_dan


def _dem_event(session: Session, request_id: int) -> int:
    """Số mốc trạng thái đã ghi cho một yêu cầu."""
    return int(
        session.scalar(
            select(func.count(PickupEvent.id)).where(
                PickupEvent.request_id == request_id,
                PickupEvent.kind == "status_changed",
            )
        )
        or 0
    )


# --- Luồng hợp lệ ----------------------------------------------------------


@pytest.mark.asyncio
async def test_luong_thu_gom_chay_qua_cac_buoc_hop_le(api: AsyncClient, api_session: Session) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    yeu_cau = await _tao_yeu_cau(api, resident)
    assert yeu_cau["status"] == "cho_nhan"
    request_id = yeu_cau["id"]

    for buoc in ("da_nhan", "dang_van_chuyen", "da_giao_don_vi"):
        response = await api.post(
            f"/api/v1/pickups/{request_id}/chuyen-trang-thai",
            json={"den": buoc},
            headers=_auth(cleaner),
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == buoc

    assert _dem_event(api_session, request_id) == 3, "Mỗi bước thành công phải ghi một mốc PickupEvent"


@pytest.mark.asyncio
async def test_moi_buoc_thanh_cong_ghi_mot_moc_pickup_event(api: AsyncClient, api_session: Session) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    yeu_cau = await _tao_yeu_cau(api, resident)

    response = await api.post(
        f"/api/v1/pickups/{yeu_cau['id']}/chuyen-trang-thai",
        json={"den": "da_nhan", "ghi_chu": "đã nhận thùng carton"},
        headers=_auth(cleaner),
    )

    assert response.status_code == 200
    mot_moc = api_session.scalar(
        select(PickupEvent).where(PickupEvent.request_id == yeu_cau["id"], PickupEvent.kind == "status_changed")
    )
    assert mot_moc is not None
    assert mot_moc.label_vi == "Trạng thái chuyển từ 'cho_nhan' sang 'da_nhan'"
    assert mot_moc.detail.get("ghi_chu") == "đã nhận thùng carton"


# --- Bước chuyển không hợp lệ ----------------------------------------------


@pytest.mark.asyncio
async def test_buoc_chuyen_bat_hop_le_tra_400(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    yeu_cau = await _tao_yeu_cau(api, resident)

    response = await api.post(
        f"/api/v1/pickups/{yeu_cau['id']}/chuyen-trang-thai",
        json={"den": "hoan_tat"},  # từ cho_nhan không thể nhảy thẳng tới hoan_tat
        headers=_auth(cleaner),
    )

    assert response.status_code == 400
    loi = response.json()["error"]
    assert "cho_nhan" in loi["message_vi"]
    assert "hoan_tat" in loi["message_vi"]


# --- Id không tồn tại ------------------------------------------------------


@pytest.mark.asyncio
async def test_yeu_cau_khong_ton_tai_tra_404(api: AsyncClient) -> None:
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")

    response = await api.post(
        "/api/v1/pickups/99999/chuyen-trang-thai",
        json={"den": "da_nhan"},
        headers=_auth(cleaner),
    )

    assert response.status_code == 404
    assert "error" in response.json()


# --- Phân quyền ------------------------------------------------------------


@pytest.mark.asyncio
async def test_cu_dan_khong_day_trang_thai(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    yeu_cau = await _tao_yeu_cau(api, resident)

    response = await api.post(
        f"/api/v1/pickups/{yeu_cau['id']}/chuyen-trang-thai",
        json={"den": "da_nhan"},
        headers=_auth(resident),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_buoc_chuyen_duoc_chuan_hoa_tu_vung_cu(api: AsyncClient) -> None:
    """Máy trạng thái chịu cả hai từ vựng — đích gửi từ vựng cũ vẫn bị chuẩn hoá."""
    resident = await _dang_nhap(api, "resident@demo.vn")
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    yeu_cau = await _tao_yeu_cau(api, resident)

    response = await api.post(
        f"/api/v1/pickups/{yeu_cau['id']}/chuyen-trang-thai",
        json={"den": "approved"},  # chuan_hoa → "cho_nhan", không phải bước đi từ chính nó
        headers=_auth(cleaner),
    )

    assert response.status_code == 400
    assert "error" in response.json()


# --- Xác nhận khối lượng thật ------------------------------------------------


async def _dua_toi_da_giao_don_vi(api: AsyncClient, token: str) -> int:
    """Đẩy một yêu cầu tới trạng thái ``da_giao_don_vi`` để test xác nhận."""
    resident = await _dang_nhap(api, "resident@demo.vn")
    yeu_cau = await _tao_yeu_cau(api, resident)
    request_id = yeu_cau["id"]
    for buoc in ("da_nhan", "dang_van_chuyen", "da_giao_don_vi"):
        response = await api.post(
            f"/api/v1/pickups/{request_id}/chuyen-trang-thai",
            json={"den": buoc},
            headers=_auth(token),
        )
        assert response.status_code == 200, response.text
    return request_id


@pytest.mark.asyncio
async def test_khoi_luong_trong_khoang_thi_hoan_tat(api: AsyncClient, api_session: Session) -> None:
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    request_id = await _dua_toi_da_giao_don_vi(api, cleaner)

    response = await api.post(
        f"/api/v1/pickups/{request_id}/xac-nhan-khoi-luong",
        json={"weight_confirmed_kg": 8.0},  # trung điểm của khoảng 4,8–11,2 kg
        headers=_auth(cleaner),
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "hoan_tat"
    # Bốn trường của package 7 phải hiện trên serializer để màn duyệt hiển thị.
    assert data["weight_confirmed_kg"] == 8.0
    assert data["confirmed_by"] is not None
    assert data["confirmed_at"] is not None
    assert data["dispute_reason"] == ""

    yeu_cau = api_session.get(PickupRequest, request_id)
    assert yeu_cau.weight_confirmed_kg == 8.0
    assert yeu_cau.confirmed_by is not None
    assert yeu_cau.confirmed_at is not None
    assert yeu_cau.dispute_reason == ""


@pytest.mark.asyncio
async def test_khoi_luong_ngoai_khoang_thi_tranh_chap_kem_ly_do(api: AsyncClient, api_session: Session) -> None:
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    request_id = await _dua_toi_da_giao_don_vi(api, cleaner)

    response = await api.post(
        f"/api/v1/pickups/{request_id}/xac-nhan-khoi-luong",
        json={"weight_confirmed_kg": 30.0},  # xa ngoài khoảng 4,8–11,2 kg
        headers=_auth(cleaner),
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "tranh_chap"
    # Bốn trường của package 7 phải hiện trên serializer — kèm lý do tranh chấp.
    assert data["weight_confirmed_kg"] == 30.0
    assert data["confirmed_by"] is not None
    assert data["confirmed_at"] is not None
    assert data["dispute_reason"], "Phải ghi lý do tranh chấp bằng tiếng Việt"

    yeu_cau = api_session.get(PickupRequest, request_id)
    assert yeu_cau.weight_confirmed_kg == 30.0
    assert yeu_cau.confirmed_by is not None
    assert yeu_cau.confirmed_at is not None
    assert yeu_cau.dispute_reason, "Phải ghi lý do tranh chấp bằng tiếng Việt"
    assert "lệch ngoài khoảng" in yeu_cau.dispute_reason


@pytest.mark.asyncio
async def test_khoi_luong_trong_dung_sai_vẫn_hoan_tat(api: AsyncClient) -> None:
    """Lệch nhẹ ngoài khoảng nhưng dưới dung sai 20% vẫn chốt hoàn tất."""
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    request_id = await _dua_toi_da_giao_don_vi(api, cleaner)

    response = await api.post(
        f"/api/v1/pickups/{request_id}/xac-nhan-khoi-luong",
        json={"weight_confirmed_kg": 13.0},  # cận trên 11,2 × 1,2 = 13,44 — vẫn trong dung sai
        headers=_auth(cleaner),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "hoan_tat"


@pytest.mark.asyncio
async def test_khong_xac_nhan_duoc_tu_trang_thai_khac_da_giao_don_vi(api: AsyncClient) -> None:
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    resident = await _dang_nhap(api, "resident@demo.vn")
    yeu_cau = await _tao_yeu_cau(api, resident)  # đang ở cho_nhan

    response = await api.post(
        f"/api/v1/pickups/{yeu_cau['id']}/xac-nhan-khoi-luong",
        json={"weight_confirmed_kg": 8.0},
        headers=_auth(cleaner),
    )

    assert response.status_code == 400
    assert "giao đơn vị thu gom" in response.json()["error"]["message_vi"]


# --- Mở khoá tạo yêu cầu cho cư dân không căn hộ (gói P59) --------------------


@pytest.mark.asyncio
async def test_cu_dan_co_can_ho_tao_duoc_va_unit_id_dung(api: AsyncClient, api_session: Session) -> None:
    """(a) Cư dân có căn hộ tạo được như cũ, unit_id đúng căn hộ của họ."""
    resident = await _dang_nhap(api, "resident@demo.vn")
    cu_dan = api_session.scalar(select(User).where(User.email == "resident@demo.vn"))
    assert cu_dan is not None and cu_dan.unit_id is not None

    yeu_cau = await _tao_yeu_cau(api, resident)

    ban_ghi = api_session.get(PickupRequest, yeu_cau["id"])
    assert ban_ghi is not None
    assert ban_ghi.unit_id == cu_dan.unit_id, "Cư dân có căn hộ thì unit_id phải đúng căn hộ của họ"


@pytest.mark.asyncio
async def test_cu_dan_khong_can_ho_co_dia_chi_tao_duoc_qua_api(
    api: AsyncClient, api_session: Session
) -> None:
    """(b) Cư dân không căn hộ nhưng có users.address → tạo được qua API.

    ``address`` lấy từ nơi ở của chính người đó (tầng dịch vụ ``noi_o_cua``),
    ``unit_id`` vẫn None.
    """
    _them_cu_dan_khong_can_ho(api_session, dia_chi="123 Phố Mô Phỏng, Hà Nội", lat=21.01, lng=105.8)
    api_session.commit()
    token = await _dang_nhap(api, "dan_pho@demo.vn")

    response = await api.post("/api/v1/pickups", json=_payload_yeu_cau(), headers=_auth(token))

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["unit"] == "", "Hộ dân lẻ không có mã căn hộ"
    assert data["address"] == "123 Phố Mô Phỏng, Hà Nội", "Điểm lấy hàng lấy từ nơi ở của chính người đó"
    ban_ghi = api_session.get(PickupRequest, data["id"])
    assert ban_ghi is not None
    assert ban_ghi.unit_id is None
    assert ban_ghi.address == "123 Phố Mô Phỏng, Hà Nội"


@pytest.mark.asyncio
async def test_cu_dan_khong_can_ho_khong_dia_chi_tra_loi_400(api: AsyncClient, api_session: Session) -> None:
    """(c) Không căn hộ, không địa chỉ nào → lỗi HTTP 400 mã PU-400, KHÔNG phải 500."""
    _them_cu_dan_khong_can_ho(api_session, dia_chi="")
    api_session.commit()
    token = await _dang_nhap(api, "dan_pho@demo.vn")

    response = await api.post("/api/v1/pickups", json=_payload_yeu_cau(), headers=_auth(token))

    assert response.status_code == 400, response.text
    loi = response.json()["error"]
    assert loi["code"] == "PU-400", "Phải giữ nguyên mã lỗi hiện có của tầng dịch vụ"


@pytest.mark.asyncio
async def test_gui_dia_chi_rieng_khac_noi_o_duoc_ton_trong(api: AsyncClient, api_session: Session) -> None:
    """(d) Gửi address riêng khác nơi ở → yêu cầu nhận đúng address đó.

    Cư dân có căn hộ vẫn giữ unit_id để BQL toà duyệt được — tầng dịch vụ đã quy.
    """
    resident = await _dang_nhap(api, "resident@demo.vn")

    response = await api.post(
        "/api/v1/pickups",
        json=_payload_yeu_cau(address="999 Địa chỉ riêng, Hà Nội"),
        headers=_auth(resident),
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["address"] == "999 Địa chỉ riêng, Hà Nội"
    ban_ghi = api_session.get(PickupRequest, data["id"])
    assert ban_ghi is not None
    assert ban_ghi.address == "999 Địa chỉ riêng, Hà Nội"
    assert ban_ghi.unit_id is not None, "Cư dân có căn hộ: gửi address riêng vẫn giữ unit_id"


def test_pickup_dict_yeu_cau_unit_id_none_khong_sa_warning(api_session: Session) -> None:
    """(e) pickup_dict của yêu cầu unit_id=None → không nổ, không SAWarning, có address.

    Trước gói P59, ``session.get(Unit, None)`` trả None kèm SAWarning — may mà
    dòng sau đã có ``if unit`` nên không nổ. Giờ phải chặn tường minh.
    """
    cu_dan = _them_cu_dan_khong_can_ho(api_session, dia_chi="123 Phố Mô Phỏng, Hà Nội")
    api_session.commit()
    yeu_cau = PickupRequest(
        resident_id=cu_dan.id,
        unit_id=None,
        address="123 Phố Mô Phỏng, Hà Nội",
        items=[{"name": "Bàn gỗ", "category_code": "bulky", "qty": 1}],
        weight_min_kg=10.0,
        weight_max_kg=30.0,
        est_weight_kg=20.0,
        status="cho_nhan",
    )
    api_session.add(yeu_cau)
    api_session.commit()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data = pickup_dict(api_session, yeu_cau)

    sa_warning = [w for w in caught if issubclass(w.category, SAWarning)]
    assert sa_warning == [], [str(w.message) for w in sa_warning]
    assert data["address"] == "123 Phố Mô Phỏng, Hà Nội"
    assert data["unit"] == ""
