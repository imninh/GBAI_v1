"""Theo dõi hệ AI bằng Langfuse (P87, bước 1: chatbot + advise).

Quy tắc cứng (§2 đặc tả P87):
- Mọi dữ liệu gửi lên Langfuse phải qua ``che_du_lieu`` — che số điện thoại,
  email, toạ độ GPS, họ tên người dùng.
- ``user_id`` chỉ gửi id số, cấm gửi tên / sđt / email làm định danh.
- ``LANGFUSE_ENABLED`` mặc định TẮT; thiếu khoá cũng tắt.
- Langfuse hỏng -> tuyệt đối không làm hỏng câu trả lời người dùng. Bọc lại,
  ghi ``logger.warning(..., exc_info=True)``, rồi chạy tiếp.
- Cấm ``except Exception: pass`` (§2): mọi bắt rộng phải ghi log warning.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from src.config import get_settings

logger = logging.getLogger(__name__)

try:
    from langfuse import Langfuse

    _CO_LANGFUSE = True
except Exception:  # pragma: no cover - langfuse là tuỳ chọn, không bắt buộc chạy
    Langfuse = None
    _CO_LANGFUSE = False


# --- Che dữ liệu cá nhân -------------------------------------------------
# Nhãn cố định, đọc được, KHÔNG băm (§2).
_TEN_MAU = ["Nguyễn Văn An", "Trần Thị Bình", "Lê Văn Cường", "Phạm Thị Dung"]


def che_du_lieu(text: str, *, ten_nguoi: str | None = None) -> str:
    """Che mọi dữ liệu cá nhân trước khi gửi lên Langfuse.

    Che: số điện thoại, email, toạ độ GPS, họ tên người dùng.
    KHÔNG che: số hiệu điều luật, nghị định, số tiền phạt (§6 test 8) — nếu che
    nhầm thì vết trở nên vô dụng.
    """
    if not text:
        return text
    s = text
    if ten_nguoi and ten_nguoi.strip():
        target = ten_nguoi.strip()
        target_lower = target.lower()
        idx = 0
        while True:
            lower_s = s.lower()
            found_idx = lower_s.find(target_lower, idx)
            if found_idx == -1:
                break
            s = s[:found_idx] + "[TEN]" + s[found_idx + len(target) :]
            idx = found_idx + len("[TEN]")

    # Số điện thoại: 0xxxxxxxxx, 0xxx xxx xxx, +84xxxxxxxxx
    s = re.sub(r"0\d{3}[ .-]\d{3}[ .-]\d{3}", "[SDT]", s)
    s = re.sub(r"0\d{9}", "[SDT]", s)
    s = re.sub(r"\+84\d{9}", "[SDT]", s)
    # Email
    s = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "[EMAIL]", s)
    # Toạ độ GPS: cặp lat,lng (vd 21.0285, 105.8542)
    s = re.sub(r"[-+]?\d{1,2}\.\d{2,}[,\s]+[-+]?\d{1,3}\.\d{2,}", "[TOA_DO]", s)
    # Toạ độ GPS: gắn nhãn lat/lng/toạ độ/vĩ độ/kinh độ
    s = re.sub(
        r"(?:lat|lng|toa do|toạ độ|vĩ độ|kinh độ)[:=\s]*[-+]?\d+(?:\.\d+)?",
        "[TOA_DO]",
        s,
        flags=re.IGNORECASE,
    )
    # Họ tên: danh sách mẫu + mẫu "tôi là <tên>"
    for ten in _TEN_MAU:
        s = s.replace(ten, "[TEN]")
    s = re.sub(
        r"(tôi là|tên tôi là|tên của tôi là|tên:)\s*([A-ZÀ-Ỵ][a-zà-ỵ]*(?:\s+[A-ZÀ-Ỵ][a-zà-ỵ]*){1,2})",
        lambda m: m.group(0).replace(m.group(2), "[TEN]"),
        s,
        flags=re.IGNORECASE,
    )
    return s


class TheoDoiAI:
    """Lớp theo dõi hệ AI qua Langfuse. Tắt hoàn toàn khi thiếu cấu hình."""

    def __init__(self) -> None:
        self.enabled = False
        self.client = None
        if not _CO_LANGFUSE:
            logger.warning("Langfuse chưa được cài -> theo dõi AI tắt.")
            return
        settings = get_settings()
        if not settings.langfuse_enabled:
            return
        pk = settings.langfuse_public_key
        sk = settings.langfuse_secret_key
        if not (pk and sk):
            logger.warning(
                "LANGFUSE_ENABLED=true nhưng thiếu LANGFUSE_PUBLIC_KEY/SECRET_KEY "
                "-> theo dõi AI tắt."
            )
            return
        try:
            self.client = Langfuse(
                public_key=pk,
                secret_key=sk,
                host=settings.langfuse_base_url or "https://cloud.langfuse.com",
            )
            self.enabled = True
        except Exception:
            logger.warning("Khởi tạo Langfuse thất bại -> theo dõi AI tắt.", exc_info=True)

    def trace_chatbot(
        self,
        *,
        question: str,
        resp: Any,
        bat_dau: float,
        user_id: str = "khach",
        ten_nguoi: str | None = None,
    ) -> None:
        """Ghi một trace ``chatbot`` kèm span ``truy_hoi`` / ``goi_model`` và score.

        Mọi dữ liệu đều đã che. Hỏng thì ghi warning rồi thôi, không ném lỗi.
        """
        if not self.enabled or self.client is None:
            return
        try:
            q = che_du_lieu(question, ten_nguoi=ten_nguoi)
            a = che_du_lieu(resp.answer, ten_nguoi=ten_nguoi)
            tags = [str(getattr(resp, "intent", "unknown")), get_settings().app_env]
            ctx = {"user_id": str(user_id), "tags": tags, "name": "chatbot"}
            trace = self.client.start_observation(
                name="chatbot",
                as_type="chain",
                input=q,
                output=a,
                trace_context=ctx,
            )
            # Span truy hồi: chỉ số đoạn + điểm, KHÔNG gửi nguyên văn đoạn.
            srcs = getattr(resp, "sources", None) or []
            if srcs:
                diem = max((s.score for s in srcs), default=0.0)
                trace.start_observation(
                    name="truy_hoi",
                    as_type="retriever",
                    input={"so_doan": len(srcs), "diem_truy_hoi": round(diem, 4)},
                    output={"da_che": True},
                ).end()
            # Span gọi model: chỉ khi thực sự gọi model (không phải template/abstain).
            gb = getattr(resp, "generated_by", "")
            usage = getattr(resp, "usage", None)
            if gb and gb not in ("template", "abstain") and usage is not None:
                model = get_settings().resolve_model_for("text")
                trace.start_observation(
                    name="goi_model",
                    as_type="generation",
                    model=model,
                    input={"provider": gb},
                    output={"da_che": True},
                    usage_details={"input": usage.tokens_in, "output": usage.tokens_out},
                    metadata={"do_tre_ms": round((time.perf_counter() - bat_dau) * 1000, 1)},
                ).end()
            # Điểm needs_verification: câu độ tự tin thấp / rơi fallback cần người kiểm.
            can = (
                getattr(resp, "confidence_level", "") == "Low"
                or getattr(resp, "fallback_level", 0) >= 2
                or gb in ("template", "abstain")
            )
            try:
                trace.score_trace(name="needs_verification", value=1.0 if can else 0.0)
            except Exception:
                logger.warning("Langfuse ghi score thất bại.", exc_info=True)
            trace.end()
            self.client.flush()
        except Exception:
            logger.warning("Langfuse ghi trace chatbot thất bại.", exc_info=True)


_theo_doi: TheoDoiAI | None = None


def lay_theo_doi() -> TheoDoiAI | None:
    """Trả về singleton theo dõi; None nếu đang tắt."""
    global _theo_doi
    if _theo_doi is None:
        _theo_doi = TheoDoiAI()
    return _theo_doi if _theo_doi.enabled else None


def ghi_trace_chatbot(
    *,
    question: str,
    resp: Any,
    bat_dau: float,
    user_id: str = "khach",
    ten_nguoi: str | None = None,
) -> None:
    """Gắn trace cho một lượt hỏi chatbot. Không bao giờ ném lỗi ra ngoài."""
    try:
        td = lay_theo_doi()
        if td is None:
            return
        td.trace_chatbot(
            question=question,
            resp=resp,
            bat_dau=bat_dau,
            user_id=user_id,
            ten_nguoi=ten_nguoi,
        )
    except Exception:
        logger.warning(
            "Ghi trace chatbot bị lỗi, bỏ qua để không ảnh hưởng người dùng.",
            exc_info=True,
        )

