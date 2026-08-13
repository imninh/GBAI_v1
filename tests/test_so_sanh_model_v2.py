"""Nối Mistral + đo model vision Mistral/Groq (gói P41) — không test nào gọi model thật.

Gói này KHÔNG gài lỗi cố ý (khai rõ trong đặc tả). Test chốt ba chỗ đáng ngờ
thật: key Mistral nạp được không, `% leo T2` đếm trên tier cuối cùng, và qwen
(reasoning) phải khai `max_output_tokens` để `<think>` không nuốt trần.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from eval import so_sanh_model
from eval.metrics import KetQuaAnh
from src.config import PROVIDER_DEFAULT_MODELS, get_settings, reset_settings_cache


@pytest.fixture(autouse=True)
def _don_trang_thai() -> Iterator[None]:
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_mistral_duoc_noi() -> None:
    """`base_url_for("mistral")` khác rỗng, và `PROVIDER_DEFAULT_MODELS` có khoá mistral đủ 3 phần tử."""
    assert get_settings().base_url_for("mistral") == "https://api.mistral.ai/v1"
    cac_model = PROVIDER_DEFAULT_MODELS.get("mistral")
    assert cac_model is not None, "PROVIDER_DEFAULT_MODELS thiếu khoá 'mistral'"
    assert len(cac_model) == 3, "Mistral phải khai đủ (T1, T2, text)"


def test_cau_hinh_co_ung_vien_moi() -> None:
    """`CAC_CAU_HINH` có ít nhất một cấu hình mistral và một cấu hình groq khác qwen."""
    cac_provider = {cf["provider"] for cf in so_sanh_model.CAC_CAU_HINH}
    assert "mistral" in cac_provider, "Phải có ứng viên mistral trong danh sách đo"
    groq_khac_qwen = [
        cf for cf in so_sanh_model.CAC_CAU_HINH if cf["provider"] == "groq" and "qwen" not in str(cf["model"])
    ]
    assert groq_khac_qwen, "Phải có ứng viên groq khác qwen (Llama 4)"


def test_qwen_co_max_output_tokens() -> None:
    """Cấu hình qwen phải khai `max_output_tokens >= 4000` — chống `<think>` nuốt trần rồi VISION-500."""
    qwen = [cf for cf in so_sanh_model.CAC_CAU_HINH if "qwen" in str(cf["model"])]
    assert qwen, "Không tìm thấy cấu hình qwen"
    for cf in qwen:
        trần = int(cf.get("max_output_tokens", 0))
        assert trần >= 4000, f"Cấu hình {cf['ten']} phải khai max_output_tokens >= 4000, đang là {trần}"


def test_bang_co_cot_leo_t2(capsys: pytest.CaptureFixture) -> None:
    """`in_bang` in ra cột `% leo T2` và `p50` — dữ liệu giả, không gọi model."""
    dong_gia = {
        "ten": "gia",
        "provider": "mistral",
        "model": "pixtral",
        "tong": None,
        "token_vao": 0,
        "token_ra": 0,
        "so_loi": 0,
        "ty_le_leo_t2": 0.5,
        "loi": "",
    }
    so_sanh_model.in_bang([dong_gia])
    in_ra = capsys.readouterr().out
    assert "% leo T2" in in_ra, "Bảng phải có cột % leo T2"
    assert "p50" in in_ra, "Bảng phải có cột p50"


def test_ti_le_leo_t2_tinh_dung() -> None:
    """4 ảnh giả: 2 cái `t2_full`, 2 cái `t1_mini` → tỉ lệ leo T2 = 50%."""
    cac_kq = [
        KetQuaAnh(duong_dan="a", bo="cong_khai", nhan_dung="organic", tier="t2_full"),
        KetQuaAnh(duong_dan="b", bo="cong_khai", nhan_dung="organic", tier="t2_full"),
        KetQuaAnh(duong_dan="c", bo="cong_khai", nhan_dung="organic", tier="t1_mini"),
        KetQuaAnh(duong_dan="d", bo="cong_khai", nhan_dung="organic", tier="t1_mini"),
    ]
    assert so_sanh_model._ty_le_leo_t2(cac_kq) == pytest.approx(0.5)


def test_liet_ke_khong_goi_model(db_session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    """`--liet-ke` in đủ 6 cấu hình và KHÔNG gọi model lần nào."""
    dem = [0]

    @contextmanager
    def _phien_gia(*args, **kwargs) -> Iterator:
        yield db_session

    monkeypatch.setattr(so_sanh_model, "session_scope", _phien_gia)

    def _cam_goi_model(*args, **kwargs):
        dem[0] += 1
        raise AssertionError("--liet-ke không được gọi model")

    monkeypatch.setattr(so_sanh_model, "classify_waste", _cam_goi_model)

    ma_thoat = so_sanh_model.main(["--liet-ke"])
    in_ra = capsys.readouterr().out

    assert ma_thoat == 0, "Phải có ảnh trong data/eval để liệt kê"
    assert dem[0] == 0, "--liet-ke không được gọi model"
    assert len(so_sanh_model.CAC_CAU_HINH) == 6, "Phải có đủ 6 cấu hình"
    for cf in so_sanh_model.CAC_CAU_HINH:
        assert cf["ten"] in in_ra, f"Thiếu cấu hình {cf['ten']} trong danh sách in ra"
