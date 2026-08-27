#!/usr/bin/env python
"""scripts/sao_luu_csdl.py — sao lưu & khôi phục CSDL.

⚠️  CẢNH BÁO: File sao lưu chứa dữ liệu nhạy cảm — password_hash của toàn bộ
người dùng, dữ liệu cá nhân (email, tên, số điện thoại, địa chỉ).
KHÔNG ĐƯỢC đẩy file này lên nơi công khai, không commit vào git, không chia sẻ
qua kênh không mã hoá. Xử lý như bí mật tuyệt đối.

Sao lưu (chỉ đọc):
    python scripts/sao_luu_csdl.py
    python scripts/sao_luu_csdl.py --dir /duong
    python scripts/sao_luu_csdl.py --len-storage
    python scripts/sao_luu_csdl.py --nguon-production   # cho phép đọc production

Khôi phục (ghi — XÓA SẠCH DỮ LIỆU ĐÍCH RỒI GHI LẠI):
    python scripts/sao_luu_csdl.py --khoi-phuc file.json --database-url <URL> --toi-chac-chan
    # BẮT BUỘC: --database-url (không có mặc định), --toi-chac-chan
    # Nếu đích là CSDL xa: CHO_PHEP_GHI_DB_XA=1
    # CSDL production (Supabase, RDS, Railway, Neon, v.v.) bị CHỐT TUYỆT ĐỐI — không có cờ nào mở được.

Quy tắc an toàn:
- Sao lưu: TUYỆT ĐỐI chỉ đọc. Không INSERT/UPDATE/DROP/ALTER ở nguồn.
- Khôi phục: CHỐT TUYỆT ĐỐI production (xét theo URL đích, không theo app_env).
- --database-url BẮT BUỘC khi khôi phục — không dùng mặc định từ .env.
- Trước khi xoá: in kế hoạch (host, bảng, số dòng hiện có ở đích).
- File sao lưu & log không chứa mật khẩu kết nối DB.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Cho phép import `src` khi chạy trực tiếp từ thư mục repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.config import get_settings, reset_settings_cache
from src.db.models import Base
from src.db.session import normalize_database_url
from src.services.luu_tru import tai_len


def _gio_file() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d_%H%M")


def _ten_may_che() -> str:
    """Tên máy chủ đã che một phần (chỉ giữ 3 ký tự đầu + 3 ký tự cuối)."""
    ten = socket.gethostname()
    if len(ten) <= 6:
        return ten[0] + "***" + ten[-1] if len(ten) > 1 else "***"
    return ten[:3] + "***" + ten[-3:]


def _co_the_chay_pg_dump() -> bool:
    try:
        subprocess.run(["pg_dump", "--version"], check=True, capture_output=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _dem_bang(file_sql: str) -> int:
    """Đếm số bảng (CREATE TABLE / COPY) trong file dump SQL — chỉ để in báo cáo."""
    count = 0
    with open(file_sql, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("CREATE TABLE") or line.startswith("COPY "):
                count += 1
    return count


def _xay_dung_thu_tu_bang(metadata) -> list:
    """Sắp xếp bảng theo thứ tự topological dựa trên khóa ngoại (FK).

    Trả về danh sách tên bảng: bảng không phụ thuộc vào bảng khác đứng trước.
    Dùng cho khôi phục để tránh lỗi FK.
    """
    from collections import defaultdict, deque

    bang = list(metadata.tables.keys())
    chi_so = {ten: i for i, ten in enumerate(bang)}
    do_vao = defaultdict(int)
    ke = defaultdict(list)

    for ten_bang, bang_obj in metadata.tables.items():
        for fk in bang_obj.foreign_keys:
            bang_cha = fk.column.table.name
            if bang_cha in chi_so:
                ke[bang_cha].append(ten_bang)
                do_vao[ten_bang] += 1

    hang_doi = deque([t for t in bang if do_vao[t] == 0])
    ket_qua = []
    while hang_doi:
        t = hang_doi.popleft()
        ket_qua.append(t)
        for con in ke[t]:
            do_vao[con] -= 1
            if do_vao[con] == 0:
                hang_doi.append(con)

    if len(ket_qua) != len(bang):
        # Có vòng (hiếm), fallback dùng thứ tự metadata
        return bang
    return ket_qua


def _sao_luu_python(db_url: str, duong_dan_ra: Path) -> dict:
    """Sao lưu bằng Python thuần (SQLAlchemy) ra file JSON.

    Trả về dict thống kê: {so_bang, so_dong_tong, kich_thuoc_byte}.
    """
    engine = create_engine(normalize_database_url(db_url), future=True)
    metadata = Base.metadata

    # Đảm bảo metadata có đủ bảng (nếu chưa load models)
    if not metadata.tables:
        from src.db import models  # noqa: F401

    thu_tu = _xay_dung_thu_tu_bang(metadata)

    du_lieu = {
        "meta": {
            "thoi_gian": datetime.now(UTC).isoformat(),
            "may_chu": _ten_may_che(),
            "sqlalchemy_version:": "2.x",
            "bang": [],
            "canh_bao": "File này chứa dữ liệu nhạy cảm: password_hash của người dùng, email, tên, số điện thoại, địa chỉ. KHÔNG ĐƯỢC đẩy lên nơi công khai, không commit vào git.",
        },
        "data": {},
    }

    tong_dong = 0
    with Session(engine) as session:
        for ten_bang in thu_tu:
            bang_obj = metadata.tables[ten_bang]
            cot = [c.name for c in bang_obj.columns]
            rows = session.execute(text(f"SELECT {', '.join(cot)} FROM {ten_bang}")).fetchall()
            du_lieu["data"][ten_bang] = [dict(zip(cot, r, strict=False)) for r in rows]
            so_dong = len(rows)
            tong_dong += so_dong
            du_lieu["meta"]["bang"].append({"ten": ten_bang, "so_dong": so_dong, "cot": cot})

    # Ghi file JSON
    duong_dan_ra.parent.mkdir(parents=True, exist_ok=True)
    with open(duong_dan_ra, "w", encoding="utf-8") as f:
        json.dump(du_lieu, f, ensure_ascii=False, indent=2, default=str)

    kich_thuoc = duong_dan_ra.stat().st_size
    return {"so_bang": len(thu_tu), "so_dong_tong": tong_dong, "kich_thuoc": kich_thuoc, "thu_tu": thu_tu}


def _khoi_phuc_python(db_url: str, duong_dan_vao: Path) -> dict:
    """Khôi phục từ file JSON vào CSDL đích.

    Trả về dict thống kê: {so_bang, so_dong_tong}.
    """
    with open(duong_dan_vao, encoding="utf-8") as f:
        du_lieu = json.load(f)

    engine = create_engine(normalize_database_url(db_url), future=True)
    metadata = Base.metadata

    if not metadata.tables:
        from src.db import models  # noqa: F401

    thu_tu = _xay_dung_thu_tu_bang(metadata)

    tong_dong = 0
    with Session(engine) as session:
        for ten_bang in thu_tu:
            if ten_bang not in du_lieu.get("data", {}):
                continue
            bang_obj = metadata.tables[ten_bang]
            cot = [c.name for c in bang_obj.columns]
            rows = du_lieu["data"][ten_bang]
            if not rows:
                continue
            # Xóa dữ liệu cũ trong bảng đích (trong transaction)
            session.execute(text(f"DELETE FROM {ten_bang}"))
            # Chèn dữ liệu mới
            placeholders = ", ".join([f":{c}" for c in cot])
            sql = f"INSERT INTO {ten_bang} ({', '.join(cot)}) VALUES ({placeholders})"
            for row in rows:
                # Chỉ giữ các cột có trong bảng
                row_filtered = {k: v for k, v in row.items() if k in cot}
                session.execute(text(sql), row_filtered)
            tong_dong += len(rows)
        session.commit()

    return {"so_bang": len(thu_tu), "so_dong_tong": tong_dong}


def _sao_luu_pg_dump(db_url: str, duong_dan_ra: Path) -> dict:
    """Sao lưu bằng pg_dump ra file SQL."""
    parsed = urlparse(db_url)
    env = dict(os.environ)
    if parsed.password:
        env["PGPASSWORD"] = parsed.password

    bat_dau = time.time()
    try:
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
                "-f", str(duong_dan_ra),
            ],
            check=True,
            env=env,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        msg = exc.stderr.decode("utf-8", "ignore")[:500] if exc.stderr else str(exc)
        raise RuntimeError(f"pg_dump thất bại: {msg}") from exc

    thoi_gian = time.time() - bat_dau
    kich_thuoc = duong_dan_ra.stat().st_size
    so_bang = _dem_bang(str(duong_dan_ra))
    return {"so_bang": so_bang, "so_dong_tong": -1, "kich_thuoc": kich_thuoc, "thoi_gian": thoi_gian}


def _la_csdl_xa(db_url: str) -> bool:
    """CSDL XA = không phải sqlite VÀ host không thuộc nhóm máy cục bộ."""
    if db_url.startswith("sqlite"):
        return False
    host = (urlparse(db_url).hostname or "").lower()
    return host not in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _la_csdl_production(db_url: str, env_database_url: str) -> bool:
    """Nhận diện CSDL production bằng cách kiểm tra URL đích.

    Xét ba dấu hiệu (khớp một là đủ):
    1. Host chứa từ khóa của các nhà cung cấp đám mây phổ biến.
    2. Host trùng với host trong DATABASE_URL của .env (bắt production dù đổi tên).
    3. Host không phải localhost và có domain dạng production (heuristic).

    Args:
        db_url: URL CSDL đích đang chuẩn bị khôi phục.
        env_database_url: DATABASE_URL từ .env (để so sánh host).

    Returns:
        True nếu là production, False nếu là development/test cục bộ.
    """
    host = (urlparse(db_url).hostname or "").lower()

    # KIỂM TRA IP PRIVATE TRƯỚC HẾT - không bao giờ coi là production
    # Các dải IP private: 10.x.x.x, 172.16-31.x.x, 192.168.x.x
    try:
        parts = host.split(".")
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            a, b = int(parts[0]), int(parts[1])
            if a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168):
                return False  # IP private -> không phải production
    except Exception:
        pass

    # Danh sách từ khóa nhận diện nhà cung cấp production
    production_host_keywords = (
        "supabase",
        "pooler",
        "rds.amazonaws",
        "railway",
        "neon.tech",
        "render.com",
        "fly.io",
        "planetscale",
        "aivencloud",
        "digitalocean.com",
        "mongodb.net",  # MongoDB Atlas (nếu dùng)
    )

    # 1. Kiểm tra từ khóa nhà cung cấp
    for kw in production_host_keywords:
        if kw in host:
            return True

    # 2. So sánh với host trong .env (bắt production dù đổi tên miền tùy chỉnh)
    if env_database_url:
        env_host = (urlparse(env_database_url).hostname or "").lower()
        if env_host and env_host == host:
            return True

    # 3. Heuristic: host không phải localhost nhưng có domain public (có chấm)
    #    và không phải IP (đã kiểm tra IP private ở trên)
    if host and host not in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        # Domain public (có chấm, không phải IP) -> coi là production
        if "." in host and not all(p.isdigit() for p in host.split(".")):
            return True

    return False


def _dem_dong_bang(engine, ten_bang: str) -> int:
    """Đếm số dòng trong một bảng."""
    with Session(engine) as session:
        return session.scalar(text(f"SELECT COUNT(*) FROM {ten_bang}"))


def _in_ke_hoach_khoi_phuc(db_url: str, duong_dan_vao: Path) -> None:
    """In kế hoạch khôi phục trước khi thực hiện: host, bảng, số dòng sẽ bị xoá.

    Chỉ đọc metadata từ file backup, KHÔNG kết nối đến CSDL đích để tránh treo.
    """
    with open(duong_dan_vao, encoding="utf-8") as f:
        du_lieu = json.load(f)

    print("┌─ KẾ HOẠCH KHÔI PHỤC (SẼ XÓA SẠCH DỮ LIỆU ĐÍCH) ─")
    host = urlparse(db_url).hostname or "?"
    cong = urlparse(db_url).port or ""
    print(f"│ Đích: {host}:{cong} (mật khẩu đã che)")
    print(f"│ File: {duong_dan_vao}")
    print("│ Các bảng sẽ bị DELETE toàn bộ rồi INSERT lại (theo metadata backup):")
    tong_dong_se_ghi = 0

    for bang_info in du_lieu.get("meta", {}).get("bang", []):
        ten_bang = bang_info.get("ten", "?")
        so_dong_se_ghi = bang_info.get("so_dong", 0)
        tong_dong_se_ghi += so_dong_se_ghi
        print(f"│   - {ten_bang}: {so_dong_se_ghi:,} dòng sẽ ghi (số dòng hiện tại ở đích: chưa kiểm tra)")

    print(f"│ TỔNG: {tong_dong_se_ghi:,} dòng từ backup sẽ được ghi")
    print("└─────────────────────────────────────────────────────")


def _kiem_tra_khoa_khoi_phuc(settings, url_dich: str, env_database_url: str) -> str | None:
    """Kiểm tra khoá cho khôi phục. Trả về thông báo lỗi nếu bị chặn, None nếu cho phép.

    Logic:
    1. CHỐT TUYỆT ĐỐI: nếu đích là CSDL production (xét theo URL) -> từ chối, KHÔNG CÓ NGOẠI LỆ.
    2. Nếu CSDL đích là xa (không phải sqlite/localhost) -> yêu cầu CHO_PHEP_GHI_DB_XA=1.
    """
    # 1. CHỐT PRODUCTION THEO URL ĐÍCH (không xét app_env)
    if _la_csdl_production(url_dich, env_database_url):
        host = urlparse(url_dich).hostname or "?"
        return (
            f"CHỐT TUYỆT ĐỐI: KHÔNG khôi phục vào CSDL production ({host}). "
            f"Phát hiện production theo host. Muốn khôi phục production phải làm bằng tay, có người nhìn."
        )

    # 2. CSDL xa cần biến môi trường
    if _la_csdl_xa(url_dich):
        if os.environ.get("CHO_PHEP_GHI_DB_XA") != "1":
            host = urlparse(url_dich).hostname or "?"
            cong = urlparse(url_dich).port or ""
            return (
                f"CHỐT CHẶN: khôi phục vào CSDL xa ({host}:{cong}) cần biến môi trường "
                f"CHO_PHEP_GHI_DB_XA=1. Đặt biến này rồi chạy lại."
            )

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Sao lưu & khôi phục CSDL GreenBin AI")
    parser.add_argument("--dir", default=os.getcwd(), help="Thư mục ghi file sao lưu (mặc định: thư mục hiện tại)")
    parser.add_argument(
        "--len-storage",
        action="store_true",
        help="Đẩy bản sao lên Supabase Storage sau khi ghi xong.",
    )
    parser.add_argument(
        "--nguon-production",
        action="store_true",
        help="Cho phép đọc từ CSDL production (bắt buộc khi sao lưu production).",
    )
    parser.add_argument(
        "--khoi-phuc",
        metavar="FILE",
        help="Đường dẫn file sao lưu (.json) để khôi phục.",
    )
    parser.add_argument(
        "--database-url",
        metavar="URL",
        help="Đường dẫn CSDL đích khi khôi phục (BẮT BUỘC khi dùng --khoi-phuc).",
    )
    parser.add_argument(
        "--toi-chac-chan",
        action="store_true",
        help="Xác nhận rõ ràng cho thao tác GHI (bắt buộc khi --khoi-phuc).",
    )
    args = parser.parse_args()

    settings = get_settings()
    db_url_nguon = settings.database_url

    # --- CHẾ ĐỘ KHÔI PHỤC ---
    if args.khoi_phuc:
        if not args.toi_chac_chan:
            print("⛔ TỪ CHỐI: khôi phục cần cờ --toi-chac-chan.", file=sys.stderr)
            return 2

        if not args.database_url:
            print("⛔ TỪ CHỐI: --khoi-phuc BẮT BUỘC phải kèm --database-url (không dùng mặc định từ .env).", file=sys.stderr)
            return 2

        file_khoi_phuc = Path(args.khoi_phuc)
        if not file_khoi_phuc.exists():
            print(f"⛔ Không tìm thấy file: {file_khoi_phuc}", file=sys.stderr)
            return 2

        # Xác định URL đích (bắt buộc từ --database-url)
        url_dich = normalize_database_url(args.database_url)
        reset_settings_cache()

        # Kiểm tra khoá (truyền env_database_url để so sánh host)
        loi = _kiem_tra_khoa_khoi_phuc(settings, url_dich, db_url_nguon)
        if loi:
            print(f"⛔ {loi}", file=sys.stderr)
            return 2

        # 1. Kiểm tra đuôi file trước khi in kế hoạch
        if file_khoi_phuc.suffix == ".json":
            _in_ke_hoach_khoi_phuc(url_dich, file_khoi_phuc)
        else:
            print(f"⚠️  Không in kế hoạch cho file {file_khoi_phuc.suffix} (chỉ hỗ trợ .json)")

        print(f"🔄 Đang khôi phục từ {file_khoi_phuc} → {url_dich.split('@')[-1].split('?')[0]}")

        if file_khoi_phuc.suffix == ".json":
            thong_ke = _khoi_phuc_python(url_dich, file_khoi_phuc)
            print(f"✅ Khôi phục xong: {thong_ke['so_bang']} bảng, {thong_ke['so_dong_tong']:,} dòng.")
        elif file_khoi_phuc.suffix == ".sql":
            print("⛔ Khôi phục file .sql chưa được hỗ trợ trong script này. Dùng psql thủ công.", file=sys.stderr)
            return 2
        else:
            print(f"⛔ Định dạng file không hỗ trợ: {file_khoi_phuc.suffix} (chỉ .json)", file=sys.stderr)
            return 2
        return 0

    # --- CHẾ ĐỘ SAO LƯU ---
    # Kiểm tra production: chỉ chặn khi KHÔNG có cờ --nguon-production
    if settings.app_env == "production" and not args.nguon_production:
        print("⛔ TỪ CHỐI: không chạy sao lưu trên production nếu thiếu cờ --nguon-production.", file=sys.stderr)
        print("   Nếu thật sự muốn sao lưu production, thêm cờ --nguon-production.", file=sys.stderr)
        return 2

    if "postgresql" not in db_url_nguon and not db_url_nguon.startswith("sqlite"):
        print(
            f"⛔ Chỉ hỗ trợ Postgres (postgresql://...) hoặc SQLite. DATABASE_URL hiện tại: {db_url_nguon[:20]!r}",
            file=sys.stderr,
        )
        return 2

    # Chọn đường sao lưu
    co_pg_dump = _co_the_chay_pg_dump()
    duong_dan_ra = Path(args.dir) / f"sao_luu_{_gio_file()}"

    if co_pg_dump and db_url_nguon.startswith("postgresql"):
        duong_dan_ra = duong_dan_ra.with_suffix(".sql")
        print(f"📦 Sao lưu bằng pg_dump → {duong_dan_ra}")
        thong_ke = _sao_luu_pg_dump(db_url_nguon, duong_dan_ra)
        print(f"✅ Đã ghi: {duong_dan_ra}")
        print(f"   Kích thước : {thong_ke['kich_thuoc']:,} byte ({thong_ke['kich_thuoc'] / 1024:.1f} KB)")
        print(f"   Số bảng    : {thong_ke['so_bang']}")
        print(f"   Thời gian  : {thong_ke['thoi_gian']:.2f} giây")
    else:
        duong_dan_ra = duong_dan_ra.with_suffix(".json")
        print(f"🐍 Sao lưu bằng Python thuần (SQLAlchemy) → {duong_dan_ra}")
        thong_ke = _sao_luu_python(db_url_nguon, duong_dan_ra)
        print(f"✅ Đã ghi: {duong_dan_ra}")
        print(f"   Kích thước : {thong_ke['kich_thuoc']:,} byte ({thong_ke['kich_thuoc'] / 1024:.1f} KB)")
        print(f"   Số bảng    : {thong_ke['so_bang']}")
        print(f"   Tổng dòng  : {thong_ke['so_dong_tong']:,}")
        # Cảnh báo dữ liệu nhạy cảm
        print("⚠️  CẢNH BÁO: File sao lưu chứa password_hash, email, tên, SĐT, địa chỉ — KHÔNG ĐƯỢC đẩy lên nơi công khai.")

    if args.len_storage:
        khoa = f"backups/{duong_dan_ra.name}"
        if tai_len(str(duong_dan_ra), khoa):
            print(f"✅ Đã đẩy lên Storage: {khoa}")
        else:
            print("⚠️  Đẩy lên Storage thất bại (kiểm storage_enabled / SUPABASE_*). File vẫn giữ.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
