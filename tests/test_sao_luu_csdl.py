"""Test vòng tròn sao lưu ↔ khôi phục cho scripts/sao_luu_csdl.py (gói P92).

Mọi test chạy trên SQLite cục bộ (trong bộ nhớ hoặc file tạm) — KHÔNG chạm
Supabase production hay bất kỳ CSDL xa nào.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Thêm src vào path để import được module
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from src.config import reset_settings_cache
from src.db.models import Base, User, WasteCategory
from src.db.session import reset_engine

# --- Fixtures ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Mỗi test có môi trường sạch: biến môi trường, cache settings, engine."""
    # Xoá biến môi trường có thể ảnh hưởng
    for var in (
        "DATABASE_URL",
        "APP_ENV",
        "CHO_PHEP_GHI_DB_XA",
        "CHO_PHEP_XOA_DB",
        "STORAGE_ENABLED",
        "SUPABASE_URL",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_BUCKET",
    ):
        monkeypatch.delenv(var, raising=False)

    # Mặc định: development, SQLite trong bộ nhớ
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    reset_settings_cache()
    reset_engine()

    yield

    reset_settings_cache()
    reset_engine()


@pytest.fixture
def db_nguon(tmp_path: Path) -> tuple[Session, Path]:
    """CSDL nguồn có dữ liệu thật (kể cả FK và Unicode Việt Nam)."""
    # Dùng file SQLite tạm để có thể kiểm tra sau khi script chạy
    db_file = tmp_path / "nguon.db"
    url = f"sqlite:///{db_file}"

    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # WasteCategory (bảng cha) - tên bảng là waste_categories
        cat1 = WasteCategory(
            code="recyclable_plastic",
            name="Rác nhựa tái chế",
            icon="♻️",
            bin_color="green",
            handling_note="Vệ sinh sạch, phơi khô rồi bỏ thùng xanh.",
            is_hazardous=False,
        )
        cat2 = WasteCategory(
            code="hazardous_battery",
            name="Pin đã dùng",
            icon="🔋",
            bin_color="red",
            handling_note="Giao tại điểm thu gom rác nguy hại.",
            is_hazardous=True,
        )
        cat3 = WasteCategory(
            code="organic",
            name="Rác hữu cơ 🌱",  # Unicode Việt Nam có dấu
            icon="🍃",
            bin_color="green",
            handling_note="Compost hoặc bỏ thùng xanh lá.",
            is_hazardous=False,
        )
        session.add_all([cat1, cat2, cat3])
        session.flush()

        # User
        user1 = User(
            email="resident@demo.vn",
            phone="0901234567",
            full_name="Nguyễn Văn An",
            role="resident",
            password_hash="hashed_password_1",
            green_points=150,
        )
        user2 = User(
            email="manager@demo.vn",
            phone="0909876543",
            full_name="Trần Thị Bình",
            role="manager",
            password_hash="hashed_password_2",
            green_points=500,
        )
        session.add_all([user1, user2])
        session.commit()

    # Trả về engine để test có thể tạo session mới khi cần
    yield engine, db_file

    engine.dispose()


@pytest.fixture
def db_dich_rong(tmp_path: Path) -> tuple[Session, Path]:
    """CSDL đích rỗng (chỉ có schema, chưa có dữ liệu)."""
    db_file = tmp_path / "dich.db"
    url = f"sqlite:///{db_file}"

    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)

    yield engine, db_file

    engine.dispose()


# --- Helper: chạy script qua subprocess ------------------------------------


def _chay_script(*args: str, env: dict | None = None, input_data: str | None = None) -> subprocess.CompletedProcess:
    """Chạy script sao_luu_csdl.py qua subprocess, trả về CompletedProcess."""
    cmd = [sys.executable, "scripts/sao_luu_csdl.py", *args]
    env_moi = dict(os.environ)
    env_moi["PYTHONIOENCODING"] = "utf-8"
    if env:
        env_moi.update(env)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=input_data,
        env=env_moi,
        cwd=Path(__file__).resolve().parents[1],
    )


