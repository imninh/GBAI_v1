"""Đi trọn kịch bản demo bằng một lệnh — nối các mảnh test lại thành một chuỗi.

Mỗi test riêng lẻ trong repo kiểm một mảnh (đăng nhập, phân loại, tạo yêu cầu,
duyệt, xếp tuyến, đổ thùng, cân). Test này nối chúng lại theo đúng đường mà buổi
demo sẽ đi, mỗi bước một ``assert`` kèm câu tiếng Việt chỉ rõ đang ở bước nào.

Không gọi API model thật: ``FakeVisionClient`` cho tầng phân loại, và bước tra
quy định (advise) bị ép lui về hướng dẫn chuẩn — đúng kiểu ``test_graph.py`` làm.
"""

from __future__ import annotations

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
from src.db.models import AuditLog, Base, User
from src.main import app
from src.services import classifier
from tests.conftest import FakeVisionClient, make_result

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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _dang_nhap(api: AsyncClient, email: str) -> dict:
    """Đăng nhập bằng email — ba nút "vào thẳng" của màn đăng nhập."""
    response = await api.post("/api/v1/auth/login", json={"email": email, "password": MAT_KHAU})
    assert response.status_code == 200, f"Đăng nhập {email} thất bại — {response.text}"
    return response.json()


async def _dang_nhap_phone(api: AsyncClient, api_session: Session) -> dict:
    """Đăng nhập bằng SỐ ĐIỆN THOẠI — đường cư dân thật dùng."""
    so = api_session.scalar(select(User.phone).where(User.email == "resident@demo.vn"))
    assert so, "Bước 1: cư dân demo phải có số điện thoại để đăng nhập"
    response = await api.post("/api/v1/auth/login", json={"phone": so, "password": MAT_KHAU})
    assert response.status_code == 200, f"Đăng nhập bằng số điện thoại thất bại — {response.text}"
    return response.json()


