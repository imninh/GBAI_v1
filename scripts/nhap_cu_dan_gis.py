"""Nhập 600 tài khoản cư dân mô phỏng từ workbook GIS (bổ sung ngoài gói).

    python scripts/nhap_cu_dan_gis.py --kiem-tra   # CHỈ ĐỌC, không ghi
    python scripts/nhap_cu_dan_gis.py              # ghi thật

Nguồn: sheet ``RESIDENT_AUTH`` trong
``GreenBin_Hanoi_GIS_Simulation_with_Credentials.xlsx`` — mỗi dòng là một cư dân
MÔ PHỎNG với ``login_phone`` + ``password`` (plaintext, chỉ dùng cho demo).

Ba điều chủ đích:

* **Băm lại bằng PBKDF2** (``hash_password``) từ mật khẩu gốc — KHÔNG dùng cột
  ``password_hash_sha256`` trong file, vì hệ thống xác thực bằng
  ``pbkdf2_sha256`` chứ không phải SHA-256 trần; nhập hash sai kiểu là không ai
  đăng nhập được.
* **``unit_id`` để trống.** 600 cư dân này rải khắp Hà Nội, không thuộc ba toà
  demo S1/S2/S3. Tài khoản đăng nhập được ngay; chỉ là chưa gắn căn hộ.
* **``is_seed=True``** — đây là dữ liệu mô phỏng, UI gắn nhãn demo.

Chạy lại vô hại: tra theo ``phone`` trước, đã có thì bỏ qua, chưa có thì tạo.
Không bao giờ xoá hay đổi mật khẩu tài khoản đã tồn tại.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import openpyxl  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.db.models import User  # noqa: E402
from src.db.session import init_db, session_scope  # noqa: E402
from src.services.security import hash_password  # noqa: E402

GOC_DU_AN = Path(__file__).resolve().parents[1]
WORKBOOK = Path(r"C:\AI20K\GreenBin_Hanoi_GIS_Simulation_with_Credentials.xlsx")
SHEET = "RESIDENT_AUTH"


def _doc_hang(duong_dan: Path) -> list[dict[str, str]]:
    wb = openpyxl.load_workbook(duong_dan, read_only=True, data_only=True)
    ws = wb[SHEET]
    hang = list(ws.iter_rows(values_only=True))
    tieu_de = [str(c).strip() if c is not None else "" for c in hang[0]]
    ket_qua: list[dict[str, str]] = []
    for dong in hang[1:]:
        if dong is None or all(o is None for o in dong):
            continue
        ket_qua.append({tieu_de[i]: ("" if v is None else str(v)) for i, v in enumerate(dong)})
    wb.close()
    return ket_qua


def nhap_cu_dan(session: Session, *, kiem_tra: bool = False) -> dict[str, int | list[str]]:
    cac_hang = _doc_hang(WORKBOOK)
    so_moi = 0
    so_da_co = 0
    so_bo_qua = 0
    ly_do: list[str] = []

    # Lấy TẤT CẢ số điện thoại đang có trong MỘT truy vấn — tra từng dòng bằng
    # 600 round-trip riêng tới Supabase (đặt ở Nhật) quá chậm, dễ bị treo.
    da_ton_tai = set(session.scalars(select(User.phone)).all())

    for hang in cac_hang:
        phone = (hang.get("login_phone") or "").strip()
        matkhau = (hang.get("password") or "").strip()
        ma = (hang.get("resident_id") or "?").strip()
        if not phone or not matkhau:
            so_bo_qua += 1
            ly_do.append(f"{ma}: thiếu login_phone hoặc password")
            continue

        if phone in da_ton_tai:
            so_da_co += 1
            continue
        da_ton_tai.add(phone)

        if not kiem_tra:
            session.add(
                User(
                    phone=phone,
                    email=f"{ma.lower()}@sim.greenbin.vn",
                    full_name=f"Cư dân mô phỏng {ma}",
                    role="resident",
                    password_hash=hash_password(matkhau),
                    unit_id=None,
                )
            )
        so_moi += 1

    if not kiem_tra:
        session.flush()

    tong = len(session.scalars(select(User)).all())
    return {
        "so_dong_doc": len(cac_hang),
        "so_tao_moi": so_moi,
        "so_da_co": so_da_co,
        "so_bo_qua": so_bo_qua,
        "ly_do_bo_qua": ly_do,
        "tong_user": tong,
    }


def _in(bc: dict[str, int | list[str]], *, kiem_tra: bool) -> None:
    print(f"NHẬP CƯ DÂN MÔ PHỎNG — {'SẼ làm (chỉ đọc)' if kiem_tra else 'Đã làm'}")
    print("─" * 30)
    print(f"  Dòng đọc được:        {bc['so_dong_doc']}")
    print(f"  Tài khoản tạo mới:    {bc['so_tao_moi']}")
    print(f"  Đã có (bỏ qua):       {bc['so_da_co']}")
    print(f"  Dòng bỏ qua:          {bc['so_bo_qua']}")
    if bc["ly_do_bo_qua"]:
        for d in bc["ly_do_bo_qua"][:10]:
            print(f"     · {d}")
    print(f"  Tổng user trong CSDL: {bc['tong_user']}")
    if not kiem_tra:
        print("\nTài khoản cư dân MÔ PHỎNG (is_seed=True), chưa gắn căn hộ, đăng nhập bằng SĐT + mật khẩu.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Nhập 600 tài khoản cư dân mô phỏng từ workbook GIS.")
    parser.add_argument("--kiem-tra", action="store_true", help="CHỈ ĐỌC: in ra sẽ làm gì, không ghi một dòng nào")
    args = parser.parse_args()

    init_db()
    with session_scope() as session:
        bc = nhap_cu_dan(session, kiem_tra=args.kiem_tra)
        if args.kiem_tra:
            session.rollback()
    _in(bc, kiem_tra=args.kiem_tra)


if __name__ == "__main__":
    main()