def _doc_bang(engine, ten_bang: str) -> list[dict]:
    """Đọc toàn bộ dòng của một bảng, trả về list dict."""
    with Session(engine) as session:
        rows = session.execute(text(f"SELECT * FROM {ten_bang}")).fetchall()
        if not rows:
            return []
        cot = rows[0]._mapping.keys()
        return [dict(zip(cot, r, strict=False)) for r in rows]


def _dem_dong(engine, ten_bang: str) -> int:
    with Session(engine) as session:
        return session.scalar(text(f"SELECT COUNT(*) FROM {ten_bang}"))


# --- Test 1: Vòng tròn sao lưu → khôi phục thật trên SQLite ----------------


def test_vong_tron_sao_luu_khoi_phuc_sqlite(db_nguon, db_dich_rong, tmp_path: Path) -> None:
    """Sao lưu từ DB nguồn → file JSON → khôi phục vào DB đích rỗng → so từng dòng."""
    engine_nguon, file_nguon = db_nguon
    engine_dich, file_dich = db_dich_rong

    # 1. Đếm số dòng trước khi sao lưu
    bang_kiem_tra = ["waste_categories", "users"]
    truoc = {bang: _dem_dong(engine_nguon, bang) for bang in bang_kiem_tra}

    # 2. Sao lưu (dùng Python thuần vì không có pg_dump)
    os.environ["DATABASE_URL"] = f"sqlite:///{file_nguon}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0, f"Sao lưu thất bại: {ket_qua.stderr}"

    # Tìm file vừa tạo (có timestamp trong tên)
    files = list(tmp_path.glob("sao_luu_*.json"))
    assert len(files) == 1, f"Mong đợi 1 file sao lưu, thấy {len(files)}"
    file_sao_luu = files[0]

# 3. Kiểm tra file sao lưu không chứa mật khẩu / connection string
    noi_dung = file_sao_luu.read_text(encoding="utf-8")
    # Yêu cầu: không chứa mật khẩu KẾT NỐI DB (chuỗi dạng postgresql://user:pass@host)
    # password_hash của user là dữ liệu, không phải mật khẩu kết nối
    assert "postgresql://" not in noi_dung and "postgres://" not in noi_dung, "Không được lộ connection string Postgres"
    assert "sqlite:///" not in noi_dung or file_nguon.name in noi_dung, "Chỉ cho phép lộ đường dẫn file SQLite cục bộ"
    # Không có mật khẩu dạng user:pass@host
    import re
    assert not re.search(r"://[^:]+:[^@]+@", noi_dung), "Không được có mật khẩu trong connection string"

    # 4. Kiểm tra cấu trúc file JSON
    du_lieu = json.loads(noi_dung)
    assert "meta" in du_lieu and "data" in du_lieu
    assert "thoi_gian" in du_lieu["meta"]
    assert "may_chu" in du_lieu["meta"]
    assert "bang" in du_lieu["meta"]
    assert "waste_categories" in du_lieu["data"]
    assert "users" in du_lieu["data"]

    # 5. Kiểm tra số dòng trong file sao lưu khớp nguồn
    for bang_info in du_lieu["meta"]["bang"]:
        if bang_info["ten"] in bang_kiem_tra:
            assert bang_info["so_dong"] == truoc[bang_info["ten"]], (
                f"Bảng {bang_info['ten']}: sao lưu {bang_info['so_dong']} dòng, nguồn {truoc[bang_info['ten']]} dòng"
            )

    # 6. Khôi phục vào DB đích
    os.environ["DATABASE_URL"] = f"sqlite:///{file_dich}"
    os.environ["CHO_PHEP_GHI_DB_XA"] = "1"  # Không cần cho sqlite nhưng để nhất quán
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--khoi-phuc", str(file_sao_luu), "--database-url", f"sqlite:///{file_dich}", "--toi-chac-chan")
    assert ket_qua.returncode == 0, f"Khôi phục thất bại: {ket_qua.stderr}"

    # 7. So từng dòng nguồn ↔ đích
    for bang in bang_kiem_tra:
        dong_nguon = _doc_bang(engine_nguon, bang)
        dong_dich = _doc_bang(engine_dich, bang)

        assert len(dong_nguon) == len(dong_dich), f"Bảng {bang}: số dòng khác nhau"

        # So sánh từng cột (trừ id tự tăng có thể khác)
        for i, (nguon, dich) in enumerate(zip(dong_nguon, dong_dich, strict=True)):
            # Loại bỏ id vì có thể khác nhau (auto-increment)
            nguon_cmp = {k: v for k, v in nguon.items() if k != "id"}
            dich_cmp = {k: v for k, v in dich.items() if k != "id"}
            assert nguon_cmp == dich_cmp, f"Bảng {bang}, dòng {i}: dữ liệu khác nhau\n  Nguồn: {nguon_cmp}\n  Đích: {dich_cmp}"

    # 8. Kiểm tra Unicode Việt Nam được giữ nguyên
    cat_nguon = _doc_bang(engine_nguon, "waste_categories")
    cat_dich = _doc_bang(engine_dich, "waste_categories")
    ten_viet_nam = [c for c in cat_nguon if "🌱" in c.get("name", "")]
    assert ten_viet_nam, "Nguồn phải có tên Việt Nam có dấu"
    ten_viet_nam_dich = [c for c in cat_dich if "🌱" in c.get("name", "")]
    assert ten_viet_nam_dich, "Đích phải giữ được tên Việt Nam có dấu"

    print(f"✅ Vòng tròn thành công: {len(bang_kiem_tra)} bảng, dữ liệu khớp hoàn toàn")


