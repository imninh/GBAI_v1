"""Giới hạn tần suất theo cửa sổ trượt, giữ trong bộ nhớ tiến trình.

Dùng cho ``POST /auth/register`` — endpoint CÔNG KHAI duy nhất tạo được dữ liệu.

⚠️ **Giới hạn đã biết, nói thẳng chứ không giấu:** bộ đếm nằm trong bộ nhớ của
một tiến trình. Chạy nhiều worker (hoặc nhiều instance trên Railway/Render) thì
mỗi worker giữ bộ đếm riêng, nên giới hạn thật lỏng hơn con số cấu hình đúng bằng
số worker. Bản chặt phải đặt bộ đếm ở Redis hoặc ở tầng cạnh (Cloudflare). Với
bản demo một worker thì cách này đủ, và nó chặn đúng thứ cần chặn: vòng lặp bơm
tài khoản từ một máy.

Khoá theo địa chỉ IP của client. IP giả mạo được sau proxy — đây là hàng rào
chống lạm dụng, KHÔNG phải cơ chế xác thực.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

# {khoá: hàng đợi các mốc thời gian gọi thành công}. Cấp module, cố ý: nó phải
# sống qua từng request.
_DAU_VET: dict[str, deque[float]] = defaultdict(deque)


def cho_phep(khoa: str, gioi_han: int, cua_so_giay: float, bay_gio: float | None = None) -> bool:
    """Có cho lần gọi này đi qua không?

    Args:
        khoa: định danh người gọi, thường là địa chỉ IP.
        gioi_han: số lần tối đa trong một cửa sổ. ``0`` hoặc số âm = TẮT hẳn.
        cua_so_giay: độ dài cửa sổ, tính bằng giây.
        bay_gio: mốc thời gian, để test bơm giờ giả. Bỏ trống thì lấy giờ thật.

    Returns:
        ``True`` nếu được phép (và lần gọi này đã được ghi nhận), ``False`` nếu vượt.
    """
    if gioi_han <= 0:
        return True

    bay_gio = time.monotonic() if bay_gio is None else bay_gio
    dau_vet = _DAU_VET[khoa]

    # Vứt mọi dấu vết đã rơi ra ngoài cửa sổ trước khi đếm.
    while dau_vet and bay_gio - dau_vet[0] >= cua_so_giay:
        dau_vet.popleft()

    # Đếm TRƯỚC khi ghi nhận: lần gọi bị từ chối không được để lại dấu vết.
    # Nếu lần bị chặn mà vẫn được ghi nhận thì vài lần bấm "Thử lại" liên tiếp
    # sẽ đẩy hạn mở khoá đi xa thêm — cửa sổ trượt không bao giờ về được rỗng,
    # người dùng bị khoá vĩnh viễn chừng nào còn bấm.
    if len(dau_vet) >= gioi_han:
        return False
    dau_vet.append(bay_gio)
    return True


def dat_lai() -> None:
    """Xoá sạch bộ đếm. Chỉ dành cho test — đừng gọi từ mã sản phẩm."""
    _DAU_VET.clear()
