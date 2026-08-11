"""Test tầng T0.5 sau khi tách thành hai đường chạy (ADR-0007).

Các test ở đây **không cần file model 89 MB** — nó không nằm trong repo. Thứ
được giữ ở đây là phần dễ hỏng trong im lặng: tiền xử lý ảnh, chốt chặn khi câu
mô tả lệch, và việc tự lui về đường khác khi một đường không dùng được.
"""

from __future__ import annotations

import io
from collections.abc import Iterator

import pytest
from PIL import Image

from src.config import reset_settings_cache
from src.services.vision import local_clip
from src.services.vision.base import CategoryOption


@pytest.fixture(autouse=True)
def _don_trang_thai(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Model nạp một lần rồi giữ trong biến toàn cục — phải dọn giữa các test."""
    monkeypatch.setattr(local_clip, "_onnx_session", None)
    monkeypatch.setattr(local_clip, "_onnx_meta", None)
    monkeypatch.setattr(local_clip, "_onnx_failed", False)
    monkeypatch.setattr(local_clip, "_torch_model", None)
    monkeypatch.setattr(local_clip, "_torch_processor", None)
    monkeypatch.setattr(local_clip, "_torch_failed", False)
    reset_settings_cache()
    yield
    reset_settings_cache()


def _anh(rong: int = 400, cao: int = 300) -> Image.Image:
    return Image.new("RGB", (rong, cao), (120, 200, 80))


def _anh_bytes() -> bytes:
    buf = io.BytesIO()
    _anh().save(buf, format="JPEG")
    return buf.getvalue()


_NHOM = [
    CategoryOption(code="recyclable", name="Rác tái chế", is_hazardous=False, hint="a photo of paper|a photo of glass"),
    CategoryOption(code="hazardous", name="Rác nguy hại", is_hazardous=True, hint="a photo of a battery"),
]


# --- Tiền xử lý ảnh -------------------------------------------------------


def test_tien_xu_ly_ra_dung_khuon_clip_nhan() -> None:
    ra = local_clip.tien_xu_ly_anh(_anh(), 224, [0.5, 0.5, 0.5], [0.5, 0.5, 0.5])

    assert ra.shape == (1, 3, 224, 224)
    assert ra.dtype.name == "float32"


def test_tien_xu_ly_cat_giua_chu_khong_bop_meo_anh() -> None:
    """Ảnh rất dài mà bị bóp méo thì CLIP nhìn ra thứ khác hẳn."""
    import numpy as np

    anh = Image.new("RGB", (1000, 250), (0, 0, 0))
    # Vệt trắng đúng giữa ảnh — sau khi cắt giữa nó vẫn phải nằm giữa.
    anh.paste((255, 255, 255), (480, 0, 520, 250))

    ra = local_clip.tien_xu_ly_anh(anh, 224, [0.0, 0.0, 0.0], [1.0, 1.0, 1.0])
    cot = ra[0, 0].mean(axis=0)
    # Trọng tâm của vệt trắng theo chiều ngang. Dùng trọng tâm chứ không dùng
    # argmax vì đỉnh của vệt là một vùng bằng phẳng, argmax chỉ trả về mép trái.
    trong_tam = float((np.arange(len(cot)) * cot).sum() / cot.sum())

    assert trong_tam == pytest.approx(112, abs=6)


def test_tien_xu_ly_co_chuan_hoa_theo_mean_std() -> None:
    import numpy as np

    anh = Image.new("RGB", (224, 224), (255, 255, 255))

    ra = local_clip.tien_xu_ly_anh(anh, 224, [1.0, 1.0, 1.0], [0.5, 0.5, 0.5])

    # (1,0 - 1,0) / 0,5 = 0
    assert np.allclose(ra, 0.0, atol=1e-5)


# --- Chốt chặn khi câu mô tả lệch ----------------------------------------


class _PhienGia:
    """Thay cho phiên onnxruntime — trả về một dãy số cố định."""

    def __init__(self, so_chieu: int = 4) -> None:
        import numpy as np

        self.emb = np.zeros((1, so_chieu), dtype="float32")
        self.emb[0, 0] = 1.0

    def run(self, _outputs, _inputs):
        return [self.emb]


def _meta_gia(prompts: list[str]) -> dict:
    """Dãy số giả: prompt đầu trùng khít với ảnh, prompt sau thì không."""
    import numpy as np

    emb = np.zeros((len(prompts), 4), dtype="float32")
    emb[0, 0] = 1.0
    for i in range(1, len(prompts)):
        emb[i, 1] = 1.0
    return {
        "prompt_hash": local_clip._bam_prompt(prompts),
        "logit_scale": 100.0,
        "owner_codes": ["recyclable"] + ["hazardous"] * (len(prompts) - 1),
        "text_embeddings": emb,
        "image_preprocess": {"size": 224, "mean": [0.0, 0.0, 0.0], "std": [1.0, 1.0, 1.0]},
    }


def test_cau_mo_ta_doi_thi_bo_qua_duong_onnx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dãy số tính sẵn ứng với bộ câu cũ — chấm bằng nó là chấm sai trong im lặng.

    Đây là lớp lỗi nguy hiểm nhất của cách làm này: không có exception nào,
    chỉ có điểm số sai. Thà tắt tầng còn hơn.
    """
    meta = _meta_gia(["a photo of paper", "a photo of glass", "a photo of a battery"])
    monkeypatch.setattr(local_clip, "_load_onnx", lambda: (_PhienGia(), meta))

    ket_qua = local_clip._diem_onnx(_anh(), ["câu mô tả hoàn toàn khác"])

    assert ket_qua is None


def test_cau_mo_ta_khop_thi_cham_diem_binh_thuong(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = ["a photo of paper", "a photo of glass", "a photo of a battery"]
    monkeypatch.setattr(local_clip, "_load_onnx", lambda: (_PhienGia(), _meta_gia(prompts)))

    ket_qua = local_clip._diem_onnx(_anh(), prompts)

    assert ket_qua is not None
    assert ket_qua["recyclable"] > ket_qua["hazardous"]
    assert 0.0 <= ket_qua["recyclable"] <= 1.0


# --- Chọn đường chạy ------------------------------------------------------


def test_khong_co_duong_nao_thi_bo_qua_tang_chu_khong_vo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_clip, "_load_onnx", lambda: None)
    monkeypatch.setattr(local_clip, "_load_torch", lambda: None)

    assert local_clip.classify_image_local(_anh_bytes(), _NHOM) is None


def test_khong_co_onnx_thi_lui_ve_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_clip, "_diem_onnx", lambda *a, **k: None)
    monkeypatch.setattr(local_clip, "_diem_torch", lambda *a, **k: {"recyclable": 0.9, "hazardous": 0.1})

    ket_qua = local_clip.classify_image_local(_anh_bytes(), _NHOM)

    assert ket_qua is not None
    assert ket_qua.category_code == "recyclable"
    assert "torch" in ket_qua.model, "Phải ghi rõ đang chạy đường nào để trace đọc được"


