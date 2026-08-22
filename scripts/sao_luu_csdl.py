#!/usr/bin/env python
"""scripts/sao_luu_csdl.py — sao lưu Postgres bằng pg_dump (CHỈ ĐỌC).

⚠️  CẢNH BÁO QUAN TRỌNG
=====================
Bản sao lưu chưa từng khôi phục thử thì KHÔNG tính là bản sao lưu. Phải thử
khôi phục vào một CSDL rỗng ít nhất một lần (bằng tay, có người nhìn) để biết
file dump thật sự còn dùng được. Script này KHÔNG có chế độ khôi phục — việc
đó phải làm cẩn thận, không tự động.

Quy tắc:
- Script này TUYỆT ĐỐI chỉ đọc. Không INSERT, không UPDATE, không DROP, không
  ALTER. pg_dump sinh ra file văn bản, không đụng gì tới dữ liệu đang chạy.
- KHÔNG chạy lên cơ sở dữ liệu production. Gặp app_env == "production" là từ
  chối. Chỉ chạy trên bản test / bản sao.
- Mật khẩu truyền qua biến môi trường PGPASSWORD, không lộ trên argv.

Dùng:
    python scripts/sao_luu_csdl.py                  # ghi ra thư mục hiện tại
    python scripts/sao_luu_csdl.py --dir /duong    # ghi ra thư mục chỉ định
    python scripts/sao_luu_csdl.py --len-storage   # đẩy lên Supabase Storage
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from urllib.parse import urlparse

# Cho phép import `src` khi chạy trực tiếp từ thư mục repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import get_settings
from src.services.luu_tru import tai_len


def _gio_file() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M")


def _co_the_chay_pg_dump() -> bool:
    try:
        subprocess.run(["pg_dump", "--version"], check=True, capture_output=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _dem_bang(file_sql: str) -> int:
    """Đếm số bảng (CREATE TABLE / COPY) trong file dump — chỉ để in báo cáo."""
    count = 0
    with open(file_sql, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("CREATE TABLE") or line.startswith("COPY "):
                count += 1
    return count


def _day_len_storage(file_sql: str, khoa: str) -> bool:
    """Đẩy file lên Supabase Storage (tầng lưu trữ đã có). Trả True nếu thành công."""
    return tai_len(file_sql, khoa) is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Sao lưu CSDL (pg_dump, chỉ đọc).")
    parser.add_argument("--dir", default=os.getcwd(), help="Thư mục ghi file sao lưu.")
    parser.add_argument(
        "--len-storage",
        action="store_true",
        help="Đẩy bản sao lên Supabase Storage sau khi ghi xong.",
    )
    args = parser.parse_args()

    settings = get_settings()
    db_url = settings.database_url

    # Cổng an toàn: không chạy trên production.
    if settings.app_env == "production":
        print("⛔ TỪ CHỐI: không chạy sao lưu trên môi trường production.", file=sys.stderr)
        return 2

    if "postgresql" not in db_url:
        print(
            f"⛔ Chỉ hỗ trợ Postgres (postgresql://...). DATABASE_URL hiện tại bắt đầu bằng "
            f"{db_url[:12]!r}.",
            file=sys.stderr,
        )
        return 2

    if not _co_the_chay_pg_dump():
        print("⛔ Không tìm thấy pg_dump trên máy. Cài PostgreSQL client rồi thử lại.", file=sys.stderr)
        return 2

    os.makedirs(args.dir, exist_ok=True)
    file_sql = os.path.join(args.dir, f"sao_luu_{_gio_file()}.sql")

    # Tách thành phần để truyền qua flag (tránh lộ URL chứa mật khẩu trên argv).
    parsed = urlparse(db_url)
    env = dict(os.environ)
    if parsed.password:
        env["PGPASSWORD"] = parsed.password

    bat_dau = time.time()
    try:
        # pg_dump CHỈ ĐỌC: không có flag ghi ngược, không DROP. Sinh file văn bản.
        subprocess.run(
            [
                "pg_dump",
                "--no-owner",
                "--no-privileges",
                "--format=plain",
                "-h", str(parsed.hostname or ""),
                "-p", str(parsed.port or 5432),
                "-U", str(parsed.username or ""),
                "-d", parsed.path.lstrip("/"),
                "-f", file_sql,
            ],
            check=True,
            env=env,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        msg = exc.stderr.decode("utf-8", "ignore")[:500] if exc.stderr else str(exc)
        print(f"⛔ pg_dump thất bại: {msg}", file=sys.stderr)
        return 1

    thoi_gian = time.time() - bat_dau
    kich_thuoc = os.path.getsize(file_sql)
    so_bang = _dem_bang(file_sql)

    print(f"✅ Đã ghi: {file_sql}")
    print(f"   Kích thước : {kich_thuoc:,} byte ({kich_thuoc / 1024:.1f} KB)")
    print(f"   Số bảng    : {so_bang}")
    print(f"   Thời gian  : {thoi_gian:.2f} giây")

    if args.len_storage:
        khoa = f"backups/{os.path.basename(file_sql)}"
        if _day_len_storage(file_sql, khoa):
            print(f"✅ Đã đẩy lên Storage: {khoa}")
        else:
            print(
                "⚠️  Đẩy lên Storage thất bại (kiểm storage_enabled / SUPABASE_*). File vẫn giữ.",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
