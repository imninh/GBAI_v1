"""Test gói P80 — kíp thu gom hai người + lên lịch tự động từ đầu tuần.

Mọi ngày/tuần trong test đều TRUYỀN VÀO, không dùng ``date.today()``.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from src.config import reset_settings_cache
from src.db.models import Building, PickupRoute, RouteThanhVien, Unit, User
from src.services import kip_thu_gom, lich_tu_dong, pickup
from src.services.kip_thu_gom import SO_NGUOI_MOI_KIP
from src.services.pickup_lifecycle import CHO_DUYET


@pytest.fixture(autouse=True)
def _reset_config():
    reset_settings_cache()
    yield
    reset_settings_cache()


# ---------------------------------------------------------------------------
# Fixtures dùng chung
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(db_session):
    u = User(email="mgr80@demo.vn", full_name="BQL", role="manager", password_hash="x")
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture
def building(db_session):
    b = Building(code="B80", name="Toà 80", lat=21.0, lng=105.0)
    db_session.add(b)
    db_session.flush()
    return b


@pytest.fixture
def unit(db_session, building):
    u = Unit(building_id=building.id, code="U80-101")
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture
def cleaners_3(db_session):
    """3 nhân viên thu gom (ít hơn SO_NGUOI_MOI_KIP đối với cycle_lớn)."""
    cs = []
    for i in range(3):
        u = User(email=f"cleaner{i+1}@demo.vn", full_name=f"Cleaner {i+1}", role="cleaner", password_hash="x")
        db_session.add(u)
        cs.append(u)
    db_session.flush()
    return cs


@pytest.fixture
def cleaners_6(db_session):
    """6 nhân viên thu gom (cho test round-robin)."""
    cs = []
    for i in range(6):
        u = User(email=f"cleaner{i+1}@demo.vn", full_name=f"Cleaner {i+1}", role="cleaner", password_hash="x")
        db_session.add(u)
        cs.append(u)
    db_session.flush()
    return cs


@pytest.fixture
def route(db_session):
    """Chuyến proposed trống."""
    r = PickupRoute(service_date=date(2026, 8, 24), window="18:00-20:00", status="proposed")
    db_session.add(r)
    db_session.flush()
    return r


# ---------------------------------------------------------------------------
# Test 1–6: gan_kip
# ---------------------------------------------------------------------------


def test_gan_kip_dung_2_nguoi_ghi_2_dong(db_session, route, cleaners_6):
    """#1: gán đúng 2 người → 2 dòng RouteThanhVien, team_id = trưởng kíp."""
    u1, u2 = cleaners_6[0], cleaners_6[1]
    kip_thu_gom.gan_kip(
        db_session,
        actor=cleaners_6[0],
        route_id=route.id,
        user_ids=[u1.id, u2.id],
        truong_kip_id=u1.id,
    )
    rows = db_session.execute(
        select(RouteThanhVien).where(RouteThanhVien.route_id == route.id)
    ).scalars().all()
    assert len(rows) == 2
    assert route.team_id == u1.id


def test_gan_kip_1_nguoi_bi_tu_choi(db_session, route, cleaners_6):
    """#2a: gán 1 người → từ chối."""
    with pytest.raises(ValueError, match="2 người"):
        kip_thu_gom.gan_kip(
            db_session,
            actor=cleaners_6[0],
            route_id=route.id,
            user_ids=[cleaners_6[0].id],
        )


def test_gan_kip_3_nguoi_bi_tu_choi(db_session, route, cleaners_6):
    """#2b: gán 3 người → từ chối."""
    with pytest.raises(ValueError, match="2 người"):
        kip_thu_gom.gan_kip(
            db_session,
            actor=cleaners_6[0],
            route_id=route.id,
            user_ids=[c.id for c in cleaners_6[:3]],
        )


def test_gan_kip_trung_nguoi_bi_tu_choi(db_session, route, cleaners_6):
    """#3: gán cùng một người hai lần → từ chối."""
    with pytest.raises(ValueError, match="một người hai lần"):
        kip_thu_gom.gan_kip(
            db_session,
            actor=cleaners_6[0],
            route_id=route.id,
            user_ids=[cleaners_6[0].id, cleaners_6[0].id],
        )


