"""Gói P42 — thống kê thùng phải đếm cả nhóm "chưa triển khai".

P39 thêm trạng thái `chua_trien_khai` (thùng `deployment_status="PROPOSED"`) vào
`trang_thai_thung`, nhưng `thong_ke_thung` chưa có khoá đó nên nhóm mới rơi mất:
trên CSDL thật 70 thùng (60 PROPOSED + 10 demo) cho `tong = 70` mà bốn nhóm cộng
lại chỉ ~10 — ban quản lý không thấy 60 thùng chờ lắp thiết bị ở đâu.

Bất biến của gói: **các nhóm cộng lại phải khớp `tong`** (`binh_thuong` đếm tay
vì nó CỐ Ý không lên thẻ — hành vi cũ). Không test nào chạm mạng.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.db.models import Bin
from src.services.bins import danh_sach_thung, thong_ke_thung


def _thung(
    session: Session,
    code: str,
    *,
    deployment_status: str = "",
    last_seen_at: datetime | None = None,
    battery: float = 100.0,
    fill: float = 10.0,
) -> Bin:
    """Dựng một thùng đang hoạt động với các con số điều khiển trạng thái."""
    thung = Bin(
        code=code,
        name=f"Thùng {code}",
        deployment_status=deployment_status,
        last_seen_at=last_seen_at,
        battery_percent=battery,
        fill_percent=fill,
        is_active=True,
    )
    session.add(thung)
    session.flush()
    return thung


def test_dem_chua_trien_khai(db_session: Session) -> None:
    """3 thùng PROPOSED + 1 thùng bình thường → `chua_trien_khai == 3`."""
    now = datetime.now(UTC)
    _thung(db_session, "BIN-PROP-1", deployment_status="PROPOSED")
    _thung(db_session, "BIN-PROP-2", deployment_status="PROPOSED")
    _thung(db_session, "BIN-PROP-3", deployment_status="PROPOSED")
    _thung(db_session, "BIN-NORM", last_seen_at=now)
    db_session.commit()

    ket_qua = thong_ke_thung(db_session, now)

    assert ket_qua["chua_trien_khai"] == 3
    assert ket_qua["tong"] == 4


def test_bon_nhom_cong_lai_khop_tong(db_session: Session) -> None:
    """Chốt chặn chính: nhóm PROPOSED + offline + het_pin + can_gom + binh_thuong
    (đếm tay) cộng lại phải khớp `tong` — không thùng nào rơi mất."""
    now = datetime.now(UTC)
    _thung(db_session, "BIN-PROP", deployment_status="PROPOSED")  # chua_trien_khai
    _thung(db_session, "BIN-OFF", last_seen_at=None)  # mat_ket_noi
    _thung(db_session, "BIN-PIN", last_seen_at=now, battery=10.0)  # het_pin
    _thung(db_session, "BIN-GOM", last_seen_at=now, fill=95.0)  # can_gom
    _thung(db_session, "BIN-OK", last_seen_at=now)  # binh_thuong
    db_session.commit()

    ket_qua = thong_ke_thung(db_session, now)

    assert ket_qua["tong"] == 5
    assert ket_qua["chua_trien_khai"] == 1
    assert ket_qua["mat_ket_noi"] == 1
    assert ket_qua["het_pin"] == 1
    assert ket_qua["can_gom"] == 1
    tong_tay = (
        ket_qua["chua_trien_khai"]
        + ket_qua["can_gom"]
        + ket_qua["mat_ket_noi"]
        + ket_qua["het_pin"]
        + 1  # BIN-OK = binh_thuong — không lên thẻ, đếm tay
    )
    assert tong_tay == ket_qua["tong"], f"Nhóm cộng lại phải khớp tong: {ket_qua}"


def test_binh_thuong_van_khong_len_the(db_session: Session) -> None:
    """`binh_thuong` CỐ Ý không có trong dict — dashboard chỉ hiện nhóm cần chú ý."""
    now = datetime.now(UTC)
    _thung(db_session, "BIN-OK", last_seen_at=now)
    db_session.commit()

    ket_qua = thong_ke_thung(db_session, now)

    assert "binh_thuong" not in ket_qua
    assert ket_qua["tong"] == 1


def test_khong_co_proposed_thi_chua_trien_khai_bang_0(db_session: Session) -> None:
    """CSDL chỉ có thùng ACTIVE → `chua_trien_khai == 0`, không nổ."""
    now = datetime.now(UTC)
    _thung(db_session, "BIN-1", last_seen_at=now)
    _thung(db_session, "BIN-2", last_seen_at=now, fill=90.0)
    db_session.commit()

    ket_qua = thong_ke_thung(db_session, now)

    assert ket_qua["chua_trien_khai"] == 0
    assert ket_qua["tong"] == 2


def test_thong_ke_khop_danh_sach(db_session: Session) -> None:
    """Giữ bất biến "thẻ khớp danh sách": `tong` bằng `len(danh_sach_thung)`
    với CÙNG tham số lọc."""
    now = datetime.now(UTC)
    _thung(db_session, "BIN-PROP", deployment_status="PROPOSED")
    _thung(db_session, "BIN-OFF", last_seen_at=None)
    _thung(db_session, "BIN-OK", last_seen_at=now)
    db_session.commit()

    ket_qua = thong_ke_thung(db_session, now)
    danh_sach = danh_sach_thung(db_session, now)

    assert ket_qua["tong"] == len(danh_sach)
