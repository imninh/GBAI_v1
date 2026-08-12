"""Nhập bộ dữ liệu GIS Hà Nội — 60 vị trí thùng ĐỀ XUẤT (gói P30).

    python scripts/nhap_gis_hanoi.py             # nhập thùng (mặc định)
    python scripts/nhap_gis_hanoi.py --kiem-tra  # CHỈ ĐỌC: in ra sẽ làm gì, không ghi

Mọi dòng thùng trong ``data/samples/gis_hanoi_thung.csv`` đều mang
``deployment_status = PROPOSED`` và ``coordinate_confidence = MEDIUM`` — vị trí
đề xuất ước lượng theo POI công khai, CHƯA khảo sát thực địa. Vì vậy 60 thùng
này được gắn cờ **``is_seed=True``**: chúng là dữ liệu mô phỏng, và UI hiện nhãn
"dữ liệu demo mô phỏng" ở mọi nơi chúng xuất hiện. Gắn ``False`` là trình bày 60
vị trí đề xuất như thể hạ tầng đang vận hành — cái nhãn đó KHÔNG được tắt.

Bốn điều chủ đích KHÔNG làm:

* **Không đụng ``BIN-01``…``BIN-10``.** Dữ liệu demo cũ dùng mã HAI chữ số, bộ
  GIS dùng BA chữ số (``BIN-001``…``BIN-060``) nên không trùng — nhưng đừng ai
  "dọn cho gọn" sau này.
* **Không điền ``category_codes``** — bộ dữ liệu không nói thùng nhận nhóm rác
  nào, bịa ra là bịa số. TODO: khi có bản đồ nhóm rác thật thì điền ở đây.
* **Không cấp khoá thiết bị, không sinh ``BinReading`` giả** — thùng chưa tồn
  tại ngoài đường thì không có thiết bị để báo về.
* **Không tạo user giả** từ file cư dân — gói này cố ý chỉ nhập thùng.

Chạy lại vô hại: tra theo ``code`` trước, đã có thì cập nhật, chưa có thì tạo.
Không bao giờ xoá thùng nào.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.db.models import Bin  # noqa: E402
from src.db.session import init_db, session_scope  # noqa: E402

GOC_DU_AN = Path(__file__).resolve().parents[1]
THUNG_CSV = GOC_DU_AN / "data" / "samples" / "gis_hanoi_thung.csv"


def nhap_thung(
    session: Session,
    *,
    kiem_tra: bool = False,
    duong_dan_csv: Path | None = None,
) -> dict[str, int | list[str]]:
    """Nhập 60 thùng GIS vào session, cập nhật nếu đã có.

    Args:
        kiem_tra: ``True`` thì CHỈ đếm những gì sẽ làm, không thêm/sửa gì.
        duong_dan_csv: đường dẫn file CSV; mặc định là file bàn giao trong repo.

    Returns:
        Báo cáo: số dòng đọc · số thùng tạo mới · số thùng cập nhật · số dòng
        bỏ qua kèm lý do · tổng số thùng trong CSDL sau khi nhập.
    """
    duong = duong_dan_csv or THUNG_CSV
    with duong.open(encoding="utf-8", newline="") as tay_cam:
        cac_hang = list(csv.DictReader(tay_cam))

    so_moi = 0
    so_cap_nhat = 0
    so_bo_qua = 0
    ly_do_bo_qua: list[str] = []

    for hang in cac_hang:
        try:
            lat = float(hang["latitude"])
            lng = float(hang["longitude"])
        except (TypeError, ValueError):
            so_bo_qua += 1
            ly_do_bo_qua.append(f"{hang.get('bin_id', '?')}: thiếu/không đọc được toạ độ")
            continue

        thung = session.scalar(select(Bin).where(Bin.code == hang["bin_id"]))
        if thung is None:
            if not kiem_tra:
                session.add(
                    Bin(
                        code=hang["bin_id"],
                        name=hang["anchor_name"],
                        address=hang["address_anchor"],
                        area_name=hang["legacy_area"],
                        lat=lat,
                        lng=lng,
                        site_type=hang["site_type"],
                        priority=hang["priority"],
                        capacity_liters=float(hang["suggested_capacity_l"]),
                        deployment_status=hang["deployment_status"],
                        coordinate_confidence=hang["coordinate_confidence"],
                        # TODO: category_codes để rỗng — bộ dữ liệu không nói
                        # thùng nhận nhóm rác nào.
                        is_active=True,
                        is_seed=True,
                    )
                )
            so_moi += 1
        else:
            if not kiem_tra:
                thung.name = hang["anchor_name"]
                thung.address = hang["address_anchor"]
                thung.area_name = hang["legacy_area"]
                thung.lat = lat
                thung.lng = lng
                thung.site_type = hang["site_type"]
                thung.priority = hang["priority"]
                thung.capacity_liters = float(hang["suggested_capacity_l"])
                thung.deployment_status = hang["deployment_status"]
                thung.coordinate_confidence = hang["coordinate_confidence"]
                thung.is_active = True
                thung.is_seed = True
            so_cap_nhat += 1

    if not kiem_tra:
        session.flush()

    tong_thung = len(session.scalars(select(Bin)).all())
    return {
        "so_dong_doc": len(cac_hang),
        "so_thung_moi": so_moi,
        "so_thung_cap_nhat": so_cap_nhat,
        "so_bo_qua": so_bo_qua,
        "ly_do_bo_qua": ly_do_bo_qua,
        "tong_thung": tong_thung,
    }


def _in_bao_cao(ket_qua: dict[str, int | list[str]], *, kiem_tra: bool) -> None:
    dau = "SẼ làm (chỉ đọc)" if kiem_tra else "Đã làm"
    print(f"\nNHẬP DỮ LIỆU GIS HÀ NỘI — {dau}")
    print("──────────────────────────────")
    print(f"  Dòng đọc được:        {ket_qua['so_dong_doc']}")
    print(f"  Thùng tạo mới:        {ket_qua['so_thung_moi']}")
    print(f"  Thùng cập nhật:       {ket_qua['so_thung_cap_nhat']}")
    so_bo_qua = int(ket_qua["so_bo_qua"])
    if so_bo_qua:
        print(f"  Dòng bỏ qua:          {so_bo_qua}")
        for ly_do in ket_qua["ly_do_bo_qua"]:
            print(f"    · {ly_do}")
    else:
        print("  Dòng bỏ qua:          0")
    print(f"  Tổng số thùng trong CSDL: {ket_qua['tong_thung']}")


def main() -> None:
    # Console Windows mặc định là cp1252, không in được tiếng Việt có dấu.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Nhập 60 vị trí thùng đề xuất từ bộ dữ liệu GIS Hà Nội.")
    parser.add_argument("--kiem-tra", action="store_true", help="CHỈ ĐỌC: in ra sẽ làm gì, không ghi một dòng nào")
    parser.add_argument("--db-url", default="", help="DSN cần dùng. Bỏ trống thì dùng DATABASE_URL của ứng dụng.")
    tham_so = parser.parse_args()

    if tham_so.db_url:
        import os

        from src.db.session import reset_engine

        os.environ["DATABASE_URL"] = tham_so.db_url
        reset_engine()
    init_db()  # create_all + va_cot_thieu — CSDL cũ thiếu cột GIS phải được vá

    with session_scope() as session:
        ket_qua = nhap_thung(session, kiem_tra=tham_so.kiem_tra)
        _in_bao_cao(ket_qua, kiem_tra=tham_so.kiem_tra)
        if not tham_so.kiem_tra:
            print("\n60 thùng đề xuất đều là dữ liệu MÔ PHỎNG (is_seed=True) — UI sẽ gắn nhãn demo cho chúng.")


if __name__ == "__main__":
    main()
