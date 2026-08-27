"""Endpoint API cho RAG Chatbot (Hỏi đáp luật, thùng rác, hướng dẫn app)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from src.api.deps import CurrentUser, DbSession
from src.db.models import ChatMessage, ChatSession
from src.services.auth import write_audit
from src.services.chatbot import ask_chatbot

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


class ChatbotAskRequest(BaseModel):
    """Yêu cầu hỏi đáp gửi tới Chatbot."""

    question: str = Field(..., min_length=1, max_length=1000, description="Nội dung câu hỏi của cư dân")
    session_id: str | None = Field(default=None, description="Mã phiên hội thoại (UUID) để duy trì ngữ cảnh")
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
    char_start: int | None = None
    char_end: int | None = None
    verified: bool = True


class ChatbotAskResponse(BaseModel):
    """Phản hồi đầy đủ của Chatbot kèm siêu dữ liệu và căn cứ giải thích."""

    session_id: str = ""
    message_id: int | None = None
    answer: str
    intent: str
    confidence_level: str = "High"
    confidence_score: float = 1.0
    finish_reason: str = "stop"
    refusal: str | None = None
    model_version_pin: str = "greenbin-rag-v3"
    source_badge: str = "[AI sinh]"
    sources: list[ChatSourceChipResponse] = []
    viable_bins: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    fallback_level: int = 1
    generated_by: str = "mistral"
    tokens_used: int = 0
    cost_usd: float = 0.0
    execution_trace: dict[str, Any] = {}


class ChatbotFeedbackRequest(BaseModel):
    """Phản hồi đánh giá 👍 / 👎 của người dùng (HAX G15)."""

    question: str
    answer: str
    intent: str
    rating: int = Field(..., description="1 là Thích (👍), -1 là Không thích (👎)")
    comment: str = ""

    @field_validator("rating")
    @classmethod
    def _check_rating(cls, v: int) -> int:
        if v not in (1, -1):
            raise ValueError("rating chỉ nhận 1 (👍) hoặc -1 (👎)")
        return v


@router.post("/ask", response_model=ChatbotAskResponse)
def ask(payload: ChatbotAskRequest, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """Hỏi đáp tự do với Trợ lý GreenBin AI RAG (Luật, Thùng rác, Hướng dẫn App)."""
    building_id = payload.building_id
    if (
        building_id is not None
        and user.building_id is not None
        and building_id != user.building_id
    ):
        building_id = user.building_id

    res = ask_chatbot(
        session,
        payload.question,
        session_id=payload.session_id,
        user=user,
        building_id=building_id,
        user_lat=payload.lat,
        user_lng=payload.lng,
        user_id=str(user.id),
        ten_nguoi=user.full_name,
    )
    return res.as_dict()


@router.get("/sessions")
def list_sessions(session: DbSession, user: CurrentUser) -> list[dict[str, Any]]:
    """Lấy danh sách các phiên hội thoại của người dùng."""
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(20)
    )
    records = session.execute(stmt).scalars().all()
    return [
        {
            "id": s.id,
            "title": s.title,
            "building_id": s.building_id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in records
    ]


@router.get("/sessions/{session_id}/history")
def get_session_history(session_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """Khôi phục trạng thái và lịch sử tin nhắn của một phiên hội thoại (State Rehydration)."""
    chat_sess = session.get(ChatSession, session_id)
    if not chat_sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiên hội thoại")

    # Kiểm tra quyền truy cập (RBAC / session isolation)
    if chat_sess.user_id is not None and chat_sess.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập phiên này")

    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    msgs = session.execute(stmt).scalars().all()

    return {
        "session_id": chat_sess.id,
        "title": chat_sess.title,
        "working_memory": chat_sess.working_memory,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "intent": m.intent,
                "sources": m.sources_json,
                "tool_calls": m.tool_calls_json,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ],
    }


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """Xóa một phiên hội thoại."""
    chat_sess = session.get(ChatSession, session_id)
    if not chat_sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiên hội thoại")

    if chat_sess.user_id is not None and chat_sess.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền xóa phiên này")

    # Xóa messages liên quan
    stmt = select(ChatMessage).where(ChatMessage.session_id == session_id)
    msgs = session.execute(stmt).scalars().all()
    for m in msgs:
        session.delete(m)

    session.delete(chat_sess)
    session.commit()
    return {"status": "success", "message": "Đã xóa phiên hội thoại thành công"}


@router.post("/feedback")
def submit_feedback(payload: ChatbotFeedbackRequest, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """Ghi nhận đánh giá phản hồi 👍 / 👎 tức thì từ người dùng.

    Ghi thật vào audit_log (HAX G15 & Triplet Observability).
    """
    write_audit(
        session,
        actor=user,
        action="chatbot_feedback",
        entity="chatbot",
        detail={
            "question": payload.question[:500],
            "intent": payload.intent,
            "rating": payload.rating,
            "comment": payload.comment[:300],
        },
    )
    return {
        "status": "success",
        "message": "Cảm ơn bạn đã gửi đánh giá phản hồi.",
    }


@router.get("/suggested-questions")
def get_suggested_questions(user: CurrentUser) -> dict[str, list[dict[str, str]]]:
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

