"""So sánh lần chạy eval — test trên dict dựng tay, không I/O, không gọi model."""

from __future__ import annotations

import json

import pytest

from eval.so_sanh_lan_chay import doc_lan_chay, doi_ket_qua, nhan_lan_chay, so_sanh


def _anh(
    duong_dan: str, nhan_dung: str, nhan_du_doan: str, *, tu_choi: bool = False, loi: str = "", model: str = ""
) -> dict:
    return {
        "duong_dan": duong_dan,
        "bo": "cong_khai",
        "nhan_dung": nhan_dung,
        "nhan_du_doan": nhan_du_doan,
        "tu_choi": tu_choi,
        "loi": loi,
        "model": model,
    }


def _lan_chay(tong: dict, cac_anh: list[dict]) -> dict:
    return {
        "chay_luc": "2026-08-08T00:00:00+00:00",
        "nhan": ["plastic"],
        "tong_hop": {"cong_khai": tong},
        "tung_anh": cac_anh,
    }


def _tong(*, du_gia: bool = True, so_anh: int = 1) -> dict:
    return {
        "so_anh": so_anh,
        "ty_le_tra_loi": 1.0,
        "accuracy_khi_tra_loi": 1.0,
        "accuracy_toan_bo": 1.0,
        "macro_f1": 1.0,
        "recall_nguy_hai": 0.0,
        "latency_p50_ms": 100,
        "latency_p95_ms": 200,
        "tong_chi_phi_usd": 0.0,
        "du_gia": du_gia,
    }


def test_nhan_lan_chay_lay_model_xuat_hien_nhieu_nhat() -> None:
    lan = _lan_chay(
        _tong(),
        [
            _anh("a.jpg", "plastic", "plastic", model="llama-3.2-90b"),
            _anh("b.jpg", "plastic", "plastic", model="gpt-4o"),
            _anh("c.jpg", "plastic", "plastic", model="llama-3.2-90b"),
            _anh("d.jpg", "plastic", "plastic", model=""),
        ],
    )
    assert nhan_lan_chay(lan) == "llama-3.2-90b"


def test_nhan_lan_chay_khong_ro_khi_moi_model_de_rong() -> None:
    lan = _lan_chay(
        _tong(), [_anh("a.jpg", "plastic", "plastic", model=""), _anh("b.jpg", "plastic", "plastic", model="  ")]
    )
    assert nhan_lan_chay(lan) == "(không rõ model)"


def test_so_sanh_in_ca_ten_model_va_con_so_accuracy() -> None:
    lan_a = _lan_chay(_tong(), [_anh("a.jpg", "plastic", "plastic", model="gpt-4o")])
    tong_b = _tong()
    tong_b["accuracy_khi_tra_loi"] = 0.5
    tong_b["accuracy_toan_bo"] = 0.25
    lan_b = _lan_chay(tong_b, [_anh("b.jpg", "plastic", "plastic", model="llama-3.2-90b")])

    bang = so_sanh([lan_a, lan_b])
    assert "gpt-4o" in bang
    assert "llama-3.2-90b" in bang
    assert "100.0%" in bang  # accuracy khi trả lời của lần A
    assert "50.0%" in bang  # accuracy khi trả lời của lần B
    assert "25.0%" in bang  # accuracy toàn bộ của lần B


def test_so_sanh_in_chua_co_gia_khi_du_gia_false() -> None:
    lan = _lan_chay(_tong(du_gia=False), [_anh("a.jpg", "plastic", "plastic", model="x")])
    bang = so_sanh([lan, lan])
    assert "chưa có giá" in bang
    assert "$0" not in bang


def test_doi_ket_qua_dem_dung_anh_bi_lat() -> None:
    lan_a = _lan_chay(
        _tong(),
        [
            _anh("1.jpg", "plastic", "paper"),  # A sai → B đúng: tốt lên
            _anh("2.jpg", "plastic", "plastic"),  # A đúng → B sai: xấu đi
            _anh("3.jpg", "plastic", "plastic"),  # chỉ có ở A: bỏ qua
        ],
    )
    lan_b = _lan_chay(
        _tong(),
        [
            _anh("1.jpg", "plastic", "plastic"),
            _anh("2.jpg", "plastic", "paper"),
            _anh("4.jpg", "plastic", "plastic"),  # chỉ có ở B: bỏ qua
        ],
    )

    tot_len, xau_di = doi_ket_qua(lan_a, lan_b)
    assert [anh["duong_dan"] for anh in tot_len] == ["1.jpg"]
    assert [anh["duong_dan"] for anh in xau_di] == ["2.jpg"]
    assert len(tot_len) + len(xau_di) == 2


def test_doc_lan_chay_tu_choi_file_khong_co_tong_hop(tmp_path) -> None:
    tep = tmp_path / "sai.json"
    tep.write_text(json.dumps({"abc": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="tong_hop"):
        doc_lan_chay(tep)


def test_nhan_lan_chay_uutien_cau_hinh_ghi_san() -> None:
    """Có khối cau_hinh thì lấy model T1 ghi sẵn, không đếm tên trong tung_anh."""
    lan = _lan_chay(_tong(), [_anh("a.jpg", "plastic", "plastic", model="gemini-flash-lite-latest")])
    lan["cau_hinh"] = {"tang": {"t1": {"provider": "groq", "model": "qwen/qwen3.6-27b"}}}
    assert nhan_lan_chay(lan) == "groq/qwen/qwen3.6-27b"