def test_gan_kip_nguoi_khong_phai_cleaner_bi_tu_choi(db_session, route, cleaners_6, manager):
    """#4: gán người không phải nhân viên thu gom → từ chối."""
    with pytest.raises(ValueError, match="hoạt động"):
        kip_thu_gom.gan_kip(
            db_session,
            actor=cleaners_6[0],
            route_id=route.id,
            user_ids=[cleaners_6[0].id, manager.id],
        )


def test_gan_lai_kip_con_dung_nguoi_moi(db_session, route, cleaners_6):
    """#5: gán lại → còn đúng 2 dòng, đúng người mới, team_id cập nhật."""
    kip_thu_gom.gan_kip(
        db_session,
        actor=cleaners_6[0],
        route_id=route.id,
        user_ids=[cleaners_6[0].id, cleaners_6[1].id],
    )
    assert route.team_id == cleaners_6[0].id

    kip_thu_gom.gan_kip(
        db_session,
        actor=cleaners_6[0],
        route_id=route.id,
        user_ids=[cleaners_6[2].id, cleaners_6[3].id],
    )
    rows = db_session.execute(
        select(RouteThanhVien).where(RouteThanhVien.route_id == route.id)
    ).scalars().all()
    assert len(rows) == 2
    assert {r.user_id for r in rows} == {cleaners_6[2].id, cleaners_6[3].id}
    assert route.team_id == cleaners_6[2].id


def test_chuyen_done_khong_doi_kip(db_session, cleaners_6):
    """#6: chuyến done hoặc đã xác nhận → từ chối đổi kíp."""
    r = PickupRoute(service_date=date(2026, 8, 25), window="18:00-20:00", status="done")
    db_session.add(r)
    db_session.flush()

    with pytest.raises(ValueError, match="hoàn tất"):
        kip_thu_gom.gan_kip(
            db_session,
            actor=cleaners_6[0],
            route_id=r.id,
            user_ids=[cleaners_6[0].id, cleaners_6[1].id],
        )

    r2 = PickupRoute(
        service_date=date(2026, 8, 26), window="18:00-20:00", status="proposed",
        xac_nhan_boi=cleaners_6[0].id,
    )
    db_session.add(r2)
    db_session.flush()

    with pytest.raises(ValueError, match="xác nhận"):
        kip_thu_gom.gan_kip(
            db_session,
            actor=cleaners_6[0],
            route_id=r2.id,
            user_ids=[cleaners_6[0].id, cleaners_6[1].id],
        )


def test_kip_cua_chuyen_khong_tra_sdt_email(db_session, route, cleaners_6):
    """#7: kip_cua_chuyen không trả số điện thoại, không trả email."""
    kip_thu_gom.gan_kip(
        db_session,
        actor=cleaners_6[0],
        route_id=route.id,
        user_ids=[cleaners_6[0].id, cleaners_6[1].id],
    )
    thanh_vien = kip_thu_gom.kip_cua_chuyen(db_session, route_id=route.id)
    assert len(thanh_vien) == 2
    for tv in thanh_vien:
        assert "phone" not in tv
        assert "email" not in tv
        assert "id" in tv
        assert "full_name" in tv
        assert "vai_tro" in tv


# ---------------------------------------------------------------------------
# Test 8–10: chon_kip_tu_dong
# ---------------------------------------------------------------------------


def test_chon_kip_tat_dinh_goi_2_lan_ra_ket_qua_giong(db_session, cleaners_6):
    """#8: chon_kip_tu_dong tất định — gọi hai lần cùng đầu vào ra cùng kết quả."""
    tuan = date(2026, 8, 24)
    da_gan1: dict[int, int] = {}
    r1 = kip_thu_gom.chon_kip_tu_dong(db_session, tuan_bat_dau=tuan, da_gan=da_gan1)

    da_gan2: dict[int, int] = {}
    r2 = kip_thu_gom.chon_kip_tu_dong(db_session, tuan_bat_dau=tuan, da_gan=da_gan2)

    assert r1 == r2


def test_chi_1_nhan_vien_tra_none(db_session):
    """#9: chỉ có 1 nhân viên → trả None, không tạo kíp thiếu người."""
    u = User(email="only1@demo.vn", full_name="Only One", role="cleaner", password_hash="x")
    db_session.add(u)
    db_session.flush()

    tuan = date(2026, 8, 24)
    da_gan: dict[int, int] = {}
    result = kip_thu_gom.chon_kip_tu_dong(db_session, tuan_bat_dau=tuan, da_gan=da_gan)
    assert result is None


