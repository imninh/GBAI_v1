"""Test chuyển database sang Supabase — đường ray an toàn, không cần DB thật.

Bao gồm: ``normalize_database_url`` vẫn sửa ``postgres://`` → ``postgresql://``;
ray ``sslmode`` nối đúng cho URL có/không có query string, bỏ qua sqlite, không
nối hai lần khi đã có; và guard ``--reset`` của seed từ chối khi nhắm vào
database không phải sqlite nếu thiếu ``--toi-chac-chan``.

Toàn bộ test xây URL dưới dạng chuỗi — không kết nối database thật.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.config import reset_settings_cache
from src.db.session import _them_sslmode, normalize_database_url


@pytest.fixture(autouse=True)
def _xoam_cache() -> Iterator[None]:
    reset_settings_cache()
    yield
    reset_settings_cache()


# --- normalize_database_url -----------------------------------------------


def test_normalize_postgres_sang_postgresql() -> None:
    assert normalize_database_url("postgres://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert normalize_database_url("postgresql://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"


def test_normalize_giu_nguyen_sqlite() -> None:
    assert normalize_database_url("sqlite:///./data/app.db") == "sqlite:///./data/app.db"


# --- ray sslmode ------------------------------------------------------------


def test_sslmode_them_vao_url_khong_query() -> None:
    assert _them_sslmode("postgresql://u:p@h:5432/db") == "postgresql://u:p@h:5432/db?sslmode=require"


def test_sslmode_them_vao_url_co_query() -> None:
    assert _them_sslmode("postgresql://u:p@h:5432/db?connect_timeout=5") == (
        "postgresql://u:p@h:5432/db?connect_timeout=5&sslmode=require"
    )


def test_sslmode_khong_dong_cham_sqlite() -> None:
    assert _them_sslmode("sqlite:///./data/app.db") == "sqlite:///./data/app.db"


def test_sslmode_khong_noi_hai_lan() -> None:
    assert _them_sslmode("postgresql://u:p@h:5432/db?sslmode=require") == "postgresql://u:p@h:5432/db?sslmode=require"
    assert _them_sslmode("postgresql://u:p@h:5432/db?sslmode=disable&x=1") == (
        "postgresql://u:p@h:5432/db?sslmode=disable&x=1"
    )


# --- seed --reset với database không phải sqlite -----------------------------


def test_seed_reset_non_sqlite_khong_duoc_khi_thieu_toi_chac_chan() -> None:
    """--reset nhắm vào Supabase mà không có --toi-chac-chan phải từ chối."""
    import scripts.seed as seed

    assert seed._cho_phep_reset("postgresql://user:pass@db.example:5432/greenbin?sslmode=require", False) is False


def test_seed_reset_non_sqlite_thieu_bien_moi_truong_van_tu_choi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Có --toi-chac-chan nhưng thiếu ``CHO_PHEP_XOA_DB`` thì vẫn từ chối.

    Lớp chốt thứ hai, thêm sau ngày 16/08/2026 — CSDL đang chạy mất 600 tài
    khoản cư dân và toàn bộ bảng ``media``. Một cờ dòng lệnh gõ nhầm không được
    phép xoá cả cơ sở dữ liệu thật.
    """
    import scripts.seed as seed

    monkeypatch.delenv("CHO_PHEP_XOA_DB", raising=False)
    assert seed._cho_phep_reset("postgresql://user:pass@db.example:5432/greenbin?sslmode=require", True) is False


def test_seed_reset_non_sqlite_duoc_khi_du_hai_lop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Đủ CẢ ``--toi-chac-chan`` lẫn ``CHO_PHEP_XOA_DB=1`` thì mới cho phép."""
    import scripts.seed as seed

    monkeypatch.setenv("CHO_PHEP_XOA_DB", "1")
    assert seed._cho_phep_reset("postgresql://user:pass@db.example:5432/greenbin?sslmode=require", True) is True


def test_seed_reset_sqlite_khong_can_toi_chac_chan() -> None:
    """--reset trên sqlite vẫn là một lệnh duy nhất, không cần cờ phụ."""
    import scripts.seed as seed

    assert seed._cho_phep_reset("sqlite:///./data/app.db", False) is True
    assert seed._cho_phep_reset("sqlite:///./data/app.db", True) is True
