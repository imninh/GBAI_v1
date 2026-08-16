"""Khoá cửa cho hợp đồng trạng thái ở TypeScript (gói P32).

Quét file frontend dưới dạng văn bản, đúng khuôn ``test_di_tru_trang_thai.py``:
không import TypeScript, chỉ cắt thân khối và so chuỗi.

Ba thứ được giữ bằng test:
* ``PickupRequest.status`` phải dùng từ vựng MỚI (qua ``TrangThaiYeuCau``), trong
  khi ``PickupRoute.status`` vẫn là từ vựng TUYẾN — hai máy trạng thái khác nhau;
* mọi chuỗi trạng thái yêu cầu dùng trong component cư dân phải có trong
  ``NHAN_TRANG_THAI_YEU_CAU``;
* hàng đợi nhãn có ``AnhCoToken`` + ``media_id``, và ba trường xác nhận khối
  lượng đã khai trong ``PickupRequest``.
"""

from __future__ import annotations

import re
from pathlib import Path

GOC_DU_AN = Path(__file__).resolve().parents[1]

TU_VUNG_CU = ["pending", "approved", "rejected", "scheduled"]
TU_VUNG_TUYEN = ["proposed", "approved", "in_progress", "done", "cancelled"]

TEP_TYPES = GOC_DU_AN / "frontend" / "src" / "lib" / "types.ts"
TEP_PICKUP_STATES = GOC_DU_AN / "frontend" / "src" / "lib" / "pickup-states.ts"
TEP_QUEUES = GOC_DU_AN / "frontend" / "src" / "components" / "manager" / "queues.tsx"
TEP_PERSONAL = GOC_DU_AN / "frontend" / "src" / "components" / "resident" / "personal.tsx"


def _than_interface(noi_dung: str, ten: str) -> str:
    """Thân ``interface {ten} { ... }``, tính độ sâu ngoặc. Rỗng nếu không có."""
    bat_dau = noi_dung.find(f"interface {ten} {{")
    if bat_dau == -1:
        return ""
    mo = noi_dung.find("{", bat_dau) + 1
    do_sau = 1
    for i in range(mo, len(noi_dung)):
        ky_tu = noi_dung[i]
        if ky_tu == "{":
            do_sau += 1
        elif ky_tu == "}":
            do_sau -= 1
            if do_sau == 0:
                return noi_dung[mo:i]
    return ""


def _than_ham(noi_dung: str, ten: str) -> str:
    """Thân hàm ``function {ten}`` tới ngoặc đóng đầu tiên. Rỗng nếu không có."""
    bat_dau = noi_dung.find(f"function {ten}")
    if bat_dau == -1:
        return ""
    mo = noi_dung.find("{", bat_dau) + 1
    do_sau = 1
    for i in range(mo, len(noi_dung)):
        ky_tu = noi_dung[i]
        if ky_tu == "{":
            do_sau += 1
        elif ky_tu == "}":
            do_sau -= 1
            if do_sau == 0:
                return noi_dung[mo:i]
    return ""


def _dong_status(than: str) -> str:
    """Dòng khai ``status:`` trong một thân interface/hàm."""
    trung_khop = re.search(r"^\s*status:\s*(.+)$", than, re.MULTILINE)
    assert trung_khop is not None, "Không tìm thấy dòng status: trong khối"
    return trung_khop.group(1)


def _khoa_trang_thai_yeu_cau() -> set[str]:
    """Đọc các khoá của ``NHAN_TRANG_THAI_YEU_CAU`` từ nguồn sự thật."""
    noi_dung = TEP_PICKUP_STATES.read_text(encoding="utf-8")
    bat_dau = noi_dung.find("NHAN_TRANG_THAI_YEU_CAU")
    assert bat_dau != -1, "pickup-states.ts thiếu NHAN_TRANG_THAI_YEU_CAU"
    mo = noi_dung.find("{", bat_dau) + 1
    do_sau = 1
    for i in range(mo, len(noi_dung)):
        ky_tu = noi_dung[i]
        if ky_tu == "{":
            do_sau += 1
        elif ky_tu == "}":
            do_sau -= 1
            if do_sau == 0:
                than = noi_dung[mo:i]
                return set(re.findall(r"^\s*([a-z_]+):", than, re.MULTILINE))
    return set()


# --- PickupRequest vs PickupRoute — hai máy trạng thái khác nhau ------------


