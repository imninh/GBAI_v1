"""Test gói P77 — /health phải nói thật (chạm CSDL, không dối).

Hai trạng thái được dựng bằng cách thay engine phía dưới `/health`:
- sống: engine in-memory thật, ``SELECT 1`` thành công;
- chết: engine giả ném lỗi mỗi lần ``.connect()``.
Cả hai đều là truy vấn CSDL thật (không mock kết quả), chỉ khác nguồn engine.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


class _DeadEngine:
    """Engine giả: mở kết nối là ném lỗi ngay — mô phỏng CSDL chết."""

    def connect(self):
        raise SQLAlchemyError("mô phỏng CSDL chết")


def test_health_tra_ve_200_khi_csdl_song(client, monkeypatch) -> None:
    # Engine in-memory thật, SELECT 1 phải thành công.
    engine_song = create_engine("sqlite:///:memory:")
    with engine_song.connect() as conn:
        conn.execute(text("SELECT 1"))

    monkeypatch.setattr("src.main._ENGINE", None)
    monkeypatch.setattr("src.main._lay_engine", lambda: engine_song)

    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["db"] == "ok"
    assert body["status"] == "ok"


def test_health_tra_ve_503_khi_csdl_chet(client, monkeypatch) -> None:
    monkeypatch.setattr("src.main._ENGINE", None)
    monkeypatch.setattr("src.main._lay_engine", lambda: _DeadEngine())

    resp = client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["db"] == "down"
    assert body["status"] == "error"


def test_health_khong_ro_chuoi_ket_noi_khi_chet(client, monkeypatch) -> None:
    monkeypatch.setattr("src.main._ENGINE", None)
    monkeypatch.setattr("src.main._lay_engine", lambda: _DeadEngine())

    resp = client.get("/health")
    body_text = resp.text

    # Không rò: chuỗi kết nối, tên máy chủ, từ "postgresql".
    assert "postgresql" not in body_text
    assert "@" not in body_text  # tránh rò dạng user:pass@host
    assert "sqlite" not in body_text
    assert "SELECT" not in body_text  # không rò nội dung lỗi gốc / câu SQL
