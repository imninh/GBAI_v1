"""Ẩn danh dữ liệu cá nhân trước khi đưa vào mô hình AI.

Quy định chương trình: không đưa dữ liệu cá nhân/nhạy cảm thật vào hệ thống.
Module này là hàng rào kỹ thuật thực thi điều đó — mọi text đi tới LLM đều
phải đi qua :func:`redact` trước.

Chiến lược hai lớp:

1. **Regex** (module này) — bắt chắc các mẫu có cấu trúc: số điện thoại,
   email, CCCD/CMND, số tài khoản, và tên riêng đi sau đại từ xưng hô tiếng
   Việt ("anh Minh", "chị Lan").
2. **NER** (bổ sung ở Slice 1) — bắt tên riêng đứng độc lập, địa chỉ.

Placeholder được đánh số ổn định trong phạm vi một văn bản, nên LLM vẫn hiểu
được ngữ cảnh ("[TÊN_1] gọi lại 3 lần") mà không nhìn thấy dữ liệu thật.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field

# --- Các mẫu có cấu trúc ------------------------------------------------

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Di động VN: 0|+84 + đầu số 3/5/7/8/9 + 8 chữ số. Cho phép . - hoặc khoảng trắng xen giữa.
MOBILE_RE = re.compile(r"(?<!\d)(?:\+?84|0)[\s.\-]?[35789](?:[\s.\-]?\d){8}(?!\d)")

# Cố định VN: 02x + 8 chữ số.
LANDLINE_RE = re.compile(r"(?<!\d)0?2\d[\s.\-]?(?:[\s.\-]?\d){7,8}(?!\d)")

# CCCD 12 số đứng độc lập.
CCCD_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")

# CMND/CCCD/số tài khoản đi kèm từ khoá — tránh nhầm với giá tiền.
KEYED_ID_RE = re.compile(
    r"(cmnd|cccd|căn cước|chứng minh nhân dân|chứng minh thư)\s*[:.\-]?\s*(\d{9,12})",
    re.IGNORECASE,
)
BANK_RE = re.compile(
    r"(stk|số tài khoản|tài khoản|tk)\s*[:.\-]?\s*(\d{6,20})",
    re.IGNORECASE,
)

# Tên riêng đi sau đại từ xưng hô. Chỉ thay phần tên, giữ lại đại từ để câu còn tự nhiên.
TITLE_NAME_RE = re.compile(
    r"\b(anh|chị|chi|em|cô|co|chú|chu|bác|bac|ông|ong|bà|ba|mr|ms|mrs)\s+"
    r"([^\W\d_]+(?:\s+[^\W\d_]+){0,2})",
    re.IGNORECASE,
)

PLACEHOLDER_RE = re.compile(r"\[[A-ZÀ-Ỹ_]+_\d+\]")

# Từ thường đứng sau đại từ xưng hô nhưng không phải tên riêng.
_NOT_NAMES = {
    "ấy", "ta", "này", "kia", "đó", "ạ", "à", "ơi", "nhân", "viên", "sale",
    "tư", "vấn", "quản", "lý", "chủ", "đầu", "bên", "công", "ty", "khách",
    "hàng", "em", "anh", "chị", "cô", "chú", "bác", "ông", "bà",
}


@dataclass
class RedactionResult:
    """Kết quả ẩn danh một văn bản."""

    text: str
    mapping: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


class _Redactor:
    """Giữ bộ đếm placeholder trong phạm vi một văn bản."""

    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}
        self.counts: dict[str, int] = {}
        self._seen: dict[str, str] = {}
        self._next_index: dict[str, int] = {}

    def placeholder_for(self, kind: str, value: str) -> str:
        """Trả về placeholder cho một giá trị; giá trị giống nhau dùng lại cùng placeholder."""
        key = f"{kind}:{value.strip()}"
        if key in self._seen:
            return self._seen[key]

        index = self._next_index.get(kind, 0) + 1
        self._next_index[kind] = index
        token = f"[{kind}_{index}]"

        self._seen[key] = token
        self.mapping[token] = value.strip()
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return token

    def apply(self, text: str, pattern: re.Pattern[str], kind: str, group: int = 0) -> str:
        """Thay mọi khớp của ``pattern`` bằng placeholder loại ``kind``."""

        def _replace(match: re.Match[str]) -> str:
            value = match.group(group)
            token = self.placeholder_for(kind, value)
            if group == 0:
                return token
            # Giữ nguyên phần dẫn (từ khoá / đại từ), chỉ thay phần nhạy cảm.
            start, end = match.span(group)
            return match.group(0)[: start - match.start()] + token + match.group(0)[end - match.start() :]

        return pattern.sub(_replace, text)

    def apply_names(self, text: str) -> str:
        """Thay tên riêng sau đại từ xưng hô, bỏ qua các từ không phải tên."""

        def _replace(match: re.Match[str]) -> str:
            title, name = match.group(1), match.group(2)
            words = name.split()
            # Chỉ nhận khi từ đầu viết hoa và không nằm trong danh sách loại trừ.
            if not words or not words[0][:1].isupper() or words[0].lower() in _NOT_NAMES:
                return match.group(0)
            kept = [w for w in words if w[:1].isupper() and w.lower() not in _NOT_NAMES]
            if not kept:
                return match.group(0)
            token = self.placeholder_for("TÊN", " ".join(kept))
            tail = name[len(" ".join(kept)) :]
            return f"{title} {token}{tail}"

        return TITLE_NAME_RE.sub(_replace, text)


def redact(text: str) -> RedactionResult:
    """Ẩn danh một văn bản, trả về text đã che cùng bảng ánh xạ.

    Thứ tự xử lý có ý nghĩa: email trước số điện thoại (email chứa chữ số),
    ID có từ khoá trước ID trần (tránh cắt đôi chuỗi số).
    """
    if not text:
        return RedactionResult(text="", mapping={}, counts={})

    redactor = _Redactor()
    out = text
    out = redactor.apply(out, EMAIL_RE, "EMAIL")
    out = redactor.apply(out, KEYED_ID_RE, "CCCD", group=2)
    out = redactor.apply(out, BANK_RE, "STK", group=2)
    out = redactor.apply(out, MOBILE_RE, "SĐT")
    out = redactor.apply(out, LANDLINE_RE, "SĐT")
    out = redactor.apply(out, CCCD_RE, "CCCD")
    out = redactor.apply_names(out)

    return RedactionResult(text=out, mapping=redactor.mapping, counts=redactor.counts)


def contains_pii(text: str) -> list[tuple[str, str]]:
    """Kiểm tra text còn sót dữ liệu cá nhân có cấu trúc hay không.

    Dùng làm chốt chặn cuối trước khi gửi payload lên API LLM, và làm assert
    trong test. Trả về danh sách ``(loại, giá trị)``; rỗng nghĩa là sạch.
    """
    checks: list[tuple[str, re.Pattern[str]]] = [
        ("EMAIL", EMAIL_RE),
        ("SĐT", MOBILE_RE),
        ("SĐT", LANDLINE_RE),
        ("CCCD", CCCD_RE),
    ]
    findings: list[tuple[str, str]] = []
    for kind, pattern in checks:
        findings.extend((kind, m.group(0)) for m in pattern.finditer(text))
    return findings


def assert_clean(text: str) -> None:
    """Ném lỗi nếu text còn dữ liệu cá nhân. Gọi ngay trước mọi lệnh gọi LLM."""
    findings = contains_pii(text)
    if findings:
        kinds = ", ".join(sorted({kind for kind, _ in findings}))
        raise ValueError(f"Phát hiện dữ liệu cá nhân chưa được ẩn danh ({kinds}) — huỷ gửi tới LLM")


def hash_author(value: str) -> str:
    """Băm định danh tác giả để đếm được số người mà không lưu danh tính."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def restore(text: str, mapping: dict[str, str]) -> str:
    """Khôi phục văn bản gốc từ placeholder. CHỈ dùng cho manager, phải ghi audit log."""
    out = text
    for token, value in mapping.items():
        out = out.replace(token, value)
    return out


def redact_many(texts: list[str], on_item: Callable[[int, RedactionResult], None] | None = None) -> list[RedactionResult]:
    """Ẩn danh một lô văn bản. ``on_item`` để báo tiến độ khi chạy lô lớn."""
    results: list[RedactionResult] = []
    for index, text in enumerate(texts):
        result = redact(text)
        if on_item is not None:
            on_item(index, result)
        results.append(result)
    return results
