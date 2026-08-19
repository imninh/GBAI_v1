"""Khoá cửa cho màn "Tất cả yêu cầu" — trạng thái không màn nào hiện không được trôi.

Hàng đợi duyệt chỉ thấy ``cho_duyet``/``pending``, màn Xếp tuyến chỉ thấy
``cho_nhan``; yêu cầu ở ``da_nhan``/``hoan_tat``/``da_giao_don_vi`` không màn nào
hiện nên người quản lý tưởng là mất. Quét văn bản (khuôn
``test_anh_duyet_yeu_cau.py``) để chốt: màn mới tồn tại · gọi ``api.pickups`` ·
console nối đủ import + mục sidebar + nhánh render. Không chạm mạng, không chạm
trình duyệt.
"""

from __future__ import annotations

from pathlib import Path

GOC_DU_AN = Path(__file__).resolve().parents[1]
TEP_MAN = GOC_DU_AN / "frontend" / "src" / "components" / "manager" / "tat-ca-yeu-cau.tsx"
TEP_CONSOLE = GOC_DU_AN / "frontend" / "src" / "components" / "manager" / "console.tsx"


def test_man_tat_ca_ton_tai() -> None:
    assert TEP_MAN.is_file(), "Màn 'Tất cả yêu cầu' chưa được tạo"


def test_man_goi_api_pickups_kem_phan_trang() -> None:
    noi_dung = TEP_MAN.read_text(encoding="utf-8")
    assert ".pickups(" in noi_dung, "Màn phải gọi api.pickups (endpoint đã có, không thêm mới)"
    assert "page_size" in noi_dung, "Phải dùng phân trang page_size để không tải cả kho lúc nào cũng vậy"
    assert "NHAN_TRANG_THAI_YEU_CAU" in noi_dung, "Nhãn trạng thái phải lấy từ lib/pickup-states, không tự bịa"


def test_console_noi_du_muc_tat_ca() -> None:
    noi_dung = TEP_CONSOLE.read_text(encoding="utf-8")
    assert "from \"@/components/manager/tat-ca-yeu-cau\"" in noi_dung, "console phải import màn Tất cả yêu cầu"
    assert '"tat_ca"' in noi_dung, "Nav phải khai mục tat_ca"
    assert '"view_all_pickups"' in noi_dung, "Mục sidebar phải dùng quyền view_all_pickups"
    assert 'nav === "tat_ca"' in noi_dung, "Phải có nhánh render cho nav tat_ca"
