"""Cấp / thu hồi khoá thiết bị riêng cho từng thùng — chạy tay.

    python scripts/cap_khoa_thung.py --ma BIN-01
    python scripts/cap_khoa_thung.py --tat-ca
    python scripts/cap_khoa_thung.py --ma BIN-01 --db-url "postgresql://..."
    python scripts/cap_khoa_thung.py --thu-hoi --ma BIN-01

Khoá thô **chỉ in ra đúng một lần** ở đây; hệ thống chỉ giữ bản băm. In xong là
chép ngay vào thiết bị, mất thì cấp lại chứ không đọc lại được.

Cấp lại cho một thùng đã có khoá là **thu hồi** khoá cũ. ``--thu-hoi`` thu hồi
dứt điểm: thùng ngừng nhận reading tới khi được cấp khoá mới — không còn khoá nào
để in, nên không đi cùng ``--ghi-file``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.db.models import Bin  # noqa: E402
from src.db.session import _them_sslmode, get_engine, normalize_database_url  # noqa: E402
from src.services.khoa_thiet_bi import cap_khoa_moi, thu_hoi_khoa  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cấp khoá thiết bị cho thùng thu gom.")
    parser.add_argument("--ma", default="", help="Mã thùng cần cấp khoá.")
    parser.add_argument("--tat-ca", action="store_true", help="Cấp cho mọi thùng đang hoạt động.")
    parser.add_argument("--db-url", default="", help="DSN cần dùng. Bỏ trống thì dùng DATABASE_URL của ứng dụng.")
    parser.add_argument(
        "--ghi-file",
        default="",
        help="Ghi bảng {mã thùng: khoá thô} ra file JSON để bộ mô phỏng đọc. File này là BÍ MẬT.",
    )
    parser.add_argument(
        "--thu-hoi",
        action="store_true",
        help="Thu hồi khoá của thùng — thùng ngừng nhận reading cho tới khi được cấp khoá mới.",
    )
    tham_so = parser.parse_args()

    if not tham_so.ma and not tham_so.tat_ca:
        print("Cần --ma <MÃ THÙNG> hoặc --tat-ca.")
        return 1

    if tham_so.thu_hoi and tham_so.ghi_file:
        print("--thu-hoi không đi cùng --ghi-file: thu hồi không còn khoá nào để ghi.")
        return 1

    if tham_so.db_url:
        engine = create_engine(_them_sslmode(normalize_database_url(tham_so.db_url)), future=True)
    else:
        engine = get_engine()

    with sessionmaker(bind=engine)() as phien:
        dieu_kien = select(Bin) if tham_so.tat_ca else select(Bin).where(Bin.code == tham_so.ma)
        cac_thung = list(phien.scalars(dieu_kien).all())
        if not cac_thung:
            print("Không tìm thấy thùng nào khớp.")
            return 1
        bang_khoa: dict[str, str] = {}
        for thung in cac_thung:
            if tham_so.thu_hoi:
                thu_hoi_khoa(thung)
                print(f"{thung.code}\tĐÃ THU HỒI")
            else:
                khoa = cap_khoa_moi(thung)
                bang_khoa[thung.code] = khoa
                print(f"{thung.code}\t{khoa}")
        phien.commit()

    if tham_so.ghi_file:
        Path(tham_so.ghi_file).write_text(
            json.dumps(bang_khoa, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if tham_so.thu_hoi:
        print(f"\nĐã thu hồi khoá của {len(cac_thung)} thùng. Thùng sẽ không nhận reading cho tới khi được cấp khoá mới.")
    else:
        print(f"\nĐã cấp khoá cho {len(cac_thung)} thùng. Khoá thô KHÔNG đọc lại được — chép ngay.")
    if tham_so.ghi_file:
        print(f"Đã ghi bảng khoá vào {tham_so.ghi_file} — file này là BÍ MẬT, đừng commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