def test_6_nhan_vien_3_chuyen_moi_nguoi_dung_1(db_session, cleaners_6):
    """#10: 6 nhân viên, 3 chuyến → mỗi người đúng một chuyến."""
    tuan = date(2026, 8, 24)
    da_gan: dict[int, int] = {}
    all_chosen: list[list[int]] = []

    for _ in range(3):
        chon = kip_thu_gom.chon_kip_tu_dong(db_session, tuan_bat_dau=tuan, da_gan=da_gan)
        assert chon is not None
        all_chosen.extend(chon)

    from collections import Counter
    dem = Counter(all_chosen)
    assert len(dem) == 6
    for uid, count in dem.items():
        assert count == 1, f"User {uid} được chọn {count} lần, mong 1"


# ---------------------------------------------------------------------------
# Test 11–16: tao_lich_tuan
# ---------------------------------------------------------------------------


def _tao_lich(db_session, building_id, weekdays, window, category_code="recyclable"):
    from src.db.models import CollectionSchedule
    lich = CollectionSchedule(building_id=building_id, category_code=category_code,
                              weekdays=weekdays, window=window)
    db_session.add(lich)
    db_session.flush()
    return lich


def _tao_yeu_cau(db_session, building, unit, ngay, window, prefix="t"):
    manager = User(email=f"mgr_{prefix}@demo.vn", full_name="BQL", role="manager", password_hash="x")
    db_session.add(manager)
    db_session.flush()
    resident = User(email=f"res_{prefix}@demo.vn", full_name="Cư dân", role="resident",
                    password_hash="x", unit_id=unit.id)
    db_session.add(resident)
    db_session.flush()
    req = pickup.create_pickup_request(
        db_session,
        resident=resident,
        items=[{"name": "Giấy", "category_code": "paper", "qty": 1}],
        est_weight_kg=10.0,
        preferred_date=ngay,
        preferred_window=window,
    )
    if req.status == CHO_DUYET:
        pickup.review_pickup(db_session, request=req, actor=manager, action="approve")
    db_session.flush()
    return req


def test_tao_lich_tuan_chi_tao_cho_ngay_co_lich(db_session, building, unit, cleaners_6):
    """#11: tao_lich_tuan tạo chuyến cho đúng những ngày có lịch, không tạo cho ngày không có."""
    tuan = date(2026, 8, 24)  # Thứ 2
    window = "18:00-20:00"

    # Chỉ có lịch Thứ 2 và Thứ 4
    _tao_lich(db_session, building.id, weekdays=[0], window=window)
    _tao_lich(db_session, building.id, weekdays=[2], window=window)

    # Tạo yêu cầu cho cả 7 ngày
    for i in range(7):
        ngay = tuan + __import__("datetime").timedelta(days=i)
        _tao_yeu_cau(db_session, building, unit, ngay, window, prefix=f"day{i}")

    db_session.commit()

    actor = User(email="actor@demo.vn", full_name="Actor", role="manager", password_hash="x")
    db_session.add(actor)
    db_session.flush()

    lich_tu_dong.tao_lich_tuan(db_session, actor=actor, tuan_bat_dau=tuan)
    db_session.flush()

    # Có chuyến cho T2 và T4
    t2 = tuan + __import__("datetime").timedelta(days=0)
    t4 = tuan + __import__("datetime").timedelta(days=2)
    assert db_session.scalar(select(PickupRoute.id).where(PickupRoute.service_date == t2).limit(1)) is not None
    assert db_session.scalar(select(PickupRoute.id).where(PickupRoute.service_date == t4).limit(1)) is not None

    # Không có chuyến cho T3, T5, T6, CN, T7
    for skip_day in [1, 3, 4, 5, 6]:
        ngay = tuan + __import__("datetime").timedelta(days=skip_day)
        count = db_session.scalar(
            select(PickupRoute.id).where(PickupRoute.service_date == ngay).limit(1)
        )
        # Nếu lịch T2/T4 tạo route trùng window → pickup request đúng ngày đó vẫn tạo route
        # Nhưng windows khác nhau → không trùng
        assert count is None, f"Ngày {ngay} không có lịch nhưng vẫn tạo route"


