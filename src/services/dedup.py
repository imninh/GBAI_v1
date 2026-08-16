"""Gộp trùng lặp phản hồi.

Trùng lặp xảy ra thường xuyên: cùng một khách trả lời khảo sát hai lần, sale
copy nguyên nội dung vào CRM, comment bị crawl lặp. Không gộp thì mọi con số
trong insight đều bị thổi phồng.

Slice 0 dùng băm chính xác trên text đã chuẩn hoá. Gần-trùng (MinHash /
SimHash) bổ sung ở Slice 1 khi khối lượng đủ lớn để thấy vấn đề.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Chuẩn hoá text để so trùng: bỏ dấu câu, gộp khoảng trắng, hạ chữ thường.

    Giữ nguyên dấu tiếng Việt — "gia" và "giá" là hai từ khác nhau, bỏ dấu sẽ
    gộp nhầm các phản hồi không liên quan.
    """
    normalized = unicodedata.normalize("NFC", text or "")
    normalized = _PUNCT_RE.sub(" ", normalized)
    normalized = _SPACE_RE.sub(" ", normalized)
    return normalized.strip().lower()


def dedup_hash(text: str) -> str:
    """Băm nội dung đã chuẩn hoá. Hai phản hồi cùng hash được coi là một."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """Ước lượng số token của text tiếng Việt.

    Xấp xỉ thô ~2,2 token mỗi từ — đủ chính xác để dự toán chi phí trước khi
    chạy lô lớn. Số token thật lấy từ response của API khi chạy thực.
    """
    words = len(normalize_text(text).split())
    return max(1, round(words * 2.2))
