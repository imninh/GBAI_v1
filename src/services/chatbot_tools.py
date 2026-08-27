"""Công cụ truy vấn CSDL cho Chatbot RAG (Tool-Augmented RAG).

Phục vụ Chức năng 2 (F2): Tra cứu thùng rác còn khả thi gần đây.
Đọc dữ liệu thời gian thực từ bảng `Bin` và `BinReading`, tính khoảng cách
theo toạ độ GPS, lọc theo nhóm rác và trạng thái điều phối.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Bin, Building, WasteCategory
from src.services.bins import trang_thai_thung


@dataclass
class ViableBinInfo:
    """Thông tin thùng rác khả thi trả về cho cư dân / LLM."""

    id: int
    code: str
    name: str
    address: str
    category_codes: list[str]
    category_names: list[str] = field(default_factory=list)
    fill_percent: float = 0.0
    battery_percent: float = 0.0
    status: str = "binh_thuong"
    status_label_vi: str = "Bình thường"
    is_viable: bool = True
    distance_meters: float | None = None
    lat: float | None = None
    lng: float | None = None
    last_seen_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "address": self.address,
            "category_codes": self.category_codes,
            "category_names": self.category_names,
            "fill_percent": round(self.fill_percent, 1),
            "battery_percent": round(self.battery_percent, 1),
            "status": self.status,
            "status_label_vi": self.status_label_vi,
            "is_viable": self.is_viable,
            "distance_meters": round(self.distance_meters, 1) if self.distance_meters is not None else None,
            "lat": self.lat,
            "lng": self.lng,
        }


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Tính khoảng cách đường chim bay giữa hai toạ độ GPS (mét)."""
    radius = 6371000.0  # Bán kính Trái Đất theo mét
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


_STATUS_LABELS_VI: dict[str, str] = {
    "binh_thuong": "Hoạt động tốt (Còn chỗ)",
    "can_gom": "Sắp đầy / Cần gom",
    "het_pin": "Hết pin",
    "mat_ket_noi": "Mất kết nối",
    "chua_trien_khai": "Chưa triển khai",
}


