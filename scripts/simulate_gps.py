"""Script giả lập xe gom rác di chuyển và phát GPS thời gian thực.

Dùng để kiểm tra luồng OSRM Match API + WebSocket Live Tracking trực tiếp trên web:
1. Mở web http://localhost:3000 -> Đăng nhập tài khoản Quản lý (manager@demo.vn).
2. Vào tab Điều phối / Tuyến gom -> Mở xem một tuyến xe.
3. Chạy script này:
   .\\venv\\Scripts\\python.exe scripts/simulate_gps.py
4. Quan sát trên bản đồ: Icon xe tải 🚛 sẽ xuất hiện, xoay theo góc hướng đi,
   hiển thị radar sóng xung quanh và cập nhật tốc độ realtime qua WebSocket!
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
import requests

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Đảm bảo import được src khi chạy từ bất kỳ thư mục nào
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from src.db.models import PickupRoute, User
from src.db.session import get_session_factory
from src.services import auth, duong_di_that


def _tinh_heading(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Tính góc hướng đi (bearing) từ điểm 1 đến điểm 2 theo độ (0 - 360)."""
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    initial_bearing = math.atan2(x, y)
    bearing_deg = (math.degrees(initial_bearing) + 360) % 360
    return round(bearing_deg, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Giả lập GPS xe thu gom rác thời gian thực")
    parser.add_argument("--route-id", type=int, default=None, help="ID của tuyến cần giả lập")
    parser.add_argument("--speed", type=float, default=30.0, help="Tốc độ xe giả lập (km/h)")
    parser.add_argument("--interval", type=float, default=2.0, help="Khoảng thời gian giữa các gói tin GPS (giây)")
    parser.add_argument("--host", type=str, default="http://localhost:8000", help="Địa chỉ backend API")
    args = parser.parse_args()

    session = get_session_factory()()
    try:
        # Lấy hoặc tạo token xác thực cho nhân viên lái xe
        cleaner = session.query(User).filter(User.role == "cleaner").first()
        if not cleaner:
            cleaner = session.query(User).first()

        if not cleaner:
            print("❌ Không tìm thấy người dùng nào trong CSDL để xác thực!", flush=True)
            sys.exit(1)

        token = auth.create_token(cleaner)
        headers = {"Authorization": f"Bearer {token}"}

        if args.route_id:
            routes = [session.get(PickupRoute, args.route_id)]
            routes = [r for r in routes if r]
        else:
            routes = session.query(PickupRoute).all()

        if not routes:
            print("❌ Không tìm thấy tuyến nào trong CSDL! Hãy tạo tuyến trên web hoặc chạy seed trước.", flush=True)
            sys.exit(1)

        route_ids = [r.id for r in routes]
        print(f"[XE TAI] Dang gia lap GPS cho cac tuyen: {route_ids}", flush=True)

        # Lấy toạ độ các điểm dừng thực tế của tuyến
        actual_stops: list[tuple[float, float]] = []
        for r in routes:
            for stop in sorted(r.stops, key=lambda s: s.seq):
                if stop.stop_kind == "bin" and stop.thung and stop.thung.lat and stop.thung.lng:
                    actual_stops.append((stop.thung.lat, stop.thung.lng))
                elif stop.stop_kind == "request" and stop.yeu_cau and stop.yeu_cau.unit and stop.yeu_cau.unit.building:
                    b = stop.yeu_cau.unit.building
                    if b.lat and b.lng:
                        actual_stops.append((b.lat, b.lng))

        # Khử trùng lặp
        unique_stops = []
        for p in actual_stops:
            if not unique_stops or unique_stops[-1] != p:
                unique_stops.append(p)

        if len(unique_stops) < 2:
            unique_stops = [
                (21.0271, 105.8519),  # Toà S1
                (21.0284, 105.8531),  # Toà S2
                (21.0303, 105.8554),  # Toà S3
                (21.0278, 105.8525),  # Cổng dự án
            ]

        # Sinh chuỗi toạ độ nội suy mượt mà qua các điểm dừng để xe chạy liên tục trên bản đồ
        trajectory: list[tuple[float, float]] = []
        for i in range(len(unique_stops)):
            p1 = unique_stops[i]
            p2 = unique_stops[(i + 1) % len(unique_stops)]
            steps = 8
            for s in range(steps):
                frac = s / steps
                lat = p1[0] + (p2[0] - p1[0]) * frac
                lng = p1[1] + (p2[1] - p1[1]) * frac
                trajectory.append((round(lat, 6), round(lng, 6)))

        print(f"[OK] Da tao lo trinh noi suy qua cac toa nha S1, S2, S3 ({len(trajectory)} diem toa do).", flush=True)

    finally:
        session.close()

    print(f"[GPS] Bat dau phat GPS len {args.host}/api/v1/tracking/gps cho tuyen {route_ids}...", flush=True)

    speed_mps = round(args.speed / 3.6, 1)

    idx = 0
    total_pts = len(trajectory)

    while True:
        p_current = trajectory[idx]
        p_next = trajectory[(idx + 1) % total_pts]

        heading = _tinh_heading(p_current, p_next)

        # Thêm một chút độ lệch ngẫu nhiên (jitter) nhỏ (~5m) để kiểm tra OSRM Match API snap to road
        jitter_lat = p_current[0] + 0.00003 * math.sin(idx)
        jitter_lng = p_current[1] + 0.00003 * math.cos(idx)

        for rid in route_ids:
            payload = {
                "route_id": rid,
                "lat": round(jitter_lat, 6),
                "lng": round(jitter_lng, 6),
                "accuracy_m": 5.0,
                "speed_mps": speed_mps,
                "heading": heading,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }

            try:
                resp = requests.post(f"{args.host}/api/v1/tracking/gps", json=payload, headers=headers, timeout=5)
                if resp.status_code == 200 and rid == route_ids[0]:
                    data = resp.json()
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] [GPS] Tuyen {route_ids} | Diem {idx + 1}/{total_pts} -> "
                        f"Raw: ({payload['lat']:.5f}, {payload['lng']:.5f}) | "
                        f"Snapped: ({data.get('lat', 0):.5f}, {data.get('lng', 0):.5f}) | "
                        f"Huong: {heading:5.1f} deg | Toc do: {args.speed} km/h",
                        flush=True,
                    )
            except Exception as e:
                print(f"[WARN] Loi ket noi backend: {e}", flush=True)

        idx = (idx + 1) % total_pts
        time.sleep(args.interval)


if __name__ == "__main__":
    main()




