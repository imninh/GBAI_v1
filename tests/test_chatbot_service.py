"""Unit tests mới cho Chatbot Service — gói P66.

Không dùng lại tests/test_chatbot.py (gói khác đang giữ).
"""

from __future__ import annotations

import logging
import re
from unittest.mock import MagicMock, patch

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import PROVIDER_DEFAULT_MODELS, reset_settings_cache
from src.db.models import KnowledgeChunk, KnowledgeDoc, WasteCategory
from src.db.seed_data import WASTE_CATEGORIES
from src.services.chatbot import (
    _STRONG_LAW_SIGNALS,
    _compute_confidence,
    _contains_distance_pattern,
    _strip_xml_tags,
    ask_chatbot,
    classify_intent_rule,
    get_llm_client_for_chatbot,
)
from src.services.chatbot_tools import ViableBinInfo, format_bins_for_llm_context

# --- 1. get_llm_client_for_chatbot — không ném lỗi, trả provider hợp lệ ---

class TestGetLlmClientForChatbot:
    """§9.1 & §9.2: Provider trả về hợp lệ ở cả hai trường hợp có/không Mistral key."""

    def test_returns_three_values_with_valid_provider(self, monkeypatch, caplog):
        """Khi MISTRAL_API_KEY rỗng → fallback sang text tier, trả (client, model, provider)."""
        monkeypatch.setenv("MISTRAL_API_KEY", "")
        monkeypatch.setenv("VISION_PROVIDER_TEXT", "nvidia")
        reset_settings_cache()
        try:
            client, model, provider = get_llm_client_for_chatbot()
            assert client is not None
            assert isinstance(model, str) and len(model) > 0
            assert isinstance(provider, str) and len(provider) > 0
            assert provider in PROVIDER_DEFAULT_MODELS or provider == "local_only"
        finally:
            reset_settings_cache()

    def test_mistral_key_present_builds_mistral_client(self, monkeypatch, caplog):
        """Khi MISTRAL_API_KEY có giá trị mà build_client_for("mistral") thất bại → log warning."""
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key-fake")
        monkeypatch.setenv("VISION_PROVIDER_TEXT", "nvidia")
        reset_settings_cache()
        try:
            # build_client_for("mistral") sẽ gọi build_openai_compatible_client
            # mà không có key thật → có thể ném lỗi. Kiểm tra log.warning được ghi.
            with caplog.at_level(logging.WARNING, logger="src.services.chatbot"):
                try:
                    client, model, provider = get_llm_client_for_chatbot()
                    # Nếu không ném → provider phải là "mistral"
                    assert provider == "mistral"
                except Exception:
                    # Nếu build_client_for("mistral") ném → phải có log warning
                    assert any("MISTRAL_API_KEY" in r.message or "Mistral" in r.message for r in caplog.records), \
                        "Phải ghi log warning khi Mistral fail"
        finally:
            reset_settings_cache()

    def test_provider_matches_actual_usage(self, monkeypatch):
        """generated_by phải khớp với provider trả về, không guess bằng model name."""
        monkeypatch.setenv("MISTRAL_API_KEY", "")
        monkeypatch.setenv("VISION_PROVIDER_TEXT", "nvidia")
        reset_settings_cache()
        try:
            _, _, provider = get_llm_client_for_chatbot()
            assert provider == "nvidia"
        finally:
            reset_settings_cache()


# --- 2. classify_intent_rule — luật mạnh luôn thắng (§6) ---

class TestClassifyIntentRule:
    """§9.3: 6 câu — 3 luật+lump thùng → waste_law, 3 thuần thùng → bin_query."""

    def test_law_plus_bin_keywords_must_be_waste_law(self):
        """Câu vừa có từ khoá luật mạnh vừa có từ khoá thùng → phải là waste_law."""
        assert classify_intent_rule("Vứt rác bừa bãi bị phạt bao nhiêu?") == "waste_law"
        assert classify_intent_rule("Thùng rác không đúng quy định bị xử phạt thế nào?") == "waste_law"
        assert classify_intent_rule("Bỏ rác không đúng nơi quy định bị phạt bao nhiêu tiền?") == "waste_law"

    def test_pure_bin_keywords_must_be_bin_query(self):
        """Câu thuần thùng rác, không có dấu hiệu luật → bin_query."""
        assert classify_intent_rule("Thùng rác gần đây còn chỗ không?") == "bin_query"
        assert classify_intent_rule("Bỏ chai nhựa ở đâu?") == "bin_query"
        assert classify_intent_rule("Tìm thùng rác tái chế gần nhất?") == "bin_query"

    def test_qa03_and_qa14_correct_intent(self):
        """QA-03 và QA-14 trong golden set phải về đúng ý định sau khi sửa."""
        assert classify_intent_rule(
            "Vứt rác bừa bãi tại hành lang hoặc nơi công cộng chung cư bị phạt bao nhiêu?"
        ) == "waste_law"
        assert classify_intent_rule(
            "Rác cồng kềnh có kích thước như thế nào thì bắt buộc đăng ký trước với ban quản lý?"
        ) == "waste_law"

    def test_strong_signals_covered(self):
        """Mọi từ trong _STRONG_LAW_SIGNALS đều được kiểm tra."""
        for sig in _STRONG_LAW_SIGNALS:
            assert classify_intent_rule(f"Bị {sig} bao nhiêu?") == "waste_law"