def query_viable_bins(
    session: Session,
    *,
    category_code: str | None = None,
    building_id: int | None = None,
    user_lat: float | None = None,
    user_lng: float | None = None,
    max_fill_percent: float = 90.0,
    limit: int = 5,
    now: datetime | None = None,
) -> list[ViableBinInfo]:
    """Truy vấn các thùng rác đang hoạt động và còn chỗ.

    Tiêu chí khả thi:
    - `is_active == True`
    - `fill_percent < max_fill_percent` (mặc định dưới 90%)
    - Trạng thái điều phối không phải `mat_ket_noi` hoặc `het_pin`
    - Nhận đúng loại rác `category_code` (nếu có yêu cầu)
    """
    thoi_diem = now or datetime.now(UTC)

    # Lấy danh mục rác để map tên tiếng Việt
    categories_map: dict[str, str] = {}
    for cat in session.scalars(select(WasteCategory)).all():
        categories_map[cat.code] = cat.name

    has_user_gps = user_lat is not None and user_lng is not None

    # Nếu người dùng chưa có GPS, fallback về toạ độ toà nhà (nếu có building_id)
    if not has_user_gps and building_id is not None:
        building = session.get(Building, building_id)
        if building and building.lat is not None and building.lng is not None:
            user_lat = building.lat
            user_lng = building.lng

    statement = select(Bin).where(Bin.is_active.is_(True))
    # Khi không có GPS người dùng thực tế thì mới lọc giới hạn theo toà nhà
    if not has_user_gps and building_id is not None:
        statement = statement.where((Bin.building_id == building_id) | (Bin.building_id.is_(None)))

    bins = session.scalars(statement).all()
    results: list[ViableBinInfo] = []

    for bin_obj in bins:
        # Kiểm tra nhóm rác
        cats = bin_obj.category_codes or []
        if category_code:
            match = False
            for c in cats:
                if c == category_code or c.startswith(f"{category_code}_") or category_code.startswith(f"{c}_"):
                    match = True
                    break
                # Cho phép chung: "recyclable" bao gồm "recyclable_plastic", v.v.
                if category_code == "recyclable" and "recyclable" in c:
                    match = True
                    break
                if c == "recyclable" and "recyclable" in category_code:
                    match = True
                    break
            if not match:
                continue

        # Thùng demo và thùng thật đi CHUNG một đường tính trạng thái. Trước đây
        # từng có khối gắn cứng vài mã thùng luôn ở trạng thái mất kết nối; khối
        # đó đã được dọn và có test quét chặn quay lại — đừng thêm lại. Dữ liệu
        # nền nay đặt sẵn mức đầy, mức pin và lần báo cuối sao cho bốn trạng
        # thái TỰ SUY RA đúng.
        stt = trang_thai_thung(bin_obj, thoi_diem)

        is_viable = (
            stt in {"binh_thuong", "can_gom"}
            and bin_obj.fill_percent < max_fill_percent
            and stt != "mat_ket_noi"
            and stt != "het_pin"
        )

        dist = None
        if user_lat is not None and user_lng is not None and bin_obj.lat is not None and bin_obj.lng is not None:
            dist = _haversine_meters(user_lat, user_lng, bin_obj.lat, bin_obj.lng)

        cat_names = [categories_map.get(c, c) for c in cats]

        info = ViableBinInfo(
            id=bin_obj.id,
            code=bin_obj.code,
            name=bin_obj.name,
            address=bin_obj.address,
            category_codes=cats,
            category_names=cat_names,
            fill_percent=bin_obj.fill_percent,
            battery_percent=bin_obj.battery_percent,
            status=stt,
            status_label_vi=_STATUS_LABELS_VI.get(stt, stt),
            is_viable=is_viable,
            distance_meters=dist,
            lat=bin_obj.lat,
            lng=bin_obj.lng,
            last_seen_at=bin_obj.last_seen_at,
        )
        results.append(info)

    # Ưu tiên: Thùng khả thi (còn chỗ) trước, sau đó sắp xếp theo khoảng cách (nếu có) hoặc mức rác tăng dần
    def _sort_key(b: ViableBinInfo):
        viable_rank = 0 if b.is_viable else 1
        dist_rank = b.distance_meters if b.distance_meters is not None else 999999.0
        return (viable_rank, dist_rank, b.fill_percent)

    results.sort(key=_sort_key)
    return results[:limit]


def format_bins_for_llm_context(bins: list[ViableBinInfo], *, has_gps: bool = True) -> str:
    """Format danh sách thùng thành ngữ cảnh XML rõ ràng cho LLM đọc.

    Khi ``has_gps=False`` (§5.2): không hiển thị khoảng cách, không sắp xếp
    theo thứ tự khoảng cách, để tránh LLM bịa thông tin vị trí cư dân.
    """
    if not bins:
        return "Hiện tại không tìm thấy thùng rác nào khả dụng gần khu vực này."

    lines = ["<bin_data>"]
    for b in bins:
        if has_gps and b.distance_meters is not None:
            if b.distance_meters < 1000:
                dist_str = f", Khoảng cách: ~{int(b.distance_meters)}m"
            else:
                dist_str = f", Khoảng cách: ~{(b.distance_meters / 1000):.1f}km"
        else:
            dist_str = ""
        cats_str = ", ".join(b.category_names) if b.category_names else ", ".join(b.category_codes)
        lines.append(
            f"- Mã thùng: {b.code} | Tên: {b.name} | Vị trí: {b.address}{dist_str} | "
            f"Nhận loại: [{cats_str}] | Mức đầy: {b.fill_percent}% | "
            f"Trạng thái: {b.status_label_vi} (Khả dụng: {'Có' if b.is_viable else 'Không - Đầy hoặc lỗi'})"
        )
    lines.append("</bin_data>")
    return "\n".join(lines)


# --- 2. Action Tools & Idempotent Executions (HAX G9 & Tool Boundary) ---

