"""Hệ thống RAG Chatbot đa năng của GreenBin AI.

Bao gồm 3 chức năng chính (áp dụng kỹ năng từ Cẩm nang hd.md):
1. F1: Hỏi đáp các luật và quy định liên quan đến rác (Luật BVMT 2020, NĐ 45/2022, Hướng dẫn 9368, nội quy toà nhà).
2. F2: Hỏi đáp các thùng rác còn khả thi gần đây (Tool-Augmented RAG đọc CSDL thời gian thực).
3. F3: Hướng dẫn cách sử dụng ứng dụng GreenBin AI (5 tab chức năng, chụp ảnh, đặt lịch, điểm xanh).

Hỗ trợ model LLM Mistral (MISTRAL_API_KEY) cùng các tầng bảo vệ:
- Input Guardrail (Unicode NFKC, Injection pattern filter)
- Cascade Intent Router (Rule-based -> LLM classifier)
- Strict Grounding Prompt + Delimiters + Canary Token
- Output Guardrail (PII Scrubbing + Canary check)
- HAX Principles (Source Badges, Confidence, Evidence Chips, 3-Level Fallback)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.orm import Session

from src.config import get_settings
from src.services.chatbot_tools import format_bins_for_llm_context, query_viable_bins
from src.services.pii import redact
from src.services.rag import (
    embed_query,
    reorder_context,
    retrieve,
    so_doan_co_embedding,
)
from src.services.vision import Usage, VisionUnavailableError, build_client_for, get_tier_model, get_vision_client

# Canary token chống lộ System Prompt (hd.md Phần 5.3)
CANARY_TOKEN = "GB_CANARY_SEC_2026_9876"

ChatIntent = Literal["waste_law", "bin_query", "app_guide", "out_of_scope"]


@dataclass
class ChatSourceChip:
    """Evidence chip / nguồn trích dẫn cho UI theo nguyên tắc HAX G11."""

    doc_title: str
    section: str
    quote: str
    doc_type: str = "law"
    source: str = ""
    score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "doc_title": self.doc_title,
            "section": self.section,
            "quote": self.quote,
            "doc_type": self.doc_type,
            "source": self.source,
            "score": round(self.score, 4),
        }


@dataclass
class ChatbotResponse:
    """Kết quả phản hồi của Chatbot gửi về cho client."""

    answer: str
    intent: ChatIntent
    confidence_level: str = "High"  # High | Medium | Low
    confidence_score: float = 1.0
    source_badge: str = "[AI sinh]"  # [AI sinh từ Luật BVMT 2020] | [Dữ liệu IoT] | [Hướng dẫn App] | [Mẫu quy tắc]
    sources: list[ChatSourceChip] = field(default_factory=list)
    viable_bins: list[dict[str, Any]] = field(default_factory=list)
    fallback_level: int = 1  # 1: LLM Inference | 2: Rule Fallback | 3: Abstain
    generated_by: str = "mistral"  # mistral | template | abstain
    usage: Usage = field(default_factory=Usage)

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "intent": self.intent,
            "confidence_level": self.confidence_level,
            "confidence_score": round(self.confidence_score, 4),
            "source_badge": self.source_badge,
            "sources": [s.as_dict() for s in self.sources],
            "viable_bins": self.viable_bins,
            "fallback_level": self.fallback_level,
            "generated_by": self.generated_by,
            "tokens_used": self.usage.tokens_in + self.usage.tokens_out,
            "cost_usd": self.usage.cost_usd,
        }


# --- 1. Input Guardrails & Injection Filter (hd.md Phần 5.1) --------------

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"bỏ\s+qua\s+(hết\s+|toàn\s+bộ\s+|mọi\s+)?(hướng\s+dẫn|quy\s+định|câu\s+lệnh)",
    r"reveal\s+(system\s+)?prompt",
    r"in\s+ra\s+(toàn\s+bộ\s+)?(system\s+prompt|prompt\s+hệ\s+thống|câu\s+lệnh\s+gốc)",
    r"you\s+are\s+now\s+(dan|an\s+unrestricted)",
    r"canary_token|canary\s+token",
]


def normalize_input(text: str) -> str:
    """Chuẩn hoá Unicode NFKC và loại bỏ ký tự vô hình (Zero-width chars)."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    # Loại bỏ Zero-width characters (u200B - u200D, uFEFF)
    cleaned = re.sub(r"[\u200B-\u200D\uFEFF]", "", normalized)
    return cleaned.strip()


