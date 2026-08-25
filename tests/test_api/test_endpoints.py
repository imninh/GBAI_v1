"""Test API đầu-cuối: đăng nhập, phân quyền, phân loại, HITL #1 và #3.

Không test nào gọi API model thật — toàn bộ đi qua :class:`FakeVisionClient`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.db.models import Base
from src.main import app
from src.services import classifier
from src.services.pickup_lifecycle import CHO_DUYET, CHO_NHAN
from tests.conftest import FakeVisionClient, make_result

MAT_KHAU = "demo1234"


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """CSDL trong bộ nhớ đã seed dữ liệu nền, gắn vào dependency của app."""
    from scripts.seed import seed_buildings, seed_categories, seed_knowledge, seed_schedules, seed_units, seed_users

    # StaticPool là bắt buộc: FastAPI chạy endpoint đồng bộ ở threadpool, mà
    # SQLite in-memory mặc định cấp cho mỗi thread một CSDL rỗng riêng.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
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
    # Node advise không gọi model thật trong test.
    from src.services.vision import VisionUnavailableError

    monkeypatch.setattr(
        "src.services.vision.get_vision_client",
        lambda tier="t1": (_ for _ in ()).throw(VisionUnavailableError("test khong goi model")),
    )
    monkeypatch.setattr(classifier, "classify_image_local", lambda *a, **k: None)

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


# --- Đăng nhập và phân quyền --------------------------------------------


@pytest.mark.asyncio
async def test_health_khong_can_dang_nhap(api: AsyncClient) -> None:
    response = await api.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_root_khong_tra_dia_chi_frontend_cung(api: AsyncClient) -> None:
    """Trang gốc không được trỏ tới localhost — địa chỉ web phụ thuộc hạ tầng deploy."""
    response = await api.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert "frontend" not in payload
    assert "localhost:3000" not in str(payload)


@pytest.mark.asyncio
async def test_dang_nhap_ba_vai_tro_demo(api: AsyncClient) -> None:
    for email, role in (
        ("resident@demo.vn", "resident"),
        ("cleaner@demo.vn", "cleaner"),
        ("manager@demo.vn", "manager"),
    ):
        response = await api.post("/api/v1/auth/login", json={"email": email, "password": MAT_KHAU})
        assert response.status_code == 200
        assert response.json()["user"]["role"] == role


@pytest.mark.asyncio
async def test_sai_mat_khau_tra_ve_khuon_loi_tieng_viet(api: AsyncClient) -> None:
    response = await api.post("/api/v1/auth/login", json={"email": "resident@demo.vn", "password": "sai"})

    assert response.status_code == 401
    loi = response.json()["error"]
    assert loi["code"] == "AUTH-401"
    assert "không đúng" in loi["message_vi"]


@pytest.mark.asyncio
async def test_khong_co_token_thi_bi_chan(api: AsyncClient) -> None:
    response = await api.get("/api/v1/pickups")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH-401"


@pytest.mark.asyncio
async def test_cu_dan_khong_vao_duoc_trang_van_hanh(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.get("/api/v1/ops/metrics", headers=_auth(token))

    assert response.status_code == 403
    assert "ban quản lý" in response.json()["error"]["message_vi"]


@pytest.mark.asyncio
async def test_ma_tran_quyen_tra_ve_ca_quyen_khong_co_kem_ly_do(api: AsyncClient) -> None:
    """UI hiện mờ kèm tooltip, không ẩn hẳn — nên API phải trả cả phần bị cấm."""
    token = await _dang_nhap(api, "cleaner@demo.vn")

    quyen = (await api.get("/api/v1/auth/me", headers=_auth(token))).json()["permissions"]

    assert quyen["verify_label"]["allowed"] is True
    assert quyen["review_route"]["allowed"] is False
    assert quyen["review_route"]["reason"]


# --- Phân loại -----------------------------------------------------------


@pytest.mark.asyncio
async def test_phan_loai_bang_chu_tra_du_thong_tin_cho_man_ket_qua(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeVisionClient(results=[make_result(confidence=0.91)])
    monkeypatch.setattr(classifier, "get_vision_client", lambda tier="t1": fake)
    monkeypatch.setattr(classifier, "get_tier_model", lambda tier="t1": tier)
    monkeypatch.setattr(classifier, "get_tier_provider", lambda tier="t1": "fake")
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.post(
        "/api/v1/classify/text", json={"text_query": "hộp sữa giấy tráng nhôm"}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["refused"] is False
    assert data["category"]["code"] == "recyclable_paper"
    assert data["confidence_level"] == "chac_chan"
    assert data["run_id"] is not None, "Phải có run_id để mở được màn Agent Run"


@pytest.mark.asyncio
async def test_chan_cung_tra_ve_huong_dan_chuyen_nguoi(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.post(
        "/api/v1/classify/text", json={"text_query": "mình có bình gas mini hết"}, headers=_auth(token)
    )

    data = response.json()
    assert data["refused"] is True
    assert data["hard_block"]["code"] == "binh_gas"
    assert "ban quản lý" in data["refusal_headline_vi"]
    assert data["advice"] == "", "Từ chối thì không được kèm hướng dẫn xử lý"


@pytest.mark.asyncio
async def test_ca_bi_tu_choi_roi_vao_hang_doi_xac_nhan_nhan(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    await api.post("/api/v1/classify/text", json={"text_query": "kim tiêm cũ"}, headers=_auth(resident))

    manager = await _dang_nhap(api, "manager@demo.vn")
    hang_doi = (await api.get("/api/v1/verify-queue", headers=_auth(manager))).json()

    assert hang_doi["total"] == 1
    assert hang_doi["hard_cases"], "Khối 'Ca khó' phải được ghim trên đầu hàng đợi"


@pytest.mark.asyncio
async def test_xac_nhan_nhan_ghi_lai_nguoi_duyet(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    tao = (
        await api.post("/api/v1/classify/text", json={"text_query": "kim tiêm cũ"}, headers=_auth(resident))
    ).json()

    manager = await _dang_nhap(api, "manager@demo.vn")
    response = await api.post(
        f"/api/v1/classifications/{tao['classification_id']}/verify",
        json={"category_code": "hazardous", "reply_text": "Mang tới điểm thu gom tầng hầm B1 giúp mình."},
        headers=_auth(manager),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["human_label"]["code"] == "hazardous"
    assert data["verified_by"] is not None


# --- Danh mục và lịch ----------------------------------------------------


@pytest.mark.asyncio
async def test_danh_muc_tra_ve_mau_thung_va_nguong_rieng(api: AsyncClient) -> None:
    danh_muc = (await api.get("/api/v1/categories")).json()["items"]

    nguy_hai = next(c for c in danh_muc if c["code"] == "hazardous")
    assert nguy_hai["min_confidence"] >= 0.80
    assert nguy_hai["safety_warning"], "Cảnh báo an toàn phải lấy được từ danh mục"
    assert nguy_hai["bin_color"], "UI đọc bin_color từ API chứ không hardcode"


@pytest.mark.asyncio
async def test_lich_thu_gom_cua_toa(api: AsyncClient, api_session: Session) -> None:
    from sqlalchemy import select

    from src.db.models import Building

    building = api_session.scalar(select(Building).where(Building.code == "S1"))

    response = await api.get(f"/api/v1/buildings/{building.id}/schedule")

    assert response.status_code == 200
    data = response.json()
    assert data["items"]
    assert data["items"][0]["weekdays_vi"], "Phải có nhãn thứ bằng tiếng Việt cho UI"


@pytest.mark.asyncio
async def test_thu_truy_hoi_la_cong_cu_debug_cua_bql(api: AsyncClient) -> None:
    manager = await _dang_nhap(api, "manager@demo.vn")

    response = await api.post(
        "/api/v1/knowledge/test-retrieval",
        json={"query": "pin cũ bỏ ở đâu", "top_k": 3},
        headers=_auth(manager),
    )

    assert response.status_code == 200
    assert response.json()["items"], "Phải truy hồi được đoạn về pin"


# --- HITL #1: thu gom ----------------------------------------------------


async def _tao_yeu_cau(api: AsyncClient, token: str, weight: float, ngay: date) -> dict:
    response = await api.post(
        "/api/v1/pickups",
        json={
            "items": [{"name": "Tủ gỗ cũ", "category_code": "bulky", "qty": 1}],
            "est_weight_kg": weight,
            "preferred_date": ngay.isoformat(),
            "preferred_window": "08:00-10:00",
            "confirmed_no_hazardous": True,
        },
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_khong_tick_xac_nhan_thi_khong_gui_duoc(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.post(
        "/api/v1/pickups",
        json={"items": [{"name": "Tủ gỗ", "category_code": "bulky"}], "est_weight_kg": 10, "confirmed_no_hazardous": False},
        headers=_auth(token),
    )

    assert response.status_code == 400
    assert "rác nguy hại" in response.json()["error"]["message_vi"]


@pytest.mark.asyncio
async def test_vuot_nguong_thi_vao_hang_doi_va_noi_ro_ly_do(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")

    data = await _tao_yeu_cau(api, token, weight=48, ngay=date.today() + timedelta(days=3))

    assert data["status"] == CHO_DUYET
    assert data["requires_hitl"] is True
    assert data["threshold_hit"][0]["threshold"] == 30.0
    assert data["timeline"], "Timeline phải có mốc ngay từ lúc gửi"


@pytest.mark.asyncio
async def test_cu_dan_khong_duyet_duoc_yeu_cau(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    data = await _tao_yeu_cau(api, token, weight=48, ngay=date.today() + timedelta(days=3))

    response = await api.post(
        f"/api/v1/pickups/{data['id']}/review", json={"action": "approve"}, headers=_auth(token)
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_bql_duyet_va_thay_boi_canh_quyet_dinh(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    data = await _tao_yeu_cau(api, resident, weight=48, ngay=date.today() + timedelta(days=3))
    manager = await _dang_nhap(api, "manager@demo.vn")

    chi_tiet = (await api.get(f"/api/v1/pickups/{data['id']}", headers=_auth(manager))).json()
    assert "resident_history" in chi_tiet
    assert "agent_suggestion" in chi_tiet

    response = await api.post(
        f"/api/v1/pickups/{data['id']}/review", json={"action": "approve"}, headers=_auth(manager)
    )
    assert response.status_code == 200
    assert response.json()["status"] == CHO_NHAN


@pytest.mark.asyncio
async def test_tu_choi_bang_ly_do_tu_do_bi_chan(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    data = await _tao_yeu_cau(api, resident, weight=48, ngay=date.today() + timedelta(days=3))
    manager = await _dang_nhap(api, "manager@demo.vn")

    response = await api.post(
        f"/api/v1/pickups/{data['id']}/review",
        json={"action": "reject", "reason": "tôi không thích"},
        headers=_auth(manager),
    )

    assert response.status_code == 400
    assert "danh sách cố định" in response.json()["error"]["message_vi"]


# --- HITL #3: tuyến ------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_de_xuat_tuyen_o_trang_thai_cho_duyet(api: AsyncClient) -> None:
    ngay = date.today() + timedelta(days=3)
    resident = await _dang_nhap(api, "resident@demo.vn")
    manager = await _dang_nhap(api, "manager@demo.vn")

    a = await _tao_yeu_cau(api, resident, weight=10, ngay=ngay)
    b = await _tao_yeu_cau(api, resident, weight=12, ngay=ngay)
    assert {a["status"], b["status"]} == {CHO_NHAN}

    response = await api.post(
        "/api/v1/routes/propose",
        json={"service_date": ngay.isoformat(), "window": "08:00-10:00"},
        headers=_auth(manager),
    )

    assert response.status_code == 200, response.text
    tuyen = response.json()
    assert tuyen["status"] == "proposed", "Agent không được tự chốt lịch của người"
    assert tuyen["reasoning"]["criteria"], "Phải giải thích vì sao gộp thế này"
    assert tuyen["reasoning"]["saved_km"] >= 0


@pytest.mark.asyncio
async def test_duyet_tuyen_thi_bao_da_thong_bao_cho_cu_dan(api: AsyncClient) -> None:
    ngay = date.today() + timedelta(days=3)
    resident = await _dang_nhap(api, "resident@demo.vn")
    manager = await _dang_nhap(api, "manager@demo.vn")
    await _tao_yeu_cau(api, resident, weight=10, ngay=ngay)
    await _tao_yeu_cau(api, resident, weight=12, ngay=ngay)
    tuyen = (
        await api.post(
            "/api/v1/routes/propose",
            json={"service_date": ngay.isoformat(), "window": "08:00-10:00"},
            headers=_auth(manager),
        )
    ).json()

    # Gán kíp trước khi duyệt — tuyến đã duyệt bắt buộc phải có đội, kẻo
    # cleaner không bao giờ nhìn thấy nó (E2E §8). Kíp phải đúng 2 người.
    token_cleaner_1 = await _dang_nhap(api, "cleaner@demo.vn")
    token_cleaner_2 = await _dang_nhap(api, "cleaner2@demo.vn")
    uid_1 = (
        await api.get("/api/v1/auth/me", headers=_auth(token_cleaner_1))
    ).json()["user"]["id"]
    uid_2 = (
        await api.get("/api/v1/auth/me", headers=_auth(token_cleaner_2))
    ).json()["user"]["id"]
    response = await api.put(
        f"/api/v1/routes/{tuyen['id']}/kip",
        json={"user_ids": [uid_1, uid_2]},
        headers=_auth(manager),
    )
    assert response.status_code == 200

    response = await api.post(
        f"/api/v1/routes/{tuyen['id']}/review", json={"action": "approve"}, headers=_auth(manager)
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert "Đã thông báo" in data["message_vi"]

    thong_bao = (await api.get("/api/v1/notifications", headers=_auth(resident))).json()
    assert thong_bao["unread"] >= 1


# --- Vận hành ------------------------------------------------------------


@pytest.mark.asyncio
async def test_trang_van_hanh_luon_kem_khoi_gioi_han_da_biet(api: AsyncClient) -> None:
    manager = await _dang_nhap(api, "manager@demo.vn")

    data = (await api.get("/api/v1/ops/metrics", headers=_auth(manager))).json()

    assert data["known_limitations"], "Khối 'Giới hạn đã biết' là text cứng, luôn phải có"
    assert "túi nilon đục" in " ".join(data["known_limitations"])
    assert "budget" in data["cost"]


@pytest.mark.asyncio
async def test_trang_status_khong_lo_api_key(api: AsyncClient) -> None:
    data = (await api.get("/api/v1/status")).json()

    assert "has_api_key" in data["model"]
    assert "key" not in str(data["model"]).lower().replace("has_api_key", "")


@pytest.mark.asyncio
async def test_chi_so_an_toan_nam_o_trang_chat_luong_ai(api: AsyncClient) -> None:
    manager = await _dang_nhap(api, "manager@demo.vn")

    data = (await api.get("/api/v1/eval/summary", headers=_auth(manager))).json()

    assert data["safety"]["target"] == 0
    assert "nguy hại" in data["safety"]["label_vi"]


@pytest.mark.asyncio
async def test_loc_pickup_theo_trang_thai_khong_hop_le_tra_400_khong_phai_500(
    api: AsyncClient,
) -> None:
    """Giá trị status từ client có thể là rác — phải về khung lỗi 400, không được 500."""
    manager = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/pickups?status=khong_co_trang_thai_nay", headers=_auth(manager))

    assert response.status_code == 400, response.text
    loi = response.json()["error"]
    assert loi["code"] == "PU-400"
    assert "khong_co_trang_thai_nay" in loi["message_vi"]
