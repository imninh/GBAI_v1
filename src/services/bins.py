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
from src.db.models import Bin, BinReading, PickupRoute, RouteStop, User, WasteCategory
from src.services.auth import write_audit


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
        ``chua_trien_khai`` · ``mat_ket_noi`` · ``het_pin`` · ``can_gom`` ·
        ``binh_thuong``.
    """
    settings = get_settings()

    # Thùng ở trạng thái ĐỀ XUẤT (PROPOSED) là vị trí trên bản đồ chưa lắp thiết
    # bị — nó KHÔNG "mất kết nối", nó "chưa triển khai". Gộp hai cái làm ban quản
    # lý không phân biệt được "chưa lắp" (bình thường) với "đã lắp mà hỏng" (phải
    # đi sửa). `deployment_status` rỗng nghĩa là thùng demo/thật đang vận hành —
    # giữ nguyên đường cũ cho chúng.
    #
    # Phải đứng ĐẦU TIÊN, trước phép kiểm `last_seen_at is None`: thùng PROPOSED
    # chưa có reading nào nên `last_seen_at=None` — đặt nhánh này sau phép kiểm
    # đó thì nó trả `mat_ket_noi` và thoát trước khi nhánh mới kịp chạy.
    if bin.deployment_status == "PROPOSED":
        return "chua_trien_khai"

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

    `chua_trien_khai` (gói P39/P42): thùng `deployment_status="PROPOSED"` vẫn nằm
    trong danh sách nhưng trước đây bị rơi khỏi mọi thẻ — 70 thùng (60 PROPOSED
    + 10 demo) cho `tong = 70` mà bốn nhóm cộng lại chỉ ~10. Thêm khoá vào `dem`
    là đủ: vòng `if dong["status"] in dem` phía dưới tự đếm nhóm mới.
    """
    danh_sach = danh_sach_thung(
        session, now, cua_nhan_vien=cua_nhan_vien, cua_to_chuc=cua_to_chuc
    )
    dem: dict[str, int] = {
        "tong": len(danh_sach),
        "can_gom": 0,
        "mat_ket_noi": 0,
        "het_pin": 0,
        "chua_trien_khai": 0,
    }
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


# --- Gói P31: ban quản lý thêm / sửa / ngừng dùng thùng ------------------------

# Trường người quản lý được sửa qua PATCH. CỐ TÌNH không nằm trong danh sách:
# `code` (khoá mọi nơi khác đang tham chiếu), số đo của thiết bị
# (`fill_percent`/`battery_percent`/`last_seen_at`/`device_key_hash` — người sửa
# tay là bịa số đo), `is_seed` (cờ nguồn dữ liệu) và `organization_id` (đơn vị
# sở hữu).
#
# Ba trường GIS được gói P30 thêm vào `models_bins.py` SAU khi gói P31 dựng xong
# bốn endpoint này, nên chúng bị bỏ sót khỏi danh sách trắng. Bổ sung ở đây.
# `coordinate_confidence` và `priority` CỐ Ý không có mặt: cái đầu là mức tin cậy
# của phép khảo sát, cái sau là mức ưu tiên triển khai — cả hai thuộc về quy
# trình khảo sát thực địa, không phải thứ người trực console sửa tay.
CAC_TRUONG_SUA_DUOC = frozenset(
    {
        "name",
        "address",
        "lat",
        "lng",
        "category_codes",
        "capacity_liters",
        "site_type",
        "area_name",
        "deployment_status",
    }
)

# Trạng thái tuyến chưa hoàn tất: thùng đang là điểm dừng của một tuyến như thế
# thì không được ngừng dùng. `done` và `cancelled` là kết thúc, không giữ thùng.
TRANG_THAI_TUYEN_CHUA_XONG = frozenset({"proposed", "approved", "in_progress"})


def _tra_thung(session: Session, code: str) -> Bin:
    """Tìm thùng theo mã. Raises ``ValueError`` khi không có — cùng câu với lỗi
    của các endpoint đọc, không lộ mã nào có thật cho người đang dò."""
    thung = session.scalar(select(Bin).where(Bin.code == code))
    if thung is None:
        raise ValueError(f"Không tìm thấy thùng có mã '{code}'.")
    return thung