def check_prompt_injection(text: str) -> bool:
    """Quét phát hiện Prompt Injection / Jailbreak."""
    lower = text.lower()
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE):
            return True
    return False


# --- 2. Intent Classifier (Cascade Rule-based Multi-Signal -> LLM) -------

_LAW_PATTERNS: list[tuple[str, int]] = [
    # Mức phạt & Chế tài (Trọng số rất cao)
    (r"(phạt|bị phạt|mức phạt|bao nhiêu tiền|phạt tiền|xử phạt|chế tài)", 12),
    (r"(nghị định 45|nd 45|nđ 45|luật bảo vệ môi trường|luật bvmt|luật 72|công văn 9368|cv 9368|hướng dẫn 9368)", 15),
    (r"(điều 26|điều 29|điều 75|điều 77|điều 79)", 15),
    (r"(bắt buộc|quy định|pháp luật|pháp lý|trách nhiệm|nghĩa vụ)", 6),
    (r"(3 nhóm|mấy nhóm|phân loại tại nguồn|hạn chót|31/12/2024)", 10),
    (r"(người gây ô nhiễm phải trả tiền|khối lượng|thể tích|chi phí thu gom)", 10),
    (r"(ban quản lý có quyền|từ chối thu gom|từ chối tiếp nhận|quyền từ chối)", 12),
    (r"(vỏ hộp sữa|tetra pak|tráng nhôm|bóc tách|bóc màng)", 10),
    (r"(nước tẩy bồn cầu|bình xịt muỗi|thùng nhựa tái chế|rác nguy hại|hầm b1)", 10),
    (r"(kích thước như thế nào|vượt quá 0\.5m|nặng trên 10kg|đăng ký trước 24|đăng ký trước)", 12),
    (r"(vứt rác bừa bãi|hành lang|nơi công cộng chung cư|nơi công cộng)", 10),
]

_APP_PATTERNS: list[tuple[str, int]] = [
    (r"(app greenbin|ứng dụng greenbin|ứng dụng|app)", 8),
    (r"(5 tab|tab chức năng|tab phân loại|tab yêu cầu|tab lịch|tab điểm gửi|tab tôi)", 15),
    (r"(cách chụp ảnh|chụp ảnh phân loại|mô tả chữ|gõ chữ|chụp rõ nét|phân loại bằng hình ảnh)", 12),
    (r"(đặt lịch thu gom|tạo yêu cầu mới|theo dõi tiến độ|chờ duyệt|đã xếp tuyến)", 12),
    (r"(mất kết nối mạng|mất mạng|offline|xem lịch offline)", 12),
    (r"(ảnh rác tôi chụp|lộ thông tin|mặt người|che mặt|bảo mật ảnh|quyền riêng tư)", 14),
    (r"(điểm xanh|green points|đổi căn hộ|đổi mật khẩu|lịch sử phân loại)", 12),
]

_BIN_PATTERNS: list[tuple[str, int]] = [
    (r"(thùng rác|thùng nào|bản đồ thùng|thùng thông minh)", 8),
    (r"(còn chỗ|sắp đầy|đã đầy|mức đầy|mất kết nối|hết pin)", 8),
    (r"(gần đây|gần tôi|gần nhất|vị trí thùng|ở đâu)", 6),
    (r"(đinh tiên hoàng|hàng trống|lương văn can|tràng tiền|hàng bài|hàng khay|lý thái tổ|hàng đào|cầu gỗ|lò sũ)", 12),
    (r"(thùng xanh|thùng vàng|thùng đỏ|màu xanh|màu vàng|màu đỏ|70%|90%)", 8),
]

