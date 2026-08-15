"""Schema request/response của API.

Bám sát hợp đồng dữ liệu ở ``docs/FRONTEND_SPEC.md`` mục 7 — đó là bản cam kết
với frontend. Đổi tên trường hay đường dẫn thì **sửa cả hai nơi cùng lúc**.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

# --- Auth -----------------------------------------------------------------


class LoginRequest(BaseModel):
    """Đăng nhập bằng SĐT hoặc email. Cả hai đều tuỳ chọn nhưng phải có một.

    `email` GIỮ NGUYÊN tên trường và trở thành tuỳ chọn — ba nút "vào thẳng"
    trên màn đăng nhập đang gửi đúng trường này, đổi tên là hỏng chúng.
    """

    email: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=20)
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    """Đăng ký cư dân mới bằng số điện thoại — gói G1b.

    Cố tình KHÔNG có `role`, `email`, `green_points`. Đây là endpoint công khai,
    thứ gì client gửi được thì client tự quyết được — vai trò và điểm thưởng do
    server quyết, email do server sinh.

    `password` tối thiểu 8 ký tự, khớp với mật khẩu demo đang dùng.
    """

    phone: str = Field(min_length=9, max_length=20)
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=2, max_length=120)
    # Bỏ trống nghĩa là chưa gắn căn hộ — hợp lệ. Màn "Điểm gửi" và "Lịch thu
    # gom" đều đã chịu được trạng thái không có nơi ở.
    unit_id: int | None = None


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    # `LoginResponse` dùng UserOut làm response_model, nên trường nào không khai
    # ở đây sẽ bị FastAPI cắt khỏi phản hồi dù `user_dict` có trả về.
    phone: str = ""
    role: str
    unit: str = ""
    building: str = ""
    building_id: int | None = None
    building_lat: float | None = None
    building_lng: float | None = None
    green_points: int = 0


class UpdateProfileRequest(BaseModel):
    """Cư dân tự sửa hồ sơ — R-08.

    Cố tình KHÔNG có `email` và `role`: một cái là danh tính đăng nhập, một cái
    là ranh giới phân quyền.

    `unit_id = None` nghĩa là "không đụng tới căn hộ", nên muốn bỏ căn hộ phải
    dùng cờ riêng `xoa_can_ho`. Nhập nhằng giữa "không gửi" và "gửi null" là
    kiểu lỗi âm thầm nhất của API sửa từng phần.
    """

    full_name: str | None = Field(default=None, max_length=120)
    unit_id: int | None = None
    xoa_can_ho: bool = False


class LoginResponse(BaseModel):
    token: str
    user: UserOut
    permissions: dict[str, dict[str, Any]]


# --- Phân loại ------------------------------------------------------------


class ClassifyTextRequest(BaseModel):
    text_query: str = Field(min_length=1, max_length=500)
    building_id: int | None = None


class FeedbackRequest(BaseModel):
    is_correct: bool
    suggested_category_code: str = ""


class VerifyRequest(BaseModel):
    """Xác nhận nhãn cho ca nghi ngờ — HITL #2."""

    category_code: str = Field(min_length=1, max_length=40)
    reply_text: str = ""


# --- Thu gom --------------------------------------------------------------


class PickupItem(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category_code: str = ""
    qty: int = Field(default=1, ge=1, le=99)
    media_id: int | None = None
    est_weight_kg: float = Field(default=0.0, ge=0)


class CreatePickupRequest(BaseModel):
    items: list[PickupItem] = Field(min_length=1)
    est_weight_kg: float = Field(default=0.0, ge=0)
    weight_min_kg: float | None = None
    weight_max_kg: float | None = None
    preferred_date: date | None = None
    preferred_window: str = ""
    ngoai_lich: bool = False
    note: str = ""
    # Bắt buộc tick ở bước 3 của wizard (spec 4.7).
    confirmed_no_hazardous: bool = False


class ReviewPickupRequest(BaseModel):
    action: Literal["approve", "approve_with_changes", "reject"]
    reason: str = ""
    note: str = ""
    changes: dict[str, Any] | None = None


# --- Tuyến ----------------------------------------------------------------


class ProposeRouteRequest(BaseModel):
    service_date: date
    window: str = ""
    team_id: int | None = None
    capacity_kg: float | None = Field(default=None, gt=0)


class ReviewRouteRequest(BaseModel):
    """Body của HITL #3.

    ``stop_order`` và ``removed_stops`` mang **``RouteStop.id``**, KHÔNG phải
    ``request_id``: tuyến trộn cả điểm dừng loại yêu cầu lẫn loại thùng, mà điểm
    dừng loại thùng không có ``request_id``.
    """

    action: Literal["approve", "approve_with_changes", "regenerate", "cancel"]
    stop_order: list[int] | None = None
    removed_stops: list[int] | None = None


class CompleteStopRequest(BaseModel):
    issue: str = ""
    issue_note: str = ""
    actual_weight_kg: float | None = Field(default=None, ge=0)


# --- Danh mục và kho quy định --------------------------------------------


class UpdateCategoryRequest(BaseModel):
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    bin_color: str | None = None
    handling_note: str | None = None
    safety_warning: str | None = None


class RetrievalTestRequest(BaseModel):
    """Ô "Thử truy hồi" trong màn Kho quy định — công cụ debug RAG nhìn thấy được."""

    query: str = Field(min_length=1, max_length=300)
    building_id: int | None = None
    top_k: int = Field(default=5, ge=1, le=20)