def test_tao_lich_tuan_hai_lan_khong_tang(db_session, building, unit, cleaners_6):
    """#12: gọi hai lần liên tiếp → tổng số PickupRoute không tăng lần thứ hai."""
    tuan = date(2026, 8, 24)
    window = "18:00-20:00"
    _tao_lich(db_session, building.id, weekdays=[0], window=window)
    _tao_yeu_cau(db_session, building, unit, tuan, window, prefix="dup")

    db_session.commit()
    actor = User(email="actor@demo.vn", full_name="Actor", role="manager", password_hash="x")
    db_session.add(actor)
    db_session.flush()

    lich_tu_dong.tao_lich_tuan(db_session, actor=actor, tuan_bat_dau=tuan)
    so_sau_lan1 = db_session.scalar(select(PickupRoute.id).limit(1)) and db_session.query(PickupRoute).count()
    assert so_sau_lan1 >= 1

    ket2 = lich_tu_dong.tao_lich_tuan(db_session, actor=actor, tuan_bat_dau=tuan)
    so_sau_lan2 = db_session.query(PickupRoute).count()
    assert so_sau_lan2 == so_sau_lan1
    assert ket2["so_chuyen_tao"] == 0
    assert ket2["so_lich_bo_vi_da_co"] >= 1


def test_tao_lich_tuan_khong_trung_tao_chuyen_tu_lich(db_session, building, unit, cleaners_6):
    """#13: tao_lich_tuan không tạo trùng chuyến do tao_chuyen_tu_lich (P72) đã tạo."""
    from datetime import datetime
    tuan = date(2026, 8, 24)
    window = "18:00-20:00"
    _tao_lich(db_session, building.id, weekdays=[0], window=window)
    _tao_yeu_cau(db_session, building, unit, tuan, window, prefix="mix")

    db_session.commit()
    actor = User(email="actor@demo.vn", full_name="Actor", role="manager", password_hash="x")
    db_session.add(actor)
    db_session.flush()

    # P72 tạo chuyến trước
    lich_tu_dong.tao_chuyen_tu_lich(
        db_session,
        bay_gio=datetime(2026, 8, 24, 17, 0),
        truoc_bao_lau_phut=60,
    )
    so_sau_p72 = db_session.query(PickupRoute).count()

    # P80 tạo sau → phải bỏ vì đã có
    ket = lich_tu_dong.tao_lich_tuan(db_session, actor=actor, tuan_bat_dau=tuan)
    so_sau_p80 = db_session.query(PickupRoute).count()
    assert so_sau_p80 == so_sau_p72
    assert ket["so_lich_bo_vi_da_co"] >= 1


def test_tao_lich_tuan_nguon_tao_va_status(db_session, building, unit, cleaners_6):
    """#14: chuyến sinh ra có nguon_tao == 'tu_dong' và status == 'proposed'."""
    tuan = date(2026, 8, 24)
    window = "18:00-20:00"
    _tao_lich(db_session, building.id, weekdays=[0], window=window)
    _tao_yeu_cau(db_session, building, unit, tuan, window, prefix="src")

    db_session.commit()
    actor = User(email="actor@demo.vn", full_name="Actor", role="manager", password_hash="x")
    db_session.add(actor)
    db_session.flush()

    lich_tu_dong.tao_lich_tuan(db_session, actor=actor, tuan_bat_dau=tuan)

    for r in db_session.scalars(select(PickupRoute)).all():
        assert r.nguon_tao == "tu_dong"
        assert r.status == "proposed"