_OUT_OF_SCOPE_PATTERNS: list[tuple[str, int]] = [
    (r"(thời tiết|dự báo thời tiết|nhiệt độ)", 15),
    (r"(bóng đá|ngoại hạng anh|world cup|cầu thủ)", 15),
    (r"(xổ số|lô đề|vé số|kết quả xổ số)", 15),
    (r"(viết thơ|bài thơ|làm thơ|kể chuyện|hát)", 15),
    (r"(tổng thống|chính trị|chiến tranh)", 15),
    (r"(viết code|python|javascript|lập trình)", 15),
]


def classify_intent_rule(text: str) -> ChatIntent | None:
    """Bộ phân loại Intent chuẩn xác cao bằng Multi-Signal Pattern Scorer."""
    from src.services.rag import normalize_text

    norm = normalize_text(text)
    lower = text.lower()

    # 1. Kiểm tra Out-of-scope trước nếu khớp từ khoá phi rác thải -> trả về None
    for pat, _ in _OUT_OF_SCOPE_PATTERNS:
        if re.search(pat, norm, re.IGNORECASE) or re.search(pat, lower, re.IGNORECASE):
            return None

    # 2. Tính điểm tín hiệu từng Intent
    scores: dict[str, int] = {"waste_law": 0, "bin_query": 0, "app_guide": 0}

    for pat, weight in _LAW_PATTERNS:
        if re.search(pat, norm, re.IGNORECASE) or re.search(pat, lower, re.IGNORECASE):
            scores["waste_law"] += weight

    for pat, weight in _APP_PATTERNS:
        if re.search(pat, norm, re.IGNORECASE) or re.search(pat, lower, re.IGNORECASE):
            scores["app_guide"] += weight

    for pat, weight in _BIN_PATTERNS:
        if re.search(pat, norm, re.IGNORECASE) or re.search(pat, lower, re.IGNORECASE):
            scores["bin_query"] += weight

    best_intent, max_score = max(scores.items(), key=lambda item: item[1])

    if max_score >= 6:
        # Nếu câu hỏi có cả yếu tố tìm thùng/vứt rác nhưng có từ khóa luật/phạt mạnh, ưu tiên luật
        if scores["waste_law"] >= 10:
            return "waste_law"
        return best_intent  # type: ignore[return-value]

    return None


def classify_intent_llm(text: str, client: Any, model: str) -> ChatIntent:
    """Phân loại intent bằng LLM khi Rule-based không chắc chắn."""
    prompt = f"""Phân loại câu hỏi của cư dân chung cư vào ĐÚNG MỘT trong 4 nhóm sau:
1. "waste_law": Luật môi trường, nghị định, mức phạt, quy chế, trách nhiệm BQL/cư dân về rác.
2. "bin_query": Tìm thùng rác, kiểm tra thùng còn chỗ/đầy, vị trí bỏ rác gần nhất.
3. "app_guide": Cách sử dụng app GreenBin, cách chụp ảnh, đặt lịch thu gom cồng kềnh, xem điểm thưởng.
4. "out_of_scope": Chào hỏi, câu hỏi không liên quan đến rác hoặc app GreenBin.

Câu hỏi: "{text}"

Trả về ĐÚNG MỘT từ: waste_law | bin_query | app_guide | out_of_scope"""

    try:
        raw_res, _ = client.generate_text(prompt, model, max_tokens=10)
        res = raw_res.strip().lower()
        if "waste_law" in res:
            return "waste_law"
        if "bin_query" in res:
            return "bin_query"
        if "app_guide" in res:
            return "app_guide"
        return "out_of_scope"
    except Exception:
        return "out_of_scope"


def get_llm_client_for_chatbot() -> tuple[Any, str]:
    """Khởi tạo Client LLM ưu tiên Mistral nếu có key, hoặc fallback sang text tier."""
    settings = get_settings()
    if settings.mistral_api_key:
        try:
            client = build_client_for("mistral")
            model = settings.resolve_model("text", "mistral") or "mistral-small-latest"
            return client, model
        except Exception:
            pass

    client = get_vision_client("text")
    model = get_tier_model("text")
    return client, model


