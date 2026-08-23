"""Phạm vi theo đơn vị thu gom — nơi DUY NHẤT quyết định đơn vị của người xem.

Gói P83 tách phần quyết định phạm vi đơn vị ra khỏi ``src/services/bins.py``.
Trước đây hai hàm ``loc_theo_nguoi_xem`` (phạm vi nhân viên) và
``to_chuc_cua_nguoi_xem`` (phạm vi đơn vị) cùng nằm trong ``bins.py``, và một
test quét cấm chữ ``organization_id`` xuất hiện ở bất kỳ file nào khác. Quy tắc
"tập trung phạm vi" đúng tinh thần nhưng đặt sai chỗ: nó buộc mọi thứ liên quan
đơn vị phải chui vào module quản lý *thùng*. Giờ đây mọi thực thể — thùng cũng
như sự cố thu gom — đều hỏi module này để biết đơn vị của người xem, thay vì mỗi
service tự viết mệnh đề ``organization_id``.

Tinh thần "một nơi duy nhất" giữ nguyên: router chỉ được hỏi service rồi truyền
tiếp, không được tự viết mệnh đề lọc. Thêm vai trò hay phạm vi mới chỉ sửa một
chỗ — đây.
"""

from __future__ import annotations

from sqlalchemy import select

from src.db.models import User


def to_chuc_cua_nguoi_xem(user: User) -> int | None:
    """Id đơn vị thu gom cần lọc theo, hoặc ``None`` nếu người này không bị lọc.

    Người dùng **chưa gắn đơn vị** (``organization_id is None``) thì không bị lọc
    lớp này — đúng trạng thái của mọi CSDL trước khi seed gắn đơn vị, và của cư
    dân. Lọc họ về rỗng là làm cả hệ thống trống trơn mà không ai hiểu vì sao.

    Đây là **nơi duy nhất** quyết định phạm vi đơn vị, y như
    ``bins.loc_theo_nguoi_xem`` là nơi duy nhất quyết định phạm vi nhân viên.
    Đừng rải điều kiện ra endpoint.
    """
    return user.organization_id


def dieu_kien_theo_to_chuc(nguoi_xem: User, cot_user_id):
    """Điều kiện SQLAlchemy lọc một bảng theo đơn vị của người xem.

    Trả về ``None`` khi người xem không bị lọc (``to_chuc_cua_nguoi_xem`` trả
    ``None``) — gọi tới chỗ này phải tự bỏ qua điều kiện.

    Ngược lại trả mệnh đề ``cot_user_id IN (SELECT users.id WHERE
    users.organization_id == org OR users.organization_id IS NULL)``.

    ⚠️ Nhánh ``IS NULL`` phải giữ. Đây là quy ước đã có của dự án: bản ghi chưa
    gắn đơn vị là **việc phải xử, không được giấu đi**. Bỏ nhánh này là làm biến
    mất dữ liệu cũ mà không ai hiểu vì sao.
    """
    org = to_chuc_cua_nguoi_xem(nguoi_xem)
    if org is None:
        return None
    id_nguoi_trong_don_vi = select(User.id).where(
        (User.organization_id == org) | (User.organization_id.is_(None))
    )
    return cot_user_id.in_(id_nguoi_trong_don_vi.scalar_subquery())
