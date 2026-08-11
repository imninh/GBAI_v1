"""Mô phỏng thiết bị thùng thu gom — thay phần cứng chưa tồn tại gửi reading.

Mỗi bước đẩy mức rác và mức pin mới của từng thùng qua
``POST /bins/{code}/readings`` kèm header ``X-Device-Key``, để màn hình điều
phối có dữ liệu "sống" trước khi có thùng thật. Cách chạy:

    python scripts/device_simulator.py --key <khoa> --api http://localhost:8000

Phần thú vị nhất (quy luật tăng/giảm của một thùng) nằm trong
:func:`buoc_tiep_theo` — hàm thuần, không đụng mạng, test được mà không cần
máy chủ. Phần còn lại là vỏ I/O mỏng bằng thư viện chuẩn.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from src.db.seed_data import SEED_BINS  # noqa: E402


def buoc_tiep_theo(fill_percent: float, battery_percent: float) -> tuple[float, float]:
    """Trạng thái tiếp theo của một thùng sau một bước mô phỏng.

    Quy luật:
    * mức rác tăng một lượng nhỏ ngẫu nhiên;
    * vượt quá 95 thì coi như thùng vừa được đổ, reset về mức thấp;
    * pin tụt chậm và không bao giờ dưới 0.

    Cả hai giá trị luôn nằm trong 0–100.
    """
    fill = fill_percent + random.uniform(1.0, 8.0)
    if fill > 95.0:
        fill = random.uniform(2.0, 15.0)
    battery = max(0.0, battery_percent - random.uniform(0.1, 0.8))
    return round(min(100.0, fill), 1), round(battery, 1)


def doc_bang_khoa(duong_dan: str) -> dict[str, str]:
    """Đọc file JSON {mã thùng: khoá thô}. Không có file thì trả về bảng rỗng.

    File hỏng thì báo bằng tiếng Việt rồi thoát — chạy tiếp với bảng rỗng nghĩa
    là im lặng rơi về khoá chung, đúng thứ gói này sinh ra để bỏ.
    """
    if not duong_dan:
        return {}
    duong = Path(duong_dan)
    if not duong.exists():
        print(f"Không thấy file khoá {duong_dan}.")
        sys.exit(1)
    try:
        du_lieu = json.loads(duong.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"File khoá {duong_dan} không phải JSON hợp lệ — {exc}.")
        sys.exit(1)
    if not isinstance(du_lieu, dict):
        print(f"File khoá {duong_dan} phải là một đối tượng JSON {{mã thùng: khoá}}.")
        sys.exit(1)
    return {str(k): str(v) for k, v in du_lieu.items()}


def khoa_cho_thung(bang_khoa: dict[str, str], code: str, khoa_chung: str) -> str:
    """Chọn khoá gửi cho một thùng: khoá riêng nếu có, không thì khoá chung.

    Thứ tự này bám đúng luật của endpoint ingest — thùng đã cấp khoá riêng thì
    khoá chung không mở được nữa. Vì vậy phải ưu tiên khoá RIÊNG trước, khoá
    chung chỉ là phương án rớt lại khi thùng chưa được cấp.
    """
    return bang_khoa.get(code, "") or khoa_chung


def _doc_loi_vi(exc: urllib.error.HTTPError) -> str:
    """Rút ``message_vi`` từ khuôn lỗi ``{error:{message_vi}}`` của API."""
    try:
        du_lieu = json.loads(exc.read().decode("utf-8"))
        return str(du_lieu["error"]["message_vi"])
    except (ValueError, KeyError):
        return "API trả lỗi không đọc được."


def _gui_reading(api: str, code: str, key: str, fill_percent: float, battery_percent: float) -> str:
    """Gửi một reading qua POST; trả câu tóm tắt kết quả để in ra.

    Lỗi mạng hay HTTP đều được nuốt thành câu tiếng Việt — một thùng hỏng
    không được làm dừng cả phiên mô phỏng.
    """
    payload = json.dumps(
        {"fill_percent": fill_percent, "battery_percent": battery_percent, "source": "simulator"}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{api}/api/v1/bins/{code}/readings",
        data=payload,
        headers={"Content-Type": "application/json", "X-Device-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            du_lieu: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return f"OK — fill={du_lieu['fill_percent']}%, pin={du_lieu['battery_percent']}%, trạng thái={du_lieu['status']}"
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code} — {_doc_loi_vi(exc)}"
    except urllib.error.URLError as exc:
        return f"Lỗi mạng — {exc.reason}"
    except TimeoutError:
        # `urlopen(timeout=…)` quá hạn lúc ĐỌC thì ném thẳng TimeoutError, KHÔNG
        # bọc trong URLError — thiếu nhánh này là một lần mạng chậm giết cả phiên.
        return "Quá hạn — thùng không trả lời trong 10 giây, bỏ qua bước này."


def main() -> None:
    # Console Windows mặc định là cp1252, không in được tiếng Việt có dấu.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Mô phỏng thiết bị thùng thu gom — thay phần cứng chưa có gửi reading"
    )
    parser.add_argument("--api", default="http://localhost:8000", help="địa chỉ gốc của API (mặc định http://localhost:8000)")
    parser.add_argument(
        "--key",
        default=os.environ.get("BIN_DEVICE_KEY", ""),
        help="khoá thiết bị (mặc định đọc từ biến môi trường BIN_DEVICE_KEY)",
    )
    parser.add_argument(
        "--key-file",
        default=os.environ.get("BIN_KEY_FILE", ""),
        help="file JSON {mã thùng: khoá riêng} do scripts/cap_khoa_thung.py --ghi-file sinh ra",
    )
    parser.add_argument("--steps", type=int, default=10, help="số bước mô phỏng (mặc định 10)")
    parser.add_argument("--interval", type=float, default=5, help="số giây giữa hai bước (mặc định 5)")
    parser.add_argument(
        "--bins",
        default="",
        help="danh sách mã thùng cách nhau bằng dấu phẩy (mặc định: mọi thùng demo đã seed)",
    )
    parser.add_argument("--dry-run", action="store_true", help="chỉ in những gì sẽ gửi, không gửi thật")
    args = parser.parse_args()

    codes = [c.strip() for c in args.bins.split(",") if c.strip()] if args.bins else [b["code"] for b in SEED_BINS]
    if not codes:
        print("Không có mã thùng nào để mô phỏng.")
        sys.exit(1)
    bang_khoa = doc_bang_khoa(args.key_file)
    if not args.key and not bang_khoa and not args.dry_run:
        print(
            "Thiếu khoá thiết bị — đặt qua --key, qua biến môi trường BIN_DEVICE_KEY,"
            " hoặc qua --key-file (xem scripts/cap_khoa_thung.py --ghi-file)."
        )
        sys.exit(1)

    trang_thai = {b["code"]: (b["fill_percent"], b["battery_percent"]) for b in SEED_BINS}
    for code in codes:
        trang_thai.setdefault(code, (50.0, 70.0))

    # Cố tình để một thùng im lặng suốt phiên — đường "mất kết nối" chỉ hiện
    # trên màn hình khi có một thùng thật sự không gửi gì.
    code_cam = codes[-1]
    hoat_dong = codes[:-1]

    for buoc in range(1, args.steps + 1):
        print(f"[Bước {buoc}/{args.steps}]")
        for code in hoat_dong:
            fill, battery = trang_thai[code]
            fill_moi, battery_moi = buoc_tiep_theo(fill, battery)
            trang_thai[code] = (fill_moi, battery_moi)
            if args.dry_run:
                print(f"  {code}: sẽ gửi fill={fill_moi}%, pin={battery_moi}% (nguồn=simulator)")
            else:
                khoa = khoa_cho_thung(bang_khoa, code, args.key)
                print(f"  {code}: {_gui_reading(args.api, code, khoa, fill_moi, battery_moi)}")
        print(f"  {code_cam}: bỏ im lặng — cố ý không gửi để thấy trạng thái mất kết nối")
        if buoc < args.steps and not args.dry_run:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
