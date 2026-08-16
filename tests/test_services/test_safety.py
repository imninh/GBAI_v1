"""Test hàng rào an toàn — module `src/services/safety.py`.

Bao phủ ba cơ chế trong docstring của module: danh sách chặn cứng, ngưỡng
confidence riêng theo nhóm, và lý do từ chối lấy từ danh sách cố định. Đây là
module duy nhất trong `src/services/` chưa có file test riêng — `test_classifier.py`
chỉ phủ các nhánh an toàn qua luồng chạy end-to-end.

Mọi test ở đây **không gọi API thật**: nhánh nào đi qua `classify_waste` thì
thay lớp vision bằng model giả, đúng cách `test_classifier.py` đang làm.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import WasteCategory
from src.services import classifier, safety
from src.services.classifier import classify_waste
from src.services.safety import RefusalReason
from tests.conftest import FakeVisionClient, make_result


@pytest.fixture(autouse=True)
def _tat_model_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tắt tầng T0.5 cho các test đi qua `classify_waste`."""
    monkeypatch.setattr(classifier, "classify_image_local", lambda *a, **k: None)


_MODEL_GIA: dict[str, str] = {"t1": "model-t1", "t2": "model-t2", "text": "model-text"}


def _dung_model_gia(
    monkeypatch: pytest.MonkeyPatch,
    *results,
    theo_tang: dict[str, FakeVisionClient] | None = None,
    nha_cung_cap: dict[str, str] | None = None,
) -> FakeVisionClient:
    """Thay lớp vision bằng model giả — không đụng mạng."""
    fake = FakeVisionClient(results=list(results))
    clients = theo_tang or {}
    providers = nha_cung_cap or {}
    monkeypatch.setattr(classifier, "get_vision_client", lambda tier="t1": clients.get(tier, fake))
    monkeypatch.setattr(classifier, "get_tier_model", lambda tier="t1": _MODEL_GIA[tier])
    monkeypatch.setattr(classifier, "get_tier_provider", lambda tier="t1": providers.get(tier, "fake"))
    return fake


# --- Danh sách chặn cứng -------------------------------------------------


def test_danh_sach_chan_cung_co_du_ba_nhom_va_thong_tin_day_du() -> None:
    """Ba luật theo CLAUDE.md mục 5: vật sắc nhọn y tế · bình gas · hoá chất."""
    assert len(safety.HARD_BLOCK_RULES) == 3
    codes = [rule.code for rule in safety.HARD_BLOCK_RULES]
    assert set(codes) == {"vat_sac_nhon_y_te", "binh_gas", "hoa_chat"}
    assert len(codes) == len(set(codes)), "Mã luật chặn cứng không được trùng nhau"
    for rule in safety.HARD_BLOCK_RULES:
        assert rule.label_vi and rule.keywords and rule.instruction_vi, "Luật thiếu nhãn, từ khoá hoặc câu dặn"


def test_vat_sac_nhon_y_te_luon_chuyen_nguoi() -> None:
    """Kim tiêm là rác y tế lây nhiễm — hệ thống không bao giờ được tự hướng dẫn."""
    rule = safety.check_hard_block("bơm kim tiêm đã qua sử dụng")
    assert rule is not None
    assert rule.code == "vat_sac_nhon_y_te"


def test_binh_gas_luon_chuyen_nguoi() -> None:
    rule = safety.check_hard_block("bình gas mini du lịch hết gas")
    assert rule is not None
    assert rule.code == "binh_gas"


def test_hoa_chat_luon_chuyen_nguoi() -> None:
    rule = safety.check_hard_block("thuốc trừ sâu còn nửa chai")
    assert rule is not None
    assert rule.code == "hoa_chat"


def test_so_khop_khong_phu_thuoc_chu_hoa_dau_tieng_viet() -> None:
    """Từ khoá viết không dấu, so với đầu vào đã chuẩn hoá — cả hai phía đều bắt được."""
    assert safety.check_hard_block("KIM TIÊM") is not None
    assert safety.check_hard_block("Kim Tiêm cũ") is not None
    assert safety.check_hard_block("bom tiem") is not None
    assert safety.check_hard_block("thuoc tru sau") is not None
    assert safety.check_hard_block("ống tiêm") is not None


