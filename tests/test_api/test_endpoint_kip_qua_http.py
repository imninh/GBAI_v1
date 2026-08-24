"""Test P82 — gọi 4 endpoint kíp/quản lý lịch qua HTTP thật, không mock service.

Dùng ``with TestClient(app) as c:`` để ``lifespan`` chạy, bảng được tạo.

⛔ Gói P84: test phải TỰ DỰNG DỮ LIỆU — không trông chờ CSDL tình cờ đã seed.
Fixture ``kip_du_lieu`` dùng ``session_scope()`` (đúng cây CSDL của app — SQLite
tạm do ``conftest.py`` ép) tạo: 1 manager, 2 cleaner, 1 cư dân, 1 chuyến, rồi
đăng nhập bằng chính tài khoản vừa tạo. Gói P90: định danh nhúng thêm token từ
``uuid.uuid4`` — duy nhất theo tiến trình — để dù file CSDL dùng chung còn sót
dữ liệu phiên trước thì cũng không đụng ràng buộc duy nhất.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from src.main import app

MAT_KHAU = "demo1234"


def _moi_dinh_danh(tien_to: str) -> tuple[str, str]:
    """Sinh ``(email, sdt)`` mới, duy nhất cả giữa các tiến trình pytest.

    Bộ đếm khởi động lại từ 1 ở mỗi phiên, trong khi file CSDL dùng chung có thể
    còn sót tài khoản của phiên trước — chạy lần hai là đụng UNIQUE trên
    ``users.email``/``users.phone``. Nên ghép thêm 8 ký tự hex từ
    :func:`uuid.uuid4` vào cả hai định danh.

    SĐT giữ đúng khuôn mà ``chuan_hoa_sdt`` (src/services/auth.py) chấp nhận:
    đúng 10 chữ số bắt đầu bằng ``0`` — sai khuôn là bước đăng nhập hỏng ngay.
    """
    token = uuid.uuid4().hex[:8]
    return f"{tien_to}-{token}@demo.vn", f"09{int(token, 16) % 10**8:08d}"


@pytest.fixture
def kip_du_lieu() -> dict:
    """Tự dựng dữ liệu trên CSDL của app, trả về số điện thoại + id để dùng."""
    from src.db.models import PickupRoute, User
    from src.db.session import init_db, session_scope
    from src.services.security import hash_password

    # Bảng phải tồn tại trước khi ghi — init_db tạo trên CSDL tạm (sqlite).
    init_db()

    email_ql, sdt_ql = _moi_dinh_danh("ql")
    email_ve1, sdt_ve1 = _moi_dinh_danh("ve1")
    email_ve2, sdt_ve2 = _moi_dinh_danh("ve2")
    email_cd, sdt_cd = _moi_dinh_danh("cd")
    mat_khau_bam = hash_password(MAT_KHAU)

    with session_scope() as s:
        ql = User(
            email=email_ql,
            phone=sdt_ql,
            full_name="Quản lý kíp",
            role="manager",
            password_hash=mat_khau_bam,
        )
        ve1 = User(
            email=email_ve1,
            phone=sdt_ve1,
            full_name="Vệ sinh 1",
            role="cleaner",
            password_hash=mat_khau_bam,
        )
        ve2 = User(
            email=email_ve2,
            phone=sdt_ve2,
            full_name="Vệ sinh 2",
            role="cleaner",
            password_hash=mat_khau_bam,
        )
        cd = User(
            email=email_cd,
            phone=sdt_cd,
            full_name="Cư dân kíp",
            role="resident",
            password_hash=mat_khau_bam,
        )
        s.add_all([ql, ve1, ve2, cd])
        s.flush()
        route = PickupRoute(service_date=date(2026, 8, 24), window="08:00-10:00", status="proposed")
        s.add(route)
        s.flush()
        du_lieu = {
            "ql": {"phone": sdt_ql, "id": ql.id},
            "ve1": {"phone": sdt_ve1, "id": ve1.id},
            "ve2": {"phone": sdt_ve2, "id": ve2.id},
            "cd": {"phone": sdt_cd, "id": cd.id},
            "route_id": route.id,
        }
    return du_lieu


def _token(c: TestClient, phone: str) -> str:
    """Đăng nhập bằng tài khoản do fixture tự tạo và trả token."""
    r = c.post("/api/v1/auth/login", json={"phone": phone, "password": MAT_KHAU})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["token"]


def _auth(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


# ---------------------------------------------------------------------------
# 1. nhan-vien-kha-dung: 200, không 422
# ---------------------------------------------------------------------------


def test_nhan_vien_kha_dung_tra_200_khong_phai_422(kip_du_lieu: dict) -> None:
    """Trước P82, endpoint này rơi vào /{route_id} và trả 422 vì
    'nhan-vien-kha-dung' không parse được thành int."""
    with TestClient(app) as c:
        tok = _token(c, kip_du_lieu["ql"]["phone"])
        r = c.get("/api/v1/routes/nhan-vien-kha-dung", headers=_auth(tok))
        assert r.status_code != 422, (
            f"Endpoint trả 422 — route literal bị che bởi /{{route_id}}. "
            f"Body: {r.text}"
        )
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert len(body["items"]) >= 2, "Phải có ít nhất 2 cleaner do fixture dựng"


# ---------------------------------------------------------------------------
# 2. nhan-vien-kha-dung: không có phone/email
# ---------------------------------------------------------------------------


def test_nhan_vien_kha_dung_khong_ro_sdt_email(kip_du_lieu: dict) -> None:
    with TestClient(app) as c:
        tok = _token(c, kip_du_lieu["ql"]["phone"])
        r = c.get("/api/v1/routes/nhan-vien-kha-dung", headers=_auth(tok))
        assert r.status_code == 200
        body_str = r.text
        assert "phone" not in body_str, "Phản hồi chứa số điện thoại — vi phạm quyền riêng tư"
        assert "email" not in body_str, "Phản hồi chứa email — vi phạm quyền riêng tư"
        assert "@" not in body_str, "Phản hồi chứa '@' — có thể rò email"


# ---------------------------------------------------------------------------
# 3. tao-lich-tuan qua HTTP: 200
# ---------------------------------------------------------------------------


def test_tao_lich_tuan_qua_http(kip_du_lieu: dict) -> None:
    with TestClient(app) as c:
        tok = _token(c, kip_du_lieu["ql"]["phone"])
        tuan = date(2026, 8, 24)
        r = c.post(
            "/api/v1/routes/tao-lich-tuan",
            json={"tuan_bat_dau": tuan.isoformat()},
            headers=_auth(tok),
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
        body = r.json()
        assert "so_chuyen_tao" in body


# ---------------------------------------------------------------------------
# 4. tao-lich-tuan: gọi hai lần không tăng
# ---------------------------------------------------------------------------


def test_tao_lich_tuan_goi_hai_lan_khong_tang(kip_du_lieu: dict) -> None:
    with TestClient(app) as c:
        tok = _token(c, kip_du_lieu["ql"]["phone"])
        tuan = date(2026, 8, 24)
        payload = {"tuan_bat_dau": tuan.isoformat()}

        c.post("/api/v1/routes/tao-lich-tuan", json=payload, headers=_auth(tok))

        before = len(
            c.get("/api/v1/routes", headers=_auth(tok)).json().get("items", [])
        )
        r2 = c.post("/api/v1/routes/tao-lich-tuan", json=payload, headers=_auth(tok))
        after = len(
            c.get("/api/v1/routes", headers=_auth(tok)).json().get("items", [])
        )
        assert r2.json().get("so_chuyen_tao", -1) == 0
        assert after == before


# ---------------------------------------------------------------------------
# 5. get_kip qua HTTP: chỉ có id, full_name, vai_tro
# ---------------------------------------------------------------------------


def test_get_kip_qua_http(kip_du_lieu: dict) -> None:
    with TestClient(app) as c:
        tok = _token(c, kip_du_lieu["ql"]["phone"])
        # Chuyến do fixture dựng phải có mặt trong danh sách.
        routes = c.get("/api/v1/routes", headers=_auth(tok)).json().get("items", [])
        route_id = kip_du_lieu["route_id"]
        assert any(r["id"] == route_id for r in routes), "Chuyến do fixture dựng phải có trong danh sách"
        r = c.get(f"/api/v1/routes/{route_id}/kip", headers=_auth(tok))
        assert r.status_code == 200
        for tv in r.json().get("items", []):
            assert "phone" not in tv
            assert "email" not in tv
            assert "id" in tv
            assert "full_name" in tv
            assert "vai_tro" in tv


# ---------------------------------------------------------------------------
# 6. put_kip qua HTTP: gán 2 người, rồi get kiểm tra
# ---------------------------------------------------------------------------


def test_put_kip_qua_http(kip_du_lieu: dict) -> None:
    with TestClient(app) as c:
        tok = _token(c, kip_du_lieu["ql"]["phone"])
        # Fixture đã dựng sẵn 2 cleaner — không còn đường "không đủ người".
        ds = c.get("/api/v1/routes/nhan-vien-kha-dung", headers=_auth(tok)).json().get("items", [])
        cleaners = [x for x in ds if x.get("role") == "cleaner"]
        assert len(cleaners) >= 2, "Fixture phải dựng đủ 2 cleaner"

        route_id = kip_du_lieu["route_id"]
        user_ids = [cleaners[0]["id"], cleaners[1]["id"]]
        r = c.put(
            f"/api/v1/routes/{route_id}/kip",
            json={"user_ids": user_ids, "truong_kip_id": user_ids[0]},
            headers=_auth(tok),
        )
        assert r.status_code == 200, f"PUT kip failed: {r.text}"

        # Kiểm tra lại
        r2 = c.get(f"/api/v1/routes/{route_id}/kip", headers=_auth(tok))
        assert r2.status_code == 200
        ids_trong_kip = {x["id"] for x in r2.json().get("items", [])}
        assert ids_trong_kip == set(user_ids)


# ---------------------------------------------------------------------------
# 7. Ba endpoint điểm qua HTTP: cư dân gọi, cả ba 200
# ---------------------------------------------------------------------------


def test_ba_endpoint_diem_qua_http(kip_du_lieu: dict) -> None:
    """Cư dân do fixture dựng gọi ba endpoint điểm → cả ba trả 200."""
    with TestClient(app) as c:
        tok = _token(c, kip_du_lieu["cd"]["phone"])

        r1 = c.get("/api/v1/diem/nhan-thuc", headers=_auth(tok))
        assert r1.status_code == 200, f"GET /diem/nhan-thuc: {r1.status_code}"

        r2 = c.get("/api/v1/diem/nhiem-vu", headers=_auth(tok))
        assert r2.status_code == 200, f"GET /diem/nhiem-vu: {r2.status_code}"

        r3 = c.post("/api/v1/diem/nhiem-vu/kiem", json={}, headers=_auth(tok))
        assert r3.status_code == 200, f"POST /diem/nhiem-vu/kiem: {r3.status_code}"
