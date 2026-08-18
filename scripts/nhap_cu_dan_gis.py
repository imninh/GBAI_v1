"""Nhập và cập nhật cư dân mô phỏng từ workbook GIS (gói P56).

    python scripts/nhap_cu_dan_gis.py --kiem-tra   # CHỈ ĐỌC, không ghi
    python scripts/nhap_cu_dan_gis.py              # ghi thật

Nguồn: sheet ``RESIDENT_SIMULATION`` trong
``GreenBin_Hanoi_GIS_Simulation_with_Credentials.xlsx`` — mỗi dòng là một cư dân
MÔ PHỎNG trên phố Hà Nội với ``login_phone`` + ``password`` + địa chỉ + toạ độ.

Đây vừa là **đường nhập ban đầu** (CSDL rỗng → tạo đủ 600 tài khoản), vừa là
**đường khôi phục sau sự cố mất dữ liệu**: ngày 16/08/2026 CSDL production mất
600 tài khoản cư dân và toàn bộ bảng ``media``; chính script này tạo lại từng tài
khoản từ workbook.

Với mỗi dòng workbook có đủ **bốn ngả tường minh**:

* thiếu ``login_phone`` → bỏ qua, ghi lý do (đếm vào ``so_dong_hong``);
* chưa có tài khoản khớp ``login_phone`` → **tạo tài khoản mới** và điền luôn
  ``address`` / ``lat`` / ``lng`` (đếm vào ``so_tao_moi``);
* đã có tài khoản, chưa có ``address`` → chỉ điền ``address`` / ``lat`` / ``lng``
  (đếm vào ``so_cap_nhat_dia_chi``);
* đã có tài khoản, đã có ``address`` → không đụng gì (đếm vào ``so_da_du``).

Chạy lại vô hại: lần thứ hai mọi dòng rơi vào ngả "đã có địa chỉ", không tạo
thêm ai, không ghi đè địa chỉ.

Ba điều chủ đích của nhánh tạo tài khoản:

* **Mật khẩu băm lại bằng ``hash_password``** (PBKDF2-HMAC-SHA256, 200.000 vòng)
  từ cột ``password`` của workbook. ⛔ TUYỆT ĐỐI KHÔNG nhét cột
  ``password_hash_sha256`` của workbook vào ``password_hash`` — hệ thống xác thực
  bằng ``pbkdf2_sha256`` (xem ``src/services/security.py``); nhét hash SHA-256 thô
  vào là 600 người không đăng nhập được mà không có lỗi nào báo ra.
* **``unit_id = None``.** 600 người này là hộ dân lẻ trên phố, không thuộc ba
  toà demo S1/S2/S3. Không đẻ căn hộ giả.
* Model ``User`` **không có trường ``is_seed``** (đã đọc
  ``src/db/models_users.py``) nên không có gì để gắn — bỏ qua, không tự thêm.

``email`` và ``full_name`` sinh từ ``resident_id`` vì workbook không có cột tên
và cột ``email`` là NOT NULL + unique. Đuôi email ``@sim.greenbin.vn`` là dấu
**duy nhất** đánh dấu dữ liệu mô phỏng — model ``User`` không có ``is_seed``, nên
nhánh tạo mới PHẢI dùng đúng đuôi này còn nhánh cập nhật địa chỉ KHÔNG được sửa
email của tài khoản đã có. ``--kiem-tra`` in đủ bốn con số + tổng user, tối đa 10
lý do dòng hỏng, và **không ghi một dòng nào**.
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
SHEET = "RESIDENT_SIMULATION"

# Tên tối đa in cho danh sách lý do dòng hỏng.
_MAX_LY_DO = 10


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


def _doc_toa_do(hang: dict[str, str]) -> tuple[float | None, float | None]:
    """Đọc ``latitude`` / ``longitude`` của một dòng; thiếu/không đọc được → None."""
    try:
        lat = float(hang.get("latitude") or "")
    except ValueError:
        lat = None
    try:
        lng = float(hang.get("longitude") or "")
    except ValueError:
        lng = None
    return lat, lng


def _tao_user(hang: dict[str, str], phone: str) -> User:
    """Dựng tài khoản cư dân mới từ một dòng workbook (nhánh ``so_tao_moi``).

    Mật khẩu băm lại bằng PBKDF2 từ cột ``password`` — KHÔNG dùng cột
    ``password_hash_sha256``. ``unit_id`` để None: hộ dân lẻ trên phố, không
    thuộc toà demo nào, nơi ở nằm ở ``address`` / ``lat`` / ``lng``.
    """
    ma = (hang.get("resident_id") or "").strip()
    email_goc = ma.lower() if ma else phone
    dia_chi = (hang.get("home_address_simulated") or "").strip()
    lat, lng = _doc_toa_do(hang)
    # Đuôi @sim.greenbin.vn là dấu DUY NHẤT đánh dấu đây là dữ liệu mô phỏng:
    # model `User` không có trường `is_seed` (đã đọc src/db/models_users.py), và
    # đo trên CSDL thật ngày 18/08: 600 tài khoản đang dùng @sim.greenbin.vn.
    # Script là đường khôi phục sau sự cố mất dữ liệu — nếu dựng lại với đuôi
    # khác thì lần khôi phục sau mất dấu mô phỏng và CSDL lẫn lộn hai đuôi cho
    # cùng một nhóm người. Chỉ áp cho nhánh TẠO MỚI; nhánh cập nhật địa chỉ không
    # được sửa email của tài khoản đã tồn tại.
    email = f"{email_goc}@sim.greenbin.vn"
    return User(
        email=email,
        phone=phone,
        full_name=f"Cư dân {ma or phone}",
        role="resident",
        password_hash=hash_password(hang.get("password") or ""),
        unit_id=None,
        address=dia_chi,
        lat=lat,
        lng=lng,
    )


def nhap_va_cap_nhat_cu_dan(
    session: Session,
    *,
    kiem_tra: bool = False,
    duong_dan: Path | None = None,
) -> dict[str, int | list[str]]:
    """Nhập và cập nhật cư dân mô phỏng từ workbook GIS vào session.

    Args:
        session: phiên CSDL. Trong chế độ thật phải có người gọi commit.
        kiem_tra: ``True`` thì CHỈ đếm những gì sẽ làm, không thêm/sửa gì.
        duong_dan: đường dẫn workbook; mặc định là file bàn giao ngoài repo.

    Returns:
        Báo cáo: số dòng đọc · dòng hỏng kèm lý do · tài khoản tạo mới ·
        địa chỉ cập nhật · đã có địa chỉ (bỏ qua) · tổng user trong CSDL.
    """
    duong = duong_dan or WORKBOOK
    cac_hang = _doc_hang(duong)
    so_dong_hong = 0
    so_tao_moi = 0
    so_cap_nhat_dia_chi = 0
    so_da_du = 0
    ly_do_dong_hong: list[str] = []

    # Lấy TẤT CẢ user trong MỘT truy vấn rồi tra trong bộ nhớ — tra từng dòng
    # bằng 600 round-trip riêng tới Supabase (đặt ở Nhật) quá chậm, dễ bị treo.
    cac_nguoi = {u.phone: u for u in session.scalars(select(User)).all()}

    for hang in cac_hang:
        phone = (hang.get("login_phone") or "").strip()
        ma = (hang.get("resident_id") or "?").strip()

        if not phone:
            so_dong_hong += 1
            ly_do_dong_hong.append(f"{ma}: thiếu login_phone")
            continue

        nguoi = cac_nguoi.get(phone)
        if nguoi is None:
            # Chưa có tài khoản khớp → TẠO mới, điền luôn địa chỉ + toạ độ.
            if not kiem_tra:
                session.add(_tao_user(hang, phone))
            so_tao_moi += 1
            continue

        if nguoi.address:
            # Đã có tài khoản và đã có địa chỉ → không đụng gì.
            so_da_du += 1
            continue

        # Đã có tài khoản, chưa có địa chỉ → chỉ điền địa chỉ + toạ độ.
        if not kiem_tra:
            nguoi.address = (hang.get("home_address_simulated") or "").strip()
            nguoi.lat, nguoi.lng = _doc_toa_do(hang)
        so_cap_nhat_dia_chi += 1

    if not kiem_tra:
        session.flush()

    tong_user = len(session.scalars(select(User)).all())
    return {
        "so_dong_doc": len(cac_hang),
        "so_dong_hong": so_dong_hong,
        "so_tao_moi": so_tao_moi,
        "so_cap_nhat_dia_chi": so_cap_nhat_dia_chi,
        "so_da_du": so_da_du,
        "ly_do_dong_hong": ly_do_dong_hong,
        "tong_user": tong_user,
    }


def _in(bc: dict[str, int | list[str]], *, kiem_tra: bool) -> None:
    dau = "SẼ làm (chỉ đọc)" if kiem_tra else "Đã làm"
    print(f"\nNHẬP VÀ CẬP NHẬT CƯ DÂN MÔ PHỎNG (GIS) — {dau}")
    print("─" * 46)
    print(f"  Dòng đọc được:                {bc['so_dong_doc']}")
    print(f"  Dòng hỏng (thiếu login_phone): {bc['so_dong_hong']}")
    print(f"  Tạo tài khoản mới:            {bc['so_tao_moi']}")
    print(f"  Cập nhật địa chỉ:             {bc['so_cap_nhat_dia_chi']}")
    print(f"  Đã có địa chỉ (bỏ qua):       {bc['so_da_du']}")
    cac_ly_do = bc["ly_do_dong_hong"]
    if cac_ly_do:
        print(f"  Lý do dòng hỏng (tối đa {_MAX_LY_DO}):")
        for ly_do in cac_ly_do[:_MAX_LY_DO]:
            print(f"    · {ly_do}")
    print(f"  Tổng user trong CSDL:         {bc['tong_user']}")
    if not kiem_tra:
        print("\nĐã tạo/cập nhật tài khoản cư dân mô phỏng; unit_id để None (hộ dân lẻ trên phố).")


def main() -> None:
    # Console Windows mặc định là cp1252, không in được tiếng Việt có dấu.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description=(
            "Nhập và cập nhật cư dân mô phỏng từ workbook GIS: chưa có tài khoản "
            "theo login_phone thì tạo mới (mật khẩu băm PBKDF2), có rồi thì điền "
            "địa chỉ + toạ độ. Vừa là đường nhập ban đầu vừa là đường khôi phục "
            "sau sự cố mất dữ liệu."
        )
    )
    parser.add_argument("--kiem-tra", action="store_true", help="CHỈ ĐỌC: in ra sẽ làm gì, không ghi một dòng nào")
    args = parser.parse_args()

    init_db()
    with session_scope() as session:
        bc = nhap_va_cap_nhat_cu_dan(session, kiem_tra=args.kiem_tra)
        if args.kiem_tra:
            session.rollback()
    _in(bc, kiem_tra=args.kiem_tra)


if __name__ == "__main__":
    main()
