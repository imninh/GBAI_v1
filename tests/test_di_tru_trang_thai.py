"""Khoá cửa cho đợt di trú từ vựng trạng thái của PickupRequest.

Quét **dưới dạng văn bản** toàn bộ ``src/`` và ``scripts/`` và khẳng định không
file nào còn **gán** một giá trị trạng thái CŨ cho ``request.status`` hay cho
keyword ``status=`` khi dựng một ``PickupRequest``. Nếu test này đỏ, nghĩa là
một gói trước đó bỏ sót một chỗ — báo file và dòng, đừng sửa test.

Test cố ý **BỎ QUA**:
- ``route.status`` / ``PickupRoute(status=...)`` — tuyến là một máy trạng thái
  KHÁC, vẫn giữ từ vựng cũ ``proposed | approved | done | in_progress | cancelled``;
- ``PickupEvent(kind="cancelled")`` — đó là loại sự kiện, không phải trạng thái.
"""

from __future__ import annotations

import re
from pathlib import Path

GOC_DU_AN = Path(__file__).resolve().parents[1]

GIA_TRI_CU = ["pending", "approved", "scheduled", "done", "cancelled", "rejected"]

# Pattern gán trạng thái cũ cho request.status.
RE_GAN_REQUEST_STATUS = re.compile(
    r'request\.status\s*=\s*"(pending|approved|scheduled|done|cancelled|rejected)"'
)
# Pattern gán trạng thái cũ qua keyword status= khi dựng PickupRequest.
RE_STATUS_PICKUP_REQUEST = re.compile(
    r"PickupRequest\s*\(\s*.*?status\s*=\s*\"(pending|approved|scheduled|done|cancelled|rejected)\"",
    re.DOTALL,
)


def _cac_file_py() -> list[Path]:
    cac_file: list[Path] = []
    for thu_muc in (GOC_DU_AN / "src", GOC_DU_AN / "scripts"):
        cac_file.extend(sorted(thu_muc.rglob("*.py")))
    return cac_file


def test_khong_con_chỗ_gan_gia_tri_cu_cho_request_status() -> None:
    """Không file nào được gán giá trị cũ cho ``request.status``.

    Lọc bỏ cú pháp ``==`` (so sánh) — chỉ đánh dấu cú pháp GÁN ``=``, nơi trạng
    thái cũ thực sự đi vào cơ sở dữ liệu.
    """
    vi_pham: list[str] = []
    for file in _cac_file_py():
        noi_dung = file.read_text(encoding="utf-8")
        for dong in noi_dung.splitlines():
            if RE_GAN_REQUEST_STATUS.search(dong):
                vi_pham.append(f"{file.relative_to(GOC_DU_AN)}:{dong.strip()}")

    assert vi_pham == [], "Còn chỗ gán giá trị trạng thái cũ cho request.status:\n" + "\n".join(vi_pham)


def test_khong_con_chỗ_gan_gia_tri_cu_qua_status_keyword_cho_pickup_request() -> None:
    """Không file nào dựng ``PickupRequest(status="giá trị cũ")``.

    Bỏ qua ``PickupRoute`` — mỗi pattern của ``PickupRequest`` có tên bảng riêng.
    """
    vi_pham: list[str] = []
    for file in _cac_file_py():
        noi_dung = file.read_text(encoding="utf-8")
        for trung_khop in RE_STATUS_PICKUP_REQUEST.finditer(noi_dung):
            dong = noi_dung[: trung_khop.start()].count("\n") + 1
            vi_pham.append(f"{file.relative_to(GOC_DU_AN)}:{dong}")

    assert vi_pham == [], "Còn chỗ dựng PickupRequest với status= giá trị cũ:\n" + "\n".join(vi_pham)


def test_khong_con_chuoi_trang_thai_cu_gan_cho_request_status_trong_scripts_seed() -> None:
    """Riêng ``scripts/seed.py``: không giá trị cũ nào lọt vào tuple kế hoạch demo."""
    noi_dung = (GOC_DU_AN / "scripts" / "seed.py").read_text(encoding="utf-8")
    for gia_tri in GIA_TRI_CU:
        assert f'("{gia_tri}")' not in noi_dung, f"seed.py còn chứa tuple trạng thái cũ '{gia_tri}'"


# --- Gói P24: nửa giao diện của đợt di trú nằm ở frontend/ ---------------------


def _cac_file_frontend() -> list[Path]:
    """Mọi file ``.ts`` / ``.tsx`` dưới ``frontend/src`` — nơi giao diện sống."""
    cac_file: list[Path] = []
    goc = GOC_DU_AN / "frontend" / "src"
    if goc.is_dir():
        cac_file.extend(sorted(goc.rglob("*.ts")))
        cac_file.extend(sorted(goc.rglob("*.tsx")))
    return cac_file