# --- 3. handle_bin_query — không truyền lat/lng → không bịa khoảng cách (§5) ---

class TestHandleBinQueryNoGps:
    """§9.4: handle_bin_query không truyền lat/lng → answer không chứa mẫu khoảng cách."""

    def test_no_gps_no_distance_pattern(self, db_session: Session):
        """Không có GPS → answer không khớp \\d+ m\\b và không chứa 'gần nhất'."""
        from src.services.chatbot import handle_bin_query

        # Tạo mock bins
        mock_bins = [
            ViableBinInfo(
                id=1, code="BIN-01", name="Thùng A", address="123 Test St",
                category_codes=["recyclable"], category_names=["Tái chế"],
                fill_percent=50.0, battery_percent=90.0,
                status="binh_thuong", status_label_vi="Hoạt động tốt",
                is_viable=True, distance_meters=None,
            ),
        ]

        with patch("src.services.chatbot.query_viable_bins", return_value=mock_bins):
            with patch("src.services.chatbot.get_llm_client_for_chatbot") as mock_get:
                fake_client = MagicMock()
                fake_client.generate_text.return_value = (
                    "Thùng rác gần bạn nhất là Thùng A, cách bạn 50m.",
                    MagicMock(tokens_in=100, tokens_out=50, cost_usd=0.001),
                )
                mock_get.return_value = (fake_client, "test-model", "fake")

                resp = handle_bin_query(db_session, "Thùng rác gần đây?", user_lat=None, user_lng=None)

                # Lớp bảo hiểm phải cắt bỏ câu trả lời chứa khoảng cách
                assert not re.search(r"\d+\s*m\b", resp.answer), \
                    f"Answer không được chứa mẫu mét: {resp.answer}"
                assert "gần nhất" not in resp.answer.lower(), \
                    f"Answer không được chứa 'gần nhất': {resp.answer}"
                assert "cách bạn" not in resp.answer.lower(), \
                    f"Answer không được chứa 'cách bạn': {resp.answer}"

    def test_no_gps_confidence_lower(self, db_session: Session):
        """Không có GPS → confidence_score phải thấp hơn có GPS."""
        from src.services.chatbot import handle_bin_query

        mock_bins = [
            ViableBinInfo(
                id=1, code="BIN-01", name="Thùng A", address="123 Test St",
                category_codes=["recyclable"], category_names=["Tái chế"],
                fill_percent=50.0, battery_percent=90.0,
                status="binh_thuong", status_label_vi="Hoạt động tốt",
                is_viable=True, distance_meters=None,
            ),
        ]

        with patch("src.services.chatbot.query_viable_bins", return_value=mock_bins):
            with patch("src.services.chatbot.get_llm_client_for_chatbot") as mock_get:
                fake_client = MagicMock()
                fake_client.generate_text.return_value = (
                    "Thùng rác khả dụng: Thùng A.",
                    MagicMock(tokens_in=100, tokens_out=50, cost_usd=0.001),
                )
                mock_get.return_value = (fake_client, "test-model", "fake")

                resp = handle_bin_query(db_session, "Thùng rác?", user_lat=None, user_lng=None)
                assert resp.confidence_level == "Low"
                assert resp.confidence_score <= 0.5


# --- 4. Lọc thẻ XML (§7.1) ---

class TestStripXmlTags:
    """§9.5: Lớp lọc thẻ XML — đưa vào chuỗi có <retrieved_context> → đầu ra sạch."""

    def test_removes_retrieved_context_tag(self):
        text = "Có thông tin trong <retrieved_context> nội dung </retrieved_context> bạn nhé."
        result = _strip_xml_tags(text)
        assert "<retrieved_context>" not in result
        assert "nội dung" in result

    def test_removes_multiple_tags(self):
        text = "<bin_data>- Thùng A</bin_data> <user_question>Hỏi</user_question>"
        result = _strip_xml_tags(text)
        assert "<bin_data>" not in result
        assert "</bin_data>" not in result
        assert "<user_question>" not in result

    def test_no_change_without_tags(self):
        text = "Đây là câu trả lời bình thường không có thẻ XML."
        assert _strip_xml_tags(text) == text


# --- 5. Confidence score tính từ điểm truy hồi (§7.3) ---

