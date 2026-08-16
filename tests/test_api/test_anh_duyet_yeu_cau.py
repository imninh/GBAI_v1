"""Khoá cửa cho gói P40 — hàng đợi duyệt phải cho người duyệt NHÌN được món đồ.

Trước gói này `PickupQueue` (HITL #1) hiện mỗi món bằng một ô sọc CSS giả — người
duyệt bấm "chấp nhận" một yêu cầu đồ cồng kềnh mà chưa từng thấy món đồ. Nay thay
ô sọc bằng `AnhCoToken` (đã có từ gói P27, đang dùng ở `VerifyQueue` cùng file) với
`media_id` mà backend đã trả sẵn nhưng frontend bỏ rơi.

Quét **thân đúng một hàm** trong `queues.tsx` bằng khuôn các gói trước (tìm điểm
mở, đếm độ sâu ngoặc tới điểm đóng) — file có 4 hàng đợi gần giống nhau, quét cả
file là đỏ nhầm. Không test nào chạm mạng, không chạm trình duyệt.
"""

from __future__ import annotations

from pathlib import Path

GOC_DU_AN = Path(__file__).resolve().parents[2]
TEP_QUEUES = GOC_DU_AN / "frontend" / "src" / "components" / "manager" / "queues.tsx"
TEP_TYPES = GOC_DU_AN / "frontend" / "src" / "lib" / "types.ts"


def _than_khoi(noi_dung: str, ten: str) -> str:
    """Thân khối bắt đầu sau token `ten`, tính độ sâu ngoặc tới ngoặc đóng cân bằng.

    Trả về chuỗi rỗng khi không tìm thấy. Cách cắt này lặp lại khuôn các gói
    trước (P28/P34): tìm điểm mở rồi đếm `{`/`}`.
    """
    bat_dau = noi_dung.find(ten)
    if bat_dau == -1:
        return ""
    mo = noi_dung.find("{", bat_dau)
    if mo == -1:
        return ""
    do_sau = 0
    for i in range(mo, len(noi_dung)):
        ky_tu = noi_dung[i]
        if ky_tu == "{":
            do_sau += 1
        elif ky_tu == "}":
            do_sau -= 1
            if do_sau == 0:
                return noi_dung[mo + 1 : i]
    return ""


def _noi_dung_queues() -> str:
    return TEP_QUEUES.read_text(encoding="utf-8")


def _than_pickup_queue() -> str:
    return _than_khoi(_noi_dung_queues(), "function PickupQueue")


def test_pickupqueue_dung_anh_that() -> None:
    """`PickupQueue` không còn ô sọc giả cho món đồ — phải dùng `AnhCoToken`.

    Ô ``repeating-linear-gradient`` là chỗ người duyệt NHÌN THẤY món đồ; thay nó
    bằng ảnh thật là điểm của cả gói. Quét thân đúng `PickupQueue`, không quét cả
    file (các hàng đợi khác không liên quan).
    """
    than = _than_pickup_queue()
    assert than, "Không tìm thấy thân hàm PickupQueue"
    assert "repeating-linear-gradient" not in than, "Ô sọc giả còn nằm trong khối món đồ"
    assert "<AnhCoToken" in than, "Phải dùng AnhCoToken để hiện ảnh món đồ"


def test_pickupqueue_truyen_media_id() -> None:
    """`AnhCoToken` trong `PickupQueue` phải nhận `mediaId={m.media_id}`."""
    than = _than_pickup_queue()
    assert "mediaId={m.media_id}" in than, "AnhCoToken phải nhận mediaId từ item của yêu cầu"


def test_pickupitem_type_co_media_id() -> None:
    """Item của `PickupRequest` trong `types.ts` phải khai `media_id`.

    Backend đã trả `media_id` sẵn (serializers.pickup_dict) — thêm trường này chỉ
    để TypeScript đọc được. Quét riêng khối `PickupRequest`, không đụng
    `Classification.items` (kiểu khác) hay `RouteStop.items`.
    """
    noi_dung = TEP_TYPES.read_text(encoding="utf-8")
    than = _than_khoi(noi_dung, "PickupRequest")
    assert than, "Không tìm thấy khối PickupRequest trong types.ts"
    dong_items = next((d for d in than.splitlines() if "items:" in d), "")
    assert dong_items, "Không tìm thấy khai báo items của PickupRequest"
    assert "media_id" in dong_items, f"Item của PickupRequest phải khai media_id — gặp: {dong_items.strip()}"


def test_van_dung_lai_anhcotoken_co_san() -> None:
    """`queues.tsx` phải dùng lại `AnhCoToken` — không được viết component ảnh mới."""
    noi_dung = _noi_dung_queues()
    assert 'from "@/lib/anh-co-token"' in noi_dung, "Phải import AnhCoToken từ anh-co-token"
    assert "function AnhCoToken" not in noi_dung, "Không được tự định nghĩa component ảnh"
    assert "const AnhCoToken" not in noi_dung, "Không được tự định nghĩa component ảnh"


def test_verifyqueue_khong_bi_dung_toi() -> None:
    """Khối ảnh của `VerifyQueue` (hàng đợi nhãn) không bị đụng tới.

    `VerifyQueue` tải ảnh LAZY — chỉ dựng `<AnhCoToken>` khi người duyệt mở một
    thẻ (`dangMo === ca.classification_id`). Cổng này là của gói P28/P32; gói này
    chỉ được sửa `PickupQueue`, đụng tới VerifyQueue là hồi quy.
    """
    than = _than_khoi(_noi_dung_queues(), "function VerifyQueue")
    assert than, "Không tìm thấy thân hàm VerifyQueue"
    assert "dangMo === ca.classification_id" in than, "Cổng lazy của VerifyQueue bị đụng tới"