def test_so_khop_tren_ca_ten_model_doan_va_cau_nguoi_dung() -> None:
    """Chặn cứng chạy trên tổ hợp tên model đoán ra + câu hỏi gốc."""
    assert safety.check_hard_block("ống tiêm", "món này vứt đi đâu") is not None
    assert safety.check_hard_block("chai nhựa", "có phải hoá chất không?") is not None
    assert safety.check_hard_block("hộp sữa", "bỏ thùng nào?") is None


def test_mon_rac_lanh_khong_bi_chan_cung() -> None:
    """Rác tái chế bình thường không được dính vào danh sách chặn cứng."""
    assert safety.check_hard_block("hộp sữa giấy tráng nhôm") is None
    assert safety.check_hard_block("ly trà sữa có màng nhựa") is None
    assert safety.check_hard_block("lon bia") is None


def test_chan_cung_voi_dau_vao_rong_thi_khong_co_luat() -> None:
    assert safety.check_hard_block() is None
    assert safety.check_hard_block("") is None
    assert safety.check_hard_block("   ", "") is None


# --- Ngưỡng confidence theo nhóm -----------------------------------------


def test_nhom_khong_khai_bao_thi_lay_nguong_mac_dinh() -> None:
    """Nhóm không tồn tại / chưa khai báo → dùng `default_min_confidence`."""
    assert safety.min_confidence_for(None) == pytest.approx(0.60)


def test_nhom_thuong_dung_nguong_khai_cua_rieng_no(db_session: Session) -> None:
    thuong = classifier._category_by_code(db_session, "other")
    assert safety.min_confidence_for(thuong) == pytest.approx(0.55)


def test_nhom_nguy_hai_dung_nguong_cao_hon_nhom_thuong(db_session: Session) -> None:
    hazardous = classifier._category_by_code(db_session, "hazardous")
    thuong = classifier._category_by_code(db_session, "recyclable_plastic")
    assert safety.min_confidence_for(hazardous) == pytest.approx(0.80)
    assert safety.min_confidence_for(hazardous) > safety.min_confidence_for(thuong)


def test_nguy_hai_bi_ha_nguong_trong_quan_tri_van_bi_keo_len() -> None:
    """Dù ai đó sửa nhầm `min_confidence` của nhóm nguy hại xuống 0.5 trong màn
    quản trị, hệ thống vẫn không cho thấp hơn `hazardous_min_confidence`."""
    category = WasteCategory(code="nguy_hai_gia", name="Nguy hại giả", is_hazardous=True, min_confidence=0.5)
    assert safety.min_confidence_for(category) == pytest.approx(0.80)


# --- Mức hiển thị độ tin cậy ----------------------------------------------


def test_ba_muc_do_tin_cay_theo_nguong() -> None:
    assert safety.confidence_level(0.79, 0.80) == "duoi_nguong"
    assert safety.confidence_level(0.80, 0.80) == "kha_chac"
    assert safety.confidence_level(0.94, 0.80) == "kha_chac"
    assert safety.confidence_level(0.96, 0.80) == "chac_chan"


# NGHI NGO: `0.80 + 0.15` trong số chấm động bằng 0.95000000000000006661, lớn hơn
# literal `0.95` (0.94999999999999995559) đúng một ulp. Hệ quả: confidence đúng
# bằng 0.95 với ngưỡng 0.80 vẫn bị xếp `kha_chac` thay vì `chac_chan`, dù docstring
# của `confidence_level` nói "lớn hơn hoặc bằng ngưỡng + 0.15". Đây là hành vi hiện
# tại của code — test ghi nhận nó, không sửa `safety.py`.
def test_confidence_dung_bang_nguong_cong_015_bi_loat_so_cham_dong() -> None:
    assert safety.confidence_level(0.95, 0.80) == "kha_chac"
    assert safety.confidence_level(0.96, 0.80) == "chac_chan"


def test_ca_bien_confidence_0_va_1() -> None:
    assert safety.confidence_level(0.0, 0.60) == "duoi_nguong"
    assert safety.confidence_level(1.0, 0.60) == "chac_chan"


def test_nguong_bang_1_thi_confidence_1_khong_duoc_tinh_chac_chan() -> None:
    """`chac_chan` cần ≥ ngưỡng + 0.15 — với ngưỡng 1.0 thì 1.0 chỉ đạt `kha_chac`."""
    assert safety.confidence_level(1.0, 1.0) == "kha_chac"
    assert safety.confidence_level(0.99, 1.0) == "duoi_nguong"