class TestComputeConfidence:
    """§9.6: confidence_score đổi theo điểm truy hồi — hai ca cho hai giá trị khác nhau."""

    def test_high_score_gives_high_confidence(self):
        level, score = _compute_confidence(0.85)
        assert level == "High"
        assert score == 0.85

    def test_low_score_gives_low_confidence(self):
        level, score = _compute_confidence(0.20)
        assert level == "Low"
        assert score == 0.20

    def test_medium_score(self):
        level, score = _compute_confidence(0.55)
        assert level == "Medium"
        assert score == 0.55

    def test_clamping(self):
        _, score = _compute_confidence(1.5)
        assert score == 1.0
        _, score = _compute_confidence(-0.5)
        assert score == 0.0


# --- 6. format_bins_for_llm_context — không có GPS ẩn khoảng cách ---

class TestFormatBinsNoGps:
    """§5.2: Không có GPS → khoảng cách không xuất hiện trong context."""

    def test_no_distance_when_no_gps(self):
        bins = [
            ViableBinInfo(
                id=1, code="BIN-01", name="Thùng A", address="123 St",
                category_codes=["recyclable"], category_names=["Tái chế"],
                fill_percent=50.0, distance_meters=123.4,
            ),
        ]
        result = format_bins_for_llm_context(bins, has_gps=False)
        assert "123m" not in result
        assert "Khoảng cách" not in result

    def test_distance_shown_when_gps(self):
        bins = [
            ViableBinInfo(
                id=1, code="BIN-01", name="Thùng A", address="123 St",
                category_codes=["recyclable"], category_names=["Tái chế"],
                fill_percent=50.0, distance_meters=123.4,
            ),
        ]
        result = format_bins_for_llm_context(bins, has_gps=True)
        assert "123m" in result


# --- 7. _contains_distance_pattern ---

class TestContainsDistancePattern:
    """Kiểm tra regex mẫu khoảng cách."""

    def test_matches_meter_pattern(self):
        assert _contains_distance_pattern("Thùng cách bạn 50m") is True
        assert _contains_distance_pattern("Khoảng 120m") is True

    def test_matches_km_pattern(self):
        assert _contains_distance_pattern("Cách 1.5km") is True

    def test_matches_vietnamese_phrases(self):
        assert _contains_distance_pattern("Thùng gần nhất là A") is True
        assert _contains_distance_pattern("Cách bạn 100m") is True

    def test_no_match_clean_text(self):
        assert _contains_distance_pattern("Thùng rác khả dụng: A") is False


# --- 8. Test đi qua ask_chatbot() — chống tái phát lỗi provider (P68) ---

class _FakeClient:
    """Client giả trả về chuỗi biết trước, ghi nhận provider để test đối chiếu."""

    def __init__(self, text: str):
        self._text = text

    def generate_text(self, prompt: str, model: str, max_tokens: int | None = None):
        from src.services.vision import Usage

        return self._text, Usage(tokens_in=10, tokens_out=20, cost_usd=0.001)


