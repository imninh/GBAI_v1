"""Cất ảnh vào Supabase Storage (gói P38) — KHÔNG test nào chạm mạng thật.

Phần 1 (test 1–7) gọi thẳng ``src.services.luu_tru`` với lớp HTTP giả, đúng khuôn
``test_duong_di_that.py``. Phần 2 (test 8–10) dựng API trong tiến trình, đúng khuôn
``test_endpoints.py``, để chứng minh: Storage hỏng thì ảnh vẫn lưu được (đường
đĩa), đọc ưu tiên Storage rồi mới tới đĩa, và quyền xem ảnh không hề nới ra.
"""

from __future__ import annotations

import io
from collections.abc import Iterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.api.routers import classify as classify_router
from src.api.routers import media as media_router
from src.config import reset_settings_cache
from src.db.models import Base, Media
from src.main import app
from src.services import classifier, luu_tru

MAT_KHAU = "demo1234"
KHO_BI_MAT_TEST = "KHO_BI_MAT_TEST_XYZ"


@pytest.fixture(autouse=True)
def _xoam_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("STORAGE_ENABLED", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_BUCKET", raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


def _bat_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://supabase.example")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", KHO_BI_MAT_TEST)
    monkeypatch.setenv("SUPABASE_BUCKET", "greenbin")
    reset_settings_cache()


class _PhanHoiGia:
    def __init__(self, noi_dung: bytes = b"", ma: int = 200) -> None:
        self.noi_dung = noi_dung
        self.ma = ma
        self.status_code = ma

    def raise_for_status(self) -> _PhanHoiGia:
        if self.ma >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.ma}",
                request=httpx.Request("POST", "http://fake"),
                response=self,
            )
        return self

    @property
    def content(self) -> bytes:
        return self.noi_dung


class _KhachGia:
    """Thay cho httpx.Client — không chạm mạng, giữ lại header để test đọc."""

    def __init__(self, phan_hoi: _PhanHoiGia | None = None, loi: Exception | None = None) -> None:
        self.phan_hoi = phan_hoi
        self.loi = loi
        self.cac_goi: list[tuple[str, str, dict, bytes | None]] = []

    def __enter__(self) -> _KhachGia:
        return self

    def __exit__(self, *args) -> None:
        return None

    def post(self, url: str, *, headers: dict, content: bytes):
        self.cac_goi.append(("POST", url, headers, content))
        return self._tra()

    def get(self, url: str, *, headers: dict):
        self.cac_goi.append(("GET", url, headers, None))
        return self._tra()

    def delete(self, url: str, *, headers: dict):
        self.cac_goi.append(("DELETE", url, headers, None))
        return self._tra()

    def _tra(self):
        if self.loi is not None:
            raise self.loi
        return self.phan_hoi


def _gia_http(monkeypatch: pytest.MonkeyPatch, *, phan_hoi=None, loi=None) -> _KhachGia:
    khach = _KhachGia(phan_hoi=phan_hoi, loi=loi)
    gia = type(
        "GiaHttpx",
        (),
        {
            "Client": lambda *a, **k: khach,
            "HTTPStatusError": httpx.HTTPStatusError,
            "HTTPError": httpx.HTTPError,
            "TimeoutException": httpx.TimeoutException,
        },
    )
    monkeypatch.setattr(luu_tru, "httpx", gia)
    return khach


def _anh_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (120, 200, 80)).save(buf, format="JPEG")
    return buf.getvalue()


# --- Phần 1: hàm thuần của luu_tru ------------------------------------------


def test_tat_co_thi_khong_goi_mang(monkeypatch: pytest.MonkeyPatch) -> None:
    khach = _gia_http(monkeypatch)

    ket_qua = luu_tru.tai_len("khong-ton-tai.jpg", "uploads/2026/08/12/x.jpg")

    assert ket_qua is None
    assert khach.cac_goi == [], "Cờ tắt thì không được gọi mạng một lần nào"


def test_thieu_bien_thi_khong_goi_mang(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_ENABLED", "true")  # nhưng SUPABASE_URL rỗng
    # Máy dev đã cấu hình Storage thật trong `.env` thì hai biến dưới có giá trị,
    # và test này đo nhầm nhánh (gọi mạng thật thay vì thoát sớm). Ép rỗng để
    # nhánh "thiếu biến" luôn được đo đúng, không phụ thuộc môi trường.
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "")
    reset_settings_cache()
    khach = _gia_http(monkeypatch)

    assert luu_tru.tai_len("x.jpg", "khoa") is None
    assert luu_tru.tai_ve("khoa") is None
    assert luu_tru.xoa("khoa") is False
    assert khach.cac_goi == []