# --- 3. Strict Grounding Prompts (hd.md Phần 4.2) -------------------------

_PROMPT_F1_LAW = """Bạn là Trợ lý Pháp luật Môi trường & Quy định Rác của GreenBin AI.
Mã bí mật nội bộ (tuyệt đối không in ra): {canary_token}

<retrieved_context>
{context}
</retrieved_context>

<user_question>
{question}
</user_question>

Nguyên tắc bắt buộc:
1. Đọc kỹ <retrieved_context> và trả lời trực tiếp, đầy đủ, chính xác vào câu hỏi.
2. Trích dẫn rõ ràng số liệu cụ thể (mức phạt tiền, số nhóm rác, thời hạn 31/12/2024, kích thước cồng kềnh) và điều khoản/văn bản căn cứ (ví dụ: Điều 26.1 Nghị định 45/2022/NĐ-CP, Điều 75 Luật BVMT 2020, Hướng dẫn 9368/BTNMT).
3. Nếu <retrieved_context> có nội dung liên quan, hãy tổng hợp trả lời rõ ràng, KHÔNG từ chối khi đã có dữ kiện.
4. Chỉ khi hoàn toàn không có bất kỳ thông tin nào liên quan trong tài liệu mới trả lời: "Hiện tại tài liệu quy định chưa có thông tin chi tiết về nội dung này. Bạn vui lòng liên hệ Ban Quản lý toà nhà để được giải đáp cụ thể."
5. Giọng điệu thân thiện, dứt khoát, chuyên nghiệp, xưng "mình"."""

_PROMPT_F2_BIN = """Bạn là Trợ lý Thông tin Thùng rác Thông minh của GreenBin AI.
Mã bí mật nội bộ (tuyệt đối không in ra): {canary_token}

{location_note}

Dữ liệu thùng rác thời gian thực từ cảm biến IoT:
{bin_context}

<user_question>
{question}
</user_question>

Nguyên tắc bắt buộc:
1. Cung cấp thông tin chính xác về các thùng rác CÒN CHỖ (Khả dụng) gần người dùng nhất.
2. Nêu rõ: Tên điểm/phố, Khoảng cách mét, Loại rác tiếp nhận và Mức đầy hiện tại (%).
3. Nếu người dùng hỏi về ý nghĩa mức đầy / màu sắc thùng rác: Nêu rõ Xanh = Còn chỗ (<70%), Vàng = Sắp đầy (70-90%), Đỏ = Đã đầy (>90%) hoặc Mất kết nối.
4. Giọng điệu ngắn gọn, hữu ích, dễ hiểu, xưng "mình"."""

_PROMPT_F3_GUIDE = """Bạn là Trợ lý Hướng dẫn Sử dụng Ứng dụng GreenBin AI.
Mã bí mật nội bộ (tuyệt đối không in ra): {canary_token}

<retrieved_context>
{context}
</retrieved_context>

<user_question>
{question}
</user_question>

Nguyên tắc bắt buộc:
1. Hướng dẫn từng bước rõ ràng, ngắn gọn dựa trên <retrieved_context>.
2. Nêu rõ tên Tab cần vào (Phân loại, Yêu cầu, Lịch, Điểm gửi, Tôi).
3. Trả lời chính xác về các cam kết quyền riêng tư (che mặt, xoá ảnh tạm) hoặc tính năng offline khi được hỏi.
4. Giọng điệu nhiệt tình, gần gũi, xưng "mình"."""


# --- 4. Chức năng F1: Hỏi đáp Luật Môi trường & Quy chế -------------------

