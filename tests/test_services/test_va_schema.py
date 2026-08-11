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
