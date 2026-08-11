"""Đăng nhập, thông tin phiên, hồ sơ cá nhân, và lịch sử theo vật liệu."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from src.api.deps import CurrentUser, DbSession, require
from src.api.errors import ApiError, bad_request, not_found
from src.api.serializers import user_dict
from src.config import get_settings
from src.db.models import Classification, PickupRequest, Unit, User, WasteCategory
from src.db.seed_data import DEMO_PASSWORD, USERS
from src.models.schemas import LoginRequest, LoginResponse, RegisterRequest, UpdateProfileRequest
from src.services.auth import (
    AuthError,
    authenticate,
    create_token,
    dang_ky,
    permission_matrix,
    write_audit,
)
from src.services.gioi_han_tan_suat import cho_phep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, session: DbSession) -> dict:
    """Đăng nhập bằng **số điện thoại** hoặc email, kèm mật khẩu.

    Ưu tiên `phone` khi client gửi cả hai. Đường email giữ lại cho ba nút "vào
    thẳng" của màn đăng nhập — chúng là cách người chấm vào cả ba vai trò.
    """
    dinh_danh = payload.phone.strip() or payload.email.strip()
    if not dinh_danh:
        raise bad_request("Cần số điện thoại hoặc email để đăng nhập.")
    try:
        user = authenticate(session, dinh_danh, payload.password)
    except AuthError as exc:
        raise ApiError(401, exc.code, exc.message_vi) from exc

    return {
        "token": create_token(user),
        "user": user_dict(session, user),
        "permissions": permission_matrix(user),
    }


# Mã lỗi nghiệp vụ của `dang_ky` → mã HTTP. Để ở đây chứ không ở tầng dịch vụ:
# tầng dịch vụ không nên biết gì về HTTP.
MA_HTTP_DANG_KY = {"REG-400": 400, "REG-404": 404, "REG-409": 409}


@router.post("/register", response_model=LoginResponse, status_code=201)
def register(payload: RegisterRequest, session: DbSession, request: Request) -> dict:
    """Đăng ký cư dân mới bằng số điện thoại, rồi đăng nhập luôn.

    Trả về đúng khuôn của ``/auth/login`` để app không phải gọi thêm một vòng —
    đăng ký xong là vào thẳng màn hình chính.

    ⚠️ Đây là endpoint CÔNG KHAI duy nhất tạo được dữ liệu. Nó có **giới hạn tần
    suất theo IP** (``REGISTER_RATE_LIMIT`` lần mỗi ``REGISTER_RATE_WINDOW_SECONDS``
    giây, mặc định 10 lần / 10 phút; đặt ``0`` để tắt). Bộ đếm nằm trong bộ nhớ
    tiến trình nên nhiều worker thì mỗi worker một bộ đếm — hàng rào chống lạm
    dụng, không phải cơ chế xác thực. Bước còn thiếu để mở cho người dùng thật
    vẫn là **xác thực số điện thoại**.
    """
    cau_hinh = get_settings()
    nguoi_goi = request.client.host if request.client else "khong-ro"
    if not cho_phep(nguoi_goi, cau_hinh.register_rate_limit, cau_hinh.register_rate_window_seconds):
        raise ApiError(
            429,
            "RATE-429",
            "Bạn đã thử đăng ký quá nhiều lần. Chờ ít phút rồi thử lại giúp mình nhé.",
        )

    try:
        user = dang_ky(
            session,
            phone=payload.phone,
            password=payload.password,
            full_name=payload.full_name,
            unit_id=payload.unit_id,
        )
    except AuthError as exc:
        raise ApiError(MA_HTTP_DANG_KY.get(exc.code, 400), exc.code, exc.message_vi) from exc

    return {
        "token": create_token(user),
        "user": user_dict(session, user),
        "permissions": permission_matrix(user),
    }


@router.get("/me")
def me(user: CurrentUser, session: DbSession) -> dict:
    """Thông tin người đang đăng nhập kèm ma trận quyền."""
    return {"user": user_dict(session, user), "permissions": permission_matrix(user)}


@router.patch("/me")
def update_me(
    payload: UpdateProfileRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("edit_own_profile"))],
) -> dict:
    """Tự sửa hồ sơ của chính mình — yêu cầu R-08 của Gate01.

    Chỉ hai thứ sửa được: tên hiển thị và căn hộ đang ở. Đổi căn hộ kéo theo đổi
    toạ độ nơi ở, tức đổi luôn thứ tự danh sách điểm gửi ở app cư dân — nên mọi
    lần sửa đều ghi nhật ký kiểm toán, kèm giá trị TRƯỚC khi sửa.

    Trả về đúng khuôn của ``GET /me`` để client thay thẳng phiên hiện tại.
    """
    # Giá trị TRƯỚC phải chụp TRƯỚC khi sửa — chụp sau thì log không còn ý nghĩa.
    truoc = {"full_name": user.full_name, "unit_id": user.unit_id}

    if payload.full_name is not None:
        ten = payload.full_name.strip()
        if not ten:
            raise bad_request("Tên hiển thị không được để trống.")
        user.full_name = ten

    if payload.xoa_can_ho:
        user.unit_id = None
    elif payload.unit_id is not None:
        if session.get(Unit, payload.unit_id) is None:
            raise not_found("căn hộ này")
        user.unit_id = payload.unit_id

    session.flush()

    write_audit(
        session,
        actor=user,
        action="update_profile",
        entity="user",
        entity_id=str(user.id),
        detail={
            "truoc": truoc,
            "sau": {"full_name": user.full_name, "unit_id": user.unit_id},
        },
    )
    return {"user": user_dict(session, user), "permissions": permission_matrix(user)}


@router.get("/me/history")
def me_history(user: CurrentUser, session: DbSession) -> dict:
    """Lịch sử theo vật liệu của chính mình — yêu cầu R-04 của Gate01.

    KHÔNG chia khối lượng theo vật liệu. Cân nặng trong CSDL ước lượng cho cả
    yêu cầu chứ không cho từng món, nên chia ra là bịa một con số mà dữ liệu
    không đỡ nổi. Theo vật liệu chỉ đếm số món và số yêu cầu; kg chỉ tổng ở mức
    toàn bộ, và luôn là khoảng min–max chứ không phải một số duy nhất.

    Yêu cầu bị huỷ hoặc bị từ chối không tính vào lịch sử — chúng không phản
    ánh rác đã thực sự được giao.
    """
    bo_qua = {"cancelled", "rejected"}

    tinh = [
        y
        for y in session.scalars(
            select(PickupRequest).where(PickupRequest.resident_id == user.id)
        ).all()
        if y.status not in bo_qua
    ]

    nhom = {c.code: c for c in session.scalars(select(WasteCategory)).all()}
    theo_ma: dict[str, dict[str, int]] = {}

    def o(ma: str) -> dict[str, int]:
        return theo_ma.setdefault(ma, {"so_mon": 0, "so_yeu_cau": 0, "so_lan_hoi": 0})

    for y in tinh:
        ma_trong_yeu_cau: set[str] = set()
        for mon in y.items or []:
            ma = str(mon.get("category_code") or "")
            if not ma:
                continue
            o(ma)["so_mon"] += int(mon.get("qty") or 1)
            ma_trong_yeu_cau.add(ma)
        for ma in ma_trong_yeu_cau:
            o(ma)["so_yeu_cau"] += 1

    # Số lần hỏi phân loại, đếm theo nhóm AI đoán ra. CHỈ của chính mình —
    # đây là màn hình cá nhân, đếm lẫn của người khác là rò rỉ dữ liệu.
    hoi = session.execute(
        select(WasteCategory.code, func.count(Classification.id))
        .join(WasteCategory, WasteCategory.id == Classification.predicted_category_id)
        .where(Classification.asker_id == user.id)
        .group_by(WasteCategory.code)
    ).all()
    for ma, so in hoi:
        o(str(ma))["so_lan_hoi"] = int(so)

    items = [
        {
            "category_code": ma,
            "category_name": nhom[ma].name if ma in nhom else ma,
            "bin_color": nhom[ma].bin_color if ma in nhom else "",
            "icon": nhom[ma].icon if ma in nhom else "",
            **dem,
        }
        for ma, dem in theo_ma.items()
    ]
    items.sort(key=lambda x: (-x["so_mon"], -x["so_lan_hoi"], x["category_name"]))

    return {
        "tong": {
            "so_yeu_cau": len(tinh),
            "so_yeu_cau_da_thu": sum(1 for y in tinh if y.status == "done"),
            "khoi_luong_min_kg": round(sum(y.weight_min_kg for y in tinh), 1),
            "khoi_luong_max_kg": round(sum(y.weight_max_kg for y in tinh), 1),
        },
        "theo_vat_lieu": items,
        "ghi_chu": (
            "Khối lượng chỉ tổng hợp ở mức yêu cầu vì hệ thống ước lượng cân nặng cho cả "
            "yêu cầu, không cho từng món. Đây là số ước lượng, không phải số cân thật."
        ),
    }


@router.get("/demo-accounts")
def demo_accounts() -> dict:
    """Ba nút "vào thẳng" trên màn đăng nhập.

    Trả mật khẩu ra ngoài là có chủ đích: đây là **tài khoản demo dùng dữ liệu
    mô phỏng**, và người chấm cần đăng nhập được cả ba vai trò.
    """
    mo_ta = {
        "resident": "Hỏi phân loại, đặt lịch thu gom, xem yêu cầu của mình",
        "cleaner": "Xem tuyến hôm nay, đánh dấu đã thu, xác nhận nhãn nghi ngờ",
        "manager": "Duyệt 3 hàng đợi HITL, xem vận hành và chất lượng AI",
    }
    return {
        "password": DEMO_PASSWORD,
        "accounts": [
            {
                "email": u["email"],
                "full_name": u["full_name"],
                "role": u["role"],
                "unit": u["unit_code"],
                "description": mo_ta.get(u["role"], ""),
            }
            for u in USERS
            if u["email"] in {"resident@demo.vn", "cleaner@demo.vn", "manager@demo.vn"}
        ],
        "notice": (
            "Hệ thống demo dùng dữ liệu mô phỏng và dữ liệu công khai. Ảnh tải lên được tự động "
            "xoá thông tin vị trí và làm mờ khuôn mặt trước khi xử lý."
        ),
    }
