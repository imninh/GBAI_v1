"""Lớp nghiệp vụ thùng thu gom thông minh.

Thùng đặt ngoài hiện trường định kỳ báo về mức rác và mức pin; đơn vị thu gom
nhìn trạng thái đó để quyết định hôm nay đi gom thùng nào. Lớp này gồm bốn
việc: ghi nhận một lần báo về, quy ra trạng thái điều phối của một thùng, đếm
số thùng theo trạng thái, và lấy danh sách thùng cho đơn vị thu gom.

Quy tắc thời gian: **mọi hàm phụ thuộc ``now`` đều nhận ``now: datetime`` truyền
vào, không gọi ``datetime.now()`` bên trong** — test kiểm được chuyện "mất kết
nối" mà không phải chờ 30 phút thật.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import Bin, BinReading, User


def _ve_naive_utc(value: datetime) -> datetime:
    """Đưa một mốc thời gian về naive UTC để so sánh được.

    Cột ``DateTime`` không kèm múi giờ nên giá trị đọc lại từ SQLite là naive
    (ngầm hiểu là UTC); còn ``now`` từ caller có thể là aware theo đúng quy ước
    ``utcnow()`` của dự án. Trộn hai dạng với nhau khi trừ sẽ ném TypeError.

    Chuẩn hoá phải nằm NGAY TẠI ĐÂY, không phải ở caller: hàm này là nơi duy
    nhất biết mình đang so một giá trị đọc từ CSDL với một giá trị đồng hồ —
    caller chỉ thấy một trong hai, nên đưa quyết định lên caller là rải lỗi ra
    ngoài cho mọi chỗ gọi phải nhớ.
    """
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def ghi_nhan_reading(
    session: Session,
    bin: Bin,
    fill_percent: float,
    battery_percent: float,
    source: str,
    now: datetime,
) -> BinReading:
    """Ghi một lần thùng báo về và cập nhật trạng thái gần nhất của thùng.

    Raises:
        ValueError: khi mức rác hoặc mức pin ngoài khoảng 0–100.
    """
    if not 0 <= fill_percent <= 100:
        raise ValueError(f"Mức rác phải nằm trong khoảng 0–100, nhận được {fill_percent}")
    if not 0 <= battery_percent <= 100:
        raise ValueError(f"Mức pin phải nằm trong khoảng 0–100, nhận được {battery_percent}")

    reading = BinReading(
        bin_id=bin.id,
        fill_percent=fill_percent,
        battery_percent=battery_percent,
        source=source,
        created_at=now,
    )
    session.add(reading)
    bin.fill_percent = fill_percent
    bin.battery_percent = battery_percent
    bin.last_seen_at = now
    session.flush()
    return reading


def trang_thai_thung(bin: Bin, now: datetime) -> str:
    """Trạng thái điều phối của một thùng.

    Returns:
        ``mat_ket_noi`` · ``het_pin`` · ``can_gom`` · ``binh_thuong``.
    """
    settings = get_settings()

    # THỨ TỰ ƯU TIÊN LÀ BẮT BUỘC: mất kết nối phải thắng mọi trạng thái khác.
    # Một thùng offline 3 ngày vẫn còn lưu con số 85% của lần báo cuối; nếu xét
    # "can_gom" trước thì đội xe sẽ chạy tới một thùng mà không ai biết thực sự
    # đầy bao nhiêu. Cũng phải xét trước "het_pin": mất kết nối nghĩa là không
    # biết tình trạng pin hiện tại ra sao.
    if bin.last_seen_at is None:
        return "mat_ket_noi"
    # Chuẩn hoá cả hai toán hạng về naive UTC trước khi trừ: ``last_seen_at``
    # đọc từ CSDL là naive (cột không có múi giờ), còn ``now`` có thể aware —
    # trộn hai dạng là ném TypeError ngay.
    now_naive = _ve_naive_utc(now)
    last_seen_naive = _ve_naive_utc(bin.last_seen_at)
    if (now_naive - last_seen_naive) > timedelta(minutes=settings.bin_offline_minutes):
        return "mat_ket_noi"
    if bin.battery_percent <= settings.bin_low_battery_percent:
        return "het_pin"
    if bin.fill_percent >= settings.bin_fill_alert_percent:
        return "can_gom"
    return "binh_thuong"


def danh_sach_thung(
    session: Session,
    now: datetime,
    *,
    chi_can_gom: bool = False,
    cua_nhan_vien: int | None = None,
    cua_to_chuc: int | None = None,
) -> list[dict[str, Any]]:
    """Danh sách thùng đang hoạt động kèm trạng thái đã tính.

    Args:
        chi_can_gom: chỉ giữ thùng ``can_gom`` và sắp xếp mức rác giảm dần —
            đúng thứ tự đơn vị thu gom muốn ghé từng thùng.
        cua_nhan_vien: chỉ giữ thùng đã giao cho nhân viên có id này. ``None``
            (mặc định) là **không lọc gì** — giữ nguyên hành vi cũ cho mọi chỗ
            gọi không truyền, kể cả bộ xếp tuyến.
        cua_to_chuc: chỉ giữ thùng thuộc đơn vị có id này, **cộng với** thùng
            chưa gắn đơn vị nào (``organization_id IS NULL``). ``None`` (mặc
            định) là **không lọc lớp tổ chức** — giữ nguyên hành vi cũ.
    """
    # NGHI NGO: chỉ lấy thùng ``is_active`` — đề không nói rõ, nhưng thùng đã
    # ngừng dùng không nên xuất hiện trong danh sách điều phối.
    dieu_kien = [Bin.is_active.is_(True)]
    if cua_nhan_vien is not None:
        dieu_kien.append(Bin.assigned_cleaner_id == cua_nhan_vien)
    if cua_to_chuc is not None:
        # Thùng chưa gắn đơn vị là việc phải XỬ chứ không phải thứ được giấu đi —
        # mọi CSDL cũ đều NULL cho tới khi ai đó chạy seed gắn đơn vị. Bỏ vế
        # ``IS NULL`` là màn hình điều phối trống trơn mà không ai hiểu vì sao.
        dieu_kien.append((Bin.organization_id == cua_to_chuc) | (Bin.organization_id.is_(None)))
    rows = session.scalars(select(Bin).where(*dieu_kien)).all()
    ket_qua = [
        {
            "id": thung.id,
            "code": thung.code,
            "name": thung.name,
            "building_id": thung.building_id,
            "address": thung.address,
            # Nhóm rác thùng này nhận. `or []` vì cột cho phép NULL với bản ghi
            # tạo trước khi có mặc định — frontend lọc theo vật liệu dựa vào đây.
            "category_codes": thung.category_codes or [],
            "lat": thung.lat,
            "lng": thung.lng,
            "fill_percent": thung.fill_percent,
            "battery_percent": thung.battery_percent,
            "assigned_cleaner_id": thung.assigned_cleaner_id,
            "last_seen_at": thung.last_seen_at,
            "status": trang_thai_thung(thung, now),
        }
        for thung in rows
    ]
    if chi_can_gom:
        ket_qua = [r for r in ket_qua if r["status"] == "can_gom"]
        ket_qua.sort(key=lambda r: r["fill_percent"], reverse=True)
    return ket_qua


def diem_gui_cho_cu_dan(session: Session, now: datetime) -> list[dict[str, Any]]:
    """Danh sách điểm gửi rác cho app cư dân — bản thu gọn của `danh_sach_thung`.

    Khác hai chỗ so với bản của đơn vị thu gom:

    * **Bỏ dữ liệu vận hành** (mức pin, lần báo cuối, mã toà). Cư dân không dùng
      tới, và khi thùng được chia theo tổ chức thì đây là chỗ rò rỉ.
    * **Nói thật về tình trạng.** Thùng mất kết nối hoặc hết pin thì con số mức
      đầy đang lưu có thể đã cũ vài ngày — trả `chua_ro` chứ KHÔNG trả con số đó.
      Bảo cư dân "còn chỗ" dựa trên số đo hôm kia là đẩy họ đi một chuyến vô ích,
      đúng thứ màn hình này sinh ra để tránh.
    """
    ket_qua = []
    for thung in session.scalars(select(Bin).where(Bin.is_active.is_(True))).all():
        trang_thai = trang_thai_thung(thung, now)
        if trang_thai == "binh_thuong":
            tinh_trang, tinh_trang_vi = "con_cho", "Còn chỗ"
        elif trang_thai == "can_gom":
            tinh_trang, tinh_trang_vi = "sap_day", "Sắp đầy"
        else:
            tinh_trang, tinh_trang_vi = "chua_ro", "Chưa rõ còn chỗ không"
        ket_qua.append(
            {
                "code": thung.code,
                "name": thung.name,
                "address": thung.address,
                "lat": thung.lat,
                "lng": thung.lng,
                "category_codes": thung.category_codes or [],
                "tinh_trang": tinh_trang,
                "tinh_trang_vi": tinh_trang_vi,
                # Số cũ không được hiện cho cư dân — `chua_ro` thì là `None`.
                "fill_percent": None if tinh_trang == "chua_ro" else thung.fill_percent,
            }
        )
    return ket_qua


def thong_ke_thung(
    session: Session,
    now: datetime,
    *,
    cua_nhan_vien: int | None = None,
    cua_to_chuc: int | None = None,
) -> dict[str, int]:
    """Đếm số thùng đang hoạt động theo trạng thái điều phối.

    Bốn con số trên dashboard phải đếm **đúng tập thùng mà người đang xem nhìn
    thấy trong danh sách**. Thẻ thống kê nói 10 trong khi danh sách chỉ có 6 là
    hai màn hình nói hai chuyện khác nhau, và người dùng sẽ tin con số to hơn.
    """
    danh_sach = danh_sach_thung(
        session, now, cua_nhan_vien=cua_nhan_vien, cua_to_chuc=cua_to_chuc
    )
    dem: dict[str, int] = {"tong": len(danh_sach), "can_gom": 0, "mat_ket_noi": 0, "het_pin": 0}
    for dong in danh_sach:
        if dong["status"] in dem:
            dem[dong["status"]] += 1
    return dem


def lich_su_readings(session: Session, bin_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """Các lần báo về gần nhất của một thùng, mới trước cũ sau.

    Args:
        bin_id: khoá chính của thùng cần xem lịch sử.
        limit: số bản ghi tối đa trả về, kẹp trong khoảng 1..100 — không tin số
            caller truyền vào.
    """
    limit = max(1, min(100, limit))
    cac_dong = session.scalars(
        select(BinReading).where(BinReading.bin_id == bin_id).order_by(BinReading.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "fill_percent": dong.fill_percent,
            "battery_percent": dong.battery_percent,
            "source": dong.source,
            "created_at": dong.created_at,
        }
        for dong in cac_dong
    ]


def thung_can_gom(session: Session, now: datetime) -> list[Bin]:
    """Các thùng đang ở trạng thái ``can_gom``, mức rác giảm dần.

    Trả về đối tượng ``Bin`` chứ không phải dict như :func:`danh_sach_thung`:
    bên xếp tuyến cần ``capacity_liters`` và toạ độ để tính tải trọng và quãng
    đường, hai trường mà khuôn dict cho giao diện không có.
    """
    thung = session.scalars(select(Bin).where(Bin.is_active.is_(True))).all()
    can_gom = [t for t in thung if trang_thai_thung(t, now) == "can_gom"]
    return sorted(can_gom, key=lambda t: t.fill_percent, reverse=True)


def gan_thung_cho_nhan_vien(session: Session, thung: Bin, nhan_vien: User | None) -> None:
    """Giao một thùng cho nhân viên vệ sinh, hoặc bỏ gán khi ``nhan_vien`` là ``None``.

    Chỉ vai ``cleaner`` mới nhận được thùng. Cho phép gán cho một cư dân là tự
    mở đường cho người ngoài đội đọc dữ liệu vận hành ngay khi gói A2b bật phần
    lọc theo người đang đăng nhập — chặn ở đây, chỗ duy nhất đổi được cột này.

    Chặn giao chéo đơn vị ở đúng nơi này: nếu hai bên đều đã gắn đơn vị mà khác
    đơn vị thì không giao. Thùng hoặc nhân viên chưa gắn đơn vị (NULL) thì
    không bị chặn — thứ chưa gắn là việc phải xử, không phải thứ bị khoá lại.

    Raises:
        ValueError: khi người nhận không phải nhân viên vệ sinh, hoặc hai bên
            thuộc hai đơn vị thu gom khác nhau.
    """
    if nhan_vien is not None and nhan_vien.role != "cleaner":
        raise ValueError(
            f"Chỉ giao thùng được cho nhân viên vệ sinh — '{nhan_vien.full_name}' đang là vai '{nhan_vien.role}'."
        )
    if (
        nhan_vien is not None
        and nhan_vien.organization_id is not None
        and thung.organization_id is not None
        and nhan_vien.organization_id != thung.organization_id
    ):
        raise ValueError(
            f"Không giao được thùng '{thung.code}' cho '{nhan_vien.full_name}' — hai bên khác đơn vị thu gom."
        )
    thung.assigned_cleaner_id = nhan_vien.id if nhan_vien is not None else None
    session.flush()


def loc_theo_nguoi_xem(user: User) -> int | None:
    """Id nhân viên cần lọc theo, hoặc ``None`` nếu người này được xem mọi thùng.

    Chỉ vai ``cleaner`` bị giới hạn trong phần thùng được giao. Ban quản lý thấy
    toàn bộ, **kể cả thùng chưa giao cho ai** — thùng chưa gán là việc phải xử
    của quản lý, không phải thứ được giấu đi; lọc luôn cả quản lý thì nó thành
    vô hình với mọi người.

    Đây là **nơi duy nhất** quyết định "ai thấy gì" cho phần đọc dữ liệu thùng.
    Thêm vai trò mới thì sửa đúng ở đây, đừng rải điều kiện ra từng endpoint.
    """
    return user.id if user.role == "cleaner" else None


def to_chuc_cua_nguoi_xem(user: User) -> int | None:
    """Id đơn vị thu gom cần lọc theo, hoặc ``None`` nếu người này không bị lọc.

    Người dùng **chưa gắn đơn vị** (``organization_id is None``) thì không bị lọc
    lớp này — đúng trạng thái của mọi CSDL trước khi seed gắn đơn vị, và của cư
    dân. Lọc họ về rỗng là làm cả hệ thống trống trơn mà không ai hiểu vì sao.

    Đây là **nơi duy nhất** quyết định phạm vi đơn vị, y như `loc_theo_nguoi_xem`
    là nơi duy nhất quyết định phạm vi nhân viên. Đừng rải điều kiện ra endpoint.
    """
    return user.organization_id


def xem_duoc_thung(thung: Bin, cua_nhan_vien: int | None, cua_to_chuc: int | None = None) -> bool:
    """Người đang xem có được mở chi tiết thùng này không.

    ``cua_nhan_vien is None`` nghĩa là người xem không bị giới hạn. Nhân viên chỉ
    mở được thùng **được giao cho chính mình** — thùng của người khác hay thùng
    chưa gán đều không thuộc về người đang xem.

    ``cua_to_chuc is None`` nghĩa là không bị giới hạn theo đơn vị. Có đơn vị thì
    thùng ngoài đơn vị đó không mở được — trừ thùng chưa gắn đơn vị nào
    (``organization_id IS NULL``), vì đó là việc phải xử, không được giấu đi.
    """
    if cua_to_chuc is not None and thung.organization_id is not None and thung.organization_id != cua_to_chuc:
        return False
    return cua_nhan_vien is None or thung.assigned_cleaner_id == cua_nhan_vien


def danh_sach_nhan_vien(session: Session, *, cua_to_chuc: int | None = None) -> list[dict[str, Any]]:
    """Nhân viên vệ sinh kèm số thùng mỗi người đang được giao.

    Dùng cho màn giao thùng của ban quản lý: người đứng ở đó cần thấy ai đang
    nhẹ việc, không phải chỉ thấy một danh sách tên.

    Đếm bằng **một truy vấn gộp** rồi tra bảng trong bộ nhớ, không đếm lẻ từng
    người — 20 nhân viên là 20 lượt đi CSDL, và đây là màn hình mở thường xuyên.

    Chỉ đếm thùng ``is_active``: thùng đã ngừng dùng không phải việc của ai.

    ``cua_to_chuc`` giới hạn **cả hai truy vấn** (danh sách người lẫn số thùng
    của mỗi người) trong cùng một phạm vi đơn vị, đúng luật NULL của P12: người
    chưa gắn đơn vị vẫn hiện, thùng chưa gắn đơn vị vẫn được đếm — thứ chưa gắn
    là việc phải xử, không phải thứ bị giấu đi. Hai truy vấn lọc lệch nhau là
    con số "đang giữ mấy thùng" đếm cả thùng của đơn vị khác, và sai số đó
    trông vẫn như một con số.
    """
    dieu_kien_nguoi = [User.role == "cleaner"]
    dieu_kien_dem = [Bin.is_active.is_(True), Bin.assigned_cleaner_id.is_not(None)]
    if cua_to_chuc is not None:
        dieu_kien_nguoi.append((User.organization_id == cua_to_chuc) | (User.organization_id.is_(None)))
        dieu_kien_dem.append((Bin.organization_id == cua_to_chuc) | (Bin.organization_id.is_(None)))

    dem = dict(
        session.execute(
            select(Bin.assigned_cleaner_id, func.count(Bin.id))
            .where(*dieu_kien_dem)
            .group_by(Bin.assigned_cleaner_id)
        ).all()
    )
    nhan_vien = session.scalars(
        select(User).where(*dieu_kien_nguoi).order_by(User.full_name, User.id)
    ).all()
    return [
        {
            "id": nv.id,
            "full_name": nv.full_name,
            "phone": nv.phone,
            "so_thung_duoc_giao": dem.get(nv.id, 0),
        }
        for nv in nhan_vien
    ]
