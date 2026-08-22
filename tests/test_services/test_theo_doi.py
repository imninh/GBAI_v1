"""Test tầng theo dõi Langfuse và lá chắn quyền riêng tư (P89)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.config import get_settings, reset_settings_cache
from src.services.chatbot import ChatbotResponse, ask_chatbot
from src.services.theo_doi import TheoDoiAI, che_du_lieu


@pytest.fixture(autouse=True)
def _clean_settings():
    """Tự động xoá cache settings trước và sau mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_mac_dinh_tat(monkeypatch):
    """1. Không đặt gì -> lớp theo dõi ở trạng thái tắt."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    reset_settings_cache()
    td = TheoDoiAI()
    assert td.enabled is False


def test_thieu_khoa_thi_tat_du_bat_co(monkeypatch, caplog):
    """2. Bật cờ nhưng thiếu khoá -> vẫn tắt, và ghi log warning."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    reset_settings_cache()
    with caplog.at_level(logging.WARNING):
        td = TheoDoiAI()
    assert td.enabled is False
    assert any("thiếu LANGFUSE_PUBLIC_KEY" in record.message for record in caplog.records)


def test_doc_dung_bien_base_url(monkeypatch):
    """3. Đặt LANGFUSE_BASE_URL -> cấu hình đọc đúng giá trị đó, không rơi về mặc định."""
    custom_url = "https://custom-langfuse.example.com"
    monkeypatch.setenv("LANGFUSE_BASE_URL", custom_url)
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    reset_settings_cache()
    settings = get_settings()
    assert settings.langfuse_base_url == custom_url

    with patch("src.services.theo_doi.Langfuse") as mock_langfuse:
        td = TheoDoiAI()
        assert td.enabled is True
        mock_langfuse.assert_called_once_with(
            public_key="pk-lf-test",
            secret_key="sk-lf-test",
            host=custom_url,
        )


def test_che_so_dien_thoai():
    """4. Che số điện thoại dạng 0xxxxxxxxx thành [SDT]."""
    text = "Số của tôi là 0901000001 vui lòng gọi."
    assert che_du_lieu(text) == "Số của tôi là [SDT] vui lòng gọi."


def test_che_so_dien_thoai_co_dau_cach():
    """5. Che số điện thoại có dấu cách 0xxx xxx xxx thành [SDT]."""
    text = "Liên hệ 0901 000 001 ngay."
    assert che_du_lieu(text) == "Liên hệ [SDT] ngay."


def test_che_so_dien_thoai_quoc_te():
    """6. Che số điện thoại quốc tế +84901000001 thành [SDT]."""
    text = "SĐT: +84901000001"
    assert che_du_lieu(text) == "SĐT: [SDT]"


def test_che_email():
    """7. Che email thành [EMAIL]."""
    text = "Gửi thư về ninh@example.com để biết thêm chi tiết."
    assert che_du_lieu(text) == "Gửi thư về [EMAIL] để biết thêm chi tiết."


def test_che_toa_do():
    """8. Che cặp toạ độ 21.0285, 105.8542 thành [TOA_DO]."""
    text = "Vị trí rác ở 21.0285, 105.8542 gần hồ."
    assert che_du_lieu(text) == "Vị trí rác ở [TOA_DO] gần hồ."


def test_che_ten_that_cua_nguoi_dung():
    """9. Che đúng tên người dùng truyền vào (ten_nguoi) thành [TEN]."""
    text = "Tôi tên là Trần Văn Ninh, muốn hỏi thủ tục."
    res = che_du_lieu(text, ten_nguoi="Trần Văn Ninh")
    assert "[TEN]" in res
    assert "Trần Văn Ninh" not in res


def test_che_ten_khong_phan_biet_hoa_thuong():
    """10. Che tên người dùng không phân biệt hoa thường."""
    text = "Chào bạn trần văn ninh nhé."
    res = che_du_lieu(text, ten_nguoi="Trần Văn Ninh")
    assert "[TEN]" in res
    assert "trần văn ninh" not in res


def test_khong_che_nham_so_hieu_dieu_luat():
    """11. Không che nhầm Điều 79, Nghị định 45, 500.000 đồng, 31/12/2024."""
    text = "Theo Điều 79 Nghị định 45, phạt 500.000 đồng từ ngày 31/12/2024."
    res = che_du_lieu(text, ten_nguoi="Trần Văn Ninh")
    assert "Điều 79" in res
    assert "Nghị định 45" in res
    assert "500.000 đồng" in res
    assert "31/12/2024" in res


def test_langfuse_hong_khong_lam_hong_cau_tra_loi(monkeypatch):
    """12. Giả lập lớp theo dõi ném lỗi -> ask_chatbot vẫn trả lời bình thường."""
    mock_session = MagicMock(spec=Session)

    def _mock_trace_crash(*args, **kwargs):
        raise RuntimeError("Langfuse trace execution crashed!")

    monkeypatch.setattr("src.services.theo_doi.TheoDoiAI.trace_chatbot", _mock_trace_crash)
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    reset_settings_cache()

    with patch("src.services.chatbot._chay_chatbot") as mock_chay:
        mock_chay.return_value = ChatbotResponse(
            answer="Phạt từ 500.000 đến 1.000.000 đồng.",
            intent="waste_law",
        )
        resp = ask_chatbot(mock_session, "Không phân loại rác bị phạt bao nhiêu?")
        assert resp.answer == "Phạt từ 500.000 đến 1.000.000 đồng."


def test_khong_nuot_loi_im_lang():
    """13. Quét mã nguồn theo_doi.py: không có except Exception: pass; mọi except rộng phải kèm warning."""
    file_path = Path("src/services/theo_doi.py")
    lines = file_path.read_text(encoding="utf-8").splitlines()

    for idx, line in enumerate(lines):
        # Bỏ qua docstring
        if line.strip().startswith("- Cấm") or line.strip().startswith('"""'):
            continue
        if re.search(r"except\s+Exception\s*:", line):
            # Dòng kế tiếp không được là pass
            next_line = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
            assert next_line != "pass", f"Dòng {idx + 2} chứa pass sau except Exception"
            # Phải có logger.warning hoặc gán cờ ngắt
            block = "\n".join(lines[idx : idx + 4])
            assert "logger.warning" in block or "_CO_LANGFUSE = False" in block
