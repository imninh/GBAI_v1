"""Dựng cảnh điều phối cho toàn bộ thùng đang có trên CSDL (gói P78).

Mục đích: cập nhật ``fill_percent`` · ``battery_percent`` · ``last_seen_at``
cho mọi thùng để màn điều phối trông đủ các tình huống (đầy / hết pin / mất
kết nối / bình thường) mà KHÔNG sửa tay từng thùng.

⚠️ Chỉ đụng đúng ba trường trên. Không đổi ``deployment_status`` · ``is_active``
· ``is_seed`` · toạ độ. Bỏ qua thùng ``is_seed = False`` (thùng thật do người
nhập, ví dụ VinUni) — không ghi đè số đo của nó bằng số bịa.

⛔ KHÔNG gọi ``init_db()`` — script này chỉ SELECT và UPDATE, tuyệt đối không
ALTER lược đồ. Chạy mặc định là **khô** (chỉ in), chỉ ghi khi có CẢ HAI cờ
``--that`` và ``--toi-chac-chan``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.db.models import Bin  # noqa: E402
from src.db.session import session_scope  # noqa: E402
from src.services.bins import trang_thai_thung  # noqa: E402

# Tỉ lệ mục tiêu áp cho tổng số thùng thật (§7): ~60 / 25 / 8 / 7 %.
_TY_LE = {"binh_thuong": 0.60, "can_gom": 0.25, "het_pin": 0.08, "mat_ket_noi": 0.07}


def _phan_bo_so_luong(n: int) -> dict[str, int]:
    """Chia ``n`` thùng theo tỉ lệ mục tiêu, tất định, mỗi loại >=1 khi n >= 4."""
    binh = round(n * _TY_LE["binh_thuong"])
    cang = round(n * _TY_LE["can_gom"])
    het = round(n * _TY_LE["het_pin"])
    mat = n - binh - cang - het
    if n >= 4:
        if het < 1:
            het = 1
        if mat < 1:
            mat = 1
        binh = n - cang - het - mat
        if binh < 1:
            binh = 1
    return {"binh_thuong": binh, "can_gom": cang, "het_pin": het, "mat_ket_noi": mat}


def _gan_gia_tri(
    trang_thai: str, idx: int, settings
) -> tuple[float, float, int]:
    """Trả về (fill_percent, battery_percent, last_seen_ago_minutes) tạo ra ``trang_thai``.

    Mọi giá trị đều **vượt ngưỡng một khoảng rõ ràng** (không sát mép) và tính
    quyết định từ ``idx`` — không dùng ``random``. Ngưỡng lấy từ cấu hình thật.
    """
    offline = settings.bin_offline_minutes
    fill_alert = settings.bin_fill_alert_percent

    if trang_thai == "binh_thuong":
        fill = 15.0 + (idx * 7) % (fill_alert - 20)  # < fill_alert
        batt = 55.0 + (idx * 5) % 40  # > low_batt
        ago = 1 + (idx % 10)  # < offline
    elif trang_thai == "can_gom":
        fill = float(fill_alert + 2 + (idx * 3) % (100 - fill_alert - 2))  # >= fill_alert
        batt = 55.0 + (idx * 5) % 40
        ago = 1 + (idx % 10)
    elif trang_thai == "het_pin":
        fill = 10.0 + (idx * 7) % 60  # < fill_alert
        batt = 5.0 + (idx % 10)  # <= low_batt
        ago = 1 + (idx % 10)
    else:  # mat_ket_noi
        fill = 40.0 + (idx * 5) % 40
        batt = 55.0 + (idx * 5) % 40
        ago = offline + 60 * 24  # > offline (1 ngày rưỡi)
    return fill, batt, ago


def tinh_canh_demo(session, *, write: bool = False) -> dict:
    """Dựng cảnh cho thùng có trên CSDL. Trả về tóm tắt để in.

    Không ghi đè thùng ``is_seed = False``. Ở chế độ khô, không thay đổi gì.
    """
    settings = get_settings()
    now = datetime.now(UTC)

    thung_trong_csdl = session.scalars(select(Bin)).all()
    # Chỉ thùng demo (is_seed=True) — bỏ qua thùng thật do người nhập.
    danh_sach = [t for t in thung_trong_csdl if t.is_seed]
    bo_qua = len(thung_trong_csdl) - len(danh_sach)

    # Sắp xếp theo code rồi chia lượt tất định.
    danh_sach.sort(key=lambda t: t.code)
    so_luong = _phan_bo_so_luong(len(danh_sach))
    thu_tu = (
        ["binh_thuong"] * so_luong["binh_thuong"]
        + ["can_gom"] * so_luong["can_gom"]
        + ["het_pin"] * so_luong["het_pin"]
        + ["mat_ket_noi"] * so_luong["mat_ket_noi"]
    )

    truoc: dict[str, int] = {}
    sau: dict[str, int] = {}
    for t in danh_sach:
        tt = trang_thai_thung(t, now)
        truoc[tt] = truoc.get(tt, 0) + 1

    da_cap_nhat = 0
    for idx, (t, trang_thai) in enumerate(zip(danh_sach, thu_tu)):
        fill, batt, ago = _gan_gia_tri(trang_thai, idx, settings)
        sau[trang_thai] = sau.get(trang_thai, 0) + 1
        if write:
            t.fill_percent = fill
            t.battery_percent = batt
            t.last_seen_at = now - timedelta(minutes=ago)
            da_cap_nhat += 1
        else:
            print(
                f"  {t.code:14s} {trang_thai:13s} "
                f"(fill={fill:5.1f}, batt={batt:5.1f}, seen_ago={ago} phut)"
            )

    if write:
        session.flush()

    return {
        "tong": len(danh_sach),
        "bo_qua_is_seed_false": bo_qua,
        "da_cap_nhat": da_cap_nhat,
        "truoc": truoc,
        "sau": sau,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Dựng cảnh điều phối cho thùng đang có (P78)")
    parser.add_argument("--that", action="store_true", help="thực sự ghi (cần kèm --toi-chac-chan)")
    parser.add_argument("--toi-chac-chan", action="store_true", help="xác nhận ghi thật")
    args = parser.parse_args()

    write = args.that and args.toi_chac_chan
    if args.that and not args.toi_chac_chan:
        print("⛔ Cần cả --toi-chac-chan để ghi thật.")
        sys.exit(2)

    with session_scope() as session:
        ket_qua = tinh_canh_demo(session, write=write)
        print(f"[{( 'GHI THAT' if write else 'CHAY KHO' )}] Tổng thùng xét: {ket_qua['tong']}")
        print(f"  Bỏ qua (is_seed=False): {ket_qua['bo_qua_is_seed_false']}")
        if write:
            print(f"  Đã cập nhật: {ket_qua['da_cap_nhat']}")
        print("  Truoc:", ket_qua["truoc"])
        print("  Sau  :", ket_qua["sau"])


if __name__ == "__main__":
    main()