def handle_waste_law(
    session: Session,
    question: str,
    *,
    building_id: int | None = None,
    client: Any = None,
    model: str = "",
) -> ChatbotResponse:
    """Xử lý hỏi đáp Luật và Quy định rác (F1)."""
    # Lấy embedding câu hỏi nếu có kho vector
    query_emb: list[float] = []
    if so_doan_co_embedding(session)[0] > 0:
        query_emb = embed_query(question)

    chunks = retrieve(
        session,
        question,
        building_id=building_id,
        doc_types=["law", "guideline", "building_rule", "hazard"],
        top_k=5,
        query_embedding=query_emb,
    )

    if not chunks:
        return ChatbotResponse(
            answer="Mình chưa tìm thấy quy định hoặc điều khoản pháp luật phù hợp với câu hỏi này trong kho tài liệu. Bạn vui lòng liên hệ trực tiếp BQL toà nhà nhé!",
            intent="waste_law",
            confidence_level="Low",
            confidence_score=0.2,
            source_badge="[Chưa có dữ liệu]",
            fallback_level=3,
            generated_by="abstain",
        )

    # Tái sắp xếp chống Lost-in-the-Middle (hd.md Phần 2.6)
    reordered_chunks = reorder_context(chunks)

    context_lines = []
    source_chips: list[ChatSourceChip] = []
    for c in reordered_chunks:
        context_lines.append(f"- {c.doc_title} · {c.section}: {c.content}")
        source_chips.append(
            ChatSourceChip(
                doc_title=c.doc_title,
                section=c.section,
                quote=c.content,
                doc_type=c.doc_type,
                source=c.source,
                score=c.score,
            )
        )

    context_text = "\n".join(context_lines)
    prompt = _PROMPT_F1_LAW.format(
        canary_token=CANARY_TOKEN,
        context=context_text,
        question=question,
    )

    top_score = max((c.score for c in chunks), default=0.0)
    conf_level = "High" if top_score >= 0.70 else ("Medium" if top_score >= 0.40 else "Low")
    badge = f"[Luật & Quy định: {chunks[0].doc_title}]"

    if client is None:
        client, model = get_llm_client_for_chatbot()

    try:
        text, usage = client.generate_text(prompt, model, max_tokens=500)
        # Quét Canary leak
        if CANARY_TOKEN in text:
            text = text.replace(CANARY_TOKEN, "").strip()
        # Quét PII
        cleaned_text = redact(text).text

        return ChatbotResponse(
            answer=cleaned_text,
            intent="waste_law",
            confidence_level=conf_level,
            confidence_score=top_score,
            source_badge=badge,
            sources=source_chips,
            fallback_level=1,
            generated_by="mistral" if "mistral" in model.lower() else "llm",
            usage=usage,
        )
    except (VisionUnavailableError, Exception):
        # Level 2 Fallback: Mẫu quy tắc dựng sẵn
        top = chunks[0]
        rule_answer = f"Theo quy định tại **{top.doc_title}** ({top.section}): {top.content}"
        return ChatbotResponse(
            answer=rule_answer,
            intent="waste_law",
            confidence_level=conf_level,
            confidence_score=top_score,
            source_badge="[Mẫu quy tắc]",
            sources=source_chips,
            fallback_level=2,
            generated_by="template",
        )


# --- 5. Chức năng F2: Tra cứu Thùng rác Khả thi (Tool-Augmented RAG) --------

def _detect_category_from_query(query: str) -> str | None:
    """Nhận diện loại rác người dùng muốn bỏ từ câu hỏi."""
    lowered = query.lower()
    if any(k in lowered for k in ["nhựa", "chai nhựa", "ly nhựa", "plastic"]):
        return "recyclable_plastic"
    if any(k in lowered for k in ["giấy", "bìa", "carton", "hộp sữa", "paper"]):
        return "recyclable_paper"
    if any(k in lowered for k in ["kim loại", "lon", "nhôm", "sắt", "metal"]):
        return "recyclable_metal"
    if any(k in lowered for k in ["thuỷ tinh", "chai thuỷ tinh", "glass"]):
        return "recyclable_glass"
    if any(k in lowered for k in ["tái chế", "đồ tái chế", "recyclable"]):
        return "recyclable"
    if any(k in lowered for k in ["thực phẩm", "thức ăn", "hữu cơ", "rau củ", "organic"]):
        return "organic"
    if any(k in lowered for k in ["pin", "ắc quy", "bóng đèn", "thuốc", "hoá chất", "nguy hại", "hazardous"]):
        return "hazardous"
    if any(k in lowered for k in ["cồng kềnh", "sofa", "nệm", "giường", "tủ", "bulky"]):
        return "bulky"
    return None


