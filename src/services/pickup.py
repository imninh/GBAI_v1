"""Yêu cầu thu gom đồ cồng kềnh và điểm HITL #1.

Hai quyết định thiết kế đáng chú ý:

* **Khối lượng là một KHOẢNG, không phải một số** (ADR-0003). Vision ước lượng
  kg từ ảnh sai vài lần là bình thường, nên ngưỡng duyệt so với **cận trên** —
  sai số phải nghiêng về phía cần người duyệt, không nghiêng về phía tự động
  cho qua.
* **Ngưỡng đã kích hoạt được lưu thành bản ghi** (``threshold_hit``) chứ không
  tính lại lúc hiển thị. Màn duyệt bắt buộc nói rõ vì sao mục này rơi vào hàng
  đợi; một hàng đợi không nói lý do là hàng đợi vô nghĩa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import (
    Building,
    Notification,
    PickupEvent,
    PickupRequest,
    Unit,
    User,
    WasteCategory,
)
from src.db.seed_data import PICKUP_REJECT_REASONS
from src.services.pickup_lifecycle import (
    CHO_DUYET,
    CHO_NHAN,
    DA_HUY,
    DA_NHAN,
    HOAN_TAT,
    TU_CHOI,
    chuan_hoa,
    trang_thai_tuong_duong,
)

# Sai số ước lượng khối lượng từ ảnh, dùng khi client chỉ gửi một con số.
# ±40% là con số ghi trong khối "Giới hạn đã biết" trên UI — giữ hai chỗ khớp nhau.
WEIGHT_ESTIMATE_TOLERANCE = 0.40

REJECT_REASON_CODES = {r["code"] for r in PICKUP_REJECT_REASONS}


@dataclass
class ThresholdHit:
    """Một luật đã kích hoạt, kèm con số để hiển thị."""

    rule: str
    label_vi: str
    value: float
    threshold: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "label_vi": self.label_vi,
            "value": self.value,
            "threshold": self.threshold,
        }


def weight_range_from_estimate(
    est_weight_kg: float,
    weight_min_kg: float | None = None,
    weight_max_kg: float | None = None,
) -> tuple[float, float, float]:
    """Chuẩn hoá khối lượng về ``(min, max, mid)``.

    Client gửi khoảng thì tôn trọng khoảng đó; chỉ gửi một số thì nở ra ±40%
    theo sai số đã công bố của phần ước lượng bằng ảnh.
    """
    if weight_min_kg is not None and weight_max_kg is not None and weight_max_kg >= weight_min_kg > 0:
        return weight_min_kg, weight_max_kg, (weight_min_kg + weight_max_kg) / 2
    base = max(0.0, est_weight_kg)
    low = round(base * (1 - WEIGHT_ESTIMATE_TOLERANCE), 1)
    high = round(base * (1 + WEIGHT_ESTIMATE_TOLERANCE), 1)
    return low, high, base


def evaluate_thresholds(
    session: Session,
    items: list[dict[str, Any]],
    weight_max_kg: float,
) -> list[ThresholdHit]:
    """Liệt kê các ngưỡng đã kích hoạt của một yêu cầu.

    Có món nghi nguy hại thì **luôn** cần người duyệt, bất kể khối lượng —
    nhóm đó có quy trình xử lý riêng, không đi cùng chuyến đồ cồng kềnh.
    """
    settings = get_settings()
    hits: list[ThresholdHit] = []

    if weight_max_kg > settings.hitl_weight_threshold_kg:
        hits.append(
            ThresholdHit(
                rule="vuot_khoi_luong",
                label_vi="Khối lượng ước tính vượt ngưỡng tự động",
                value=weight_max_kg,
                threshold=settings.hitl_weight_threshold_kg,
            )
        )

    item_count = sum(int(i.get("qty", 1) or 1) for i in items)
    if item_count > settings.hitl_item_count_threshold:
        hits.append(
            ThresholdHit(
                rule="vuot_so_mon",
                label_vi="Số món vượt ngưỡng tự động",
                value=float(item_count),
                threshold=float(settings.hitl_item_count_threshold),
            )
        )

    codes = {str(i.get("category_code", "")) for i in items if i.get("category_code")}
    if codes:
        hazardous = session.scalars(
            select(WasteCategory.code).where(WasteCategory.code.in_(codes), WasteCategory.is_hazardous.is_(True))
        ).all()
        if hazardous:
            hits.append(
                ThresholdHit(
                    rule="co_mon_nguy_hai",
                    label_vi="Có món thuộc nhóm rác nguy hại — cần quy trình riêng",
                    value=float(len(hazardous)),
                    threshold=0.0,
                )
            )

    return hits


def create_pickup_request(
    session: Session,
    *,
    resident: User,
    items: list[dict[str, Any]],
    est_weight_kg: float = 0.0,
    weight_min_kg: float | None = None,
    weight_max_kg: float | None = None,
    preferred_date: date | None = None,
    preferred_window: str = "",
    note: str = "",
    ngoai_lich: bool = False,
) -> PickupRequest:
    """Tạo yêu cầu thu gom và ghi hai mốc đầu tiên trên timeline.

    Raises:
        ValueError: khi cư dân chưa gắn với căn hộ nào (không biết thu ở đâu).
    """
    if resident.unit_id is None:
        raise ValueError("Tài khoản chưa gắn với căn hộ nào nên không tạo được yêu cầu thu gom")

    co_khoang_ro = (
        weight_min_kg is not None and weight_max_kg is not None and weight_max_kg >= weight_min_kg > 0
    )
    if not co_khoang_ro and est_weight_kg <= 0:
        raise ValueError("Yêu cầu thu gom phải có khối lượng ước tính lớn hơn 0 kg")

    low, high, mid = weight_range_from_estimate(est_weight_kg, weight_min_kg, weight_max_kg)
    hits = evaluate_thresholds(session, items, high)

    if ngoai_lich and preferred_window:
        hits.append(
            ThresholdHit(
                rule="gio_ngoai_lich",
                label_vi="Giờ đề xuất nằm ngoài lịch thu gom của toà — cần ban quản lý duyệt",
                value=0.0,
                threshold=0.0,
            )
        )

    request = PickupRequest(
        resident_id=resident.id,
        unit_id=resident.unit_id,
        items=items,
        weight_min_kg=low,
        weight_max_kg=high,
        est_weight_kg=mid,
        preferred_date=preferred_date,
        preferred_window=preferred_window,
        note=note,
        requires_hitl=bool(hits),
        threshold_hit=[h.as_dict() for h in hits],
        status=CHO_DUYET if hits else CHO_NHAN,
    )
    session.add(request)
    session.flush()

    session.add(
        PickupEvent(request_id=request.id, kind="created", label_vi="Đã gửi yêu cầu", actor_id=resident.id)
    )
    if hits:
        detail = " · ".join(f"{h.label_vi} ({h.value:g} so với ngưỡng {h.threshold:g})" for h in hits)
        session.add(
            PickupEvent(
                request_id=request.id,
                kind="threshold",
                label_vi=f"Hệ thống kiểm tra — {detail}, cần ban quản lý duyệt",
                detail={"threshold_hit": request.threshold_hit},
            )
        )
    else:
        session.add(
            PickupEvent(
                request_id=request.id,
                kind="reviewed",
                label_vi="Trong ngưỡng tự động — không cần duyệt tay",
            )
        )
    session.flush()
    return request


def review_pickup(
    session: Session,
    *,
    request: PickupRequest,
    actor: User,
    action: str,
    reason: str = "",
    note: str = "",
    changes: dict[str, Any] | None = None,
) -> PickupRequest:
    """HITL #1 — ban quản lý duyệt / duyệt kèm điều chỉnh / từ chối.

    Args:
        action: ``approve`` · ``approve_with_changes`` · ``reject``.
        reason: bắt buộc khi từ chối, và **phải chọn từ danh sách cố định** —
            cho gõ tự do là mất dữ liệu cho vòng lặp cải tiến (PLO 7).

    Raises:
        ValueError: khi hành động không hợp lệ, thiếu lý do từ chối, hoặc lý do
            nằm ngoài danh sách cố định.
    """
    if action not in {"approve", "approve_with_changes", "reject"}:
        raise ValueError(f"Hành động không hợp lệ: {action}")
    if chuan_hoa(request.status) not in {CHO_DUYET, CHO_NHAN}:
        raise ValueError(f"Yêu cầu đang ở trạng thái '{request.status}', không duyệt lại được")

    if action == "reject":
        if not reason:
            raise ValueError("Từ chối phải kèm lý do")
        if reason not in REJECT_REASON_CODES:
            raise ValueError(f"Lý do từ chối '{reason}' không nằm trong danh sách cố định")
        request.status = TU_CHOI
        request.reject_reason = reason
        request.review_note = note
        label = next(r["label_vi"] for r in PICKUP_REJECT_REASONS if r["code"] == reason)
        session.add(
            PickupEvent(
                request_id=request.id,
                kind="reviewed",
                label_vi=f"Ban quản lý từ chối — {label}",
                actor_id=actor.id,
                detail={"reason": reason, "note": note},
            )
        )
        _notify(session, request.resident_id, "Yêu cầu thu gom bị từ chối", f"{label}. {note}".strip(), request)
        session.flush()
        return request

    if action == "approve_with_changes" and changes:
        if "preferred_date" in changes and changes["preferred_date"]:
            request.preferred_date = changes["preferred_date"]
        if "preferred_window" in changes:
            request.preferred_window = str(changes["preferred_window"])
        if "weight_max_kg" in changes and changes["weight_max_kg"]:
            request.weight_max_kg = float(changes["weight_max_kg"])
            request.est_weight_kg = (request.weight_min_kg + request.weight_max_kg) / 2

    request.status = CHO_NHAN
    request.approved_by = actor.id
    request.approved_at = datetime.now()
    request.review_note = note
    label = "Ban quản lý đã duyệt" if action == "approve" else "Ban quản lý duyệt kèm điều chỉnh"
    session.add(
        PickupEvent(
            request_id=request.id,
            kind="reviewed",
            label_vi=f"{label} — {actor.full_name}",
            actor_id=actor.id,
            detail={"changes": {k: str(v) for k, v in (changes or {}).items()}, "note": note},
        )
    )
    _notify(session, request.resident_id, "Yêu cầu thu gom đã được duyệt", note or label, request)
    session.flush()
    return request


def cancel_pickup(session: Session, *, request: PickupRequest, actor: User) -> PickupRequest:
    """Cư dân huỷ yêu cầu của chính mình. Đã xếp tuyến thì không huỷ được nữa.

    Raises:
        ValueError: khi yêu cầu đã ở trạng thái ``scheduled`` trở đi.
    """
    if chuan_hoa(request.status) in {DA_NHAN, HOAN_TAT}:
        raise ValueError("Yêu cầu đã được xếp vào tuyến, liên hệ ban quản lý để đổi")
    request.status = DA_HUY
    session.add(
        PickupEvent(request_id=request.id, kind="cancelled", label_vi="Cư dân huỷ yêu cầu", actor_id=actor.id)
    )
    session.flush()
    return request


def decision_context(session: Session, request: PickupRequest) -> dict[str, Any]:
    """Bối cảnh ra quyết định cho màn duyệt — **tính bằng SQL, không phải LLM**.

    Người duyệt cần con số chính xác chứ không cần câu văn hay; và số do SQL
    tính thì luôn đúng, không có chuyện bịa.
    """
    unit = session.get(Unit, request.unit_id)
    building_id = unit.building_id if unit else None

    lich_su = session.execute(
        select(
            func.count(PickupRequest.id),
            func.sum(case((PickupRequest.status.in_(trang_thai_tuong_duong(HOAN_TAT)), 1), else_=0)),
            func.sum(case((PickupRequest.status.in_(trang_thai_tuong_duong(DA_HUY)), 1), else_=0)),
        ).where(PickupRequest.resident_id == request.resident_id, PickupRequest.id != request.id)
    ).one()

    tuan_nay = (0, 0.0)
    if building_id is not None:
        tuan_nay = session.execute(
            select(func.count(PickupRequest.id), func.coalesce(func.sum(PickupRequest.est_weight_kg), 0.0))
            .join(Unit, PickupRequest.unit_id == Unit.id)
            .where(
                Unit.building_id == building_id,
                # Không được viết ``!= "da_huy"``: hàng còn giữ giá trị cũ
                # "cancelled" sẽ lọt qua bộ lọc và bị tính là yêu cầu đang sống.
                # Phải not_in CẢ HAI giá trị cũ lẫn mới.
                PickupRequest.status.not_in(trang_thai_tuong_duong(DA_HUY)),
            )
        ).one()

    cung_ngay = 0
    if request.preferred_date is not None:
        cung_ngay = session.scalar(
            select(func.count(PickupRequest.id)).where(
                PickupRequest.preferred_date == request.preferred_date,
                PickupRequest.status.in_(trang_thai_tuong_duong(CHO_NHAN) + trang_thai_tuong_duong(DA_NHAN)),
                PickupRequest.id != request.id,
            )
        )

    return {
        "resident_history": {
            "so_yeu_cau_truoc": int(lich_su[0] or 0),
            "so_lan_hoan_thanh": int(lich_su[1] or 0),
            "so_lan_huy": int(lich_su[2] or 0),
        },
        "building_context": {
            "so_yeu_cau": int(tuan_nay[0] or 0),
            "tong_khoi_luong_kg": round(float(tuan_nay[1] or 0.0), 1),
        },
        "capacity_context": {
            "ngay_mong_muon": request.preferred_date.isoformat() if request.preferred_date else "",
            "so_yeu_cau_cung_ngay": int(cung_ngay or 0),
            "tai_trong_xe_kg": get_settings().vehicle_capacity_kg,
        },
    }


def _notify(session: Session, user_id: int, title: str, body: str, request: PickupRequest) -> None:
    session.add(
        Notification(
            user_id=user_id,
            title=title,
            body=body,
            entity="pickup_request",
            entity_id=str(request.id),
        )
    )


def building_of(session: Session, request: PickupRequest) -> Building | None:
    """Toà nhà của một yêu cầu, lấy qua căn hộ."""
    unit = session.get(Unit, request.unit_id)
    return session.get(Building, unit.building_id) if unit else None
