"""Module giải bài toán VRP (Vehicle Routing Problem) bằng PyVRP.

Giải quyết đồng thời bài toán gom nhóm (clustering) và tối ưu thứ tự ghé (routing)
bằng thuật toán Hybrid Genetic Search (HGS).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:
    import pyvrp
    from pyvrp import Client, Depot, Model, ProblemData, VehicleType, stop

    HAS_PYVRP = True
except ImportError:  # pragma: no cover
    pyvrp = None
    Model = None
    stop = None
    ProblemData = None
    Client = None
    Depot = None
    VehicleType = None
    HAS_PYVRP = False


@dataclass
class VRPSolution:
    """Kết quả giải bài toán VRP."""

    routes: list[list[Any]] = field(default_factory=list)
    unassigned: list[Any] = field(default_factory=list)
    is_feasible: bool = True
    runtime_seconds: float = 0.0
    algorithm: str = "pyvrp"
    note: str = ""


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Khoảng cách đường chim bay giữa hai điểm, tính bằng km."""
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def _khoang_cach_mac_dinh(c1: Any, c2: Any) -> float:
    """Khoảng cách đường chim bay giữa 2 candidate, nếu thiếu toạ độ trả về 0.6 km."""
    t1 = getattr(c1, "toa_do", None)
    t2 = getattr(c2, "toa_do", None)
    if t1 is not None and t2 is not None:
        return haversine_km(t1[0], t1[1], t2[0], t2[1])
    return 0.6


