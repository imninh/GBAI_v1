"""Tự tạo chuyến theo lịch cố định + đánh dấu ĐẦY khi không có người thu gom.

Gói P72 — hai mảng nghiệp vụ:

1. **Tự tạo chuyến theo lịch cố định.** Hệ thống chạy định kỳ (cron ngoài gọi
   ``POST /routes/tu-dong-tao``), cách giờ thu gom trong ``collection_schedules``
   một khoảng cho trước (mặc định 60 phút) thì gộp các yêu cầu đã duyệt của
   ngày + khung giờ đó thành chuyến đề xuất (``status="proposed"``), đánh dấu
   ``nguon_tao="tu_dong"``. Chuyến vẫn phải qua người duyệt như chuyến do người
   bấm — agent không tự đổi lịch làm việc của con người.

2. **Không tìm được người vận chuyển thì báo ĐẦY.** Đặt cờ ``dat_day_thu_cong``
   cho các thùng thuộc điểm dừng của chuyến để cư dân và người thu gom không mang
   vật liệu tới. Cờ này CHỈ ảnh hưởng tới cái người dùng nhìn thấy — điểm vẫn thu
   gom theo lịch cố định, và tuyệt đối KHÔNG ghi đè số đo cảm biến của thùng.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import (
    STOP_KIND_THUNG,
    Bin,
    CollectionSchedule,
    PickupRoute,
    RouteStop,
    User,
)
from src.services import route_planner
from src.services.auth import write_audit
from src.services.kip_thu_gom import chon_kip_tu_dong, gan_kip

_LOG = logging.getLogger(__name__)

NGUON_TU_DONG = "tu_dong"


def _parse_gio_bat_dau(window: str):
    """Bóc giờ bắt đầu từ ``window`` như ``"18:00-20:00"`` → ``time(18, 0)``.

    ``window`` rỗng hoặc sai định dạng (ví dụ ``"tối"``) → trả ``None``; lịch đó
    bị bỏ qua chứ không ném lỗi làm chết cả lượt chạy.
    """
    if not window or "-" not in window:
        return None
    phan_dau = window.split("-", 1)[0].strip()
    try:
        return datetime.strptime(phan_dau, "%H:%M").time()
    except ValueError:
        return None


def cac_lich_sap_toi(
    session: Session,
    *,
    bay_gio: datetime,
    truoc_bao_lau_phut: int = 60,
) -> list[CollectionSchedule]:
    """Lịch cần tạo chuyến: giờ bắt đầu nằm trong ``(bay_gio, bay_gio + truoc_bao_lau_phut]``.

    Khớp theo thứ trong tuần: ``weekdays`` lưu 0 = Thứ Hai … 6 = Chủ Nhật, trùng
    với ``bay_gio.weekday()`` của Python (Monday=0 … Sunday=6).

    ``bay_gio`` là tham số truyền vào — không gọi ``datetime.now()`` bên trong,
    để test truyền thời điểm cố định.
    """
    gio_gioi_han = bay_gio + timedelta(minutes=truoc_bao_lau_phut)
    ket_qua: list[CollectionSchedule] = []
    for lich in session.scalars(select(CollectionSchedule)).all():
        if bay_gio.weekday() not in (lich.weekdays or []):
            continue
        gio_bat_dau = _parse_gio_bat_dau(lich.window)
        if gio_bat_dau is None:
            _LOG.warning(
                "Bỏ qua lịch %s: window %r rỗng hoặc sai định dạng, không tạo được chuyến.",
                lich.id,
                lich.window,
            )
            continue
        thoi_diem_bat_dau = datetime.combine(bay_gio.date(), gio_bat_dau)
        if bay_gio < thoi_diem_bat_dau <= gio_gioi_han:
            ket_qua.append(lich)
    return ket_qua


def tao_chuyen_tu_lich(
    session: Session,
    *,
    bay_gio: datetime,
    truoc_bao_lau_phut: int = 60,
    run_id: int | None = None,
) -> dict[str, int]:
    """Với mỗi lịch sắp tới, tạo chuyến đề xuất từ các yêu cầu đã duyệt.

    - **Chống tạo trùng:** đã có ``PickupRoute`` cùng ``service_date`` + ``window``
      và ``nguon_tao == "tu_dong"`` thì bỏ qua. Cron gọi mỗi 15 phút nên một lịch
      bị nhìn thấy nhiều lần — thiếu chốt này là sinh chuyến trùng.
    - Không có yêu cầu nào để gom → không tạo chuyến rỗng, ghi log và đi tiếp.

    Trả về dict tóm tắt đi thẳng vào phản hồi endpoint để nhìn log cron là biết
    chuyện gì vừa xảy ra.
    """
    cac_lich = cac_lich_sap_toi(
        session,
        bay_gio=bay_gio,
        truoc_bao_lau_phut=truoc_bao_lau_phut,
    )
    ngay = bay_gio.date()
    so_chuyen_tao = 0
    so_bo_vi_da_co = 0
    so_bo_vi_khong_yeu_cau = 0

    for lich in cac_lich:
        da_co = session.scalar(
            select(PickupRoute.id)
            .where(
                PickupRoute.service_date == ngay,
                PickupRoute.window == lich.window,
                PickupRoute.nguon_tao == NGUON_TU_DONG,
            )
            .limit(1)
        )
        if da_co is not None:
            so_bo_vi_da_co += 1
            continue

        try:
            cac_route = route_planner.propose_routes(
                session,
                service_date=ngay,
                window=lich.window,
                run_id=run_id,
            )
        except ValueError:
            # Không có yêu cầu nào đã duyệt cho ngày/khung giờ này.
            so_bo_vi_khong_yeu_cau += 1
            _LOG.info(
                "Lịch %s: không có yêu cầu thu gom cho %s %s, bỏ qua.",
                lich.id,
                ngay,
                lich.window,
            )
            continue

        for route in cac_route:
            route.nguon_tao = NGUON_TU_DONG
        session.flush()
        so_chuyen_tao += len(cac_route)

    return {
        "so_lich_xet": len(cac_lich),
        "so_chuyen_tao": so_chuyen_tao,
        "so_lich_bo_vi_da_co": so_bo_vi_da_co,
        "so_lich_bo_vi_khong_yeu_cau": so_bo_vi_khong_yeu_cau,
    }


def tao_lich_tuan(
    session: Session,
    *,
    actor: User,
    tuan_bat_dau: date,
    run_id: int | None = None,
) -> dict[str, int]:
    """Lên lịch cả tuần từ ``tuan_bat_dau`` — một lệnh tạo chuyến cho 7 ngày.

    Khác ``tao_chuyen_tu_lich`` (chạy mỗi 15 phút, tạo chuyến 1 giờ trước giờ
    đi). Hàm này gọi **một lần đầu tuần**, duyệt 7 ngày, tạo chuyến và gán
    kíp sẵn theo vòng tròn (§3.2). Chống tạo trùng nhận ra chuyến do **cả hai
    đường** tạo ra (cùng ``nguon_tao == "tu_dong"``).

    - ``tuan_bat_dau`` là tham số truyền vào, không ``date.today()``.
    - Không đủ người cho kíp → vẫn tạo chuyến, để trống kíp.
    - Window rỗng hoặc sai định dạng → bỏ qua, ``log.warning``.
    - Không có yêu cầu đã duyệt → không tạo chuyến rỗng.
    """
    from datetime import timedelta

    so_ngay_xet = 0
    so_chuyen_tao = 0
    so_da_gan_kip = 0
    so_chua_gan_kip = 0
    so_bo_vi_da_co = 0
    so_bo_vi_khong_yeu_cau = 0
    da_gan: dict[int, int] = {}

    all_schedules = list(session.scalars(select(CollectionSchedule)).all())

    for i in range(7):
        ngay = tuan_bat_dau + timedelta(days=i)
        thu = ngay.weekday()

        cac_lich = [s for s in all_schedules if thu in (s.weekdays or [])]
        if not cac_lich:
            continue
        so_ngay_xet += 1

        for lich in cac_lich:
            if _parse_gio_bat_dau(lich.window) is None:
                _LOG.warning(
                    "Bỏ qua lịch %s: window %r rỗng hoặc sai định dạng, không tạo được chuyến.",
                    lich.id,
                    lich.window,
                )
                continue

            da_co = session.scalar(
                select(PickupRoute.id)
                .where(
                    PickupRoute.service_date == ngay,
                    PickupRoute.window == lich.window,
                    PickupRoute.nguon_tao == NGUON_TU_DONG,
                )
                .limit(1)
            )
            if da_co is not None:
                so_bo_vi_da_co += 1
                continue

            try:
                cac_route = route_planner.propose_routes(
                    session,
                    service_date=ngay,
                    window=lich.window,
                    run_id=run_id,
                )
            except ValueError:
                so_bo_vi_khong_yeu_cau += 1
                continue

            for route in cac_route:
                route.nguon_tao = NGUON_TU_DONG
                so_chuyen_tao += 1

                kip = chon_kip_tu_dong(session, tuan_bat_dau=tuan_bat_dau, da_gan=da_gan)
                if kip is None:
                    so_chua_gan_kip += 1
                else:
                    try:
                        gan_kip(session, actor=actor, route_id=route.id, user_ids=kip)
                        so_da_gan_kip += 1
                    except ValueError:
                        so_chua_gan_kip += 1
            session.flush()

    return {
        "so_ngay_xet": so_ngay_xet,
        "so_chuyen_tao": so_chuyen_tao,
        "so_chuyen_da_gan_kip": so_da_gan_kip,
        "so_chuyen_chua_gan_kip": so_chua_gan_kip,
        "so_lich_bo_vi_da_co": so_bo_vi_da_co,
        "so_lich_bo_vi_khong_yeu_cau": so_bo_vi_khong_yeu_cau,
    }


def _cac_thung_cua_route(session: Session, route_id: int) -> list[Bin]:
    """Các thùng thuộc điểm dừng loại "thung" của chuyến."""
    cac_diem = session.scalars(
        select(RouteStop).where(
            RouteStop.route_id == route_id,
            RouteStop.stop_kind == STOP_KIND_THUNG,
        )
    ).all()
    ket_qua: list[Bin] = []
    for diem in cac_diem:
        if diem.bin_id is None:
            continue
        thung = session.get(Bin, diem.bin_id)
        if thung is not None:
            ket_qua.append(thung)
    return ket_qua


def danh_dau_day_khi_khong_co_nguoi(
    session: Session,
    *,
    actor: User,
    route_id: int,
    ly_do: str = "",
) -> int:
    """Đánh dấu các thùng của chuyến là ĐẦY khi không tìm được người vận chuyển.

    - Chỉ đặt ``dat_day_thu_cong = True`` cho thùng thuộc điểm dừng của chuyến.
    - KHÔNG đụng số đo cảm biến của thùng — lần đọc cảm biến tiếp theo không bị
      nhảy vô duyên, và đây không phải con số bịa.
    - Ghi ``write_audit`` cho từng thùng bị đặt cờ: ai đặt, chuyến nào, lý do.

    Trả về số thùng vừa đánh dấu.
    """
    route = session.get(PickupRoute, route_id)
    if route is None:
        raise ValueError("Không tìm thấy tuyến này")

    so_thung = 0
    for thung in _cac_thung_cua_route(session, route_id):
        if thung.dat_day_thu_cong:
            continue
        thung.dat_day_thu_cong = True
        so_thung += 1
        write_audit(
            session,
            actor=actor,
            action="bin_dat_day_thu_cong",
            entity="bin",
            entity_id=str(thung.id),
            detail={
                "route_id": route_id,
                "ly_do": ly_do,
                "service_date": str(route.service_date),
                "window": route.window,
            },
        )
    session.flush()
    return so_thung


def bo_danh_dau_day(session: Session, *, actor: User, route_id: int) -> int:
    """Ngược với :func:`danh_dau_day_khi_khong_co_nguoi` — gỡ cờ ĐẦY về ``False``."""
    route = session.get(PickupRoute, route_id)
    if route is None:
        raise ValueError("Không tìm thấy tuyến này")

    so_thung = 0
    for thung in _cac_thung_cua_route(session, route_id):
        if not thung.dat_day_thu_cong:
            continue
        thung.dat_day_thu_cong = False
        so_thung += 1
        write_audit(
            session,
            actor=actor,
            action="bin_bo_danh_dau_day",
            entity="bin",
            entity_id=str(thung.id),
            detail={"route_id": route_id},
        )
    session.flush()
    return so_thung
