"""Test nghiệp vụ sự cố thu gom & xác nhận hoàn thành chuyến (Gói P73)."""

from __future__ import annotations

import itertools
from datetime import date

import pytest
from sqlalchemy import select

from src.db.models import (
    DiemThuongLog,
    Notification,
    PickupRoute,
    RouteStop,
    User,
)
from src.services import su_co_thu_gom

_ma_dem = itertools.count(1)


def _tao_nguoi(session, role: str, organization_id: int | None = None) -> User:
    user = User(
        email=f"{role}-{next(_ma_dem)}@test.vn",
        full_name=f"Người {role}",
        role=role,
        password_hash="x",
        organization_id=organization_id,
    )
    session.add(user)
    session.flush()
    return user


def _tao_tuyen(session, team_id: int | None, status: str = "done") -> PickupRoute:
    tuyen = PickupRoute(service_date=date.today(), window="sang", team_id=team_id, status=status)
    session.add(tuyen)
    session.flush()
    return tuyen


def _tao_diem(session, route_id: int, done_at=None) -> RouteStop:
    diem = RouteStop(route_id=route_id, seq=1, done_at=done_at)
    session.add(diem)
    session.flush()
    return diem


# 1. bao_su_co tạo cho_xu_ly, không đổi trạng thái chuyến / điểm dừng ------------
def test_bao_su_co_tao_cho_xu_ly_khong_doi_trang_thai(db_session) -> None:
    nguoi = _tao_nguoi(db_session, "cleaner")
    tuyen = _tao_tuyen(db_session, team_id=nguoi.id, status="in_progress")
    diem = _tao_diem(db_session, tuyen.id, done_at=None)

    su_co = su_co_thu_gom.bao_su_co(
        db_session,
        nguoi_bao=nguoi,
        route_id=tuyen.id,
        stop_id=diem.id,
        loai="phan_loai_sai",
        mo_ta="Chủ nhà để nhầm thùng",
    )

    assert su_co.trang_thai == "cho_xu_ly"
    assert su_co.nguoi_bao_id == nguoi.id
    # Không đổi trạng thái chuyến hay điểm dừng.
    assert db_session.get(PickupRoute, tuyen.id).status == "in_progress"
    assert db_session.get(RouteStop, diem.id).done_at is None


# 2. loai lạ → ném lỗi ---------------------------------------------------------
def test_bao_su_co_loai_la_bi_tu_choi(db_session) -> None:
    nguoi = _tao_nguoi(db_session, "cleaner")
    tuyen = _tao_tuyen(db_session, team_id=nguoi.id)


    with pytest.raises(ValueError):
        su_co_thu_gom.bao_su_co(
            db_session,
            nguoi_bao=nguoi,
            route_id=tuyen.id,
            stop_id=None,
            loai="bat_ko_ton_tai",
            mo_ta="x",
        )


# 3. stop_id không thuộc route_id → từ chối -----------------------------------
def test_bao_su_co_stop_khong_thuoc_tuyen(db_session) -> None:
    nguoi = _tao_nguoi(db_session, "cleaner")
    tuyen1 = _tao_tuyen(db_session, team_id=nguoi.id)
    tuyen2 = _tao_tuyen(db_session, team_id=nguoi.id)
    diem2 = _tao_diem(db_session, tuyen2.id)


    with pytest.raises(ValueError):
        su_co_thu_gom.bao_su_co(
            db_session,
            nguoi_bao=nguoi,
            route_id=tuyen1.id,
            stop_id=diem2.id,
            loai="khong_tiep_can",
            mo_ta="x",
        )


# 4. Người không được giao chuyến → từ chối -----------------------------------
def test_bao_su_co_nguoi_khong_duoc_giao_tuyen(db_session) -> None:
    nguoi_a = _tao_nguoi(db_session, "cleaner")
    nguoi_b = _tao_nguoi(db_session, "cleaner")
    tuyen = _tao_tuyen(db_session, team_id=nguoi_a.id)


    with pytest.raises(ValueError):
        su_co_thu_gom.bao_su_co(
            db_session,
            nguoi_bao=nguoi_b,
            route_id=tuyen.id,
            stop_id=None,
            loai="thung_day",
            mo_ta="x",
        )


