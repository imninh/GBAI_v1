"""Test hợp đồng phản hồi thiết bị phân loại (CP2).

Khoá chặt bốn quy tắc an toàn của hợp đồng (xem docstring của
:mod:`src.services.hop_dong_thiet_bi`). Test thuần — không gọi model, không chạm
CSDL, không chạm mạng.
"""

from __future__ import annotations

from uuid import UUID

from src.db.models import WasteCategory
from src.services.classifier_types import ClassifyOutcome
from src.services.dinh_tuyen_ngan import NGAN_OTHER
from src.services.hop_dong_thiet_bi import LABEL_UNKNOWN, dung_phan_hoi, sinh_item_id
from src.services.safety import RefusalReason

CAU_KHOA = {"item_id", "label", "confidence", "route", "review_required", "model_version"}


def _nhom(code: str, is_hazardous: bool = False) -> WasteCategory:
    return WasteCategory(code=code, name=code, is_hazardous=is_hazardous)


# --- Quy tắc 1: ca thường ------------------------------------------------


def test_ca_thuong_co_nhan_du_tin_khong_nguy_hai() -> None:
    outcome = ClassifyOutcome(category=_nhom("recyclable_plastic"), confidence=0.94, refused=False)

    ra = dung_phan_hoi(outcome, item_id="abc-123")

    assert ra["label"] == "recyclable_plastic"
    assert ra["route"] == "plastic"
    assert ra["review_required"] is False
    assert ra["item_id"] == "abc-123"
    assert ra["confidence"] == 0.94


def test_ca_thuong_ket_qua_du_du_sau_khoa() -> None:
    outcome = ClassifyOutcome(category=_nhom("recyclable_metal"), confidence=0.9, refused=False)

    assert set(dung_phan_hoi(outcome, item_id="m-1").keys()) == CAU_KHOA


# --- Quy tắc 2: từ chối / không chắc -------------------------------------


def test_ca_tu_choi_nhan_unknown_va_route_an_toan() -> None:
    outcome = ClassifyOutcome(
        category=None,
        confidence=0.3,
        refused=True,
        refusal_reason=RefusalReason.DUOI_NGUONG,
    )

    ra = dung_phan_hoi(outcome, item_id="x-1")

    assert ra["label"] == "UNKNOWN"
    assert ra["route"] == "other"
    assert ra["review_required"] is True


def test_ca_khong_co_nhan_cung_la_unknown_khong_phai_loi() -> None:
    """Outcome không từ chối nhưng không ra được nhãn — vẫn là UNKNOWN, không lỗi."""
    outcome = ClassifyOutcome(category=None, confidence=0.0, refused=False)

    ra = dung_phan_hoi(outcome, item_id="")

    assert ra["label"] == "UNKNOWN"
    assert ra["review_required"] is True


def test_label_unknown_khong_doi_thanh_other_o_phan_nhan() -> None:
    """⛔ UNKNOWN và other là hai thứ tách bạch — nhãn không được biến thành ngăn.

    ``label`` nói máy chủ nghĩ gì (UNKNOWN = chưa dám kết luận), ``route`` nói
    servo quay đâu (other = ngăn an toàn). Đổi UNKNOWN thành other ở phần nhãn
    là báo nhầm cho người duyệt.
    """
    outcome = ClassifyOutcome(
        category=None,
        confidence=0.2,
        refused=True,
        refusal_reason=RefusalReason.ANH_TOI,
    )

    ra = dung_phan_hoi(outcome, item_id="")

    assert ra["label"] == LABEL_UNKNOWN
    assert ra["label"] != "other"
    assert ra["route"] == NGAN_OTHER


# --- Quy tắc 3: nhóm nguy hại ---------------------------------------------


def test_nhom_nguy_hai_luon_yeu_cau_duyet_du_confidence_cao() -> None:
    outcome = ClassifyOutcome(category=_nhom("hazardous", is_hazardous=True), confidence=0.99, refused=False)

    ra = dung_phan_hoi(outcome, item_id="h-1")

    assert ra["label"] == "hazardous"
    assert ra["route"] == "other"
    assert ra["review_required"] is True


def test_nhom_nguy_hai_khong_dua_vao_ngan_thu_hoi() -> None:
    outcome = ClassifyOutcome(category=_nhom("hazardous", is_hazardous=True), confidence=0.98, refused=False)

    assert dung_phan_hoi(outcome, item_id="")["route"] == "other"


# --- Quy tắc 4: model_version ---------------------------------------------


def test_model_version_lay_tu_prompt_version_cua_outcome() -> None:
    outcome = ClassifyOutcome(
        category=_nhom("recyclable_paper"),
        confidence=0.9,
        refused=False,
        prompt_version="prompt-v3",
        model="gemini",
    )

    assert dung_phan_hoi(outcome, item_id="")["model_version"] == "prompt-v3"


def test_khong_co_prompt_version_thi_lay_model() -> None:
    outcome = ClassifyOutcome(
        category=_nhom("recyclable_paper"),
        confidence=0.9,
        refused=False,
        prompt_version="",
        model="gemini",
    )

    assert dung_phan_hoi(outcome, item_id="")["model_version"] == "gemini"


def test_khong_co_gi_thi_model_version_la_chuoi_rong() -> None:
    outcome = ClassifyOutcome(
        category=_nhom("recyclable_paper"),
        confidence=0.9,
        refused=False,
        prompt_version="",
        model="",
    )

    assert dung_phan_hoi(outcome, item_id="")["model_version"] == ""


# --- item_id ---------------------------------------------------------------


def test_thiet_bi_gui_item_id_thi_giu_nguyen_chuoi() -> None:
    assert sinh_item_id("abc-123") == "abc-123"


def test_thiet_bi_gui_item_id_co_khoang_trang_thi_bo_khoang_thua() -> None:
    assert sinh_item_id("  abc-123  ") == "abc-123"


def test_khong_gui_item_id_thi_sinh_uuid4() -> None:
    ra = sinh_item_id("")

    UUID(ra)  # ném lỗi nếu không phải UUID hợp lệ
    assert str(UUID(ra)) == ra
