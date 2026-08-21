"""Dữ liệu nền của hệ thống, khai báo một chỗ để test và script seed dùng chung.

**Quy định dữ liệu của chương trình:** chỉ dùng dữ liệu công khai, mô phỏng hoặc
đã ẩn danh. Toàn bộ toà nhà, căn hộ, cư dân dưới đây là **nhân vật mô phỏng** —
không có dữ liệu cá nhân thật nào trong hệ thống.

⚠️ **Về phần trích dẫn pháp luật:** các đoạn thuộc `doc_type="law"` là **diễn
giải rút gọn**, có gắn cờ ``needs_verification`` trong ``meta``. Trước khi đưa
lên pitch deck hoặc lên UI như trích dẫn nguyên văn, phải mở văn bản gốc tại
nguồn đã ghi và đối chiếu điều khoản lẫn hiệu lực hiện hành.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Bin, Organization, User

# --- Danh mục rác --------------------------------------------------------
# ``clip_prompts``: các câu mô tả tiếng Anh cho CLIP zero-shot ở tầng T0.5,
# phân cách bằng dấu "|". Viết tiếng Anh vì CLIP được huấn luyện trên tiếng Anh.

WASTE_CATEGORIES: list[dict[str, Any]] = [
    {
        "code": "recyclable",
        "name": "Rác tái chế",
        "parent_code": "",
        "is_hazardous": False,
        "min_confidence": 0.60,
        "bin_color": "#3a8fea",
        "icon": "♻️",
        "sort_order": 10,
        "handling_note": "Đổ hết phần thừa bên trong · Để ráo · Bóp dẹp cho gọn thùng",
        "safety_warning": "",
        "clip_prompts": "a photo of a recyclable item|a photo of clean packaging waste",
    },
    {
        "code": "recyclable_paper",
        "name": "Giấy, bìa carton",
        "parent_code": "recyclable",
        "is_hazardous": False,
        "min_confidence": 0.60,
        "bin_color": "#3a8fea",
        "icon": "📄",
        "sort_order": 11,
        "handling_note": "Gỡ băng dính và ghim · Xếp phẳng · Giấy dính dầu mỡ thì bỏ sang rác khác",
        "safety_warning": "",
        "clip_prompts": (
            "a photo of cardboard boxes|a photo of waste paper|a photo of a paper carton|"
            "a photo of a milk carton"
        ),
    },
    {
        "code": "recyclable_plastic",
        "name": "Nhựa tái chế",
        "parent_code": "recyclable",
        "is_hazardous": False,
        "min_confidence": 0.60,
        "bin_color": "#3a8fea",
        "icon": "🥤",
        "sort_order": 12,
        "handling_note": "Đổ hết nước · Tráng qua nếu dính đường sữa · Bóp dẹp · Giữ lại nắp",
        "safety_warning": "",
        "clip_prompts": (
            "a photo of a plastic bottle|a photo of a plastic cup|a photo of plastic packaging|"
            "a photo of a plastic container"
        ),
    },
    {
        "code": "recyclable_metal",
        "name": "Kim loại",
        "parent_code": "recyclable",
        "is_hazardous": False,
        "min_confidence": 0.60,
        "bin_color": "#3a8fea",
        "icon": "🥫",
        "sort_order": 13,
        "handling_note": "Đổ sạch phần thừa · Cẩn thận mép hộp sắc · Bóp dẹp lon nếu được",
        "safety_warning": "",
        "clip_prompts": "a photo of an aluminium can|a photo of a metal tin can|a photo of scrap metal",
    },
    {
        "code": "recyclable_glass",
        "name": "Thuỷ tinh",
        "parent_code": "recyclable",
        "is_hazardous": False,
        "min_confidence": 0.65,
        "bin_color": "#3a8fea",
        "icon": "🍾",
        "sort_order": 14,
        "handling_note": "Để nguyên chai lọ, không đập vỡ · Bọc riêng nếu đã vỡ · Không lẫn gương và bóng đèn",
        "safety_warning": "",
        "clip_prompts": "a photo of a glass bottle|a photo of a glass jar|a photo of glass containers",
    },
    {
        "code": "organic",
        "name": "Rác thực phẩm",
        "parent_code": "",
        "is_hazardous": False,
        "min_confidence": 0.60,
        "bin_color": "#2fae66",
        "icon": "🍃",
        "sort_order": 20,
        "handling_note": "Để ráo nước · Buộc kín túi · Bỏ đúng khung giờ thu gom để tránh mùi",
        "safety_warning": "",
        "clip_prompts": (
            "a photo of food waste|a photo of vegetable scraps|a photo of leftover food|"
            "a photo of fruit peels"
        ),
    },
    {
        "code": "other",
        "name": "Rác sinh hoạt khác",
        "parent_code": "",
        "is_hazardous": False,
        "min_confidence": 0.55,
        "bin_color": "#8a938a",
        "icon": "🗑",
        "sort_order": 30,
        "handling_note": "Buộc kín túi · Không lẫn pin, bóng đèn, thuốc vào nhóm này",
        "safety_warning": "",
        "clip_prompts": (
            "a photo of general household waste|a photo of a dirty foam food box|"
            "a photo of used tissues|a photo of a plastic bag of trash"
        ),
    },
    {
        "code": "hazardous",
        "name": "Rác nguy hại",
        "parent_code": "",
        "is_hazardous": True,
        # Ngưỡng cao hơn hẳn: sai ở nhóm này gây hại thật (CLAUDE.md mục 5).
        "min_confidence": 0.80,
        "bin_color": "#e8622a",
        "icon": "⚠️",
        "sort_order": 40,
        "handling_note": "Để riêng, không bỏ chung bất kỳ thùng nào · Mang tới điểm thu gom chuyên dụng",
        # Text cố định — KHÔNG BAO GIỜ để LLM sinh phần này.
        "safety_warning": (
            "KHÔNG bỏ vào thùng rác thường, KHÔNG vứt chung rác thực phẩm, "
            "KHÔNG làm thủng, không nén và không đốt. "
            "Mang tới điểm thu gom rác nguy hại của toà hoặc đăng ký để đội vệ sinh tới nhận."
        ),
        "clip_prompts": (
            "a photo of used batteries|a photo of a fluorescent light bulb|a photo of expired medicine|"
            "a photo of a chemical bottle|a photo of a spray can|a photo of an electronic device to discard"
        ),
    },
    {
        "code": "bulky",
        "name": "Đồ cồng kềnh",
        "parent_code": "",
        "is_hazardous": False,
        "min_confidence": 0.55,
        "bin_color": "#8b5cf6",
        "icon": "📦",
        "sort_order": 50,
        "handling_note": "Không để ở hành lang hay lối thoát hiểm · Đăng ký lịch thu gom trong app",
        "safety_warning": "",
        "clip_prompts": (
            "a photo of an old wooden cabinet|a photo of a discarded mattress|a photo of broken furniture|"
            "a photo of a large cardboard box pile|a photo of an old sofa"
        ),
    },
]


# --- Toà nhà và căn hộ ---------------------------------------------------

BUILDINGS: list[dict[str, Any]] = [
    {"code": "S1", "name": "Sunrise Residence — Toà S1", "address": "25 Lý Thường Kiệt, Hoàn Kiếm, Hà Nội", "lat": 21.0271, "lng": 105.8519},
    {"code": "S2", "name": "Sunrise Residence — Toà S2", "address": "5 Đinh Tiên Hoàng, Hoàn Kiếm, Hà Nội", "lat": 21.0284, "lng": 105.8531},
    {"code": "S3", "name": "Sunrise Residence — Toà S3", "address": "26 Lò Sũ, Hoàn Kiếm, Hà Nội", "lat": 21.0303, "lng": 105.8554},
]

UNITS: list[dict[str, str]] = [
    {"building_code": "S1", "code": "S1-1203"},
    {"building_code": "S1", "code": "S1-0805"},
    {"building_code": "S1", "code": "S1-1508"},
    {"building_code": "S1", "code": "S1-0302"},
    {"building_code": "S2", "code": "S2-0501"},
    {"building_code": "S2", "code": "S2-1102"},
    {"building_code": "S3", "code": "S3-0710"},
]


# --- Tài khoản demo ------------------------------------------------------
# Ba nút "vào thẳng" trên màn đăng nhập, đúng bảng ở FRONTEND_SPEC mục 1.

DEMO_PASSWORD = "demo1234"

USERS: list[dict[str, Any]] = [
    {
        "email": "resident@demo.vn",
        "phone": "0901000001",
        "full_name": "Nguyễn Thị Lan",
        "role": "resident",
        "unit_code": "S1-1203",
        "green_points": 120,
    },
    {
        "email": "cleaner@demo.vn",
        "phone": "0901000002",
        "full_name": "Lê Văn Hùng",
        "role": "cleaner",
        "unit_code": "",
        "green_points": 0,
    },
    {
        "email": "manager@demo.vn",
        "phone": "0901000003",
        "full_name": "Trần Minh Đức",
        "role": "manager",
        "unit_code": "",
        "green_points": 0,
    },
    # Nhân viên vệ sinh thứ hai. Có hai người thì ô "giao thùng cho ai" mới có
    # nghĩa, và mới thấy được cảnh mỗi người chỉ nhìn phần việc của mình.
    {
        "email": "cleaner2@demo.vn",
        "phone": "0901000009",
        "full_name": "Bùi Thị Mai",
        "role": "cleaner",
        "unit_code": "",
        "green_points": 0,
    },
    # Cư dân phụ — để tuyến gộp có nhiều điểm dừng thật, không phải bịa số.
    {"email": "resident2@demo.vn", "phone": "0901000004", "full_name": "Phạm Quốc Anh", "role": "resident", "unit_code": "S1-0805", "green_points": 60},
    {"email": "resident3@demo.vn", "phone": "0901000005", "full_name": "Đỗ Thu Hà", "role": "resident", "unit_code": "S1-1508", "green_points": 45},
    {"email": "resident4@demo.vn", "phone": "0901000006", "full_name": "Vũ Minh Khôi", "role": "resident", "unit_code": "S2-0501", "green_points": 30},
    {"email": "resident5@demo.vn", "phone": "0901000007", "full_name": "Ngô Bảo Trâm", "role": "resident", "unit_code": "S2-1102", "green_points": 15},
    {"email": "resident6@demo.vn", "phone": "0901000008", "full_name": "Lý Gia Huy", "role": "resident", "unit_code": "S3-0710", "green_points": 10},
]


# --- Lịch thu gom --------------------------------------------------------
# weekdays: 0 = Thứ 2 … 6 = Chủ nhật.

COLLECTION_SCHEDULES: list[dict[str, Any]] = [
    {"building_code": "S1", "category_code": "recyclable", "weekdays": [1, 3, 5], "window": "18:00-20:00", "location": "Phòng rác tầng — thùng xanh dương thứ 2"},
    {"building_code": "S1", "category_code": "organic", "weekdays": [0, 1, 2, 3, 4, 5, 6], "window": "06:00-08:00", "location": "Phòng rác tầng — thùng xanh lá"},
    {"building_code": "S1", "category_code": "other", "weekdays": [0, 2, 4], "window": "18:00-20:00", "location": "Phòng rác tầng — thùng xám"},
    {"building_code": "S1", "category_code": "hazardous", "weekdays": [5], "window": "09:00-11:00", "location": "Điểm thu rác nguy hại — tầng hầm B1"},
    {"building_code": "S1", "category_code": "bulky", "weekdays": [3], "window": "08:00-10:00", "location": "Khu tập kết sân sau, cần đăng ký trước"},
    {"building_code": "S2", "category_code": "recyclable", "weekdays": [1, 4], "window": "17:00-19:00", "location": "Phòng rác tầng — thùng xanh dương"},
    {"building_code": "S2", "category_code": "organic", "weekdays": [0, 1, 2, 3, 4, 5, 6], "window": "06:00-08:00", "location": "Phòng rác tầng — thùng xanh lá"},
    {"building_code": "S2", "category_code": "hazardous", "weekdays": [5], "window": "09:00-11:00", "location": "Điểm thu rác nguy hại — tầng hầm B1"},
    {"building_code": "S2", "category_code": "bulky", "weekdays": [3], "window": "08:00-10:00", "location": "Khu tập kết sân sau, cần đăng ký trước"},
    {"building_code": "S3", "category_code": "recyclable", "weekdays": [2, 5], "window": "17:00-19:00", "location": "Phòng rác tầng — thùng xanh dương"},
    {"building_code": "S3", "category_code": "bulky", "weekdays": [3], "window": "14:00-16:00", "location": "Khu tập kết sân sau, cần đăng ký trước"},
]


# --- Thùng thu gom thông minh (demo) -------------------------------------
# Thùng đặt ngoài đường khu Hoàn Kiếm — toạ độ và tên phố thật, con số là mô
# phỏng. ``last_seen_ago_minutes`` lưu KHOẢNG thời gian cách thời điểm seed, để
# ``seed_bins`` tính lại ``last_seen_at`` tương đối khi chạy — một ngày cố định
# sẽ làm mọi thùng thành "mất kết nối" sau một tuần.
#
# Chủ đích để đủ cả bốn trạng thái: binh_thuong (BIN-01/05/09) · can_gom
# (BIN-02/06/10) · het_pin (BIN-03/07) · mat_ket_noi (BIN-04/08).

SEED_BINS: list[dict[str, Any]] = [
    {
        "code": "BIN-01",
        "name": "Phố Đinh Tiên Hoàng (Bờ Hồ)",
        "address": "Phố Đinh Tiên Hoàng, quận Hoàn Kiếm, Hà Nội",
        "lat": 21.0285,
        "lng": 105.8542,
        "category_codes": ["recyclable", "other"],
        "capacity_liters": 660,
        "fill_percent": 25.0,
        "battery_percent": 85.0,
        "last_seen_ago_minutes": 10,
        "is_active": True,
    },
    {
        "code": "BIN-02",
        "name": "Phố Hàng Trống",
        "address": "Phố Hàng Trống, quận Hoàn Kiếm, Hà Nội",
        "lat": 21.0296,
        "lng": 105.8501,
        "category_codes": ["recyclable_paper", "recyclable_plastic"],
        "capacity_liters": 500,
        "fill_percent": 88.0,
        "battery_percent": 60.0,
        "last_seen_ago_minutes": 5,
        "is_active": True,
    },
    {
        "code": "BIN-03",
        "name": "Phố Lương Văn Can",
        "address": "Phố Lương Văn Can, quận Hoàn Kiếm, Hà Nội",
        "lat": 21.0322,
        "lng": 105.8503,
        "category_codes": ["organic", "other"],
        "capacity_liters": 500,
        "fill_percent": 12.0,
        "battery_percent": 8.0,
        "last_seen_ago_minutes": 8,
        "is_active": True,
    },
    {
        "code": "BIN-04",
        "name": "Phố Tràng Tiền",
        "address": "Phố Tràng Tiền, quận Hoàn Kiếm, Hà Nội",
        "lat": 21.0256,
        "lng": 105.8521,
        "category_codes": ["recyclable_glass", "recyclable_metal"],
        "capacity_liters": 660,
        "fill_percent": 65.0,
        "battery_percent": 90.0,
        # Mất kết nối hai ngày: con số 65% là của lần báo cuối, không ai biết
        # thực tế đầy bao nhiêu — đúng ca mà trạng thái phải ưu tiên.
        "last_seen_ago_minutes": 60 * 48,
        "is_active": True,
    },
    {
        "code": "BIN-05",
        "name": "Phố Hàng Bài",
        "address": "Phố Hàng Bài, quận Hoàn Kiếm, Hà Nội",
        "lat": 21.0247,
        "lng": 105.8543,
        "category_codes": ["other"],
        "capacity_liters": 500,
        "fill_percent": 45.0,
        "battery_percent": 75.0,
        "last_seen_ago_minutes": 3,
        "is_active": True,
    },
    {
        "code": "BIN-06",
        "name": "Phố Hàng Khay",
        "address": "Phố Hàng Khay, quận Hoàn Kiếm, Hà Nội",
        "lat": 21.0291,
        "lng": 105.8523,
        "category_codes": ["recyclable_plastic"],
        "capacity_liters": 660,
        "fill_percent": 92.0,
        "battery_percent": 55.0,
        "last_seen_ago_minutes": 4,
        "is_active": True,
    },
    {
        "code": "BIN-07",
        "name": "Phố Lý Thái Tổ",
        "address": "Phố Lý Thái Tổ, quận Hoàn Kiếm, Hà Nội",
        "lat": 21.0326,
        "lng": 105.8541,
        "category_codes": ["hazardous"],
        "capacity_liters": 240,
        "fill_percent": 30.0,
        "battery_percent": 5.0,
        "last_seen_ago_minutes": 6,
        "is_active": True,
    },
    {
        "code": "BIN-08",
        "name": "Phố Hàng Đào",
        "address": "Phố Hàng Đào, quận Hoàn Kiếm, Hà Nội",
        "lat": 21.0331,
        "lng": 105.8492,
        "category_codes": ["recyclable_paper", "recyclable_metal"],
        "capacity_liters": 500,
        "fill_percent": 18.0,
        "battery_percent": 80.0,
        "last_seen_ago_minutes": 60 * 72,
        "is_active": True,
    },
    {
        "code": "BIN-09",
        "name": "Phố Cầu Gỗ",
        "address": "Phố Cầu Gỗ, quận Hoàn Kiếm, Hà Nội",
        "lat": 21.0312,
        "lng": 105.8507,
        "category_codes": ["organic", "recyclable"],
        "capacity_liters": 500,
        "fill_percent": 55.0,
        "battery_percent": 95.0,
        "last_seen_ago_minutes": 7,
        "is_active": True,
    },
    {
        "code": "BIN-10",
        "name": "Phố Lò Sũ",
        "address": "Phố Lò Sũ, quận Hoàn Kiếm, Hà Nội",
        "lat": 21.0289,
        "lng": 105.8556,
        "category_codes": ["recyclable_glass"],
        "capacity_liters": 660,
        "fill_percent": 82.0,
        "battery_percent": 65.0,
        "last_seen_ago_minutes": 2,
        "is_active": True,
    },
]


def seed_bins(session: Session) -> int:
    """Nạp thùng thu gom demo; mọi bản ghi đều gắn ``is_seed=True``.

    Idempotent: khớp theo ``code``, thùng đã có thì bỏ qua — chạy hai lần không
    tạo bản ghi trùng. ``last_seen_at`` tính TƯƠNG ĐỐI so với thời điểm seed chứ
    không phải ngày cố định, để trạng thái "mất kết nối" không tự lan ra toàn bộ
    thùng chỉ vì demo chạy muộn hơn ngày viết dữ liệu.
    """
    now = datetime.now(UTC)
    them = 0
    for row in SEED_BINS:
        if session.scalar(select(Bin).where(Bin.code == row["code"])) is not None:
            continue
        session.add(
            Bin(
                code=row["code"],
                name=row["name"],
                address=row["address"],
                lat=row["lat"],
                lng=row["lng"],
                category_codes=row["category_codes"],
                capacity_liters=row["capacity_liters"],
                fill_percent=row["fill_percent"],
                battery_percent=row["battery_percent"],
                last_seen_at=now - timedelta(minutes=row["last_seen_ago_minutes"]),
                is_active=row["is_active"],
                is_seed=True,
            )
        )
        them += 1
    session.flush()
    return them


# --- Gán thùng cho nhân viên vệ sinh (demo) ------------------------------
# Sáu thùng đầu giao cho nhân viên demo, bốn thùng còn lại cố ý để trống: màn
# hình của ban quản lý phải có chỗ để thấy "thùng chưa giao cho ai". Sáu thùng
# này phủ đủ bốn trạng thái (binh_thuong · can_gom · het_pin · mat_ket_noi) nên
# màn hình của nhân viên không bị rỗng nghĩa.

SEED_GAN_THUNG: dict[str, list[str]] = {
    "cleaner@demo.vn": ["BIN-01", "BIN-02", "BIN-03", "BIN-04", "BIN-05", "BIN-06"],
    "cleaner2@demo.vn": ["BIN-07", "BIN-08"],
}


def gan_thung_demo(session: Session) -> int:
    """Gán thùng demo cho nhân viên vệ sinh. Trả về số thùng vừa gán.

    **Không bao giờ ghi đè:** chỉ điền vào thùng đang ``assigned_cleaner_id IS
    NULL``. Ban quản lý có thể đã giao tay trên giao diện, mà seed chạy lại mỗi
    lần khởi động máy chủ — ghi đè là mỗi lần restart lại xoá quyết định của
    người dùng. Cùng lý lẽ với ô số điện thoại ở gói G1a.

    Thùng chưa tồn tại hoặc tài khoản chưa tồn tại thì bỏ qua chứ không nổ:
    hàm này chạy cả trên CSDL trống lẫn CSDL đã đầy dữ liệu.
    """
    da_gan = 0
    for email, ma_thung in SEED_GAN_THUNG.items():
        nhan_vien = session.scalar(select(User).where(User.email == email))
        if nhan_vien is None:
            continue
        for ma in ma_thung:
            thung = session.scalar(select(Bin).where(Bin.code == ma))
            if thung is None or thung.assigned_cleaner_id is not None:
                continue
            thung.assigned_cleaner_id = nhan_vien.id
            da_gan += 1
    session.flush()
    return da_gan


# --- Đơn vị thu gom (demo) ------------------------------------------------
# Bảng Gate 01 chốt khách hàng chính là đơn vị thu gom / đơn vị vận hành chuỗi
# thu gom tái chế — SỐ NHIỀU. Hệ thống hiện vẫn chạy với đúng MỘT đơn vị; bảng
# `organizations` và cột `organization_id` trên `users` / `bins` mới chỉ là NỀN
# DỮ LIỆU để sau này tách. Chưa có truy vấn nào lọc theo tổ chức — đó là gói A1b.

SEED_TO_CHUC: dict[str, str] = {
    "code": "GBAI",
    "name": "GreenBin Demo — Đơn vị thu gom tái chế",
    "address": "Khu đô thị mô phỏng, Quận Hoàn Kiếm, Hà Nội",
    "phone": "0900000000",
}


def to_chuc_demo(session: Session) -> int:
    """Gắn người dùng và thùng vào đơn vị thu gom. Trả về số bản ghi vừa gắn.

    Hệ thống chạy với **đúng một** đơn vị (`GreenBin Demo`); hàm này chỉ điền
    ``organization_id`` cho nhân viên vệ sinh, quản lý và mọi thùng còn đang
    NULL. **Cư dân KHÔNG được gắn** — cư dân là người gửi rác, không thuộc đơn
    vị thu gom nào.

    **Không bao giờ ghi đè:** chỉ điền vào chỗ đang NULL, cùng lý lẽ với
    ``gan_thung_demo`` — seed chạy lại mỗi lần khởi động máy chủ, ghi đè là mỗi
    lần restart lại xoá quyết định của người dùng. Gọi lại nhiều lần vô hại.
    """
    to_chuc = session.scalar(select(Organization).where(Organization.code == SEED_TO_CHUC["code"]))
    if to_chuc is None:
        to_chuc = Organization(**SEED_TO_CHUC)
        session.add(to_chuc)
        session.flush()

    da_gan = 0
    for nguoi_dung in session.scalars(
        select(User).where(User.role.in_(["cleaner", "manager"]), User.organization_id.is_(None))
    ):
        nguoi_dung.organization_id = to_chuc.id
        da_gan += 1
    for thung in session.scalars(select(Bin).where(Bin.organization_id.is_(None))):
        thung.organization_id = to_chuc.id
        da_gan += 1
    session.flush()
    return da_gan


# --- Kho tri thức (RAG) --------------------------------------------------

KNOWLEDGE_DOCS: list[dict[str, Any]] = [
    {
        "title": "Nội quy phân loại rác — Toà Sunrise S1",
        "building_code": "S1",
        "doc_type": "building_rule",
        "source": "Nội quy toà nhà (tài liệu mô phỏng cho demo)",
        "effective_date": "2026-01-01",
        "chunks": [
            {
                "section": "Mục 4.1 — Nguyên tắc chung",
                "content": (
                    "Cư dân toà S1 phân loại rác tại nguồn thành bốn nhóm: rác tái chế, rác thực phẩm, "
                    "rác sinh hoạt khác và rác nguy hại. Đồ cồng kềnh không bỏ tại phòng rác tầng mà "
                    "phải đăng ký lịch thu gom riêng."
                ),
            },
            {
                "section": "Mục 4.2 — Rác tái chế",
                "content": (
                    "Rác tái chế gồm giấy, bìa carton, nhựa, kim loại và thuỷ tinh, bỏ vào thùng xanh dương "
                    "đặt tại phòng rác mỗi tầng. Vỏ hộp sữa giấy tráng nhôm được tính là rác tái chế và "
                    "KHÔNG cần tách lớp bạc; chỉ cần đổ hết phần sữa thừa và bóp dẹp hộp. "
                    "Thu gom vào thứ Ba, thứ Năm và thứ Bảy, khung 18:00–20:00."
                ),
            },
            {
                "section": "Mục 4.3 — Rác thực phẩm",
                "content": (
                    "Rác thực phẩm để ráo nước, buộc kín túi, bỏ vào thùng xanh lá. Thu gom tất cả các ngày "
                    "trong tuần, khung 06:00–08:00. Không bỏ vỏ sò, xương lớn và dầu mỡ lỏng vào nhóm này."
                ),
            },
            {
                "section": "Mục 4.4 — Rác nguy hại",
                "content": (
                    "Pin, ắc quy, bóng đèn huỳnh quang, thuốc hết hạn, hoá chất tẩy rửa mạnh và thiết bị "
                    "điện tử hỏng thuộc nhóm rác nguy hại. Cư dân mang tới điểm thu gom tại tầng hầm B1, "
                    "hoặc đăng ký để đội vệ sinh tới nhận. Tuyệt đối không bỏ chung với rác sinh hoạt."
                ),
            },
            {
                "section": "Mục 4.5 — Đồ cồng kềnh",
                "content": (
                    "Đồ cồng kềnh gồm tủ, giường, đệm, ghế sofa, thùng carton số lượng lớn. Cư dân đăng ký "
                    "trước ít nhất một ngày. Yêu cầu có tổng khối lượng ước tính vượt 30 kg hoặc trên 3 món "
                    "cần ban quản lý duyệt trước khi xếp lịch. Không để đồ tại hành lang hoặc lối thoát hiểm."
                ),
            },
        ],
    },
    {
        "title": "Nội quy phân loại rác — Toà Sunrise S2",
        "building_code": "S2",
        "doc_type": "building_rule",
        "source": "Nội quy toà nhà (tài liệu mô phỏng cho demo)",
        "effective_date": "2026-01-01",
        "chunks": [
            {
                "section": "Mục 3.1 — Nhóm rác và thùng chứa",
                "content": (
                    "Toà S2 dùng chung bảng màu thùng với toà S1. Khác biệt: rác tái chế của S2 thu gom "
                    "vào thứ Ba và thứ Sáu, khung 17:00–19:00, sớm hơn S1 một tiếng."
                ),
            },
            {
                "section": "Mục 3.2 — Điểm tập kết",
                "content": (
                    "Phòng rác tầng của S2 chỉ đặt được hai thùng, nên thùng kim loại và thuỷ tinh gộp chung "
                    "với thùng nhựa. Đội vệ sinh tách lại tại khu tập kết sân sau."
                ),
            },
        ],
    },
    {
        "title": "Danh mục rác nguy hại và cách xử lý",
        "building_code": "",
        "doc_type": "hazard",
        "source": "Danh mục nội bộ, biên soạn theo hướng dẫn phân loại rác tại nguồn",
        "effective_date": "2026-01-01",
        "chunks": [
            {
                "section": "Pin và ắc quy",
                "content": (
                    "Pin tiểu, pin cúc áo, pin sạc dự phòng và ắc quy chứa kim loại nặng. Không làm thủng, "
                    "không nén, không đốt. Pin phồng hoặc rò rỉ phải để riêng trong hộp kín và báo ban quản lý ngay."
                ),
            },
            {
                "section": "Bóng đèn huỳnh quang",
                "content": (
                    "Bóng đèn huỳnh quang chứa thuỷ ngân. Giữ nguyên bóng, bọc giấy báo, không đập vỡ. "
                    "Nếu đã vỡ thì mở cửa thông gió, không dùng máy hút bụi để dọn."
                ),
            },
            {
                "section": "Thuốc hết hạn",
                "content": (
                    "Thuốc hết hạn không đổ xuống bồn cầu và không bỏ chung rác sinh hoạt. Giữ nguyên vỉ, "
                    "mang tới điểm thu gom của toà hoặc nhà thuốc có nhận lại."
                ),
            },
            {
                "section": "Vật sắc nhọn y tế",
                "content": (
                    "Kim tiêm, bơm tiêm, que thử đường huyết và dao mổ thuộc nhóm rác y tế lây nhiễm. "
                    "Hệ thống KHÔNG tự hướng dẫn nhóm này trong mọi trường hợp, luôn chuyển cho ban quản lý "
                    "để xử lý theo quy trình riêng."
                ),
            },
        ],
    },
    {
        "title": "Luật Bảo vệ môi trường 2020 — phân loại chất thải rắn sinh hoạt tại nguồn",
        "building_code": "",
        "doc_type": "law",
        "source": "Luật số 72/2020/QH14",
        "effective_date": "2022-01-01",
        "chunks": [
            {
                "section": "Điều 75.1 — 3 Nhóm phân loại CTRSH bắt buộc",
                "content": (
                    "Chất thải rắn sinh hoạt từ hộ gia đình, cá nhân phải phân loại thành 3 nhóm: "
                    "(1) Rác có khả năng tái sử dụng, tái chế (giấy, nhựa, kim loại, thủy tinh, vải, gỗ, cao su, e-waste); "
                    "(2) Rác thực phẩm (thức ăn thừa, rau củ quả, hữu cơ dễ phân hủy); "
                    "(3) Rác sinh hoạt khác (rác nguy hại hộ gia đình, rác cồng kềnh, rác trơ vô cơ). "
                    "Hạn chót thực hiện bắt buộc toàn quốc là ngày 31/12/2024."
                ),
            },
            {
                "section": "Điều 79 — Nguyên tắc chi trả giá dịch vụ thu gom",
                "needs_verification": True,
                "content": (
                    "Cơ chế giá dịch vụ thu gom, vận chuyển và xử lý chất thải rắn sinh hoạt được tính dựa trên "
                    "nguyên tắc Người gây ô nhiễm phải trả tiền, định lượng theo khối lượng hoặc thể tích chất thải. "
                    "Hộ gia đình không phân loại sẽ phải trả mức phí cao hơn như đối với rác thải sinh hoạt khác."
                ),
            },
            {
                "section": "Điều 75 — Trách nhiệm Ban quản lý chung cư và Chủ đầu tư",
                "needs_verification": True,
                "content": (
                    "Ban quản lý chung cư có trách nhiệm bố trí thiết bị chứa và điểm tập kết riêng biệt cho từng "
                    "loại rác (tái chế, hữu cơ, rác khác, rác nguy hại, rác cồng kềnh). BQL có quyền từ chối tiếp nhận "
                    "chất thải của cư dân nếu không phân loại đúng quy định."
                ),
            },
        ],
    },
    {
        "title": "Nghị định 45/2022/NĐ-CP — xử phạt vi phạm hành chính trong lĩnh vực bảo vệ môi trường",
        "building_code": "",
        "doc_type": "law",
        "source": "Nghị định 45/2022/NĐ-CP",
        "effective_date": "2022-08-25",
        "chunks": [
            {
                "section": "Điều 26.1 — Mức phạt không phân loại rác tại nguồn",
                "content": (
                    "Phạt tiền từ 500.000 đồng đến 1.000.000 đồng đối với hành vi hộ gia đình, cá nhân không "
                    "phân loại chất thải rắn sinh hoạt theo quy định; không sử dụng bao bì chứa chất thải rắn sinh hoạt đúng quy chuẩn."
                ),
            },
            {
                "section": "Điều 26.2 — Phạt vứt rác bừa bãi tại chung cư và nơi công cộng",
                "needs_verification": True,
                "content": (
                    "Phạt tiền từ 500.000 đồng đến 1.000.000 đồng đối với hành vi vứt, thải, bỏ rác thải sinh hoạt, "
                    "đổ nước thải không đúng nơi quy định tại khu chung cư, thương mại, dịch vụ hoặc nơi công cộng."
                ),
            },
            {
                "section": "Điều 29 — Phạt vi phạm về quản lý rác nguy hại sinh hoạt",
                "needs_verification": True,
                "content": (
                    "Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng đối với hành vi không lưu giữ riêng chất thải nguy hại "
                    "(pin, ắc quy, bóng đèn huỳnh quang, chai lọ hóa chất) mà để lẫn vào rác sinh hoạt thông thường. "
                    "Phạt từ 5.000.000 đồng đến 10.000.000 đồng nếu xả hóa chất độc hại vào hệ thống thoát nước hoặc họng rác chung cư."
                ),
            },
        ],
    },
    {
        "title": "Hướng dẫn Kỹ thuật 9368/BTNMT-KSONMT — Phân loại chi tiết từng loại rác",
        "building_code": "",
        "doc_type": "guideline",
        "source": "Công văn số 9368/BTNMT-KSONMT ngày 02/11/2023 của Bộ TN&MT",
        "effective_date": "2023-11-02",
        "chunks": [
            {
                "section": "Nhóm Tái chế — Giấy, Hộp sữa và Bìa Carton",
                "content": (
                    "Giấy báo, sách vở, bìa carton và vỏ hộp sữa giấy (Tetra Pak) thuộc nhóm rác tái chế. "
                    "Vỏ hộp sữa chỉ cần trút hết sữa, bóp dẹp phẳng, KHÔNG cần bóc tách lớp nhôm bên trong. "
                    "Giấy dính dầu mỡ hoặc khăn giấy ướt đã dùng phải chuyển sang thùng rác khác."
                ),
            },
            {
                "section": "Nhóm Tái chế — Chai Nhựa, Ly Nhựa và Kim Loại",
                "content": (
                    "Chai nhựa PET, ly nhựa trà sữa, can nhựa HDPE, lon bia lon nước ngọt nhôm thuộc nhóm rác tái chế. "
                    "Yêu cầu: Đổ sạch nước/trân châu thừa, tráng sơ bằng nước sạch và bóp dẹp để tiết kiệm thể tích."
                ),
            },
            {
                "section": "Nhóm Rác Nguy hại — Chai Lọ Hóa Chất, Pin và Đèn Thủy Ngân",
                "content": (
                    "Chai nước tẩy bồn cầu, nước xịt muỗi, bình sơn, pin, bóng đèn huỳnh quang, thuốc hết hạn thuộc RÁC NGUY HẠI. "
                    "Tuyệt đối KHÔNG vứt vào thùng nhựa tái chế dù vỏ là nhựa. Cần đậy chặt nắp và đem xuống điểm thu gom riêng ở hầm B1."
                ),
            },
            {
                "section": "Nhóm Rác Cồng Kềnh — Đồ Quá Khổ và Nội Thất Cũ",
                "content": (
                    "Đồ cồng kềnh (sofa, nệm, giường, tủ, máy giặt, tivi) là vật phẩm có kích thước vượt 0.5m x 0.5m x 0.5m "
                    "hoặc nặng trên 10kg. Bắt buộc đăng ký trước với BQL ít nhất 24 giờ, sử dụng thang máy chở hàng và trả phí dịch vụ bốc dỡ."
                ),
            },
        ],
    },
    {
        "title": "Hướng dẫn sử dụng App GreenBin AI — Cẩm nang Cư dân",
        "building_code": "",
        "doc_type": "app_guide",
        "source": "Sổ tay người dùng GreenBin AI v1.0",
        "effective_date": "2026-01-01",
        "chunks": [
            {
                "section": "Tổng quan 5 Tab chức năng của App",
                "content": (
                    "Ứng dụng GreenBin AI gồm 5 tab chức năng chính: "
                    "(1) Phân loại: Chụp ảnh hoặc gõ chữ để AI nhận diện nhóm rác và hướng dẫn màu thùng; "
                    "(2) Yêu cầu: Đặt lịch thu gom đồ cồng kềnh (sofa, nệm, tủ) và theo dõi tiến độ; "
                    "(3) Lịch: Xem lịch thu gom rác toà nhà (hoạt động được cả khi mất mạng); "
                    "(4) Điểm gửi: Bản đồ thùng rác thông minh gần nhất với mức đầy thời gian thực; "
                    "(5) Tôi: Quản lý điểm thưởng xanh Green Points, đổi căn hộ và lịch sử phân loại."
                ),
            },
            {
                "section": "Cách Phân loại Rác bằng Ảnh và Chữ",
                "content": (
                    "Để phân loại rác: Vào tab 'Phân loại'. Bạn có thể chụp ảnh hoặc gõ mô tả chữ. "
                    "Khi chụp ảnh, giữ thẳng camera, đủ sáng. AI sẽ trả về nhóm rác, màu thùng cần bỏ, "
                    "hướng dẫn xử lý sơ bộ và trích dẫn quy định toà nhà. Nếu nhiều món rác trong ảnh, AI sẽ liệt kê từng món."
                ),
            },
            {
                "section": "Cách Đặt lịch Thu gom Đồ Cồng Kềnh",
                "content": (
                    "Để đăng ký thu gom đồ cồng kềnh: Vào tab 'Yêu cầu' > Bấm 'Tạo yêu cầu mới' > Chọn loại đồ "
                    "(nội thất, nệm, sofa), chụp ảnh và ước tính số lượng > Chọn ngày & khung giờ mong muốn > Gửi yêu cầu. "
                    "Bạn có thể theo dõi 10 trạng thái từ 'Chờ duyệt', 'Đã xếp tuyến' cho tới 'Hoàn tất'."
                ),
            },
            {
                "section": "Tra cứu Thùng Rác Thông Minh và Điểm Gửi",
                "content": (
                    "Vào tab 'Điểm gửi' để xem bản đồ các thùng rác thông minh. Bạn có thể lọc theo loại rác tái chế "
                    "(nhựa, giấy, kim loại), xem khoảng cách thực tế, và xem mức đầy theo màu "
                    "(Xanh = Còn chỗ <70%, Vàng = Sắp đầy 70-90%, Đỏ = Đã đầy >90% hoặc Mất kết nối)."
                ),
            },
            {
                "section": "Điểm Xanh Green Points và Quyền Riêng Tư",
                "content": (
                    "Mỗi lần phân loại đúng và gửi rác tái chế, bạn được cộng Điểm Xanh (Green Points) hiển thị ở tab 'Tôi'. "
                    "Tại tab này bạn cũng có thể xem lịch sử phân loại, đổi thông tin căn hộ, và kiểm tra chính sách bảo mật "
                    "(ảnh chụp được tự động che mặt và xoá tạm thời sau khi xử lý)."
                ),
            },
        ],
    },
]


# --- Giới hạn đã biết của hệ thống ---------------------------------------
# Text cứng, luôn hiển thị trên trang Vận hành và trên màn kết quả (spec 4.16).
# Đây là phần đáp thẳng yêu cầu "nêu rõ giới hạn, rủi ro" của chương trình.

KNOWN_LIMITATIONS: list[str] = [
    "Nhận diện tốt nhất với một món rác, chụp rõ, đủ sáng. Ảnh nhiều món chồng lên nhau có độ chính xác thấp hơn đáng kể.",
    "Không nhìn xuyên được túi nilon đục — rác đã đóng túi kín nằm ngoài phạm vi xử lý của hệ thống, có chủ đích.",
    "Không phân biệt được nhựa PET và nhựa HDPE khi nhãn bị mờ hoặc mất.",
    "Không xác định được rác y tế lây nhiễm — luôn chuyển người, không tự trả lời.",
    "Quy định phân loại khác nhau giữa các toà; hướng dẫn chỉ đúng với toà đang chọn.",
    "Khối lượng do cư dân tự nhập ước tính, hệ thống để dung sai ±40% — chỉ dùng để gợi ý, đội vệ sinh cân lại tại chỗ.",
    "Dữ liệu demo là dữ liệu mô phỏng và ảnh tự chụp, không phải dữ liệu cư dân thật.",
    "Ảnh tải lên từ 16/08/2026 được lưu trên Supabase Storage nên bền vững; ảnh tải lên trước thời điểm đó vẫn nằm ở đĩa tạm và sẽ mất khi máy chủ khởi động lại.",
    "Tầng T0.5 trên bản deploy chạy bản CLIP đã nén (int8) để vừa bộ nhớ máy chủ miễn phí. "
    "Bản nén cho điểm số lệch so với bản đầy đủ, và ngưỡng chấp nhận CHƯA được chuẩn lại "
    "trên bộ ảnh thật — bảng Cấu hình model bên dưới cho biết đang chạy bản nào.",
]

# Lý do từ chối yêu cầu thu gom — danh sách cố định, không cho gõ tự do, để dữ
# liệu chảy ngược vào trang Chất lượng AI (PLO 7).
PICKUP_REJECT_REASONS: list[dict[str, str]] = [
    {"code": "vuot_nang_luc", "label_vi": "Vượt năng lực xử lý trong ngày"},
    {"code": "co_rac_nguy_hai", "label_vi": "Có rác nguy hại cần quy trình riêng"},
    {"code": "thieu_thong_tin", "label_vi": "Thông tin không đủ"},
    {"code": "trung_yeu_cau", "label_vi": "Trùng với yêu cầu đã có"},
    {"code": "sai_dia_chi", "label_vi": "Sai địa chỉ hoặc căn hộ"},
    {"code": "khac", "label_vi": "Khác (ghi rõ)"},
]

# Các cặp nhãn hay bị nhầm, ghim trên đầu hàng đợi xác nhận nhãn (spec 4.11).
HARD_CASES: list[dict[str, str]] = [
    {"pair": "Hộp sữa giấy tráng nhôm ↔ Giấy", "note": "Lớp tráng nhôm làm model nghiêng về nhóm kim loại"},
    {"pair": "Ly nhựa có màng ↔ Nhựa tái chế", "note": "Màng dán miệng ly thường bị bỏ qua khi chụp từ trên xuống"},
    {"pair": "Khay cơm dính dầu ↔ Rác thực phẩm", "note": "Khay bẩn không còn tái chế được nhưng nhìn vẫn giống nhựa sạch"},
]
