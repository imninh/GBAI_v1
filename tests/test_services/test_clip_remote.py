"""Tầng T0.5 đường `remote` (gói H1) — gọi HTTP sang Hugging Face Space.

Không test nào chạm mạng thật: lớp gọi HTTP được thay bằng giả lập. Trọng tâm
là **rơi êm tuyệt đối** — Space ngủ / quá hạn / trả rác đều phải đưa ảnh lên T1,
không ngoại lệ nào thoát ra khỏi tầng.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from PIL import Image

from src.config import reset_settings_cache
from src.services.vision import local_clip
from src.services.vision.base import CategoryOption

_NHOM = [
    CategoryOption(code="recyclable", name="Rác tái chế", is_hazardous=False, hint="a photo of paper|a photo of glass"),
    CategoryOption(code="hazardous", name="Rác nguy hại", is_hazardous=True, hint="a photo of a battery"),
]


@pytest.fixture(autouse=True)
def _don_trang_thai(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Bộ đếm/flag cấp module phải dọn giữa các test, và cache cấu hình nữa."""
    monkeypatch.setattr(local_clip, "_remote_thieu_url_da_bao", False)
    reset_settings_cache()
    yield
    reset_settings_cache()


def _anh(rong: int = 400, cao: int = 300) -> Image.Image:
    return Image.new("RGB", (rong, cao), (120, 200, 80))


def _anh_bytes() -> bytes:
    buf = io.BytesIO()
    _anh().save(buf, format="JPEG")
    return buf.getvalue()


def _prompts_nhom() -> list[str]:
    return [p for c in _NHOM for p in local_clip._prompts_for(c)]


def _bam_phan_hoi() -> dict:
    """JSON hợp lệ đúng khuôn Space trả về, hash khớp với bộ câu mô tả."""
    return {
        "nhan": "recyclable",
        "diem": 0.91,
        "moi_nhan": {"recyclable": 0.91, "hazardous": 0.09},
        "prompt_hash": local_clip._bam_prompt(_prompts_nhom()),
    }


class _PhanHoiGia:
    """Phản hồi HTTP giả: raise_for_status trả về chính nó, json trả dữ liệu."""

    def __init__(self, du_lieu: object, loi: BaseException | None = None) -> None:
        self._du_lieu = du_lieu
        self._loi = loi

    def raise_for_status(self) -> _PhanHoiGia:
        if self._loi is not None:
            raise self._loi
        return self

    def json(self):
        return self._du_lieu


class _KhachHangGia:
    """Thay cho httpx.Client — không chạm mạng, trả phản hồi tuỳ cấu hình."""

    def __init__(self, phan_hoi: object | None = None, loi: BaseException | None = None) -> None:
        self.phan_hoi = phan_hoi
        self.loi = loi
        self.so_lan_goi = 0

    def __enter__(self) -> _KhachHangGia:
        return self

    def __exit__(self, *args) -> None:
        return None

    def post(self, *args, **kwargs) -> object:
        self.so_lan_goi += 1
        if self.loi is not None:
            raise self.loi
        return self.phan_hoi


def _gan_remote(monkeypatch: pytest.MonkeyPatch, khach: _KhachHangGia | None = None) -> _KhachHangGia:
    """Bật CLIP_RUNTIME=remote, trỏ URL giả, thay httpx.Client bằng giả lập."""
    import httpx as _httpx

    monkeypatch.setenv("CLIP_RUNTIME", "remote")
    monkeypatch.setenv("CLIP_REMOTE_URL", "https://space.example")
    reset_settings_cache()
    khach = khach or _KhachHangGia(phan_hoi=_PhanHoiGia(_bam_phan_hoi()))
    monkeypatch.setattr(_httpx, "Client", lambda *a, **k: khach)
    return khach


# --- Chọn đường chạy -------------------------------------------------------


def test_runtime_khac_remote_thi_khong_goi_mang(monkeypatch: pytest.MonkeyPatch) -> None:
    """`CLIP_RUNTIME=onnx` thì không một dòng nào của nhánh remote chạy."""
    import httpx as _httpx

    dem = [0]

    class _CamGoiMang:
        def __init__(self, *args, **kwargs) -> None:
            dem[0] += 1

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, *args, **kwargs):
            raise AssertionError("CLIP_RUNTIME=onnx mà vẫn gọi mạng")

    monkeypatch.setenv("CLIP_RUNTIME", "onnx")
    reset_settings_cache()
    monkeypatch.setattr(local_clip, "_load_onnx", lambda: None)
    monkeypatch.setattr(_httpx, "Client", _CamGoiMang)

    ket_qua = local_clip.classify_image_local(_anh_bytes(), _NHOM)

    assert ket_qua is None
    assert dem[0] == 0, "Không được gọi HTTP lần nào khi runtime không phải remote"


