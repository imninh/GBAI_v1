"""Test tầng theo dõi Langfuse và lá chắn quyền riêng tư (P89)."""

from __future__ import annotations

import copy
import logging
import re
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.config import get_settings, reset_settings_cache
from src.services.chatbot import ChatbotResponse, ask_chatbot
from src.services.classifier import classify_waste
from src.services.classifier_types import ClassifyOutcome, NodeMetric
from src.services.theo_doi import (
    TheoDoiAI,
    che_du_lieu,
    ghi_trace_chatbot,
    ghi_trace_phan_loai,
)


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


# --- Trace phân loại rác (P98) -------------------------------------------------


class _CapObs:
    """Observation giả ghi lại mọi kwarg để test soi payload gửi đi."""

    def __init__(self, name, **kw):
        self.name = name
        self.kw = kw
        self.children = []

    def start_observation(self, **kw):
        name = kw.pop("name", "?")
        child = _CapObs(name, **kw)
        self.children.append(child)
        return child

    def end(self):
        return self

    def score_trace(self, **kw):
        return self


class _CapClient:
    def __init__(self, **kw):
        self.init_kwargs = kw
        self.traces = []
        self.flushed = False
        self.propagated = None

    def propagate_attributes(self, **kw):
        self.propagated = kw

    def start_observation(self, **kw):
        name = kw.pop("name", "trace")
        t = _CapObs(name, **kw)
        self.traces.append(t)
        return t

    def flush(self):
        self.flushed = True


def _enable_langfuse(monkeypatch, client_cls):
    """Bật Langfuse thật sự (với client giả) và ép tạo lại singleton."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://jp.cloud.langfuse.com")
    reset_settings_cache()
    monkeypatch.setattr("src.services.theo_doi.Langfuse", client_cls)
    # Singleton đã tạo từ test trước (tắt) phải bị ép tạo lại.
    monkeypatch.setattr("src.services.theo_doi._theo_doi", None)


def _dump(client: _CapClient) -> str:
    parts = []
    for t in client.traces:
        parts.append(str(t.kw))
        for c in t.children:
            parts.append(str(c.kw))
    return "\n".join(parts)


def test_phan_loai_tat_khong_tao_client(monkeypatch):
    """1. Langfuse tắt -> ghi_trace_phan_loai không ném, không tạo client."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    reset_settings_cache()
    monkeypatch.setattr("src.services.theo_doi._theo_doi", None)
    fake = MagicMock()
    monkeypatch.setattr("src.services.theo_doi.Langfuse", fake)
    out = ClassifyOutcome(item_name="x")
    ghi_trace_phan_loai(outcome=out, bat_dau=0.0)  # phải không ném
    fake.assert_not_called()


def test_phan_loai_client_hong_khong_nem(monkeypatch, caplog):
    """2. Langfuse bật, client ném giữa chừng -> không ném ra ngoài, có warning."""

    class _Boom:
        def __init__(self, **kw):
            self.kw = kw

        def start_observation(self, **kw):
            raise RuntimeError("mid crash")

        def flush(self):
            pass

    _enable_langfuse(monkeypatch, _Boom)
    out = ClassifyOutcome(item_name="chai", confidence=0.9)
    with caplog.at_level(logging.WARNING):
        ghi_trace_phan_loai(outcome=out, bat_dau=0.0, text_query="chai nhựa")
    assert any("trace phân loại" in r.message for r in caplog.records)


def test_phan_loai_khong_ro_anh(monkeypatch):
    """3. Ảnh không bao giờ rò: classifier truyền image_bytes nhưng trace chỉ nhận phash."""
    client = _CapClient()
    _enable_langfuse(monkeypatch, lambda **kw: client)
    fixed = ClassifyOutcome(item_name="chai", confidence=0.9)
    monkeypatch.setattr(
        "src.services.classifier._classify_waste",
        lambda *a, **k: copy.deepcopy(fixed),
    )
    sentinel = b"LEAKME_RAW_BYTES_XYZ"
    classify_waste(MagicMock(), image_bytes=sentinel, image_phash="phashABC")
    dump = _dump(client)
    assert "phashABC" in dump  # pHash được ghi
    assert "LEAKME_RAW_BYTES_XYZ" not in dump  # ảnh gốc tuyệt đối không lọt ra


def test_phan_loai_che_du_lieu(monkeypatch):
    """4. Số điện thoại trong text_query phải bị che trước khi gửi."""
    client = _CapClient()
    _enable_langfuse(monkeypatch, lambda **kw: client)
    out = ClassifyOutcome(item_name="x")
    ghi_trace_phan_loai(
        outcome=out, bat_dau=0.0, text_query="Số của tôi là 0901000001 vui lòng gọi"
    )
    dump = _dump(client)
    assert "0901000001" not in dump
    assert "[SDT]" in dump