def test_ep_dung_onnx_thi_khong_dung_toi_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    """`CLIP_RUNTIME=onnx` trên máy chủ 512 MB: lỡ có torch cũng không được nạp."""
    monkeypatch.setenv("CLIP_RUNTIME", "onnx")
    reset_settings_cache()
    monkeypatch.setattr(local_clip, "_diem_onnx", lambda *a, **k: None)

    def khong_duoc_goi(*args, **kwargs):
        raise AssertionError("CLIP_RUNTIME=onnx mà vẫn chạm vào đường torch")

    monkeypatch.setattr(local_clip, "_diem_torch", khong_duoc_goi)

    assert local_clip.classify_image_local(_anh_bytes(), _NHOM) is None


def test_tat_model_local_thi_khong_nap_gi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_MODEL_ENABLED", "false")
    reset_settings_cache()

    assert local_clip.classify_image_local(_anh_bytes(), _NHOM) is None
    assert local_clip.warm_up() is False


def test_nhom_nguy_hai_diem_cao_thi_danh_dau_nghi_ngo(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLAUDE.md mục 5: model local không bao giờ được tự chốt nhóm nguy hại."""
    monkeypatch.setattr(local_clip, "_diem_onnx", lambda *a, **k: {"recyclable": 0.6, "hazardous": 0.4})

    ket_qua = local_clip.classify_image_local(_anh_bytes(), _NHOM)

    assert ket_qua is not None
    assert ket_qua.suspect_hazardous is True


# --- Lấy bộ model về từ GitHub Release -----------------------------------


def test_link_khong_phai_trang_release_thi_giu_nguyen() -> None:
    url = "https://example.com/clip-assets.tar.gz"

    assert local_clip._giai_url_trang_release(url) == url


def test_dan_nham_link_trang_release_thi_tu_tim_ra_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nút copy của GitHub cho ra link TRANG, không phải link FILE.

    Đã vấp thật khi cấu hình Render. Tải link trang về thì được một trang HTML,
    giải nén hỏng, tầng T0.5 tắt mà không ai hiểu vì sao.
    """
    import httpx

    class _PhanHoiGia:
        def raise_for_status(self):
            return self

        def json(self):
            return {
                "assets": [
                    {"name": "ghi-chu.txt", "browser_download_url": "https://x/ghi-chu.txt"},
                    {"name": "clip-assets.tar.gz", "browser_download_url": "https://x/clip-assets.tar.gz"},
                ]
            }

    class _ClientGia:
        def __init__(self, *args, **kwargs) -> None:
            self.duong_dan = ""

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def get(self, url: str):
            self.duong_dan = url
            _ClientGia.da_goi = url
            return _PhanHoiGia()

    monkeypatch.setattr(httpx, "Client", _ClientGia)

    ra = local_clip._giai_url_trang_release("https://github.com/imninh/Test_GBAI/releases/tag/First")

    assert ra == "https://x/clip-assets.tar.gz"
    assert _ClientGia.da_goi == "https://api.github.com/repos/imninh/Test_GBAI/releases/tags/First"


def test_tra_ve_trang_web_thay_vi_file_thi_bo_qua_gon(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    """Không được để lỗi giải nén khó hiểu thay cho một câu nói rõ chuyện gì."""
    import httpx

    class _PhanHoiGia:
        content = b"<!DOCTYPE html><html>trang release</html>"

        def raise_for_status(self):
            return self

    class _ClientGia:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def get(self, url: str):
            return _PhanHoiGia()

    monkeypatch.setenv("CLIP_ASSETS_URL", "https://example.com/khong-phai-file")
    reset_settings_cache()
    monkeypatch.setattr(httpx, "Client", _ClientGia)

    with caplog.at_level("WARNING"):
        local_clip._tai_asset_neu_thieu(tmp_path / "clip")

    assert not (tmp_path / "clip" / local_clip.ONNX_MODEL_FILE).exists()
    assert "releases/download" in caplog.text, "Cảnh báo phải chỉ ra dạng link đúng"


# --- Hợp đồng giữa script xuất và runtime --------------------------------


def test_script_xuat_dung_bo_cau_mo_ta_y_het_runtime() -> None:
    """Hai bên lệch nhau thì mã băm không khớp và tầng T0.5 tự tắt lúc chạy.

    Test này bắt việc đó ngay ở CI thay vì để lộ ra trên bản deploy.
    """
    from scripts.export_clip_onnx import _danh_sach_prompt
    from src.db.seed_data import WASTE_CATEGORIES

    prompts_script, owner_script = _danh_sach_prompt()

    nhom = [
        CategoryOption(
            code=row["code"],
            name=row["name"],
            is_hazardous=row["is_hazardous"],
            hint=row.get("clip_prompts") or "",
        )
        for row in sorted(WASTE_CATEGORIES, key=lambda r: r["sort_order"])
    ]
    prompts_runtime: list[str] = []
    owner_runtime: list[str] = []
    for category in nhom:
        for prompt in local_clip._prompts_for(category):
            prompts_runtime.append(prompt)
            owner_runtime.append(category.code)

    assert prompts_script == prompts_runtime
    assert owner_script == owner_runtime
