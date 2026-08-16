"""Vá schema cho một cơ sở dữ liệu đã tồn tại — chạy tay khi cần.

Trên máy chủ, việc này đã tự chạy lúc khởi động (``init_db`` gọi
``va_cot_thieu``). Script này dành cho lúc muốn vá một CSDL **mà không khởi động
máy chủ** — ví dụ vá ``data/app.db`` ở máy dev, hoặc vá Supabase từ máy mình.

    python scripts/them_cot_phone.py
    python scripts/them_cot_phone.py --db-url "postgresql://..."

Không truyền ``--db-url`` thì dùng đúng ``DATABASE_URL`` mà ứng dụng đang dùng.
Chạy lại nhiều lần vô hại.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Chạy như `python scripts/them_cot_phone.py` thì `scripts/` đứng đầu sys.path,
# còn gói `src` nằm ở thư mục cha (xem scripts/seed.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from src.db.schema_patch import va_cot_thieu  # noqa: E402
from src.db.seed_data import USERS  # noqa: E402
from src.db.session import _them_sslmode, get_engine, normalize_database_url  # noqa: E402

# Console Windows mặc định cp1252, in tiếng Việt thẳng ra là vỡ.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description="Vá schema và điền số điện thoại demo.")
    parser.add_argument("--db-url", default="", help="DSN cần vá. Bỏ trống thì dùng DATABASE_URL của ứng dụng.")
    tham_so = parser.parse_args()

    if tham_so.db_url:
        engine = create_engine(_them_sslmode(normalize_database_url(tham_so.db_url)), future=True)
    else:
        engine = get_engine()

    da_them = va_cot_thieu(engine)
    print(f"Cột vừa thêm: {da_them or 'không có, CSDL đã đủ cột'}")

    # Điền số cho tài khoản demo. KHÔNG ghi đè số người dùng tự đặt.
    da_dien = 0
    with engine.begin() as ket_noi:
        for row in USERS:
            ket_qua = ket_noi.execute(
                text(
                    "UPDATE users SET phone = :phone "
                    "WHERE email = :email AND (phone IS NULL OR phone = '')"
                ),
                {"phone": row["phone"], "email": row["email"]},
            )
            da_dien += ket_qua.rowcount
    print(f"Đã điền số điện thoại cho {da_dien} tài khoản.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
