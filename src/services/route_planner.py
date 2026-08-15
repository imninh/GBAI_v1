"""Gộp yêu cầu thu gom thành tuyến — HITL #3.

Nguyên tắc bất di bất dịch: **agent không được tự đổi lịch làm việc của con
người.** Tuyến do agent gộp luôn ở trạng thái ``proposed`` cho tới khi đội
trưởng bấm duyệt.

Cách gộp (P0, cố ý không dùng VRP đầy đủ — xem CLAUDE.md mục 3): nhóm theo
**cùng ngày + cùng khung giờ + cụm toà gần nhau**, giới hạn bởi tải trọng xe.
Kèm theo tuyến là khối "vì sao gộp thế này" liệt kê tiêu chí, các yêu cầu bị
loại và lý do, cùng phần tiết kiệm so với đi lẻ. Khối đó quan trọng bằng chính
cái tuyến: người duyệt phải hiểu logic mới dám duyệt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import (
    STOP_KIND_THUNG,
    STOP_KIND_YEU_CAU,
    Bin,
    Building,
    Notification,
    PickupEvent,
    PickupRequest,
    PickupRoute,
    RouteStop,
    Unit,
    User,
)
from src.db.models_base import utcnow
from src.services import bins, duong_di_that, vrp_solver
from src.services.auth import write_audit
from src.services.pickup_lifecycle import (
    CHO_NHAN,
    DA_NHAN,
    HOAN_TAT,
    chuan_hoa,
    trang_thai_tuong_duong,
)
from src.services.toi_uu_tuyen import sap_thu_tu

# Hai toà cách nhau dưới ngưỡng này thì coi là cùng cụm, gộp được một chuyến.
CLUSTER_RADIUS_KM = 0.8

# Ước lượng khối lượng rác tái chế rời trong thùng: ~0,08 kg mỗi lít (rác tái
# chế cồng kềnh nhưng nhẹ). CHỈ dùng để xếp tải trọng chuyến xe.
#
# **Không bao giờ** dùng con số này để tính điểm hay thanh toán: chỗ đó chỉ
# nhận khối lượng cân thật (``weight_confirmed_kg``), đúng nguyên tắc "hệ thống
# không trao điểm dựa trên ước lượng của máy".
KG_MOI_LIT_RAC_TAI_CHE = 0.08

STOP_ISSUES: list[dict[str, str]] = [
    {"code": "khong_co_nguoi", "label_vi": "Không có người"},
    {"code": "khoi_luong_khac", "label_vi": "Khối lượng khác dự kiến"},
    {"code": "co_rac_nguy_hai", "label_vi": "Có rác nguy hại lẫn vào"},
    {"code": "khong_tiep_can", "label_vi": "Không tiếp cận được"},
    {"code": "khac", "label_vi": "Khác"},
]
STOP_ISSUE_CODES = {i["code"] for i in STOP_ISSUES}


@dataclass
class Candidate:
    """Một điểm dừng đang chờ xếp tuyến: yêu cầu của cư dân, HOẶC một thùng đầy.

    Đúng một trong hai ``request`` / ``thung`` được điền. Ba thuộc tính
    ``diem_id`` / ``toa_do`` / ``nhan_nhom`` là **mặt tiếp xúc duy nhất** mà
    phần tính khoảng cách được phép dùng, nên thuật toán gộp không cần biết
    điểm dừng thuộc loại nào.
    """

    request: PickupRequest | None
    building: Building | None
    unit_code: str
    thung: Bin | None = None

    @property
    def la_thung(self) -> bool:
        """Điểm dừng này là một thùng, không phải một yêu cầu của cư dân."""
        return self.thung is not None

    @property
    def weight_kg(self) -> float:
        """Khối lượng dùng để xếp tải trọng xe.

        Yêu cầu của cư dân lấy cận TRÊN của khoảng — thà xe còn chỗ trống còn
        hơn quá tải. Thùng thì **ước lượng** từ thể tích và mức đầy, vì không ai
        cân thùng trước khi xe tới.
        """
        if self.thung is not None:
            return self.thung.capacity_liters * (self.thung.fill_percent / 100.0) * KG_MOI_LIT_RAC_TAI_CHE
        if self.request is None:
            return 0.0
        return self.request.weight_max_kg or self.request.est_weight_kg

    @property
    def diem_id(self) -> str:
        """Định danh CHỖ ĐỨNG. Rỗng nghĩa là chưa gắn với chỗ nào trên bản đồ."""
        if self.thung is not None:
            return f"thung:{self.thung.id}"
        return f"toa:{self.building.id}" if self.building is not None else ""

    @property
    def toa_do(self) -> tuple[float, float] | None:
        """``(lat, lng)`` của chỗ đứng, hoặc ``None`` khi chưa có toạ độ."""
        nguon = self.thung if self.thung is not None else self.building
        if nguon is None or nguon.lat is None or nguon.lng is None:
            return None
        return (nguon.lat, nguon.lng)

    @property
    def nhan_nhom(self) -> str:
        """Nhãn ngắn của chỗ đứng, dùng để sắp thứ tự và để giải thích tuyến."""
        if self.thung is not None:
            return self.thung.code
        return self.building.code if self.building is not None else ""


def _so(value: float) -> str:
    """Định dạng số theo quy ước tiếng Việt: dấu phẩy là dấu thập phân."""
    text = f"{value:g}"
    return text.replace(".", ",")


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


def _khoang_cach(a: Candidate, b: Candidate) -> float:
    """Khoảng cách giữa hai điểm dừng, km. Giữ **nguyên văn** ba ca của bản cũ.

    Ba ca đó không phải ngẫu nhiên, đừng rút gọn:

    * chưa gắn chỗ đứng, hoặc cùng một chỗ đứng → ``0.0`` (xe không phải đi đâu);
    * hai chỗ khác nhau nhưng thiếu toạ độ → ``0.3`` km ước lượng tối thiểu,
      thà đoán thấp còn hơn để một điểm chưa có toạ độ đá mọi điểm khác ra
      khỏi cụm;
    * đủ toạ độ → đường chim bay thật.
    """
    if not a.diem_id or not b.diem_id or a.diem_id == b.diem_id:
        return 0.0
    toa_do_a, toa_do_b = a.toa_do, b.toa_do
    if toa_do_a is None or toa_do_b is None:
        return 0.3
    return haversine_km(toa_do_a[0], toa_do_a[1], toa_do_b[0], toa_do_b[1])


def yeu_cau_cua(session: Session, stop: RouteStop) -> PickupRequest | None:
    """Yêu cầu đứng sau một điểm dừng, hoặc ``None`` nếu đó là điểm dừng loại thùng.

    ``session.get(Model, None)`` **ném lỗi** chứ không trả ``None``, nên mọi chỗ
    tra yêu cầu từ điểm dừng đều phải đi qua đây kể từ khi tuyến gộp cả thùng.
    """
    if not stop.request_id:
        return None
    return session.get(PickupRequest, stop.request_id)


def estimate_route_km(candidates: list[Candidate]) -> float:
    """Quãng đường ước tính của tuyến: đi qua các toà theo thứ tự, rồi quay về.

    Đây là **ước lượng đường chim bay**, không phải quãng đường thực tế theo
    đường đi. Con số hiển thị trên UI ghi rõ là ước tính.
    """
    if not candidates:
        return 0.0
    total = 0.0
    for previous, current in zip(candidates, candidates[1:], strict=False):
        total += _khoang_cach(previous, current)
    # Chặng đi và chặng về từ khu tập kết: cộng một lượng cố định nhỏ.
    return round(total + 1.2, 2)


def _load_candidates(session: Session, service_date: date, window: str) -> tuple[list[Candidate], list[Candidate]]:
    """Trả về ``(hợp lệ, bị loại)`` cho một ngày và khung giờ.

    Ứng viên nay đến từ hai nguồn: yêu cầu thu gom đã duyệt (lọc theo ngày và
    khung giờ) và thùng thông minh đang ở trạng thái ``can_gom`` — thùng đầy
    không có lịch hẹn nên không bao giờ bị lọc theo ngày.

    Bị loại = đã duyệt, chờ xếp tuyến, nhưng lệch ngày hoặc lệch khung giờ.
    Danh sách này lên thẳng khối "vì sao gộp thế này" — người duyệt cần thấy
    agent đã cân nhắc gì rồi mới bỏ ra.
    """
    rows = session.execute(
        select(PickupRequest, Unit, Building)
        .join(Unit, PickupRequest.unit_id == Unit.id)
        .join(Building, Unit.building_id == Building.id)
        .where(PickupRequest.status.in_(trang_thai_tuong_duong(CHO_NHAN)))
        .order_by(PickupRequest.created_at)
    ).all()

    matched: list[Candidate] = []
    excluded: list[Candidate] = []
    for request, unit, building in rows:
        candidate = Candidate(request=request, building=building, unit_code=unit.code)
        if request.preferred_date == service_date and (not window or request.preferred_window == window):
            matched.append(candidate)
        else:
            excluded.append(candidate)

    # Thùng đầy KHÔNG có lịch hẹn nào để lọc theo ngày/khung giờ: đầy là phải
    # đi gom. Nối vào SAU danh sách yêu cầu để cụm vẫn neo vào toà của yêu cầu
    # đầu tiên y như trước — nhờ vậy mọi tuyến cũ ra kết quả không đổi khi
    # không có thùng nào đang đầy.
    for thung in bins.thung_can_gom(session, utcnow()):
        matched.append(Candidate(request=None, building=None, unit_code="", thung=thung))

    return matched, excluded


def _ma_ung_vien(candidate: Candidate) -> str:
    """Mã hiển thị của một ứng viên trong khối "vì sao gộp thế này"."""
    if candidate.thung is not None:
        return f"thung {candidate.thung.code}"
    return str(candidate.request.id) if candidate.request is not None else "?"


def _propose_routes_legacy(
    session: Session,
    matched: list[Candidate],
    excluded: list[Candidate],
    *,
    service_date: date,
    window: str,
    team_id: int | None = None,
    capacity: float,
    run_id: int | None = None,
    settings: Any,
) -> list[PickupRoute]:
    """Thuật toán gom cụm greedy + nearest-neighbour + 2-opt truyền thống."""
    neo = matched[0]
    selected: list[Candidate] = []
    over_capacity: list[Candidate] = []
    too_far: list[Candidate] = []
    total_weight = 0.0

    for candidate in matched:
        if _khoang_cach(neo, candidate) > CLUSTER_RADIUS_KM:
            too_far.append(candidate)
            continue
        if total_weight + candidate.weight_kg > capacity:
            over_capacity.append(candidate)
            continue
        selected.append(candidate)
        total_weight += candidate.weight_kg

    if not selected:  # tất cả đều quá tải — vẫn xếp yêu cầu đầu để người duyệt xử lý
        selected = [matched[0]]
        over_capacity = [c for c in matched[1:]]
        total_weight = selected[0].weight_kg

    chi_so: dict[str, int] = {}
    toa_do: list[tuple[float, float]] = []
    for candidate in selected:
        if candidate.toa_do is not None:
            chi_so[candidate.diem_id] = len(toa_do)
            toa_do.append(candidate.toa_do)
    ma_tran = duong_di_that.ma_tran_km(toa_do)
    dung_duong_di_that = ma_tran is not None
    if ma_tran is not None:
        do_that = duong_di_that.ham_do_tu_ma_tran(ma_tran, chi_so)

        def _do_moi(a: Candidate, b: Candidate) -> float:
            khoang = do_that(a, b)
            return _khoang_cach(a, b) if khoang is None else khoang

        selected = sap_thu_tu(selected, _do_moi)
    else:
        selected = sap_thu_tu(selected, _khoang_cach)

    est_km = estimate_route_km(selected)
    baseline_km = round(len(selected) * settings.baseline_km_per_standalone_trip, 2)
    building_names = sorted({c.nhan_nhom for c in selected if c.nhan_nhom})

    criteria = [
        f"Cùng ngày {service_date.strftime('%d/%m/%Y')}" + (f" và khung giờ {window}" if window else ""),
        f"Cùng cụm toà {', '.join(building_names)} (bán kính {_so(CLUSTER_RADIUS_KM)} km)",
        f"Tổng {total_weight:.0f} kg — trong tải trọng {capacity:.0f} kg của xe",
        f"{sum(1 for c in selected if c.la_thung)} thùng đang đầy + "
        f"{sum(1 for c in selected if not c.la_thung)} yêu cầu của cư dân — gộp chung một chuyến",
        "Thứ tự ghé tối ưu bằng nearest-neighbour + 2-opt trên "
        + ("khoảng cách đường đi thật lấy từ OSRM" if dung_duong_di_that else "khoảng cách đường chim bay"),
    ]

    excluded_notes: list[dict[str, str]] = []
    for candidate in excluded:
        ly_do = []
        if candidate.request.preferred_date != service_date:
            ly_do.append(f"lệch ngày ({candidate.request.preferred_date})")
        elif candidate.request.preferred_window != window:
            ly_do.append(f"lệch khung giờ ({candidate.request.preferred_window})")
        excluded_notes.append(
            {
                "request_id": _ma_ung_vien(candidate),
                "unit": candidate.unit_code,
                "ly_do": " · ".join(ly_do) or "không khớp điều kiện",
            }
        )
    for candidate in too_far:
        excluded_notes.append(
            {
                "request_id": _ma_ung_vien(candidate),
                "unit": candidate.unit_code,
                "ly_do": f"toà {candidate.nhan_nhom or '?'} nằm ngoài cụm",
            }
        )
    for candidate in over_capacity:
        excluded_notes.append(
            {
                "request_id": _ma_ung_vien(candidate),
                "unit": candidate.unit_code,
                "ly_do": f"vượt tải trọng còn lại của xe ({_so(capacity)} kg)",
            }
        )

    route = PickupRoute(
        service_date=service_date,
        window=window,
        team_id=team_id,
        status="proposed",
        total_weight_kg=round(total_weight, 1),
        est_distance_km=est_km,
        run_id=run_id,
        reasoning={
            "criteria": criteria,
            "excluded": excluded_notes,
            "baseline_km": baseline_km,
            "saved_km": round(max(0.0, baseline_km - est_km), 2),
            "saved_trips": max(0, len(selected) - 1),
            "capacity_kg": capacity,
            "note": "Quãng đường là ước tính theo đường chim bay giữa các toà, không phải quãng đường thực tế.",
        },
        # Chỉ điểm dừng loại yêu cầu vào đây: `route_diff` so bản AI đề xuất với
        # bản người duyệt sửa bằng danh sách request_id, và thùng không nằm
        # trong phép so đó.
        proposed_stop_order=[c.request.id for c in selected if c.request is not None],
    )
    session.add(route)
    session.flush()

    for index, candidate in enumerate(selected, start=1):
        if candidate.thung is not None:
            session.add(
                RouteStop(
                    route_id=route.id,
                    stop_kind=STOP_KIND_THUNG,
                    bin_id=candidate.thung.id,
                    seq=index,
                )
            )
        else:
            session.add(
                RouteStop(
                    route_id=route.id,
                    stop_kind=STOP_KIND_YEU_CAU,
                    request_id=candidate.request.id,
                    seq=index,
                )
            )
    session.flush()
    return [route]


def propose_routes(
    session: Session,
    *,
    service_date: date,
    window: str,
    team_id: int | None = None,
    capacity_kg: float | None = None,
    run_id: int | None = None,
) -> list[PickupRoute]:
    """Agent đề xuất danh sách tuyến gộp. Kết quả luôn ở trạng thái ``proposed``.

    Nếu ``settings.vrp_enabled`` bật, giải bài toán VRP đồng thời cho toàn bộ
    ứng viên bằng PyVRP (HGS). Nếu tắt hoặc PyVRP không khả dụng/kết quả rỗng,
    rơi êm về thuật toán greedy + NN + 2-opt.

    Raises:
        ValueError: khi không có yêu cầu nào đã duyệt cho ngày/khung giờ đó.
    """
    settings = get_settings()
    capacity = capacity_kg or settings.vehicle_capacity_kg
    matched, excluded = _load_candidates(session, service_date, window)
    if not matched:
        raise ValueError("Không có yêu cầu nào đã duyệt và không có thùng nào cần gom cho ngày và khung giờ này")

    if not settings.vrp_enabled:
        return _propose_routes_legacy(
            session,
            matched,
            excluded,
            service_date=service_date,
            window=window,
            team_id=team_id,
            capacity=capacity,
            run_id=run_id,
            settings=settings,
        )

    # Khi bật PyVRP: chuẩn bị ma trận khoảng cách
    chi_so: dict[str, int] = {}
    toa_do: list[tuple[float, float]] = []
    for candidate in matched:
        if candidate.toa_do is not None:
            chi_so[candidate.diem_id] = len(toa_do)
            toa_do.append(candidate.toa_do)
    ma_tran = duong_di_that.ma_tran_km(toa_do) if toa_do else None
    dung_duong_di_that = ma_tran is not None

    if ma_tran is not None:
        do_that = duong_di_that.ham_do_tu_ma_tran(ma_tran, chi_so)

        def _do_moi(a: Candidate, b: Candidate) -> float:
            khoang = do_that(a, b)
            return _khoang_cach(a, b) if khoang is None else khoang

        dist_fn = _do_moi
    else:
        dist_fn = _khoang_cach

    try:
        sol = vrp_solver.solve(
            matched,
            capacity_kg=capacity,
            num_vehicles=settings.vrp_num_vehicles,
            max_runtime_seconds=settings.vrp_max_runtime_seconds,
            depot_lat=settings.vrp_depot_lat,
            depot_lng=settings.vrp_depot_lng,
            distance_fn=dist_fn,
        )
    except Exception:
        sol = None

    if sol is None or not sol.routes:
        return _propose_routes_legacy(
            session,
            matched,
            excluded,
            service_date=service_date,
            window=window,
            team_id=team_id,
            capacity=capacity,
            run_id=run_id,
            settings=settings,
        )

    created_routes: list[PickupRoute] = []
    for selected in sol.routes:
        total_weight = sum(c.weight_kg for c in selected)
        est_km = estimate_route_km(selected)
        baseline_km = round(len(selected) * settings.baseline_km_per_standalone_trip, 2)
        building_names = sorted({c.nhan_nhom for c in selected if c.nhan_nhom})

        criteria = [
            f"Cùng ngày {service_date.strftime('%d/%m/%Y')}" + (f" và khung giờ {window}" if window else ""),
            f"Cùng cụm toà {', '.join(building_names)}" if building_names else "Cùng cụm toà",
            f"Tổng {total_weight:.0f} kg — trong tải trọng {capacity:.0f} kg của xe",
            f"{sum(1 for c in selected if c.la_thung)} thùng đang đầy + "
            f"{sum(1 for c in selected if not c.la_thung)} yêu cầu của cư dân — gộp chung một chuyến",
            "Tối ưu bằng PyVRP (Hybrid Genetic Search) trên ma trận N×N "
            + ("khoảng cách đường đi thật lấy từ OSRM" if dung_duong_di_that else "khoảng cách đường chim bay"),
        ]

        excluded_notes: list[dict[str, str]] = []
        for candidate in excluded:
            ly_do = []
            if candidate.request.preferred_date != service_date:
                ly_do.append(f"lệch ngày ({candidate.request.preferred_date})")
            elif candidate.request.preferred_window != window:
                ly_do.append(f"lệch khung giờ ({candidate.request.preferred_window})")
            excluded_notes.append(
                {
                    "request_id": _ma_ung_vien(candidate),
                    "unit": candidate.unit_code,
                    "ly_do": " · ".join(ly_do) or "không khớp điều kiện",
                }
            )
        for candidate in sol.unassigned:
            excluded_notes.append(
                {
                    "request_id": _ma_ung_vien(candidate),
                    "unit": candidate.unit_code,
                    "ly_do": "vượt tải trọng hoặc ngoài khả năng phục vụ của đội xe",
                }
            )

        route = PickupRoute(
            service_date=service_date,
            window=window,
            team_id=team_id,
            status="proposed",
            total_weight_kg=round(total_weight, 1),
            est_distance_km=est_km,
            run_id=run_id,
            reasoning={
                "criteria": criteria,
                "excluded": excluded_notes,
                "baseline_km": baseline_km,
                "saved_km": round(max(0.0, baseline_km - est_km), 2),
                "saved_trips": max(0, len(selected) - 1),
                "capacity_kg": capacity,
                "vrp_runtime_seconds": sol.runtime_seconds,
                "note": "Quãng đường là ước tính theo đường chim bay giữa các toà, không phải quãng đường thực tế.",
            },
            proposed_stop_order=[c.request.id for c in selected if c.request is not None],
        )
        session.add(route)
        session.flush()

        for index, candidate in enumerate(selected, start=1):
            if candidate.thung is not None:
                session.add(
                    RouteStop(
                        route_id=route.id,
                        stop_kind=STOP_KIND_THUNG,
                        bin_id=candidate.thung.id,
                        seq=index,
                    )
                )
            else:
                session.add(
                    RouteStop(
                        route_id=route.id,
                        stop_kind=STOP_KIND_YEU_CAU,
                        request_id=candidate.request.id,
                        seq=index,
                    )
                )
        session.flush()
        created_routes.append(route)

    return created_routes


def propose_route(
    session: Session,
    *,
    service_date: date,
    window: str,
    team_id: int | None = None,
    capacity_kg: float | None = None,
    run_id: int | None = None,
) -> PickupRoute:
    """Agent đề xuất một tuyến gộp. Kết quả luôn ở trạng thái ``proposed``.

    Gọi ``propose_routes`` và trả về tuyến đầu tiên để giữ tương thích ngược.

    Raises:
        ValueError: khi không có yêu cầu nào đã duyệt cho ngày/khung giờ đó.
    """
    routes = propose_routes(
        session,
        service_date=service_date,
        window=window,
        team_id=team_id,
        capacity_kg=capacity_kg,
        run_id=run_id,
    )
    return routes[0]


def review_route(
    session: Session,
    *,
    route: PickupRoute,
    actor: User,
    action: str,
    stop_order: list[int] | None = None,
    removed_stops: list[int] | None = None,
) -> PickupRoute:
    """HITL #3 — đội trưởng duyệt / sửa rồi duyệt / đề xuất lại / huỷ tuyến.

    Args:
        action: ``approve`` · ``approve_with_changes`` · ``cancel``.
            ``regenerate`` do lớp API xử lý vì nó tạo tuyến mới.
        stop_order: danh sách **``RouteStop.id``** theo thứ tự người duyệt sắp lại.
        removed_stops: các **``RouteStop.id``** bị bỏ khỏi tuyến. Điểm dừng loại
            yêu cầu thì yêu cầu quay về nhóm chờ xếp; điểm dừng loại thùng thì
            chỉ rời tuyến, thùng vẫn đầy và sẽ được gộp lại ở lần đề xuất sau.

    Raises:
        ValueError: khi hành động không hợp lệ hoặc tuyến đã chốt.
    """
    if action not in {"approve", "approve_with_changes", "cancel"}:
        raise ValueError(f"Hành động không hợp lệ: {action}")
    if route.status not in {"proposed", "approved"}:
        raise ValueError(f"Tuyến đang ở trạng thái '{route.status}', không duyệt lại được")

    if action == "cancel":
        for stop in route.stops:
            request = yeu_cau_cua(session, stop)
            if request is not None and chuan_hoa(request.status) == DA_NHAN:
                request.status = CHO_NHAN
        route.status = "cancelled"
        session.flush()
        return route

    if action == "approve_with_changes":
        # Khớp theo KHOÁ CHÍNH của điểm dừng, không phải `request_id`: điểm dừng
        # loại `thung` có `request_id = NULL` nên khớp kiểu cũ thì không bao giờ
        # bỏ được thùng khỏi tuyến — mà từ gói B3b thì tuyến trộn cả hai loại.
        removed = set(removed_stops or [])
        for stop in list(route.stops):
            if stop.id in removed:
                request = yeu_cau_cua(session, stop)
                if request is not None:
                    request.status = CHO_NHAN
                    session.add(
                        PickupEvent(
                            request_id=request.id,
                            kind="routed",
                            label_vi="Bị bỏ khỏi tuyến khi ban quản lý duyệt — chờ xếp chuyến khác",
                            actor_id=actor.id,
                        )
                    )
                # Gỡ khỏi quan hệ để collection trong bộ nhớ khớp với CSDL ngay;
                # cascade delete-orphan lo phần xoá bản ghi.
                route.stops.remove(stop)
        session.flush()

        if stop_order:
            position = {stop_id: index for index, stop_id in enumerate(stop_order, start=1)}
            for stop in route.stops:
                stop.seq = position.get(stop.id, stop.seq)
        session.flush()
        _recalculate_totals(session, route)

    route.status = "approved"
    route.approved_by = actor.id
    route.approved_at = datetime.now()
    session.flush()

    for stop in sorted(route.stops, key=lambda s: s.seq):
        request = yeu_cau_cua(session, stop)
        if request is None:
            continue
        request.status = DA_NHAN
        session.add(
            PickupEvent(
                request_id=request.id,
                kind="routed",
                label_vi=(
                    f"Đã xếp vào chuyến {route.window or ''} ngày "
                    f"{route.service_date.strftime('%d/%m')} cùng {len(route.stops) - 1} hộ khác"
                ).strip(),
                actor_id=actor.id,
                detail={"route_id": route.id, "seq": stop.seq},
            )
        )
        session.add(
            Notification(
                user_id=request.resident_id,
                title="Yêu cầu của bạn đã được xếp lịch thu gom",
                body=(
                    f"Chuyến {route.window} ngày {route.service_date.strftime('%d/%m/%Y')}. "
                    f"Đi cùng chuyến với {max(0, len(route.stops) - 1)} hộ khác trong toà — giảm "
                    f"{route.reasoning.get('saved_trips', 0)} chuyến xe."
                ),
                entity="pickup_route",
                entity_id=str(route.id),
            )
        )
    if route.team_id:
        session.add(
            Notification(
                user_id=route.team_id,
                title="Có tuyến mới đã được duyệt",
                body=f"{len(route.stops)} điểm dừng · {route.total_weight_kg:.0f} kg",
                entity="pickup_route",
                entity_id=str(route.id),
            )
        )
    session.flush()
    return route


def _recalculate_totals(session: Session, route: PickupRoute) -> None:
    """Tính lại khối lượng và quãng đường sau khi người duyệt sửa tuyến."""
    candidates: list[Candidate] = []
    for stop in sorted(route.stops, key=lambda s: s.seq):
        request = yeu_cau_cua(session, stop)
        if request is None:
            continue
        unit = session.get(Unit, request.unit_id)
        building = session.get(Building, unit.building_id) if unit else None
        candidates.append(Candidate(request=request, building=building, unit_code=unit.code if unit else ""))

    route.total_weight_kg = round(sum(c.weight_kg for c in candidates), 1)
    route.est_distance_km = estimate_route_km(candidates)
    baseline = round(len(candidates) * get_settings().baseline_km_per_standalone_trip, 2)
    reasoning = dict(route.reasoning or {})
    reasoning["baseline_km"] = baseline
    reasoning["saved_km"] = round(max(0.0, baseline - route.est_distance_km), 2)
    reasoning["saved_trips"] = max(0, len(candidates) - 1)
    reasoning["edited_by_human"] = True
    route.reasoning = reasoning


def route_diff(route: PickupRoute) -> dict[str, Any]:
    """So sánh bản AI đề xuất với bản người duyệt đã sửa.

    Phần diff này rất đáng giá khi demo: nó cho thấy người vẫn là người chốt.
    """
    proposed = list(route.proposed_stop_order or [])
    # Chỉ điểm dừng loại yêu cầu mới có mặt trong diff: bản AI đề xuất
    # (``proposed_stop_order``) vốn là danh sách request_id.
    current = [s.request_id for s in sorted(route.stops, key=lambda s: s.seq) if s.request_id]
    return {
        "proposed": proposed,
        "final": current,
        "removed": [r for r in proposed if r not in current],
        "reordered": proposed != current and sorted(proposed) == sorted(current),
        "changed": proposed != current,
    }


def complete_stop(
    session: Session,
    *,
    stop: RouteStop,
    actor: User,
    issue: str = "",
    issue_note: str = "",
    actual_weight_kg: float | None = None,
) -> RouteStop:
    """Đội vệ sinh đánh dấu đã thu tại một điểm dừng.

    Điểm dừng loại ``yeu_cau`` chuyển yêu cầu sang ``hoan_tat``; điểm dừng loại
    ``thung`` đưa mức rác của thùng về 0. Báo có sự cố (``issue``) thì KHÔNG hạ
    mức rác — kẹt nắp hay không tiếp cận được nghĩa là thùng vẫn đầy.

    Raises:
        ValueError: khi mã sự cố nằm ngoài danh sách cố định.
    """
    if issue and issue not in STOP_ISSUE_CODES:
        raise ValueError(f"Mã sự cố '{issue}' không nằm trong danh sách cố định")

    stop.done_at = datetime.now()
    stop.issue = issue
    stop.issue_note = issue_note
    stop.actual_weight_kg = actual_weight_kg

    request = yeu_cau_cua(session, stop)
    if request is not None:
        request.status = HOAN_TAT
        session.add(
            PickupEvent(
                request_id=request.id,
                kind="done",
                label_vi="Đội vệ sinh đã thu gom",
                actor_id=actor.id,
                detail={"issue": issue, "note": issue_note},
            )
        )

    # Điểm dừng loại thùng: đổ xong thì mức rác phải về 0, nếu không thùng vẫn
    # báo đầy và ngày mai lại đứng đầu tuyến. Ghi qua `ghi_nhan_reading` với
    # nguồn `manual` chứ không gán thẳng `fill_percent`: lịch sử readings giữ
    # nguyên, và chính dòng reading đó là bằng chứng ai đổ, lúc nào.
    if stop.bin_id:
        thung = session.get(Bin, stop.bin_id)
        if thung is not None and not issue:
            muc_rac_truoc = thung.fill_percent
            bins.ghi_nhan_reading(session, thung, 0.0, thung.battery_percent, "manual", utcnow())
            # Món nợ B3c: hạ mức rác là đổi dữ liệu thật do người thực hiện, nên
            # nó phải có mặt trong nhật ký kiểm toán y như giao thùng hay sửa hồ
            # sơ. `BinReading` chứng minh "thùng đã được đổ"; `AuditLog` chứng
            # minh "ai đổ, lúc nào" theo đúng khuôn chung của cả hệ thống.
            write_audit(
                session,
                actor=actor,
                action="do_thung",
                entity="bin",
                entity_id=str(thung.id),
                detail={
                    "code": thung.code,
                    "stop_id": stop.id,
                    "route_id": stop.route_id,
                    "fill_percent_truoc": muc_rac_truoc,
                    "fill_percent_sau": 0.0,
                },
            )

    route = session.get(PickupRoute, stop.route_id)
    if route is not None:
        if all(s.done_at is not None for s in route.stops):
            route.status = "done"
        elif route.status == "approved":
            route.status = "in_progress"
    session.flush()
    return stop
