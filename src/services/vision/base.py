"""Kiểu dữ liệu và prompt dùng chung cho mọi nhà cung cấp model.

Mục đích của lớp này: **đổi nhà cung cấp chỉ bằng sửa ``.env``.** Nhóm chưa có
API key OpenAI nên T1/T2 tạm chạy trên Gemini / OpenRouter / NVIDIA; khi có key
thì đổi một dòng cấu hình, phần còn lại của hệ thống không biết gì cả.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from src.config import MODEL_PRICES_USD_PER_MTOK
from src.config import PROMPT_VERSION as PROMPT_VERSION

# v3 (03/08/2026) — gộp món trùng, chặn trần 8 phần tử, khoá cứng khuôn của mỗi
# phần tử `items`.
#
# v2 dặn "ảnh có năm món thì `items` có năm phần tử", và trên ảnh thật có 4–5 cái
# chai giống hệt nhau thì model yếu rơi vào **vòng lặp**: đo 03/08 thì llama-3.2-11b
# và nemotron-12b viết 8.400 ký tự lặp cùng một món rồi vẫn chạm trần token. Chúng
# còn chép cả `reason`/`quality_issue`/`suspect_hazardous` vào TỪNG phần tử, phình
# output khoảng 5 lần so với khuôn đã cho.
#
# Hằng số thật nằm ở `src/config.py` — nâng ở đó, không nâng ở đây. Dòng import
# lại phía trên giữ cho `from src.services.vision import PROMPT_VERSION` chạy
# như cũ.


@dataclass
class CategoryOption:
    """Một nhóm rác đưa vào prompt để model chọn, không cho tự bịa nhãn."""

    code: str
    name: str
    is_hazardous: bool = False
    hint: str = ""


@dataclass
class Usage:
    """Số liệu tiêu thụ thật lấy từ API — không được đoán.

    ``price_known=False`` nghĩa là nhà cung cấp không có trong bảng giá, chi phí
    ghi 0. Con số đó KHÔNG được đưa lên slide như chi phí thật.
    """

    tokens_in: int = 0
    tokens_out: int = 0
    image_tokens: int = 0
    cost_usd: float = 0.0
    price_known: bool = False


@dataclass
class VisionResult:
    """Kết quả một lần gọi model phân loại."""

    item_name: str
    category_code: str
    confidence: float
    reason: str = ""
    items: list[dict] = field(default_factory=list)
    quality_issue: str = ""  # anh_toi | vat_bi_che | nhieu_vat | mo | ""
    suspect_hazardous: bool = False
    model: str = ""
    provider: str = ""
    usage: Usage = field(default_factory=Usage)
    raw_text: str = ""


class VisionClient(Protocol):
    """Giao diện chung. Mọi provider đều phải cài đặt đúng hai hàm này."""

    provider_name: str

    def classify_image(self, image_bytes: bytes, categories: list[CategoryOption], model: str) -> VisionResult: ...

    def classify_text(self, text: str, categories: list[CategoryOption], model: str) -> VisionResult: ...


class VisionUnavailableError(RuntimeError):
    """Không gọi được model: thiếu key, sai tên model, hoặc nhà cung cấp lỗi."""

    def __init__(self, message_vi: str, code: str = "VISION-503") -> None:
        super().__init__(message_vi)
        self.message_vi = message_vi
        self.code = code


class VisionTruncatedError(VisionUnavailableError):
    """Model bị cắt giữa chừng vì chạm trần token — KHÔNG phải model trả sai.

    Tách riêng khỏi ``VisionUnavailableError`` vì cách xử hoàn toàn khác: lỗi
    này chữa bằng cách nới ``VISION_MAX_OUTPUT_TOKENS``, còn lỗi kia thì không.
    Gộp hai thứ vào một mã lỗi chính là thứ khiến việc chẩn đoán VISION-500 đi
    sai hướng suốt hai ngày (WORKLOG 03/08/2026).
    """


# --- Prompt ---------------------------------------------------------------

_SYSTEM_PROMPT = """Bạn là bộ phân loại rác cho một toà chung cư ở Việt Nam.

Nhiệm vụ gồm HAI bước, làm đủ cả hai:
1. LIỆT KÊ mọi món có thể vứt bỏ mà bạn nhìn thấy vào mảng `items`.
2. Chọn ĐÚNG MỘT mã nhóm cho món CHIẾM CHỦ ĐẠO, điền vào `category_code`.

