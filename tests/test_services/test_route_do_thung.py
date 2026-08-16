"""Đổ thùng xong thì mức rác về 0; báo sự cố thì không."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import STOP_KIND_THUNG, AuditLog, Bin, PickupRoute, RouteStop, User, utcnow
from src.services import bins, route_planner


def _dung_canh(db_session: Session, fill: float = 95.0) -> tuple[RouteStop, Bin, User]:
    thung = Bin(
        code="T-DO-01",
        name="Thùng thử đổ",
        lat=21.0285,
        lng=105.8542,
        capacity_liters=240.0,
        fill_percent=fill,
        battery_percent=88.0,
        last_seen_at=utcnow(),
        is_active=True,
    )
    nhan_vien = User(email="thu-gom@test.vn", full_name="Nhân viên thu gom", role="cleaner", password_hash="x")
    tuyen = PickupRoute(service_date=date.today(), window="sang", status="approved")
    db_session.add_all([thung, nhan_vien, tuyen])
    db_session.flush()
    diem = RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_THUNG, bin_id=thung.id, seq=1)
    db_session.add(diem)
    db_session.flush()
    return diem, thung, nhan_vien


def test_do_xong_thi_muc_rac_ve_khong(db_session: Session) -> None:
    diem, thung, nhan_vien = _dung_canh(db_session)

    route_planner.complete_stop(db_session, stop=diem, actor=nhan_vien)

    assert thung.fill_percent == 0.0
    assert diem.done_at is not None


def test_do_xong_thi_co_mot_dong_reading_nguon_manual(db_session: Session) -> None:
    """Dòng reading chính là bằng chứng ai đổ, lúc nào — không gán lén fill_percent."""
    diem, thung, nhan_vien = _dung_canh(db_session)

    route_planner.complete_stop(db_session, stop=diem, actor=nhan_vien)

    lich_su = bins.lich_su_readings(db_session, thung.id, limit=5)
    assert lich_su
    assert lich_su[0]["source"] == "manual"
    assert lich_su[0]["fill_percent"] == 0.0


def test_bao_su_co_thi_khong_ha_muc_rac(db_session: Session) -> None:
    """Kẹt nắp hay không tiếp cận được nghĩa là thùng VẪN đầy."""
    diem, thung, nhan_vien = _dung_canh(db_session)

    route_planner.complete_stop(
        db_session, stop=diem, actor=nhan_vien, issue="khong_tiep_can", issue_note="Xe đỗ chắn lối"
    )

    assert thung.fill_percent == 95.0
    assert diem.issue == "khong_tiep_can"


def test_diem_dung_loai_yeu_cau_khong_bi_anh_huong(db_session: Session) -> None:
    """Không có bin_id thì nhánh mới phải đứng ngoài hoàn toàn."""
    _, _, nhan_vien = _dung_canh(db_session)
    tuyen = PickupRoute(service_date=date.today(), window="sang", status="approved")
    db_session.add(tuyen)
    db_session.flush()
    diem = RouteStop(route_id=tuyen.id, seq=1)
    db_session.add(diem)
    db_session.flush()

    route_planner.complete_stop(db_session, stop=diem, actor=nhan_vien)

    assert diem.done_at is not None


def _cac_dong_audit_do_thung(db_session: Session) -> list[AuditLog]:
    return db_session.scalars(select(AuditLog).where(AuditLog.action == "do_thung")).all()


def test_do_thung_xong_thi_ghi_mot_dong_audit(db_session: Session) -> None:
    """Món nợ B3c: hạ mức rác là đổi dữ liệu thật nên phải có dòng kiểm toán."""
    diem, thung, nhan_vien = _dung_canh(db_session)

    route_planner.complete_stop(db_session, stop=diem, actor=nhan_vien)

    cac_dong = _cac_dong_audit_do_thung(db_session)
    assert len(cac_dong) == 1, "Đổ thùng phải ghi đúng MỘT dòng audit"
    dong = cac_dong[0]
    assert dong.actor_id == nhan_vien.id, "Actor phải là nhân viên đã đổ"
    assert dong.entity == "bin"
    assert dong.entity_id == str(thung.id)
    assert dong.detail["fill_percent_sau"] == 0.0


def test_bao_su_co_thi_khong_ghi_audit_do_thung(db_session: Session) -> None:
    """Báo sự cố thì mức rác không hạ, nên cũng không có việc gì để ghi."""
    diem, _thung, nhan_vien = _dung_canh(db_session)

    route_planner.complete_stop(
        db_session, stop=diem, actor=nhan_vien, issue="khong_tiep_can", issue_note="Xe đỗ chắn lối"
    )

    assert _cac_dong_audit_do_thung(db_session) == []


def test_diem_dung_loai_yeu_cau_khong_ghi_audit_do_thung(db_session: Session) -> None:
    """Điểm dừng yêu cầu cư dân không hạ mức rác thùng nào, nên không có dòng đổ thùng."""
    _, _, nhan_vien = _dung_canh(db_session)
    tuyen = PickupRoute(service_date=date.today(), window="sang", status="approved")
    db_session.add(tuyen)
    db_session.flush()
    diem = RouteStop(route_id=tuyen.id, seq=1)
    db_session.add(diem)
    db_session.flush()

    route_planner.complete_stop(db_session, stop=diem, actor=nhan_vien)

    assert _cac_dong_audit_do_thung(db_session) == []
