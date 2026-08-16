"""Kho tri thức quy định phân loại và node ``advise``.

Ba điểm khiến phần này **vượt naive RAG** (PLO 3):

1. **Hybrid** — gộp điểm BM25 (từ khoá) với cosine similarity (embedding).
   BM25 chạy thuần Python nên hệ thống vẫn truy hồi được khi chưa có API key,
   embedding chỉ là phần cộng thêm.
2. **Lọc theo toà trước khi xếp hạng** — quy định mỗi toà mỗi khác, nên trộn
   chung tài liệu của toà khác vào là trả lời sai chứ không phải "hơi lệch".
3. **Đo được** — :func:`retrieve` trả về điểm từng nguồn, có script tính
   precision@5 trong ``eval/``.

Mọi câu trả lời đều **phải chỉ ra được nguồn**. Khối UI nào đưa kết luận mà
không có đường dẫn về văn bản gốc là khối thiết kế sai (FRONTEND_SPEC mục 0).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import KnowledgeChunk, KnowledgeDoc, WasteCategory
from src.services.vision import Usage, VisionUnavailableError

# Tham số BM25 tiêu chuẩn.
_BM25_K1 = 1.5
_BM25_B = 0.75

# Từ dừng tiếng Việt — bỏ đi để điểm từ khoá không bị các hư từ chi phối.
_STOPWORDS = {
    "la", "cua", "va", "co", "khong", "thi", "o", "cho", "de", "duoc", "nay", "do",
    "mot", "cac", "nhung", "voi", "trong", "tren", "duoi", "khi", "nao", "gi", "vao",
    "ra", "toi", "minh", "ban", "phai", "se", "da", "dang", "bi", "boi", "hay", "hoac",
}


@dataclass
class RetrievedChunk:
    """Một đoạn văn bản đã truy hồi, kèm điểm để đưa lên UI và để đo."""

    chunk_id: int
    doc_id: int
    doc_title: str
    doc_type: str
    section: str
    content: str
    source: str = ""
    building_id: int | None = None
    needs_verification: bool = False
    bm25_score: float = 0.0
    vector_score: float = 0.0
    score: float = 0.0

    def as_source_dict(self) -> dict:
        """Khuôn ``advice_sources`` mà frontend dùng để vẽ chip nguồn."""
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "doc_title": self.doc_title,
            "doc_type": self.doc_type,
            "section": self.section,
            "quote": self.content,
            "source": self.source,
            "needs_verification": self.needs_verification,
            "score": round(self.score, 4),
        }


@dataclass
class AdviceResult:
    """Kết quả node advise."""

    advice: str = ""
    sources: list[RetrievedChunk] = field(default_factory=list)
    degraded: bool = False
    degraded_note: str = ""
    generated_by: str = "template"  # template | llm
    usage: Usage = field(default_factory=Usage)


# --- Tách từ và BM25 ------------------------------------------------------


def normalize_text(text: str) -> str:
    """Hạ chữ thường và bỏ dấu — để "thùng" và "thung" khớp nhau."""
    lowered = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(c for c in lowered if unicodedata.category(c) != "Mn")
    return stripped.replace("đ", "d")


def tokenize(text: str) -> list[str]:
    """Tách từ đơn giản, bỏ từ dừng. Đủ dùng cho kho vài chục trang."""
    tokens = re.findall(r"[a-z0-9]+", normalize_text(text))
    return [t for t in tokens if len(t) > 1 and t not in _STOPWORDS]


def bm25_scores(query: str, documents: list[list[str]]) -> list[float]:
    """Tính điểm BM25 của truy vấn với từng tài liệu đã tách từ."""
    if not documents:
        return []
    query_terms = tokenize(query)
    if not query_terms:
        return [0.0] * len(documents)

    total_docs = len(documents)
    avg_len = sum(len(d) for d in documents) / total_docs or 1.0
    doc_freq: Counter[str] = Counter()
    for doc in documents:
        for term in set(doc):
            doc_freq[term] += 1

    scores: list[float] = []
    for doc in documents:
        counts = Counter(doc)
        length = len(doc) or 1
        score = 0.0
        for term in query_terms:
            freq = counts.get(term, 0)
            if freq == 0:
                continue
            idf = math.log(1 + (total_docs - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            denom = freq + _BM25_K1 * (1 - _BM25_B + _BM25_B * length / avg_len)
            score += idf * (freq * (_BM25_K1 + 1)) / denom
        scores.append(score)
    return scores


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _normalize_scores(values: list[float]) -> list[float]:
    """Đưa điểm về [0,1] để gộp hai thang đo khác nhau."""
    if not values:
        return []
    top = max(values)
    if top <= 0:
        return [0.0] * len(values)
    return [v / top for v in values]


# --- Truy hồi -------------------------------------------------------------


def retrieve(
    session: Session,
    query: str,
    *,
    building_id: int | None = None,
    doc_types: list[str] | None = None,
    top_k: int = 5,
    query_embedding: list[float] | None = None,
) -> list[RetrievedChunk]:
    """Truy hồi các đoạn quy định liên quan nhất.

    Lọc **trước** khi xếp hạng: chỉ lấy tài liệu của đúng toà đang hỏi cộng với
    tài liệu dùng chung (``building_id IS NULL``). Trộn quy định toà khác vào là
    trả lời sai, không phải "hơi lệch".
    """
    statement = select(KnowledgeChunk, KnowledgeDoc).join(KnowledgeDoc, KnowledgeChunk.doc_id == KnowledgeDoc.id)
    if building_id is not None:
        statement = statement.where(
            or_(KnowledgeDoc.building_id == building_id, KnowledgeDoc.building_id.is_(None))
        )
    else:
        statement = statement.where(KnowledgeDoc.building_id.is_(None))
    if doc_types:
        statement = statement.where(KnowledgeDoc.doc_type.in_(doc_types))

    rows = session.execute(statement).all()
    if not rows:
        return []

    candidates: list[RetrievedChunk] = []
    tokenized: list[list[str]] = []
    for chunk, doc in rows:
        meta = chunk.meta or {}
        candidates.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                doc_id=doc.id,
                doc_title=doc.title,
                doc_type=doc.doc_type,
                section=chunk.section,
                content=chunk.content,
                source=doc.source,
                building_id=doc.building_id,
                needs_verification=bool(meta.get("needs_verification")),
            )
        )
        tokenized.append(tokenize(f"{doc.title} {chunk.section} {chunk.content}"))

    keyword_scores = _normalize_scores(bm25_scores(query, tokenized))
    vector_scores = [0.0] * len(candidates)
    if query_embedding:
        raw = []
        for chunk, _doc in rows:
            raw.append(cosine(query_embedding, chunk.embedding or []))
        vector_scores = _normalize_scores(raw)

    # Trọng số nghiêng về từ khoá vì kho nhỏ và nhiều câu hỏi rất cụ thể ("bỏ
    # pin ở đâu"); embedding đóng vai trò bắt các cách diễn đạt khác. Chỉnh được
    # qua ``RAG_VECTOR_WEIGHT`` — xem ghi chú ở ``config.py`` về việc vì sao chưa
    # đổi mặc dù phép quét gợi ý một con số cao hơn.
    #
    # Không có vector (chưa nhúng kho, hoặc nhúng câu hỏi hỏng) thì **xếp hạng
    # thuần BM25**, không phải trả về rỗng: truy hồi phải sống khi mất API.
    trong_so = get_settings().rag_vector_weight
    has_vector = any(v > 0 for v in vector_scores)
    for index, candidate in enumerate(candidates):
        candidate.bm25_score = keyword_scores[index]
        candidate.vector_score = vector_scores[index]
        candidate.score = (
            (1.0 - trong_so) * keyword_scores[index] + trong_so * vector_scores[index]
            if has_vector
            else keyword_scores[index]
        )

    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    return [c for c in ranked[:top_k] if c.score > 0]


# --- Sinh hướng dẫn -------------------------------------------------------

_ADVICE_PROMPT = """Bạn viết hướng dẫn bỏ rác cho cư dân một chung cư Việt Nam.

