"""Nhập và cập nhật cư dân mô phỏng từ workbook GIS (gói P56, cập nhật P62).

    python scripts/nhap_cu_dan_gis.py --kiem-tra   # CHỈ ĐỌC, không ghi
    python scripts/nhap_cu_dan_gis.py              # ghi thật

Nguồn: sheet ``RESIDENT_SIMULATION`` trong
``GreenBin_Hanoi_GIS_Simulation_with_Credentials.xlsx`` — mỗi dòng là một cư dân
MÔ PHỎNG với ``login_phone`` + ``password`` + ``resident_id``.

**Gói P62 — không còn nhập địa chỉ phố.** 600 địa chỉ trong workbook là dữ liệu
bịa (``data_status: SYNTHETIC``): 33,7% số nhà lặp, 0% có Phường/Quận, chỉ 38 tên
đường cho 600 người. Sản phẩm là hệ cho toà chung cư, và 44 toà trong CSDL là
chung cư thật (43/44 có thùng ngay tại chỗ). Nên giờ **rải đều cư dân vào 44
toà**: cư dân thứ ``i`` (theo ``resident_id`` đã sắp) vào toà thứ
``i % số_toà``. 600 ÷ 44 ≈ 14 hộ/toà. Cách này tất định — chạy lại ra y hệt.

``users.building_id`` ghi thẳng toà; ``address``/``lat``/``lng`` chép từ toà đó.
``unit_id`` vẫn để ``None`` — không đẻ căn hộ giả.

Đây vừa là **đường nhập ban đầu** (CSDL rỗng → tạo đủ 600 tài khoản), vừa là
**đường khôi phục sau sự cố mất dữ liệu**: ngày 16/08/2026 CSDL production mất
600 tài khoản cư dân và toàn bộ bảng ``media``; chính script này tạo lại từng tài
khoản từ workbook.

Với mỗi dòng workbook có đủ **bốn ngả tường minh**:

* thiếu ``login_phone`` → bỏ qua, ghi lý do (đếm vào ``so_dong_hong``);
* chưa có tài khoản khớp ``login_phone`` → **tạo tài khoản mới** và gán vào toà
  (đếm vào ``so_tao_moi``);
* đã có tài khoản, chưa có địa chỉ → chỉ điền toà + địa chỉ (đếm vào
  ``so_cap_nhat_dia_chi``);
* đã có tài khoản, đã có địa chỉ → không đụng gì (đếm vào ``so_da_du``).

Chạy lại vô hại: lần thứ hai mọi dòng rơi vào ngả "đã có địa chỉ", không tạo
thêm ai, không ghi đè địa chỉ, không ai bị đổi toà.

Ba điều chủ đích của nhánh tạo tài khoản:

* **Mật khẩu băm lại bằng ``hash_password``** (PBKDF2-HMAC-SHA256, 200.000 vòng)
  từ cột ``password`` của workbook. ⛔ TUYỆT ĐỐI KHÔNG nhét cột
  ``password_hash_sha256`` của workbook vào ``password_hash`` — hệ thống xác thực
  bằng ``pbkdf2_sha256`` (xem ``src/services/security.py``); nhét hash SHA-256 thô
  vào là 600 người không đăng nhập được mà không có lỗi nào báo ra.
* **``unit_id = None``.** Không đẻ căn hộ giả; nơi ở nằm ở ``building_id`` +
  ``address``/``lat``/``lng``.
* Model ``User`` **không có trường ``is_seed``** (đã đọc
  ``src/db/models_users.py``) nên không có gì để gắn — bỏ qua, không tự thêm.

``email`` và ``full_name`` sinh từ ``resident_id`` vì workbook không có cột tên
và cột ``email`` là NOT NULL + unique. Đuôi email ``@sim.greenbin.vn`` là dấu
**duy nhất** đánh dấu dữ liệu mô phỏng — model ``User`` không có ``is_seed``, nên
nhánh tạo mới PHẢI dùng đúng đuôi này còn nhánh cập nhật địa chỉ KHÔNG được sửa
email của tài khoản đã có. ``--kiem-tra`` in đủ bốn con số + số toà + tổng user,
tối đa 10 lý do dòng hỏng, và **không ghi một dòng nào**.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import openpyxl  # noqa: E402
from sqlalchemy import Engine, inspect, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.db.models import Building, User  # noqa: E402
from src.db.schema_patch import COT_CAN_VA  # noqa: E402
from src.db.session import get_engine, init_db, session_scope  # noqa: E402
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


def _doc_toa_nhan_dia_chi(session: Session) -> list[Building]:
    """Toàn bộ toà có toạ độ, sắp theo ``code`` để kết quả rải LẶP LẠI ĐƯỢC.

    Sắp theo ``code`` (chuỗi) chứ không theo ``id`` (số tự tăng) — id có thể khác
    giữa các lần dựng CSDL, còn ``code`` ổn định. Đây là nền cho việc rải tất
    định: cùng một CSDL, chạy mấy lần cũng ra cùng một bản gán.
    """
    cac_toa = session.scalars(
        select(Building).where(Building.lat.is_not(None), Building.lng.is_not(None))
    ).all()
    return sorted(cac_toa, key=lambda t: t.code)


def _toa_cua_chi_so(chỉ_so: int, cac_toa: list[Building]) -> Building:
    """Toà chịu cư dân thứ ``chỉ_so`` — rải đều theo vòng: ``i % số_toà``."""
    return cac_toa[chỉ_so % len(cac_toa)]


def _tao_user(hang: dict[str, str], phone: str, toa: Building) -> User:
    """Dựng tài khoản cư dân mới từ một dòng workbook (nhánh ``so_tao_moi``).

    Mật khẩu băm lại bằng PBKDF2 từ cột ``password`` — KHÔNG dùng cột
    ``password_hash_sha256``. ``building_id`` gắn thẳng toà; ``unit_id`` để None:
    không đẻ căn hộ giả. ``address``/``lat``/``lng`` chép từ toà (P62 — bỏ địa chỉ
    phố bịa của workbook).
    """
    ma = (hang.get("resident_id") or "").strip()
    email_goc = ma.lower() if ma else phone
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
        building_id=toa.id,
        address=toa.address,
        lat=toa.lat,
        lng=toa.lng,
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
        địa chỉ cập nhật · đã có địa chỉ (bỏ qua) · số toà dùng · số hộ mỗi toà ·
        tổng user trong CSDL.
    """
    duong = duong_dan or WORKBOOK
    cac_hang = sorted(_doc_hang(duong), key=lambda h: (h.get("resident_id") or ""))
    cac_toa = _doc_toa_nhan_dia_chi(session)
    so_toa = len(cac_toa)
    so_dong_hong = 0
    so_tao_moi = 0
    so_cap_nhat_dia_chi = 0
    so_da_du = 0
    ly_do_dong_hong: list[str] = []

    # Lấy TẤT CẢ user trong MỘT truy vấn rồi tra trong bộ nhớ — tra từng dòng
    # bằng 600 round-trip riêng tới Supabase (đặt ở Nhật) quá chậm, dễ bị treo.
    cac_nguoi = {u.phone: u for u in session.scalars(select(User)).all()}

    # Toà nào nhận cư dân thứ i — tính MỘT lần cho cả nhánh tạo lẫn nhánh cập nhật
    # để cư dân thứ i luôn về cùng một toà giữa các lần chạy. Chỉ dòng có
    # login_phone mới được tính thứ tự (dòng hỏng không phải một cư dân).
    chi_so = 0
    for hang in cac_hang:
        phone = (hang.get("login_phone") or "").strip()
        ma = (hang.get("resident_id") or "?").strip()

        if not phone:
            so_dong_hong += 1
            ly_do_dong_hong.append(f"{ma}: thiếu login_phone")
            continue

        toa = _toa_cua_chi_so(chi_so, cac_toa) if so_toa else None
        chi_so += 1

        nguoi = cac_nguoi.get(phone)
        if nguoi is None:
            # Chưa có tài khoản khớp → TẠO mới, gán thẳng vào toà.
            if not kiem_tra and toa is not None:
                session.add(_tao_user(hang, phone, toa))
            so_tao_moi += 1
            continue

        if nguoi.address:
            # Đã có tài khoản và đã có địa chỉ → không đụng gì.
            so_da_du += 1
            continue

        # Đã có tài khoản, chưa có địa chỉ → chỉ điền toà + địa chỉ.
        if not kiem_tra and toa is not None:
            nguoi.building_id = toa.id
            nguoi.address = toa.address
            nguoi.lat = toa.lat
            nguoi.lng = toa.lng
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
        "so_toa_dung": so_toa,
        "so_ho_moi_toa": round(len(cac_hang) / so_toa, 1) if so_toa else 0,
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
    print(f"  Toà dùng:                     {bc['so_toa_dung']}")
    print(f"  Hộ mỗi toà (bình quân):       {bc['so_ho_moi_toa']}")
    cac_ly_do = bc["ly_do_dong_hong"]
    if cac_ly_do:
        print(f"  Lý do dòng hỏng (tối đa {_MAX_LY_DO}):")
        for ly_do in cac_ly_do[:_MAX_LY_DO]:
            print(f"    · {ly_do}")
    print(f"  Tổng user trong CSDL:         {bc['tong_user']}")
    if not kiem_tra:
        print("\nĐã tạo/cập nhật tài khoản cư dân mô phỏng; gán vào toà, unit_id để None (không đẻ căn hộ giả).")