def test_pickuprequest_khong_con_tu_vung_trang_thai_cu() -> None:
    """`PickupRequest.status` không còn chứa 4 từ vựng cũ.

    Chỉ quét THÂN interface PickupRequest — `PickupRoute` ngay bên dưới dùng hợp
    lệ `approved`/`done`/`cancelled`, quét cả file là đỏ nhầm.
    """
    than = _than_interface(TEP_TYPES.read_text(encoding="utf-8"), "PickupRequest")
    dong_status = _dong_status(than)

    for tu in TU_VUNG_CU:
        assert tu not in dong_status, f"PickupRequest.status còn chứa từ vựng cũ '{tu}': {dong_status}"


def test_pickuproute_van_giu_tu_vung_tuyen() -> None:
    """Mặt còn lại: `PickupRoute.status` VẪN là từ vựng tuyến — không đổi."""
    than = _than_interface(TEP_TYPES.read_text(encoding="utf-8"), "PickupRoute")
    dong_status = _dong_status(than)

    for tu in TU_VUNG_TUYEN:
        assert tu in dong_status, f"PickupRoute.status phải giữ '{tu}': {dong_status}"


# --- Từ vựng dùng thật trong component cư dân -------------------------------


def test_moi_khoa_trang_thai_yeu_cau_deu_co_trong_pickup_states() -> None:
    """Mọi chuỗi trạng thái yêu cầu so trong component cư dân đều có nhãn.

    Bắt được lớp lỗi này lần sau, không chỉ lần này: một cú `status === "..."`
    viết tay kiểu cũ sẽ lọt vào đây và đỏ ngay.
    """
    cac_khoa = _khoa_trang_thai_yeu_cau()
    assert len(cac_khoa) >= 9, f"Đọc được ít khoá trạng thái: {cac_khoa}"

    cac_ma: set[str] = set()
    thu_muc = GOC_DU_AN / "frontend" / "src" / "components" / "resident"
    for tep in sorted(thu_muc.rglob("*.tsx")):
        noi_dung = tep.read_text(encoding="utf-8")
        for trung_khop in re.finditer(r'\.status\s*(?:as\s+string)?\s*(?:===|!==)\s*"([a-z_]+)"', noi_dung):
            cac_ma.add(trung_khop.group(1))

    assert cac_ma, "Không rút được trạng thái nào từ component cư dân — regex có thể lệch thực tế"
    thieu = [ma for ma in sorted(cac_ma) if ma not in cac_khoa]
    assert thieu == [], f"Trạng thái dùng nhưng không có trong NHAN_TRANG_THAI_YEU_CAU: {thieu}"


# --- Ép kiểu chỉ còn tồn tại khi types.ts khai sai --------------------------


def test_khong_con_ep_kieu_status_as_string() -> None:
    """`personal.tsx` không còn `status as string`.

    Cú ép đó tồn tại CHỈ VÌ `types.ts` khai từ vựng chết; vá xong thì nó phải
    biến mất. ⚠️ File này do gói P27 giữ (chỉ đọc) — nếu test đỏ nghĩa là cú ép
    còn đó và là tín hiệu để chủ gói quyết, không phải lỗi của gói này.
    """
    noi_dung = TEP_PERSONAL.read_text(encoding="utf-8")
    assert "status as string" not in noi_dung, "personal.tsx còn ép kiểu status as string"


# --- Hàng đợi nhãn có ảnh ---------------------------------------------------


def test_hang_doi_nhan_co_anh() -> None:
    """Thân `VerifyQueue` phải có `AnhCoToken` và `media_id`."""
    than = _than_ham(TEP_QUEUES.read_text(encoding="utf-8"), "VerifyQueue")
    assert than, "Không tìm thấy hàm VerifyQueue trong queues.tsx"
    assert "AnhCoToken" in than, "VerifyQueue chưa dùng AnhCoToken"
    assert "media_id" in than, "VerifyQueue chưa đọc media_id của ca"


# --- Ba trường xác nhận khối lượng -------------------------------------------


def test_ba_truong_xac_nhan_da_khai() -> None:
    """`PickupRequest` khai đủ ba trường xác nhận backend trả từ gói P29."""
    than = _than_interface(TEP_TYPES.read_text(encoding="utf-8"), "PickupRequest")
    for truong in ("weight_confirmed_kg", "confirmed_by", "confirmed_at"):
        assert truong in than, f"PickupRequest thiếu trường '{truong}'"