def _kiem_toa_do(lat: float | None, lng: float | None) -> None:
    """Toạ độ cho phép NULL (thùng chưa xác định vị trí), nhưng nếu có thì phải
    nằm trong khoảng hợp lệ — một thùng ớ vĩ độ 200 là dữ liệu hỏng ngay."""
    if lat is not None and not -90 <= lat <= 90:
        raise ValueError(f"Toạ độ vĩ độ {lat} nằm ngoài khoảng cho phép (-90..90).")
    if lng is not None and not -180 <= lng <= 180:
        raise ValueError(f"Toạ độ kinh độ {lng} nằm ngoài khoảng cho phép (-180..180).")


def _kiem_nhom_rac(session: Session, cac_ma: list[str]) -> list[str]:
    """Mọi mã nhóm rác phải tồn tại trong bảng ``waste_categories``. Không tự
    tạo danh mục mới — tạo thùng kéo theo danh mục là thay đổi hệ thống trộm lén."""
    cac_ma = list(cac_ma)
    ma_rac = {ma for (ma,) in session.execute(select(WasteCategory.code)).all()}
    sai = [ma for ma in cac_ma if ma not in ma_rac]
    if sai:
        raise ValueError(f"Nhóm rác không tồn tại: {', '.join(sai)}.")
    return cac_ma


def tao_thung(session: Session, du_lieu: dict[str, Any], nguoi_tao: User) -> Bin:
    """Ban quản lý tạo một thùng thu gom mới.

    Thùng do người nhập (``is_seed=False``) — khác hẳn 60 điểm đề xuất của gói
    P30. Đơn vị thu gom lấy theo đơn vị của người tạo, không nhận từ client:
    người ta không được tạo thùng cho đơn vị khác.

    Raises:
        ValueError: khi `code` thiếu/trùng, tên thiếu, toạ độ ngoài khoảng, hay
            nhóm rác không tồn tại.
    """
    code = (du_lieu.get("code") or "").strip().upper()
    if not code:
        raise ValueError("Cần mã thùng để tạo — mã không được để trống.")
    if session.scalar(select(Bin).where(Bin.code == code)) is not None:
        raise ValueError(f"Đã có thùng mã '{code}' — mã thùng phải là duy nhất.")

    ten = (du_lieu.get("name") or "").strip()
    if not ten:
        raise ValueError("Cần tên thùng để tạo — tên không được để trống.")

    lat = du_lieu.get("lat")
    lng = du_lieu.get("lng")
    _kiem_toa_do(lat, lng)

    cac_ma = _kiem_nhom_rac(session, du_lieu.get("category_codes") or [])

    thung = Bin(
        code=code,
        name=ten,
        address=(du_lieu.get("address") or "").strip(),
        lat=lat,
        lng=lng,
        category_codes=cac_ma,
        capacity_liters=du_lieu.get("capacity_liters") or 0.0,
        building_id=du_lieu.get("building_id"),
        is_active=True,
        is_seed=False,
        organization_id=nguoi_tao.organization_id,
    )
    session.add(thung)
    session.flush()

    write_audit(
        session,
        actor=nguoi_tao,
        action="create_bin",
        entity="bin",
        entity_id=thung.code,
        detail={"name": thung.name, "category_codes": thung.category_codes},
    )
    return thung