_LANDMARKS: dict[str, tuple[float, float]] = {
    "dinh tien hoang": (21.0285, 105.8542),
    "hang trong": (21.0296, 105.8501),
    "luong van can": (21.0322, 105.8503),
    "trang tien": (21.0256, 105.8521),
    "hang bai": (21.0247, 105.8543),
    "hang khay": (21.0291, 105.8523),
    "ly thai to": (21.0326, 105.8541),
    "hang dao": (21.0331, 105.8492),
    "cau go": (21.0312, 105.8507),
    "lo su": (21.0289, 105.8556),
    "bo ho": (21.0285, 105.8542),
    "hoan kiem": (21.0285, 105.8542),
    "ly thuong kiet": (21.0271, 105.8519),
}


def handle_bin_query(
    session: Session,
    question: str,
    *,
    building_id: int | None = None,
    user_lat: float | None = None,
    user_lng: float | None = None,
    client: Any = None,
    model: str = "",
) -> ChatbotResponse:
    """Xử lý tra cứu thùng rác thông minh khả thi (F2)."""
    from src.services.rag import normalize_text
    norm_q = normalize_text(question)

    if user_lat is None and user_lng is None:
        for landmark_name, coords in _LANDMARKS.items():
            if landmark_name in norm_q:
                user_lat, user_lng = coords
                break

    cat_code = _detect_category_from_query(question)
    bins = query_viable_bins(
        session,
        category_code=cat_code,
        building_id=building_id,
        user_lat=user_lat,
        user_lng=user_lng,
        limit=5,
    )

    guide_chunks = retrieve(
        session,
        question,
        doc_types=["app_guide"],
        top_k=2,
    )
    guide_text = "\n".join(c.content for c in guide_chunks) if guide_chunks else ""

    if not bins and not guide_chunks:
        return ChatbotResponse(
            answer="Hiện tại mình không tìm thấy thùng rác nào còn chỗ hoặc khả dụng ở khu vực gần bạn. Bạn hãy kiểm tra lại tại phòng rác tầng hoặc liên hệ BQL nhé!",
            intent="bin_query",
            confidence_level="Medium",
            confidence_score=0.5,
            source_badge="[Dữ liệu IoT thời gian thực]",
            viable_bins=[],
            fallback_level=3,
            generated_by="abstain",
        )

    loc_note = (
        f"Vị trí cư dân đã được định vị GPS chính xác tại toạ độ ({user_lat:.5f}, {user_lng:.5f}). Khoảng cách các thùng bên dưới được tính toán trực tiếp từ toạ độ GPS này."
        if user_lat is not None and user_lng is not None
        else "Vị trí cư dân: Xác định theo khu vực toà nhà."
    )
    bin_context = format_bins_for_llm_context(bins)
    if guide_text:
        bin_context = f"{bin_context}\n\nQuy định tra cứu & bảng màu trên bản đồ:\n{guide_text}"

    prompt = _PROMPT_F2_BIN.format(
        canary_token=CANARY_TOKEN,
        location_note=loc_note,
        bin_context=bin_context,
        question=question,
    )

    if client is None:
        client, model = get_llm_client_for_chatbot()

    viable_dict = [b.as_dict() for b in bins]

    try:
        text, usage = client.generate_text(prompt, model, max_tokens=400)
        if CANARY_TOKEN in text:
            text = text.replace(CANARY_TOKEN, "").strip()
        cleaned_text = redact(text).text

        return ChatbotResponse(
            answer=cleaned_text,
            intent="bin_query",
            confidence_level="High",
            confidence_score=0.95,
            source_badge="[Dữ liệu IoT thời gian thực]",
            viable_bins=viable_dict,
            fallback_level=1,
            generated_by="mistral" if "mistral" in model.lower() else "llm",
            usage=usage,
        )
    except (VisionUnavailableError, Exception):
        # Level 2 Fallback: Tổng hợp mẫu định sẵn
        top_bins = [b for b in bins if b.is_viable][:3]
        if top_bins:
            items_str = "\n".join(
                f"- **{b.name}** ({b.address}): Mức đầy **{b.fill_percent}%**, nhận [{', '.join(b.category_names)}]"
                for b in top_bins
            )
            rule_text = f"Dưới đây là các thùng rác còn chỗ gần nhất:\n{items_str}"
        elif bins:
            rule_text = f"Thùng rác gần nhất hiện là **{bins[0].name}** ({bins[0].address}) nhưng đang ở trạng thái {bins[0].status_label_vi}."
        else:
            rule_text = ""

        if guide_chunks and any(k in norm_q for k in ["lam sao", "mau", "ban do", "y nghia"]):
            rule_text = f"{guide_chunks[0].content}\n\n{rule_text}".strip()

        return ChatbotResponse(
            answer=rule_text,
            intent="bin_query",
            confidence_level="High",
            confidence_score=0.9,
            source_badge="[Mẫu quy tắc - Dữ liệu IoT]",
            viable_bins=viable_dict,
            fallback_level=2,
            generated_by="template",
        )


