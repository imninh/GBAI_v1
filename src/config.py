from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # Vision / classification
    # "openai" | "stub". "stub" returns a canned label without calling any model —
    # local testing only, never production. See services/vision.py.
    vision_provider: str = "openai"
    vision_model_name: str = "gpt-4o-mini"
    # Any OpenAI-compatible endpoint. Empty means OpenAI itself. Set this to use
    # a different vendor's compatibility layer (Google AI Studio, OpenRouter,
    # Groq, a local server) without changing any code — the wire format is the
    # same, only the host and the model name differ.
    vision_base_url: str = ""
    stub_vision_label: str = "plastic"
    stub_vision_confidence: float = Field(default=0.91, ge=0.0, le=1.0)
    low_confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    hazard_labels: str = "battery,chemical,medical,sharps,e-waste,paint,aerosol"

    # IoT devices — "device_id:key" pairs, comma separated. Never commit real keys.
    iot_device_keys: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
