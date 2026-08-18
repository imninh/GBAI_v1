"""Test CP2 — `/iot/captures` nối vào bộ phân loại thật, ghi CSDL, trả `route`.

Gói P61: endpoint đi qua bộ phân loại 4 tầng (``classify_waste``), ghi
``Media`` (``uploader_id=None``) và ``Classification`` xuống CSDL, và phản hồi
mang hợp đồng CP2 (``route`` / ``item_id`` / ``review_required`` /
``model_version``) BÊN CẠNH mọi trường hợp đồng cũ — firmware đang dựa vào chúng.

Không test nào gọi model thật: ``classify_waste`` bị thay bằng kết quả giả.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import get_settings, reset_settings_cache
from src.db.models import Base, Classification, Media, WasteCategory
from src.main import app
from src.services import device_auth
from src.services.classifier_types import ClassifyOutcome

DEVICE_ID = "GBIN-001"
DEVICE_KEY = "test-key-123"

# Mọi trường hợp đồng CŨ — firmware đang dựa vào, không được bỏ trường nào.
_CAC_TRUONG_CU = {
    "status",
    "label",
    "confidence",
    "requires_review",
    "message",
    "capture_id",
    "phash",
    "image_bytes",
    "faces_blurred",
    "exif_stripped",
}


@pytest.fixture
def device_keys(monkeypatch):
    monkeypatch.setenv("IOT_DEVICE_KEYS", f"{DEVICE_ID}:{DEVICE_KEY}")
    get_settings.cache_clear()
    device_auth.reset_cache()
    yield DEVICE_KEY
    get_settings.cache_clear()
    device_auth.reset_cache()


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """CSDL trong bộ nhớ đã seed danh mục, gắn vào dependency của app."""
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


def make_jpeg(width: int = 800, height: int = 600) -> bytes:
    image = Image.new("RGB", (width, height), (120, 200, 90))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def upload_files(jpeg: bytes):
    return {"image": ("capture.jpg", jpeg, "image/jpeg")}


def upload_data(item_id: str = ""):
    data = {
        "device_id": DEVICE_ID,
        "bin_code": "BIN-001",
        "event_type": "waste_detected",
        "uptime_s": "120",
    }
    if item_id:
        data["item_id"] = item_id
    return data


def _nhom(api_session: Session, code: str) -> WasteCategory:
    return api_session.scalar(select(WasteCategory).where(WasteCategory.code == code))


def _chot_loai(api_session: Session, code: str = "recyclable_plastic", confidence: float = 0.94):
    def fake(session, image_bytes=None, image_phash=""):
        return ClassifyOutcome(category=_nhom(api_session, code), confidence=confidence, refused=False)

    return fake


# ─── Khoá sai / thiếu ảnh ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_khoa_sai_tra_401(api: AsyncClient, api_session: Session, device_keys, monkeypatch) -> None:
    with patch("src.api.iot.classify_waste", side_effect=_chot_loai(api_session)):
        response = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(),
            headers={"X-Device-Key": "sai-khoa"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_thieu_anh_tra_422(api: AsyncClient, api_session: Session, device_keys, monkeypatch) -> None:
    """Thiếu file ảnh → 422 ở tầng FastAPI (bắt buộc `File(...)`), giữ mã hiện có."""
    with patch("src.api.iot.classify_waste", side_effect=_chot_loai(api_session)):
        response = await api.post(
            "/api/v1/iot/captures",
            data=upload_data(),
            headers={"X-Device-Key": DEVICE_KEY},
        )
    assert response.status_code == 422


# ─── Ca thường ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ca_thuong_tra_route_va_ghi_csdl(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
) -> None:
    with patch("src.api.iot.classify_waste", side_effect=_chot_loai(api_session, "recyclable_plastic")):
        response = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-1"),
            headers={"X-Device-Key": DEVICE_KEY},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route"] == "plastic", "route phải theo bảng ánh xạ nhóm rác → ngăn"
    assert body["label"] == "recyclable_plastic"
    assert body["review_required"] is False
    assert body["requires_review"] is False
    assert body["item_id"] == "item-1"
    assert body["model_version"], "model_version phải lấy từ outcome"

    phan_loai = api_session.scalar(select(Classification).where(Classification.item_id == "item-1"))
    assert phan_loai is not None, "Phải có bản ghi Classification trong CSDL"
    assert phan_loai.predicted_category_id is not None
    assert phan_loai.refused is False
    assert phan_loai.asker_id is None, "Thiết bị không có tài khoản — asker_id phải None"
    assert phan_loai.text_query == "", "item_id phải nằm ở cột riêng, KHÔNG được nhét vào text_query"

    media = api_session.get(Media, phan_loai.media_id)
    assert media is not None, "Phải có bản ghi Media trong CSDL"
    assert media.uploader_id is None, "uploader_id phải None — thiết bị không có tài khoản"


@pytest.mark.asyncio
async def test_ca_thuong_route_khac_nhom_khac_ngan(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
) -> None:
    """Mỗi nhóm rác ánh xạ sang đúng ngăn — không gắn cứng một ngăn cho mọi ca."""
    for code, ngan in (("recyclable_metal", "metal"), ("recyclable_paper", "paper")):
        with patch("src.api.iot.classify_waste", side_effect=_chot_loai(api_session, code)):
            response = await api.post(
                "/api/v1/iot/captures",
                files=upload_files(make_jpeg()),
                data=upload_data(item_id=f"item-{code}"),
                headers={"X-Device-Key": DEVICE_KEY},
            )
        assert response.status_code == 200, response.text
        assert response.json()["route"] == ngan, f"{code} phải về ngăn {ngan}"


# ─── Ca bị từ chối ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ca_tu_choi_label_unknown_route_other(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
) -> None:
    def _tu_choi(session, image_bytes=None, image_phash=""):
        return ClassifyOutcome(category=None, confidence=0.0, refused=True, refusal_reason="duoi_nguong")

    with patch("src.api.iot.classify_waste", side_effect=_tu_choi):
        response = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-refused"),
            headers={"X-Device-Key": DEVICE_KEY},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["label"] == "UNKNOWN"
    assert body["route"] == "other"
    assert body["review_required"] is True
    assert body["status"] == "refused"

    phan_loai = api_session.scalar(select(Classification).where(Classification.item_id == "item-refused"))
    assert phan_loai is not None
    assert phan_loai.refused is True


# ─── Ca nguy hại ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ca_nguy_hai_luon_review_du_confidence_cao(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
) -> None:
    with patch("src.api.iot.classify_waste", side_effect=_chot_loai(api_session, "hazardous", confidence=0.99)):
        response = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-hazard"),
            headers={"X-Device-Key": DEVICE_KEY},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["review_required"] is True, "Nhóm nguy hại luôn cần duyệt dù confidence cao"
    assert body["route"] == "other", "Nhóm nguy hại không bao giờ vào ngăn thu hồi"
    assert body["label"] == "hazardous"


# ─── Idempotency ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gui_lai_cung_item_id_khong_tao_ban_ghi_thu_hai(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
) -> None:
    with patch("src.api.iot.classify_waste", side_effect=_chot_loai(api_session)):
        lan_dau = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-tron-lap"),
            headers={"X-Device-Key": DEVICE_KEY},
        )
        lan_hai = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-tron-lap"),
            headers={"X-Device-Key": DEVICE_KEY},
        )

    assert lan_dau.status_code == 200, lan_dau.text
    assert lan_hai.status_code == 200, lan_hai.text

    so_ban_ghi = api_session.scalar(
        select(func.count(Classification.id)).where(Classification.item_id == "item-tron-lap")
    )
    assert so_ban_ghi == 1, "Gửi lại cùng item_id không được tạo bản ghi thứ hai"
    khoi_text_query = api_session.scalar(
        select(func.count(Classification.id)).where(Classification.text_query.like("item_id:%"))
    )
    assert khoi_text_query == 0, "text_query không được còn tiền tố item_id:"

    dau = lan_dau.json()
    hai = lan_hai.json()
    for truong in ("status", "label", "confidence", "route", "review_required", "requires_review", "model_version"):
        assert dau[truong] == hai[truong], f"Phản hồi lặp phải giống lần đầu ở trường {truong}"


# ─── Mọi trường hợp đồng cũ còn nguyên ────────────────────────────────────────


@pytest.mark.asyncio
async def test_moi_truong_hop_dong_cu_con_nguyen(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
) -> None:
    """Hợp đồng cũ không được bỏ trường nào — firmware và api-contract dựa vào chúng."""
    with patch("src.api.iot.classify_waste", side_effect=_chot_loai(api_session)):
        response = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-cac-truong"),
            headers={"X-Device-Key": DEVICE_KEY},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _CAC_TRUONG_CU <= set(body), f"Thiếu trường hợp đồng cũ: {_CAC_TRUONG_CU - set(body)}"


# ─── Gắn kết quả vào phiên bỏ rác (P63) ───────────────────────────────────────


def _them_thung(api_session: Session, code: str = "BIN-001") -> None:
    from src.db.models import Bin

    thung = api_session.scalar(select(Bin).where(Bin.code == code))
    if thung is None:
        api_session.add(Bin(code=code, name=f"Thùng {code}"))
        api_session.flush()


@pytest.mark.asyncio
async def test_capture_co_phien_thi_cong_vat_va_tra_ma_phien(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
) -> None:
    """Có phiên đang mở của thùng → so_vat tăng, phản hồi có `ma_phien`."""
    from src.db.models import User
    from src.services import phien_thung

    _them_thung(api_session, "BIN-001")
    nguoi = User(email="chu-phien@demo.vn", full_name="Chủ phiên", role="resident", password_hash="x")
    api_session.add(nguoi)
    api_session.flush()
    phien = phien_thung.mo_phien(api_session, nguoi, "BIN-001")
    api_session.commit()

    with patch("src.api.iot.classify_waste", side_effect=_chot_loai(api_session)):
        response = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-voi-phien"),
            headers={"X-Device-Key": DEVICE_KEY},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ma_phien"] == phien.ma_phien, "Phản hồi phải có ma_phien của phiên đang mở"
    assert body["so_vat"] == 1

    api_session.refresh(phien)
    assert phien.so_vat == 1, "Vật được chấp nhận phải cộng vào phiên"


@pytest.mark.asyncio
async def test_capture_khong_co_phien_van_200_co_route(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
) -> None:
    """Không có phiên KHÔNG phải là lỗi — vẫn phân loại, vẫn trả route, không lỗi."""
    with patch("src.api.iot.classify_waste", side_effect=_chot_loai(api_session)):
        response = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-khong-phien"),
            headers={"X-Device-Key": DEVICE_KEY},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["route"] == "plastic"
    assert body["label"] == "recyclable_plastic"
    assert "ma_phien" not in body, "Không có phiên thì không thêm ma_phien"


@pytest.mark.asyncio
async def test_capture_vat_tu_choi_khong_cong_vao_phien(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
) -> None:
    """Vật bị từ chối → so_vat KHÔNG tăng, dù có phiên đang mở."""
    from src.db.models import User
    from src.services import phien_thung

    _them_thung(api_session, "BIN-001")
    nguoi = User(email="chu-phien-tu-choi@demo.vn", full_name="Chủ phiên", role="resident", password_hash="x")
    api_session.add(nguoi)
    api_session.flush()
    phien = phien_thung.mo_phien(api_session, nguoi, "BIN-001")
    api_session.commit()

    def _tu_choi(session, image_bytes=None, image_phash=""):
        return ClassifyOutcome(category=None, confidence=0.0, refused=True, refusal_reason="duoi_nguong")

    with patch("src.api.iot.classify_waste", side_effect=_tu_choi):
        response = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-tu-choi-phien"),
            headers={"X-Device-Key": DEVICE_KEY},
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "refused"
    api_session.refresh(phien)
    assert phien.so_vat == 0, "Vật bị từ chối không được cộng vào phiên"


@pytest.mark.asyncio
async def test_capture_nguy_hai_khong_cong_vao_phien(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
) -> None:
    """Ca nguy hại cần người duyệt → so_vat KHÔNG tăng."""
    from src.db.models import User
    from src.services import phien_thung

    _them_thung(api_session, "BIN-001")
    nguoi = User(email="chu-phien-nguy@demo.vn", full_name="Chủ phiên", role="resident", password_hash="x")
    api_session.add(nguoi)
    api_session.flush()
    phien = phien_thung.mo_phien(api_session, nguoi, "BIN-001")
    api_session.commit()

    with patch("src.api.iot.classify_waste", side_effect=_chot_loai(api_session, "hazardous", confidence=0.99)):
        response = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-nguy-hai-phien"),
            headers={"X-Device-Key": DEVICE_KEY},
        )

    assert response.status_code == 200, response.text
    assert response.json()["review_required"] is True
    api_session.refresh(phien)
    assert phien.so_vat == 0, "Ca nguy hại không được tính điểm"


@pytest.mark.asyncio
async def test_gui_lai_cung_item_id_khong_cong_hai_lan(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
) -> None:
    """Gửi lại cùng item_id → không tạo Classification thứ hai VÀ so_vat không tăng hai lần."""
    from src.db.models import User
    from src.services import phien_thung

    _them_thung(api_session, "BIN-001")
    nguoi = User(email="chu-phien-tron@demo.vn", full_name="Chủ phiên", role="resident", password_hash="x")
    api_session.add(nguoi)
    api_session.flush()
    phien = phien_thung.mo_phien(api_session, nguoi, "BIN-001")
    api_session.commit()

    with patch("src.api.iot.classify_waste", side_effect=_chot_loai(api_session)):
        lan_dau = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-tron-phien"),
            headers={"X-Device-Key": DEVICE_KEY},
        )
        lan_hai = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(item_id="item-tron-phien"),
            headers={"X-Device-Key": DEVICE_KEY},
        )

    assert lan_dau.status_code == 200 and lan_hai.status_code == 200
    so_ban_ghi = api_session.scalar(
        select(func.count(Classification.id)).where(Classification.item_id == "item-tron-phien")
    )
    assert so_ban_ghi == 1, "Gửi lại cùng item_id không được tạo bản ghi thứ hai"
    api_session.refresh(phien)
    assert phien.so_vat == 1, "so_vat không được tăng hai lần vì lần lặp"