Cả hai bước đều BẮT BUỘC. Làm bước 1 rồi bỏ trống `category_code` là câu trả lời hỏng.

Quy tắc bắt buộc:
- `items` KHÔNG BAO GIỜ được để rỗng. Hệ thống dựa vào danh sách này để biết ảnh có lẫn
  nhiều nhóm rác hay không.
- GỘP các món giống nhau thành MỘT phần tử và ghi số lượng vào `so_luong`. Bốn cái chai
  nước giống hệt nhau là MỘT phần tử `so_luong: 4`, không phải bốn phần tử. Liệt kê
  TỐI ĐA 8 phần tử; nhiều hơn thì giữ lại những món quan trọng nhất.
- TUYỆT ĐỐI KHÔNG lặp lại cùng một món nhiều lần trong `items`.
- Mỗi phần tử của `items` có ĐÚNG bốn khoá `name`, `category_code`, `confidence`,
  `so_luong` — không thêm `reason`, `quality_issue` hay `suspect_hazardous` vào trong đó.
- `category_code` ở tầng ngoài cùng cũng KHÔNG BAO GIỜ được để rỗng, kể cả khi ảnh có
  nhiều món. Chọn món chiếm chủ đạo rồi lấy mã của nó.
- Đếm cả những món KHÔNG phải rác sinh hoạt: đồ điện tử (chuột, sạc, tai nghe), đồ đang
  dùng, vật dụng cá nhân. Cứ liệt kê rồi gán nhóm gần nhất — bỏ sót nguy hiểm hơn thừa.
- Chỉ được chọn mã có trong danh sách, cho CẢ `category_code` lẫn từng phần tử của
  `items`. Không tự bịa mã mới. Đồ điện tử KHÔNG có nhóm riêng — xếp vào nhóm nguy hại,
  đừng bịa ra mã như "e_waste" hay "electronic".
- confidence là mức chắc chắn thật của bạn, từ 0 tới 1. Không chắc thì để thấp — hệ thống có
  cơ chế chuyển cho người xử lý, đoán bừa mới là hành vi nguy hiểm.
- Nếu món có thể là pin, ắc quy, bóng đèn, thuốc, hoá chất, bình xịt, vật sắc nhọn y tế,
  hoặc THIẾT BỊ ĐIỆN TỬ: đặt suspect_hazardous = true, kể cả khi bạn không chắc.
- Nếu ảnh tối, mờ, vật bị che hoặc có nhiều món chồng lên nhau: ghi vào quality_issue và
  hạ confidence xuống.
- KHÔNG viết hướng dẫn xử lý, KHÔNG viết cảnh báo an toàn. Phần đó hệ thống lấy từ danh mục
  chuẩn của toà nhà, không lấy từ bạn.