# 5. xu_ly_su_co(chap_nhan=True) → da_xu_ly, có xu_ly_luc, đúng 1 Notification -
def test_xu_ly_su_co_chap_nhan_tao_mot_thong_bao(db_session) -> None:
    nguoi_bao = _tao_nguoi(db_session, "cleaner")
    nguoi_duyet = _tao_nguoi(db_session, "manager")
    tuyen = _tao_tuyen(db_session, team_id=nguoi_bao.id)
    su_co = su_co_thu_gom.bao_su_co(
        db_session, nguoi_bao=nguoi_bao, route_id=tuyen.id, stop_id=None,
        loai="phan_loai_sai", mo_ta="x",
    )

    ket_qua = su_co_thu_gom.xu_ly_su_co(
        db_session, nguoi_xu_ly=nguoi_duyet, su_co_id=su_co.id, chap_nhan=True,
        ghi_chu="Đã kiểm tra",
    )

    assert ket_qua.trang_thai == "da_xu_ly"
    assert ket_qua.xu_ly_luc is not None
    assert ket_qua.nguoi_xu_ly_id == nguoi_duyet.id
    # C3: bao_su_co nay cũng notify manager cùng đơn vị, nhưng notification của
    # xu_ly_su_co là dành riêng cho người báo → lọc user_id để đếm đúng 1 cái
    # do chính xu_ly_su_co sinh ra (không làm yếu test).
    cac_tb = db_session.scalars(
        select(Notification).where(
            Notification.entity == "su_co_thu_gom",
            Notification.entity_id == str(su_co.id),
            Notification.user_id == nguoi_bao.id,
        )
    ).all()
    assert len(cac_tb) == 1


# 6. Xử lý lần hai → từ chối ---------------------------------------------------
def test_xu_ly_su_co_hai_lan_bi_tu_choi(db_session) -> None:
    nguoi_bao = _tao_nguoi(db_session, "cleaner")
    nguoi_duyet = _tao_nguoi(db_session, "manager")
    tuyen = _tao_tuyen(db_session, team_id=nguoi_bao.id)
    su_co = su_co_thu_gom.bao_su_co(
        db_session, nguoi_bao=nguoi_bao, route_id=tuyen.id, stop_id=None,
        loai="phan_loai_sai", mo_ta="x",
    )
    su_co_thu_gom.xu_ly_su_co(
        db_session, nguoi_xu_ly=nguoi_duyet, su_co_id=su_co.id, chap_nhan=True,
    )


    with pytest.raises(ValueError):
        su_co_thu_gom.xu_ly_su_co(
            db_session, nguoi_xu_ly=nguoi_duyet, su_co_id=su_co.id, chap_nhan=False,
        )


# 7. Thông báo ném lỗi → sự cố vẫn xử lý xong --------------------------------
def test_xu_ly_su_co_thong_bao_loi_van_xu_ly_xong(db_session, monkeypatch) -> None:
    nguoi_bao = _tao_nguoi(db_session, "cleaner")
    nguoi_duyet = _tao_nguoi(db_session, "manager")
    tuyen = _tao_tuyen(db_session, team_id=nguoi_bao.id)
    su_co = su_co_thu_gom.bao_su_co(
        db_session, nguoi_bao=nguoi_bao, route_id=tuyen.id, stop_id=None,
        loai="phan_loai_sai", mo_ta="x",
    )

    original_add = db_session.add

    def fake_add(obj):
        if isinstance(obj, Notification):
            raise RuntimeError("simulated notification failure")
        return original_add(obj)

    monkeypatch.setattr(db_session, "add", fake_add)

    ket_qua = su_co_thu_gom.xu_ly_su_co(
        db_session, nguoi_xu_ly=nguoi_duyet, su_co_id=su_co.id, chap_nhan=True,
    )
    assert ket_qua.trang_thai == "da_xu_ly"


# 8. danh_sach_su_co: người thu gom A không thấy sự cố của B ------------------
def test_danh_sach_su_co_nguoi_thu_gom_khong_thay_cua_nguoi_khac(db_session) -> None:
    a = _tao_nguoi(db_session, "cleaner")
    b = _tao_nguoi(db_session, "cleaner")
    tuyen_a = _tao_tuyen(db_session, team_id=a.id)
    tuyen_b = _tao_tuyen(db_session, team_id=b.id)
    su_co_a = su_co_thu_gom.bao_su_co(
        db_session, nguoi_bao=a, route_id=tuyen_a.id, stop_id=None,
        loai="phan_loai_sai", mo_ta="x",
    )
    su_co_thu_gom.bao_su_co(
        db_session, nguoi_bao=b, route_id=tuyen_b.id, stop_id=None,
        loai="thung_day", mo_ta="y",
    )

    ds_a = su_co_thu_gom.danh_sach_su_co(db_session, nguoi_xem=a)
    assert [s.id for s in ds_a] == [su_co_a.id]


# 9. xac_nhan khi chuyến chưa done → từ chối ---------------------------------
def test_xac_nhan_chuyen_chua_done_bi_tu_choi(db_session) -> None:
    nguoi_duyet = _tao_nguoi(db_session, "manager")
    tuyen = _tao_tuyen(db_session, team_id=None, status="in_progress")


    with pytest.raises(ValueError):
        su_co_thu_gom.xac_nhan_hoan_thanh_chuyen(
            db_session, nguoi_xac_nhan=nguoi_duyet, route_id=tuyen.id,
        )