# --- 6. Chức năng F3: Hướng dẫn Sử dụng App -------------------------------

def handle_app_guide(
    session: Session,
    question: str,
    *,
    building_id: int | None = None,
    client: Any = None,
    model: str = "",
) -> ChatbotResponse:
    """Xử lý hướng dẫn sử dụng ứng dụng GreenBin AI (F3)."""
    query_emb: list[float] = []
    if so_doan_co_embedding(session)[0] > 0:
        query_emb = embed_query(question)

    chunks = retrieve(
        session,
        question,
        building_id=building_id,
        doc_types=["app_guide"],
        top_k=4,
        query_embedding=query_emb,
    )

    if not chunks:
        # Thử tìm rộng hơn nếu chưa có chunk doc_type="app_guide"
        chunks = retrieve(
            session,
            question,
            building_id=building_id,
            top_k=3,
            query_embedding=query_emb,
        )

    if not chunks:
        return ChatbotResponse(
            answer="Bạn có thể sử dụng các tính năng của GreenBin qua 5 tab: (1) Phân loại rác bằng ảnh/chữ; (2) Đặt lịch thu gom đồ cồng kềnh; (3) Xem lịch thu gom toà nhà; (4) Xem bản đồ điểm gửi; (5) Quản lý tài khoản & Điểm xanh.",
            intent="app_guide",
            confidence_level="Medium",
            confidence_score=0.6,
            source_badge="[Hướng dẫn cơ bản]",
            fallback_level=2,
            generated_by="template",
        )

    reordered = reorder_context(chunks)
    context_lines = []
    source_chips: list[ChatSourceChip] = []
    for c in reordered:
        context_lines.append(f"- {c.doc_title} · {c.section}: {c.content}")
        source_chips.append(
            ChatSourceChip(
                doc_title=c.doc_title,
                section=c.section,
                quote=c.content,
                doc_type=c.doc_type,
                source=c.source,
                score=c.score,
            )
        )

    context_text = "\n".join(context_lines)
    prompt = _PROMPT_F3_GUIDE.format(
        canary_token=CANARY_TOKEN,
        context=context_text,
        question=question,
    )

    top_score = max((c.score for c in chunks), default=0.0)
    conf_level = "High" if top_score >= 0.65 else ("Medium" if top_score >= 0.35 else "Low")

    if client is None:
        client, model = get_llm_client_for_chatbot()

    try:
        text, usage = client.generate_text(prompt, model, max_tokens=450)
        if CANARY_TOKEN in text:
            text = text.replace(CANARY_TOKEN, "").strip()
        cleaned_text = redact(text).text

        return ChatbotResponse(
            answer=cleaned_text,
            intent="app_guide",
            confidence_level=conf_level,
            confidence_score=top_score,
            source_badge="[Hướng dẫn App GreenBin]",
            sources=source_chips,
            fallback_level=1,
            generated_by="mistral" if "mistral" in model.lower() else "llm",
            usage=usage,
        )
    except (VisionUnavailableError, Exception):
        top = chunks[0]
        rule_answer = f"**{top.section}**:\n{top.content}"
        return ChatbotResponse(
            answer=rule_answer,
            intent="app_guide",
            confidence_level=conf_level,
            confidence_score=top_score,
            source_badge="[Mẫu quy tắc - Sổ tay App]",
            sources=source_chips,
            fallback_level=2,
            generated_by="template",
        )


