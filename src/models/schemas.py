from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Phản hồi từ agent")
    analysis: str = Field(default="", description="Phân tích nội bộ")


# ─── Classification ──────────────────────────────────────────────────────────

ClassifyStatus = Literal["ok", "warning", "hazard", "refused", "error"]


class ClassifyOutcome(BaseModel):
    """Kết quả phân loại sau khi đã qua safety/HITL rules.

    Dùng chung cho mọi nguồn ảnh (IoT device, web/PWA) — spec §11.
    """

    status: ClassifyStatus = Field(..., description="Trạng thái an toàn của kết quả")
    label: str = Field(default="", description="Nhãn loại rác; rỗng nếu không chắc chắn")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_review: bool = Field(default=False, description="Cần người kiểm tra (HITL)")
    message: str = Field(default="", description="Giải thích ngắn gọn cho người dùng")


class IoTCaptureResponse(BaseModel):
    """Phản hồi cho thiết bị sau khi upload ảnh.

    Ba trường đầu là tối thiểu thiết bị cần (spec §11); phần còn lại là bằng
    chứng cho thấy privacy pipeline đã chạy.
    """

    status: ClassifyStatus
    label: str = ""
    confidence: float = 0.0
    requires_review: bool = False
    message: str = ""

    capture_id: str
    phash: str
    image_bytes: int
    faces_blurred: int | None = Field(
        default=None,
        description="Số khuôn mặt đã làm mờ; None nghĩa là CHƯA kiểm tra được",
    )
    exif_stripped: bool = True


# ─── Device heartbeat ────────────────────────────────────────────────────────


class HeartbeatRequest(BaseModel):
    """Liveness ping from a bin (IoT Checkpoint 1 §21).

    Deliberately minimal: a heartbeat that carried sensor data would tempt
    devices to report state on a schedule instead of on a change.
    """

    device_id: str = Field(..., min_length=1, max_length=64)
    status: str = Field(default="online", max_length=32)


class HeartbeatResponse(BaseModel):
    status: str = "ok"
    device_id: str
    server_time: datetime


# ─── Bin readings ────────────────────────────────────────────────────────────


class BinReadingRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64)
    fill_percent: float = Field(..., ge=0.0, le=100.0)
    is_full: bool = False
    uptime_s: int = Field(default=0, ge=0)


class BinReading(BaseModel):
    reading_id: str
    bin_code: str
    device_id: str
    fill_percent: float = Field(..., ge=0.0, le=100.0)
    is_full: bool
    uptime_s: int = 0
    recorded_at: datetime
