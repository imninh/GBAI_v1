"""Test API thùng thu gom thông minh — phía đọc cho bản đồ vận hành."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base, Bin
from src.main import app

MAT_KHAU = "demo1234"
KHOI_DEVICE = "khoa-demo-thiet-bi"

_so_thung = itertools.count(1)


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    """Cấu hình đọc qua ``lru_cache`` nên phải xoá cache quanh mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


def _dat_khoa_thiet_bi(monkeypatch: pytest.MonkeyPatch, gia_tri: str) -> None:
    """Đặt BIN_DEVICE_KEY rồi xoá cache — Settings không đọc lại nếu không xoá."""
    monkeypatch.setenv("BIN_DEVICE_KEY", gia_tri)
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


# --- Danh sách và chi tiết ------------------------------------------------


@pytest.mark.asyncio
async def test_lay_danh_sach_thung_kem_trang_thai(api: AsyncClient, api_session: Session) -> None:
    _tao_thung(api_session, code="BIN-DAY", fill_percent=85.0)
    _tao_thung(api_session, code="BIN-NHE", fill_percent=10.0)
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bins", headers=_auth(token))

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 2
    theo_ma = {i["code"]: i for i in items}
    assert theo_ma["BIN-DAY"]["status"] == "can_gom"
    assert theo_ma["BIN-NHE"]["status"] == "binh_thuong"


@pytest.mark.asyncio
async def test_loc_chi_thung_can_gom(api: AsyncClient, api_session: Session) -> None:
    _tao_thung(api_session, code="BIN-A", fill_percent=85.0)
    _tao_thung(api_session, code="BIN-B", fill_percent=92.0)
    _tao_thung(api_session, code="BIN-C", fill_percent=10.0)
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bins?only_needs_collection=true", headers=_auth(token))

    assert response.status_code == 200, response.text
    codes = [i["code"] for i in response.json()["items"]]
    assert codes == ["BIN-B", "BIN-A"], "Chỉ thùng cần gom, xếp theo mức đầy giảm dần"


@pytest.mark.asyncio
async def test_chi_tiet_mot_thung(api: AsyncClient, api_session: Session) -> None:
    _tao_thung(api_session, code="BIN-CHI-TIET", fill_percent=88.0)
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bins/BIN-CHI-TIET", headers=_auth(token))

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["code"] == "BIN-CHI-TIET"
    assert data["status"] == "can_gom"


@pytest.mark.asyncio
async def test_unknown_code_tra_ve_404(api: AsyncClient, api_session: Session) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bins/BIN-KHONG-CO", headers=_auth(token))

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NF-404"
    assert "thùng" in error["message_vi"]


# --- Thống kê -------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_bon_chi_so_dung(api: AsyncClient, api_session: Session) -> None:
    _tao_thung(api_session, code="BIN-CANGOM", fill_percent=85.0)
    _tao_thung(api_session, code="BIN-OFF", last_seen_at=datetime.now(UTC) - timedelta(days=3))
    _tao_thung(api_session, code="BIN-PIN", battery_percent=5.0)
    _tao_thung(api_session, code="BIN-THONG", fill_percent=10.0)
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bins/stats", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json() == {"tong": 4, "can_gom": 1, "mat_ket_noi": 1, "het_pin": 1}


@pytest.mark.asyncio
async def test_stats_khong_bi_nuot_boi_route_code(api: AsyncClient, api_session: Session) -> None:
    """Bẫy thứ tự route: "stats" phải tới endpoint stats, không bị đọc thành mã thùng."""
    _tao_thung(api_session, code="stats")
    api_session.commit()
    token = await _dang_nhap(api, "cleaner@demo.vn")

    response = await api.get("/api/v1/bins/stats", headers=_auth(token))

    assert response.status_code == 200, "Có một thùng tên 'stats' nhưng request này phải về trang thống kê"
    data = response.json()
    assert "error" not in data
    assert "tong" in data and "can_gom" in data


# --- Phân quyền -----------------------------------------------------------


@pytest.mark.asyncio
async def test_cu_dan_bi_chan_tren_moi_endpoint(api: AsyncClient, api_session: Session) -> None:
    _tao_thung(api_session)
    api_session.commit()
    token = await _dang_nhap(api, "resident@demo.vn")

    for path in ("/api/v1/bins", "/api/v1/bins/stats", "/api/v1/bins/BIN-001"):
        response = await api.get(path, headers=_auth(token))
        assert response.status_code == 403, path
        error = response.json()["error"]
        assert error["code"] == "PERM-403"
        assert "thùng thu gom" in error["message_vi"], error