# --- Dưới ngưỡng → từ chối, không đoán bừa -------------------------------


def test_duoi_nguong_nhom_thuong_thi_tu_choi_chu_khong_chot_nhan(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cả T1 lẫn T2 đều dưới ngưỡng → `refused`, không trả về nhãn đoán bừa."""
    _dung_model_gia(
        monkeypatch,
        make_result(item_name="Vỏ bánh", category_code="other", confidence=0.40),
        make_result(item_name="Vỏ bánh", category_code="other", confidence=0.45),
    )

    outcome = classify_waste(db_session, image_bytes=b"anh", image_phash="1111000022229999")

    assert outcome.refused is True
    assert outcome.category is None, "Từ chối mà vẫn chốt nhãn là mâu thuẫn"
    assert outcome.confidence_level == "duoi_nguong"
    assert outcome.refusal_reason == RefusalReason.DUOI_NGUONG


def test_duoi_nguong_nhom_nguy_hai_thi_ly_do_la_nghi_nguy_hai(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nhóm nguy hại dưới ngưỡng dùng lý do riêng, nghiêm khắc hơn nhóm thường."""
    _dung_model_gia(
        monkeypatch,
        make_result(item_name="Cục pin", category_code="hazardous", confidence=0.70),
        make_result(item_name="Cục pin", category_code="hazardous", confidence=0.75),
    )

    outcome = classify_waste(db_session, image_bytes=b"anh", image_phash="2222111133338888")

    assert outcome.refused is True
    assert outcome.refusal_reason == RefusalReason.NGHI_NGUY_HAI


def test_vua_duoi_nguong_thi_phai_tu_choi(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Biên dưới: 0.54 < 0.55 của nhóm `other` → phải từ chối, không nới nhẹ."""
    _dung_model_gia(
        monkeypatch,
        make_result(item_name="Vỏ bánh", category_code="other", confidence=0.54),
        make_result(item_name="Vỏ bánh", category_code="other", confidence=0.54),
    )

    outcome = classify_waste(db_session, image_bytes=b"anh", image_phash="4444333322221111")

    assert outcome.refused is True
    assert outcome.refusal_reason == RefusalReason.DUOI_NGUONG


def test_vua_tren_nguong_thi_khong_tu_choi(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Biên trên: confidence đúng bằng ngưỡng thì vẫn trả lời bình thường."""
    _dung_model_gia(monkeypatch, make_result(item_name="Vỏ bánh", category_code="other", confidence=0.55))

    outcome = classify_waste(db_session, image_bytes=b"anh", image_phash="3333222211118888")

    assert outcome.refused is False
    assert outcome.category is not None and outcome.category.code == "other"


def test_chan_cung_qua_cau_hoi_thi_tu_choi_ngay_khong_goi_model(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chặn cứng đứng trước mọi lệnh gọi model — thấy `kim tiêm` là chặn ngay."""
    fake = _dung_model_gia(monkeypatch)

    outcome = classify_waste(db_session, text_query="mình có kim tiêm cũ muốn vứt")

    assert outcome.refused is True
    assert outcome.refusal_reason == RefusalReason.CHAN_CUNG
    assert fake.calls == [], "Chặn cứng phải chặn TRƯỚC khi tốn tiền gọi model"


# --- Lý do từ chối từ danh sách cố định ----------------------------------


def test_moi_ly_do_tu_choi_deu_co_nhan_tieng_viet() -> None:
    """Thêm lý do mới vào `RefusalReason` mà quên nhãn là mất dữ liệu cho PLO 7."""
    for reason in RefusalReason:
        nhan = safety.REFUSAL_LABELS_VI.get(str(reason))
        assert nhan, f"Lý do {reason!r} thiếu nhãn tiếng Việt"
        assert nhan.strip()


def test_nhan_tu_choi_khong_chua_chuoi_tu_do() -> None:
    """`REFUSAL_LABELS_VI` không được chứa khoá lạ ngoài danh sách cố định."""
    hop_le = {str(reason) for reason in RefusalReason}
    assert set(safety.REFUSAL_LABELS_VI) == hop_le


def test_ly_do_tu_choi_trong_ket_qua_luon_thuoc_danh_sach_co_dinh(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dung_model_gia(
        monkeypatch,
        make_result(item_name="Bóng đèn huỳnh quang", category_code="hazardous", confidence=0.50),
        make_result(item_name="Bóng đèn huỳnh quang", category_code="hazardous", confidence=0.55),
    )

    outcome = classify_waste(db_session, image_bytes=b"anh", image_phash="5555444433332222")

    assert outcome.refused is True
    assert outcome.refusal_reason in {str(r) for r in RefusalReason}
    assert outcome.refusal_label_vi == safety.REFUSAL_LABELS_VI[outcome.refusal_reason]


# --- Leo tầng T1 → T2 ----------------------------------------------------


def test_nghi_nguy_hai_thi_leo_len_t2_du_confidence_cao() -> None:
    """Điều kiện escalate mà đa số nhóm bỏ sót — CLAUDE.md mục 4."""
    reason = safety.should_escalate_to_t2(confidence=0.99, min_confidence=0.60, suspect_hazardous=True)
    assert reason.startswith("Nghi rác nguy hại")


def test_chat_luong_anh_kem_thi_leo_len_t2_du_confidence_cao() -> None:
    reason = safety.should_escalate_to_t2(
        confidence=0.95,
        min_confidence=0.60,
        suspect_hazardous=False,
        quality_issue=RefusalReason.NHIEU_VAT.value,
    )
    assert "nhiều món" in reason


def test_model_khong_liet_ke_mon_nao_thi_leo_len_t2() -> None:
    """`items` rỗng với ảnh là model không tuân thủ prompt — tự nó là lý do leo tầng."""
    reason = safety.should_escalate_to_t2(confidence=0.93, min_confidence=0.60, suspect_hazardous=False, items=[])
    assert reason


def test_hoi_bang_chu_thi_items_rong_khong_leo_tang() -> None:
    """Hỏi bằng chữ thì `items` rỗng là bình thường — không leo tầng chỉ vì điều đó."""
    assert (
        safety.should_escalate_to_t2(
            confidence=0.90, min_confidence=0.60, suspect_hazardous=False, items=[], co_anh=False
        )
        == ""
    )


def test_confidence_duoi_nguong_thi_leo_len_t2() -> None:
    items = [{"name": "Hộp sữa", "category_code": "recyclable_paper", "confidence": 0.9}]
    reason = safety.should_escalate_to_t2(
        confidence=0.41, min_confidence=0.60, suspect_hazardous=False, items=items
    )
    assert "dưới ngưỡng" in reason


def test_confidence_tren_nguong_va_moi_dieu_kien_qua_thi_khong_leo() -> None:
    items = [{"name": "Hộp sữa", "category_code": "recyclable_paper", "confidence": 0.9}]
    assert (
        safety.should_escalate_to_t2(confidence=0.90, min_confidence=0.60, suspect_hazardous=False, items=items)
        == ""
    )


def test_nghi_nguy_hai_uu_tien_hon_moi_dieu_kien_khac() -> None:
    reason = safety.should_escalate_to_t2(
        confidence=0.99,
        min_confidence=0.60,
        suspect_hazardous=True,
        quality_issue=RefusalReason.NHIEU_VAT.value,
        items=[],
    )
    assert reason.startswith("Nghi rác nguy hại")


# --- Nhiều món rác -------------------------------------------------------


def test_ma_nhom_trong_items_lay_duoc_cac_ma_hop_le() -> None:
    items = [
        {"name": "Chai nhựa", "category_code": "  recyclable_plastic  "},
        {"name": "Pin AA", "category_code": "hazardous"},
        {"name": "Vật không rõ", "category_code": ""},
        {"name": "Không khai mã"},
    ]
    assert safety.ma_nhom_trong_items(items) == {"recyclable_plastic", "hazardous"}


def test_ma_nhom_trong_items_voi_items_rong() -> None:
    assert safety.ma_nhom_trong_items([]) == set()


def test_mot_nhom_thi_khong_bi_coi_la_nhieu() -> None:
    items = [
        {"name": "Chai nhựa", "category_code": "recyclable_plastic"},
        {"name": "Nắp chai", "category_code": "recyclable_plastic"},
    ]
    assert safety.nhieu_nhom_khac_nhau(items, {"hazardous"}) is False


def test_nhieu_nhom_khong_ro_danh_muc_thi_giu_hanh_vi_chet() -> None:
    """`ma_nguy_hai=None` (không tra được danh mục) → không được đoán là an toàn."""
    items = [
        {"name": "Chai nhựa", "category_code": "recyclable_plastic"},
        {"name": "Bình thuỷ tinh", "category_code": "recyclable_glass"},
    ]
    assert safety.nhieu_nhom_khac_nhau(items, None) is True


def test_nhieu_nhom_khong_nguy_hai_thi_van_tra_loi() -> None:
    """Bản vá 03/08: nhựa + giấy + thuỷ tinh không nguy hiểm — cứ trả lời theo món chủ đạo."""
    items = [
        {"name": "Chai nhựa", "category_code": "recyclable_plastic"},
        {"name": "Bình thuỷ tinh", "category_code": "recyclable_glass"},
    ]
    assert safety.nhieu_nhom_khac_nhau(items, {"hazardous"}) is False


def test_nhieu_nhom_co_nguy_hai_lan_thi_phai_tu_choi() -> None:
    """Phần an toàn của bản vá 03/08: pin lẫn chai nhựa → từ chối bất kể confidence."""
    items = [
        {"name": "Chai nhựa", "category_code": "recyclable_plastic"},
        {"name": "Pin AA", "category_code": "hazardous"},
    ]
    assert safety.nhieu_nhom_khac_nhau(items, {"hazardous"}) is True


def test_nhieu_nhom_voi_items_rong_thi_khong_ket_luan() -> None:
    assert safety.nhieu_nhom_khac_nhau([], {"hazardous"}) is False


# --- Cảnh báo an toàn ----------------------------------------------------


def test_nhom_nguy_hai_tra_ve_canh_bao_co_dinh_tu_csdl(db_session: Session) -> None:
    """Cảnh báo lấy nguyên văn từ CSDL — không bao giờ để LLM sinh phần này."""
    hazardous = classifier._category_by_code(db_session, "hazardous")
    warning = safety.safety_warning_for(hazardous)
    assert warning
    assert "KHÔNG bỏ vào thùng rác thường" in warning


def test_nhom_thuong_va_khong_co_nhom_thi_khong_co_canh_bao(db_session: Session) -> None:
    assert safety.safety_warning_for(None) == ""
    assert safety.safety_warning_for(classifier._category_by_code(db_session, "organic")) == ""


# ─── Tests for IoT safety / HITL rules (spec §11) ────────────────────────────


def test_confident_ordinary_waste_is_ok():
    outcome = safety.evaluate("plastic", 0.94)
    assert outcome.status == "ok"
    assert outcome.label == "plastic"
    assert outcome.requires_review is False


def test_low_confidence_becomes_warning_and_needs_review():
    outcome = safety.evaluate("plastic", 0.21)
    assert outcome.status == "warning"
    assert outcome.requires_review is True
    # The label is still reported, but the status makes the uncertainty explicit.
    assert outcome.confidence == pytest.approx(0.21)


def test_hazard_label_beats_low_confidence():
    """A possible battery at low confidence is a hazard, not a shrug."""
    outcome = safety.evaluate("battery", 0.35)
    assert outcome.status == "hazard"
    assert outcome.requires_review is True


@pytest.mark.parametrize("label", ["battery", "chemical", "medical", "sharps", "e-waste"])
def test_all_configured_hazard_labels(label):
    assert safety.evaluate(label, 0.99).status == "hazard"


def test_label_matching_is_case_insensitive():
    assert safety.evaluate("BATTERY", 0.9).status == "hazard"
    assert safety.evaluate("  Plastic  ", 0.9).label == "plastic"


@pytest.mark.parametrize("label", ["", "   ", None])
def test_empty_label_is_refused_not_guessed(label):
    outcome = safety.evaluate(label, 0.9)
    assert outcome.status == "refused"
    assert outcome.label == ""
    assert outcome.requires_review is True


def test_errored_never_looks_like_a_classification():
    outcome = safety.errored("provider exploded")
    assert outcome.status == "error"
    assert outcome.label == ""
    assert outcome.confidence == 0.0


def test_threshold_boundary_is_inclusive_on_ok_side(monkeypatch):
    monkeypatch.setenv("LOW_CONFIDENCE_THRESHOLD", "0.6")
    get_settings.cache_clear()
    assert safety.evaluate("paper", 0.6).status == "ok"
    assert safety.evaluate("paper", 0.599).status == "warning"
