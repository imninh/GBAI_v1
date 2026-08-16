"""Tách "chưa triển khai" khỏi "mất kết nối" trên bản đồ thùng (gói P39).

60 thùng GIS vừa nhập (P30) đều `deployment_status = PROPOSED`, chưa lắp thiết
bị nên `last_seen_at = None` — trước gói này chúng bị gộp vào "mất kết nối" lẫn
với những thùng đã lắp mà hỏng thật. Test 1 (PROPOSED + `last_seen_at=None`)
là chốt chặn thứ tự: nếu nhánh mới bị đặt SAU phép kiểm `last_seen_at is None`
thì nó không bao giờ chạy và gói vô tác dụng.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from src.db.models import Bin
from src.services.bins import trang_thai_thung


def _thung(
    db_session: Session,
    code: str,
    *,
    deployment_status: str = "",
    last_seen_at: datetime | None = None,
    fill: float = 0.0,
    battery: float = 100.0,
) -> Bin:
    thung = Bin(
        code=code,
        name=f"Thùng {code}",
        deployment_status=deployment_status,
        fill_percent=fill,
        battery_percent=battery,
        last_seen_at=last_seen_at,
        is_active=True,
    )
    db_session.add(thung)
    db_session.flush()
    return thung


def test_proposed_thi_chua_trien_khai(db_session: Session) -> None:
    """Thùng PROPOSED, `last_seen_at=None` → `chua_trien_khai`, KHÔNG phải `mat_ket_noi`."""
    thung = _thung(db_session, "GIS-001", deployment_status="PROPOSED", last_seen_at=None)

    assert trang_thai_thung(thung, datetime.now(UTC)) == "chua_trien_khai"


def test_proposed_bo_qua_ca_fill_va_pin(db_session: Session) -> None:
    """Nhánh PROPOSED thắng mọi thứ — kể cả fill 95 / pin 5 (mọi con số đều vô nghĩa khi chưa lắp)."""
    thung = _thung(db_session, "GIS-002", deployment_status="PROPOSED", fill=95.0, battery=5.0)

    assert trang_thai_thung(thung, datetime.now(UTC)) == "chua_trien_khai"


def test_deploy_rong_van_theo_logic_cu(db_session: Session) -> None:
    """`deployment_status=""` (thùng demo/thật) + `last_seen_at=None` → vẫn `mat_ket_noi` như hôm nay."""
    thung = _thung(db_session, "BIN-DEMO", deployment_status="", last_seen_at=None)

    assert trang_thai_thung(thung, datetime.now(UTC)) == "mat_ket_noi"


def test_active_offline_van_mat_ket_noi(db_session: Session) -> None:
    """`deployment_status="ACTIVE"` mà quá hạn → `mat_ket_noi` — đã lắp mà hỏng thật, phân biệt được với PROPOSED."""
    thung = _thung(
        db_session,
        "BIN-ACTIVE-OFF",
        deployment_status="ACTIVE",
        last_seen_at=datetime.now(UTC) - timedelta(days=3),
    )

    assert trang_thai_thung(thung, datetime.now(UTC)) == "mat_ket_noi"


def test_active_binh_thuong(db_session: Session) -> None:
    """`deployment_status="ACTIVE"`, vừa báo về, pin/fill tốt → `binh_thuong`."""
    thung = _thung(
        db_session,
        "BIN-ACTIVE-OK",
        deployment_status="ACTIVE",
        last_seen_at=datetime.now(UTC),
        fill=40.0,
        battery=90.0,
    )

    assert trang_thai_thung(thung, datetime.now(UTC)) == "binh_thuong"


def test_60_thung_gis_deu_chua_trien_khai(db_session: Session) -> None:
    """Cụm giống bộ GIS Hà Nội (PROPOSED, không có reading) → tất cả chưa triển khai, 0 cái mất kết nối."""
    for i in range(1, 4):
        _thung(db_session, f"GIS-0{i:02d}", deployment_status="PROPOSED", last_seen_at=None)
    db_session.flush()

    cac_trang_thai = {t.code: trang_thai_thung(t, datetime.now(UTC)) for t in db_session.query(Bin).all()}
    assert all(trang_thai == "chua_trien_khai" for trang_thai in cac_trang_thai.values()), cac_trang_thai
    assert "mat_ket_noi" not in cac_trang_thai.values(), "Không thùng GIS nào được tính là mất kết nối"