def test_url_rong_thi_coi_nhu_tat(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """`CLIP_RUNTIME=remote` mà URL rỗng → không nổ, coi như tầng T0.5 tắt."""
    monkeypatch.setenv("CLIP_RUNTIME", "remote")
    monkeypatch.setenv("CLIP_REMOTE_URL", "")
    reset_settings_cache()

    with caplog.at_level("WARNING"):
        ket_qua = local_clip.classify_image_local(_anh_bytes(), _NHOM)

    assert ket_qua is None
    assert "clip_remote_url" in caplog.text, "Phải có cảnh báo tiếng Việt nói rõ chuyện gì"


# --- Gọi được / hỏng rồi rơi êm -------------------------------------------


def test_goi_duoc_va_doc_dung_nhan(monkeypatch: pytest.MonkeyPatch) -> None:
    khach = _gan_remote(monkeypatch)

    ket_qua = local_clip.classify_image_local(_anh_bytes(), _NHOM)

    assert ket_qua is not None
    assert ket_qua.category_code == "recyclable"
    assert ket_qua.confidence == 0.91
    assert "remote" in ket_qua.model, "Phải ghi rõ đang chạy đường nào để trace đọc được"
    assert khach.so_lan_goi == 1, "Đúng một lệnh gọi HTTP cho một ảnh"


def test_qua_han_thi_roi_ve_khong_co_ket_qua(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan_remote(monkeypatch, _KhachHangGia(loi=httpx.TimeoutException("Space ngủ quá lâu")))

    assert local_clip.classify_image_local(_anh_bytes(), _NHOM) is None


def test_dich_vu_tra_rac_thi_roi_ve_khong_co_ket_qua(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan_remote(monkeypatch, _KhachHangGia(phan_hoi=_PhanHoiGia({"nhan": "x", "diem": 0.5})))

    assert local_clip.classify_image_local(_anh_bytes(), _NHOM) is None


@pytest.mark.parametrize(
    "loai_loi",
    ["timeout", "http_500", "tra_list", "thieu_khoa", "diem_sai_kieu"],
)
def test_khong_ngoai_le_nao_thoat_ra(monkeypatch: pytest.MonkeyPatch, loai_loi: str) -> None:
    """Mọi ca hỏng của Space đều phải rơi êm về None, không ném ra ngoài."""
    import httpx as _httpx

    cac_truong_hop: dict[str, _KhachHangGia] = {
        "timeout": _KhachHangGia(loi=_httpx.TimeoutException("quá hạn")),
        "http_500": _KhachHangGia(phan_hoi=_PhanHoiGia({}, loi=_httpx.HTTPStatusError("500", request=None, response=None))),
        "tra_list": _KhachHangGia(phan_hoi=_PhanHoiGia(["không phải object"])),
        "thieu_khoa": _KhachHangGia(phan_hoi=_PhanHoiGia({"nhan": "x"})),
        "diem_sai_kieu": _KhachHangGia(
            phan_hoi=_PhanHoiGia(
                {
                    "nhan": "x",
                    "diem": 0.5,
                    "moi_nhan": {"recyclable": "không phải số"},
                    "prompt_hash": local_clip._bam_prompt(_prompts_nhom()),
                }
            )
        ),
    }
    khach = cac_truong_hop[loai_loi]
    monkeypatch.setenv("CLIP_RUNTIME", "remote")
    monkeypatch.setenv("CLIP_REMOTE_URL", "https://space.example")
    reset_settings_cache()
    monkeypatch.setattr(_httpx, "Client", lambda *a, **k: khach)

    assert local_clip.classify_image_local(_anh_bytes(), _NHOM) is None


# --- Bộ file của Space -----------------------------------------------------


def test_requirements_cua_space_khong_co_torch() -> None:
    """Cả gói H1 sinh ra vì torch không vừa RAM — để nó lọt vào là hỏng mục đích."""
    duong_dan = Path(__file__).resolve().parents[2] / "hf_space" / "requirements.txt"
    cac_dong = duong_dan.read_text(encoding="utf-8").splitlines()

    co_torch = [dong for dong in cac_dong if dong.strip().startswith("torch")]
    assert not co_torch, f"hf_space/requirements.txt không được có torch: {co_torch}"
    assert cac_dong, "requirements.txt phải có nội dung"
