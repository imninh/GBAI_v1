"""Một lệnh dựng đủ bối cảnh trước buổi trình bày (gói P7).

Trước mỗi lần demo, nhóm phải nhớ làm tay một chuỗi việc — chạy bộ mô phỏng
thùng, chuyển vài yêu cầu về trạng thái hoàn tất, bấm "Đề xuất lại" trên màn
duyệt tuyến. Quên một bước là màn hình trống giữa buổi trình bày. Script này
gom phần **kiểm tra được bằng máy** thành một lệnh, in ra checklist cho phần chỉ
người làm được:

    python scripts/chuan_bi_demo.py
    python scripts/chuan_bi_demo.py --lam --so-yeu-cau 2
    python scripts/chuan_bi_demo.py --db-url "sqlite:///..." --lam

Mặc định chỉ kiểm tra và in — **không ghi gì**. Muốn ghi phải truyền ``--lam``,
và kể cả khi có ``--lam`` thì script **không bịa số liệu**: thùng không bao giờ
được "hồi sinh" bằng cách ghi thẳng ``last_seen_at`` (phải qua
``device_simulator.py``), và yêu cầu không bao giờ được gán thẳng
``status = "hoan_tat"`` (phải qua ``pickup_flow.xac_nhan_khoi_luong``).
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.db.models import (  # noqa: E402
    STOP_KIND_THUNG,
    Bin,
    Building,
    PickupRequest,
    PickupRoute,
    RouteStop,
    Unit,
    User,
    WasteCategory,
)
from src.db.schema_patch import va_cot_thieu  # noqa: E402
from src.db.session import _them_sslmode, get_engine, normalize_database_url  # noqa: E402
from src.services import bins as bins_service  # noqa: E402
from src.services import pickup_flow  # noqa: E402
from src.services.pickup_lifecycle import DA_GIAO_DON_VI, HOAN_TAT, chuan_hoa  # noqa: E402
from src.services.rag import so_doan_co_embedding  # noqa: E402

# Console Windows mặc định cp1252, in tiếng Việt thẳng ra là vỡ. Giữ guard vì
# pytest thay stdout bằng đối tượng không có ``reconfigure``.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEMO_RESIDENT_EMAIL = "resident@demo.vn"

# Những việc chỉ người làm được — máy không thay được, chỉ nhắc.
CHECKLIST_NGUOI: tuple[str, ...] = (
    "Chạy bộ mô phỏng thùng: `python scripts/device_simulator.py` (lấy BIN_DEVICE_KEY trong .env).",
    "Bấm 'Đề xuất lại' trên màn duyệt tuyến để agent gộp thùng vào chuyến.",
    "Mở web một lần cho máy chủ miễn phí thức dậy trước buổi trình bày.",
)


@dataclass
class MucKiemTra:
    """Một mục trong báo cáo kiểm tra: đạt hay chưa, kèm dòng in ra.

    ``viec_nguoi`` là việc chỉ người làm được, in ở khối "VIỆC NGƯỜI PHẢI TỰ
    LÀM" — để trống nghĩa là mục này không có thêm việc gì cho người.
    """

    ten: str
    da_dat: bool
    dong: str
    viec_nguoi: str = ""


def _dem_thung(session: Session, now: datetime) -> tuple[int, int, int]:
    """``(sống, cần gom, tổng)`` trong số thùng đang hoạt động.

    Chỉ đếm thùng ``is_active``; trạng thái tính bằng ``bins.trang_thai_thung``
    chứ không tự nhân bản quy tắc — nơi duy nhất quyết định là ``bins.py``.
    """
    cac_thung = session.scalars(select(Bin).where(Bin.is_active.is_(True))).all()
    song = 0
    can_gom = 0
    for thung in cac_thung:
        trang_thai = bins_service.trang_thai_thung(thung, now)
        if trang_thai != "mat_ket_noi":
            song += 1
        if trang_thai == "can_gom":
            can_gom += 1
    return song, can_gom, len(cac_thung)


def kiem_tra(session: Session, now: datetime | None = None) -> list[MucKiemTra]:
    """Kiểm tra bối cảnh demo — **chỉ đọc, không ghi gì**.

    Args:
        now: mốc thời gian tính trạng thái thùng; mặc định lấy đồng hồ hiện tại.
    """
    if now is None:
        now = datetime.now(UTC)

    ket_qua: list[MucKiemTra] = []

    # 1. Thùng còn sống
    song, _can_gom, tong = _dem_thung(session, now)
    so_chet = tong - song
    if so_chet:
        ket_qua.append(
            MucKiemTra(
                ten="Thùng còn sống",
                da_dat=False,
                dong=(
                    f"⚠️ Thùng còn sống: {song}/{tong} đang kết nối, {so_chet} mất kết nối — "
                    "chạy `python scripts/device_simulator.py` để thùng báo về trở lại "
                    "(lấy BIN_DEVICE_KEY trong .env, không in giá trị khoá ra màn hình)."
                ),
            )
        )
    else:
        ket_qua.append(
            MucKiemTra(ten="Thùng còn sống", da_dat=True, dong=f"✅ Thùng còn sống: {song}/{tong} đang kết nối.")
        )

    # 2. Thùng cần gom
    _song, can_gom, _tong = _dem_thung(session, now)
    if can_gom == 0:
        ket_qua.append(
            MucKiemTra(
                ten="Thùng cần gom",
                da_dat=False,
                dong=(
                    "⚠️ Thùng cần gom: 0 — bộ xếp tuyến sẽ không có thùng nào để gộp, "
                    "chạy bộ mô phỏng cho mức rác vượt ngưỡng."
                ),
            )
        )
    else:
        ket_qua.append(MucKiemTra(ten="Thùng cần gom", da_dat=True, dong=f"✅ Thùng cần gom: {can_gom} thùng."))

    # 3. Giao thùng cho nhân viên
    nhan_vien = bins_service.danh_sach_nhan_vien(session)
    chua_giao = session.scalar(
        select(func.count(Bin.id)).where(Bin.is_active.is_(True), Bin.assigned_cleaner_id.is_(None))
    )
    if len(nhan_vien) <= 1:
        ket_qua.append(
            MucKiemTra(
                ten="Giao thùng cho nhân viên",
                da_dat=False,
                dong=(
                    f"⚠️ Chỉ có {len(nhan_vien)} nhân viên vệ sinh — màn giao việc mất ý nghĩa, "
                    f"cần ít nhất 2 người. Thùng chưa giao ai: {chua_giao}."
                ),
            )
        )
    else:
        chi_tiet = ", ".join(f"{nv['full_name']}: {nv['so_thung_duoc_giao']}" for nv in nhan_vien)
        ket_qua.append(
            MucKiemTra(
                ten="Giao thùng cho nhân viên",
                da_dat=True,
                dong=f"✅ Giao thùng: {len(nhan_vien)} nhân viên ({chi_tiet}) · chưa giao ai: {chua_giao}.",
            )
        )

    # 4. Lịch sử cư dân
    cu_dan = session.scalar(select(User).where(User.email == DEMO_RESIDENT_EMAIL))
    if cu_dan is None:
        ket_qua.append(
            MucKiemTra(
                ten="Lịch sử cư dân",
                da_dat=False,
                dong=f"⚠️ Không tìm thấy {DEMO_RESIDENT_EMAIL} — chạy `python scripts/seed.py --demo`.",
            )
        )
    else:
        cac_yeu_cau = session.scalars(select(PickupRequest).where(PickupRequest.resident_id == cu_dan.id)).all()
        so_hoan_tat = sum(1 for r in cac_yeu_cau if chuan_hoa(r.status) == HOAN_TAT)
        if so_hoan_tat == 0:
            ket_qua.append(
                MucKiemTra(
                    ten="Lịch sử cư dân",
                    da_dat=False,
                    dong=(
                        f"⚠️ Lịch sử cư dân: {len(cac_yeu_cau)} yêu cầu, 0 hoàn tất — màn 'Lịch sử theo "
                        "vật liệu' sẽ hiện 'đã thu 0', chạy lại với --lam."
                    ),
                )
            )
        else:
            ket_qua.append(
                MucKiemTra(
                    ten="Lịch sử cư dân",
                    da_dat=True,
                    dong=f"✅ Lịch sử cư dân: {len(cac_yeu_cau)} yêu cầu, {so_hoan_tat} hoàn tất.",
                )
            )

    # 5. Tuyến chờ duyệt
    tuyen = session.scalar(select(PickupRoute).where(PickupRoute.status == "proposed").limit(1))
    co_diem_dung_thung = (
        session.scalar(
            select(RouteStop.id)
            .where(RouteStop.route_id == tuyen.id, RouteStop.stop_kind == STOP_KIND_THUNG)
            .limit(1)
        )
        is not None
        if tuyen is not None
        else False
    )
    if tuyen is None:
        ket_qua.append(
            MucKiemTra(
                ten="Tuyến chờ duyệt",
                da_dat=False,
                dong="⚠️ Không có tuyến nào đang chờ duyệt — bấm 'Đề xuất lại' trên màn duyệt tuyến.",
            )
        )
    elif not co_diem_dung_thung:
        ket_qua.append(
            MucKiemTra(
                ten="Tuyến chờ duyệt",
                da_dat=False,
                dong=(
                    "⚠️ Tuyến chờ duyệt chỉ có điểm dừng yêu cầu, chưa có thùng — bấm 'Đề xuất lại' trên "
                    "màn duyệt tuyến để agent gộp cả thùng vào chuyến."
                ),
            )
        )
    else:
        ket_qua.append(
            MucKiemTra(
                ten="Tuyến chờ duyệt",
                da_dat=True,
                dong=f"✅ Tuyến chờ duyệt có cả điểm dừng yêu cầu lẫn thùng (#{tuyen.id}).",
            )
        )

    # 5b. Tuyến demo "đủ điểm" — command-center phải khoe được PyVRP.
    # Tuyến suy biến (2 điểm cùng toà, 0 km) làm bản đồ vẽ polyline vô nghĩa.
    # Chỉ đọc: đếm điểm dừng + quãng đường đã lưu, không gọi agent gộp lại.
    if tuyen is None:
        ket_qua.append(
            MucKiemTra(
                ten="Tuyến demo đủ điểm",
                da_dat=False,
                dong="⚠️ Chưa có tuyến nào để khoe tối ưu — chạy `python scripts/seed.py --demo` rồi bấm 'Đề xuất lại' trên màn duyệt tuyến.",
            )
        )
    else:
        so_diem = len(tuyen.stops or [])
        km = tuyen.est_distance_km or 0.0
        if so_diem >= 5 and km > 0:
            ket_qua.append(
                MucKiemTra(
                    ten="Tuyến demo đủ điểm",
                    da_dat=True,
                    dong=f"✅ Tuyến demo: {so_diem} điểm dừng · ~{km} km — command-center vẽ được tuyến thật.",
                )
            )
        else:
            ket_qua.append(
                MucKiemTra(
                    ten="Tuyến demo đủ điểm",
                    da_dat=False,
                    dong=(
                        f"⚠️ Tuyến demo suy biến ({so_diem} điểm, {km} km) — bản đồ không chứng minh được "
                        "PyVRP tối ưu. Chạy `python scripts/seed.py --demo` và `python scripts/dung_canh_demo.py "
                        "--that --toi-chac-chan` để có thùng đầy gộp vào tuyến."
                    ),
                )
            )

    # 6. Dữ liệu nền
    so_toa = session.scalar(select(func.count(Building.id))) or 0
    so_can_ho = session.scalar(select(func.count(Unit.id))) or 0
    so_nhom_rac = session.scalar(select(func.count(WasteCategory.id))) or 0
    co_vector, tong_doan = so_doan_co_embedding(session)
    du_du_lieu = so_toa >= 1 and so_can_ho >= 1 and so_nhom_rac >= 1 and tong_doan >= 1 and co_vector >= 1
    if du_du_lieu:
        ket_qua.append(
            MucKiemTra(
                ten="Dữ liệu nền",
                da_dat=True,
                dong=(
                    f"✅ Dữ liệu nền: {so_toa} toà · {so_can_ho} căn hộ · {so_nhom_rac} nhóm rác · "
                    f"{co_vector}/{tong_doan} đoạn quy định có vector."
                ),
            )
        )
    else:
        ket_qua.append(
            MucKiemTra(
                ten="Dữ liệu nền",
                da_dat=False,
                dong=(
                    f"⚠️ Dữ liệu nền: {so_toa} toà · {so_can_ho} căn hộ · {so_nhom_rac} nhóm rác · "
                    f"{co_vector}/{tong_doan} đoạn quy định có vector — chạy `python scripts/seed.py --demo` "
                    "nếu thiếu toà/căn hộ/nhóm rác, và `python scripts/seed.py --embed` nếu chưa có vector."
                ),
            )
        )

    # 7. Khoá thiết bị riêng của thùng
    cac_thung = session.scalars(select(Bin).where(Bin.is_active.is_(True))).all()
    da_cap = sum(1 for thung in cac_thung if thung.device_key_hash != "")
    if da_cap == 0:
        ket_qua.append(
            MucKiemTra(
                ten="Khoá thiết bị thùng",
                da_dat=True,
                dong=(
                    "✅ Mọi thùng đang dùng khoá chung — bộ mô phỏng chạy được ngay với "
                    "`BIN_DEVICE_KEY`."
                ),
            )
        )
    elif da_cap == len(cac_thung):
        ket_qua.append(
            MucKiemTra(
                ten="Khoá thiết bị thùng",
                da_dat=True,
                dong=(
                    f"✅ {da_cap}/{len(cac_thung)} thùng đã cấp khoá riêng — chạy bộ mô phỏng với "
                    "`python scripts/device_simulator.py --key-file <file khoá>` thay vì `--key`."
                ),
                viec_nguoi=(
                    "Đã cấp khoá riêng cho thùng — chạy bộ mô phỏng bằng "
                    "`python scripts/device_simulator.py --key-file <file khoá>` thay vì `--key`."
                ),
            )
        )
    else:
        ma_da_cap = ", ".join(thung.code for thung in cac_thung if thung.device_key_hash != "")
        ket_qua.append(
            MucKiemTra(
                ten="Khoá thiết bị thùng",
                da_dat=False,
                dong=(
                    f"⚠️ Chỉ {da_cap}/{len(cac_thung)} thùng được cấp khoá riêng ({ma_da_cap}), phần còn "
                    "lại vẫn dùng khoá chung — bộ mô phỏng chạy nửa được nửa không mà không hề báo. "
                    "Cấp hết bằng `python scripts/cap_khoa_thung.py`, hoặc bỏ hết và dùng `--key`."
                ),
                viec_nguoi=(
                    "Khoá thiết bị mới cấp một phần — chạy bộ mô phỏng bằng "
                    "`python scripts/device_simulator.py --key-file <file khoá>` đúng cho các thùng đã "
                    "cấp, hoặc cấp hết / bỏ hết cho nhất quán."
                ),
            )
        )

    # 8. Đơn vị thu gom
    nhan_su = session.scalars(select(User).where(User.role.in_(["cleaner", "manager"]))).all()
    so_nguoi_chua_gan = sum(1 for nguoi in nhan_su if nguoi.organization_id is None)
    tong_thung = len(cac_thung)
    so_thung_chua_gan = sum(1 for thung in cac_thung if thung.organization_id is None)
    quan_ly = session.scalar(select(User).where(User.email == "manager@demo.vn"))
    so_thung_cung_don_vi = 0
    if quan_ly is not None and quan_ly.organization_id is not None:
        so_thung_cung_don_vi = session.scalar(
            select(func.count(Bin.id)).where(Bin.organization_id == quan_ly.organization_id)
        ) or 0
    if so_nguoi_chua_gan or so_thung_chua_gan:
        ket_qua.append(
            MucKiemTra(
                ten="Đơn vị thu gom",
                da_dat=False,
                dong=(
                    f"⚠️ {so_nguoi_chua_gan} người và {so_thung_chua_gan} thùng chưa thuộc đơn vị nào — "
                    "chạy `python scripts/seed.py --demo`."
                ),
            )
        )
    elif quan_ly is not None and quan_ly.organization_id is not None and so_thung_cung_don_vi == 0:
        ket_qua.append(
            MucKiemTra(
                ten="Đơn vị thu gom",
                da_dat=False,
                dong=(
                    "⚠️ Quản lý demo thuộc đơn vị có 0 thùng — danh sách thùng của quản lý sẽ TRỐNG "
                    "trên màn hình. Gắn thùng vào cùng đơn vị của `manager@demo.vn`."
                ),
            )
        )
    else:
        ket_qua.append(
            MucKiemTra(
                ten="Đơn vị thu gom",
                da_dat=True,
                dong=f"✅ {len(nhan_su)} người và {tong_thung} thùng đã thuộc đơn vị thu gom.",
            )
        )

    # 9. Hàng đợi chờ xác nhận khối lượng
    so_cho_xac_nhan = (
        session.scalar(select(func.count(PickupRequest.id)).where(PickupRequest.status == DA_GIAO_DON_VI)) or 0
    )
    if so_cho_xac_nhan == 0:
        ket_qua.append(
            MucKiemTra(
                ten="Hàng đợi chờ xác nhận khối lượng",
                da_dat=False,
                dong=(
                    "⚠️ Hàng đợi 'Chờ xác nhận khối lượng' đang rỗng — mất màn chứng minh nguyên tắc "
                    "chỉ khối lượng người cân mới được dùng để chốt. Chạy `python scripts/seed.py --demo`."
                ),
            )
        )
    else:
        ket_qua.append(
            MucKiemTra(
                ten="Hàng đợi chờ xác nhận khối lượng",
                da_dat=True,
                dong=f"✅ Hàng đợi 'Chờ xác nhận khối lượng': {so_cho_xac_nhan} yêu cầu đang chờ cân.",
            )
        )

    # 10. Giới hạn tần suất đăng ký
    settings = get_settings()
    so_lan = settings.register_rate_limit
    cua_so = settings.register_rate_window_seconds
    if so_lan == 0:
        ket_qua.append(
            MucKiemTra(
                ten="Giới hạn tần suất đăng ký",
                da_dat=False,
                dong=(
                    "⚠️ Rate limit `/auth/register` đang TẮT — an toàn cho diễn thử, nhớ bật lại "
                    "trước khi mở cho người thật."
                ),
            )
        )
    else:
        ket_qua.append(
            MucKiemTra(
                ten="Giới hạn tần suất đăng ký",
                da_dat=True,
                dong=(
                    f"✅ Rate limit `/auth/register`: {so_lan} lần mỗi {cua_so} giây. Định diễn cảnh "
                    "đăng ký nhiều lần liên tiếp thì đặt `REGISTER_RATE_LIMIT=0`."
                ),
            )
        )

    return ket_qua


def _ma_don_vi(session: Session, request: PickupRequest) -> str:
    """Mã căn hộ của yêu cầu — dùng làm cột "đơn vị" khi in."""
    don_vi = session.get(Unit, request.unit_id)
    return don_vi.code if don_vi else ""


def _so_hoan_tat_cua(session: Session, user: User) -> int:
    """Số yêu cầu đã hoàn tất của một người — tính bằng trạng thái chuẩn hoá."""
    cac_yeu_cau = session.scalars(select(PickupRequest).where(PickupRequest.resident_id == user.id)).all()
    return sum(1 for r in cac_yeu_cau if chuan_hoa(r.status) == HOAN_TAT)


def lam_hoan_tat(session: Session, so_yeu_cau: int) -> list[str]:
    """Đưa tối đa ``so_yeu_cau`` yêu cầu của cư dân demo về trạng thái hoàn tất.

    Chỉ xử lý yêu cầu đang ở trạng thái đủ điều kiện xác nhận khối lượng
    (``da_giao_don_vi``) và **phải đi qua** ``pickup_flow.xac_nhan_khoi_luong``.
    Khối lượng thật chọn bằng trung điểm của khoảng ``weight_min_kg..weight_max_kg``
    để rơi vào nhánh ``hoan_tat`` chứ không phải ``tranh_chap``.

    Chạy lại vô hại: số cần xử lý tính so với con số hoàn tất đã đạt, nên đã đủ
    ``so_yeu_cau`` cái thì lần sau không làm gì thêm.

    Returns:
        Các dòng mô tả từng yêu cầu vừa chốt, hoặc một dòng nêu lý do khi không
        xử lý được gì.
    """
    cu_dan = session.scalar(select(User).where(User.email == DEMO_RESIDENT_EMAIL))
    if cu_dan is None:
        return [f"Không tìm thấy {DEMO_RESIDENT_EMAIL} — chạy `python scripts/seed.py --demo` trước."]

    nguoi_xac_nhan = session.scalar(select(User).where(User.role == "cleaner").order_by(User.id).limit(1))
    if nguoi_xac_nhan is None:
        nguoi_xac_nhan = session.scalar(select(User).where(User.role == "manager").order_by(User.id).limit(1))
    if nguoi_xac_nhan is None:
        return ["Không tìm thấy tài khoản nào để làm người xác nhận khối lượng (cần vai cleaner hoặc manager)."]

    cac_yeu_cau = session.scalars(
        select(PickupRequest).where(PickupRequest.resident_id == cu_dan.id).order_by(PickupRequest.id)
    ).all()
    du_dieu_kien = [r for r in cac_yeu_cau if chuan_hoa(r.status) == DA_GIAO_DON_VI]
    if not du_dieu_kien:
        trang_thai = ", ".join(f"#{r.id} '{chuan_hoa(r.status)}'" for r in cac_yeu_cau) or "không có yêu cầu nào"
        return [
            "Không có yêu cầu nào của cư dân demo đang ở trạng thái đủ điều kiện xác nhận khối lượng "
            f"(da_giao_don_vi). Trạng thái hiện tại: {trang_thai}."
        ]

    con_thieu = so_yeu_cau - _so_hoan_tat_cua(session, cu_dan)
    can_xu_ly = du_dieu_kien[: max(0, con_thieu)]

    ket_qua: list[str] = []
    for request in can_xu_ly:
        khoi_luong = ((request.weight_min_kg or 0.0) + (request.weight_max_kg or 0.0)) / 2
        try:
            pickup_flow.xac_nhan_khoi_luong(
                session, request=request, weight_confirmed_kg=khoi_luong, actor=nguoi_xac_nhan
            )
        except ValueError as loi:
            ket_qua.append(f"#{request.id} · {_ma_don_vi(session, request)} · bỏ qua — {loi}")
            continue
        ket_qua.append(f"#{request.id} · {_ma_don_vi(session, request)} · {khoi_luong:g} kg → hoan_tat")
    session.flush()
    return ket_qua


def main() -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra và dựng bối cảnh trước buổi trình bày demo.")
    parser.add_argument("--lam", action="store_true", help="cho phép ghi: đưa các yêu cầu đủ điều kiện của cư dân demo về hoàn tất")
    parser.add_argument("--so-yeu-cau", type=int, default=2, help="số yêu cầu cần đưa về hoàn tất (mặc định 2)")
    parser.add_argument("--db-url", default="", help="DSN cần kiểm tra. Bỏ trống thì dùng DATABASE_URL của ứng dụng.")
    tham_so = parser.parse_args()

    if tham_so.db_url:
        engine = create_engine(_them_sslmode(normalize_database_url(tham_so.db_url)), future=True)
    else:
        engine = get_engine()

    # CSDL thật có thể cũ hơn model (giống app tự vá ở ``init_db``). Chạy trước
    # khi truy vấn — idempotent, không đổi bản ghi nào, chỉ thêm cột còn thiếu.
    # Cảnh báo của riêng bước vá là chuyện nội bộ, script in báo cáo riêng.
    logging.getLogger("src.db.schema_patch").setLevel(logging.ERROR)
    va_cot_thieu(engine)

    with Session(engine) as session:
        bao_cao = kiem_tra(session, datetime.now(UTC))
        print("KIỂM TRA BỐI CẢNH DEMO")
        print("──────────────────────")
        for muc in bao_cao:
            print(muc.dong)

        if tham_so.lam:
            print()
            print("ĐƯA YÊU CẦU VỀ HOÀN TẤT")
            print("──────────────────────")
            for dong in lam_hoan_tat(session, tham_so.so_yeu_cau):
                print(dong)
            session.commit()
            bao_cao = kiem_tra(session, datetime.now(UTC))

        print()
        print("VIỆC NGƯỜI PHẢI TỰ LÀM")
        print("──────────────────────")
        for viec in CHECKLIST_NGUOI:
            print(f"• {viec}")
        for muc in bao_cao:
            if muc.viec_nguoi:
                print(f"• {muc.viec_nguoi}")

        so_viec = sum(1 for muc in bao_cao if not muc.da_dat)
        print()
        print("SẴN SÀNG" if so_viec == 0 else f"CHƯA SẴN SÀNG — còn {so_viec} việc")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
