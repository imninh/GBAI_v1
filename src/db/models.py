"""Schema cơ sở dữ liệu cho GreenBin AI (VHR-17).

File này là điểm hội tụ duy nhất: mọi bảng nằm ở một module theo miền nghiệp vụ
bên dưới, và được re-export ở đây để ``from src.db.models import X`` không bao
giờ đổi. Import ``models`` sẽ đăng ký toàn bộ bảng lên ``Base.metadata``, nên
``create_all`` / ``drop_all`` chạy đúng trên đủ mọi bảng.

Nguyên tắc thiết kế:

* ``Media`` tách khỏi ``Classification``: ảnh có vòng đời riêng (hạn lưu trữ,
  cờ đã tước EXIF, cờ đã làm mờ khuôn mặt) và là nơi chịu trách nhiệm về
  quyền riêng tư. Hai cờ đó hiển thị được lên UI làm bằng chứng tuân thủ.
* ``Classification`` ghi lại ``tier`` và ``model`` của từng lần phân loại —
  đây là dữ liệu để chứng minh việc định tuyến model 3 tầng có hiệu quả.
* ``AgentRun`` / ``RunNodeMetric`` có mặt từ đầu vì yêu cầu chương trình bắt
  buộc theo dõi độ trễ, lỗi, chi phí và trace được chuỗi xử lý.
* Mọi hành động rủi ro (duyệt thu gom lớn, chốt tuyến, xem ảnh gốc) đều phải
  ghi ``AuditLog``.
"""

from __future__ import annotations

from src.db.models_base import Base, utcnow  # noqa: F401
from src.db.models_bins import Bin, BinReading  # noqa: F401
from src.db.models_chatbot import ChatMessage, ChatSession, ToolExecutionRecord  # noqa: F401
from src.db.models_classify import Classification, ClassificationFeedback, Media  # noqa: F401
from src.db.models_diem import (  # noqa: F401
    DiemNhanThucLog,
    DiemThuongLog,
    NhiemVu,
    NhiemVuHoanThanh,
)
from src.db.models_eval import EvalRun, FailureCase  # noqa: F401
from src.db.models_knowledge import KnowledgeChunk, KnowledgeDoc  # noqa: F401
from src.db.models_ops import AgentRun, AuditLog, BatchGanNhan, RunNodeMetric  # noqa: F401
from src.db.models_phien import MaQrThung, PhienThung, TokenThietBi  # noqa: F401
from src.db.models_pickup import (  # noqa: F401
    STOP_KIND_THUNG,
    STOP_KIND_YEU_CAU,
    STOP_KINDS,
    GPSLog,
    PickupEvent,
    PickupRequest,
    PickupRoute,
    RouteStop,
    RouteThanhVien,
    SuCoThuGom,
)
from src.db.models_schedule import Alert, CollectionSchedule, Notification  # noqa: F401
from src.db.models_users import Building, Organization, Unit, User  # noqa: F401
from src.db.models_waste import WasteCategory  # noqa: F401

__all__ = [
    "Alert",
    "AgentRun",
    "AuditLog",
    "Base",
    "BatchGanNhan",
    "Bin",
    "BinReading",
    "Building",
    "ChatMessage",
    "ChatSession",
    "Classification",
    "ClassificationFeedback",
    "CollectionSchedule",
    "DiemNhanThucLog",
    "NhiemVu",
    "NhiemVuHoanThanh",
    "RouteThanhVien",
    "EvalRun",
    "FailureCase",
    "GPSLog",
    "KnowledgeChunk",
    "KnowledgeDoc",
    "Media",
    "MaQrThung",
    "Notification",
    "Organization",
    "PhienThung",
    "PickupEvent",
    "PickupRequest",
    "PickupRoute",
    "RouteStop",
    "RunNodeMetric",
    "STOP_KINDS",
    "STOP_KIND_THUNG",
    "STOP_KIND_YEU_CAU",
    "SuCoThuGom",
    "TokenThietBi",
    "ToolExecutionRecord",
    "Unit",
    "User",
    "WasteCategory",
    "utcnow",
]
