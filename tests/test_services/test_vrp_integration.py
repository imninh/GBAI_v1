"""Integration tests cho PyVRP & route_planner (kịch bản I1 - I8)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest

from src.config import reset_settings_cache
from src.db.models import Building, PickupRequest, Unit, User
from src.services import pickup, route_planner, vrp_solver
from src.services.pickup_lifecycle import CHO_DUYET


@pytest.fixture(autouse=True)
def _reset_config() -> Iterator[None]:
    reset_settings_cache()
    yield
    reset_settings_cache()


def _tao_du_lieu_demo(session, prefix: str = "T") -> tuple[Building, Unit, list[PickupRequest]]:
    manager = User(email=f"m_{prefix}@demo.vn", full_name="BQL Demo", role="manager", password_hash="x")
    session.add(manager)
    session.flush()

    building = Building(code=f"B-{prefix}", name=f"Toà {prefix}", lat=21.0285, lng=105.8542)
    session.add(building)
    session.flush()

    unit = Unit(building_id=building.id, code=f"U-{prefix}-101")
    session.add(unit)
    session.flush()

    resident = User(
        email=f"r_{prefix}@demo.vn", full_name="Cư dân Demo", role="resident", password_hash="x", unit_id=unit.id
    )
    session.add(resident)
    session.flush()

    today = date.today()
    requests = []
    for i in range(3):
        req = pickup.create_pickup_request(
            session,
            resident=resident,
            items=[{"name": "Giấy carton", "category_code": "paper", "qty": 1}],
            est_weight_kg=15.0 + i * 5,
            preferred_date=today,
            preferred_window="sang",
        )
        if req.status == CHO_DUYET:
            pickup.review_pickup(session, request=req, actor=manager, action="approve")
        requests.append(req)
    session.flush()
    return building, unit, requests


def test_i1_vrp_disabled_matches_legacy(db_session, monkeypatch: pytest.MonkeyPatch):
    """I1: vrp_enabled=False -> chạy thuật toán cũ, criteria có nearest-neighbour."""
    monkeypatch.setenv("VRP_ENABLED", "false")
    reset_settings_cache()
    _tao_du_lieu_demo(db_session, prefix="I1")

    route = route_planner.propose_route(db_session, service_date=date.today(), window="sang")
    assert route.status == "proposed"
    criteria = route.reasoning["criteria"]
    assert any("nearest-neighbour" in c for c in criteria)
    assert not any("PyVRP" in c for c in criteria)


def test_i2_vrp_enabled_smoke_test(db_session, monkeypatch: pytest.MonkeyPatch):
    """I2: vrp_enabled=True -> tạo PickupRoute thành công, status=proposed."""
    monkeypatch.setenv("VRP_ENABLED", "true")
    reset_settings_cache()
    _tao_du_lieu_demo(db_session, prefix="I2")

    route = route_planner.propose_route(db_session, service_date=date.today(), window="sang")
    assert route.status == "proposed"
    assert len(route.stops) >= 1
    assert "vrp_runtime_seconds" in route.reasoning


def test_i3_vrp_enabled_fallback_on_import_error(db_session, monkeypatch: pytest.MonkeyPatch):
    """I3: vrp_enabled=True nhưng mock lỗi import -> rơi êm về thuật toán cũ."""
    monkeypatch.setenv("VRP_ENABLED", "true")
    reset_settings_cache()
    _tao_du_lieu_demo(db_session, prefix="I3")

    monkeypatch.setattr(vrp_solver, "HAS_PYVRP", False)

    route = route_planner.propose_route(db_session, service_date=date.today(), window="sang")
    assert route.status == "proposed"
    criteria = route.reasoning["criteria"]
    assert any("nearest-neighbour" in c for c in criteria)


def test_i4_vrp_enabled_fallback_on_solver_failure(db_session, monkeypatch: pytest.MonkeyPatch):
    """I4: vrp_enabled=True nhưng solver trả kết quả rỗng -> rơi êm về thuật toán cũ."""
    monkeypatch.setenv("VRP_ENABLED", "true")
    reset_settings_cache()
    _tao_du_lieu_demo(db_session, prefix="I4")

    def _mock_solve(*args, **kwargs):
        return vrp_solver.VRPSolution(routes=[], unassigned=[], is_feasible=False)

    monkeypatch.setattr(vrp_solver, "solve", _mock_solve)

    route = route_planner.propose_route(db_session, service_date=date.today(), window="sang")
    assert route.status == "proposed"
    criteria = route.reasoning["criteria"]
    assert any("nearest-neighbour" in c for c in criteria)


def test_i5_criteria_when_vrp_enabled(db_session, monkeypatch: pytest.MonkeyPatch):
    """I5: reasoning.criteria[] khi PyVRP bật -> chứa 'PyVRP', không chứa 'nearest-neighbour'."""
    monkeypatch.setenv("VRP_ENABLED", "true")
    reset_settings_cache()
    _tao_du_lieu_demo(db_session, prefix="I5")

    route = route_planner.propose_route(db_session, service_date=date.today(), window="sang")
    criteria = route.reasoning["criteria"]
    assert any("PyVRP" in c for c in criteria)
    assert not any("nearest-neighbour" in c for c in criteria)


def test_i6_criteria_when_vrp_disabled(db_session, monkeypatch: pytest.MonkeyPatch):
    """I6: reasoning.criteria[] khi PyVRP tắt -> giữ nguyên 5 dòng chuẩn."""
    monkeypatch.setenv("VRP_ENABLED", "false")
    reset_settings_cache()
    _tao_du_lieu_demo(db_session, prefix="I6")

    route = route_planner.propose_route(db_session, service_date=date.today(), window="sang")
    criteria = route.reasoning["criteria"]
    assert len(criteria) == 5
    assert "nearest-neighbour" in criteria[4]


def test_i7_reviewer_approves_with_changes(db_session, monkeypatch: pytest.MonkeyPatch):
    """I7: Người duyệt sửa thứ tự / bỏ điểm -> _recalculate_totals hoạt động, reasoning ghi edited_by_human."""
    monkeypatch.setenv("VRP_ENABLED", "true")
    reset_settings_cache()
    _tao_du_lieu_demo(db_session, prefix="I7")

    actor = db_session.query(User).filter_by(role="manager").first()
    route = route_planner.propose_route(db_session, service_date=date.today(), window="sang")
    # Contract mới (E2E-03a): tuyến đã duyệt bắt buộc phải có kíp.
    don_vi = db_session.query(User).filter_by(role="cleaner").first()
    route.team_id = don_vi.id if don_vi else actor.id

    # Đảo ngược thứ tự điểm dừng
    stop_ids = [s.id for s in sorted(route.stops, key=lambda s: s.seq, reverse=True)]
    updated = route_planner.review_route(
        db_session,
        route=route,
        actor=actor,
        action="approve_with_changes",
        stop_order=stop_ids,
    )
    assert updated.status == "approved"
    assert updated.reasoning.get("edited_by_human") is True


def test_propose_routes_multi_vehicles(db_session, monkeypatch: pytest.MonkeyPatch):
    """Test propose_routes tạo nhiều tuyến khi tổng tải trọng vượt quá 1 xe."""
    monkeypatch.setenv("VRP_ENABLED", "true")
    monkeypatch.setenv("VEHICLE_CAPACITY_KG", "50.0")
    monkeypatch.setenv("VRP_NUM_VEHICLES", "3")
    reset_settings_cache()

    manager = User(email="m_multi@demo.vn", full_name="Manager", password_hash="h", role="manager")
    db_session.add(manager)
    db_session.flush()

    building = Building(code="B-MULTI", name="Toà Multi", lat=21.0285, lng=105.8542)
    db_session.add(building)
    db_session.flush()

    unit = Unit(building_id=building.id, code="U-M-1")
    db_session.add(unit)
    db_session.flush()

    resident = User(
        email="res_multi@demo.vn", full_name="Resident", password_hash="h", role="resident", unit_id=unit.id
    )
    db_session.add(resident)
    db_session.flush()

    today = date.today()
    # 4 requests each 25 kg -> total 100 kg, vehicle capacity 50 kg -> needs >= 2 routes
    for i in range(4):
        req = pickup.create_pickup_request(
            db_session,
            resident=resident,
            items=[{"name": "Giấy", "category_code": "paper", "qty": 1}],
            est_weight_kg=25.0,
            preferred_date=today,
            preferred_window="chieu",
        )
        if req.status == CHO_DUYET:
            pickup.review_pickup(db_session, request=req, actor=manager, action="approve")
    db_session.flush()

    routes = route_planner.propose_routes(db_session, service_date=today, window="chieu")
    assert len(routes) >= 2
    for r in routes:
        assert r.total_weight_kg <= 50.0 + 1e-5
        assert r.status == "proposed"