def test_phan_loai_moi_node_la_mot_span(monkeypatch):
    """5. Mỗi NodeMetric -> đúng một span con, đúng tên."""
    client = _CapClient()
    _enable_langfuse(monkeypatch, lambda **kw: client)
    out = ClassifyOutcome()
    out.nodes = [
        NodeMetric(node="safety_precheck"),
        NodeMetric(node="cache_lookup"),
        NodeMetric(node="t1_mini"),
    ]
    ghi_trace_phan_loai(outcome=out, bat_dau=0.0)
    assert len(client.traces) == 1
    child_names = {c.name for c in client.traces[0].children}
    assert child_names == {"safety_precheck", "cache_lookup", "t1_mini"}


def test_ket_qua_phan_loai_khong_doi_khi_trace_hong(monkeypatch):
    """6. classify_waste trả outcome GIỐNG NHAU dù trace tắt hay trace hỏng."""
    fixed = ClassifyOutcome(
        item_name="Chai nhựa", confidence=0.9, tier="t1_mini", latency_ms=123
    )

    def _core(*a, **k):
        return copy.deepcopy(fixed)

    monkeypatch.setattr("src.services.classifier._classify_waste", _core)
    sess = MagicMock()
    out_off = classify_waste(sess, text_query="chai nhựa")  # Langfuse tắt mặc định

    def _raise(*a, **k):
        raise RuntimeError("trace crash")

    monkeypatch.setattr("src.services.theo_doi.ghi_trace_phan_loai", _raise)
    out_broken = classify_waste(sess, text_query="chai nhựa")
    assert out_off == out_broken


# --- Mới thêm: verify propagate_attributes và flush cho chatbot ---

def _bat_propagate(monkeypatch):
    """Patch hàm module-level propagate_attributes, trả dict ghi lại kwargs."""
    captured = {}

    @contextmanager
    def fake_pa(**kw):
        captured.update(kw)
        yield

    monkeypatch.setattr("src.services.theo_doi.propagate_attributes", fake_pa)
    return captured


def test_phan_loai_propagate_attributes(monkeypatch):
    """7. trace_phan_loai gọi propagate_attributes kèm user_id và 5 tag."""
    client = _CapClient()
    _enable_langfuse(monkeypatch, lambda **kw: client)
    captured = _bat_propagate(monkeypatch)
    out = ClassifyOutcome(
        item_name="chai", confidence=0.9,
        tier="t1_mini", provider="groq", refused=False, suspect_hazardous=False,
    )
    ghi_trace_phan_loai(outcome=out, bat_dau=0.0, text_query="chai nhựa")
    assert captured.get("user_id") == "khach"
    tags = captured.get("tags")
    assert len(tags) == 5
    assert tags[0] == "t1_mini"       # tier
    assert tags[1] == "groq"          # provider
    assert tags[2] == get_settings().app_env
    assert tags[3] == "refused:False"
    assert tags[4] == "suspect_hazardous:False"


def test_phan_loai_user_id_propagate(monkeypatch):
    """8. trace_phan_loai propagate_attributes nhận user_id đúng."""
    client = _CapClient()
    _enable_langfuse(monkeypatch, lambda **kw: client)
    captured = _bat_propagate(monkeypatch)
    out = ClassifyOutcome(item_name="chai", confidence=0.9)
    ghi_trace_phan_loai(outcome=out, bat_dau=0.0, text_query="chai nhựa", user_id="12")
    assert captured.get("user_id") == "12"


def test_chatbot_khong_goi_flush(monkeypatch, caplog):
    """9. trace_chatbot KHÔNG gọi client.flush trong đường phục vụ người dùng."""
    client = _CapClient()
    _enable_langfuse(monkeypatch, lambda **kw: client)
    captured = _bat_propagate(monkeypatch)

    # Giả lập resp có intent + sources để có span truy_hoi
    mock_resp = MagicMock()
    mock_resp.answer = "Cái này rác quá."
    mock_resp.intent = "waste_general"
    mock_resp.sources = []
    mock_resp.generated_by = ""
    mock_resp.usage = None

    with caplog.at_level(logging.WARNING):
        ghi_trace_chatbot(question="Rác gì đó?", resp=mock_resp, bat_dau=0.0)
    # flush KHÔNG bao giờ được gọi
    assert client.flushed is False
    # thuộc tính cấp trace vẫn đi qua propagate_attributes
    assert captured.get("user_id") == "khach"
    assert captured.get("tags") == ["waste_general", get_settings().app_env]


def test_chatbot_luot_luu_loi(monkeypatch, caplog):
    """10. Langfuse SDK ném lỗi -> vẫn nuốt lỗi, chỉ ghi warning."""

    class _Boom:
        def __init__(self, **kw):
            self.kw = kw

        def start_observation(self, **kw):
            raise RuntimeError("observation crash")

        def flush(self):
            pass

    def _boom_pa(**kw):
        raise RuntimeError("propagate crash")

    _enable_langfuse(monkeypatch, _Boom)
    monkeypatch.setattr("src.services.theo_doi.propagate_attributes", _boom_pa)
    with caplog.at_level(logging.WARNING):
        ghi_trace_chatbot(question="test", resp=MagicMock(), bat_dau=0.0)
    assert any("ghi trace chatbot" in r.message.lower() for r in caplog.records)
