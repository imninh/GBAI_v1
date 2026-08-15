"""Unit test cho module giải VRP (vrp_solver.py).

Kiểm tra các kịch bản U1 đến U8 theo Kế hoạch triển khai PyVRP.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.services import vrp_solver


@dataclass
class FakeBuilding:
    id: int
    code: str
    lat: float | None = None
    lng: float | None = None


@dataclass
class FakeRequest:
    id: int
    weight_max_kg: float | None = None
    est_weight_kg: float = 10.0


@dataclass
class FakeBin:
    id: int
    code: str
    lat: float | None = None
    lng: float | None = None
    capacity_liters: float = 240.0
    fill_percent: float = 80.0


@dataclass
class FakeCandidate:
    request: FakeRequest | None = None
    building: FakeBuilding | None = None
    unit_code: str = ""
    thung: FakeBin | None = None
    _custom_weight: float | None = None

    @property
    def la_thung(self) -> bool:
        return self.thung is not None

    @property
    def weight_kg(self) -> float:
        if self._custom_weight is not None:
            return self._custom_weight
        if self.thung is not None:
            return self.thung.capacity_liters * (self.thung.fill_percent / 100.0) * 0.08
        if self.request is None:
            return 0.0
        return self.request.weight_max_kg or self.request.est_weight_kg

    @property
    def diem_id(self) -> str:
        if self.thung is not None:
            return f"thung:{self.thung.id}"
        return f"toa:{self.building.id}" if self.building is not None else ""

    @property
    def toa_do(self) -> tuple[float, float] | None:
        nguon = self.thung if self.thung is not None else self.building
        if nguon is None or nguon.lat is None or nguon.lng is None:
            return None
        return (nguon.lat, nguon.lng)

    @property
    def nhan_nhom(self) -> str:
        if self.thung is not None:
            return self.thung.code
        return self.building.code if self.building is not None else ""


def test_u1_zero_candidates():
    """U1: 0 candidate -> trả về danh sách rỗng, không ném lỗi."""
    sol = vrp_solver.solve([])
    assert sol.routes == []
    assert sol.unassigned == []
    assert sol.is_feasible is True


def test_u2_single_candidate():
    """U2: 1 candidate -> trả về 1 tuyến có 1 điểm dừng."""
    b = FakeBuilding(id=1, code="TOA-A", lat=21.0285, lng=105.8542)
    req = FakeRequest(id=101, est_weight_kg=25.0)
    c = FakeCandidate(request=req, building=b, unit_code="A-101")

    sol = vrp_solver.solve([c], capacity_kg=200.0)
    assert len(sol.routes) == 1
    assert len(sol.routes[0]) == 1
    assert sol.routes[0][0] == c
    assert sol.unassigned == []
    assert sol.is_feasible is True


def test_u3_three_candidates_same_building():
    """U3: 3 candidate cùng toà -> trả về 1 tuyến, 3 điểm."""
    b = FakeBuilding(id=1, code="TOA-A", lat=21.0285, lng=105.8542)
    c1 = FakeCandidate(request=FakeRequest(id=1, est_weight_kg=20.0), building=b, unit_code="A-101")
    c2 = FakeCandidate(request=FakeRequest(id=2, est_weight_kg=30.0), building=b, unit_code="A-102")
    c3 = FakeCandidate(request=FakeRequest(id=3, est_weight_kg=25.0), building=b, unit_code="A-103")

    sol = vrp_solver.solve([c1, c2, c3], capacity_kg=200.0, num_vehicles=2)
    assert len(sol.routes) == 1
    assert len(sol.routes[0]) == 3
    assert sol.unassigned == []
    assert sol.is_feasible is True


def test_u4_seven_candidates_split_capacity():
    """U4: 7 candidate, tải trọng xe 200 kg, tổng rác 500 kg -> trả về >= 2 tuyến, mỗi tuyến <= 200 kg."""
    weights = [80.0, 70.0, 75.0, 65.0, 70.0, 80.0, 60.0]  # total = 500 kg
    candidates = []
    for i, w in enumerate(weights):
        b = FakeBuilding(id=i + 1, code=f"TOA-{i + 1}", lat=21.0285 + i * 0.002, lng=105.8542 + i * 0.002)
        candidates.append(FakeCandidate(request=FakeRequest(id=i + 1, est_weight_kg=w), building=b, unit_code=f"U-{i}"))

    sol = vrp_solver.solve(candidates, capacity_kg=200.0, num_vehicles=3, max_runtime_seconds=2.0)
    assert sol.is_feasible is True
    assert len(sol.routes) >= 2
    for r in sol.routes:
        total_w = sum(c.weight_kg for c in r)
        assert total_w <= 200.0 + 1e-5, f"Route weight {total_w} exceeds capacity 200kg"

    # Tất cả 7 candidate đều được phục vụ
    all_served = [c for r in sol.routes for c in r]
    assert len(all_served) == 7


def test_u5_candidates_missing_coordinates():
    """U5: 10 candidate thiếu toạ độ -> solver vẫn chạy trơn tru với khoảng cách mặc định."""
    candidates = []
    for i in range(10):
        b = FakeBuilding(id=i + 1, code=f"TOA-{i + 1}", lat=None, lng=None)
        candidates.append(
            FakeCandidate(request=FakeRequest(id=i + 1, est_weight_kg=15.0), building=b, unit_code=f"U-{i}")
        )

    sol = vrp_solver.solve(candidates, capacity_kg=200.0, num_vehicles=2)
    assert sol.is_feasible is True
    assert len(sol.routes) >= 1
    all_served = [c for r in sol.routes for c in r]
    assert len(all_served) == 10


def test_u6_deterministic_seed():
    """U6: Chạy 5 lần cùng seed cố định -> 5 kết quả giống nhau."""
    weights = [40.0, 50.0, 30.0, 60.0, 45.0]
    candidates = []
    for i, w in enumerate(weights):
        b = FakeBuilding(id=i + 1, code=f"TOA-{i + 1}", lat=21.0285 + (i % 3) * 0.003, lng=105.8542 + (i // 3) * 0.003)
        candidates.append(FakeCandidate(request=FakeRequest(id=i + 1, est_weight_kg=w), building=b))

    results = []
    for _ in range(5):
        sol = vrp_solver.solve(candidates, capacity_kg=120.0, num_vehicles=3, seed=42, max_runtime_seconds=1.0)
        route_ids = [[c.request.id for c in r] for r in sol.routes]
        results.append(route_ids)

    for i in range(1, 5):
        assert results[i] == results[0], f"Run {i} differs from run 0: {results[i]} vs {results[0]}"


def test_u7_short_runtime_timeout():
    """U7: max_runtime_seconds=0.001 -> không treo, trả về kết quả hợp lệ."""
    candidates = []
    for i in range(5):
        b = FakeBuilding(id=i + 1, code=f"TOA-{i + 1}", lat=21.0285 + i * 0.001, lng=105.8542 + i * 0.001)
        candidates.append(FakeCandidate(request=FakeRequest(id=i + 1, est_weight_kg=20.0), building=b))

    sol = vrp_solver.solve(candidates, capacity_kg=200.0, max_runtime_seconds=0.001)
    assert isinstance(sol, vrp_solver.VRPSolution)
    assert len(sol.routes) >= 1


def test_u8_mixed_requests_and_bins():
    """U8: Trộn cả yêu cầu cư dân và thùng thông minh -> cả hai đều xuất hiện trong kết quả."""
    b = FakeBuilding(id=1, code="TOA-1", lat=21.0285, lng=105.8542)
    req1 = FakeCandidate(request=FakeRequest(id=1, est_weight_kg=30.0), building=b, unit_code="101")
    req2 = FakeCandidate(request=FakeRequest(id=2, est_weight_kg=40.0), building=b, unit_code="102")

    thung1 = FakeCandidate(
        thung=FakeBin(id=1, code="THUNG-01", lat=21.0290, lng=105.8550, capacity_liters=240.0, fill_percent=90.0)
    )
    thung2 = FakeCandidate(
        thung=FakeBin(id=2, code="THUNG-02", lat=21.0280, lng=105.8530, capacity_liters=120.0, fill_percent=85.0)
    )

    candidates = [req1, req2, thung1, thung2]
    sol = vrp_solver.solve(candidates, capacity_kg=200.0, num_vehicles=2)

    all_served = [c for r in sol.routes for c in r]
    assert len(all_served) == 4
    has_req = any(not c.la_thung for c in all_served)
    has_thung = any(c.la_thung for c in all_served)
    assert has_req and has_thung


def test_pyvrp_not_installed_fallback(monkeypatch: pytest.MonkeyPatch):
    """Fallback khi HAS_PYVRP=False."""
    monkeypatch.setattr(vrp_solver, "HAS_PYVRP", False)
    b = FakeBuilding(id=1, code="TOA-1", lat=21.0285, lng=105.8542)
    c = FakeCandidate(request=FakeRequest(id=1, est_weight_kg=30.0), building=b)

    sol = vrp_solver.solve([c])
    assert sol.is_feasible is False
    assert sol.algorithm == "fallback"
    assert sol.routes == []
    assert sol.unassigned == [c]


def test_solve_with_custom_distance_and_duration_fn():
    """Kiểm tra truyền distance_fn và duration_fn tuỳ biến."""
    b1 = FakeBuilding(id=1, code="TOA-1", lat=21.0285, lng=105.8542)
    b2 = FakeBuilding(id=2, code="TOA-2", lat=21.0295, lng=105.8552)
    b3 = FakeBuilding(id=3, code="TOA-3", lat=21.0305, lng=105.8562)

    c1 = FakeCandidate(request=FakeRequest(id=1, est_weight_kg=30.0), building=b1)
    c2 = FakeCandidate(request=FakeRequest(id=2, est_weight_kg=40.0), building=b2)
    c3 = FakeCandidate(request=FakeRequest(id=3, est_weight_kg=50.0), building=b3)

    called_duration = [0]

    def my_dist(a, b):
        return 1.5

    def my_duration(a, b):
        called_duration[0] += 1
        return 180.0

    sol = vrp_solver.solve(
        [c1, c2, c3],
        capacity_kg=200.0,
        distance_fn=my_dist,
        duration_fn=my_duration,
        max_runtime_seconds=0.5,
    )
    assert len(sol.routes) >= 1
    assert called_duration[0] > 0