def test_tai_len_thanh_cong_tra_khoa(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _bat_storage(monkeypatch)
    tep = tmp_path / "anh.jpg"
    tep.write_bytes(_anh_jpeg())
    khach = _gia_http(monkeypatch, phan_hoi=_PhanHoiGia())

    khoa = luu_tru.tai_len(str(tep), "uploads/2026/08/12/x.jpg")

    assert khoa == "uploads/2026/08/12/x.jpg"
    assert khach.cac_goi[0][0] == "POST"
    assert "storage/v1/object/greenbin/uploads/2026/08/12/x.jpg" in khach.cac_goi[0][1]


def test_dich_vu_hong_thi_tra_none(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _bat_storage(monkeypatch)
    tep = tmp_path / "anh.jpg"
    tep.write_bytes(_anh_jpeg())
    _gia_http(
        monkeypatch,
        loi=httpx.HTTPStatusError("401", request=httpx.Request("POST", "http://fake"), response=_PhanHoiGia(ma=401)),
    )

    assert luu_tru.tai_len(str(tep), "khoa") is None, "4xx phải rơi êm, không ném ngoại lệ"


def test_qua_han_thi_tra_none(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _bat_storage(monkeypatch)
    tep = tmp_path / "anh.jpg"
    tep.write_bytes(_anh_jpeg())
    _gia_http(monkeypatch, loi=httpx.TimeoutException("quá hạn"))

    assert luu_tru.tai_len(str(tep), "khoa") is None


def test_khong_ghi_khoa_bi_mat_vao_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    """Chốt chặn an toàn: khoá BÍ MẬT không được lọt vào một dòng log nào."""
    _bat_storage(monkeypatch)
    tep = tmp_path / "anh.jpg"
    tep.write_bytes(_anh_jpeg())
    _gia_http(monkeypatch, loi=httpx.TimeoutException("quá hạn"))

    with caplog.at_level("WARNING"):
        luu_tru.tai_len(str(tep), "uploads/2026/08/12/x.jpg")

    assert KHO_BI_MAT_TEST not in caplog.text, "Khoá bí mật KHÔNG được xuất hiện trong log"
    assert "uploads/2026/08/12/x.jpg" in caplog.text, "Log phải nói được khoá FILE"


def test_dung_khoa_bi_mat_khong_dung_khoa_cong_khai(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Chốt chặn chính: request từ máy chủ tới bucket RIÊNG TƯ phải mang khoá
    BÍ MẬT (service role). Khoá CÔNG KHAI chỉ dành cho trình duyệt — dùng nó ở
    máy chủ với bucket bật RLS sẽ trả 401/403 và ảnh âm thầm không lên Storage."""
    _bat_storage(monkeypatch)
    tep = tmp_path / "anh.jpg"
    tep.write_bytes(_anh_jpeg())
    khach = _gia_http(monkeypatch, phan_hoi=_PhanHoiGia())

    luu_tru.tai_len(str(tep), "khoa-1")
    luu_tru.tai_ve("khoa-2")
    luu_tru.xoa("khoa-3")

    assert len(khach.cac_goi) == 3
    for _, _, headers, _ in khach.cac_goi:
        assert headers["Authorization"] == f"Bearer {KHO_BI_MAT_TEST}", (
            "Authorization phải dựng từ supabase_secret_key, không phải khoá công khai"
        )


# --- Phần 2: API trong tiến trình --------------------------------------------


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[Session]:
    from scripts.seed import seed_buildings, seed_categories, seed_knowledge, seed_schedules, seed_units, seed_users

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()

    seed_categories(session)
    buildings = seed_buildings(session)
    units = seed_units(session, buildings)
    seed_users(session, units)
    seed_schedules(session, buildings)
    seed_knowledge(session, buildings)
    session.commit()

    def _override() -> Iterator[Session]:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_db] = _override
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    reset_settings_cache()

    from src.services.vision import VisionUnavailableError

    monkeypatch.setattr(
        "src.services.vision.get_vision_client",
        lambda tier="t1": (_ for _ in ()).throw(VisionUnavailableError("test khong goi model")),
    )
    monkeypatch.setattr(classifier, "classify_image_local", lambda *a, **k: None)

    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()


@pytest_asyncio.fixture
async def api(api_session: Session) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _dang_nhap(api: AsyncClient, email: str) -> str:
    response = await api.post("/api/v1/auth/login", json={"email": email, "password": MAT_KHAU})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mo_anh(api_session: Session, uploader_id: int, *, storage_key: str = "", stored_path: str = "") -> Media:
    media = Media(
        uploader_id=uploader_id,
        stored_path=stored_path,
        original_path="",
        storage_key=storage_key,
        original_storage_key="",
        phash="",
        bytes_size=0,
    )
    api_session.add(media)
    api_session.flush()
    return media


@pytest.mark.asyncio
async def test_storage_hong_thi_van_tao_duoc_media(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import FakeVisionClient, make_result

    fake = FakeVisionClient(results=[make_result(confidence=0.91)])
    monkeypatch.setattr(classifier, "get_vision_client", lambda tier="t1": fake)
    monkeypatch.setattr(classifier, "get_tier_model", lambda tier="t1": tier)
    monkeypatch.setattr(classifier, "get_tier_provider", lambda tier="t1": "fake")
    # Storage hỏng: tai_len luôn trả None → vẫn phải tạo Media, khoá rỗng.
    monkeypatch.setattr(classify_router, "tai_len", lambda *a, **k: None)

    token = await _dang_nhap(api, "resident@demo.vn")
    response = await api.post(
        "/api/v1/classify",
        data={"text_query": "chai nhựa"},
        files={"image": ("anh.jpg", _anh_jpeg(), "image/jpeg")},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text

    media = api_session.scalar(select(Media).order_by(Media.id.desc()))
    assert media is not None, "Storage hỏng KHÔNG được chặn việc tạo Media"
    assert media.storage_key == "", "tai_len None → khoá phải rỗng, không nổ"

    anh = await api.get(f"/api/v1/media/{media.id}", headers=_auth(token))
    assert anh.status_code == 200, "Ảnh vẫn xem được qua đường đĩa"


@pytest.mark.asyncio
async def test_doc_uu_tien_storage_roi_moi_toi_dia(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    media = _mo_anh(api_session, uploader_id=1, storage_key="uploads/2026/08/12/x.jpg", stored_path="khong-ton-tai.jpg")
    api_session.commit()

    # (a) Có storage_key + tai_ve trả dữ liệu → KHÔNG đọc đĩa (đĩa không tồn tại
    #     nhưng vẫn phải trả ảnh từ Storage).
    monkeypatch.setattr(media_router, "tai_ve", lambda *a, **k: b"TUI-TU-STORAGE")
    anh = await api.get(f"/api/v1/media/{media.id}", headers=_auth(token))
    assert anh.status_code == 200
    assert anh.content == b"TUI-TU-STORAGE", "Phải ưu tiên Storage trước đường đĩa"

    # (b) tai_ve trả None → rơi về đĩa.
    tep_dia = api_session.get(Media, media.id).stored_path  # giữ giá trị cũ
    import pathlib

    tep = pathlib.Path(tep_dia)
    tep.parent.mkdir(parents=True, exist_ok=True)
    tep.write_bytes(b"TUI-TU-DIA")
    monkeypatch.setattr(media_router, "tai_ve", lambda *a, **k: None)

    anh = await api.get(f"/api/v1/media/{media.id}", headers=_auth(token))
    assert anh.status_code == 200
    assert anh.content == b"TUI-TU-DIA", "tai_ve None phải rơi về FileResponse đường đĩa"


@pytest.mark.asyncio
async def test_khong_noi_quyen_xem_anh(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cư dân khác mở ảnh không phải của mình → 403, kể cả khi ảnh nằm trên Storage."""
    media = _mo_anh(api_session, uploader_id=1, storage_key="uploads/2026/08/12/x.jpg", stored_path="")
    api_session.commit()

    def khong_duoc_goi(*args, **kwargs):
        raise AssertionError("tai_ve không được gọi khi chưa qua phép kiểm quyền")

    monkeypatch.setattr(media_router, "tai_ve", khong_duoc_goi)

    token = await _dang_nhap(api, "resident2@demo.vn")  # cư dân khác
    response = await api.get(f"/api/v1/media/{media.id}", headers=_auth(token))

    assert response.status_code == 403