def _cot_con_thieu(engine: Engine) -> list[str]:
    """Liệt kê cột còn thiếu theo ``COT_CAN_VA`` — CHỈ ĐỌC, không ALTER.

    Dùng cho ``--kiem-tra``: báo cáo chạy khô phải nói được "chạy thật sẽ thêm
    các cột này" mà KHÔNG được chạy ``va_cot_thieu`` (một 'chạy khô' mà đổi lược
    đồ là lỗi an toàn — chính nó từng vá 6 cột lên CSDL production ngày 18/08).
    """
    thieu: list[str] = []
    for bang, cot, _ in COT_CAN_VA:
        soi = inspect(engine)
        if bang not in soi.get_table_names():
            continue
        if cot not in {c["name"] for c in soi.get_columns(bang)}:
            thieu.append(f"{bang}.{cot}")
    return thieu


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

    if args.kiem_tra:
        _kiem_tra()
        return

    init_db()
    with session_scope() as session:
        bc = nhap_va_cap_nhat_cu_dan(session, kiem_tra=args.kiem_tra)
        if args.kiem_tra:
            session.rollback()
    _in(bc, kiem_tra=args.kiem_tra)


def _kiem_tra() -> None:
    """Chạy khô thật sự CHỈ ĐỌC — không ``init_db()``, không vá lược đồ.

    ``init_db()`` chạy ``va_cot_thieu()`` → ``ALTER TABLE … ADD COLUMN``; gọi nó
    trong nhánh khô là một "chạy khô" đổi lược đồ. Thay bằng: dò cột thiếu qua
    inspector (chỉ đọc), in ra dự toán, rồi mới đếm dữ liệu trên session.
    """
    engine = get_engine()
    thieu = _cot_con_thieu(engine)
    if thieu:
        print("Chạy thật sẽ thêm các cột còn thiếu này:")
        for cot in thieu:
            print(f"  · {cot}")

    try:
        with session_scope() as session:
            bc = nhap_va_cap_nhat_cu_dan(session, kiem_tra=True)
            session.rollback()
    except Exception as exc:
        # Thiếu cột làm query chết — báo gọn, không ghi gì.
        print(f"\nKHÔNG đọc được dữ liệu vì thiếu cột — dừng ở đây: {exc}")
        return
    _in(bc, kiem_tra=True)


if __name__ == "__main__":
    main()
