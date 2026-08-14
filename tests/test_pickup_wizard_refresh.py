"""Guard test cho gói P45a — bỏ món giả "Tủ gỗ nhỏ" + hàng đợi BQL tự làm mới.

Không test nào chạm trình duyệt hay mạng; quét văn bản file `.tsx` (khuôn
`test_di_tru_trang_thai.py`). Không có trình chạy test JS trong dự án nên guard
Python này là chỗ duy nhất khoá lại các hồi quy này.
"""

from __future__ import annotations

from pathlib import Path

GOC_DU_AN = Path(__file__).resolve().parents[1]

PICKUP_WIZARD = GOC_DU_AN / "frontend" / "src" / "components" / "resident" / "pickup-wizard.tsx"
QUEUES = GOC_DU_AN / "frontend" / "src" / "components" / "manager" / "queues.tsx"
CONSOLE = GOC_DU_AN / "frontend" / "src" / "components" / "manager" / "console.tsx"


def test_khong_con_mon_gia() -> None:
    """`pickup-wizard.tsx` không còn chuỗi "Tủ gỗ nhỏ" — món giả tự chèn đã bỏ."""
    noi_dung = PICKUP_WIZARD.read_text(encoding="utf-8")
    assert "Tủ gỗ nhỏ" not in noi_dung


def test_van_con_guard_rong() -> None:
    """Guard `mon.length > 0` (chặn Gửi khi danh sách rỗng) phải còn nguyên."""
    noi_dung = PICKUP_WIZARD.read_text(encoding="utf-8")
    assert "mon.length > 0" in noi_dung


def test_pickup_queue_polling() -> None:
    """`PickupQueue` tự làm mới mỗi 30s — cư dân vừa gửi là BQL thấy ngay."""
    noi_dung = QUEUES.read_text(encoding="utf-8")
    assert "setInterval(tai, 30000)" in noi_dung
    assert "clearInterval(id)" in noi_dung, "Phải dọn interval khi unmount — không thì request nhân bội"


def test_console_badge_polling() -> None:
    """Badge đếm trên console cũng làm mới mỗi 30s."""
    noi_dung = CONSOLE.read_text(encoding="utf-8")
    assert "setInterval(lay, 30000)" in noi_dung
    assert "clearInterval(id)" in noi_dung, "Phải dọn interval khi unmount"
