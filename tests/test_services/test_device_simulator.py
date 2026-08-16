"""Bộ mô phỏng thùng dùng khoá riêng từng thùng và không chết vì timeout (gói P9).

Test các hàm thuần của ``scripts/device_simulator`` — không gọi mạng thật:

* ``khoa_cho_thung`` chọn đúng khoá theo luật của endpoint ingest: thùng đã cấp
  khoá riêng thì dùng khoá riêng, thùng chưa cấp thì rơi về khoá chung;
* ``doc_bang_khoa`` đọc bảng khoá {mã thùng: khoá} từ file JSON, file hỏng thì
  thoát chứ không chạy tiếp với bảng rỗng;
* ``_gui_reading`` nuốt ``TimeoutError`` thành một câu báo tiếng Việt thay vì
  làm vỡ cả phiên mô phỏng.
"""

from __future__ import annotations

import pytest

from scripts.device_simulator import _gui_reading, doc_bang_khoa, khoa_cho_thung


def test_thung_co_khoa_rieng_thi_dung_khoa_rieng() -> None:
    assert khoa_cho_thung({"BIN-01": "rieng"}, "BIN-01", "chung") == "rieng"


def test_thung_chua_co_khoa_rieng_thi_rot_ve_khoa_chung() -> None:
    assert khoa_cho_thung({"BIN-01": "rieng"}, "BIN-09", "chung") == "chung"


def test_khong_co_khoa_nao_thi_tra_ve_rong() -> None:
    assert khoa_cho_thung({}, "BIN-01", "") == ""


def test_doc_bang_khoa_tu_file_json(tmp_path) -> None:
    file_khoa = tmp_path / "khoa.json"
    file_khoa.write_text('{"BIN-01": "khoa-1", "BIN-02": "khoa-2"}', encoding="utf-8")

    bang_khoa = doc_bang_khoa(str(file_khoa))

    assert bang_khoa == {"BIN-01": "khoa-1", "BIN-02": "khoa-2"}


def test_file_khoa_hong_thi_thoat_chu_khong_chay_tiep(tmp_path) -> None:
    file_khoa = tmp_path / "hong.json"
    file_khoa.write_text("{ khong-phai-json", encoding="utf-8")

    with pytest.raises(SystemExit):
        doc_bang_khoa(str(file_khoa))


def test_qua_han_khong_lam_vo_phien(monkeypatch: pytest.MonkeyPatch) -> None:
    def _qua_han(*args, **kwargs) -> None:
        raise TimeoutError("quá hạn lúc đọc")

    monkeypatch.setattr("urllib.request.urlopen", _qua_han)

    ket_qua = _gui_reading("http://localhost:8000", "BIN-01", "khoa", 50.0, 70.0)

    assert isinstance(ket_qua, str)
    assert "Quá hạn" in ket_qua