# --- 7. Điểm Điều phối Chính (Chatbot Orchestrator) -----------------------

def ask_chatbot(
    session: Session,
    question: str,
    *,
    building_id: int | None = None,
    user_lat: float | None = None,
    user_lng: float | None = None,
) -> ChatbotResponse:
    """Xử lý toàn diện một câu hỏi của người dùng gửi tới RAG Chatbot.

    Quy trình:
    1. Chuẩn hoá văn bản (Unicode NFKC)
    2. Input Guardrail: Kiểm tra Prompt Injection
    3. Cascade Intent Router (Rule -> LLM)
    4. Điều phối tới F1 (Luật), F2 (Thùng rác), F3 (App Guide) hoặc Abstain
    5. Output Guardrail (PII Sanitization + Canary Check)
    """
    clean_q = normalize_input(question)
    if not clean_q:
        return ChatbotResponse(
            answer="Xin chào! Bạn hãy nhập câu hỏi về phân loại rác, tra cứu thùng rác gần nhất hoặc cách dùng app GreenBin nhé.",
            intent="out_of_scope",
            confidence_level="High",
            confidence_score=1.0,
            source_badge="[GreenBin AI]",
            fallback_level=3,
            generated_by="abstain",
        )

    # 1. Input Guardrail: Injection check
    if check_prompt_injection(clean_q):
        return ChatbotResponse(
            answer="Yêu cầu chứa câu lệnh không hợp lệ hoặc vượt quá quyền truy cập. Mình chỉ có thể hỗ trợ về quy định rác và ứng dụng GreenBin.",
            intent="out_of_scope",
            confidence_level="High",
            confidence_score=1.0,
            source_badge="[Hàng rào bảo mật]",
            fallback_level=3,
            generated_by="abstain",
        )

    # 2. Intent Classification
    client, model = get_llm_client_for_chatbot()
    intent = classify_intent_rule(clean_q)
    if intent is None:
        intent = classify_intent_llm(clean_q, client, model)

    # 3. Routing & Execution
    if intent == "waste_law":
        return handle_waste_law(session, clean_q, building_id=building_id, client=client, model=model)
    elif intent == "bin_query":
        return handle_bin_query(
            session, clean_q, building_id=building_id, user_lat=user_lat, user_lng=user_lng, client=client, model=model
        )
    elif intent == "app_guide":
        return handle_app_guide(session, clean_q, building_id=building_id, client=client, model=model)
    else:
        return ChatbotResponse(
            answer=(
                "Chào bạn! Mình là Trợ lý GreenBin AI. Mình chuyên hỗ trợ:\n"
                "1. **Luật & Quy định**: Mức phạt vứt rác, quy định Luật BVMT 2020, NĐ 45, nội quy toà nhà.\n"
                "2. **Tra cứu Thùng rác**: Tìm thùng rác còn chỗ gần bạn, vị trí bỏ rác tái chế / nguy hại.\n"
                "3. **Hướng dẫn Sử dụng App**: Cách chụp ảnh phân loại, đặt lịch thu gom đồ cồng kềnh, xem điểm xanh.\n\n"
                "Bạn cần mình hỗ trợ thông tin nào trong các mục trên ạ?"
            ),
            intent="out_of_scope",
            confidence_level="High",
            confidence_score=1.0,
            source_badge="[Trợ lý GreenBin AI]",
            fallback_level=3,
            generated_by="abstain",
        )
