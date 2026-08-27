"""Nơi ở của một người — chỗ DUY NHẤT quyết định "người này ở đâu".

Trước gói P52, hệ thống chỉ biết một người ở đâu qua chuỗi
``users.unit_id → units.building_id → buildings.lat/lng``. Chuỗi đó đúng với cư
dân chung cư, nhưng 600 tài khoản nhập từ dữ liệu GIS là hộ dân lẻ trên phố — họ
có địa chỉ và toạ độ rõ ràng nhưng không thuộc căn hộ nào, nên bị coi là "không
biết ở đâu" và bị chặn không cho tạo yêu cầu thu gom.

Gói này tách hai khái niệm đang bị nhập làm một:

* **Quan hệ hành chính** — thuộc toà nào, ai duyệt, lịch nào áp → vẫn là
  ``unit_id`` trên ``users``.
* **Toạ độ địa lý** — xe đi đến đâu để lấy hàng → cột riêng ``address`` / ``lat``
  / ``lng`` trên ``users`` (và trên từng ``pickup_requests`` khi điểm lấy hàng
  khác nơi ở).

Đây là nơi duy nhất biết thứ tự ưu tiên này — làm đúng tiền lệ
``loc_theo_nguoi_xem`` trong ``src/services/bins.py``. Đừng rải
``if user.unit_id is None`` ra router hay serializer.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.db.models import Building, Unit, User


def noi_o_cua(session: Session, user: User) -> tuple[str, float | None, float | None]:
    """Trả về ``(address, lat, lng)`` quyết định nơi ở của một người.

    Thứ tự ưu tiên, khai tường minh:

    1. ``user.unit_id`` có giá trị → tra ``Unit`` → tra ``Building`` → trả địa chỉ
       và toạ độ của **toà** (toà thắng, kể cả khi user cũng có cột riêng).
    2. Không có căn hộ nhưng ``user.building_id`` có giá trị (cư dân chỉ gắn toà,
       chưa gắn căn — 41 toà trong hệ thống chưa có danh sách căn) → tra thẳng
       ``Building`` → trả địa chỉ/toạ độ của toà.
    3. Không có căn hộ, không có toà, nhưng ``user.address`` khác rỗng → trả cột
       riêng của user (hộ dân lẻ trên phố, có toạ độ riêng).
    4. Không có gì → ``("", None, None)``.

    Thuần đọc, không ghi CSDL.
    """
    if user.unit_id is not None:
        unit = session.get(Unit, user.unit_id)
        if unit is not None:
            building = session.get(Building, unit.building_id)
            if building is not None:
                return building.address, building.lat, building.lng

    if user.building_id is not None:
        building = session.get(Building, user.building_id)
        if building is not None:
            return building.address, building.lat, building.lng

    if user.address:
        return user.address, user.lat, user.lng

    return "", None, None


def co_noi_o(session: Session, user: User) -> bool:
    """Người này có biết nơi ở hay không (có căn hộ hoặc có địa chỉ riêng)."""
    dia_chi, _, _ = noi_o_cua(session, user)
    return bool(dia_chi)
