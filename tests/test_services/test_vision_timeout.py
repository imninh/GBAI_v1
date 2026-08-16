"""fast-fail timeout cho lệnh gọi model (gói P43a) — không test nào gọi mạng thật.

Trace production 13/08 (Run #150): T1 llama-90b TREO hết 60s rồi mới rơi xuống T2
— nút thắt là timeout hardcode 60s. Gói hạ xuống config 15s. Ba chỗ đáng ngờ thật:
đọc nhầm biến (viết thành vision_max_output_tokens), sót một trong hai chỗ
`httpx.Client`, và hạ quá thấp cắt luôn T2 reasoning.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from src.config import get_settings, reset_settings_cache

GOC_DU_AN = Path(__file__).resolve().parents[2]
OPENAI_COMPAT = GOC_DU_AN / "src" / "services" / "vision" / "openai_compat.py"


@pytest.fixture(autouse=True)
def _don_trang_thai() -> Iterator[None]:
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_config_co_vision_timeout_mac_dinh_15() -> None:
    assert get_settings().vision_timeout_seconds == 15.0


def test_timeout_doc_tu_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISION_TIMEOUT_SECONDS", "8")
    reset_settings_cache()
    try:
        assert get_settings().vision_timeout_seconds == 8.0
    finally:
        monkeypatch.delenv("VISION_TIMEOUT_SECONDS", raising=False)
        reset_settings_cache()


def test_khong_con_hang_so_cu() -> None:
    noi_dung = OPENAI_COMPAT.read_text(encoding="utf-8")
    assert "_TIMEOUT_SECONDS" not in noi_dung, (
        "Còn tham chiếu _TIMEOUT_SECONDS trong openai_compat.py — sẽ NameError lúc chạy"
    )


def test_httpx_client_dung_config() -> None:
    noi_dung = OPENAI_COMPAT.read_text(encoding="utf-8")
    so_lan = noi_dung.count("get_settings().vision_timeout_seconds")
    assert so_lan >= 2, (
        f"get_settings().vision_timeout_seconds phải xuất hiện ở CẢ HAI chỗ "
        f"(embed + _post), đang thấy {so_lan} lần — sót một chỗ là đường đó vẫn treo 60s"
    )