# 10. Còn sự cố cho_xu_ly → từ chối xác nhận ---------------------------------
def test_xac_nhan_chuyen_con_su_co_treo_bi_tu_choi(db_session) -> None:
    nguoi_bao = _tao_nguoi(db_session, "cleaner")
    nguoi_duyet = _tao_nguoi(db_session, "manager")
    tuyen = _tao_tuyen(db_session, team_id=nguoi_bao.id, status="done")
    su_co_thu_gom.bao_su_co(
        db_session, nguoi_bao=nguoi_bao, route_id=tuyen.id, stop_id=None,
        loai="phan_loai_sai", mo_ta="x",
    )


    with pytest.raises(ValueError):
        su_co_thu_gom.xac_nhan_hoan_thanh_chuyen(
            db_session, nguoi_xac_nhan=nguoi_duyet, route_id=tuyen.id,
        )


# 11. Xử lý hết sự cố rồi xác nhận → ghi xac_nhan_boi/luc, status vẫn done ----
def test_xu_ly_het_su_co_roi_xac_nhan_ghi_moc(db_session) -> None:
    nguoi_bao = _tao_nguoi(db_session, "cleaner")
    nguoi_duyet = _tao_nguoi(db_session, "manager")
    tuyen = _tao_tuyen(db_session, team_id=nguoi_bao.id, status="done")
    su_co = su_co_thu_gom.bao_su_co(
        db_session, nguoi_bao=nguoi_bao, route_id=tuyen.id, stop_id=None,
        loai="phan_loai_sai", mo_ta="x",
    )
    su_co_thu_gom.xu_ly_su_co(
        db_session, nguoi_xu_ly=nguoi_duyet, su_co_id=su_co.id, chap_nhan=True,
    )

    ket_qua = su_co_thu_gom.xac_nhan_hoan_thanh_chuyen(
        db_session, nguoi_xac_nhan=nguoi_duyet, route_id=tuyen.id,
    )
    assert ket_qua.xac_nhan_boi == nguoi_duyet.id
    assert ket_qua.xac_nhan_luc is not None
    assert ket_qua.status == "done"  # KHÔNG đổi status


# 12. Xác nhận lần hai → từ chối ----------------------------------------------
def test_xac_nhan_chuyen_hai_lan_bi_tu_choi(db_session) -> None:
    nguoi_bao = _tao_nguoi(db_session, "cleaner")
    nguoi_duyet = _tao_nguoi(db_session, "manager")
    tuyen = _tao_tuyen(db_session, team_id=nguoi_bao.id, status="done")
    su_co = su_co_thu_gom.bao_su_co(
        db_session, nguoi_bao=nguoi_bao, route_id=tuyen.id, stop_id=None,
        loai="phan_loai_sai", mo_ta="x",
    )
    su_co_thu_gom.xu_ly_su_co(
        db_session, nguoi_xu_ly=nguoi_duyet, su_co_id=su_co.id, chap_nhan=True,
    )
    su_co_thu_gom.xac_nhan_hoan_thanh_chuyen(
        db_session, nguoi_xac_nhan=nguoi_duyet, route_id=tuyen.id,
    )


    with pytest.raises(ValueError):
        su_co_thu_gom.xac_nhan_hoan_thanh_chuyen(
            db_session, nguoi_xac_nhan=nguoi_duyet, route_id=tuyen.id,
        )


# 13. Không ghi vào green_points hay diem_thuong_log -------------------------
def test_khong_ghi_diem_thuong_hay_log(db_session) -> None:
    nguoi_bao = _tao_nguoi(db_session, "cleaner")
    nguoi_duyet = _tao_nguoi(db_session, "manager")
    tuyen = _tao_tuyen(db_session, team_id=nguoi_bao.id, status="done")
    su_co = su_co_thu_gom.bao_su_co(
        db_session, nguoi_bao=nguoi_bao, route_id=tuyen.id, stop_id=None,
        loai="phan_loai_sai", mo_ta="x",
    )
    su_co_thu_gom.xu_ly_su_co(
        db_session, nguoi_xu_ly=nguoi_duyet, su_co_id=su_co.id, chap_nhan=True,
    )
    su_co_thu_gom.xac_nhan_hoan_thanh_chuyen(
        db_session, nguoi_xac_nhan=nguoi_duyet, route_id=tuyen.id,
    )

    assert db_session.get(User, nguoi_bao.id).green_points == 0
    assert db_session.get(User, nguoi_duyet.id).green_points == 0
    assert db_session.scalars(select(DiemThuongLog)).all() == []
