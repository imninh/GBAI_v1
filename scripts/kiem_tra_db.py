"""Kiểm tra kết nối cơ sở dữ liệu — "DATABASE_URL của tôi dùng được không".

Script **chỉ đọc, không đụng dữ liệu**: nối, chạy ``SELECT 1``, in phiên bản
máy chủ, liệt kê bảng và đếm dòng của ``bins`` + ``users``. Không bao giờ in
mật khẩu. Trả về exit code 0 khi dùng được, 1 khi không — với câu tiếng Việt
đoán nguyên nhân.

Chạy:

    python scripts/kiem_tra_db.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from src.db.session import _them_sslmode, normalize_database_url  # noqa: E402


def _chay(url: str) -> int:
    print("=" * 60)
    print("KIỂM TRA KẾT NỐI CƠ SỞ DỮ LIỆU")
    print("=" * 60)

    # --- In đích đến, KHÔNG in mật khẩu --------------------------------
    parts = urlsplit(url)
    if url.startswith("sqlite"):
        print(f"  Backend: sqlite — {url}")
    else:
        print("  Backend: postgresql")
        print(f"  Máy chủ: {parts.hostname} · Cổng: {parts.port}")

    # --- Cảnh báo transaction pooler --------------------------------
    if not url.startswith("sqlite") and parts.port == 6543:
        print()
        print("  ⚠️  CẢNH BÁO: cổng 6543 là TRANSACTION POOLER của Supabase.")
        print("     Dự án này dùng SESSION POOLER (cổng 5432) — transaction")
        print("     pooler cắt kết nối khi chạy lâu, sẽ gây lỗi khó đoán.")
        print()

    # --- Nối và SELECT 1 ---------------------------------------------
    try:
        engine = create_engine(_them_sslmode(normalize_database_url(url)), future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            if url.startswith("sqlite"):
                phien_ban = conn.execute(text("SELECT sqlite_version()")).scalar()
                in_phien_ban = f"SQLite {phien_ban}"
            else:
                phien_ban = conn.execute(text("SELECT version()")).scalar()
                in_phien_ban = str(phien_ban).split(" on ")[0].strip()
            print("\n  Kết nối OK — SELECT 1 chạy được.")
            print(f"  Phiên bản máy chủ: {in_phien_ban}")
            inspector = inspect(conn)
            bang = inspector.get_table_names()
            print(f"\n  {len(bang)} bảng: {', '.join(sorted(bang))}")
            for ten in ("bins", "users"):
                if ten in bang:
                    dem = conn.execute(text(f"SELECT COUNT(*) FROM {ten}")).scalar()
                    print(f"  - {ten}: {dem} dòng")
                else:
                    print(f"  - {ten}: (chưa có bảng — chạy seed trước)")
        engine.dispose()
    except Exception as exc:
        print("\n  ❌ KHÔNG KẾT NỐI ĐƯỢC.")
        print(f"     Lỗi: {exc}")
        print()
        print("  Nguyên nhân có thể:")
        if not url.startswith("sqlite"):
            if "password" in str(exc).lower():
                print("    - Sai mật khẩu — kiểm tra lại phần mật khẩu trong DATABASE_URL.")
            if "sslmode" not in url:
                print("    - Thiếu sslmode=require — DATABASE_URL phải có sslmode=require (Supabase yêu cầu TLS).")
            if parts.port == 6543:
                print("    - Đang dùng transaction pooler (cổng 6543) — dùng session pooler (5432).")
            else:
                print("    - Chuỗi Direct connection của Supabase chỉ hỗ trợ IPv6 — Render free tier không tới được; hãy dùng SESSION POOLER.")
            if "paused" in str(exc).lower() or "sleeping" in str(exc).lower():
                print("    - Project Supabase đang bị tạm dừng (paused) — mở lại trên Dashboard.")
        else:
            print("    - Đường dẫn file sqlite không tồn tại hoặc thư mục cha chưa tạo.")
        return 1

    print("\n  ✅ MỌI THỨ OK — DATABASE_URL dùng được.")
    return 0


def main() -> int:
    # Console Windows mặc định là cp1252, không in được tiếng Việt có dấu.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("Thiếu biến môi trường DATABASE_URL.")
        return 1
    return _chay(url)


if __name__ == "__main__":
    sys.exit(main())
