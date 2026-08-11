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