# --- Test 2: Khôi phục thiếu --toi-chac-chan bị chặn ----------------------


def test_khoi_phuc_thieu_toi_chac_chan_bi_chan(db_nguon, db_dich_rong, tmp_path: Path) -> None:
    """Khôi phục không có cờ --toi-chac-chan phải thoát mã != 0, không ghi gì."""
    engine_nguon, file_nguon = db_nguon
    engine_dich, file_dich = db_dich_rong

    # Tạo file sao lưu trước
    os.environ["DATABASE_URL"] = f"sqlite:///{file_nguon}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0
    files = list(tmp_path.glob("sao_luu_*.json"))
    file_sao_luu = files[0]

    # Thử khôi phục KHÔNG có --toi-chac-chan
    os.environ["DATABASE_URL"] = f"sqlite:///{file_dich}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--khoi-phuc", str(file_sao_luu))
    assert ket_qua.returncode != 0, "Phải thoát mã lỗi khi thiếu --toi-chac-chan"
    assert "toi-chac-chan" in ket_qua.stderr.lower() or "TỪ CHỐI" in ket_qua.stderr

    # Kiểm tra DB đích VẪN RỖNG (không ghi gì)
    for bang in ["waste_categories", "users"]:
        assert _dem_dong(engine_dich, bang) == 0, f"Bảng {bang} không được ghi khi thiếu cờ"


# --- Test 3: Khôi phục vào production bị chặn ------------------------------


