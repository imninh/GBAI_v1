"""Đi trọn kịch bản demo bằng một lệnh, trên BẢN SAO ``data/app.db`` (gói P21).

Repo có hơn 500 test nhưng không test nào nối các mảnh thành một chuỗi như buổi
demo sẽ đi. Script này chạy đúng chuỗi 9 bước qua API **trong tiến trình**
(``httpx.AsyncClient(transport=ASGITransport(app))`` — không cần cổng, không đụng
uvicorn) trên một **bản sao** của ``data/app.db``, để trả lời câu hỏi mà test
(dựng CSDL mới mỗi lần) không bao giờ trả lời được:

*"dữ liệu demo hiện tại có đi trọn được đường không?"*

    python scripts/thu_kich_ban_demo.py
    python scripts/thu_kich_ban_demo.py --db-url "sqlite:///duong-den-ban-sao.db"

Không bao giờ ghi vào ``data/app.db``. Bước phân loại dùng model giả (như cả bộ
test) — script kiểm đường DỮ LIỆU, không phải chất lượng model, và không được
phụ thuộc máy đang có API key hay không.

Mã thoát: ``0`` chỉ khi đủ 9 bước; gãy giữa chừng trả về ``1`` — đừng để ai chạy
script này trong một chuỗi lệnh mà tin một cái ``0`` giả.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from src.db.models import AuditLog, User  # noqa: E402
from src.db.session import get_session_factory, init_db, reset_engine  # noqa: E402

MAT_KHAU = "demo1234"
TONG_SO_BUOC = 9


class _BuocError(Exception):
    """Một bước không đi qua được — kèm lý do bằng tiếng Việt để in ra."""


def _dung_model_gia() -> None:
    """Thay model thật bằng bản giả — script kiểm đường DỮ LIỆU, không phải model.

    Demo thật sẽ gọi model thật; ở đây giữ cho lần chạy smoke-test không tiêu
    quota, không gọi mạng, và không phụ thuộc máy đang có key hay không.
    """
    from src.services import classifier, rag
    from src.services.vision import Usage, VisionResult, VisionUnavailableError

    class _Fake:
        def classify_text(self, text, categories, model):
            return VisionResult(
                item_name="Hộp sữa giấy tráng nhôm",
                category_code="recyclable_paper",
                confidence=0.91,
                items=[
                    {"name": "Hộp sữa giấy tráng nhôm", "category_code": "recyclable_paper", "confidence": 0.91}
                ],
                usage=Usage(tokens_in=0, tokens_out=0, cost_usd=0.0, price_known=True),
            )

        def classify_image(self, image_bytes, categories, model):
            return self.classify_text("", categories, model)

    classifier.get_vision_client = lambda tier="t1": _Fake()
    classifier.get_tier_model = lambda tier="t1": f"model-{tier}"
    classifier.get_tier_provider = lambda tier="t1": "fake"
    classifier.classify_image_local = lambda *a, **k: None

    # Node advise gọi ``src.services.vision.get_vision_client("text")`` trực tiếp —
    # ép nó ném để lui về hướng dẫn chuẩn của danh mục, không gọi model thật.
    import src.services.vision as vision

    def _chan_text_client(tier="t1"):
        raise VisionUnavailableError("script khong goi model that")

    vision.get_vision_client = _chan_text_client

    # CSDL demo có thể đã nhúng vector → bước advise sẽ gọi embedding thật.
    # Ép về BM25 thuần, không mạng.
    rag.embed_texts = lambda texts: []


def _chuan_bi_csdl(db_url: str) -> Path | None:
    """Trỏ ``DATABASE_URL`` vào bản sao, vá cột như app làm lúc khởi động.

    Returns:
        Đường dẫn bản sao tạm để xoá lúc kết thúc, hoặc ``None`` khi người dùng
        tự truyền ``--db-url``.
    """
    if db_url:
        os.environ["DATABASE_URL"] = db_url
        return None

    goc = Path(__file__).resolve().parents[1] / "data" / "app.db"
    if not goc.exists():
        print(f"❌ Không tìm thấy {goc} — chạy `python scripts/seed.py --reset --demo` trước.")
        raise SystemExit(1)

    ban_sao = Path(tempfile.gettempdir()) / f"thu-kich-ban-demo-{os.getpid()}.db"
    shutil.copy2(goc, ban_sao)
    os.environ["DATABASE_URL"] = f"sqlite:///{ban_sao.as_posix()}"
    print(f"Đã chép {goc} → bản sao tạm {ban_sao}")
    return ban_sao


def _dem_audit() -> int:
    with get_session_factory()() as phien:
        return int(phien.scalar(select(func.count(AuditLog.id))) or 0)


async def _chay_tat_ca(api: AsyncClient) -> int:
    """Chạy 9 bước; trả về số bước đã ĐẠT (dừng ở bước hỏng đầu tiên)."""
    so_buoc_dat = 0
    bau_vat: dict[str, str] = {"ngay_thu": ""}
    # Chụp TRƯỚC cả chuỗi — bước 9 so với con số này để chứng minh có thêm dòng.
    so_audit_truoc = _dem_audit()

    def _hoi_du_lieu(so: str, ten: str) -> dict:
        """Lấy một tài khoản demo từ CSDL mà app đang dùng."""
        with get_session_factory()() as phien:
            dong = phien.scalar(select(User).where(User.email == f"{so}@demo.vn"))
        if dong is None:
            raise _BuocError(f"không tìm thấy tài khoản {so}@demo.vn trong CSDL demo")
        return {"email": dong.email, "phone": dong.phone, "full_name": dong.full_name}

    # Bước 1 — Cư dân đăng nhập bằng số điện thoại
    try:
        cu_dan = _hoi_du_lieu("resident", "cư dân")
        if not cu_dan["phone"]:
            raise _BuocError("tài khoản cư dân demo chưa có số điện thoại")
        response = await api.post(
            "/api/v1/auth/login", json={"phone": cu_dan["phone"], "password": MAT_KHAU}
        )
        if response.status_code != 200:
            raise _BuocError(f"HTTP {response.status_code} — {response.text}")
        than = response.json()
        if than["user"]["role"] != "resident":
            raise _BuocError(f"vai trò trả về là '{than['user']['role']}', không phải resident")
        bau_vat["token_resident"] = than["token"]
        so_buoc_dat = 1
    except _BuocError as loi:
        print(f"❌ Bước 1/{TONG_SO_BUOC} — Cư dân đăng nhập bằng số điện thoại: {loi}")
        print("   Bước tiếp theo cần: token cư dân để phân loại bằng chữ.")
        return so_buoc_dat
    print(f"✅ Bước 1/{TONG_SO_BUOC} — Cư dân đăng nhập bằng số điện thoại ({cu_dan['phone']})")

    def _auth() -> dict[str, str]:
        return {"Authorization": f"Bearer {bau_vat['token_resident']}"}

    # Bước 2 — Cư dân phân loại bằng mô tả bằng chữ
    try:
        response = await api.post(
            "/api/v1/classify/text",
            json={"text_query": "hộp sữa giấy tráng nhôm"},
            headers=_auth(),
        )
        if response.status_code != 200:
            raise _BuocError(f"HTTP {response.status_code} — {response.text}")
        phan_loai = response.json()
        if not phan_loai["category"] or not phan_loai["category"]["code"]:
            raise _BuocError("không có nhãn phân loại")
        if not phan_loai["advice"]:
            raise _BuocError("không có hướng dẫn xử lý")
        if not phan_loai["advice_sources"]:
            raise _BuocError("hướng dẫn không kèm trích nguồn quy định")
        so_buoc_dat = 2
    except _BuocError as loi:
        print(f"❌ Bước 2/{TONG_SO_BUOC} — Cư dân phân loại bằng chữ: {loi}")
        print("   Bước tiếp theo cần: nhãn + hướng dẫn để người dùng hiểu rác bỏ đâu.")
        return so_buoc_dat
    print(f"✅ Bước 2/{TONG_SO_BUOC} — Cư dân phân loại bằng chữ ({phan_loai['category']['code']})")

    # Bước 3 — Cư dân tạo yêu cầu thu gom đồ cồng kềnh vượt ngưỡng
    try:
        ngay_thu = (date.today() + timedelta(days=3)).isoformat()
        bau_vat["ngay_thu"] = ngay_thu
        cac_yeu_cau: dict[str, dict] = {}
        for ten in ("a", "b"):
            response = await api.post(
                "/api/v1/pickups",
                json={
                    "items": [{"name": "Tủ gỗ cũ", "category_code": "bulky", "qty": 1}],
                    "est_weight_kg": 40,
                    "preferred_date": ngay_thu,
                    "preferred_window": "08:00-10:00",
                    "confirmed_no_hazardous": True,
                },
                headers=_auth(),
            )
            if response.status_code != 200:
                raise _BuocError(f"HTTP {response.status_code} — {response.text}")
            yeu_cau = response.json()
            if yeu_cau["status"] != "cho_duyet":
                raise _BuocError(f"yêu cầu phải ở 'cho_duyet', nhận được '{yeu_cau['status']}'")
            cac_yeu_cau[ten] = yeu_cau
        so_buoc_dat = 3
    except _BuocError as loi:
        print(f"❌ Bước 3/{TONG_SO_BUOC} — Cư dân tạo yêu cầu thu gom: {loi}")
        print("   Bước tiếp theo cần: ít nhất một yêu cầu vượt ngưỡng ở trạng thái cho_duyet.")
        return so_buoc_dat
    print(f"✅ Bước 3/{TONG_SO_BUOC} — Cư dân tạo 2 yêu cầu thu gom (cho_duyet)")

    # Bước 4 — Đơn vị thu gom đăng nhập và duyệt cả hai yêu cầu
    try:
        nhan_vien = _hoi_du_lieu("manager", "quản lý")
        response = await api.post(
            "/api/v1/auth/login", json={"email": nhan_vien["email"], "password": MAT_KHAU}
        )
        if response.status_code != 200:
            raise _BuocError(f"HTTP {response.status_code} — {response.text}")
        bau_vat["token_manager"] = response.json()["token"]
        for ten in ("a", "b"):
            response = await api.post(
                f"/api/v1/pickups/{cac_yeu_cau[ten]['id']}/review",
                json={"action": "approve"},
                headers={"Authorization": f"Bearer {bau_vat['token_manager']}"},
            )
            if response.status_code != 200:
                raise _BuocError(f"duyệt #{cac_yeu_cau[ten]['id']}: HTTP {response.status_code} — {response.text}")
            if response.json()["status"] != "cho_nhan":
                raise _BuocError(f"yêu cầu #{cac_yeu_cau[ten]['id']} phải về 'cho_nhan' sau khi duyệt")
        so_buoc_dat = 4
    except _BuocError as loi:
        print(f"❌ Bước 4/{TONG_SO_BUOC} — Đơn vị thu gom duyệt yêu cầu: {loi}")
        print("   Bước tiếp theo cần: hai yêu cầu ở trạng thái cho_nhan để xếp tuyến.")
        return so_buoc_dat
    print(f"✅ Bước 4/{TONG_SO_BUOC} — Đơn vị thu gom duyệt 2 yêu cầu (cho_nhan)")

    # Bước 5 — Agent xếp tuyến
    try:
        response = await api.post(
            "/api/v1/routes/propose",
            json={"service_date": bau_vat["ngay_thu"], "window": "08:00-10:00", "capacity_kg": 500},
            headers={"Authorization": f"Bearer {bau_vat['token_manager']}"},
        )
        if response.status_code != 200:
            raise _BuocError(f"HTTP {response.status_code} — {response.text}")
        tuyen = response.json()
        if tuyen["status"] != "proposed":
            raise _BuocError(f"tuyến phải ở 'proposed', nhận được '{tuyen['status']}'")
        if len(tuyen["stops"]) < 1:
            raise _BuocError("tuyến không có điểm dừng nào")
        if not tuyen["reasoning"].get("criteria"):
            raise _BuocError("không có lời giải thích vì sao gộp thế này")
        so_buoc_dat = 5
    except _BuocError as loi:
        print(f"❌ Bước 5/{TONG_SO_BUOC} — Agent xếp tuyến: {loi}")
        print("   Bước tiếp theo cần: một tuyến proposed có điểm dừng để người duyệt sửa rồi chốt.")
        return so_buoc_dat
    print(f"✅ Bước 5/{TONG_SO_BUOC} — Agent xếp tuyến ({len(tuyen['stops'])} điểm dừng, proposed)")

    # Bước 6 — Duyệt tuyến kèm bỏ một điểm để diff khác bản AI
    try:
        diem_b = next((s for s in tuyen["stops"] if s.get("request_id") == cac_yeu_cau["b"]["id"]), None)
        diem_bot = diem_b or tuyen["stops"][0]
        response = await api.post(
            f"/api/v1/routes/{tuyen['id']}/review",
            json={"action": "approve_with_changes", "removed_stops": [diem_bot["stop_id"]]},
            headers={"Authorization": f"Bearer {bau_vat['token_manager']}"},
        )
        if response.status_code != 200:
            raise _BuocError(f"HTTP {response.status_code} — {response.text}")
        duyet = response.json()
        if duyet["status"] != "approved":
            raise _BuocError(f"tuyến phải được duyệt, nhận được '{duyet['status']}'")
        if not duyet.get("diff", {}).get("changed"):
            raise _BuocError("bỏ điểm dừng nhưng diff không khác bản AI đề xuất")
        so_buoc_dat = 6
    except _BuocError as loi:
        print(f"❌ Bước 6/{TONG_SO_BUOC} — Duyệt tuyến (bỏ một điểm): {loi}")
        print("   Bước tiếp theo cần: tuyến approved và một yêu cầu ở cho_nhan để đội vệ sinh xử lý.")
        return so_buoc_dat
    print(f"✅ Bước 6/{TONG_SO_BUOC} — Duyệt tuyến kèm bỏ điểm (approved, diff thay đổi)")

    # Bước 7 — Nhân viên vệ sinh đẩy yêu cầu B tới giao đơn vị
    try:
        nhan_vien = _hoi_du_lieu("cleaner", "nhân viên vệ sinh")
        response = await api.post(
            "/api/v1/auth/login", json={"email": nhan_vien["email"], "password": MAT_KHAU}
        )
        if response.status_code != 200:
            raise _BuocError(f"HTTP {response.status_code} — {response.text}")
        bau_vat["token_cleaner"] = response.json()["token"]
        yeu_cau_b_id = cac_yeu_cau["b"]["id"]
        for buoc in ("da_nhan", "dang_van_chuyen", "da_giao_don_vi"):
            response = await api.post(
                f"/api/v1/pickups/{yeu_cau_b_id}/chuyen-trang-thai",
                json={"den": buoc},
                headers={"Authorization": f"Bearer {bau_vat['token_cleaner']}"},
            )
            if response.status_code != 200:
                raise _BuocError(f"đẩy tới {buoc}: HTTP {response.status_code} — {response.text}")
            if response.json()["status"] != buoc:
                raise _BuocError(f"phải đang ở '{buoc}', nhận được '{response.json()['status']}'")
        so_buoc_dat = 7
    except _BuocError as loi:
        print(f"❌ Bước 7/{TONG_SO_BUOC} — Nhân viên vệ sinh đẩy trạng thái: {loi}")
        print("   Bước tiếp theo cần: yêu cầu ở da_giao_don_vi để xác nhận khối lượng thật.")
        return so_buoc_dat
    print(f"✅ Bước 7/{TONG_SO_BUOC} — Nhân viên vệ sinh đẩy yêu cầu tới da_giao_don_vi")

    # Bước 8 — Xác nhận khối lượng THẬT nằm trong khoảng → hoàn tất
    try:
        response = await api.post(
            f"/api/v1/pickups/{yeu_cau_b_id}/xac-nhan-khoi-luong",
            json={"weight_confirmed_kg": 40.0},
            headers={"Authorization": f"Bearer {bau_vat['token_cleaner']}"},
        )
        if response.status_code != 200:
            raise _BuocError(f"HTTP {response.status_code} — {response.text}")
        if response.json()["status"] != "hoan_tat":
            raise _BuocError(f"cân đúng khoảng phải hoàn tất, nhận được '{response.json()['status']}'")
        so_buoc_dat = 8
    except _BuocError as loi:
        print(f"❌ Bước 8/{TONG_SO_BUOC} — Xác nhận khối lượng thật: {loi}")
        print("   Bước tiếp theo cần: yêu cầu hoàn tất để màn lịch sử cư dân có số thật.")
        return so_buoc_dat
    print(f"✅ Bước 8/{TONG_SO_BUOC} — Xác nhận khối lượng thật (hoan_tat)")

    # Bước 9 — Audit log dày lên
    try:
        if _dem_audit() <= so_audit_truoc:
            raise _BuocError(
                f"số dòng audit không tăng (trước {so_audit_truoc}, sau {_dem_audit()}) "
                "— các thao tác ghi trong chuỗi không để lại dấu vết"
            )
        so_buoc_dat = 9
    except _BuocError as loi:
        print(f"❌ Bước 9/{TONG_SO_BUOC} — Audit log dày lên: {loi}")
        return so_buoc_dat
    print(f"✅ Bước 9/{TONG_SO_BUOC} — Audit log dày lên ({so_audit_truoc} → {_dem_audit()} dòng)")

    return so_buoc_dat


def main() -> int:
    # PHẢI đứng trước `ArgumentParser`: `--help` in mô tả tiếng Việt rồi thoát
    # ngay trong `parse_args()` — đặt sau là quá muộn, console Windows cp1252 sẽ
    # nổ `UnicodeEncodeError`. Giữ guard vì pytest thay stdout bằng đối tượng
    # không có ``reconfigure`` (gói P7 đã vấp đúng chỗ này).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Đi trọn kịch bản demo trên bản sao data/app.db")
    parser.add_argument("--db-url", default="", help="DSN cần dùng. Bỏ trống thì chép data/app.db ra bản sao tạm.")
    tham_so = parser.parse_args()

    ban_sao = _chuan_bi_csdl(tham_so.db_url)
    reset_engine()
    init_db()  # create_all + va_cot_thieu — y như app làm lúc khởi động

    # Đường dây logging của schema_patch là chuyện nội bộ — script in báo cáo riêng.
    logging.getLogger("src.db.schema_patch").setLevel(logging.ERROR)

    from src.main import app  # noqa: E402

    _dung_model_gia()

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        so_buoc_dat = asyncio.run(_chay_tat_ca(client))
    finally:
        asyncio.run(client.aclose())
        reset_engine()  # đóng các kết nối đang giữ file trước khi xoá bản sao
        if ban_sao is not None:
            ban_sao.unlink(missing_ok=True)

    print(f"\nXong {so_buoc_dat}/{TONG_SO_BUOC} bước.")
    # Mã thoát phải nói thật: 0 chỉ khi đủ cả 9 bước, gãy giữa chừng thì 1.
    # Trả 0 mù khi script vừa in ❌ là nói dối đúng lúc người ta cần nó nói thật.
    return 0 if so_buoc_dat == TONG_SO_BUOC else 1


if __name__ == "__main__":
    raise SystemExit(main())
