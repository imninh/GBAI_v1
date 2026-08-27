"""Chuyển bản ghi CSDL thành khuôn JSON đúng hợp đồng API.

Gom vào một chỗ để hai màn khác nhau nhìn cùng một thực thể không bao giờ nhận
được hai khuôn dữ liệu khác nhau.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import (
    Bin,
    Building,
    Classification,
    Media,
    PickupEvent,
    PickupRequest,
    PickupRoute,
    RouteStop,
    Unit,
    User,
    WasteCategory,
)
from src.services import safety
from src.services.classifier import TIER_LABELS_VI


def category_dict(category: WasteCategory | None) -> dict[str, Any] | None:
    if category is None:
        return None
    return {
        "code": category.code,
        "name": category.name,
        "parent_code": category.parent_code,
        "is_hazardous": category.is_hazardous,
        "min_confidence": category.min_confidence,
        "bin_color": category.bin_color,
        "icon": category.icon,
        "handling_note": category.handling_note,
        "safety_warning": category.safety_warning,
    }


def user_dict(session: Session, user: User) -> dict[str, Any]:
    # Toà của người dùng lấy TRỰC TIẾP từ `building_id` (liên kết chính từ gói
    # P62) — người không có căn hộ (hộ dân lẻ / cư dân GIS) vẫn có toà. Chỉ khi
    # cột đó rỗng mới lui về đường cũ qua `unit → building`.
    building = session.get(Building, user.building_id) if user.building_id else None
    unit = session.get(Unit, user.unit_id) if user.unit_id else None
    if building is None and unit is not None:
        building = session.get(Building, unit.building_id)
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "unit": unit.code if unit else "",
        "building": building.name if building else "",
        "building_id": building.id if building else None,
        # Toạ độ toà nhà đăng ký, để app cư dân sắp điểm gửi theo khoảng cách mà
        # KHÔNG phải xin quyền vị trí. Cả hai cột đều cho phép NULL — người dùng
        # chưa gắn căn hộ thì không có toạ độ, app phải chịu được `null`.
        "building_lat": building.lat if building else None,
        "building_lng": building.lng if building else None,
        # Nơi ở tự khai của CHÍNH người dùng (gói P52) — khác toà khi hộ dân lẻ
        # nhập địa chỉ riêng; khác rỗng khi chưa có gì.
        "address": user.address,
        "lat": user.lat,
        "lng": user.lng,
        "green_points": user.green_points,
    }


def classification_dict(
    session: Session,
    classification: Classification,
    *,
    full: bool = False,
) -> dict[str, Any]:
    """Khuôn kết quả phân loại trả về cho UI.

    ``safety_warning`` luôn lấy từ danh mục trong CSDL, không lấy từ text model
    sinh ra — trên UI có dòng "không do AI tự viết" và câu đó phải đúng.
    """
    category = (
        session.get(WasteCategory, classification.predicted_category_id)
        if classification.predicted_category_id
        else None
    )
    human_label = session.get(WasteCategory, classification.human_label_id) if classification.human_label_id else None
    min_confidence = safety.min_confidence_for(category)

    data: dict[str, Any] = {
        "classification_id": classification.id,
        "media_id": classification.media_id,
        "input_type": classification.input_type,
        # `text_query` là câu hỏi bằng chữ của cư dân. Trước gói P62 khoá
        # chống-trùng của THIẾT BỊ bị nhét vào đây dưới dạng "item_id:…"; lọc bỏ
        # để dữ liệu đã lỡ ghi không hiện lên màn hình (dọn dữ liệu cũ).
        "text_query": "" if classification.text_query.startswith("item_id:") else classification.text_query,
        "item_name": classification.item_name,
        "category": category_dict(category),
        "confidence": round(classification.confidence, 4),
        "min_confidence": round(min_confidence, 4),
        "confidence_level": safety.confidence_level(classification.confidence, min_confidence),
        "tier": classification.tier,
        "tier_label_vi": TIER_LABELS_VI.get(classification.tier, ""),
        "model": classification.model,
        "refused": classification.refused,
        "refusal_reason": classification.refusal_reason,
        "refusal_label_vi": safety.REFUSAL_LABELS_VI.get(classification.refusal_reason, ""),
        "escalated_to_human": classification.escalated_to_human,
        "items": classification.items or [],
        "advice": classification.advice,
        "advice_sources": classification.advice_sources or [],
        "safety_warning": category.safety_warning if category and category.is_hazardous else "",
        "safety_warning_note": (
            "Cảnh báo an toàn theo danh mục chuẩn — không do AI tự viết." if category and category.is_hazardous else ""
        ),
        "degraded": classification.degraded,
        "degraded_note": classification.degraded_note,
        "human_label": category_dict(human_label),
        "verified_by": classification.verified_by,
        "verified_at": classification.verified_at.isoformat() if classification.verified_at else None,
        "latency_ms": classification.latency_ms,
        "cost_usd": classification.cost_usd,
        "run_id": classification.run_id,
        "is_seed": classification.is_seed,
        "created_at": classification.created_at.isoformat(),
    }

    if full:
        data.update(
            {
                "prompt_version": classification.prompt_version,
                "escalation_reason": classification.escalation_reason,
                "building_id": classification.building_id,
                "asker_id": classification.asker_id,
            }
        )
    return data


def media_privacy_dict(media: Media) -> dict[str, Any]:
    """Dữ liệu cho màn "Ảnh của tôi đã được xử lý thế nào" (spec 4.5)."""
    return {
        "media_id": media.id,
        "exif_stripped": media.exif_stripped,
        "removed_fields": media.removed_fields or [],
        "faces_blurred": media.faces_blurred,
        "original_size": {
            "width": media.original_width,
            "height": media.original_height,
            "bytes": media.original_bytes_size,
        },
        "processed_size": {"width": media.width, "height": media.height, "bytes": media.bytes_size},
        "expires_at": media.expires_at.isoformat() if media.expires_at else None,
        "has_original": bool(media.original_path),
    }


def pickup_dict(session: Session, request: PickupRequest, *, full: bool = False) -> dict[str, Any]:
    # Hộ dân lẻ (unit_id = None) không có căn hộ để tra — chặn tường minh kẻo
    # session.get(Unit, None) trả None kèm SAWarning.
    unit = session.get(Unit, request.unit_id) if request.unit_id is not None else None
    building = session.get(Building, unit.building_id) if unit else None
    # Cư dân chỉ gắn toà (không có căn) → lấy toà từ resident.building_id.
    resident = session.get(User, request.resident_id)
    if building is None and resident is not None and resident.building_id is not None:
        building = session.get(Building, resident.building_id)

    data: dict[str, Any] = {
        "id": request.id,
        "resident": {"id": resident.id, "full_name": resident.full_name} if resident else None,
        "unit": unit.code if unit else "",
        "building": building.name if building else "",
        "building_code": building.code if building else "",
        # Điểm lấy hàng của RIÊNG yêu cầu này — màn duyệt phải biết xe đi đâu.
        # Rỗng nghĩa là lấy theo nơi ở của cư dân (users.address / toà nhà).
        "address": request.address,
        "items": request.items or [],
        "weight_min_kg": request.weight_min_kg,
        "weight_max_kg": request.weight_max_kg,
        "est_weight_kg": request.est_weight_kg,
        "preferred_date": request.preferred_date.isoformat() if request.preferred_date else None,
        "preferred_window": request.preferred_window,
        "note": request.note,
        "requires_hitl": request.requires_hitl,
        "threshold_hit": request.threshold_hit or [],
        "status": request.status,
        "reject_reason": request.reject_reason,
        "review_note": request.review_note,
        "approved_by": request.approved_by,
        "approved_at": request.approved_at.isoformat() if request.approved_at else None,
        # Khối lượng THẬT do đội vệ sinh cân — điểm chỉ được trao từ con số này.
        "weight_confirmed_kg": request.weight_confirmed_kg,
        "confirmed_by": request.confirmed_by,
        "confirmed_at": request.confirmed_at.isoformat() if request.confirmed_at else None,
        "dispute_reason": request.dispute_reason,
        "is_seed": request.is_seed,
        "created_at": request.created_at.isoformat(),
    }

    if full:
        events = session.scalars(
            select(PickupEvent).where(PickupEvent.request_id == request.id).order_by(PickupEvent.created_at)
        ).all()
        data["timeline"] = [
            {
                "kind": e.kind,
                "label_vi": e.label_vi,
                "actor_id": e.actor_id,
                "detail": e.detail,
                "at": e.created_at.isoformat(),
            }
            for e in events
        ]
        stop = session.scalars(select(RouteStop).where(RouteStop.request_id == request.id)).first()
        route = session.get(PickupRoute, stop.route_id) if stop else None
        data["route"] = (
            {
                "id": route.id,
                "service_date": route.service_date.isoformat(),
                "window": route.window,
                "status": route.status,
                "stop_count": len(route.stops),
                "saved_trips": (route.reasoning or {}).get("saved_trips", 0),
            }
            if route
            else None
        )
    return data


def route_dict(session: Session, route: PickupRoute, *, full: bool = False) -> dict[str, Any]:
    team = session.get(User, route.team_id) if route.team_id else None
    data: dict[str, Any] = {
        "id": route.id,
        "service_date": route.service_date.isoformat(),
        "window": route.window,
        "status": route.status,
        "total_weight_kg": route.total_weight_kg,
        "est_distance_km": route.est_distance_km,
        "stop_count": len(route.stops),
        "team": {"id": team.id, "full_name": team.full_name} if team else None,
        "approved_by": route.approved_by,
        "approved_at": route.approved_at.isoformat() if route.approved_at else None,
        "run_id": route.run_id,
        "is_seed": route.is_seed,
        "created_at": route.created_at.isoformat(),
    }

    if full:
        cac_diem = sorted(route.stops, key=lambda s: s.seq)
        # Gom toàn bộ thực thể của điểm dừng TRƯỚC vòng lặp: mỗi bảng một câu IN
        # thay cho một `session.get` cho từng điểm dừng, nên tuyến 30 điểm không
        # phát ra 30 lượt hỏi CSDL mỗi lần mở màn hình.
        ma_yeu_cau = [d.request_id for d in cac_diem if d.request_id]
        ma_thung = [d.bin_id for d in cac_diem if d.bin_id]
        cac_yeu_cau = (
            {yc.id: yc for yc in session.scalars(select(PickupRequest).where(PickupRequest.id.in_(ma_yeu_cau)))}
            if ma_yeu_cau
            else {}
        )
        cac_can = (
            {
                can.id: can
                for can in session.scalars(
                    select(Unit).where(Unit.id.in_([yc.unit_id for yc in cac_yeu_cau.values() if yc.unit_id]))
                )
            }
            if cac_yeu_cau
            else {}
        )
        cac_toa = (
            {
                toa.id: toa
                for toa in session.scalars(
                    select(Building).where(Building.id.in_([can.building_id for can in cac_can.values()]))
                )
            }
            if cac_can
            else {}
        )
        cac_cu_dan = (
            {
                nd.id: nd
                for nd in session.scalars(
                    select(User).where(User.id.in_([yc.resident_id for yc in cac_yeu_cau.values()]))
                )
            }
            if cac_yeu_cau
            else {}
        )
        cac_thung = (
            {thung.id: thung for thung in session.scalars(select(Bin).where(Bin.id.in_(ma_thung)))}
            if ma_thung
            else {}
        )

        stops = []
        for stop in cac_diem:
            # Điểm dừng loại "thung" không có request_id nên phải chặn trước khi tra.
            request = cac_yeu_cau.get(stop.request_id) if stop.request_id else None
            unit = cac_can.get(request.unit_id) if request and request.unit_id else None
            resident = cac_cu_dan.get(request.resident_id) if request else None
            thung = cac_thung.get(stop.bin_id) if stop.bin_id else None
            # Toạ độ để vẽ điểm dừng lên bản đồ. Thùng mang toạ độ của chính nó;
            # yêu cầu của cư dân mượn toạ độ toà nhà. Hai cột đều cho phép NULL
            # nên frontend buộc phải chịu được `null`, không được coi là luôn có.
            toa_nha = cac_toa.get(unit.building_id) if unit else None
            noi_dung = thung if thung is not None else toa_nha
            # Địa chỉ để người cầm điện thoại đi thu gom biết đến chỗ nào: thùng
            # dùng địa chỉ của chính nó; yêu cầu của cư dân ghép mã căn với địa
            # chỉ toà nhà. Toà chưa có địa chỉ thì lui về mã căn — không phát ra
            # chuỗi rỗng hay chuỗi "Căn S1-0805 · " cụt đuôi.
            if thung is not None:
                dia_chi = thung.address
            elif unit is not None and toa_nha is not None and toa_nha.address:
                dia_chi = f"Căn {unit.code} · {toa_nha.address}"
            elif unit is not None:
                dia_chi = unit.code
            else:
                dia_chi = ""
            stops.append(
                {
                    "stop_id": stop.id,
                    "seq": stop.seq,
                    "stop_kind": stop.stop_kind,
                    "request_id": stop.request_id,
                    "bin_id": stop.bin_id,
                    # Một dòng điểm dừng trên app phải đọc được mà không cần biết
                    # nó thuộc loại nào.
                    "diem_dung_vi": thung.name if thung else (unit.code if unit else ""),
                    "dia_chi": dia_chi,
                    "lat": noi_dung.lat if noi_dung is not None else None,
                    "lng": noi_dung.lng if noi_dung is not None else None,
                    "fill_percent": thung.fill_percent if thung else None,
                    "unit": unit.code if unit else "",
                    "resident_name": resident.full_name if resident else "",
                    # Số điện thoại che một phần; hệ thống demo không lưu SĐT thật.
                    "phone_masked": ("090•••" + str(stop.request_id).zfill(3)) if stop.request_id else "",
                    "weight_max_kg": request.weight_max_kg if request else 0.0,
                    "items": request.items if request else [],
                    "done_at": stop.done_at.isoformat() if stop.done_at else None,
                    "issue": stop.issue,
                    "issue_note": stop.issue_note,
                    "actual_weight_kg": stop.actual_weight_kg,
                }
            )
        data["stops"] = stops
        data["reasoning"] = route.reasoning or {}
        data["proposed_stop_order"] = route.proposed_stop_order or []

        # Tải hình đường đi thật OSRM và metadata lộ trình
        from src.services import duong_di_that
        toa_do = [(float(s["lat"]), float(s["lng"])) for s in stops if s.get("lat") is not None and s.get("lng") is not None]
        if len(toa_do) >= 2:
            lt = duong_di_that.lo_trinh(toa_do)
            if lt:
                data["duong_di"] = [[lat, lng] for lat, lng in lt.polyline]
                data["lo_trinh_meta"] = {
                    "total_km": lt.total_km,
                    "total_minutes": lt.total_minutes,
                    "legs": [
                        {
                            "from_seq": stops[i].get("seq", i + 1),
                            "to_seq": stops[i + 1].get("seq", i + 2),
                            "distance_km": leg.distance_km,
                            "duration_minutes": leg.duration_minutes,
                        }
                        for i, leg in enumerate(lt.legs)
                    ],
                }
    return data

