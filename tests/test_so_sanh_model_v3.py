"""Gói P43b — mở khoá Mistral trong `build_client_for` + cột `p95 ms` cho công cụ đo.

P41 nối Mistral vào `config.py`/`eval/so_sanh_model.py` nhưng `build_client_for`
chưa nhận `"mistral"` → `eval/so_sanh_model.py --dong-y` ném `VISION-400` và bảng
ra "LỖI" chứ không ra số. Gói này thêm `"mistral"` vào set (đi qua đúng đường
OpenAI-compatible). Đồng thời thêm cột `p95 ms` vào bảng so sánh — p95 ≈ 60000
tố cáo cấu hình hay timeout, thứ `p50` giấu đi.

Không test nào gọi model/mạng thật. Không sửa `metrics.py`, không sửa
`test_so_sanh_model.py` (P34) hay `test_so_sanh_model_v2.py` (P41).
"""

from __future__ import annotations

import pytest

from eval import so_sanh_model
from eval.metrics import KetQuaAnh


def test_build_client_nhan_mistral() -> None:
    """`build_client_for("mistral")` không ném VISION-400, trả client của Mistral.

    Mistral đi qua đúng đường OpenAI-compatible (base_url đã có từ P41). Key chỉ
    cần lúc GỌI, không cần lúc DỰNG client.
    """
    from src.services.vision import build_client_for

    client = build_client_for("mistral")
    assert getattr(client, "provider_name", None) == "mistral"


def test_build_client_van_chan_ten_bay() -> None:
    """Provider không tồn tại vẫn bị chặn VISION-400 — không nới nhánh chặn."""
    from src.services.vision import VisionUnavailableError, build_client_for

    with pytest.raises(VisionUnavailableError) as loi:
        build_client_for("khong-co-that")
    assert loi.value.code == "VISION-400"


def test_p95_tinh_dung() -> None:
    """`_p95_ms` theo kiểu nearest-rank `ceil(0.95*n) - 1`."""
    cac_ket_qua = [
        KetQuaAnh(duong_dan=f"anh-{i}", bo="cong_khai", nhan_dung="x", latency_ms=100 + i * 100)
        for i in range(20)
    ]
    assert so_sanh_model._p95_ms(cac_ket_qua) == 1900


def test_p95_bat_duoc_duoi_treo() -> None:
    """9 ảnh 200ms + 1 ảnh 60000ms → p95 = 60000 (p50 sẽ là 200).

    Đây là ca cột p95 sinh ra để lộ: p50 nhìn ra 200ms trong sạch, p95 mới thấy
    cấu hình hay treo tới hết timeout rồi mới leo T2.
    """
    cac_ket_qua = [
        KetQuaAnh(duong_dan=f"anh-{i}", bo="cong_khai", nhan_dung="x", latency_ms=200) for i in range(9)
    ]
    cac_ket_qua.append(KetQuaAnh(duong_dan="anh-treo", bo="cong_khai", nhan_dung="x", latency_ms=60000))
    assert so_sanh_model._p95_ms(cac_ket_qua) == 60000


def test_dong_loi_co_khoa_p95(capsys) -> None:
    """`in_bang` chạy được với danh sách có dòng LỖI (kèm `p95_ms`) — không KeyError.

    Dòng LỖI do `chay_luot_do` sinh ra phải mang đủ khoá (trong đó `p95_ms: 0`),
    nếu không `in_bang` đọc `dong["p95_ms"]` là ném KeyError ngay khi có cấu hình
    hỏng — đúng ca hay xảy ra nhất khi so model.
    """
    cac_dong = [
        {
            "ten": "ok-1",
            "provider": "nvidia",
            "model": "m-ok",
            "tong": None,
            "token_vao": 0,
            "token_ra": 0,
            "so_loi": 0,
            "ty_le_leo_t2": 0.0,
            "p95_ms": 0,
            "file": "",
            "loi": "",
        },
        {
            "ten": "hong-2",
            "provider": "groq",
            "model": "m-hong",
            "tong": None,
            "token_vao": 0,
            "token_ra": 0,
            "so_loi": 0,
            "ty_le_leo_t2": 0.0,
            "p95_ms": 0,
            "file": "",
            "loi": "LỖI: RuntimeError: hết quota",
        },
    ]
    so_sanh_model.in_bang(cac_dong)  # không được ném KeyError
    out = capsys.readouterr().out
    assert "hong-2" in out
    assert "p95 ms" in out