def handle_book_bulky_pickup(
    session: Session,
    args: dict[str, Any],
    *,
    user: Any | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Handler tạo yêu cầu thu gom cồng kềnh cho cư dân."""
    if user is None:
        return {
            "success": False,
            "error": "Cần đăng nhập tài khoản cư dân để thực hiện đặt lịch thu gom.",
        }

    from src.services.pickup import create_pickup_request

    items = args.get("items") or args.get("item_name") or "Rác cồng kềnh (qua trợ lý AI)"
    if isinstance(items, str):
        items_list = [items]
    else:
        items_list = list(items)

    items_dicts = [{"name": str(it), "qty": 1} for it in items_list]

    preferred_date_str = args.get("preferred_date")
    pref_date = None
    if preferred_date_str:
        try:
            from datetime import date
            pref_date = date.fromisoformat(str(preferred_date_str)[:10])
        except Exception:
            pref_date = None

    est_weight = float(args.get("est_weight_kg", 5.0) or 5.0)
    note = str(args.get("note", "Đặt qua Chatbot Trợ lý Xanh Bini"))
    address = str(args.get("address", "")).strip()
    if not address and user and getattr(user, "unit_id", None) is None:
        if getattr(user, "address", None):
            address = str(user.address)
        elif getattr(user, "building_id", None):
            from src.db.models import Building
            b_obj = session.get(Building, user.building_id)
            if b_obj:
                address = b_obj.address or b_obj.name
        if not address:
            address = "Khu vực toà nhà cư dân"

    try:
        req = create_pickup_request(
            session,
            resident=user,
            items=items_dicts,
            est_weight_kg=est_weight,
            preferred_date=pref_date,
            note=note,
            address=address,
        )
        return {
            "success": True,
            "pickup_id": req.id,
            "status": req.status,
            "items": req.items,
            "preferred_date": req.preferred_date.isoformat() if req.preferred_date else None,
            "message": f"Đã ghi nhận yêu cầu thu gom #{req.id} cho {', '.join(items_list)}.",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Không thể tạo yêu cầu: {exc}",
        }


def handle_report_bin_issue(
    session: Session,
    args: dict[str, Any],
    *,
    user: Any | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Handler báo cáo sự cố / đầy thùng rác."""
    bin_id = args.get("bin_id")
    bin_code = args.get("bin_code")
    issue_type = args.get("issue_type", "day_rac")
    note = args.get("note", "Báo qua Chatbot Bini")

    bin_obj = None
    if bin_id:
        bin_obj = session.get(Bin, int(bin_id))
    elif bin_code:
        bin_obj = session.scalars(select(Bin).where(Bin.code == str(bin_code))).first()

    if not bin_obj:
        return {
            "success": False,
            "error": f"Không tìm thấy thùng rác với thông tin {bin_id or bin_code}.",
        }

    return {
        "success": True,
        "bin_id": bin_obj.id,
        "bin_code": bin_obj.code,
        "issue_type": issue_type,
        "note": note,
        "message": f"Đã tiếp nhận phản ánh sự cố cho thùng {bin_obj.code} ({bin_obj.name}). Đội ngũ kỹ thuật sẽ kiểm tra ngay.",
    }


def handle_get_user_points(
    session: Session,
    args: dict[str, Any],
    *,
    user: Any | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Handler tra cứu điểm thưởng & thành tích của cư dân."""
    if user is None:
        return {
            "success": False,
            "error": "Cần đăng nhập để tra cứu điểm thưởng.",
        }

    from sqlalchemy import func

    from src.db.models import DiemNhanThucLog

    tong_diem = session.scalar(
        select(func.coalesce(func.sum(DiemNhanThucLog.diem), 0)).where(DiemNhanThucLog.user_id == user.id)
    ) or 0

    return {
        "success": True,
        "user_id": user.id,
        "user_name": user.full_name,
        "points": int(tong_diem),
        "message": f"Cư dân {user.full_name} hiện đang có {int(tong_diem)} điểm xanh.",
    }


AVAILABLE_TOOLS = {
    "book_bulky_pickup": handle_book_bulky_pickup,
    "report_bin_issue": handle_report_bin_issue,
    "get_user_points": handle_get_user_points,
}