def solve(
    candidates: list[Any],
    capacity_kg: float = 200.0,
    num_vehicles: int = 1,
    max_runtime_seconds: float = 1.0,
    distance_fn: Callable[[Any, Any], float] | None = None,
    duration_fn: Callable[[Any, Any], float | None] | None = None,
    depot_lat: float = 21.0285,
    depot_lng: float = 105.8542,
    seed: int = 42,
) -> VRPSolution:
    """Giải bài toán gom tuyến và sắp thứ tự bằng PyVRP.

    Args:
        candidates: Danh sách ứng viên (Candidate/PickupStop/ThungRac/YeuCauThuGom).
        capacity_kg: Tải trọng tối đa mỗi xe (kg).
        num_vehicles: Số xe tối đa được phép dùng.
        max_runtime_seconds: Thời gian chạy tối đa của solver (giây).
        distance_fn: Hàm tính khoảng cách (km) giữa 2 candidate. Mặc định: haversine.
        duration_fn: Hàm tính thời gian (giây) giữa 2 candidate. Mặc định: ước tính theo v=30km/h.
        depot_lat: Vĩ độ điểm xuất phát (depot/bãi tập kết).
        depot_lng: Kinh độ điểm xuất phát (depot/bãi tập kết).
        seed: Random seed cho solver để kết quả có tính lặp lại (reproducible).

    Returns:
        VRPSolution chứa danh sách các tuyến (mỗi tuyến là 1 list candidates theo thứ tự ghé).
    """
    if not HAS_PYVRP:
        return VRPSolution(
            routes=[],
            unassigned=list(candidates),
            is_feasible=False,
            runtime_seconds=0.0,
            algorithm="fallback",
            note="PyVRP is not installed",
        )

    if not candidates:
        return VRPSolution(routes=[], unassigned=[], is_feasible=True, runtime_seconds=0.0)

    valid_candidates: list[Any] = []
    unassigned: list[Any] = []
    for c in candidates:
        weight = getattr(c, "weight_kg", 0.0)
        if weight > capacity_kg:
            unassigned.append(c)
        else:
            valid_candidates.append(c)

    if not valid_candidates:
        return VRPSolution(
            routes=[],
            unassigned=unassigned,
            is_feasible=False,
            runtime_seconds=0.0,
            note="Tất cả ứng viên đều vượt tải trọng xe",
        )

    calc_dist = distance_fn or _khoang_cach_mac_dinh

    try:
        scale = 100  # 0.01 kg
        scaled_capacity = int(round(capacity_kg * scale))
        n_clients = len(valid_candidates)
        n_locs = n_clients + 1

        dist_matrix = np.zeros((n_locs, n_locs), dtype=np.int64)
        dur_matrix = np.zeros((n_locs, n_locs), dtype=np.int64)

        for u_idx in range(n_locs):
            for v_idx in range(n_locs):
                if u_idx == v_idx:
                    continue
                elif u_idx == 0 and v_idx > 0:
                    cand = valid_candidates[v_idx - 1]
                    toa_do = getattr(cand, "toa_do", None)
                    if toa_do is not None:
                        d_km = haversine_km(depot_lat, depot_lng, toa_do[0], toa_do[1])
                    else:
                        d_km = 0.6
                    dist_meters = max(1, int(round(d_km * 1000)))
                    dur_seconds = max(1, int(round((d_km * 1000.0) / (30.0 / 3.6))))
                    dist_matrix[u_idx, v_idx] = dist_meters
                    dur_matrix[u_idx, v_idx] = dur_seconds
                elif u_idx > 0 and v_idx == 0:
                    cand = valid_candidates[u_idx - 1]
                    toa_do = getattr(cand, "toa_do", None)
                    if toa_do is not None:
                        d_km = haversine_km(depot_lat, depot_lng, toa_do[0], toa_do[1])
                    else:
                        d_km = 0.6
                    dist_meters = max(1, int(round(d_km * 1000)))
                    dur_seconds = max(1, int(round((d_km * 1000.0) / (30.0 / 3.6))))
                    dist_matrix[u_idx, v_idx] = dist_meters
                    dur_matrix[u_idx, v_idx] = dur_seconds
                else:
                    cand_u = valid_candidates[u_idx - 1]
                    cand_v = valid_candidates[v_idx - 1]
                    d_km = calc_dist(cand_u, cand_v)
                    dist_meters = int(round(d_km * 1000))
                    dur_s = None
                    if duration_fn is not None:
                        dur_val = duration_fn(cand_u, cand_v)
                        if dur_val is not None:
                            dur_s = int(round(dur_val))
                    if dur_s is None:
                        dur_s = int(round((d_km * 1000.0) / (30.0 / 3.6)))
                    dist_matrix[u_idx, v_idx] = dist_meters
                    dur_matrix[u_idx, v_idx] = dur_s

        clients = []
        for i, c in enumerate(valid_candidates):
            weight = getattr(c, "weight_kg", 0.0)
            demand = max(0, int(round(weight * scale)))
            prize = demand * 1000 + 1_000_000
            client = Client(
                float(i + 1),
                float(i + 1),
                delivery=[demand],
                required=False,
                prize=prize,
            )
            clients.append(client)

        depot = Depot(0.0, 0.0)
        vehicle_type = VehicleType(
            num_available=max(1, num_vehicles),
            capacity=[scaled_capacity],
            fixed_cost=50_000,
        )

        data = ProblemData(
            clients=clients,
            depots=[depot],
            vehicle_types=[vehicle_type],
            distance_matrices=[dist_matrix],
            duration_matrices=[dur_matrix],
        )

        model = Model.from_data(data)

        t0 = time.perf_counter()
        stop_criterion = stop.MaxRuntime(max(0.001, max_runtime_seconds))
        res = model.solve(stop=stop_criterion, seed=seed, display=False)
        runtime = time.perf_counter() - t0

        routes: list[list[Any]] = []
        served_indices: set[int] = set()

        if res.best is not None:
            for r in res.best.routes():
                visits = r.visits()
                if visits:
                    route_cands = [valid_candidates[idx - 1] for idx in visits]
                    routes.append(route_cands)
                    served_indices.update(visits)

        for i in range(1, len(valid_candidates) + 1):
            if i not in served_indices:
                unassigned.append(valid_candidates[i - 1])

        is_feasible = res.is_feasible() if res.best is not None else False
        return VRPSolution(
            routes=routes,
            unassigned=unassigned,
            is_feasible=is_feasible,
            runtime_seconds=round(runtime, 4),
            algorithm="pyvrp",
        )

    except Exception as exc:  # pragma: no cover
        return VRPSolution(
            routes=[],
            unassigned=list(candidates),
            is_feasible=False,
            runtime_seconds=0.0,
            algorithm="fallback",
            note=str(exc),
        )
