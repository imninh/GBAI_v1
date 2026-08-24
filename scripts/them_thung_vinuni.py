"""Thêm thùng rác thật tại Đại học VinUni (gói P78).

Thùng VinUni là **thùng thật, phần cứng thật**, nên không đi qua ``seed_bins``
(mô phỏng) mà dùng đường đã có sẵn ``tao_thung`` — hàm này đặt sẵn
``is_seed = False`` (xem ``src/services/bins.py:463``).

⛔ KHÔNG chạy ``scripts/cap_khoa_thung.py``. Script chỉ **in ra** lệnh người
duyệt cần chạy sau đó để cấp khoá riêng (chuỗi khoá thô chỉ hiện một lần).
⛔ KHÔNG chạy script này lên production.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from src.db.models import Bin, User  # noqa: E402
from src.db.session import session_scope  # noqa: E402
from src.services.bins import tao_thung  # noqa: E402

# Toạ độ lấy từ Wikipedia (trang VinUniversity): 20.9893°N, 105.9436°E
# — Vinhomes Ocean Park, Gia Lâm, Hà Nội. Nằm trong hộp Hà Nội (20.5–21.5 / 105.0–106.5).
VINUNI = {
    "code": "BIN_HN_VINUNI_01",
    "name": "Thùng thông minh — Đại học VinUni",
    "address": "Vinhomes Ocean Park, Gia Lâm, Hà Nội",
    "lat": 20.9893,
    "lng": 105.9436,
    "category_codes": ["recyclable", "organic", "other"],
}

MANAGER_EMAIL = "manager@demo.vn"
LENH_CAP_KHOA = f"python scripts/cap_khoa_thung.py --ma {VINUNI['code']}"


def _in_thong_tin_kho() -> None:
    print("[chạy khô] Sẽ tạo thùng thật:")
    for k, v in VINUNI.items():
        print(f"  {k}: {v}")
    print("  is_seed: False (thùng phần cứng thật, không phải dữ liệu mô phỏng)")
    print("Lệnh cấp khoá thiết bị (do NGƯỜI DUYỆT chạy SAU, script này KHÔNG tự chạy):")
    print(f"  {LENH_CAP_KHOA}")


def tao_vinuni(session, *, write: bool = False) -> Bin | None:
    """Tạo thùng VinUni qua ``tao_thung``. Trả về Bin hoặc None.

    Ở chế độ khô không tạo gì. Nếu mã đã tồn tại, bắt lỗi và trả về None (chạy
    lại không được ném lỗi ra ngoài).
    """
    nguoi_tao = session.scalar(select(User).where(User.email == MANAGER_EMAIL))
    if nguoi_tao is None:
        print(f"⛔ Không tìm thấy tài khoản quản lý demo ({MANAGER_EMAIL}).")
        return None

    if not write:
        _in_thong_tin_kho()
        return None

    try:
        thung = tao_thung(session, dict(VINUNI), nguoi_tao)
        # Thùng vừa lắp: mức đầy thấp, pin đầy, vừa báo về → trạng thái bình thường.
        thung.fill_percent = 5.0
        thung.battery_percent = 100.0
        thung.last_seen_at = datetime.now(UTC)
        session.flush()
        print(f"Đã tạo thùng {thung.code} (is_seed={thung.is_seed}).")
        print("Lệnh cấp khoá thiết bị (do NGƯỜI DUYỆT chạy SAU, script này KHÔNG tự chạy):")
        print(f"  {LENH_CAP_KHOA}")
        return thung
    except ValueError as e:
        # Trùng mã — chạy lại không được hỏng.
        print(f"ℹ️ {e} — thùng đã tồn tại, bỏ qua.")
        return None


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Thêm thùng thật Đại học VinUni (P78)")
    parser.add_argument("--that", action="store_true", help="thực sự tạo (ngược lại chỉ chạy khô)")
    args = parser.parse_args()

    with session_scope() as session:
        tao_vinuni(session, write=args.that)
    # Không ném lỗi ra ngoài ngay cả khi trùng mã.
    sys.exit(0)


if __name__ == "__main__":
    main()
