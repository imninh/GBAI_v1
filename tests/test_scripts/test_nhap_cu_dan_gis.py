"""Test script nhập/cập nhật cư dân GIS (gói P56) — không gọi CSDL thật.

Dùng CSDL SQLite trong bộ nhớ (fixture ``db_session`` của ``tests/conftest.py``)
và workbook giả dựng ngay trong test bằng openpyxl — không đọc file ``.xlsx``
thật, không chạy script, không gọi mạng. Test (b) là quan trọng nhất: khẳng định
mật khẩu băm đúng kiểu PBKDF2 nên đăng nhập được bằng mật khẩu gốc của workbook.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.nhap_cu_dan_gis import nhap_va_cap_nhat_cu_dan
from src.db.models import User
from src.services.security import verify_password

TIEU_DE = [
    "resident_id",
    "home_address_simulated",
    "legacy_area",
    "latitude",
    "longitude",
    "nearest_bin_id",
    "distance_to_bin_m",
    "household_size",
    "waste_kg_day_est",
    "data_status",
    "privacy_note",
    "login_phone",
    "password",
    "password_hash_sha256",
    "auth_note",
]

# Giá trị cột ``password_hash_sha256`` của workbook — dùng để khẳng định KHÔNG
# được nhét vào ``password_hash`` (xem test (b)).
_SHA256_MAU = "3af350dd568fdeb23ad4ee3a573f4420c0cc75f5bbb44db162b721a7f71e8da7"


def _hang(
    *,
    resident_id: str = "RES-0001",
    phone: str = "0909000001",
    password: str = "GreenBin@0001",
    dia_chi: str = "165 120 Lê Duẩn, Hà Nội",
    lat: object = 21.025679,
    lng: object = 105.85,
) -> dict[str, object]:
    return {
        "resident_id": resident_id,
        "home_address_simulated": dia_chi,
        "legacy_area": "Đống Đa",
        "latitude": lat,
        "longitude": lng,
        "nearest_bin_id": "",
        "distance_to_bin_m": "",
        "household_size": "",
        "waste_kg_day_est": "",
        "data_status": "",
        "privacy_note": "",
        "login_phone": phone,
        "password": password,
        "password_hash_sha256": _SHA256_MAU,
        "auth_note": "",
    }


def _workbook_gia(tmp_path: Path, cac_hang: list[dict[str, object]]) -> Path:
    duong = tmp_path / "workbook_gia.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RESIDENT_SIMULATION"
    ws.append(TIEU_DE)
    for hang in cac_hang:
        ws.append([hang.get(c, "") for c in TIEU_DE])
    wb.save(duong)
    return duong


def _tim(db_session: Session, phone: str) -> User:
    nguoi = db_session.scalar(select(User).where(User.phone == phone))
    assert nguoi is not None, f"Phải có tài khoản mang số {phone}"
    return nguoi


# --- (a) CSDL rỗng → tạo đủ tài khoản --------------------------------------


def test_csdl_rong_tao_du_tai_khoan(db_session: Session, tmp_path: Path) -> None:
    duong = _workbook_gia(
        tmp_path,
        [_hang(), _hang(resident_id="RES-0002", phone="0909000002", dia_chi="42 Hàng Ngang, Hà Nội")],
    )

    ket_qua = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    assert ket_qua["so_tao_moi"] == 2, ket_qua
    assert ket_qua["so_dong_hong"] == 0
    assert len(db_session.scalars(select(User)).all()) == 2

    nguoi_1 = _tim(db_session, "0909000001")
    assert nguoi_1.unit_id is None, "Hộ dân lẻ không được gán căn hộ"
    assert nguoi_1.address == "165 120 Lê Duẩn, Hà Nội"
    assert nguoi_1.lat == pytest.approx(21.025679)
    assert nguoi_1.lng == pytest.approx(105.85)
    assert nguoi_1.role == "resident"
    assert nguoi_1.email == "res-0001@sim.greenbin.vn", (
        "email sinh từ resident_id, đuôi @sim.greenbin.vn là dấu dữ liệu mô phỏng"
    )
    assert nguoi_1.full_name == "Cư dân RES-0001", "full_name sinh từ resident_id (workbook không có cột tên)"

    nguoi_2 = _tim(db_session, "0909000002")
    assert nguoi_2.address == "42 Hàng Ngang, Hà Nội"


# --- (b) mật khẩu băm đúng kiểu → đăng nhập được -----------------------------


def test_mat_khau_bam_pbkdf2_dang_nhap_duoc(db_session: Session, tmp_path: Path) -> None:
    """Test quan trọng nhất: dùng đúng hàm kiểm mật khẩu của hệ thống.

    ``authenticate`` đăng nhập bằng ``verify_password`` — khẳng định ngay bằng
    chính hàm đó, và khẳng định KHÔNG nhét cột ``password_hash_sha256`` vào.
    """
    duong = _workbook_gia(tmp_path, [_hang()])

    nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    nguoi = _tim(db_session, "0909000001")
    assert verify_password("GreenBin@0001", nguoi.password_hash) is True, (
        "Phải đăng nhập được bằng mật khẩu gốc trong workbook"
    )
    assert nguoi.password_hash != _SHA256_MAU, (
        "⛔ KHÔNG được nhét password_hash_sha256 của workbook vào password_hash"
    )
    assert nguoi.password_hash.startswith("pbkdf2_sha256$"), nguoi.password_hash


# --- (c) chạy lại lần hai → vô hại -------------------------------------------


def test_chay_lai_khong_tao_them_khong_doi_dia_chi(db_session: Session, tmp_path: Path) -> None:
    duong = _workbook_gia(tmp_path, [_hang()])

    nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()
    lan_hai = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    assert lan_hai["so_tao_moi"] == 0, "Lần hai không được tạo thêm ai"
    assert lan_hai["so_cap_nhat_dia_chi"] == 0
    assert lan_hai["so_da_du"] == 1, "Lần hai mọi dòng phải rơi vào đã có địa chỉ"
    assert len(db_session.scalars(select(User)).all()) == 1, "Không được nhân đôi tài khoản"
    assert _tim(db_session, "0909000001").address == "165 120 Lê Duẩn, Hà Nội"


# --- (d) tài khoản có sẵn thiếu địa chỉ → được điền, không đổi mật khẩu --------


def test_tai_khoan_co_san_thieu_dia_chi_duoc_dien_khong_doi_mat_khau(
    db_session: Session, tmp_path: Path
) -> None:
    db_session.add(
        User(
            email="cu_dan_cu@demo.vn",
            phone="0909000001",
            full_name="Cư dân cũ",
            role="resident",
            password_hash="pbkdf2_sha256$1$aa$bb",
            unit_id=None,
            address="",
        )
    )
    db_session.commit()
    duong = _workbook_gia(tmp_path, [_hang()])

    ket_qua = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    assert ket_qua["so_cap_nhat_dia_chi"] == 1, ket_qua
    assert ket_qua["so_tao_moi"] == 0, "Đã có tài khoản rồi thì không tạo mới"
    nguoi = _tim(db_session, "0909000001")
    assert nguoi.address == "165 120 Lê Duẩn, Hà Nội"
    assert nguoi.password_hash == "pbkdf2_sha256$1$aa$bb", "Chỉ điền địa chỉ, không được đổi mật khẩu"
    assert nguoi.email == "cu_dan_cu@demo.vn", "Không được đổi email của tài khoản có sẵn"


# --- (e) nhánh cập nhật không sửa email của tài khoản mô phỏng đã có ----------


def test_nhanh_cap_nhat_khong_sua_email_tai_khoan_sim_co_san(
    db_session: Session, tmp_path: Path
) -> None:
    """Đuôi @sim.greenbin.vn là dấu mô phỏng — nhánh cập nhật không được chạm email.

    Tài khoản đã có mang chính email nhánh tạo mới sẽ sinh; nếu nhánh cập nhật
    ghi đè email thì lần khôi phục sau mất dấu mô phỏng và CSDL lẫn lộn hai đuôi.
    """
    db_session.add(
        User(
            email="res-0001@sim.greenbin.vn",
            phone="0909000001",
            full_name="Cư dân mô phỏng",
            role="resident",
            password_hash="pbkdf2_sha256$1$aa$bb",
            unit_id=None,
            address="",
        )
    )
    db_session.commit()
    duong = _workbook_gia(tmp_path, [_hang()])

    ket_qua = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    assert ket_qua["so_cap_nhat_dia_chi"] == 1, ket_qua
    nguoi = _tim(db_session, "0909000001")
    assert nguoi.email == "res-0001@sim.greenbin.vn", "Nhánh cập nhật không được sửa email"
    assert nguoi.address == "165 120 Lê Duẩn, Hà Nội"


# --- (f) dòng thiếu login_phone → dòng hỏng, không làm hỏng cả lần chạy ---------


def test_dong_thieu_login_phone_tinh_vao_dong_hong(db_session: Session, tmp_path: Path) -> None:
    duong = _workbook_gia(
        tmp_path,
        [_hang(phone=""), _hang(resident_id="RES-0002", phone="0909000002")],
    )

    ket_qua = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    assert ket_qua["so_dong_hong"] == 1, ket_qua
    assert ket_qua["so_tao_moi"] == 1, "Dòng còn tốt vẫn phải được xử lý"
    assert len(db_session.scalars(select(User)).all()) == 1


# --- (f) --kiem-tra không ghi một dòng nào ------------------------------------


def test_kiem_tra_khong_ghi_gi(db_session: Session, tmp_path: Path) -> None:
    db_session.add(
        User(
            email="cu_dan_cu@demo.vn",
            phone="0909000001",
            full_name="Cư dân cũ",
            role="resident",
            password_hash="pbkdf2_sha256$1$aa$bb",
            unit_id=None,
            address="",
        )
    )
    db_session.commit()

    duong = _workbook_gia(
        tmp_path,
        [
            _hang(phone="0909000001", dia_chi="Địa chỉ không được ghi"),  # sẽ cập nhật nếu chạy thật
            _hang(resident_id="RES-0009", phone="0909999999"),  # sẽ tạo nếu chạy thật
        ],
    )

    ket_qua = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong, kiem_tra=True)

    assert ket_qua["so_tao_moi"] == 1, "Kiểm tra phải đếm đúng sẽ tạo bao nhiêu"
    assert ket_qua["so_cap_nhat_dia_chi"] == 1, "Kiểm tra phải đếm đúng sẽ cập nhật bao nhiêu"
    assert len(db_session.scalars(select(User)).all()) == 1, "--kiem-tra không được thêm user nào"
    nguoi = _tim(db_session, "0909000001")
    assert nguoi.address == "", "--kiem-tra không được sửa địa chỉ"