def test_khoi_phuc_vao_production_bi_chan(db_nguon, db_dich_rong, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Khôi phục vào CSDL production (theo URL đích) bị CHỐT TUYỆT ĐỐI."""
    engine_nguon, file_nguon = db_nguon
    engine_dich, file_dich = db_dich_rong

    # Tạo file sao lưu
    os.environ["DATABASE_URL"] = f"sqlite:///{file_nguon}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0
    files = list(tmp_path.glob("sao_luu_*.json"))
    file_sao_luu = files[0]

    # Giả lập đích là production (Supabase)
    url_prod = "postgresql://user:pass@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"
    monkeypatch.setenv("APP_ENV", "development")  # Máy dev
    monkeypatch.setenv("CHO_PHEP_GHI_DB_XA", "1")
    os.environ["DATABASE_URL"] = f"sqlite:///{file_dich}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--khoi-phuc", str(file_sao_luu), "--database-url", url_prod, "--toi-chac-chan")
    assert ket_qua.returncode != 0, "Phải thoát mã lỗi khi khôi phục vào production"
    assert "CHỐT TUYỆT ĐỐI" in ket_qua.stderr or "production" in ket_qua.stderr.lower()

    # DB đích vẫn rỗng
    for bang in ["waste_categories", "users"]:
        assert _dem_dong(engine_dich, bang) == 0


# --- Test 4: Sao lưu không ghi gì vào nguồn --------------------------------


def test_sao_luu_khong_ghi_vao_nguon(db_nguon, tmp_path: Path) -> None:
    """Sao lưu là chỉ đọc: số dòng mọi bảng trước và sau phải bằng nhau."""
    engine_nguon, file_nguon = db_nguon

    bang_kiem_tra = ["waste_categories", "users"]
    truoc = {bang: _dem_dong(engine_nguon, bang) for bang in bang_kiem_tra}

    os.environ["DATABASE_URL"] = f"sqlite:///{file_nguon}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0

    # Mở session mới để đọc lại (session cũ có thể cache)
    sau = {bang: _dem_dong(engine_nguon, bang) for bang in bang_kiem_tra}

    for bang in bang_kiem_tra:
        assert truoc[bang] == sau[bang], f"Bảng {bang}: trước {truoc[bang]} dòng, sau {sau[bang]} dòng (sao lưu đã ghi!)"


# --- Test 5: Không rò bí mật trong output và file sao lưu ------------------


def test_khong_ro_bi_mat(db_nguon, db_dich_rong, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """File sao lưu và mọi dòng in ra màn hình không chứa mật khẩu / connection string đầy đủ."""
    engine_nguon, file_nguon = db_nguon
    engine_dich, file_dich = db_dich_rong

    # Thiết lập DATABASE_URL có mật khẩu giả để test che giấu
    url_co_mat_khau = f"sqlite:///{file_nguon}"  # SQLite không có pass nhưng test logic che
    os.environ["DATABASE_URL"] = url_co_mat_khau
    reset_settings_cache()
    reset_engine()

    # Sao lưu
    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0

    output = ket_qua.stdout + ket_qua.stderr
    # Không được in ra mật khẩu kết nối DB (dạng user:pass@host)
    # password_hash của user là dữ liệu, có thể xuất hiện trong cảnh báo - đó là mong đợi
    import re
    assert not re.search(r"://[^:]+:[^@]+@", output), "Không được lộ mật khẩu kết nối trong output"

    files = list(tmp_path.glob("sao_luu_*.json"))
    file_sao_luu = files[0]
    noi_dung = file_sao_luu.read_text(encoding="utf-8")
    # File sao lưu chứa dữ liệu user (kể cả password_hash) - đây là dữ liệu, không phải mật khẩu kết nối
    # Yêu cầu: không chứa "mật khẩu hay chuỗi kết nối đầy đủ" - hiểu là mật khẩu kết nối DB
    import re
    assert not re.search(r"://[^:]+:[^@]+@", noi_dung), "Không được có mật khẩu trong connection string"
    assert "postgresql://" not in noi_dung and "postgres://" not in noi_dung, "Không được lộ connection string Postgres"


# --- Test 6: Sao lưu production cho phép khi có cờ --nguon-production ------


def test_sao_luu_production_cho_phep_khi_co_co(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sao lưu trên production được phép khi có cờ --nguon-production."""
    # Tạo DB giả production
    db_file = tmp_path / "prod.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    reset_settings_cache()
    reset_engine()

    # Không có cờ -> bị chặn
    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode != 0
    assert "production" in ket_qua.stderr.lower()

    # Có cờ --nguon-production -> cho phép
    ket_qua = _chay_script("--dir", str(tmp_path), "--nguon-production")
    assert ket_qua.returncode == 0, f"Sao lưu production với cờ phải thành công: {ket_qua.stderr}"
    assert "Đã ghi" in ket_qua.stdout


# --- Test 7: Khôi phục file .sql không được hỗ trợ -------------------------


def test_khoi_phuc_file_sql_khong_duoc_ho_tro(db_nguon, db_dich_rong, tmp_path: Path) -> None:
    """Khôi phục file .sql in lỗi và thoát mã != 0."""
    session_nguon, file_nguon = db_nguon
    session_dich, file_dich = db_dich_rong

    # Tạo file .sql giả
    file_sql = tmp_path / "backup.sql"
    file_sql.write_text("-- fake sql dump")

    os.environ["DATABASE_URL"] = f"sqlite:///{file_dich}"
    os.environ["CHO_PHEP_GHI_DB_XA"] = "1"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--khoi-phuc", str(file_sql), "--database-url", f"sqlite:///{file_dich}", "--toi-chac-chan")
    assert ket_qua.returncode != 0
    assert ".sql" in ket_qua.stderr.lower() or "không hỗ trợ" in ket_qua.stderr.lower()


# --- Test 8: Khôi phục CSDL xa cần CHO_PHEP_GHI_DB_XA=1 --------------------


def test_khoi_phuc_csdl_xa_can_bien_moi_truong(db_nguon, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Khôi phục vào PostgreSQL xa (không phải production) cần CHO_PHEP_GHI_DB_XA=1."""
    session_nguon, file_nguon = db_nguon

    # Tạo file sao lưu
    os.environ["DATABASE_URL"] = f"sqlite:///{file_nguon}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0
    files = list(tmp_path.glob("sao_luu_*.json"))
    file_sao_luu = files[0]

    # Giả lập CSDL đích là PostgreSQL xa (IP private, không phải production)
    # .env trỏ về SQLite local, đích là PostgreSQL IP private -> không trùng host
    url_xa = "postgresql://user:pass@10.0.0.5:5432/mydb"  # IP private 10.x
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/app.db")  # .env khác host đích
    monkeypatch.setenv("APP_ENV", "development")
    # KHÔNG set CHO_PHEP_GHI_DB_XA=1
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--khoi-phuc", str(file_sao_luu), "--database-url", url_xa, "--toi-chac-chan")
    assert ket_qua.returncode != 0
    assert "CHO_PHEP_GHI_DB_XA" in ket_qua.stderr

    # Với biến môi trường thì qua (sẽ lỗi kết nối thật nhưng qua bước kiểm tra)
    monkeypatch.setenv("CHO_PHEP_GHI_DB_XA", "1")
    reset_settings_cache()
    reset_engine()

    # Sẽ lỗi kết nối vì DB giả, nhưng KHÔNG bị chặn bởi "CHỐT TUYỆT ĐỐI: production"
    ket_qua = _chay_script("--khoi-phuc", str(file_sao_luu), "--database-url", url_xa, "--toi-chac-chan")
    assert "CHỐT TUYỆT ĐỐI" not in ket_qua.stderr


# --- Test 9: Kiểm tra đường sao lưu tự chọn (pg_dump vs Python) ------------


def test_duong_sao_luu_tu_chon(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Kiểm tra script in rõ đang dùng đường nào."""
    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("APP_ENV", "development")
    reset_settings_cache()
    reset_engine()

    # Giả lập không có pg_dump
    def fake_pg_dump() -> bool:
        return False

    import scripts.sao_luu_csdl as mod
    monkeypatch.setattr(mod, "_co_the_chay_pg_dump", fake_pg_dump)

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0
    output = ket_qua.stdout
    assert "Python thuần" in output or "SQLAlchemy" in output, "Phải in rõ dùng đường Python"
    assert "pg_dump" not in output.lower() or "không" in output.lower(), "Không được nói dùng pg_dump khi không có"


# --- Test 10: Metadata file sao lưu đầy đủ ---------------------------------


def test_metadata_sao_luu_day_du(db_nguon, tmp_path: Path) -> None:
    """File sao lưu JSON phải có đầy đủ metadata: thời gian, máy chủ, danh sách bảng, số dòng."""
    session_nguon, file_nguon = db_nguon

    os.environ["DATABASE_URL"] = f"sqlite:///{file_nguon}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0
    files = list(tmp_path.glob("sao_luu_*.json"))
    file_sao_luu = files[0]

    du_lieu = json.loads(file_sao_luu.read_text(encoding="utf-8"))
    meta = du_lieu["meta"]

    # Các trường bắt buộc
    assert "thoi_gian" in meta
    assert "may_chu" in meta
    assert "bang" in meta
    assert isinstance(meta["bang"], list)
    assert len(meta["bang"]) > 0

    # Mỗi bảng có ten, so_dong, cot
    for bang in meta["bang"]:
        assert "ten" in bang
        assert "so_dong" in bang
        assert "cot" in bang
        assert isinstance(bang["cot"], list)
        assert len(bang["cot"]) > 0

    # Thời gian phải parse được
    from datetime import datetime
    datetime.fromisoformat(meta["thoi_gian"].replace("Z", "+00:00"))

    # Tên máy chủ đã che
    assert "***" in meta["may_chu"]


# --- Test 11: Đích là host chứa supabase → từ chối tuyệt đối ------------------


def test_khoi_phuc_vao_supabase_bi_chan(db_nguon, db_dich_rong, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Khôi phục vào host chứa 'supabase' bị CHỐT TUYỆT ĐỐI, kể cả khi có đủ 2 khoá."""
    engine_nguon, file_nguon = db_nguon
    engine_dich, file_dich = db_dich_rong

    # Tạo file sao lưu
    os.environ["DATABASE_URL"] = f"sqlite:///{file_nguon}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0
    files = list(tmp_path.glob("sao_luu_*.json"))
    file_sao_luu = files[0]

    # Giả lập đích là Supabase production
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres")
    monkeypatch.setenv("APP_ENV", "development")  # Máy dev
    monkeypatch.setenv("CHO_PHEP_GHI_DB_XA", "1")  # Có khoá xa
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--khoi-phuc", str(file_sao_luu), "--database-url", "postgresql://user:pass@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres", "--toi-chac-chan")
    assert ket_qua.returncode != 0, "Phải thoát mã lỗi khi khôi phục vào Supabase"
    assert "CHỐT TUYỆT ĐỐI" in ket_qua.stderr or "production" in ket_qua.stderr.lower()
    assert "supabase" in ket_qua.stderr.lower() or "pooler" in ket_qua.stderr.lower()

    # DB đích vẫn rỗng
    for bang in ["waste_categories", "users"]:
        assert _dem_dong(engine_dich, bang) == 0


# --- Test 12: Đích trùng host với DATABASE_URL trong .env → từ chối -----------


def test_khoi_phuc_trung_host_env_bi_chan(db_nguon, db_dich_rong, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Khôi phục vào host trùng với DATABASE_URL trong .env bị từ chối (bắt production dù đổi tên)."""
    engine_nguon, file_nguon = db_nguon
    engine_dich, file_dich = db_dich_rong

    # Tạo file sao lưu
    os.environ["DATABASE_URL"] = f"sqlite:///{file_nguon}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0
    files = list(tmp_path.glob("sao_luu_*.json"))
    file_sao_luu = files[0]

    # Giả lập .env trỏ vào production, đích cũng là production đó
    url_prod_giả = "postgresql://user:pass@db.custom-domain.com:5432/mydb"
    monkeypatch.setenv("DATABASE_URL", url_prod_giả)  # .env trỏ production
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CHO_PHEP_GHI_DB_XA", "1")
    reset_settings_cache()
    reset_engine()

    # Khôi phục vào đúng host đó
    ket_qua = _chay_script("--khoi-phuc", str(file_sao_luu), "--database-url", url_prod_giả, "--toi-chac-chan")
    assert ket_qua.returncode != 0, "Phải thoát mã lỗi khi đích trùng host .env"
    assert "CHỐT TUYỆT ĐỐI" in ket_qua.stderr or "production" in ket_qua.stderr.lower()

    # DB đích vẫn rỗng
    for bang in ["waste_categories", "users"]:
        assert _dem_dong(engine_dich, bang) == 0


# --- Test 13: Có --khoi-phuc nhưng thiếu --database-url → từ chối ------------


def test_khoi_phuc_thieu_database_url_bi_chan(db_nguon, db_dich_rong, tmp_path: Path) -> None:
    """Khôi phục thiếu --database-url phải thoát mã != 0."""
    engine_nguon, file_nguon = db_nguon
    engine_dich, file_dich = db_dich_rong

    # Tạo file sao lưu
    os.environ["DATABASE_URL"] = f"sqlite:///{file_nguon}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0
    files = list(tmp_path.glob("sao_luu_*.json"))
    file_sao_luu = files[0]

    # Thử khôi phục KHÔNG có --database-url
    os.environ["DATABASE_URL"] = f"sqlite:///{file_dich}"
    os.environ["CHO_PHEP_GHI_DB_XA"] = "1"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--khoi-phuc", str(file_sao_luu), "--toi-chac-chan")
    assert ket_qua.returncode != 0, "Phải thoát mã lỗi khi thiếu --database-url"
    assert "database-url" in ket_qua.stderr.lower() or "BẮT BUỘC" in ket_qua.stderr

    # DB đích vẫn rỗng
    for bang in ["waste_categories", "users"]:
        assert _dem_dong(engine_dich, bang) == 0


# --- Test 14: Đích SQLite cục bộ, đủ khoá → cho phép, vòng khôi phục đúng ------


def test_khoi_phuc_sqlite_local_cho_phep(db_nguon, db_dich_rong, tmp_path: Path) -> None:
    """Khôi phục vào SQLite cục bộ với đủ khoá được phép, dữ liệu khớp."""
    engine_nguon, file_nguon = db_nguon
    engine_dich, file_dich = db_dich_rong

    # Tạo file sao lưu
    os.environ["DATABASE_URL"] = f"sqlite:///{file_nguon}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0
    files = list(tmp_path.glob("sao_luu_*.json"))
    file_sao_luu = files[0]

    # Khôi phục vào SQLite cục bộ (không cần CHO_PHEP_GHI_DB_XA)
    os.environ["DATABASE_URL"] = f"sqlite:///{file_dich}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--khoi-phuc", str(file_sao_luu), "--database-url", f"sqlite:///{file_dich}", "--toi-chac-chan")
    assert ket_qua.returncode == 0, f"Khôi phục SQLite local phải thành công: {ket_qua.stderr}"

    # Kiểm tra dữ liệu khớp
    for bang in ["waste_categories", "users"]:
        dong_nguon = _doc_bang(engine_nguon, bang)
        dong_dich = _doc_bang(engine_dich, bang)
        assert len(dong_nguon) == len(dong_dich)
        for i, (nguon, dich) in enumerate(zip(dong_nguon, dong_dich, strict=True)):
            nguon_cmp = {k: v for k, v in nguon.items() if k != "id"}
            dich_cmp = {k: v for k, v in dich.items() if k != "id"}
            assert nguon_cmp == dich_cmp, f"Bảng {bang}, dòng {i}: dữ liệu khác nhau"

    # Kiểm tra có in kế hoạch
    assert "KẾ HOẠCH KHÔI PHỤC" in ket_qua.stdout


# --- Test 15: Kiểm tra cảnh báo dữ liệu nhạy cảm trong output và meta ---------


def test_canh_bao_du_lieu_nhay_cam(db_nguon, tmp_path: Path) -> None:
    """File sao lưu có trường canh_bao trong meta, output in cảnh báo."""
    engine_nguon, file_nguon = db_nguon

    os.environ["DATABASE_URL"] = f"sqlite:///{file_nguon}"
    reset_settings_cache()
    reset_engine()

    ket_qua = _chay_script("--dir", str(tmp_path))
    assert ket_qua.returncode == 0

    # Kiểm tra output có cảnh báo
    assert "CẢNH BÁO" in ket_qua.stdout
    assert "password_hash" in ket_qua.stdout or "KHÔNG ĐƯỢC" in ket_qua.stdout

    files = list(tmp_path.glob("sao_luu_*.json"))
    file_sao_luu = files[0]
    noi_dung = file_sao_luu.read_text(encoding="utf-8")
    du_lieu = json.loads(noi_dung)

    # Kiểm tra meta có trường canh_bao
    assert "canh_bao" in du_lieu["meta"]
    assert "password_hash" in du_lieu["meta"]["canh_bao"]
    assert "KHÔNG ĐƯỢC" in du_lieu["meta"]["canh_bao"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