def _than_tb_trang_thai(noi_dung: str) -> str:
    """Thân khối ``TRANG_THAI_YEU_CAU = { ... }``, tính độ sâu ngoặc.

    Mở đầu là ``{`` ngay sau dấu ``=`` (không phải ``{`` trong chú thích kiểu
    ``Record<...>``, thứ nằm trước ``=``). Trả về chuỗi rỗng nếu file không khai
    báo bảng này — các file còn lại khỏi bị quét.
    """
    bat_dau = noi_dung.find("TRANG_THAI_YEU_CAU")
    if bat_dau == -1:
        return ""
    bang = noi_dung.find("= {", bat_dau)
    if bang == -1:
        return ""
    mo = bang + 2
    do_sau = 0
    for i in range(mo, len(noi_dung)):
        ky_tu = noi_dung[i]
        if ky_tu == "{":
            do_sau += 1
        elif ky_tu == "}":
            do_sau -= 1
            if do_sau == 0:
                return noi_dung[mo:i]
    return ""


RE_KHOA_CU_DAU_DONG = re.compile(r"^\s*(pending|approved|scheduled|done|cancelled|rejected)\s*:")


def test_frontend_khong_con_tu_vung_trang_thai_cu() -> None:
    """Không file frontend nào còn dùng 6 khoá cũ trong bảng trạng thái yêu cầu.

    Chỉ quét **thân khối khai báo** ``TRANG_THAI_YEU_CAU = { ... }``, KHÔNG quét
    cả file: ``approved`` · ``done`` · ``cancelled`` vẫn là từ vựng HỢP LỆ của
    máy trạng thái TUYẾN (``TRANG_THAI_TUYEN``, ``route.status``) — quét cả file
    là đỏ nhầm. Bảng trạng thái yêu cầu là thứ duy nhất phải giữ từ vựng MỚI.
    """
    vi_pham: list[str] = []
    for tep in _cac_file_frontend():
        than = _than_tb_trang_thai(tep.read_text(encoding="utf-8"))
        if not than:
            continue
        for dong in than.splitlines():
            if RE_KHOA_CU_DAU_DONG.search(dong):
                vi_pham.append(f"{tep.relative_to(GOC_DU_AN)}:{dong.strip()}")
    assert vi_pham == [], (
        "Còn bảng trạng thái yêu cầu dùng khoá cũ trong frontend:\n" + "\n".join(vi_pham)
    )


RE_TRANG_THAI_NGUON_THAT = re.compile(r"^[A-Z_]+\s*=\s*\"([a-z_]+)\"\s*$", re.MULTILINE)


def _cac_trang_thai_tu_may_trang_thai() -> list[str]:
    """Đọc 10 trạng thái từ ``src/services/pickup_lifecycle.py`` — nguồn sự thật.

    Pattern khớp đúng các dòng ``MOI_TAO = "moi_tao"`` … ``DA_HUY = "da_huy"``;
    ``CHUYEN_TIEP`` / ``NHAN_VI`` là dict nên không lọt vào.
    """
    noi_dung = (GOC_DU_AN / "src" / "services" / "pickup_lifecycle.py").read_text(encoding="utf-8")
    return [trung_khop.group(1) for trung_khop in RE_TRANG_THAI_NGUON_THAT.finditer(noi_dung)]


def test_bang_trang_thai_frontend_phu_du_may_trang_thai() -> None:
    """``format.ts`` phải phủ hết trạng thái của máy trạng thái yêu cầu.

    Đọc danh sách trạng thái từ ``pickup_lifecycle.py`` (nguồn sự thật) chứ không
    chép tay một danh sách thứ hai. Loại ``moi_tao`` vì nó không bao giờ tới được
    giao diện: ``create_pickup_request`` gán ngay ``cho_duyet``/``cho_nhan`` khi
    tạo (pickup.py:175), không trạng thái nào được lưu hay trả về ở ``moi_tao``.
    """
    cac_trang_thai = _cac_trang_thai_tu_may_trang_thai()
    assert len(cac_trang_thai) == 10, f"Kỳ vọng 10 trạng thái, đọc được {cac_trang_thai}"
    noi_dung = (GOC_DU_AN / "frontend" / "src" / "lib" / "format.ts").read_text(encoding="utf-8")
    thieu = [t for t in cac_trang_thai if t != "moi_tao" and f"{t}:" not in noi_dung]
    assert thieu == [], f"format.ts thiếu trạng thái yêu cầu (sẽ rơi vào giá trị lui): {thieu}"