def _dung_model_gia(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ép mọi lệnh gọi model về bản giả — test không bao giờ đụng mạng."""
    fake = FakeVisionClient(results=[make_result(confidence=0.91)])
    monkeypatch.setattr(classifier, "get_vision_client", lambda tier="t1": fake)
    monkeypatch.setattr(classifier, "get_tier_model", lambda tier="t1": f"model-{tier}")
    monkeypatch.setattr(classifier, "get_tier_provider", lambda tier="t1": "fake")
    monkeypatch.setattr(classifier, "classify_image_local", lambda *a, **k: None)

    from src.services.vision import VisionUnavailableError

    # Bước advise gọi ``src.services.vision.get_vision_client("text")`` trực tiếp;
    # ép nó ném để lui về hướng dẫn chuẩn của danh mục (đúng test_graph.py).
    monkeypatch.setattr(
        "src.services.vision.get_vision_client",
        lambda tier="t1": (_ for _ in ()).throw(VisionUnavailableError("test khong goi model")),
    )


def _dem_audit(session: Session) -> int:
    return int(session.scalar(select(func.count(AuditLog.id))) or 0)


@pytest.mark.asyncio
async def test_di_tron_kich_ban_demo(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dung_model_gia(monkeypatch)
    audit_truoc = _dem_audit(api_session)

    # Bước 1 — Cư dân đăng nhập bằng số điện thoại
    resident = await _dang_nhap_phone(api, api_session)
    token_resident = resident["token"]
    assert resident["user"]["role"] == "resident", "Bước 1: vai trò đăng nhập phải là cư dân"

    # Bước 2 — Cư dân phân loại bằng mô tả bằng chữ
    response = await api.post(
        "/api/v1/classify/text",
        json={"text_query": "hộp sữa giấy tráng nhôm"},
        headers=_auth(token_resident),
    )
    assert response.status_code == 200, f"Bước 2: phân loại bằng chữ thất bại — {response.text}"
    phan_loai = response.json()
    assert phan_loai["category"]["code"], "Bước 2: phải có nhãn phân loại"
    assert phan_loai["advice"], "Bước 2: phải có hướng dẫn xử lý"
    assert phan_loai["advice_sources"], "Bước 2: hướng dẫn phải kèm trích nguồn quy định"

    # Bước 3 — Cư dân tạo yêu cầu thu gom đồ cồng kềnh vượt ngưỡng
    ngay_thu = (date.today() + timedelta(days=3)).isoformat()

    async def _tao_pickup_vuot_nguong() -> dict:
        resp = await api.post(
            "/api/v1/pickups",
            json={
                "items": [{"name": "Tủ gỗ cũ", "category_code": "bulky", "qty": 1}],
                "est_weight_kg": 40,
                "preferred_date": ngay_thu,
                "preferred_window": "08:00-10:00",
                "confirmed_no_hazardous": True,
            },
            headers=_auth(token_resident),
        )
        assert resp.status_code == 200, f"Bước 3: tạo yêu cầu thất bại — {resp.text}"
        return resp.json()

    yeu_cau_a = await _tao_pickup_vuot_nguong()
    yeu_cau_b = await _tao_pickup_vuot_nguong()
    assert yeu_cau_a["status"] == "cho_duyet", "Bước 3: vượt ngưỡng thì phải chờ ban quản lý duyệt"
    assert yeu_cau_b["status"] == "cho_duyet", "Bước 3: yêu cầu thứ hai cũng phải chờ duyệt"

    # Bước 4 — Đơn vị thu gom đăng nhập và duyệt cả hai yêu cầu
    manager = await _dang_nhap(api, "manager@demo.vn")
    token_manager = manager["token"]
    for yc in (yeu_cau_a, yeu_cau_b):
        response = await api.post(
            f"/api/v1/pickups/{yc['id']}/review",
            json={"action": "approve"},
            headers=_auth(token_manager),
        )
        assert response.status_code == 200, f"Bước 4: duyệt yêu cầu {yc['id']} thất bại — {response.text}"
        assert response.json()["status"] == "cho_nhan", "Bước 4: duyệt xong phải về nhóm chờ xếp tuyến"

    # Bước 5 — Xếp tuyến, agent đề xuất tuyến có 2 điểm dừng
    response = await api.post(
        "/api/v1/routes/propose",
        json={"service_date": ngay_thu, "window": "08:00-10:00"},
        headers=_auth(token_manager),
    )
    assert response.status_code == 200, f"Bước 5: xếp tuyến thất bại — {response.text}"
    tuyen = response.json()
    assert tuyen["status"] == "proposed", "Bước 5: agent không được tự chốt lịch, tuyến phải là đề xuất"
    assert len(tuyen["stops"]) >= 2, "Bước 5: tuyến phải gộp được cả hai yêu cầu"
    assert tuyen["reasoning"]["criteria"], "Bước 5: phải có lời giải thích vì sao gộp thế này"

    # Bước 5.5 — Gán kíp TRƯỚC khi duyệt: tuyến đã duyệt mà không có đội thì
    # cleaner không bao giờ thấy được (E2E §8) — API từ chối duyệt tuyến trống
    # kíp. Kíp phải đúng SO_NGUOI_MOI_KIP = 2 người.
    nhan_kip_1 = await _dang_nhap(api, "cleaner@demo.vn")
    nhan_kip_2 = await _dang_nhap(api, "cleaner2@demo.vn")
    response = await api.put(
        f"/api/v1/routes/{tuyen['id']}/kip",
        json={
            "user_ids": [nhan_kip_1["user"]["id"], nhan_kip_2["user"]["id"]],
            "truong_kip_id": nhan_kip_1["user"]["id"],
        },
        headers=_auth(token_manager),
    )
    assert response.status_code == 200, f"Bước 5.5: gán kíp thất bại — {response.text}"

    # Bước 6 — Duyệt tuyến kèm bỏ một điểm để diff khác bản AI
    diem_b = next(s for s in tuyen["stops"] if s["request_id"] == yeu_cau_b["id"])
    response = await api.post(
        f"/api/v1/routes/{tuyen['id']}/review",
        json={"action": "approve_with_changes", "removed_stops": [diem_b["stop_id"]]},
        headers=_auth(token_manager),
    )
    assert response.status_code == 200, f"Bước 6: duyệt tuyến thất bại — {response.text}"
    duyet = response.json()
    assert duyet["status"] == "approved", "Bước 6: tuyến phải được chốt"
    assert duyet["diff"]["changed"] is True, "Bước 6: bỏ điểm dừng thì diff phải khác bản AI đề xuất"

    # Bước 7 — Nhân viên vệ sinh đẩy yêu cầu B (bị bỏ khỏi tuyến) tới giao đơn vị
    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    token_cleaner = cleaner["token"]
    for buoc in ("da_nhan", "dang_van_chuyen", "da_giao_don_vi"):
        response = await api.post(
            f"/api/v1/pickups/{yeu_cau_b['id']}/chuyen-trang-thai",
            json={"den": buoc},
            headers=_auth(token_cleaner),
        )
        assert response.status_code == 200, f"Bước 7: đẩy tới {buoc} thất bại — {response.text}"
        assert response.json()["status"] == buoc, f"Bước 7: phải đang ở trạng thái {buoc}"

    # Bước 8 — Xác nhận khối lượng THẬT nằm trong khoảng ước lượng → hoàn tất
    response = await api.post(
        f"/api/v1/pickups/{yeu_cau_b['id']}/xac-nhan-khoi-luong",
        json={"weight_confirmed_kg": 40.0},
        headers=_auth(token_cleaner),
    )
    assert response.status_code == 200, f"Bước 8: xác nhận khối lượng thất bại — {response.text}"
    assert response.json()["status"] == "hoan_tat", "Bước 8: cân đúng khoảng ước lượng thì phải hoàn tất"

    # Bước 9 — Audit log đã dày lên sau cả chuỗi
    assert _dem_audit(api_session) > audit_truoc, "Bước 9: cả chuỗi thao tác phải để lại dấu vết audit"


@pytest.mark.asyncio
async def test_can_lech_qua_dung_sai_thi_ra_tranh_chap(api: AsyncClient, api_session: Session) -> None:
    """Nửa còn lại của nguyên tắc "chỉ khối lượng người cân mới chốt": cân lệch thì tranh chấp."""
    resident = await _dang_nhap_phone(api, api_session)
    token_resident = resident["token"]

    # Yêu cầu trong ngưỡng tự động → cho_nhan ngay, không cần duyệt
    response = await api.post(
        "/api/v1/pickups",
        json={
            "items": [{"name": "Thùng carton", "category_code": "recyclable_paper", "qty": 2}],
            "est_weight_kg": 8,
            "preferred_date": (date.today() + timedelta(days=3)).isoformat(),
            "preferred_window": "08:00-10:00",
            "confirmed_no_hazardous": True,
        },
        headers=_auth(token_resident),
    )
    assert response.status_code == 200, f"Tạo yêu cầu thất bại — {response.text}"
    yeu_cau = response.json()
    assert yeu_cau["status"] == "cho_nhan", "Yêu cầu trong ngưỡng phải tự động vào nhóm chờ xếp"

    cleaner = await _dang_nhap(api, "cleaner@demo.vn")
    token_cleaner = cleaner["token"]
    for buoc in ("da_nhan", "dang_van_chuyen", "da_giao_don_vi"):
        response = await api.post(
            f"/api/v1/pickups/{yeu_cau['id']}/chuyen-trang-thai",
            json={"den": buoc},
            headers=_auth(token_cleaner),
        )
        assert response.status_code == 200, f"Đẩy tới {buoc} thất bại — {response.text}"

    # Cân 30 kg trong khi khoảng ước lượng là 4,8–11,2 kg → tranh chấp, không hoàn tất
    response = await api.post(
        f"/api/v1/pickups/{yeu_cau['id']}/xac-nhan-khoi-luong",
        json={"weight_confirmed_kg": 30.0},
        headers=_auth(token_cleaner),
    )
    assert response.status_code == 200, f"Xác nhận khối lượng thất bại — {response.text}"
    data = response.json()
    assert data["status"] == "tranh_chap", "Cân lệch xa khoảng ước lượng phải ra tranh chấp"
    assert data["dispute_reason"], "Tranh chấp phải kèm lý do tiếng Việt giải thích vì sao"
