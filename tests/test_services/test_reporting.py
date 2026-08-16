"""Test báo cáo tuân thủ theo tháng — dịch vụ và endpoint.

Báo cáo phải tính đúng trên một fixture nhỏ, **tách riêng ``is_seed``** để dữ
liệu demo không lẫn vào báo cáo thật; tháng sai định dạng phải trả 400 trong
khuôn lỗi; tháng không có dữ liệu phải trả báo cáo toàn số 0, không phải 404.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import (
    Base,
    Classification,
    PickupRequest,
    WasteCategory,
)
from src.main import app
from src.services import reporting

MAT_KHAU = "demo1234"
THANG_CO_DU_LIEU = "2026-07"


def _trong_thang(created: datetime) -> bool:
    return created.year == 2026 and created.month == 7


def _tao_pickup(session: Session, *, is_seed: bool, weight: float, items: list[dict], ngay: datetime) -> PickupRequest:
    yeu_cau = PickupRequest(
        resident_id=1,
        unit_id=1,
        items=items,
        weight_min_kg=weight,
        weight_max_kg=weight,
        est_weight_kg=weight,
        weight_confirmed_kg=weight,
        status="hoan_tat",
        is_seed=is_seed,
        created_at=ngay,
    )
    session.add(yeu_cau)
    session.flush()
    return yeu_cau


def _tao_phan_loai(
    session: Session,
    *,
    is_seed: bool,
    ngay: datetime,
    refused: bool = False,
    escalated: bool = False,
    human_label_code: str | None = None,
) -> Classification:
    nhom_dung = session.scalar(select(WasteCategory).where(WasteCategory.code == human_label_code)) if human_label_code else None
    ca = Classification(
        text_query="",
        input_type="text",
        item_name="",
        tier="t2_full" if escalated else "t1_mini",
        refused=refused,
        escalated_to_human=escalated,
        human_label_id=nhom_dung.id if nhom_dung else None,
        is_seed=is_seed,
        created_at=ngay,
    )
    session.add(ca)
    session.flush()
    return ca


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    reset_settings_cache()
    yield
    reset_settings_cache()


# --- Dịch vụ ----------------------------------------------------------------


def test_bao_cao_tinh_dung_tren_fixture_nho(db_session: Session) -> None:
    """Aggregation đúng: khối lượng theo nhóm, trạng thái, phân loại, nguy hại."""
    trong = datetime(2026, 7, 10, 9, 0)
    ngoai = datetime(2026, 6, 1, 9, 0)  # nằm ngoài tháng 07

    # Hai yêu cầu khối lượng xác nhận 30 và 50 → tổng 80 kg.
    _tao_pickup(
        db_session,
        is_seed=False,
        weight=30.0,
        items=[{"name": "Tủ gỗ", "category_code": "bulky", "qty": 1}],
        ngay=trong,
    )
    _tao_pickup(
        db_session,
        is_seed=False,
        weight=50.0,
        items=[{"name": "Thùng carton", "category_code": "recyclable_paper", "qty": 2}],
        ngay=trong,
    )
    _tao_pickup(db_session, is_seed=True, weight=99.0, items=[{"name": "X", "category_code": "bulky", "qty": 1}], ngay=trong)
    _tao_pickup(db_session, is_seed=False, weight=10.0, items=[{"name": "Lệch tháng", "category_code": "bulky", "qty": 1}], ngay=ngoai)

    # Phân loại: 1 bình thường, 1 từ chối, 1 leo T2, 1 ghi nhận nguy hại.
    _tao_phan_loai(db_session, is_seed=False, ngay=trong, human_label_code="recyclable_paper")
    _tao_phan_loai(db_session, is_seed=False, ngay=trong, refused=True)
    _tao_phan_loai(db_session, is_seed=False, ngay=trong, escalated=True)
    _tao_phan_loai(db_session, is_seed=False, ngay=trong, human_label_code="hazardous")
    _tao_phan_loai(db_session, is_seed=True, ngay=trong, human_label_code="hazardous")
    db_session.commit()

    bao_cao = reporting.bao_cao_tuan_thu(db_session, THANG_CO_DU_LIEU)

    # Khối lượng theo nhóm — chỉ thật, seed tách riêng.
    assert bao_cao["confirmed_weight_by_category"]["bulky"]["real"] == 30.0
    assert bao_cao["confirmed_weight_by_category"]["recyclable_paper"]["real"] == 50.0
    assert bao_cao["confirmed_weight_by_category"]["bulky"]["seed"] == 99.0

    # Trạng thái: 2 yêu cầu thật trong tháng (1 lệch tháng bị loại) + 1 seed.
    assert bao_cao["pickup_requests_by_state"]["hoan_tat"]["real"] == 2
    assert bao_cao["pickup_requests_by_state"]["hoan_tat"]["seed"] == 1

    # Phân loại AI: 4 thật + 1 seed; 1 từ chối; 1 leo T2 (tất cả thật).
    assert bao_cao["ai_classifications"]["total"] == {"real": 4, "seed": 1}
    assert bao_cao["ai_classifications"]["refused"] == {"real": 1, "seed": 0}
    assert bao_cao["ai_classifications"]["escalated"] == {"real": 1, "seed": 0}

    # Phát hiện nguy hại: 1 thật (human label hazardous) + 1 seed.
    assert bao_cao["hazardous_detections"] == {"real": 1, "seed": 1}

    assert bao_cao["has_seed_data"] is True


def test_bao_cao_loc_bo_du_lieu_seed(db_session: Session) -> None:
    """Chỉ có dữ liệu seed thì khối ``real`` phải toàn số 0, không lẫn."""
    _tao_pickup(db_session, is_seed=True, weight=42.0, items=[{"name": "X", "category_code": "bulky", "qty": 1}], ngay=datetime(2026, 7, 5))
    _tao_phan_loai(db_session, is_seed=True, ngay=datetime(2026, 7, 5), human_label_code="hazardous")
    db_session.commit()

    bao_cao = reporting.bao_cao_tuan_thu(db_session, THANG_CO_DU_LIEU)

    assert bao_cao["confirmed_weight_by_category"]["bulky"] == {"real": 0.0, "seed": 42.0}
    assert bao_cao["hazardous_detections"] == {"real": 0, "seed": 1}
    assert bao_cao["ai_classifications"]["total"] == {"real": 0, "seed": 1}
    assert bao_cao["has_seed_data"] is True


def test_thang_khong_du_lieu_tra_so_khong(db_session: Session) -> None:
    """Một tháng không có gì phải trả báo cáo đầy đủ số 0 — không phải 404."""
    bao_cao = reporting.bao_cao_tuan_thu(db_session, "2025-01")

    assert bao_cao["confirmed_weight_by_category"] == {}
    assert bao_cao["hazardous_detections"] == {"real": 0, "seed": 0}
    assert bao_cao["pickup_requests_by_state"]["hoan_tat"] == {"real": 0, "seed": 0}
    assert bao_cao["ai_classifications"]["total"] == {"real": 0, "seed": 0}
    assert bao_cao["has_seed_data"] is False


def test_thang_sai_dinh_dang_nem_valueerror(db_session: Session) -> None:
    with pytest.raises(ValueError, match="YYYY-MM"):
        reporting.bao_cao_tuan_thu(db_session, "07-2026")


def test_thang_12_chuyen_sang_nam_sau(db_session: Session) -> None:
    """Tháng 12 phải kết thúc ở đầu tháng 1 năm sau — không vỡ ranh giới năm."""
    bao_cao = reporting.bao_cao_tuan_thu(db_session, "2026-12")
    assert bao_cao["from"].startswith("2026-12-01")
    assert bao_cao["to"].startswith("2027-01-01")


# --- Endpoint ---------------------------------------------------------------


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


@pytest.mark.asyncio
async def test_endpoint_thang_sai_dinh_dang_tra_400(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bao-cao-tuan-thu", params={"thang": "thang-7"}, headers=_auth(token))

    assert response.status_code == 400
    assert "YYYY-MM" in response.json()["error"]["message_vi"]
    assert response.json()["error"]["code"] == "REPORT-400"


@pytest.mark.asyncio
async def test_endpoint_thang_trong_tra_so_khong(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bao-cao-tuan-thu", params={"thang": "2025-01"}, headers=_auth(token))

    assert response.status_code == 200, response.text
    bao_cao = response.json()
    assert bao_cao["ai_classifications"]["total"] == {"real": 0, "seed": 0}
    assert bao_cao["hazardous_detections"] == {"real": 0, "seed": 0}
