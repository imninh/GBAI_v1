"""Test script nhập/cập nhật cư dân GIS (gói P56, cập nhật P62) — không gọi CSDL thật.

Dùng CSDL SQLite trong bộ nhớ (fixture ``db_session`` của ``tests/conftest.py``)
và workbook giả dựng ngay trong test bằng openpyxl — không đọc file ``.xlsx``
thật, không chạy script, không gọi mạng.

Gói P62 đổi nguồn địa chỉ: cư dân được **rải đều vào các toà** (có ``lat``/``lng``)
thay vì dùng địa chỉ phố bịa của workbook. Test (b) là quan trọng nhất: khẳng định
mật khẩu băm đúng kiểu PBKDF2 nên đăng nhập được bằng mật khẩu gốc của workbook.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.nhap_cu_dan_gis import _cot_con_thieu, nhap_va_cap_nhat_cu_dan
from src.db.models import Building, User
from src.services.security import verify_password

TIEU_DE = [
    "resident_id",
    "home_address_simulated",
    "legacy_area",
    "latitude",
    "longitude",
    "nearest_bin_id",
    "distance_to_bin_m",
    "household_size",
    "waste_kg_day_est",
    "data_status",
    "privacy_note",
    "login_phone",
    "password",
    "password_hash_sha256",
    "auth_note",
]

# Giá trị cột ``password_hash_sha256`` của workbook — dùng để khẳng định KHÔNG
# được nhét vào ``password_hash`` (xem test (b)).
_SHA256_MAU = "3af350dd568fdeb23ad4ee3a573f4420c0cc75f5bbb44db162b721a7f71e8da7"


def _hang(
    *,
    resident_id: str = "RES-0001",
    phone: str = "0909000001",
    password: str = "GreenBin@0001",
    dia_chi: str = "165 120 Lê Duẩn, Hà Nội",
    lat: object = 21.025679,
    lng: object = 105.85,
) -> dict[str, object]:
    return {
        "resident_id": resident_id,
        "home_address_simulated": dia_chi,
        "legacy_area": "Đống Đa",
        "latitude": lat,
        "longitude": lng,
        "nearest_bin_id": "",
        "distance_to_bin_m": "",
        "household_size": "",
        "waste_kg_day_est": "",
        "data_status": "",
        "privacy_note": "",
        "login_phone": phone,
        "password": password,
        "password_hash_sha256": _SHA256_MAU,
        "auth_note": "",
    }


def _workbook_gia(tmp_path: Path, cac_hang: list[dict[str, object]]) -> Path:
    duong = tmp_path / "workbook_gia.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RESIDENT_SIMULATION"
    ws.append(TIEU_DE)
    for hang in cac_hang:
        ws.append([hang.get(c, "") for c in TIEU_DE])
    wb.save(duong)
    return duong


def _them_toa(db_session: Session, code: str, dia_chi: str, lat: float, lng: float) -> Building:
    """Tạo một toà giả có toạ độ — nền cho việc rải cư dân (gói P62)."""
    toa = Building(code=code, name=f"Chung cư {code}", address=dia_chi, lat=lat, lng=lng)
    db_session.add(toa)
    db_session.flush()
    return toa


def _them_hai_toa(db_session: Session) -> list[Building]:
    return [
        _them_toa(db_session, "TOA-A", "12 Phố A, Hoàn Kiếm, Hà Nội", 21.01, 105.80),
        _them_toa(db_session, "TOA-B", "34 Phố B, Hoàn Kiếm, Hà Nội", 21.02, 105.81),
    ]


def _tim(db_session: Session, phone: str) -> User:
    nguoi = db_session.scalar(select(User).where(User.phone == phone))
    assert nguoi is not None, f"Phải có tài khoản mang số {phone}"
    return nguoi


# --- (a) CSDL rỗng → tạo đủ tài khoản, rải vào toà ----------------------------


def test_csdl_rong_tao_du_tai_khoan(db_session: Session, tmp_path: Path) -> None:
    cac_toa = _them_hai_toa(db_session)
    db_session.commit()
    duong = _workbook_gia(
        tmp_path,
        [_hang(), _hang(resident_id="RES-0002", phone="0909000002", dia_chi="42 Hàng Ngang, Hà Nội")],
    )

    ket_qua = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    assert ket_qua["so_tao_moi"] == 2, ket_qua
    assert ket_qua["so_dong_hong"] == 0
    assert len(db_session.scalars(select(User)).all()) == 2

    nguoi_1 = _tim(db_session, "0909000001")
    assert nguoi_1.unit_id is None, "Không được gán căn hộ"
    assert nguoi_1.building_id == cac_toa[0].id, "Cư dân thứ 0 vào toà thứ 0"
    # Địa chỉ chép TỪ TOÀ, không phải từ workbook.
    assert nguoi_1.address == cac_toa[0].address
    assert nguoi_1.lat == pytest.approx(cac_toa[0].lat)
    assert nguoi_1.lng == pytest.approx(cac_toa[0].lng)
    assert nguoi_1.role == "resident"
    assert nguoi_1.email == "res-0001@sim.greenbin.vn", (
        "email sinh từ resident_id, đuôi @sim.greenbin.vn là dấu dữ liệu mô phỏng"
    )
    assert nguoi_1.full_name == "Cư dân RES-0001", "full_name sinh từ resident_id (workbook không có cột tên)"

    nguoi_2 = _tim(db_session, "0909000002")
    assert nguoi_2.building_id == cac_toa[1].id, "Cư dân thứ 1 vào toà thứ 1"
    assert nguoi_2.address == cac_toa[1].address


# --- (b) mật khẩu băm đúng kiểu → đăng nhập được -----------------------------


def test_mat_khau_bam_pbkdf2_dang_nhap_duoc(db_session: Session, tmp_path: Path) -> None:
    """Test quan trọng nhất: dùng đúng hàm kiểm mật khẩu của hệ thống.

    ``authenticate`` đăng nhập bằng ``verify_password`` — khẳng định ngay bằng
    chính hàm đó, và khẳng định KHÔNG nhét cột ``password_hash_sha256`` vào.
    """
    _them_hai_toa(db_session)
    db_session.commit()
    duong = _workbook_gia(tmp_path, [_hang()])

    nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    nguoi = _tim(db_session, "0909000001")
    assert verify_password("GreenBin@0001", nguoi.password_hash) is True, (
        "Phải đăng nhập được bằng mật khẩu gốc trong workbook"
    )
    assert nguoi.password_hash != _SHA256_MAU, (
        "⛔ KHÔNG được nhét password_hash_sha256 của workbook vào password_hash"
    )
    assert nguoi.password_hash.startswith("pbkdf2_sha256$"), nguoi.password_hash


# --- (c) chạy lại lần hai → vô hại -------------------------------------------


def test_chay_lai_khong_tao_them_khong_doi_dia_chi(db_session: Session, tmp_path: Path) -> None:
    cac_toa = _them_hai_toa(db_session)
    db_session.commit()
    duong = _workbook_gia(tmp_path, [_hang()])

    nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()
    lan_hai = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    assert lan_hai["so_tao_moi"] == 0, "Lần hai không được tạo thêm ai"
    assert lan_hai["so_cap_nhat_dia_chi"] == 0
    assert lan_hai["so_da_du"] == 1, "Lần hai mọi dòng phải rơi vào đã có địa chỉ"
    assert len(db_session.scalars(select(User)).all()) == 1, "Không được nhân đôi tài khoản"
    nguoi = _tim(db_session, "0909000001")
    assert nguoi.address == cac_toa[0].address, "Địa chỉ không được đổi ở lần chạy thứ hai"
    assert nguoi.building_id == cac_toa[0].id, "Toà không được đổi ở lần chạy thứ hai"


# --- (d) tài khoản có sẵn thiếu địa chỉ → được điền, không đổi mật khẩu --------


def test_tai_khoan_co_san_thieu_dia_chi_duoc_dien_khong_doi_mat_khau(
    db_session: Session, tmp_path: Path
) -> None:
    cac_toa = _them_hai_toa(db_session)
    db_session.add(
        User(
            email="cu_dan_cu@demo.vn",
            phone="0909000001",
            full_name="Cư dân cũ",
            role="resident",
            password_hash="pbkdf2_sha256$1$aa$bb",
            unit_id=None,
            address="",
        )
    )
    db_session.commit()
    duong = _workbook_gia(tmp_path, [_hang()])

    ket_qua = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    assert ket_qua["so_cap_nhat_dia_chi"] == 1, ket_qua
    assert ket_qua["so_tao_moi"] == 0, "Đã có tài khoản rồi thì không tạo mới"
    nguoi = _tim(db_session, "0909000001")
    assert nguoi.building_id == cac_toa[0].id, "Tài khoản cũ cũng được gán toà"
    assert nguoi.address == cac_toa[0].address
    assert nguoi.password_hash == "pbkdf2_sha256$1$aa$bb", "Chỉ điền địa chỉ, không được đổi mật khẩu"
    assert nguoi.email == "cu_dan_cu@demo.vn", "Không được đổi email của tài khoản có sẵn"


# --- (e) nhánh cập nhật không sửa email của tài khoản mô phỏng đã có ----------


def test_nhanh_cap_nhat_khong_sua_email_tai_khoan_sim_co_san(
    db_session: Session, tmp_path: Path
) -> None:
    """Đuôi @sim.greenbin.vn là dấu mô phỏng — nhánh cập nhật không được chạm email."""
    cac_toa = _them_hai_toa(db_session)
    db_session.add(
        User(
            email="res-0001@sim.greenbin.vn",
            phone="0909000001",
            full_name="Cư dân mô phỏng",
            role="resident",
            password_hash="pbkdf2_sha256$1$aa$bb",
            unit_id=None,
            address="",
        )
    )
    db_session.commit()
    duong = _workbook_gia(tmp_path, [_hang()])

    ket_qua = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    assert ket_qua["so_cap_nhat_dia_chi"] == 1, ket_qua
    nguoi = _tim(db_session, "0909000001")
    assert nguoi.email == "res-0001@sim.greenbin.vn", "Nhánh cập nhật không được sửa email"
    assert nguoi.address == cac_toa[0].address


# --- (f) dòng thiếu login_phone → dòng hỏng, không làm hỏng cả lần chạy ---------


def test_dong_thieu_login_phone_tinh_vao_dong_hong(db_session: Session, tmp_path: Path) -> None:
    _them_hai_toa(db_session)
    db_session.commit()
    duong = _workbook_gia(
        tmp_path,
        [_hang(phone=""), _hang(resident_id="RES-0002", phone="0909000002")],
    )

    ket_qua = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    assert ket_qua["so_dong_hong"] == 1, ket_qua
    assert ket_qua["so_tao_moi"] == 1, "Dòng còn tốt vẫn phải được xử lý"
    assert len(db_session.scalars(select(User)).all()) == 1


# --- (f) --kiem-tra không ghi một dòng nào ------------------------------------


def test_kiem_tra_khong_ghi_gi(db_session: Session, tmp_path: Path) -> None:
    _them_hai_toa(db_session)
    db_session.add(
        User(
            email="cu_dan_cu@demo.vn",
            phone="0909000001",
            full_name="Cư dân cũ",
            role="resident",
            password_hash="pbkdf2_sha256$1$aa$bb",
            unit_id=None,
            address="",
        )
    )
    db_session.commit()

    duong = _workbook_gia(
        tmp_path,
        [
            _hang(phone="0909000001", dia_chi="Địa chỉ không được ghi"),  # sẽ cập nhật nếu chạy thật
            _hang(resident_id="RES-0009", phone="0909999999"),  # sẽ tạo nếu chạy thật
        ],
    )

    ket_qua = nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong, kiem_tra=True)

    assert ket_qua["so_tao_moi"] == 1, "Kiểm tra phải đếm đúng sẽ tạo bao nhiêu"
    assert ket_qua["so_cap_nhat_dia_chi"] == 1, "Kiểm tra phải đếm đúng sẽ cập nhật bao nhiêu"
    assert len(db_session.scalars(select(User)).all()) == 1, "--kiem-tra không được thêm user nào"
    nguoi = _tim(db_session, "0909000001")
    assert nguoi.address == "", "--kiem-tra không được sửa địa chỉ"
    assert nguoi.building_id is None, "--kiem-tra không được gán toà"


# --- (g) rải đều vào toà (gói P62) ---------------------------------------------


def test_rai_deu_chenh_lech_toi_da_mot_ho(db_session: Session, tmp_path: Path) -> None:
    """600-style: chênh lệch số hộ giữa toà đông nhất và ít nhất ≤ 1."""
    cac_toa = [
        _them_toa(db_session, f"TOA-{i:02d}", f"Địa chỉ toà {i}", 21.0 + i / 100, 105.0 + i / 100)
        for i in range(5)
    ]
    db_session.commit()
    duong = _workbook_gia(
        tmp_path,
        [_hang(resident_id=f"RES-{i:04d}", phone=f"0909{i:06d}") for i in range(1, 14)],
    )

    nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    so_ho_theo_toa: dict[int, int] = {}
    for nguoi in db_session.scalars(select(User)).all():
        so_ho_theo_toa[nguoi.building_id] = so_ho_theo_toa.get(nguoi.building_id, 0) + 1
    danh_sach = sorted(so_ho_theo_toa.values())
    assert danh_sach[-1] - danh_sach[0] <= 1, f"Rải phải đều: {danh_sach}"
    assert set(so_ho_theo_toa) == {t.id for t in cac_toa}, "Mọi toà phải có cư dân"


def test_moi_user_building_id_khop_toa(db_session: Session, tmp_path: Path) -> None:
    """(b) Mỗi user có `building_id`, và address/lat/lng khớp đúng toà đó."""
    cac_toa = _them_hai_toa(db_session)
    db_session.commit()
    duong = _workbook_gia(
        tmp_path,
        [_hang(resident_id="RES-0001", phone="0909000001"), _hang(resident_id="RES-0002", phone="0909000002")],
    )

    nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()

    theo_toa = {t.id: t for t in cac_toa}
    for nguoi in db_session.scalars(select(User)).all():
        assert nguoi.building_id is not None, "Ai cũng phải có toà"
        toa = theo_toa[nguoi.building_id]
        assert nguoi.address == toa.address, "Địa chỉ phải chép từ toà"
        assert nguoi.lat == pytest.approx(toa.lat)
        assert nguoi.lng == pytest.approx(toa.lng)
        assert nguoi.unit_id is None, "Không đẻ căn hộ giả"


def test_lan_hai_khong_doi_toa(db_session: Session, tmp_path: Path) -> None:
    """(d) Chạy lần hai → không ai bị đổi toà, không ai bị ghi đè địa chỉ."""
    _them_hai_toa(db_session)
    db_session.commit()
    duong = _workbook_gia(tmp_path, [_hang(), _hang(resident_id="RES-0002", phone="0909000002")])

    nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()
    truoc = {n.phone: (n.building_id, n.address, n.lat, n.lng) for n in db_session.scalars(select(User)).all()}

    nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()
    sau = {n.phone: (n.building_id, n.address, n.lat, n.lng) for n in db_session.scalars(select(User)).all()}

    assert truoc == sau, "Lần hai không được đổi toà hay địa chỉ"


def test_hai_lan_tu_csdl_trang_ket_qua_giong_het(db_session: Session, tmp_path: Path) -> None:
    """(e) Chạy hai lần từ CSDL trắng → kết quả gán y hệt nhau (tất định)."""
    _them_hai_toa(db_session)
    db_session.commit()
    duong = _workbook_gia(tmp_path, [_hang(), _hang(resident_id="RES-0002", phone="0909000002")])

    nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong)
    db_session.commit()
    lan_1 = {n.phone: (n.building_id, n.address, n.lat, n.lng) for n in db_session.scalars(select(User)).all()}

    # CSDL thứ hai hoàn toàn độc lập (engine mới), seed cùng toà, cùng workbook.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.db.models import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db2 = factory()
    _them_hai_toa(db2)
    db2.commit()

    nhap_va_cap_nhat_cu_dan(db2, duong_dan=duong)
    db2.commit()
    lan_2 = {n.phone: (n.building_id, n.address, n.lat, n.lng) for n in db2.scalars(select(User)).all()}

    assert lan_1 == lan_2, "Rải cư dân phải tất định — hai lần chạy từ CSDL trắng phải ra y hệt"


def test_kiem_tra_khong_doi_user_khong_doi_dia_chi(db_session: Session, tmp_path: Path) -> None:
    """(f) `--kiem-tra` → số user và địa chỉ không đổi một chút nào."""
    _them_hai_toa(db_session)
    db_session.add(
        User(
            email="res-0001@sim.greenbin.vn",
            phone="0909000001",
            full_name="Cư dân cũ",
            role="resident",
            password_hash="pbkdf2_sha256$1$aa$bb",
            unit_id=None,
            address="",
        )
    )
    db_session.commit()
    duong = _workbook_gia(tmp_path, [_hang(phone="0909000001")])

    nhap_va_cap_nhat_cu_dan(db_session, duong_dan=duong, kiem_tra=True)

    nguoi = _tim(db_session, "0909000001")
    assert nguoi.address == "", "--kiem-tra không được sửa địa chỉ"
    assert nguoi.building_id is None, "--kiem-tra không được gán toà"
    assert len(db_session.scalars(select(User)).all()) == 1, "--kiem-tra không được thêm user"


# --- (g) --kiem-tra KHÔNG được vá lược đồ (gói P61) ----------------------------


def test_cot_con_thieu_chi_do_khong_alter(tmp_path: Path) -> None:
    """`_cot_con_thieu` liệt kê cột thiếu bằng inspector — không ALTER, không ghi.

    CSDL dựng chỉ có bảng `users` THIẾU cột `address`; chạy `_cot_con_thieu` phải
    báo cột thiếu và KHÔNG được thêm cột nào vào CSDL.
    """
    from sqlalchemy import create_engine, inspect

    engine = create_engine("sqlite://")
    with engine.begin() as ket_noi:
        ket_noi.exec_driver_sql(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255), "
            "phone VARCHAR(20), full_name VARCHAR(120), role VARCHAR(20), "
            "password_hash VARCHAR(255), unit_id INTEGER, organization_id INTEGER, "
            "green_points INTEGER DEFAULT 0, created_at DATETIME)"
        )

    thieu = _cot_con_thieu(engine)

    assert "users.address" in thieu, f"Phải báo users.address thiếu, nhận được: {thieu}"
    assert "users.lat" in thieu
    assert "users.lng" in thieu
    cac_cot = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "address" not in cac_cot, "Đã vá cột khi chỉ được phép đọc — ALTER bị cấm ở --kiem-tra"


def test_kiem_tra_khong_goi_init_db_khong_va_luoc_do(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """`--kiem-tra` không gọi `init_db()` (thứ chạy `va_cot_thieu` → ALTER).

    Gói P61: một "chạy khô" từng vá 6 cột lên CSDL production (18/08) vì `main()`
    gọi `init_db()` trước nhánh khô. Giờ nhánh khô phải tránh `init_db()` hẳn —
    test chặn chính điều đó: đổi `init_db` thành hàm nổ, gọi `main` với
    `--kiem-tra`, và khẳng định nó KHÔNG nổ.
    """
    import sys

    from sqlalchemy import create_engine

    import scripts.nhap_cu_dan_gis as mod

    duong = _workbook_gia(tmp_path, [_hang()])
    monkeypatch.setattr(mod, "WORKBOOK", duong)
    monkeypatch.setattr(sys, "argv", ["nhap_cu_dan_gis.py", "--kiem-tra"])

    def _no_never():
        raise AssertionError("init_db() bị gọi trong --kiem-tra — nó chạy va_cot_thieu (ALTER)!")

    monkeypatch.setattr(mod, "init_db", _no_never)

    # CSDL nhỏ thiếu cột: dựng engine rồi gắn session factory vào module để
    # nhánh khô đọc được qua session_scope mà không cần DB thật.
    engine = create_engine("sqlite://")
    from src.db.models import Base

    Base.metadata.create_all(engine)
    # Cố ý bỏ cột address khỏi bảng users — CSDL "cũ" chưa có 6 cột gói P52.
    with engine.begin() as ket_noi:
        ket_noi.exec_driver_sql("ALTER TABLE users DROP COLUMN address")
        ket_noi.exec_driver_sql("ALTER TABLE users DROP COLUMN lat")
        ket_noi.exec_driver_sql("ALTER TABLE users DROP COLUMN lng")

    monkeypatch.setattr(mod, "session_scope", _session_scope(engine))
    # Nhánh khô cũng đọc engine để dò cột thiếu — gắn đúng engine đã dựng.
    monkeypatch.setattr(mod, "get_engine", lambda: engine)

    mod.main()

    ra = capsys.readouterr()
    assert "sẽ thêm các cột còn thiếu" in ra.out, f"Nhánh khô phải báo cột thiếu:\n{ra.out}"
    # Không có lỗi AssertionError từ init_db — nghĩa là nhánh khô không gọi nó.


def _session_scope(engine):
    """Context manager session đúng kiểu `session_scope` nhưng gắn vào engine tạm."""
    from contextlib import contextmanager

    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def _scope():
        session: Session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _scope