class TestAskChatbotRealPath:
    """§7: Gọi ask_chatbot() — đường sản phẩm thật, không phải handler trực tiếp.

    Lỗi P68: provider không được gán khi client truyền từ ask_chatbot → mọi câu
    hỏi trả về mẫu (fallback_level=2, generated_by="template").
    """

    def _seed_law_knowledge(self, session: Session) -> None:
        for row in WASTE_CATEGORIES:
            if session.scalar(select(WasteCategory).where(WasteCategory.code == row["code"])) is None:
                session.add(WasteCategory(**row))
        session.flush()
        doc = KnowledgeDoc(
            title="Nghị định 45/2022/NĐ-CP",
            source="Nghị định 45/2022/NĐ-CP",
            doc_type="law",
            effective_date=None,
        )
        session.add(doc)
        session.flush()
        session.add(
            KnowledgeChunk(
                doc_id=doc.id,
                content="Phạt tiền từ 500.000 đồng đến 1.000.000 đồng đối với hành vi không phân loại rác.",
                section="Điều 26.1 — Mức phạt không phân loại rác tại nguồn",
                meta={"needs_verification": False},
            )
        )
        session.commit()

    def _seed_app_guide_knowledge(self, session: Session) -> None:
        doc = KnowledgeDoc(
            title="App Guide", source="x", doc_type="app_guide", effective_date=None
        )
        session.add(doc)
        session.flush()
        session.add(
            KnowledgeChunk(
                doc_id=doc.id,
                content="Mở tab Phân loại để chụp ảnh.",
                section="Cách Phân loại Rác",
                meta={"needs_verification": False},
            )
        )
        session.commit()

    def test_waste_law_uses_model_not_template(self, db_session: Session, monkeypatch):
        """Đường thật waste_law: fallback_level=1, generated_by=provider giả."""
        self._seed_law_knowledge(db_session)
        fake = _FakeClient("KHONG_PHAN_LOAI_PHAT_500_000_DEN_1_000_000")
        monkeypatch.setattr(
            "src.services.chatbot.get_llm_client_for_chatbot",
            lambda: (fake, "fake-model", "mistral"),
        )
        resp = ask_chatbot(db_session, "không phân loại rác bị phạt bao nhiêu tiền?")
        assert resp.intent == "waste_law"
        assert resp.fallback_level == 1, f"fallback_level phải là 1, got {resp.fallback_level}"
        assert resp.generated_by == "mistral", f"generated_by phải là 'mistral', got {resp.generated_by}"
        assert "KHONG_PHAN_LOAI_PHAT_500_000_DEN_1_000_000" in resp.answer

    def test_bin_query_uses_model_not_template(self, db_session: Session, monkeypatch):
        """Đường thật bin_query: fallback_level=1, generated_by=provider giả."""
        mock_bins = [
            ViableBinInfo(
                id=1, code="BIN-01", name="Thùng A", address="123 Test St",
                category_codes=["recyclable"], category_names=["Tái chế"],
                fill_percent=50.0, battery_percent=90.0,
                status="binh_thuong", status_label_vi="Hoạt động tốt",
                is_viable=True, distance_meters=None,
            ),
        ]
        fake = _FakeClient("THUNG_GAN_NHAT_LA_THUNG_A")
        monkeypatch.setattr(
            "src.services.chatbot.get_llm_client_for_chatbot",
            lambda: (fake, "fake-model", "nvidia"),
        )
        with patch("src.services.chatbot.query_viable_bins", return_value=mock_bins):
            resp = ask_chatbot(db_session, "thùng rác tái chế gần đây còn chỗ không?")
        assert resp.intent == "bin_query"
        assert resp.fallback_level == 1, f"fallback_level phải là 1, got {resp.fallback_level}"
        assert resp.generated_by == "nvidia", f"generated_by phải là 'nvidia', got {resp.generated_by}"
        assert "THUNG_GAN_NHAT_LA_THUNG_A" in resp.answer

    def test_app_guide_uses_model_not_template(self, db_session: Session, monkeypatch):
        """Đường thật app_guide: fallback_level=1, generated_by=provider giả."""
        self._seed_app_guide_knowledge(db_session)
        fake = _FakeClient("MO_TAB_PHAN_LOAI_DE_CHUP_ANH")
        monkeypatch.setattr(
            "src.services.chatbot.get_llm_client_for_chatbot",
            lambda: (fake, "fake-model", "mistral"),
        )
        resp = ask_chatbot(db_session, "cách dùng app để phân loại rác bằng ảnh?")
        assert resp.intent == "app_guide"
        assert resp.fallback_level == 1, f"fallback_level phải là 1, got {resp.fallback_level}"
        assert resp.generated_by == "mistral", f"generated_by phải là 'mistral', got {resp.generated_by}"
        assert "MO_TAB_PHAN_LOAI_DE_CHUP_ANH" in resp.answer

    def test_generated_by_changes_with_provider(self, db_session: Session, monkeypatch):
        """generated_by phải khớp provider giả (mistral vs nvidia)."""
        self._seed_law_knowledge(db_session)
        fake_m = _FakeClient("ANSWER_MISTRAL")
        monkeypatch.setattr(
            "src.services.chatbot.get_llm_client_for_chatbot",
            lambda: (fake_m, "fake-model", "mistral"),
        )
        resp_m = ask_chatbot(db_session, "phạt bao nhiêu tiền?")
        assert resp_m.generated_by == "mistral"

        fake_n = _FakeClient("ANSWER_NVIDIA")
        monkeypatch.setattr(
            "src.services.chatbot.get_llm_client_for_chatbot",
            lambda: (fake_n, "fake-model", "nvidia"),
        )
        resp_n = ask_chatbot(db_session, "phạt bao nhiêu tiền?")
        assert resp_n.generated_by == "nvidia"


class TestMistralModelSelection:
    """§7.4: model cho Mistral không được lấy từ model của nvidia khi VISION_PROVIDER_TEXT=nvidia."""

    def test_mistral_model_not_from_nvidia(self, monkeypatch):
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key-fake")
        monkeypatch.setenv("VISION_PROVIDER_TEXT", "nvidia")
        reset_settings_cache()
        fake_client = MagicMock()
        monkeypatch.setattr("src.services.chatbot.build_client_for", lambda p: fake_client)
        try:
            _, model, provider = get_llm_client_for_chatbot()
            assert provider == "mistral"
            # model KHÔNG được là model nvidia (meta/llama-3.1-8b-instruct)
            assert "llama" not in model.lower(), f"model không được là model nvidia: {model}"
            assert "mistral" in model.lower(), f"model phải là mistral: {model}"
        finally:
            reset_settings_cache()
