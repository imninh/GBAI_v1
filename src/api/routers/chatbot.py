"""Endpoint API cho RAG Chatbot (Hỏi đáp luật, thùng rác, hướng dẫn app)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.deps import DbSession
from src.services.chatbot import ask_chatbot

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


class ChatbotAskRequest(BaseModel):
    """Yêu cầu hỏi đáp gửi tới Chatbot."""

    question: str = Field(..., min_length=1, max_length=1000, description="Nội dung câu hỏi của cư dân")
    building_id: int | None = Field(default=None, description="Mã toà nhà (nếu có)")
    lat: float | None = Field(default=None, description="Toạ độ Vĩ độ GPS của người dùng")
    lng: float | None = Field(default=None, description="Toạ độ Kinh độ GPS của người dùng")


class ChatSourceChipResponse(BaseModel):
    doc_title: str
    section: str
    quote: str
    doc_type: str = "law"
    source: str = ""
    score: float = 0.0


class ChatbotAskResponse(BaseModel):
    """Phản hồi đầy đủ của Chatbot kèm siêu dữ liệu và căn cứ giải thích."""

    answer: str
    intent: str
    confidence_level: str = "High"
    confidence_score: float = 1.0
    source_badge: str = "[AI sinh]"
    sources: list[ChatSourceChipResponse] = []
    viable_bins: list[dict[str, Any]] = []
    fallback_level: int = 1
    generated_by: str = "mistral"
    tokens_used: int = 0
    cost_usd: float = 0.0


class ChatbotFeedbackRequest(BaseModel):
    """Phản hồi đánh giá 👍 / 👎 của người dùng (HAX G15)."""

    question: str
    answer: str
    intent: str
    rating: int = Field(..., description="1 là Thích (👍), -1 là Không thích (👎)")
    comment: str = ""


@router.post("/ask", response_model=ChatbotAskResponse)
def ask(payload: ChatbotAskRequest, session: DbSession) -> dict[str, Any]:
    """Hỏi đáp tự do với Trợ lý GreenBin AI RAG (Luật, Thùng rác, Hướng dẫn App)."""
    res = ask_chatbot(
        session,
        payload.question,
        building_id=payload.building_id,
        user_lat=payload.lat,
        user_lng=payload.lng,
    )
    return res.as_dict()


@router.post("/feedback")
def submit_feedback(payload: ChatbotFeedbackRequest, session: DbSession) -> dict[str, Any]:
    """Ghi nhận đánh giá phản hồi 👍 / 👎 tức thì từ người dùng."""
    # Phục vụ vòng phản hồi chất lượng (HAX G15 & Triplet Observability)
    return {
        "status": "success",
        "message": "Cảm ơn bạn đã đóng góp phản hồi để cải thiện chất lượng AI!",
        "rating": payload.rating,
    }


@router.get("/suggested-questions")
def get_suggested_questions() -> dict[str, list[dict[str, str]]]:
    """Danh sách câu hỏi gợi ý nhanh cho 3 nhóm tính năng."""
    return {
        "suggestions": [
            {
                "category": "waste_law",
                "label": "📜 Mức phạt không phân loại rác",
                "question": "Không phân loại rác tại nguồn bị phạt bao nhiêu tiền theo Nghị định 45?",
            },
            {
                "category": "waste_law",
                "label": "📜 Vỏ hộp sữa có cần bóc nhôm?",
                "question": "Vỏ hộp sữa giấy tráng nhôm bỏ vào thùng nào, có cần bóc tách lớp nhôm không?",
            },
            {
                "category": "bin_query",
                "label": "🗑️ Thùng rác gần nhất còn chỗ",
                "question": "Cho tôi biết thùng rác tái chế gần đây còn chỗ không?",
            },
            {
                "category": "bin_query",
                "label": "⚠️ Bỏ pin cũ ở đâu",
                "question": "Pin cũ và bóng đèn huỳnh quang bỏ ở đâu trong toà nhà?",
            },
            {
                "category": "app_guide",
                "label": "📱 Cách chụp ảnh phân loại",
                "question": "Làm thế nào để chụp ảnh phân loại rác trong app GreenBin?",
            },
            {
                "category": "app_guide",
                "label": "📦 Đặt lịch thu gom cồng kềnh",
                "question": "Cách đặt lịch thu gom đồ cồng kềnh như sofa, nệm cũ như thế nào?",
            },
        ]
    }
