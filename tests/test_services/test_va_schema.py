"""Vá cột thiếu vào CSDL cũ — mô phỏng bằng SQLite bộ nhớ, không cần Postgres."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from src.db.schema_patch import COT_CAN_VA, va_cot_thieu


def _cot_can_va_cua_bang_users() -> list[str]:
    """Danh sách cột `users` mà `va_cot_thieu` PHẢI vá, suy ra từ chính bảng khai báo.

    Test cũ đóng đinh `== ["users.phone"]`, nên mỗi lần dự án khai thêm một cột
    vào `COT_CAN_VA` là hai test này đỏ dù `va_cot_thieu` chạy đúng — đã xảy ra
    thật với `users.organization_id` của gói A1. Suy ra từ `COT_CAN_VA` thì khẳng
    định vẫn chặt (đúng danh sách, đúng thứ tự) mà không rot theo từng gói sau.

    Chỉ lọc bảng `users` vì hàm dựng CSDL của file test này chỉ tạo mỗi bảng đó;
    `va_cot_thieu` bỏ qua bảng chưa tồn tại.
    """
    return [f"{bang}.{cot}" for bang, cot, _ in COT_CAN_VA if bang == "users"]


def _tao_bang_users_thieu_phone(engine) -> None:
    """Dựng bảng `users` kiểu CSDL cũ — KHÔNG có cột phone."""
    with engine.begin() as ket_noi:
        ket_noi.execute(
            text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255), full_name VARCHAR(120))")
        )


def test_them_duoc_cot_con_thieu() -> None:
    engine = create_engine("sqlite://")
    _tao_bang_users_thieu_phone(engine)
    with engine.begin() as ket_noi:
        ket_noi.execute(text("INSERT INTO users (email, full_name) VALUES ('a@x.vn', 'An')"))

    da_them = va_cot_thieu(engine)

    assert da_them == _cot_can_va_cua_bang_users()
    assert "users.phone" in da_them
    cot = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "phone" in cot
    with engine.connect() as ket_noi:
        dong = ket_noi.execute(text("SELECT email, phone FROM users")).all()
    assert len(dong) == 1
    assert dong[0].email == "a@x.vn"
    assert dong[0].phone == "", "dòng cũ phải có phone rỗng, không phải NULL"


def test_chay_lan_hai_khong_them_gi() -> None:
    engine = create_engine("sqlite://")
    _tao_bang_users_thieu_phone(engine)

    assert va_cot_thieu(engine) == _cot_can_va_cua_bang_users()
    assert va_cot_thieu(engine) == []


def test_bang_chua_ton_tai_thi_bo_qua_khong_no() -> None:
    engine = create_engine("sqlite://")

    assert va_cot_thieu(engine) == []


def test_du_lieu_cu_khong_bi_dong_cham() -> None:
    engine = create_engine("sqlite://")
    _tao_bang_users_thieu_phone(engine)
    with engine.begin() as ket_noi:
        ket_noi.execute(
            text("INSERT INTO users (email, full_name) VALUES ('a@x.vn', 'Nguyễn An'), ('b@x.vn', 'Trần Bình')")
        )

    va_cot_thieu(engine)

    with engine.connect() as ket_noi:
        cac_dong = {r.email: r.full_name for r in ket_noi.execute(text("SELECT email, full_name FROM users"))}
    assert cac_dong == {"a@x.vn": "Nguyễn An", "b@x.vn": "Trần Bình"}


# --- Gói P62: hai cột thêm vào bảng đã có phải được vá -------------------------


def test_building_id_va_item_id_duoc_khai_trong_cot_can_va() -> None:
    """Hai cột mới (users.building_id, classifications.item_id) phải trong `COT_CAN_VA`.

    Quên khai là CSDL production thiếu cột mà test vẫn xanh — bẫy đã ghi trong sổ.
    """
    cac_cot = {f"{bang}.{cot}" for bang, cot, _ in COT_CAN_VA}
    assert "users.building_id" in cac_cot
    assert "classifications.item_id" in cac_cot


def test_va_duoc_building_id_va_item_id() -> None:
    """`va_cot_thieu` thêm được cả hai cột mới lên bảng đã tồn tại."""
    engine = create_engine("sqlite://")
    with engine.begin() as ket_noi:
        ket_noi.execute(
            text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255), full_name VARCHAR(120))")
        )
        ket_noi.execute(
            text("CREATE TABLE classifications (id INTEGER PRIMARY KEY, text_query TEXT)")
        )

    da_them = va_cot_thieu(engine)

    assert "users.building_id" in da_them
    assert "classifications.item_id" in da_them
    cot_users = {c["name"] for c in inspect(engine).get_columns("users")}
    cot_phan_loai = {c["name"] for c in inspect(engine).get_columns("classifications")}
    assert "building_id" in cot_users
    assert "item_id" in cot_phan_loai


# --- Gói P62: hai bảng mới dựng được bằng `create_all` -------------------------


def test_hai_bang_moi_duoc_create_all_dung_ten_cot() -> None:
    """`create_all` dựng `phien_thung` và `token_thiet_bi` với đúng tên cột."""
    from sqlalchemy import create_engine, inspect

    from src.db.models import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    cot_phien = {c["name"] for c in inspect(engine).get_columns("phien_thung")}
    assert {
        "id",
        "ma_phien",
        "user_id",
        "bin_id",
        "trang_thai",
        "bat_dau",
        "ket_thuc",
        "so_vat",
        "diem_nhan_thuc",
        "ghi_chu",
    } <= cot_phien, f"Thiếu cột bảng phien_thung: {cot_phien}"

    cot_token = {c["name"] for c in inspect(engine).get_columns("token_thiet_bi")}
    assert {"id", "user_id", "token", "nen_tang", "created_at", "last_seen"} <= cot_token, (
        f"Thiếu cột bảng token_thiet_bi: {cot_token}"
    )

    # Tên cột điểm phải là `diem_nhan_thuc`, không phải `diem` — không quy đổi.
    assert "diem_nhan_thuc" in cot_phien
    assert "diem" not in cot_phien
