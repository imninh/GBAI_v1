"""Groq đăng ký được như một nhà cung cấp tương thích OpenAI."""

from __future__ import annotations

from src.config import (
    OPENAI_COMPATIBLE_BASE_URLS,
    PROVIDER_DEFAULT_EMBEDDING_MODELS,
    PROVIDER_DEFAULT_MODELS,
    Settings,
)
from src.services.vision import build_client_for


def test_groq_co_diem_cuoi() -> None:
    assert OPENAI_COMPATIBLE_BASE_URLS["groq"] == "https://api.groq.com/openai/v1"


def test_groq_co_model_mac_dinh_cho_ba_tang() -> None:
    t1, t2, text = PROVIDER_DEFAULT_MODELS["groq"]
    assert t1 == "qwen/qwen3.6-27b"
    assert t2 == "qwen/qwen3.6-27b"
    assert text == "openai/gpt-oss-120b"


def test_groq_khong_co_model_embedding() -> None:
    """Groq không sinh vector — để trống thì RAG tự lui về BM25 thuần."""
    assert PROVIDER_DEFAULT_EMBEDDING_MODELS["groq"] == ""


def test_key_va_base_url_tra_ve_dung() -> None:
    settings = Settings(groq_api_key="gsk_test", vision_provider="groq")
    assert settings.api_key_for("groq") == "gsk_test"
    assert settings.base_url_for("groq") == "https://api.groq.com/openai/v1"


def test_dung_duoc_client_cho_groq() -> None:
    """Không cần lớp client mới: Groq đi chung đường OpenAI-compatible."""
    client = build_client_for("groq")
    assert client.provider_name == "groq"
