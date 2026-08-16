"""Nhập bộ dữ liệu GIS Hà Nội (gói P30) — 8 test, không test nào chạm mạng.

Test 7 (``is_seed``) là chốt chặn chính: 60 thùng là vị trí ĐỀ XUẤT với độ tin
cậy toạ độ MEDIUM, phải mang nhãn "dữ liệu demo mô phỏng" trên mọi màn hình.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.nhap_gis_hanoi import nhap_thung
from src.db.models import Bin
from src.db.schema_patch import COT_CAN_VA

GOC_DU_AN = Path(__file__).resolve().parents[2]
THUNG_CSV = GOC_DU_AN / "data" / "samples" / "gis_hanoi_thung.csv"

COT_GIS = {
    "site_type",
    "priority",
    "deployment_status",
    "coordinate_confidence",
    "area_name",
}


def _dem_thung_gis(session: Session) -> int:
    return len(session.scalars(select(Bin).where(Bin.code.like("BIN-0%"))).all())


def test_nhap_du_60_thung(db_session: Session) -> None:
    ket_qua = nhap_thung(db_session)
    db_session.commit()

    assert ket_qua["so_thung_moi"] == 60, ket_qua
    assert _dem_thung_gis(db_session) == 60, "Phải nhập đủ 60 thùng mã BIN-0xx"


def test_chay_lai_khong_nhan_doi(db_session: Session) -> None:
    nhap_thung(db_session)
    db_session.commit()
    lan_hai = nhap_thung(db_session)
    db_session.commit()

    assert _dem_thung_gis(db_session) == 60, "Chạy lại không được nhân đôi thùng"
    bin_002 = db_session.scalar(select(Bin).where(Bin.code == "BIN-002"))
    assert bin_002 is not None
    assert bin_002.name == "Quảng trường Đông Kinh Nghĩa Thục"
    assert lan_hai["so_thung_cap_nhat"] == 60, "Lần hai phải là cập nhật, không phải tạo mới"


def test_khong_dung_toi_thung_demo_cu(db_session: Session) -> None:
    demo_cu = Bin(code="BIN-01", name="Thùng demo cũ", is_active=True, is_seed=True)
    db_session.add(demo_cu)
    db_session.flush()

    nhap_thung(db_session)
    db_session.commit()

    bin_01 = db_session.scalar(select(Bin).where(Bin.code == "BIN-01"))
    assert bin_01 is not None, "Thùng demo cũ không được bị xoá"
    assert bin_01.name == "Thùng demo cũ", "Thùng demo cũ (mã hai chữ số) không được bị sửa"


def test_kiem_tra_khong_ghi_gi(db_session: Session) -> None:
    ket_qua = nhap_thung(db_session, kiem_tra=True)

    assert ket_qua["so_thung_moi"] == 60, "Chế độ kiểm tra phải đếm được sẽ làm gì"
    assert _dem_thung_gis(db_session) == 0, "--kiem-tra không được tạo thùng nào"


def test_hang_thieu_toa_do_bi_bo_qua(db_session: Session, tmp_path: Path) -> None:
    duong = tmp_path / "thieu_toa_do.csv"
    duong.write_text(
        "bin_id,anchor_name,address_anchor,legacy_area,latitude,longitude,site_type,priority,suggested_capacity_l,"
        "suggested_distance_m,deployment_status,coordinate_confidence,notes\n"
        "BIN-999,Điểm thiếu toạ độ,Đường X,Hoàn Kiếm,,105.85,commercial,P1,240,150,PROPOSED,MEDIUM,none\n",
        encoding="utf-8",
    )

    ket_qua = nhap_thung(db_session, duong_dan_csv=duong)
    db_session.commit()

    assert ket_qua["so_bo_qua"] == 1, ket_qua
    assert ket_qua["so_thung_moi"] == 0
    assert db_session.scalar(select(Bin).where(Bin.code == "BIN-999")) is None, "Thiếu toạ độ thì không tạo thùng"


def test_dung_tich_va_khu_vuc_vao_dung_cot(db_session: Session) -> None:
    nhap_thung(db_session)
    db_session.commit()

    bin_002 = db_session.scalar(select(Bin).where(Bin.code == "BIN-002"))
    assert bin_002 is not None
    assert bin_002.capacity_liters == 240, "suggested_capacity_l phải vào cột capacity_liters"
    assert bin_002.area_name == "Hoàn Kiếm", "legacy_area phải vào cột area_name"


def test_moi_thung_nhap_deu_la_du_lieu_mo_phong(db_session: Session) -> None:
    """Chốt chặn chính: 60 thùng GIS là vị trí ĐỀ XUẤT, phải gắn cờ is_seed=True.

    Toàn bộ dòng CSV đều mang ``deployment_status = PROPOSED`` và
    ``coordinate_confidence = MEDIUM`` (đọc trong ``gis_hanoi_nguon.txt``) —
    chưa khảo sát thực địa, chưa phải thùng có thật ngoài đường. Gắn
    ``is_seed=False`` là tắt nhãn "dữ liệu demo mô phỏng" cho 60 thùng trên màn
    điều phối, khiến sản phẩm trình bày vị trí đề xuất như thể hạ tầng đang vận
    hành — số mô phỏng và số thật trộn vào nhau mà không nói gì.
    """
    nhap_thung(db_session)
    db_session.commit()

    cac_thung_gis = db_session.scalars(select(Bin).where(Bin.code.like("BIN-0%"))).all()
    assert len(cac_thung_gis) == 60
    khong_nhan = [t.code for t in cac_thung_gis if not t.is_seed]
    assert khong_nhan == [], f"60 thùng GIS phải là is_seed=True, thiếu nhãn: {khong_nhan}"


def test_cot_gis_da_khai_vao_cot_can_va() -> None:
    """Chặn cái bẫy hạ tầng: quên khai COT_CAN_VA thì test vẫn xanh mà CSDL thật thiếu cột."""
    cap_bang_cot = {(bang, cot) for bang, cot, _ in COT_CAN_VA}
    thieu = {cot for cot in COT_GIS if ("bins", cot) not in cap_bang_cot}
    assert thieu == set(), f"Thiếu cột GIS trong COT_CAN_VA: {thieu}"
