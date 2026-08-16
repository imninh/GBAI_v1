"""Xác thực và phân quyền.

Nhóm tự làm auth thay vì dùng Supabase như thẻ đề gợi ý — xem ADR-0004. Lý do
gọn: hệ thống chỉ cần ba vai trò cố định và tài khoản demo, mà phần đắt giá của
đề nằm ở AI chứ không ở quản lý danh tính; thêm một dịch vụ ngoài là thêm một
điểm hỏng khi demo.

Ma trận quyền ở :data:`PERMISSIONS` là bản chép lại của bảng trong
``docs/FRONTEND_SPEC.md`` mục 1. Sửa một bên thì sửa cả hai.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import AuditLog, Unit, User
from src.services.security import hash_password, verify_password

ROLES = ("resident", "cleaner", "manager")

# Quyền → các vai trò được phép. Vai trò không có quyền thì UI **hiện mờ kèm
# tooltip giải thích**, không ẩn hẳn, để ranh giới phân quyền nhìn thấy được.
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "classify": ("resident", "cleaner", "manager"),
    "view_schedule": ("resident", "cleaner", "manager"),
    "create_pickup": ("resident", "manager"),
    "view_own_pickups": ("resident", "cleaner", "manager"),
    "view_all_pickups": ("cleaner", "manager"),
    "review_pickup": ("manager",),
    "verify_label": ("cleaner", "manager"),
    "review_route": ("manager",),
    "complete_stop": ("cleaner", "manager"),
    "edit_catalog": ("manager",),
    "view_bins": ("cleaner", "manager"),
    "assign_bin": ("manager",),
    "manage_bins": ("manager",),
    "view_diem_gui": ("resident", "cleaner", "manager"),
    "edit_own_profile": ("resident", "cleaner", "manager"),
    "view_original_media": ("manager",),
    "view_ops": ("manager",),
    "view_eval": ("manager",),
    "view_runs": ("manager",),
}

PERMISSION_DENIED_HINTS: dict[str, str] = {
    "review_pickup": "Chỉ ban quản lý được duyệt yêu cầu thu gom vượt ngưỡng",
    "review_route": "Chỉ ban quản lý được duyệt tuyến do agent đề xuất",
    "verify_label": "Chỉ đội vệ sinh và ban quản lý được xác nhận nhãn",
    "view_original_media": "Chỉ ban quản lý được xem ảnh gốc, và mỗi lần xem đều được ghi log",
    "view_ops": "Trang vận hành dành cho ban quản lý",
    "view_eval": "Trang chất lượng AI dành cho ban quản lý",
    "view_bins": "Bản đồ thùng thu gom dành cho đội vệ sinh và ban quản lý",
    "assign_bin": "Chỉ ban quản lý được giao thùng cho nhân viên vệ sinh",
    "manage_bins": "Chỉ ban quản lý được thêm, sửa và ngừng dùng thùng thu gom",
    "view_runs": "Trang trace agent dành cho ban quản lý",
    "create_pickup": "Đội vệ sinh không tạo yêu cầu thay cư dân",
}


class AuthError(Exception):
    """Sai thông tin đăng nhập hoặc token không hợp lệ."""

    def __init__(self, message_vi: str, code: str = "AUTH-401") -> None:
        super().__init__(message_vi)
        self.message_vi = message_vi
        self.code = code


def create_token(user: User) -> str:
    """Sinh JWT cho một người dùng."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Giải mã JWT.

    Raises:
        AuthError: token hết hạn hoặc không hợp lệ.
    """
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Phiên đăng nhập đã hết hạn, đăng nhập lại giúp mình nhé.", code="AUTH-419") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Phiên đăng nhập không hợp lệ.", code="AUTH-401") from exc


def chuan_hoa_sdt(gia_tri: str) -> str:
    """Đưa số điện thoại Việt Nam về dạng chuẩn ``0xxxxxxxxx`` — đúng 10 chữ số.

    Nhận cả ``0912 345 678``, ``+84912345678``, ``84912345678``, ``0912.345.678``.
    Trả về **chuỗi rỗng** khi đầu vào không phải số điện thoại hợp lệ; chỗ gọi
    dùng đúng dấu hiệu đó để biết người dùng đang nhập SĐT hay nhập email —
    không đoán bằng dấu ``@``, vì email hỏng vẫn có dấu ``@``.
    """
    tho = re.sub(r"[\s.\-()]", "", gia_tri or "")
    if tho.startswith("+84"):
        tho = "0" + tho[3:]
    elif tho.startswith("84") and len(tho) == 11:
        tho = "0" + tho[2:]
    return tho if re.fullmatch(r"0\d{9}", tho) else ""


def authenticate(session: Session, dinh_danh: str, password: str) -> User:
    """Kiểm tra **số điện thoại hoặc email** + mật khẩu.

    Đường email được giữ lại có chủ đích: ba nút "vào thẳng" trên màn đăng nhập
    đang dùng nó, và người chấm vào hệ thống bằng ba nút đó.

    Raises:
        AuthError: khi sai định danh hoặc sai mật khẩu. Câu báo lỗi **giống hệt
            nhau** cho mọi trường hợp — khác nhau là lộ tài khoản nào có thật.
    """
    sdt = chuan_hoa_sdt(dinh_danh)
    if sdt:
        user = session.scalar(select(User).where(User.phone == sdt))
    else:
        user = session.scalar(select(User).where(User.email == dinh_danh.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("Số điện thoại/email hoặc mật khẩu không đúng.", code="AUTH-401")
    return user


def dang_ky(
    session: Session,
    *,
    phone: str,
    password: str,
    full_name: str,
    unit_id: int | None = None,
) -> User:
    """Tạo tài khoản cư dân mới, định danh bằng số điện thoại.

    Vai trò **luôn** là ``resident`` và không nhận từ client — cho client chọn
    vai trò lúc đăng ký là tự mở đường cho bất kỳ ai tự phong mình làm ban quản lý.

    Cột ``email`` là NOT NULL UNIQUE có từ trước, nên tài khoản đăng ký bằng SĐT
    được cấp một email nội bộ ``<sdt>@sdt.local``. Đó không phải hộp thư thật.

    Tính duy nhất của SĐT ép ở đây chứ không ở CSDL: cột ``phone`` cố tình không
    ``unique`` vì mọi dòng có từ trước đều mang chuỗi rỗng.

    Raises:
        AuthError: mã ``REG-400`` số điện thoại hoặc tên không hợp lệ ·
            ``REG-409`` số đã có tài khoản · ``REG-404`` căn hộ không tồn tại.
    """
    sdt = chuan_hoa_sdt(phone)
    if not sdt:
        raise AuthError("Số điện thoại không hợp lệ. Nhập 10 chữ số bắt đầu bằng 0.", code="REG-400")

    ten = full_name.strip()
    if not ten:
        raise AuthError("Cần nhập tên hiển thị.", code="REG-400")

    # So theo số ĐÃ CHUẨN HOÁ, không phải chuỗi thô người gõ: `+84901000001` và
    # `0901000001` là cùng một số. So chuỗi thô thì tài khoản thứ hai lọt qua.
    if session.scalar(select(User).where(User.phone == sdt)) is not None:
        raise AuthError("Số điện thoại này đã có tài khoản. Bạn đăng nhập nhé.", code="REG-409")

    if unit_id is not None and session.get(Unit, unit_id) is None:
        raise AuthError("Không tìm thấy căn hộ này.", code="REG-404")

    user = User(
        email=f"{sdt}@sdt.local",
        phone=sdt,
        full_name=ten,
        role="resident",
        password_hash=hash_password(password),
        unit_id=unit_id,
    )
    session.add(user)
    session.flush()

    # Tạo tài khoản là việc đáng ghi lại. KHÔNG ghi mật khẩu, kể cả bản băm.
    write_audit(
        session,
        actor=user,
        action="register",
        entity="user",
        entity_id=str(user.id),
        detail={"phone": sdt, "unit_id": unit_id},
    )
    return user


def can(user: User, permission: str) -> bool:
    """Vai trò của người dùng có quyền này không."""
    return user.role in PERMISSIONS.get(permission, ())


def permission_matrix(user: User) -> dict[str, dict[str, Any]]:
    """Toàn bộ ma trận quyền của người dùng hiện tại, để UI vẽ trạng thái mờ.

    Trả cả quyền không có kèm lý do — vì spec yêu cầu hiện mờ có tooltip chứ
    không ẩn hẳn.
    """
    return {
        name: {
            "allowed": user.role in roles,
            "reason": "" if user.role in roles else PERMISSION_DENIED_HINTS.get(name, "Vai trò của bạn không có quyền này"),
        }
        for name, roles in PERMISSIONS.items()
    }


def write_audit(
    session: Session,
    *,
    actor: User | None,
    action: str,
    entity: str,
    entity_id: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    """Ghi nhật ký kiểm toán cho hành động rủi ro hoặc chạm dữ liệu nhạy cảm."""
    session.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=detail or {},
        )
    )
    session.flush()
