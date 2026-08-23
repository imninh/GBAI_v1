"""Chốt chặn ``init_db()`` — không để bảng tự mọc trên CSDL xa (P81).

Đợt trước ``.env`` trên máy dev trỏ thẳng vào Supabase production, nên chỉ cần
chạy app là bảng tự mọc trên CSDL thật — đã xảy ra với bốn bảng mới. Chốt chặn
trong ``src/db/session.py`` chặn đường đó.

Test gọi ĐÚNG hàm mà ``init_db()`` gọi (``chan_khong_ghi_csdl_xa``), không viết
lại logic. Không kết nối CSDL thật — chỉ dùng chuỗi URL giả, không mở kết nối nào.
"""

from __future__ import annotations

import pytest

from src.config import reset_settings_cache
from src.db.session import chan_khong_ghi_csdl_xa

URL_XA = "postgresql://u:matkhau@abc.supabase.com:5432/postgres"


@pytest.fixture(autouse=True)
def _dat_lai_settings() -> None:
    """Xoá cache cấu hình trước và sau mỗi test để env đổi không rò sang test khác."""
    reset_settings_cache()
    yield
    reset_settings_cache()


def _dat_csdl(monkeypatch: pytest.MonkeyPatch, url: str, app_env: str) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("APP_ENV", app_env)
    # Mặc định không mở khoá — chốt phải chặn ở môi trường dev/xa.
    monkeypatch.setenv("CHO_PHEP_GHI_DB_XA", "0")


def test_sqlite_luon_chay_duoc(monkeypatch: pytest.MonkeyPatch) -> None:
    _dat_csdl(monkeypatch, "sqlite:///./data/_p81_test.db", "development")
    # Không được ném lỗi — SQLite là máy cục bộ.
    chan_khong_ghi_csdl_xa()


def test_localhost_chay_duoc(monkeypatch: pytest.MonkeyPatch) -> None:
    _dat_csdl(monkeypatch, "postgresql://u:p@localhost:5432/db", "development")
    # localhost thuộc nhóm máy cục bộ → không chặn, kể cả khi app_env=development.
    chan_khong_ghi_csdl_xa()


def test_csdl_xa_moi_truong_dev_bi_chan(monkeypatch: pytest.MonkeyPatch) -> None:
    _dat_csdl(monkeypatch, URL_XA, "development")
    with pytest.raises(RuntimeError):
        chan_khong_ghi_csdl_xa()


def test_csdl_xa_moi_truong_production_van_chay(monkeypatch: pytest.MonkeyPatch) -> None:
    _dat_csdl(monkeypatch, URL_XA, "production")
    # Bản deploy Railway chạy app_env=production → KHÔNG bị chốt chặn.
    chan_khong_ghi_csdl_xa()


def test_thong_bao_loi_khong_ro_mat_khau(monkeypatch: pytest.MonkeyPatch) -> None:
    _dat_csdl(monkeypatch, URL_XA, "development")
    with pytest.raises(RuntimeError) as e:
        chan_khong_ghi_csdl_xa()
    assert "matkhau" not in str(e.value), "Thông báo lỗi không được lộ mật khẩu"
    assert URL_XA not in str(e.value), "Thông báo lỗi không được in nguyên chuỗi kết nối"
    assert "abc.supabase.com" in str(e.value)
