"""Chín test bắt buộc cho hai chỉ số bám nguồn mới (gói P86).

Không gọi model thật — toàn bộ dùng chuỗi dựng sẵn, chạy lại bao nhiêu lần
cũng ra cùng kết quả và không tốn tiền.

Bối cảnh: chỉ số ``groundedness`` cũ so cụm "Điều XX" trong câu trả lời với
trường ``ground_truth_context`` của từng ca, mà trường đó CHỈ chứa nội dung
điều luật, KHÔNG chứa số hiệu (0/28 ca) — nên chatbot trích ĐÚNG điều luật vẫn
bị chấm trượt. Hai chỉ số mới tách làm hai: ``khong_bia_dieu_luat`` (so với kho
tri thức thật) và ``bam_noi_dung_nguon`` (so nội dung, bỏ số hiệu).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from eval.metrics import (
    NGUONG_BAM_NOI_DUNG,
    TU_DUNG_TIENG_VIET,
    kiem_tra_khong_bia_dieu_luat,
    ti_le_bam_noi_dung_nguon,
)
from eval.run_chatbot_eval import gom_dieu_luat_co_that

_DUONG_DAN_DATASET = Path(__file__).resolve().parents[2] / "eval" / "chatbot_golden_dataset.json"

# Đoạn nguồn dựng sẵn lấy theo nội dung chunk "Điều 26.1" trong kho tri thức
# (src/db/seed_data.py::KNOWLEDGE_DOCS) — dùng chung cho các test bám nội dung.
_DOAN_NGUON = (
    "Phạt tiền từ 500.000 đồng đến 1.000.000 đồng đối với hành vi hộ gia đình, "
    "cá nhân không phân loại chất thải rắn sinh hoạt theo quy định; "
    "không sử dụng bao bì chứa chất thải rắn sinh hoạt đúng quy chuẩn."
)

# Tập số hiệu có thật thu gọn của kho tri thức, dạng đã chuẩn hoá như
# gom_dieu_luat_co_that() trả về (chữ thường).
_DIEU_CO_THAT = {"điều 26", "điều 29", "điều 75", "điều 79"}


def test_khong_nhac_dieu_luat_thi_bo_qua():
    """Câu trả lời không nhắc điều luật nào → trả None, không tính vào tử số."""
    ket_qua = kiem_tra_khong_bia_dieu_luat(
        "Mình chưa tìm thấy quy định phù hợp với câu hỏi này trong kho tài liệu.",
        _DIEU_CO_THAT,
    )
    assert ket_qua is None


def test_trich_dieu_luat_co_that_thi_dat():
    """Trích số hiệu có thật trong kho tri thức → ĐẠT (không quan trọng hoa/thường)."""
    ket_qua = kiem_tra_khong_bia_dieu_luat(
        "Hộ gia đình không phân loại rác bị phạt theo Điều 26 Nghị định 45/2022/NĐ-CP.",
        {"Điều 26", "Điều 29"},
    )
    assert ket_qua == (True, [])


def test_trich_dieu_luat_bia_thi_truot():
    """Trích số hiệu KHÔNG có trong kho tri thức → TRƯỢT."""
    ket_qua = kiem_tra_khong_bia_dieu_luat(
        "Hành vi này bị phạt theo Điều 100 Luật Bảo vệ môi trường 2020.",
        _DIEU_CO_THAT,
    )
    assert ket_qua == (False, ["Điều 100"])


def test_bao_ten_so_hieu_bia_ra_ngoai():
    """Kết quả phải NÊU ĐÚNG số hiệu bịa; số hiệu trích đúng không bị liệt oan."""
    ket_qua = kiem_tra_khong_bia_dieu_luat(
        "Việc lưu giữ riêng rác nguy hại được quy định tại Điều 29, còn mức phí "
        "thu gom tính theo Điều 123 Nghị định 45/2022/NĐ-CP.",
        _DIEU_CO_THAT,
    )
    assert ket_qua is not None
    dat, cac_so_hieu_bia = ket_qua
    assert dat is False
    assert cac_so_hieu_bia == ["Điều 123"]


def test_bam_noi_dung_cau_tra_loi_sat_nguon_thi_dat():
    """Câu trả lời diễn đạt lại sát đoạn nguồn → tỉ lệ >= ngưỡng → ĐẠT."""
    cau_tra_loi = (
        "Mình xin thông báo: hộ gia đình, cá nhân không phân loại chất thải rắn "
        "sinh hoạt theo quy định sẽ bị phạt tiền từ 500.000 đồng đến "
        "1.000.000 đồng, và bao bì chứa rác phải dùng đúng quy chuẩn."
    )
    ti_le = ti_le_bam_noi_dung_nguon(_DOAN_NGUON, cau_tra_loi)
    assert ti_le >= NGUONG_BAM_NOI_DUNG


def test_bam_noi_dung_cau_tra_loi_lac_de_thi_truot():
    """Câu trả lời nói chuyện khác hẳn đoạn nguồn → tỉ lệ dưới ngưỡng → TRƯỢT."""
    cau_tra_loi = (
        "Trời hôm nay nắng đẹp quá, cuối tuần bạn hãy đi dã ngoại cùng gia đình nhé!"
    )
    ti_le = ti_le_bam_noi_dung_nguon(_DOAN_NGUON, cau_tra_loi)
    assert ti_le < NGUONG_BAM_NOI_DUNG


def test_tu_dung_khong_lam_diem_ao():
    """Câu trả lời chỉ toàn từ dừng → không được cộng điểm ảo, phải TRƯỢT."""
    cau_tra_loi = " ".join(sorted(TU_DUNG_TIENG_VIET))
    ti_le = ti_le_bam_noi_dung_nguon(_DOAN_NGUON, cau_tra_loi)
    assert ti_le < NGUONG_BAM_NOI_DUNG


def test_do_hai_lan_ra_cung_ket_qua():
    """Phép đo tất định: chạy hai lần trên cùng dữ liệu ra hệt cùng một số."""
    cau_tra_loi = (
        "Pin tiểu, ắc quy và bóng đèn huỳnh quang là rác nguy hại, phải để riêng "
        "và mang xuống điểm thu gom ở hầm B1 theo Điều 29."
    )
    lan_1_bia = kiem_tra_khong_bia_dieu_luat(cau_tra_loi, _DIEU_CO_THAT)
    lan_2_bia = kiem_tra_khong_bia_dieu_luat(cau_tra_loi, _DIEU_CO_THAT)
    assert lan_1_bia == lan_2_bia

    lan_1_bam = ti_le_bam_noi_dung_nguon(_DOAN_NGUON, cau_tra_loi)
    lan_2_bam = ti_le_bam_noi_dung_nguon(_DOAN_NGUON, cau_tra_loi)
    assert lan_1_bam == lan_2_bam


def test_ca_cu_trich_dung_dieu_luat_khong_con_bi_truot():
    """Chứng minh lỗi cũ đã chết: trích ĐÚNG điều luật có thật phải ĐẠT.

    Ca QA-08 thật trong bộ dữ liệu vàng có ``ground_truth_context`` KHÔNG chứa
    bất kỳ cụm "Điều XX" nào — dưới chỉ số cũ, câu trả lời trích "Điều 75"
    (có thật trong kho tri thức) vẫn bị chấm trượt. Với cách đo mới, đối chiếu
    với kho tri thức thật nên câu trả lời đó ĐẠT.
    """
    items = json.loads(_DUONG_DAN_DATASET.read_text(encoding="utf-8"))
    qa08 = next(i for i in items if i["id"] == "QA-08")

    # Tiền đề của lỗi cũ: context của ca KHÔNG chứa số hiệu điều luật nào.
    assert re.search(r"Điều\s+\d+", qa08["ground_truth_context"]) is None

    # Câu trả lời trích đúng một số hiệu có thật trong kho tri thức sản phẩm.
    dieu_co_that = gom_dieu_luat_co_that()
    cau_tra_loi = (
        "Ban quản lý có quyền từ chối tiếp nhận chất thải nếu cư dân không phân "
        "loại đúng quy định, theo Điều 75 Luật Bảo vệ môi trường 2020."
    )
    ket_qua = kiem_tra_khong_bia_dieu_luat(cau_tra_loi, dieu_co_that)
    assert "điều 75" in dieu_co_that  # số hiệu trích đúng là số hiệu có thật
    assert ket_qua == (True, [])
