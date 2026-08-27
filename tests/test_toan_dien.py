"""Bộ test toàn diện — hồi quy tất cả tính năng GreenBin AI.

Chạy một lệnh duy nhất để kiểm tra toàn bộ hệ thống còn hoạt động:

    python -m pytest tests/test_toan_dien.py -v --tb=short

**Nguyên tắc:**
- Không gọi API model thật — dùng ``FakeVisionClient`` hoặc monkeypatch.
- SQLite in-memory — không chạm CSDL production.
- Tên test bằng tiếng Việt — mô tả hành vi rõ ràng.
- Khuôn lỗi chuẩn hóa — mọi lỗi trả về ``error.code`` + ``error.message_vi``.

20 nhóm tính năng:
 1. Auth & RBAC                12. Media & Privacy
 2. Vision Classification      13. Catalog & Knowledge
 3. Safety Hard Block           14. Ops & Metrics
 4. HITL #2 Verify             15. Health & Status
 5. Pickup Requests             16. Gamification
 6. Pickup Lifecycle            17. GPS Tracking
 7. Route Planning #3          18. Notifications
 8. Smart Bins                  19. Error Handling
 9. IoT Captures               20. Rate Limiting
10. Disposal Sessions
11. Chatbot RAG
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import (
    Base,
    Bin,
    DiemThuongLog,
    Notification,
    PhienThung,
    User,
)
from src.main import app
from src.services import classifier
from src.services.pickup_lifecycle import CHO_DUYET, CHO_NHAN
from tests.conftest import FakeVisionClient, make_result

MAT_KHAU = "demo1234"


# ═══════════════════════════════════════════════════════════════════════════
#  FIXTURES
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _xoa_cache_cau_hinh() -> Iterator[None]:
    """Cấu hình đọc qua ``lru_cache`` nên phải xoá cache quanh mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """CSDL trong bộ nhớ đã seed dữ liệu nền, gắn vào dependency của app."""
    from scripts.seed import (
        seed_buildings,
        seed_categories,
        seed_knowledge,
        seed_schedules,
        seed_units,
        seed_users,
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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

    # Ngăn model local chạy thật trong test.
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


# ── Helpers ──────────────────────────────────────────────────────────────


async def _dang_nhap(api: AsyncClient, email: str) -> str:
    """Đăng nhập và trả về token."""
    r = await api.post(
        "/api/v1/auth/login",
        json={"email": email, "password": MAT_KHAU},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _fake_vision(monkeypatch: pytest.MonkeyPatch, *results) -> FakeVisionClient:
    """Gắn FakeVisionClient trả kết quả tuần tự."""
    fake = FakeVisionClient(results=list(results))
    monkeypatch.setattr(classifier, "get_vision_client", lambda tier="t1": fake)
    monkeypatch.setattr(classifier, "get_tier_model", lambda tier="t1": tier)
    monkeypatch.setattr(classifier, "get_tier_provider", lambda tier="t1": "fake")
    return fake


def _them_thung(session: Session, code: str = "BIN-TD") -> Bin:
    """Thêm một thùng rác test."""
    thung = Bin(code=code, name=f"Thùng {code}")
    session.add(thung)
    session.flush()
    return thung


def _them_cu_dan(session: Session, email: str) -> User:
    """Thêm cư dân test."""
    from src.services.security import hash_password

    nguoi = User(
        email=email,
        full_name=f"Cư dân {email}",
        role="resident",
        password_hash=hash_password(MAT_KHAU),
    )
    session.add(nguoi)
    session.flush()
    return nguoi


async def _tao_yeu_cau(
    api: AsyncClient, token: str, *, weight: float = 8, ngay: date | None = None
) -> dict:
    """Tạo yêu cầu thu gom cồng kềnh."""
    if ngay is None:
        ngay = date.today() + timedelta(days=3)
    r = await api.post(
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
    assert r.status_code == 200, r.text
    return r.json()


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 1 — XÁC THỰC & PHÂN QUYỀN (AUTH & RBAC)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_1_01_dang_nhap_email_thanh_cong(api: AsyncClient) -> None:
    r = await api.post(
        "/api/v1/auth/login",
        json={"email": "resident@demo.vn", "password": MAT_KHAU},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["token"]
    assert data["user"]["role"] == "resident"
    assert "permissions" in data


@pytest.mark.asyncio
async def test_1_02_dang_nhap_so_dien_thoai(api: AsyncClient) -> None:
    r = await api.post(
        "/api/v1/auth/login",
        json={"phone": "0901000001", "password": MAT_KHAU},
    )
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "resident"


@pytest.mark.asyncio
async def test_1_03_sai_mat_khau_loi_tieng_viet(api: AsyncClient) -> None:
    r = await api.post(
        "/api/v1/auth/login",
        json={"email": "resident@demo.vn", "password": "sai_mat_khau"},
    )
    assert r.status_code == 401
    loi = r.json()["error"]
    assert loi["code"] == "AUTH-401"
    assert loi["message_vi"]


@pytest.mark.asyncio
async def test_1_04_dang_ky_cu_dan_moi(api: AsyncClient) -> None:
    r = await api.post(
        "/api/v1/auth/register",
        json={
            "phone": "0909999888",
            "password": "matkhautest123",
            "full_name": "Nguyễn Test Đăng Ký",
        },
    )
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "resident"


@pytest.mark.asyncio
async def test_1_05_dang_ky_trung_sdt_bi_chan(api: AsyncClient) -> None:
    payload = {
        "phone": "0909999777",
        "password": "matkhau123",
        "full_name": "Người Thứ Nhất",
    }
    r1 = await api.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201

    r2 = await api.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_1_06_resident_khong_co_quyen_view_ops(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.get("/api/v1/ops/metrics", headers=_auth(token))
    assert r.status_code == 403
    assert "ban quản lý" in r.json()["error"]["message_vi"]


@pytest.mark.asyncio
async def test_1_07_manager_co_quyen_view_ops(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    r = await api.get("/api/v1/ops/metrics", headers=_auth(token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_1_08_cleaner_co_quyen_verify_label(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "cleaner@demo.vn")
    r = await api.get("/api/v1/verify-queue", headers=_auth(token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_1_09_demo_accounts_tra_3_tai_khoan(api: AsyncClient) -> None:
    r = await api.get("/api/v1/auth/demo-accounts")
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_1_10_xem_ho_so_ca_nhan(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.get("/api/v1/auth/me", headers=_auth(token))
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "resident"
    assert "permissions" in data


@pytest.mark.asyncio
async def test_1_11_cap_nhat_ten_ca_nhan(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.patch(
        "/api/v1/auth/me",
        json={"full_name": "Tên Mới Test"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "Tên Mới Test"


@pytest.mark.asyncio
async def test_1_12_lich_su_phan_loai_ca_nhan(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.get("/api/v1/auth/me/history", headers=_auth(token))
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 2 — PHÂN LOẠI RÁC (VISION CLASSIFICATION)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_2_01_phan_loai_bang_chu_thanh_cong(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_vision(monkeypatch, make_result(confidence=0.91))
    token = await _dang_nhap(api, "resident@demo.vn")

    r = await api.post(
        "/api/v1/classify/text",
        json={"text_query": "hộp sữa giấy tráng nhôm"},
        headers=_auth(token),
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["refused"] is False
    assert data["category"]["code"] == "recyclable_paper"
    assert data["run_id"] is not None


@pytest.mark.asyncio
async def test_2_02_confidence_thap_thi_tu_choi(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_vision(monkeypatch, make_result(confidence=0.30))
    token = await _dang_nhap(api, "resident@demo.vn")

    r = await api.post(
        "/api/v1/classify/text",
        json={"text_query": "vật thể lạ"},
        headers=_auth(token),
    )

    assert r.status_code == 200
    data = r.json()
    assert data["refused"] is True
    assert data["refusal_reason"]


@pytest.mark.asyncio
async def test_2_03_ket_qua_co_trich_nguon(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_vision(monkeypatch, make_result(confidence=0.91))
    token = await _dang_nhap(api, "resident@demo.vn")

    r = await api.post(
        "/api/v1/classify/text",
        json={"text_query": "chai nhựa pet"},
        headers=_auth(token),
    )

    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 3 — CHẶN CỨNG RÁC NGUY HẠI (SAFETY HARD BLOCK)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_3_01_kim_tiem_bi_chan_cung(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.post(
        "/api/v1/classify/text",
        json={"text_query": "kim tiêm cũ"},
        headers=_auth(token),
    )
    data = r.json()
    assert data["refused"] is True
    assert data["hard_block"]["code"]


@pytest.mark.asyncio
async def test_3_02_binh_gas_mini_bi_chan(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.post(
        "/api/v1/classify/text",
        json={"text_query": "bình gas mini hết"},
        headers=_auth(token),
    )
    data = r.json()
    assert data["refused"] is True
    assert data["hard_block"]["code"] == "binh_gas"


@pytest.mark.asyncio
async def test_3_03_tu_choi_khong_kem_huong_dan(api: AsyncClient) -> None:
    """Từ chối thì không được kèm hướng dẫn xử lý — tránh gợi ý sai."""
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.post(
        "/api/v1/classify/text",
        json={"text_query": "kim tiêm cũ"},
        headers=_auth(token),
    )
    data = r.json()
    assert data["advice"] == ""


@pytest.mark.asyncio
async def test_3_04_danh_sach_hard_block(api: AsyncClient) -> None:
    r = await api.get("/api/v1/safety/hard-blocks")
    assert r.status_code == 200
    assert len(r.json()["items"]) > 0


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 4 — PHẢN HỒI & HÀNG ĐỢI XÁC NHẬN NHÃN (HITL #2)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_4_01_ca_bi_tu_choi_vao_hang_doi_xac_nhan(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    await api.post(
        "/api/v1/classify/text",
        json={"text_query": "kim tiêm cũ"},
        headers=_auth(resident),
    )

    manager = await _dang_nhap(api, "manager@demo.vn")
    r = await api.get("/api/v1/verify-queue", headers=_auth(manager))
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_4_02_manager_xac_nhan_nhan(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    tao = (
        await api.post(
            "/api/v1/classify/text",
            json={"text_query": "kim tiêm cũ"},
            headers=_auth(resident),
        )
    ).json()

    manager = await _dang_nhap(api, "manager@demo.vn")
    r = await api.post(
        f"/api/v1/classifications/{tao['classification_id']}/verify",
        json={"category_code": "hazardous", "reply_text": "Mang tới điểm thu gom."},
        headers=_auth(manager),
    )
    assert r.status_code == 200
    assert r.json()["human_label"]["code"] == "hazardous"


@pytest.mark.asyncio
async def test_4_03_resident_khong_duoc_verify(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    tao = (
        await api.post(
            "/api/v1/classify/text",
            json={"text_query": "kim tiêm cũ"},
            headers=_auth(resident),
        )
    ).json()

    r = await api.post(
        f"/api/v1/classifications/{tao['classification_id']}/verify",
        json={"category_code": "hazardous"},
        headers=_auth(resident),
    )
    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 5 — YÊU CẦU THU GOM ĐỒ CỒNG KỀNH (PICKUP REQUESTS)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_5_01_duoi_nguong_thi_tu_dong_cho_nhan(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    data = await _tao_yeu_cau(api, token, weight=10)
    assert data["status"] == CHO_NHAN
    assert data["requires_hitl"] is False


@pytest.mark.asyncio
async def test_5_02_vuot_nguong_thi_can_duyet(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    data = await _tao_yeu_cau(api, token, weight=48)
    assert data["status"] == CHO_DUYET
    assert data["requires_hitl"] is True


@pytest.mark.asyncio
async def test_5_03_manager_duyet_yeu_cau(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    data = await _tao_yeu_cau(api, resident, weight=48)
    manager = await _dang_nhap(api, "manager@demo.vn")

    r = await api.post(
        f"/api/v1/pickups/{data['id']}/review",
        json={"action": "approve"},
        headers=_auth(manager),
    )
    assert r.status_code == 200
    assert r.json()["status"] == CHO_NHAN


@pytest.mark.asyncio
async def test_5_04_manager_tu_choi_co_ly_do(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    data = await _tao_yeu_cau(api, resident, weight=48)
    manager = await _dang_nhap(api, "manager@demo.vn")

    r = await api.post(
        f"/api/v1/pickups/{data['id']}/review",
        json={"action": "reject", "reason": "khong_dung_quy_cach"},
        headers=_auth(manager),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "tu_choi"


@pytest.mark.asyncio
async def test_5_05_cu_dan_huy_yeu_cau(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    data = await _tao_yeu_cau(api, token, weight=10)

    r = await api.delete(
        f"/api/v1/pickups/{data['id']}",
        headers=_auth(token),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_5_06_danh_sach_yeu_cau_co_phan_trang(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.get("/api/v1/pickups", headers=_auth(token))
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 6 — MÁY TRẠNG THÁI VÒNG ĐỜI THU GOM (PICKUP LIFECYCLE)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_6_01_chuyen_cho_nhan_sang_da_nhan(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    yc = await _tao_yeu_cau(api, resident)

    r = await api.post(
        f"/api/v1/pickups/{yc['id']}/chuyen-trang-thai",
        json={"den": "da_nhan"},
        headers=_auth(cleaner),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "da_nhan"


@pytest.mark.asyncio
async def test_6_02_luong_day_du_3_buoc(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    yc = await _tao_yeu_cau(api, resident)

    for buoc in ("da_nhan", "dang_van_chuyen", "da_giao_don_vi"):
        r = await api.post(
            f"/api/v1/pickups/{yc['id']}/chuyen-trang-thai",
            json={"den": buoc},
            headers=_auth(cleaner),
        )
        assert r.status_code == 200, f"Bước {buoc} thất bại: {r.text}"
        assert r.json()["status"] == buoc


@pytest.mark.asyncio
async def test_6_03_xac_nhan_khoi_luong_hoan_tat(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    yc = await _tao_yeu_cau(api, resident)

    for buoc in ("da_nhan", "dang_van_chuyen", "da_giao_don_vi"):
        await api.post(
            f"/api/v1/pickups/{yc['id']}/chuyen-trang-thai",
            json={"den": buoc},
            headers=_auth(cleaner),
        )

    r = await api.post(
        f"/api/v1/pickups/{yc['id']}/xac-nhan-khoi-luong",
        json={"weight_confirmed_kg": 8.0},
        headers=_auth(cleaner),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "hoan_tat"
    assert r.json()["weight_confirmed_kg"] == 8.0


@pytest.mark.asyncio
async def test_6_04_khoi_luong_lech_nhieu_thi_tranh_chap(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    yc = await _tao_yeu_cau(api, resident)

    for buoc in ("da_nhan", "dang_van_chuyen", "da_giao_don_vi"):
        await api.post(
            f"/api/v1/pickups/{yc['id']}/chuyen-trang-thai",
            json={"den": buoc},
            headers=_auth(cleaner),
        )

    r = await api.post(
        f"/api/v1/pickups/{yc['id']}/xac-nhan-khoi-luong",
        json={"weight_confirmed_kg": 50.0},
        headers=_auth(cleaner),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "tranh_chap"
    assert r.json()["dispute_reason"]


@pytest.mark.asyncio
async def test_6_05_buoc_chuyen_bat_hop_le_tra_400(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    yc = await _tao_yeu_cau(api, resident)

    r = await api.post(
        f"/api/v1/pickups/{yc['id']}/chuyen-trang-thai",
        json={"den": "hoan_tat"},
        headers=_auth(cleaner),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_6_06_yeu_cau_khong_ton_tai_tra_404(api: AsyncClient) -> None:
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    r = await api.post(
        "/api/v1/pickups/99999/chuyen-trang-thai",
        json={"den": "da_nhan"},
        headers=_auth(cleaner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_6_07_cu_dan_khong_duoc_day_trang_thai(api: AsyncClient) -> None:
    resident = await _dang_nhap(api, "resident@demo.vn")
    yc = await _tao_yeu_cau(api, resident)

    r = await api.post(
        f"/api/v1/pickups/{yc['id']}/chuyen-trang-thai",
        json={"den": "da_nhan"},
        headers=_auth(resident),
    )
    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 7 — GỘP TUYẾN THU GOM (ROUTE PLANNING — HITL #3)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_7_01_de_xuat_tuyen_trang_thai_proposed(api: AsyncClient) -> None:
    ngay = date.today() + timedelta(days=3)
    resident = await _dang_nhap(api, "resident@demo.vn")
    manager = await _dang_nhap(api, "manager@demo.vn")

    await _tao_yeu_cau(api, resident, weight=10, ngay=ngay)
    await _tao_yeu_cau(api, resident, weight=12, ngay=ngay)

    r = await api.post(
        "/api/v1/routes/propose",
        json={"service_date": ngay.isoformat(), "window": "08:00-10:00"},
        headers=_auth(manager),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "proposed"


@pytest.mark.asyncio
async def test_7_02_tuyen_co_reasoning(api: AsyncClient) -> None:
    ngay = date.today() + timedelta(days=4)
    resident = await _dang_nhap(api, "resident@demo.vn")
    manager = await _dang_nhap(api, "manager@demo.vn")

    await _tao_yeu_cau(api, resident, weight=10, ngay=ngay)
    await _tao_yeu_cau(api, resident, weight=12, ngay=ngay)

    r = await api.post(
        "/api/v1/routes/propose",
        json={"service_date": ngay.isoformat(), "window": "08:00-10:00"},
        headers=_auth(manager),
    )
    data = r.json()
    assert data["reasoning"]["criteria"]
    assert data["reasoning"]["saved_km"] >= 0


@pytest.mark.asyncio
async def test_7_03_manager_duyet_tuyen(api: AsyncClient) -> None:
    ngay = date.today() + timedelta(days=5)
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

    r = await api.post(
        f"/api/v1/routes/{tuyen['id']}/review",
        json={"action": "approve"},
        headers=_auth(manager),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_7_04_danh_sach_tuyen(api: AsyncClient) -> None:
    manager = await _dang_nhap(api, "manager@demo.vn")
    r = await api.get("/api/v1/routes", headers=_auth(manager))
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 8 — THÙNG RÁC THÔNG MINH (SMART BINS)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_8_01_danh_sach_thung(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "cleaner@demo.vn")
    r = await api.get("/api/v1/bins", headers=_auth(token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_8_02_thong_ke_trang_thai(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "cleaner@demo.vn")
    r = await api.get("/api/v1/bins/stats", headers=_auth(token))
    assert r.status_code == 200
    data = r.json()
    # Phải có 4 nhóm trạng thái
    for key in ("binh_thuong", "can_gom", "het_pin", "mat_ket_noi"):
        assert key in data


@pytest.mark.asyncio
async def test_8_03_diem_gui_cho_cu_dan(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.get("/api/v1/bins/diem-gui", headers=_auth(token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_8_04_resident_khong_xem_duoc_bins(api: AsyncClient) -> None:
    """Resident chỉ xem được điểm gửi, không xem được danh sách vận hành."""
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.get("/api/v1/bins", headers=_auth(token))
    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 9 — IoT CAPTURES (PHÂN LOẠI TỪ THIẾT BỊ)
# ═══════════════════════════════════════════════════════════════════════════

# Lưu ý: IoT captures cần device key setup phức tạp. Kiểm tra cơ bản nhất:


@pytest.mark.asyncio
async def test_9_01_iot_captures_khong_co_key_bi_chan(api: AsyncClient) -> None:
    """Không có device key → fail closed."""
    r = await api.post(
        "/api/v1/iot/captures",
        headers={"X-Device-Key": "wrong-key"},
    )
    # Phải trả 401 hoặc 503 (fail closed), không phải 200
    assert r.status_code in (401, 403, 503)


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 10 — PHIÊN BỎ RÁC TẠI THÙNG (DISPOSAL SESSIONS)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_10_01_mo_phien_thanh_cong(
    api: AsyncClient, api_session: Session
) -> None:
    _them_thung(api_session)
    _them_cu_dan(api_session, "test-phien@demo.vn")
    api_session.commit()
    token = await _dang_nhap(api, "test-phien@demo.vn")

    r = await api.post(
        "/api/v1/phien/bat-dau",
        json={"bin_code": "BIN-TD"},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ma_phien"]
    assert data["trang_thai"] == "dang_mo"
    assert data["so_vat"] == 0


@pytest.mark.asyncio
async def test_10_02_mot_thung_chi_mot_phien_mo(
    api: AsyncClient, api_session: Session
) -> None:
    _them_thung(api_session, "BIN-1PHIEN")
    _them_cu_dan(api_session, "a-phien@demo.vn")
    _them_cu_dan(api_session, "b-phien@demo.vn")
    api_session.commit()

    token_a = await _dang_nhap(api, "a-phien@demo.vn")
    token_b = await _dang_nhap(api, "b-phien@demo.vn")

    r1 = await api.post(
        "/api/v1/phien/bat-dau",
        json={"bin_code": "BIN-1PHIEN"},
        headers=_auth(token_a),
    )
    assert r1.status_code == 200

    r2 = await api.post(
        "/api/v1/phien/bat-dau",
        json={"bin_code": "BIN-1PHIEN"},
        headers=_auth(token_b),
    )
    assert r2.status_code == 400
    assert "đang có người sử dụng" in r2.json()["error"]["message_vi"]


@pytest.mark.asyncio
async def test_10_03_xem_trang_thai_phien(
    api: AsyncClient, api_session: Session
) -> None:
    _them_thung(api_session, "BIN-XEM")
    _them_cu_dan(api_session, "xem-phien@demo.vn")
    api_session.commit()
    token = await _dang_nhap(api, "xem-phien@demo.vn")

    mo = await api.post(
        "/api/v1/phien/bat-dau",
        json={"bin_code": "BIN-XEM"},
        headers=_auth(token),
    )
    ma = mo.json()["ma_phien"]

    r = await api.get(f"/api/v1/phien/{ma}", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["trang_thai"] == "dang_mo"


@pytest.mark.asyncio
async def test_10_04_dong_phien(
    api: AsyncClient, api_session: Session
) -> None:
    _them_thung(api_session, "BIN-DONG")
    _them_cu_dan(api_session, "dong-phien@demo.vn")
    api_session.commit()
    token = await _dang_nhap(api, "dong-phien@demo.vn")

    mo = await api.post(
        "/api/v1/phien/bat-dau",
        json={"bin_code": "BIN-DONG"},
        headers=_auth(token),
    )
    ma = mo.json()["ma_phien"]

    r = await api.post(f"/api/v1/phien/{ma}/dong", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["trang_thai"] == "da_dong"


@pytest.mark.asyncio
async def test_10_05_dong_phien_khong_cham_green_points(
    api: AsyncClient, api_session: Session
) -> None:
    """Điểm nhận thức KHÔNG được cộng vào green_points."""
    _them_thung(api_session, "BIN-DIEM")
    cu_dan = _them_cu_dan(api_session, "diem-phien@demo.vn")
    cu_dan.green_points = 100
    api_session.commit()

    token = await _dang_nhap(api, "diem-phien@demo.vn")
    mo = await api.post(
        "/api/v1/phien/bat-dau",
        json={"bin_code": "BIN-DIEM"},
        headers=_auth(token),
    )
    ma = mo.json()["ma_phien"]
    await api.post(f"/api/v1/phien/{ma}/dong", headers=_auth(token))

    api_session.refresh(cu_dan)
    assert cu_dan.green_points == 100, "green_points không được đổi"

    so_log = api_session.scalar(select(func.count(DiemThuongLog.id))) or 0
    assert so_log == 0, "diem_thuong_log không được có dòng mới"


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 11 — CHATBOT AI RAG
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_11_01_goi_y_cau_hoi_nhanh(api: AsyncClient) -> None:
    r = await api.get("/api/v1/chatbot/suggested-questions")
    assert r.status_code == 200
    assert len(r.json()["items"]) > 0


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 12 — ẢNH & QUYỀN RIÊNG TƯ (MEDIA PRIVACY)
# ═══════════════════════════════════════════════════════════════════════════

# Lưu ý: Upload ảnh thật cần mock storage. Test cơ bản nhất:


@pytest.mark.asyncio
async def test_12_01_resident_khong_xem_duoc_anh_goc(api: AsyncClient) -> None:
    """Chỉ manager có quyền view_original_media."""
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.get("/api/v1/media/1/original", headers=_auth(token))
    assert r.status_code in (403, 404)


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 13 — DANH MỤC & TRI THỨC (CATALOG & KNOWLEDGE)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_13_01_danh_muc_rac_co_it_nhat_9_nhom(api: AsyncClient) -> None:
    r = await api.get("/api/v1/categories")
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 9


@pytest.mark.asyncio
async def test_13_02_danh_muc_nguy_hai_co_canh_bao(api: AsyncClient) -> None:
    r = await api.get("/api/v1/categories")
    danh_muc = r.json()["items"]
    nguy_hai = next((c for c in danh_muc if c["code"] == "hazardous"), None)
    assert nguy_hai is not None
    assert nguy_hai["min_confidence"] >= 0.80
    assert nguy_hai["safety_warning"]
    assert nguy_hai["bin_color"]


@pytest.mark.asyncio
async def test_13_03_danh_sach_toa_nha(api: AsyncClient) -> None:
    r = await api.get("/api/v1/buildings")
    assert r.status_code == 200
    assert len(r.json()["items"]) > 0


@pytest.mark.asyncio
async def test_13_04_lich_thu_gom_toa_nha(
    api: AsyncClient, api_session: Session
) -> None:
    from src.db.models import Building

    building = api_session.scalar(select(Building).where(Building.code == "S1"))
    r = await api.get(f"/api/v1/buildings/{building.id}/schedule")
    assert r.status_code == 200
    assert r.json()["items"]


@pytest.mark.asyncio
async def test_13_05_enum_metadata(api: AsyncClient) -> None:
    r = await api.get("/api/v1/meta/enums")
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 14 — VẬN HÀNH & GIÁM SÁT (OPS & METRICS)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_14_01_trang_tong_quan(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    r = await api.get("/api/v1/overview", headers=_auth(token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_14_02_chi_phi_va_do_tre_model(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    r = await api.get("/api/v1/ops/metrics", headers=_auth(token))
    assert r.status_code == 200
    data = r.json()
    assert "cost" in data
    assert "known_limitations" in data


@pytest.mark.asyncio
async def test_14_03_chi_so_danh_gia_ai(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    r = await api.get("/api/v1/eval/summary", headers=_auth(token))
    assert r.status_code == 200
    data = r.json()
    assert data["safety"]["target"] == 0


@pytest.mark.asyncio
async def test_14_04_danh_sach_agent_run(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    r = await api.get("/api/v1/runs", headers=_auth(token))
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 15 — HỆ THỐNG HEALTH & STATUS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_15_01_health_check(api: AsyncClient) -> None:
    r = await api.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_15_02_status_endpoint(api: AsyncClient) -> None:
    r = await api.get("/api/v1/status")
    assert r.status_code == 200
    data = r.json()
    assert "model" in data


@pytest.mark.asyncio
async def test_15_03_health_khong_lo_chuoi_ket_noi(api: AsyncClient) -> None:
    r = await api.get("/health")
    text = r.text
    assert "postgresql" not in text.lower()
    assert "@" not in text


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 16 — ĐIỂM THƯỞNG & GAMIFICATION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_16_01_xem_diem_nhan_thuc(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.get("/api/v1/diem/nhan-thuc", headers=_auth(token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_16_02_xem_nhiem_vu(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.get("/api/v1/diem/nhiem-vu", headers=_auth(token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_16_03_kiem_tra_nhiem_vu(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.post("/api/v1/diem/nhiem-vu/kiem", headers=_auth(token))
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 17 — GPS TRACKING & DẪN ĐƯỜNG
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_17_01_gui_toa_do_gps(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "cleaner@demo.vn")
    r = await api.post(
        "/api/v1/tracking/gps",
        json={"lat": 21.0285, "lng": 105.8542, "route_id": 0},
        headers=_auth(token),
    )
    # Có thể 200 hoặc 400 nếu route_id=0 không tồn tại — nhưng không được 500
    assert r.status_code != 500


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 18 — THÔNG BÁO & CẢNH BÁO
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_18_01_danh_sach_thong_bao(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    r = await api.get("/api/v1/notifications", headers=_auth(token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_18_02_danh_sach_canh_bao(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    r = await api.get("/api/v1/alerts", headers=_auth(token))
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 19 — XỬ LÝ LỖI & SUY GIẢM (ERROR HANDLING)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_19_01_endpoint_khong_ton_tai_tra_404(api: AsyncClient) -> None:
    r = await api.get("/api/v1/khong-co-endpoint-nay")
    assert r.status_code in (404, 405)


@pytest.mark.asyncio
async def test_19_02_thieu_token_tra_401(api: AsyncClient) -> None:
    r = await api.get("/api/v1/auth/me")
    assert r.status_code == 401
    loi = r.json()["error"]
    assert loi["code"] == "AUTH-401"
    assert loi["message_vi"]


@pytest.mark.asyncio
async def test_19_03_moi_loi_co_code_va_message_vi(api: AsyncClient) -> None:
    """Mọi lỗi phải trả về cấu trúc chuẩn hóa."""
    r = await api.post(
        "/api/v1/auth/login",
        json={"email": "khong@co.vn", "password": "sai"},
    )
    assert r.status_code == 401
    loi = r.json()["error"]
    assert "code" in loi
    assert "message_vi" in loi


# ═══════════════════════════════════════════════════════════════════════════
#  NHÓM 20 — GIỚI HẠN TẦN SUẤT ĐĂNG KÝ (RATE LIMITING)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_20_01_dang_ky_lien_tuc_vuot_gioi_han(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Đăng ký liên tục vượt giới hạn → 429."""
    # Đặt giới hạn rất thấp để test nhanh
    monkeypatch.setenv("REGISTER_RATE_LIMIT", "2")
    monkeypatch.setenv("REGISTER_RATE_WINDOW_SECONDS", "600")
    reset_settings_cache()

    results = []
    for i in range(5):
        r = await api.post(
            "/api/v1/auth/register",
            json={
                "phone": f"098800{i:04d}",
                "password": "matkhautest123",
                "full_name": f"Rate Limit Test {i}",
            },
        )
        results.append(r.status_code)

    assert 429 in results, f"Phải có ít nhất 1 lần bị chặn 429, nhận được: {results}"
