"""Máy trạng thái của một yêu cầu thu gom tái chế.

Module thuần: không đụng CSDL, không I/O, không import gì từ ``src.db`` — test
được mà không cần session. Gói này định nghĩa máy trạng thái mới (10 trạng thái)
cô lập khỏi luồng ``pending/approved/scheduled/done`` cũ đang dùng ở
:mod:`src.services.pickup`; việc di cư sang đây là gói riêng, không làm trong
module này.
"""

from __future__ import annotations

# --- Mười trạng thái ---------------------------------------------------------
# Giá trị tiếng Việt theo đúng quy ước mới nhất của codebase (xem
# ``src/services/bins.py`` dùng ``can_gom``, ``mat_ket_noi``).

MOI_TAO = "moi_tao"
CHO_DUYET = "cho_duyet"
CHO_NHAN = "cho_nhan"
DA_NHAN = "da_nhan"
DANG_VAN_CHUYEN = "dang_van_chuyen"
DA_GIAO_DON_VI = "da_giao_don_vi"
TRANH_CHAP = "tranh_chap"
HOAN_TAT = "hoan_tat"
TU_CHOI = "tu_choi"
DA_HUY = "da_huy"

# --- Bảng chuyển tiếp --------------------------------------------------------
# Một yêu cầu CHỈ được tích điểm ở ``hoan_tat``, và ``hoan_tat`` chỉ tới được
# qua ``da_giao_don_vi`` — một người ở đơn vị thu gom xác nhận khối lượng thật,
# nên hệ thống không bao giờ trao điểm dựa trên ước lượng khối lượng của AI.
CHUYEN_TIEP: dict[str, frozenset[str]] = {
    MOI_TAO: frozenset({CHO_DUYET, CHO_NHAN, DA_HUY}),
    CHO_DUYET: frozenset({CHO_NHAN, TU_CHOI}),
    CHO_NHAN: frozenset({DA_NHAN, DA_HUY}),
    DA_NHAN: frozenset({DANG_VAN_CHUYEN, DA_HUY}),
    DANG_VAN_CHUYEN: frozenset({DA_GIAO_DON_VI}),
    DA_GIAO_DON_VI: frozenset({HOAN_TAT, TRANH_CHAP}),
    TRANH_CHAP: frozenset({HOAN_TAT}),
    HOAN_TAT: frozenset(),
    TU_CHOI: frozenset(),
    DA_HUY: frozenset(),
}

TRANG_THAI_KET_THUC: frozenset[str] = frozenset({HOAN_TAT, TU_CHOI, DA_HUY})

NHAN_VI: dict[str, str] = {
    MOI_TAO: "Mới tạo",
    CHO_DUYET: "Chờ duyệt",
    CHO_NHAN: "Chờ nhận",
    DA_NHAN: "Đã nhận",
    DANG_VAN_CHUYEN: "Đang vận chuyển",
    DA_GIAO_DON_VI: "Đã giao đơn vị",
    TRANH_CHAP: "Tranh chấp",
    HOAN_TAT: "Hoàn tất",
    TU_CHOI: "Từ chối",
    DA_HUY: "Đã huỷ",
}


class LoiChuyenTrangThai(Exception):  # noqa: N818
    """Chuyển trạng thái không hợp lệ; thông điệp tiếng Việt nói rõ hai trạng thái."""

    def __init__(self, tu: str, den: str) -> None:
        self.tu = tu
        self.den = den
        super().__init__(f"Không thể chuyển trạng thái từ '{tu}' sang '{den}'.")


def co_the_chuyen(tu: str, den: str) -> bool:
    """Trạng thái ``den`` có nằm trong danh sách chuyển tiếp hợp lệ của ``tu`` không."""
    cac_dich_hop_le = CHUYEN_TIEP.get(tu)
    if cac_dich_hop_le is None:
        return False
    return den in cac_dich_hop_le


def chuyen_trang_thai(tu: str, den: str) -> str:
    """Trả về ``den`` nếu bước đi hợp lệ, ngược lại ném :class:`LoiChuyenTrangThai`.

    Trạng thái không tồn tại cũng là lỗi — không bao giờ cho qua một cách im lặng.
    """
    if not co_the_chuyen(tu, den):
        raise LoiChuyenTrangThai(tu, den)
    return den


# ⚠️ CẢNH BÁO CHO NGƯỜI DI TRÚ SAU NÀY: có HAI bộ từ vựng trạng thái khác
# nhau trong dự án, và chúng dùng chung ba từ.
#   PickupRequest.status : pending · approved · scheduled · done · cancelled
#   PickupRoute.status   : proposed · approved · done · cancelled
# Bảng dưới đây CHỈ áp cho PickupRequest. Tìm-thay thế mù chuỗi "approved"
# trên cả repo sẽ phá state machine của tuyến đường, và có thể không có test
# nào bắt được. Các chỗ thuộc về TUYẾN, không được đụng tới:
#   route_planner.py:267,275 · metrics.py:369 · routes.py:120
#   classify_node.py:107
# Ngoài ra pickup.py:281 là kind="cancelled" của PickupEvent, cũng không phải
# status.
TU_TRANG_THAI_CU: dict[str, str] = {
    "pending": CHO_DUYET,  # vượt ngưỡng, chờ người duyệt
    "approved": CHO_NHAN,  # đã duyệt, chờ nhân viên nhận
    "scheduled": DA_NHAN,  # đã xếp vào tuyến nghĩa là đã có người nhận
    "done": HOAN_TAT,
    "cancelled": DA_HUY,
    "rejected": TU_CHOI,
}


def chuan_hoa(status: str) -> str:
    """Đưa một giá trị trạng thái bất kỳ về chuẩn mới.

    - giá trị cũ trả về giá trị mới tương đương;
    - giá trị vốn đã mới được giữ nguyên;
    - chuỗi rỗng hoặc kiểu None-like trả về ``MOI_TAO``;
    - mọi thứ khác ném :class:`LoiChuyenTrangThai`.

    Chịu cả hai chiều là toàn bộ ý đồ: cho phép chỗ đọc di trú trước chỗ ghi,
    và vẫn chạy tốt sau khi chỗ ghi chuyển sang giá trị mới.
    """
    if status is None or status == "":
        return MOI_TAO
    if status in CHUYEN_TIEP:
        return status
    gia_tri_moi = TU_TRANG_THAI_CU.get(status)
    if gia_tri_moi is None:
        raise LoiChuyenTrangThai(status, "chuan_hoa")
    return gia_tri_moi


def trang_thai_tuong_duong(moi: str) -> tuple[str, ...]:
    """Mọi giá trị trạng thái tương đương với một trạng thái mới.

    Trả về chính trạng thái mới, theo sau là các giá trị CŨ trong
    ``TU_TRANG_THAI_CU`` trỏ về nó (xếp theo vần). Hàm tồn tại cho câu lệnh
    SQL: Python không gọi được một hàm trên cột CSDL, nên truy vấn phải khớp
    cả hai bộ từ vựng trong lúc di trú còn đang diễn ra.
    """
    if moi not in CHUYEN_TIEP:
        raise LoiChuyenTrangThai(moi, "trang_thai_tuong_duong")
    cac_gia_tri_cu = sorted(cu for cu, gia_tri in TU_TRANG_THAI_CU.items() if gia_tri == moi)
    return (moi, *cac_gia_tri_cu)