Món rác: {item_name}
Nhóm rác đã xác định: {category_name} (thùng màu {bin_color})
Hướng dẫn xử lý chuẩn của danh mục: {handling_note}

Các đoạn quy định liên quan của toà nhà:
{sources}

Viết 2–4 câu tiếng Việt, giọng thân thiện nhưng dứt khoát, xưng "mình".
Chỉ dùng thông tin trong các đoạn quy định trên và hướng dẫn chuẩn ở trên.
KHÔNG bịa thêm khung giờ, vị trí thùng hay mức phạt không có trong đoạn quy định.
KHÔNG viết cảnh báo an toàn — phần đó hệ thống lấy từ danh mục chuẩn.
Không lặp lại tên nhóm rác ở đầu câu, người dùng đã thấy nó ở khối phía trên rồi.
Trả về đúng đoạn văn, không tiêu đề, không gạch đầu dòng."""


def _template_advice(category: WasteCategory | None, chunks: list[RetrievedChunk]) -> str:
    """Hướng dẫn dựng sẵn từ CSDL, dùng khi không gọi được LLM.

    Đây là đường lui của trạng thái "suy giảm một phần": vẫn đúng, vẫn có
    nguồn, chỉ là câu chữ khô hơn.
    """
    parts: list[str] = []
    if category is not None and category.handling_note:
        parts.append(category.handling_note)
    if chunks:
        parts.append(f"Theo {chunks[0].doc_title} — {chunks[0].section}: {chunks[0].content}")
    return " ".join(parts).strip()


def advise(
    session: Session,
    *,
    item_name: str,
    category: WasteCategory | None,
    building_id: int | None,
    query: str = "",
    top_k: int = 5,
) -> AdviceResult:
    """Tra quy định của toà và viết hướng dẫn có trích nguồn.

    Node này được phép **suy giảm một phần**: nếu không truy hồi được quy định
    riêng của toà, hệ thống vẫn trả hướng dẫn chung kèm băng cảnh báo, thay vì
    làm hỏng cả luồng (FRONTEND_SPEC mục 6, trạng thái 4).
    """
    search_text = " ".join(filter(None, [item_name, category.name if category else "", query]))
    # Chỉ nhúng câu hỏi khi kho quy định thật sự có vector để so — không thì đó
    # là một lệnh gọi API tiêu quota mà không đổi lấy gì. Bản thân lệnh gọi này
    # cũng có cache đĩa nên món rác hỏi lại lần hai là miễn phí.
    query_embedding: list[float] = []
    if so_doan_co_embedding(session)[0] > 0:
        query_embedding = embed_query(search_text)
    chunks = retrieve(
        session, search_text, building_id=building_id, top_k=top_k, query_embedding=query_embedding
    )

    result = AdviceResult(sources=chunks)
    if not chunks:
        result.degraded = True
        result.degraded_note = (
            "Mình nhận ra món rác nhưng chưa tra được quy định riêng của toà. "
            "Hướng dẫn dưới đây là hướng dẫn chung."
        )

    source_block = "\n".join(
        f"- {c.doc_title} · {c.section}: {c.content}" for c in chunks
    ) or "(không truy hồi được đoạn quy định nào)"

    prompt = _ADVICE_PROMPT.format(
        item_name=item_name or (category.name if category else "món rác"),
        category_name=category.name if category else "chưa xác định",
        bin_color=category.bin_color if category else "chưa xác định",
        handling_note=category.handling_note if category else "",
        sources=source_block,
    )

    try:
        from src.services.vision import get_tier_model, get_vision_client

        # Bước advise chạy sau MỌI lần phân loại thành công nên nó là chỗ tiêu
        # quota nhanh nhất — cho nó nhà cung cấp riêng ở tầng ``text``.
        client = get_vision_client("text")
        text, usage = client.generate_text(prompt, get_tier_model("text"), max_tokens=400)  # type: ignore[attr-defined]
    except (VisionUnavailableError, AttributeError, ValueError):
        result.advice = _template_advice(category, chunks)
        result.generated_by = "template"
        if not result.degraded:
            result.degraded = True
            result.degraded_note = (
                "Chưa gọi được model sinh hướng dẫn nên mình dùng hướng dẫn chuẩn của danh mục."
            )
        return result

    cleaned = (text or "").strip()
    if not cleaned:
        result.advice = _template_advice(category, chunks)
        result.generated_by = "template"
        return result

    result.advice = cleaned
    result.generated_by = "llm"
    result.usage = usage
    return result


# --- Chỉ mục embedding ----------------------------------------------------


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Nhúng một loạt đoạn văn. Trả về ``[]`` nếu không nhúng được.

    Embedding dùng **nhà cung cấp riêng** (``EMBEDDING_PROVIDER``), không đi
    theo tầng ``text``: nơi sinh văn bản tốt chưa chắc có endpoint embedding
    dùng được. Đo 02/08/2026: NVIDIA không trả về vector qua đường
    OpenAI-compatible, nên nếu tầng ``text`` chạy NVIDIA mà embedding cũng bám
    theo thì phần vector của RAG chết lặng.

    Rỗng là một kết quả hợp lệ, không phải lỗi: :func:`retrieve` tự chạy thuần
    BM25 khi không có vector.
    """
    settings = get_settings()
    model = settings.resolve_embedding_model()
    if not texts or not model:
        return []

    provider = settings.resolve_embedding_provider()
    try:
        from src.services.vision import build_client_for

        client = build_client_for(provider)
        # Gemini có endpoint embedding riêng và nhận thêm số chiều; nhánh
        # OpenAI-compatible chỉ nhận tên model.
        if provider == "gemini":
            return client.embed(texts, model, settings.embedding_dimensions)  # type: ignore[attr-defined]
        return client.embed(texts, model)  # type: ignore[attr-defined]
    except (VisionUnavailableError, AttributeError):
        return []


