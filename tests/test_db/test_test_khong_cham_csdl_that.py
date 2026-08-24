"""Lưới chống tái phát: bộ test KHÔNG BAO GIỜ trỏ ra CSDL thật (P84).

Ba test này đọc cấu hình THẬT của bộ test (do khối đầu `tests/conftest.py` ép
`DATABASE_URL` về SQLite + `APP_ENV=test`). Nếu ai đó gỡ khối đó, đổi `.env`,
hay đặt `APP_ENV=production` cho test xanh, ba test này đỏ ngay — bảo vệ chỗ
nguy hiểm nhất: bảng tự mọc trên Supabase mỗi lần chạy `pytest`.
"""

from __future__ import annotations

from src.config import get_settings


def test_bo_test_luon_dung_sqlite() -> None:
    url = get_settings().database_url
    assert url.startswith("sqlite"), (
        f"Bộ test đang trỏ ra CSDL ngoài: {url!r}. Kiểm lại khối đầu "
        "`tests/conftest.py` — nó phải ép DATABASE_URL về SQLite tạm."
    )


def test_bo_test_khong_tro_toi_supabase() -> None:
    assert "supabase" not in get_settings().database_url.lower(), (
        "Bộ test đang trỏ tới Supabase — kiểm lại khối đầu `tests/conftest.py`."
    )


def test_moi_truong_test_khong_phai_production() -> None:
    assert get_settings().app_env != "production", (
        "Không được đặt APP_ENV=production cho bộ test — làm vậy sẽ mở khoá "
        "chốt chặn `chan_khong_ghi_csdl_xa` và để test chạy thẳng vào CSDL thật."
    )