def test_khong_du_nguoi_kip_trong_bang_tong(db_session, building, unit):
    """#15: không đủ người → chuyến vẫn tạo, kíp trống, tổng đúng ô 'chưa gán được kíp'."""
    tuan = date(2026, 8, 24)
    window = "18:00-20:00"
    _tao_lich(db_session, building.id, weekdays=[0], window=window)
    _tao_yeu_cau(db_session, building, unit, tuan, window, prefix="few")

    db_session.commit()
    actor = User(email="actor@demo.vn", full_name="Actor", role="manager", password_hash="x")
    db_session.add(actor)
    db_session.flush()

    lich_tu_dong.tao_lich_tuan(db_session, actor=actor, tuan_bat_dau=tuan)
    db_session.flush()

    so_cleaner = db_session.query(User).filter(User.role == "cleaner").count()
    so_chuyen = db_session.query(PickupRoute).filter(
        PickupRoute.nguon_tao == "tu_dong",
    ).count()
    so_da_gan_rows = db_session.query(RouteThanhVien).count()
    so_da_gan = so_da_gan_rows // SO_NGUOI_MOI_KIP if so_da_gan_rows else 0
    if so_cleaner < SO_NGUOI_MOI_KIP:
        assert so_chuyen >= 1
        assert so_da_gan == 0
    else:
        assert so_da_gan == so_chuyen


def test_tao_lich_tuan_ngay_tuan_deu_truyen_vao(db_session, building, unit, cleaners_6):
    """#16: mọi ngày/tuần trong test đều truyền vào, không dùng date.today()."""
    tuan = date(2026, 9, 7)  # Tuần khác
    window = "18:00-20:00"
    _tao_lich(db_session, building.id, weekdays=[0], window=window)
    _tao_yeu_cau(db_session, building, unit, tuan, window, prefix="sep")

    db_session.commit()
    actor = User(email="actor@demo.vn", full_name="Actor", role="manager", password_hash="x")
    db_session.add(actor)
    db_session.flush()

    ket = lich_tu_dong.tao_lich_tuan(db_session, actor=actor, tuan_bat_dau=tuan)
    assert ket["so_ngay_xet"] == 1  # Chỉ T2 có lịch
    assert ket["so_chuyen_tao"] >= 1


# ---------------------------------------------------------------------------
# E2E-03a — cleaner visibility: tuyến đã duyệt phải có kíp, và cả thành viên
# kíp (RouteThanhVien) cũng phải thấy được chuyến của mình.
# ---------------------------------------------------------------------------


def test_duyet_tuyen_thieu_kip_bi_chan(db_session, route, manager):
    """Tuyến chưa gán kíp thì KHÔNG được duyệt — approved mà team_id=None là
    tuyến vô hình với mọi cleaner và không ai nhận thông báo (E2E §8)."""
    from src.services import route_planner

    assert route.team_id is None
    with pytest.raises(ValueError, match="gán kíp"):
        route_planner.review_route(
            db_session, route=route, actor=manager, action="approve"
        )
    db_session.refresh(route)
    assert route.status == "proposed", "Bị chặn thì trạng thái không được đổi"


def test_kip_da_gan_thi_truong_va_thanh_vien_deu_thay_tuyen(db_session, route, manager, cleaners_3):
    """Sau khi gán kíp + duyệt: trưởng kíp thấy qua team_id, thành viên thấy qua
    RouteThanhVien, cleaner ngoài kíp thì không; get_route cũng phân biệt vậy."""
    from src.api.errors import ApiError
    from src.api.routers import routes as tuyen_router
    from src.services import route_planner

    truong, thanh_vien, ngoai_kip = cleaners_3
    kip_thu_gom.gan_kip(
        db_session,
        actor=manager,
        route_id=route.id,
        user_ids=[truong.id, thanh_vien.id],
        truong_kip_id=truong.id,
    )
    route_planner.review_route(db_session, route=route, actor=manager, action="approve")

    def _ids(user):
        ket = tuyen_router.list_routes(session=db_session, user=user)
        return [r["id"] for r in ket["items"]]

    assert route.id in _ids(truong), "Trưởng kíp phải thấy tuyến"
    assert route.id in _ids(thanh_vien), "Thành viên kíp cũng phải thấy tuyến"
    assert route.id not in _ids(ngoai_kip), "Cleaner ngoài kíp không được thấy"

    assert tuyen_router.get_route(route.id, session=db_session, user=truong)["id"] == route.id
    assert tuyen_router.get_route(route.id, session=db_session, user=thanh_vien)["id"] == route.id
    with pytest.raises(ApiError) as loi:
        tuyen_router.get_route(route.id, session=db_session, user=ngoai_kip)
    # 404 chứ không 403 — che luôn sự tồn tại của tuyến với kíp khác.
    assert loi.value.status_code == 404
