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

try:
    import pyvrp
    from pyvrp import Model, stop

    HAS_PYVRP = True
except ImportError:  # pragma: no cover
    pyvrp = None
    Model = None
    stop = None
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
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def _khoang_cach_mac_dinh(a: Any, b: Any) -> float:
    """Khoảng cách mặc định giữa hai ứng viên."""
    if not getattr(a, "diem_id", "") or not getattr(b, "diem_id", "") or a.diem_id == b.diem_id:
        return 0.0
    toa_do_a, toa_do_b = getattr(a, "toa_do", None), getattr(b, "toa_do", None)
    if toa_do_a is None or toa_do_b is None:
        return 0.3
    return haversine_km(toa_do_a[0], toa_do_a[1], toa_do_b[0], toa_do_b[1])


def solve(
    candidates: list[Any],
    *,
    capacity_kg: float = 200.0,
    num_vehicles: int = 3,
    max_runtime_seconds: float = 5.0,
    depot_lat: float = 21.0285,
    depot_lng: float = 105.854,
    seed: int = 42,
    distance_fn: Callable[[Any, Any], float] | None = None,
    duration_fn: Callable[[Any, Any], float] | None = None,
) -> VRPSolution:
    """Giải bài toán gom tuyến và sắp thứ tự bằng PyVRP.

    Args:
        candidates: Danh sách Candidate cần phục vụ.
        capacity_kg: Tải trọng tối đa của mỗi xe (kg).
        num_vehicles: Số xe khả dụng tối đa.
        max_runtime_seconds: Thời gian tối đa cho solver (giây).
        depot_lat: Vĩ độ khu tập kết (depot).
        depot_lng: Kinh độ khu tập kết (depot).
        seed: Random seed đảm bảo kết quả deterministic.
        distance_fn: Hàm tính khoảng cách tuỳ biến giữa 2 candidate (km).
        duration_fn: Hàm tính thời gian di chuyển tuỳ biến giữa 2 candidate (giây).

    Returns:
        VRPSolution chứa danh sách các tuyến và các candidate bị loại.
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

    # Lọc các ứng viên đơn lẻ tự thân đã vượt quá tải trọng xe
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

    if len(valid_candidates) == 1:
        return VRPSolution(
            routes=[valid_candidates],
            unassigned=unassigned,
            is_feasible=True,
            runtime_seconds=0.0,
        )

    calc_dist = distance_fn or _khoang_cach_mac_dinh

    try:
        model = Model()
        depot = model.add_depot(x=0.0, y=0.0)

        scale = 100  # 0.01 kg
        scaled_capacity = int(round(capacity_kg * scale))

        client_objs = []
        for i, c in enumerate(valid_candidates):
            weight = getattr(c, "weight_kg", 0.0)
            demand = max(0, int(round(weight * scale)))
            prize = demand * 1000 + 1_000_000
            client_obj = model.add_client(
                x=float(i + 1),
                y=float(i + 1),
                delivery=[demand],
                required=False,
                prize=prize,
            )
            client_objs.append(client_obj)

        all_locs = [depot] + client_objs
        n_locs = len(all_locs)

        for u_idx in range(n_locs):
            for v_idx in range(n_locs):
                u = all_locs[u_idx]
                v = all_locs[v_idx]

                if u_idx == v_idx:
                    model.add_edge(u, v, distance=0, duration=0)
                elif u_idx == 0 and v_idx > 0:
                    cand = valid_candidates[v_idx - 1]
                    toa_do = getattr(cand, "toa_do", None)
                    if toa_do is not None:
                        d_km = haversine_km(depot_lat, depot_lng, toa_do[0], toa_do[1])
                    else:
                        d_km = 0.6
                    dist_meters = max(1, int(round(d_km * 1000)))
                    dur_seconds = max(1, int(round((d_km * 1000.0) / (30.0 / 3.6))))
                    model.add_edge(u, v, distance=dist_meters, duration=dur_seconds)
                elif u_idx > 0 and v_idx == 0:
                    cand = valid_candidates[u_idx - 1]
                    toa_do = getattr(cand, "toa_do", None)
                    if toa_do is not None:
                        d_km = haversine_km(depot_lat, depot_lng, toa_do[0], toa_do[1])
                    else:
                        d_km = 0.6
                    dist_meters = max(1, int(round(d_km * 1000)))
                    dur_seconds = max(1, int(round((d_km * 1000.0) / (30.0 / 3.6))))
                    model.add_edge(u, v, distance=dist_meters, duration=dur_seconds)
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
                    model.add_edge(u, v, distance=dist_meters, duration=dur_s)

        model.add_vehicle_type(
            num_available=max(1, num_vehicles),
            capacity=[scaled_capacity],
            fixed_cost=50_000,
        )


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