@pytest.mark.asyncio
async def test_cleaner_va_manager_duoc_cho(api: AsyncClient, api_session: Session) -> None:
    _tao_thung(api_session)
    api_session.commit()

    for email in ("cleaner@demo.vn", "manager@demo.vn"):
        token = await _dang_nhap(api, email)
        response = await api.get("/api/v1/bins", headers=_auth(token))
        assert response.status_code == 200, email


# --- Ghi nhận reading (ingest) -------------------------------------------


@pytest.mark.asyncio
async def test_post_reading_khoa_dung_cap_nhat_va_tra_trang_thai_moi(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trạng thái trong phản hồi phải tính từ reading vừa nhận, trong chính
    request này — chưa hề đọc lại hàng từ CSDL (ca mà phép chuẩn hoá aware/naive
    được viết ra cho)."""
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    _tao_thung(api_session, code="BIN-GOM", fill_percent=10.0)
    api_session.commit()

    response = await api.post(
        "/api/v1/bins/BIN-GOM/readings",
        json={"fill_percent": 90.0, "battery_percent": 80.0, "source": "device"},
        headers={"X-Device-Key": KHOI_DEVICE},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["fill_percent"] == 90.0
    assert data["battery_percent"] == 80.0
    assert data["status"] == "can_gom", "Trạng thái phải phản ánh reading vừa ghi"
    assert data["last_seen_at"], "Phải ghi mốc thời gian báo về"

    thung = api_session.scalar(select(Bin).where(Bin.code == "BIN-GOM"))
    assert thung.fill_percent == 90.0
    assert thung.battery_percent == 80.0
    assert thung.last_seen_at is not None


@pytest.mark.asyncio
async def test_post_reading_khoa_sai_bi_chan(api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    thung = _tao_thung(api_session)
    api_session.commit()

    response = await api.post(
        f"/api/v1/bins/{thung.code}/readings",
        json={"fill_percent": 50.0, "battery_percent": 50.0, "source": "device"},
        headers={"X-Device-Key": "khoa-sai"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "BIN-KEY-401"


@pytest.mark.asyncio
async def test_post_reading_thieu_header_khoa_bi_chan(api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    thung = _tao_thung(api_session)
    api_session.commit()

    response = await api.post(
        f"/api/v1/bins/{thung.code}/readings",
        json={"fill_percent": 50.0, "battery_percent": 50.0, "source": "device"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "BIN-KEY-401"


@pytest.mark.asyncio
async def test_post_reading_khoa_chua_cau_hinh_bi_chan(api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Khoá rỗng = fail closed, không bao giờ "mở cho tất cả"."""
    _dat_khoa_thiet_bi(monkeypatch, "")
    thung = _tao_thung(api_session)
    api_session.commit()

    response = await api.post(
        f"/api/v1/bins/{thung.code}/readings",
        json={"fill_percent": 50.0, "battery_percent": 50.0, "source": "device"},
        headers={"X-Device-Key": KHOI_DEVICE},
    )

    assert response.status_code == 503
    loi = response.json()["error"]
    assert loi["code"] == "BIN-KEY-503"
    assert "BIN_DEVICE_KEY" in loi["message_vi"], loi


@pytest.mark.asyncio
async def test_post_reading_ngoai_khoang_tra_400_khong_phai_500(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    thung = _tao_thung(api_session)
    api_session.commit()
    duong = f"/api/v1/bins/{thung.code}/readings"
    headers = {"X-Device-Key": KHOI_DEVICE}

    ra_cao = await api.post(
        duong, json={"fill_percent": 101.0, "battery_percent": 50.0, "source": "device"}, headers=headers
    )
    pin_can = await api.post(
        duong, json={"fill_percent": 50.0, "battery_percent": -5.0, "source": "device"}, headers=headers
    )

    for response in (ra_cao, pin_can):
        assert response.status_code == 400, response.text
        error = response.json()["error"]
        assert error["code"] == "BIN-400"
        assert "khoảng" in error["message_vi"], error


@pytest.mark.asyncio
async def test_post_reading_nguon_khong_hop_le_bi_chan(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    thung = _tao_thung(api_session)
    api_session.commit()

    response = await api.post(
        f"/api/v1/bins/{thung.code}/readings",
        json={"fill_percent": 50.0, "battery_percent": 50.0, "source": "manually"},
        headers={"X-Device-Key": KHOI_DEVICE},
    )

    assert response.status_code == 400
    loi = response.json()["error"]
    assert loi["code"] == "BIN-400"
    assert "device" in loi["message_vi"], loi


@pytest.mark.asyncio
async def test_post_reading_unknown_code_tra_ve_404(api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)

    response = await api.post(
        "/api/v1/bins/BIN-KHONG-CO/readings",
        json={"fill_percent": 50.0, "battery_percent": 50.0, "source": "device"},
        headers={"X-Device-Key": KHOI_DEVICE},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NF-404"


@pytest.mark.asyncio
async def test_post_reading_khong_can_jwt(api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Không gửi header Authorization, chỉ gửi khoá thiết bị — phải thành công."""
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    thung = _tao_thung(api_session)
    api_session.commit()

    response = await api.post(
        f"/api/v1/bins/{thung.code}/readings",
        json={"fill_percent": 40.0, "battery_percent": 60.0, "source": "device"},
        headers={"X-Device-Key": KHOI_DEVICE},
    )

    assert response.status_code == 200, response.text


# --- Toạ độ và lịch sử reading --------------------------------------------


@pytest.mark.asyncio
async def test_danh_sach_thung_co_toa_do_seed(api: AsyncClient, api_session: Session) -> None:
    """Bản đồ vận hành vẽ thùng cần biết thùng ở đâu — mọi thùng phải kèm lat/lng."""
    _tao_thung(api_session, code="BIN-DO-A", lat=21.01, lng=105.80)
    _tao_thung(api_session, code="BIN-DO-B", lat=21.02, lng=105.82)
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bins", headers=_auth(token))

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    theo_ma = {i["code"]: i for i in items}
    assert theo_ma["BIN-DO-A"]["lat"] == 21.01
    assert theo_ma["BIN-DO-A"]["lng"] == 105.80
    assert theo_ma["BIN-DO-B"]["lat"] == 21.02
    assert theo_ma["BIN-DO-B"]["lng"] == 105.82


@pytest.mark.asyncio
async def test_chi_tiet_thung_co_toa_do_va_lich_su(api: AsyncClient, api_session: Session) -> None:
    """Chi tiết thùng phải kèm toạ độ để vẽ một điểm trên bản đồ, và lịch sử reading."""
    _tao_thung(api_session, code="BIN-DO-CHI-TIET", lat=21.03, lng=105.83)
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bins/BIN-DO-CHI-TIET", headers=_auth(token))

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["lat"] == 21.03
    assert data["lng"] == 105.83
    assert data["readings"] == []


@pytest.mark.asyncio
async def test_lich_su_reading_moi_truoc_cu_va_gioi_han_so_luong(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lịch sử phải xếp mới trước cũ, và ``readings_limit`` kẹp số bản ghi trả về."""
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    _tao_thung(api_session, code="BIN-LICH-SU")
    api_session.commit()
    headers = {"X-Device-Key": KHOI_DEVICE}
    duong = "/api/v1/bins/BIN-LICH-SU/readings"

    for muc_rac in (10.0, 50.0, 90.0):
        response = await api.post(
            duong, json={"fill_percent": muc_rac, "battery_percent": 80.0, "source": "device"}, headers=headers
        )
        assert response.status_code == 200, response.text

    token = await _dang_nhap(api, "manager@demo.vn")
    response = await api.get("/api/v1/bins/BIN-LICH-SU?readings_limit=2", headers=_auth(token))

    assert response.status_code == 200, response.text
    readings = response.json()["readings"]
    assert len(readings) == 2
    assert readings[0]["fill_percent"] == 90.0, "Reading mới nhất phải đứng đầu"
    assert readings[1]["fill_percent"] == 50.0
    for reading in readings:
        assert "created_at" in reading
        assert "source" in reading
        assert "battery_percent" in reading


@pytest.mark.asyncio
async def test_post_reading_tra_toa_do_va_lng_khong_loi(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hồi quy EDIT 4: phản hồi của POST reading cũng qua ``_serialize_row`` —
    thiếu lat/lng ở đây là KeyError 500 thay vì 200."""
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    _tao_thung(api_session, code="BIN-DO-POST", lat=21.04, lng=105.84)
    api_session.commit()

    response = await api.post(
        "/api/v1/bins/BIN-DO-POST/readings",
        json={"fill_percent": 55.0, "battery_percent": 70.0, "source": "device"},
        headers={"X-Device-Key": KHOI_DEVICE},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["lat"] == 21.04
    assert data["lng"] == 105.84