def sua_thung(session: Session, code: str, du_lieu: dict[str, Any], nguoi_sua: User) -> Bin:
    """Sửa các trường người quản lý được phép của một thùng (PATCH đúng nghĩa).

    Trường không có trong ``du_lieu`` thì không đổi; body không có trường nào
    sửa được thì trả về nguyên trạng, không ghi nhật ký.

    Raises:
        ValueError: khi thùng không tồn tại, ngoài phạm vi người xem, toạ độ
            ngoài khoảng, hay nhóm rác không tồn tại.
    """
    thung = _tra_thung(session, code)
    if not xem_duoc_thung(thung, loc_theo_nguoi_xem(nguoi_sua), to_chuc_cua_nguoi_xem(nguoi_sua)):
        raise ValueError(f"Không tìm thấy thùng có mã '{code}'.")

    # Lọc lại một lần ở lớp nghiệp vụ: dù router gửi gì, chỉ trường trong danh
    # sách trắng mới được chạm. Cấm sửa code / số đo thiết bị nằm ngay ở đây.
    cac_truong = {k: v for k, v in du_lieu.items() if k in CAC_TRUONG_SUA_DUOC}
    if not cac_truong:
        return thung

    _kiem_toa_do(
        cac_truong.get("lat", thung.lat),
        cac_truong.get("lng", thung.lng),
    )
    if "category_codes" in cac_truong:
        cac_truong["category_codes"] = _kiem_nhom_rac(session, cac_truong["category_codes"] or [])

    # Chụp giá trị TRƯỚC của đúng các trường sẽ đổi — chụp sau là ghi vào nhật
    # ký hai giá trị giống hệt nhau, nhật ký thành vô dụng.
    truoc = {k: getattr(thung, k) for k in cac_truong}
    for k, v in cac_truong.items():
        setattr(thung, k, v)
    session.flush()

    write_audit(
        session,
        actor=nguoi_sua,
        action="update_bin",
        entity="bin",
        entity_id=thung.code,
        detail={"truoc": truoc, "sau": cac_truong},
    )
    return thung


def ngung_dung_thung(session: Session, code: str, nguoi_xoa: User) -> Bin:
    """Ngừng dùng một thùng — tắt cờ ``is_active``, KHÔNG xoá hàng.

    ⛔ Không dùng ``session.delete``: quan hệ ``readings`` có ``cascade="all,
    delete-orphan"`` nên xoá một thùng là xoá sạch toàn bộ lịch sử mức rác/pin
    (dữ liệu nuôi quyết định điều phối), và ``RouteStop`` còn tham chiếu
    ``bin_id`` — xoá thùng từng nằm trong tuyến đã chạy là làm hỏng hồ sơ tuyến
    cũ. ``is_active`` có sẵn trong model là để dành cho việc này.

    Thùng đang là điểm dừng của một tuyến chưa hoàn tất thì từ chối.

    Raises:
        ValueError: khi thùng không tồn tại, ngoài phạm vi, hoặc đang trong tuyến.
    """
    thung = _tra_thung(session, code)
    if not xem_duoc_thung(thung, loc_theo_nguoi_xem(nguoi_xoa), to_chuc_cua_nguoi_xem(nguoi_xoa)):
        raise ValueError(f"Không tìm thấy thùng có mã '{code}'.")

    tuyen_giu = session.scalar(
        select(PickupRoute)
        .join(RouteStop, RouteStop.route_id == PickupRoute.id)
        .where(RouteStop.bin_id == thung.id, PickupRoute.status.in_(TRANG_THAI_TUYEN_CHUA_XONG))
        .order_by(PickupRoute.service_date.desc(), PickupRoute.id.desc())
    )
    if tuyen_giu is not None:
        raise ValueError(
            f"Thùng '{code}' đang là điểm dừng của tuyến #{tuyen_giu.id} chưa hoàn tất — không ngừng dùng được."
        )

    thung.is_active = False
    session.flush()

    write_audit(
        session,
        actor=nguoi_xoa,
        action="deactivate_bin",
        entity="bin",
        entity_id=thung.code,
        detail={"is_active": False},
    )
    return thung


def kich_hoat_lai_thung(session: Session, code: str, nguoi_bat: User) -> Bin:
    """Đưa một thùng đã ngừng dùng trở lại hoạt động.

    Raises:
        ValueError: khi thùng không tồn tại, hoặc ngoài phạm vi người xem.
    """
    thung = _tra_thung(session, code)
    if not xem_duoc_thung(thung, loc_theo_nguoi_xem(nguoi_bat), to_chuc_cua_nguoi_xem(nguoi_bat)):
        raise ValueError(f"Không tìm thấy thùng có mã '{code}'.")

    thung.is_active = True
    session.flush()

    write_audit(
        session,
        actor=nguoi_bat,
        action="reactivate_bin",
        entity="bin",
        entity_id=thung.code,
        detail={"is_active": True},
    )
    return thung
