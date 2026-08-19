"""Vá những cột được thêm vào model SAU KHI cơ sở dữ liệu đã tồn tại.

Repo chưa bật Alembic (``requirements.txt`` để dòng alembic ở dạng chú thích).
``Base.metadata.create_all()`` tạo bảng còn thiếu nhưng **không sửa bảng đã
có**, nên mỗi lần thêm một cột vào model đã deploy thì CSDL đang chạy sẽ thiếu
cột và mọi truy vấn bảng đó chết — trong khi test vẫn xanh, vì test luôn dựng
CSDL mới từ metadata.

Chạy được trên cả SQLite (máy dev) lẫn PostgreSQL (Supabase, production): phát
hiện cột bằng ``inspect()`` của SQLAlchemy chứ không bằng ``PRAGMA`` riêng của
SQLite, và **không** dùng ``ADD COLUMN IF NOT EXISTS`` vì SQLite không hiểu cú
pháp đó. Gọi lại nhiều lần vô hại.

Đây là giải pháp tạm cho tới khi schema ổn định và nhóm bật Alembic thật.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect, text

logger = logging.getLogger(__name__)

# (bảng, cột, mệnh đề kiểu). Mệnh đề kiểu phải hợp lệ trên CẢ SQLite lẫn
# PostgreSQL — SQLite bắt buộc `NOT NULL` phải đi kèm `DEFAULT`.
#
# Chỉ thêm dòng, đừng bao giờ sửa hay xoá dòng cũ: một CSDL nào đó ngoài kia có
# thể vẫn đang ở phiên bản trước.
COT_CAN_VA: list[tuple[str, str, str]] = [
    # Gói G1a — đăng nhập bằng số điện thoại.
    ("users", "phone", "VARCHAR(20) NOT NULL DEFAULT ''"),
    # Gói A2a — gán thùng cho nhân viên vệ sinh. Kiểu để trần `INTEGER`, KHÔNG
    # kèm ràng buộc khoá ngoại: SQLite không thêm được FK bằng ALTER TABLE, và
    # mệnh đề này phải chạy y hệt trên cả SQLite lẫn PostgreSQL.
    ("bins", "assigned_cleaner_id", "INTEGER"),
    # Gói A3a — khoá thiết bị riêng cho từng thùng, lưu dạng băm SHA-256 (64 ký
    # tự hex). SQLite bắt buộc `NOT NULL` phải đi kèm `DEFAULT`.
    ("bins", "device_key_hash", "VARCHAR(64) NOT NULL DEFAULT ''"),
    # Gói A1 — đơn vị thu gom. Kiểu để trần `INTEGER`, KHÔNG kèm ràng buộc khoá
    # ngoại: SQLite không thêm được FK bằng ALTER TABLE, và mệnh đề này phải
    # chạy y hệt trên cả SQLite lẫn PostgreSQL.
    ("users", "organization_id", "INTEGER"),
    ("bins", "organization_id", "INTEGER"),
    # Gói P30 — dữ liệu GIS Hà Nội (60 vị trí thùng đề xuất). `NOT NULL` bắt buộc
    # đi kèm `DEFAULT` để SQLite chấp nhận; chỉ số `index=True` chỉ khai ở model
    # (bảng dựng mới), đường vá này không cần thêm chỉ số cho bảng cũ.
    ("bins", "site_type", "VARCHAR(40) NOT NULL DEFAULT ''"),
    ("bins", "priority", "VARCHAR(8) NOT NULL DEFAULT ''"),
    ("bins", "deployment_status", "VARCHAR(20) NOT NULL DEFAULT ''"),
    ("bins", "coordinate_confidence", "VARCHAR(10) NOT NULL DEFAULT ''"),
    ("bins", "area_name", "VARCHAR(60) NOT NULL DEFAULT ''"),
    # Gói P38 — khoá ảnh trên Supabase Storage. `NOT NULL` phải kèm `DEFAULT`
    # (SQLite bắt buộc), và không khoá ngoại trong ALTER (SQLite không làm được).
    ("media", "storage_key", "VARCHAR(1024) NOT NULL DEFAULT ''"),
    ("media", "original_storage_key", "VARCHAR(1024) NOT NULL DEFAULT ''"),
    # Gói P52 — nơi ở của cư dân (địa chỉ + toạ độ) tách khỏi liên kết căn hộ.
    # `address` dùng `NOT NULL DEFAULT ''` để SQLite chấp nhận ALTER; `lat` / `lng`
    # để NULL cho phép người không có toạ độ. `DOUBLE PRECISION` hợp lệ trên cả
    # SQLite (ánh xạ sang REAL affinity) lẫn PostgreSQL — đã kiểm bằng ALTER thật.
    ("users", "address", "VARCHAR(300) NOT NULL DEFAULT ''"),
    ("users", "lat", "DOUBLE PRECISION"),
    ("users", "lng", "DOUBLE PRECISION"),
    ("pickup_requests", "address", "VARCHAR(300) NOT NULL DEFAULT ''"),
    ("pickup_requests", "lat", "DOUBLE PRECISION"),
    ("pickup_requests", "lng", "DOUBLE PRECISION"),
    # Gói P62 — liên kết CHÍNH người → toà nhà, không phải đi vòng qua căn hộ.
    # Kiểu để trần `INTEGER`, KHÔNG kèm ràng buộc khoá ngoại: SQLite không thêm
    # được FK bằng ALTER TABLE, và mệnh đề này phải chạy y hệt trên cả SQLite lẫn
    # PostgreSQL.
    ("users", "building_id", "INTEGER"),
    # Gói P62 — khoá chống-trùng của THIẾT BỊ, cất ở cột riêng thay vì nhét vào
    # `classifications.text_query` (câu hỏi bằng chữ của cư dân — rò ra frontend).
    # `NOT NULL` bắt buộc kèm `DEFAULT` để SQLite chấp nhận ALTER.
    ("classifications", "item_id", "VARCHAR(64) NOT NULL DEFAULT ''"),
]


def va_cot_thieu(engine: Engine) -> list[str]:
    """Thêm những cột còn thiếu vào CSDL đang trỏ tới.

    Trả về danh sách cột vừa thêm, dạng ``"bảng.cột"``. Danh sách rỗng nghĩa là
    CSDL đã đủ cột — đó là trạng thái bình thường ở lần khởi động thứ hai trở đi.

    Bảng chưa tồn tại thì bỏ qua chứ không nổ: ``create_all()`` chạy trước sẽ
    tạo nó với đầy đủ cột, không có gì để vá.
    """
    da_them: list[str] = []
    for bang, cot, kieu in COT_CAN_VA:
        # Dựng inspector mới mỗi vòng: inspector có bộ nhớ đệm, mà vòng trước có
        # thể vừa đổi cấu trúc.
        soi = inspect(engine)
        if bang not in soi.get_table_names():
            continue
        if cot in {c["name"] for c in soi.get_columns(bang)}:
            continue
        with engine.begin() as ket_noi:
            ket_noi.execute(text(f"ALTER TABLE {bang} ADD COLUMN {cot} {kieu}"))
        da_them.append(f"{bang}.{cot}")
        logger.warning("Đã vá cột còn thiếu: %s.%s", bang, cot)
    return da_them