def _duong_dan_cache(text: str) -> Path:
    settings = get_settings()
    khoa = f"{settings.resolve_embedding_provider()}|{settings.resolve_embedding_model()}|{settings.embedding_dimensions}|{text}"
    ten = hashlib.sha256(khoa.encode("utf-8")).hexdigest()[:32]
    return Path(settings.llm_cache_dir) / "embeddings" / f"{ten}.json"


def embed_query(text: str) -> list[float]:
    """Nhúng câu hỏi, **có cache trên đĩa theo hash đầu vào**.

    Đây là chỗ duy nhất trong luồng thường phải gọi embedding theo từng request,
    nên nó cũng là chỗ tốn quota. Trong chung cư, cùng một món rác được hỏi đi
    hỏi lại rất nhiều ("hộp sữa giấy", "pin cũ"), nên cache đĩa cắt gần hết
    lượng gọi lặp — đúng yêu cầu ở ``CLAUDE.md`` mục 9.

    Trả về ``[]`` khi không nhúng được; người gọi coi đó là "chạy thuần BM25".
    """
    text = (text or "").strip()
    if not text:
        return []

    duong_dan = _duong_dan_cache(text)
    try:
        if duong_dan.exists():
            return json.loads(duong_dan.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass  # cache hỏng thì tính lại, không làm hỏng luồng

    vectors = embed_texts([text])
    vector = vectors[0] if vectors else []
    if vector:
        try:
            duong_dan.parent.mkdir(parents=True, exist_ok=True)
            duong_dan.write_text(json.dumps(vector), encoding="utf-8")
        except OSError:
            pass  # không ghi được cache thì thôi, không phải lỗi của người dùng
    return vector


def embed_chunks(session: Session, *, limit: int = 500) -> int:
    """Tính embedding cho các đoạn quy định chưa có. Trả về số đoạn đã xử lý.

    Gọi lại nhiều lần vô hại: đoạn nào có vector rồi thì bỏ qua. Không nhúng
    được thì trả 0 và hệ thống chạy thuần BM25 — mất một phần chất lượng truy
    hồi nhưng không ai bị chặn.
    """
    pending = [c for c in session.scalars(select(KnowledgeChunk).limit(limit)).all() if not c.embedding]
    if not pending:
        return 0

    vectors = embed_texts([f"{c.section} {c.content}" for c in pending])
    if len(vectors) != len(pending):
        return 0
    for chunk, vector in zip(pending, vectors, strict=True):
        chunk.embedding = vector
    session.commit()
    return len(pending)


def so_doan_co_embedding(session: Session) -> tuple[int, int]:
    """``(số đoạn đã có vector, tổng số đoạn)`` — cho trang Vận hành."""
    rows = session.scalars(select(KnowledgeChunk)).all()
    return sum(1 for c in rows if c.embedding), len(rows)