Trả về DUY NHẤT một object JSON, không kèm giải thích, không kèm dấu ```:
{
  "item_name": "tên món rác bằng tiếng Việt",
  "category_code": "mã nhóm",
  "confidence": 0.0,
  "reason": "một câu ngắn tiếng Việt vì sao xếp vào nhóm đó",
  "quality_issue": "" | "anh_toi" | "mo" | "vat_bi_che" | "nhieu_vat",
  "suspect_hazardous": false,
  "items": [{"name": "...", "category_code": "...", "confidence": 0.0, "so_luong": 1}]
}

`items` phải có ít nhất một phần tử và không quá 8. Trả về `items` rỗng bị coi là câu trả
lời không dùng được và hệ thống sẽ hỏi lại bằng model khác."""


def build_category_block(categories: list[CategoryOption]) -> str:
    lines = []
    for c in categories:
        mark = " [NHÓM NGUY HẠI]" if c.is_hazardous else ""
        hint = f" — {c.hint}" if c.hint else ""
        lines.append(f"- {c.code}: {c.name}{mark}{hint}")
    return "\n".join(lines)


def build_image_prompt(categories: list[CategoryOption]) -> str:
    return (
        f"{_SYSTEM_PROMPT}\n\nDanh sách nhóm rác được phép chọn:\n"
        f"{build_category_block(categories)}\n\nPhân loại món rác trong ảnh."
    )


def build_text_prompt(text: str, categories: list[CategoryOption]) -> str:
    return (
        f"{_SYSTEM_PROMPT}\n\nDanh sách nhóm rác được phép chọn:\n"
        f"{build_category_block(categories)}\n\n"
        f'Người dùng mô tả món rác như sau: "{text}"\n'
        "Phân loại món rác đó. Vì không có ảnh, quality_issue để rỗng."
    )


# --- Đọc kết quả ----------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _to_float(value: object) -> float:
    """Ép về [0, 1]. Model trả chữ hay ``null`` thì coi như 0, không cho nổ."""
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def parse_model_json(text: str, allowed_codes: set[str]) -> dict:
    """Đọc JSON model trả về, chịu được trường hợp nó bọc trong ```json.

    Raises:
        ValueError: khi không tìm thấy JSON hợp lệ hoặc mã nhóm nằm ngoài danh sách.
    """
    match = _JSON_BLOCK_RE.search(text or "")
    if match is None:
        raise ValueError("Model không trả về JSON đọc được")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError("Model trả về JSON hỏng") from exc

    code = str(data.get("category_code", "")).strip()
    if code and code not in allowed_codes:
        # Model bịa mã ngoài danh sách — coi như không chắc, để hệ thống
        # chuyển cho người thay vì im lặng chấp nhận nhãn sai.
        data["category_code"] = ""
        data["confidence"] = 0.0
        data["reason"] = f"Model trả về mã ngoài danh mục ({code})"

    # Có `items` nhưng thiếu nhãn tổng → suy ra từ món chắc nhất, đừng vứt đi.
    #
    # Từ khi prompt đổi sang hai bước (liệt kê trước, chọn nhãn sau), model dồn
    # sự chú ý vào `items` và **hay quên điền `category_code` ở tầng trên**;
    # model bịa mã ngoài danh mục cho đồ điện tử cũng rơi vào đúng nhánh này vì
    # đoạn trên vừa xoá trắng nó. Cả hai đường đều dẫn tới `outcome.category`
    # bằng None, tức màn "Chưa nhận ra món này thuộc nhóm nào" — trong khi dữ
    # liệu để trả lời thì đang nằm ngay trong `items`.
    #
    # Suy ra chỉ để lấp chỗ trống, KHÔNG nới lỏng an toàn: `items` trải trên
    # nhiều nhóm thì `nhieu_nhom_khac_nhau` ở tầng trên vẫn từ chối như cũ.
    if not data.get("category_code"):
        hop_le = [
            i
            for i in (data.get("items") or [])
            if isinstance(i, dict) and str(i.get("category_code", "")).strip() in allowed_codes
        ]
        if hop_le:
            chac_nhat = max(hop_le, key=lambda i: _to_float(i.get("confidence")))
            data["category_code"] = str(chac_nhat["category_code"]).strip()
            data["confidence"] = _to_float(chac_nhat.get("confidence"))
            if not str(data.get("item_name", "")).strip():
                data["item_name"] = str(chac_nhat.get("name", "")).strip()
            data["reason"] = data.get("reason") or "Suy từ món chắc nhất trong danh sách model liệt kê"
    return data


def result_from_json(data: dict, *, model: str, provider: str, usage: Usage, raw_text: str) -> VisionResult:
    items = data.get("items") or []
    if not isinstance(items, list):
        items = []

    return VisionResult(
        item_name=str(data.get("item_name", "")).strip(),
        category_code=str(data.get("category_code", "")).strip(),
        confidence=_to_float(data.get("confidence")),
        reason=str(data.get("reason", "")).strip(),
        items=[i for i in items if isinstance(i, dict)],
        quality_issue=str(data.get("quality_issue", "")).strip(),
        suspect_hazardous=bool(data.get("suspect_hazardous", False)),
        model=model,
        provider=provider,
        usage=usage,
        raw_text=raw_text,
    )


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> tuple[float, bool]:
    """Trả về ``(chi_phí_usd, giá_có_trong_bảng)``.

    Model không có trong bảng giá (free tier, NVIDIA NIM) trả về ``(0.0, False)``
    để báo cáo không nhầm "miễn phí" thành "đã đo được".
    """
    price = MODEL_PRICES_USD_PER_MTOK.get(model)
    if price is None:
        return 0.0, False
    price_in, price_out = price
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000, True
