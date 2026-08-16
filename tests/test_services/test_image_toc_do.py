"""Gói P37 — tốc độ và đúng chỗ của việc làm mờ khuôn mặt.

Trước gói này ``blur_faces`` dò Haar trên ảnh CÒN NGUYÊN (4000×3000 mất ~3,3 s).
Nay dò trên một bản thu nhỏ riêng (cạnh dài ``CANH_DO_MAT = 1024``) rồi **nhân
toạ độ ngược lên** và làm mờ trên ảnh đầy đủ — vừa nhanh vừa không bỏ sót mặt
nhỏ. Cách làm hiển nhiên (thu nhỏ ảnh thật rồi mới dò) là SAI: nó làm mọi mặt
cao dưới ~219px của ảnh gốc thành dưới ``minSize=(28, 28)`` của Haar và để lọt
mặt người mà không một cảnh báo nào.

Không test nào chạm mạng. Mọi test trừ test 7 dùng cascade GIẢ (monkeypatch
``_get_face_cascade``) để kiểm toán toạ độ một cách xác định; test 7 dùng
cascade thật để đo tốc độ.
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.services import image as image_module
from src.services.image import blur_faces, preprocess_image


def _anh_mau(rong: int, cao: int, nen: tuple[int, int, int] = (200, 200, 200)) -> Image.Image:
    return Image.new("RGB", (rong, cao), nen)


def _dap_noise(anh: Image.Image, x: int, y: int, w: int, h: int, seed: int = 7) -> Image.Image:
    """Đắp một mảng nhiễu lên vùng (x, y, w, h) để vết mờ dò được bằng điểm ảnh."""
    phan = np.array(anh)
    rng = np.random.default_rng(seed)
    phan[y : y + h, x : x + w] = rng.integers(0, 255, size=(h, w, 3), dtype=np.uint8)
    return Image.fromarray(phan)


def _byte_anh(anh: Image.Image) -> bytes:
    buf = io.BytesIO()
    anh.save(buf, format="JPEG")
    return buf.getvalue()


class _FakeCascade:
    """Cascade giả: trả về đúng danh sách hộp, ghi lại kích thước ảnh nhận vào."""

    def __init__(self, boxes: list[tuple[int, int, int, int]], nhan: dict | None = None) -> None:
        self.boxes = boxes
        self.nhan = nhan

    # Tên hàm và tham số phải giống hệt API thật của cv2, vì blur_faces gọi với
    # keyword `scaleFactor=...`/`minNeighbors=...`/`minSize=...`.
    def detectMultiScale(self, gray, scaleFactor=1.1, minNeighbors=5, minSize=(28, 28)):  # noqa: N802, N803
        if self.nhan is not None:
            self.nhan["shape"] = gray.shape
        return list(self.boxes)


@pytest.fixture
def cascade_rong(monkeypatch) -> dict:
    """Gắn cascade GIẢ trả về hộp rỗng — không chạm Haar thật."""
    fake = _FakeCascade([])
    monkeypatch.setattr(image_module, "_get_face_cascade", lambda: fake)
    return {"fake": fake}


def _so_sanh_diem_truoc_sau(truoc: Image.Image, sau: Image.Image, toa_do: list[tuple[int, int]]) -> list[bool]:
    """Mỗi toạ độ: pixel đổi sau blur hay không."""
    a = np.array(truoc)
    b = np.array(sau)
    return [not np.array_equal(a[y, x], b[y, x]) for x, y in toa_do]


def test_anh_nho_khong_bi_thu_nho_de_do(monkeypatch) -> None:
    """Ảnh 800×600 (≤ CANH_DO_MAT) → tỉ lệ dò bằng 1, hộp dùng nguyên toạ độ."""
    nhan: dict = {}
    fake = _FakeCascade([(100, 100, 50, 50)], nhan=nhan)
    monkeypatch.setattr(image_module, "_get_face_cascade", lambda: fake)

    truoc = _dap_noise(_anh_mau(800, 600), 100, 100, 50, 50)
    sau, so_mat = blur_faces(truoc)

    assert so_mat == 1
    # Không thu nhỏ: ảnh đưa vào detectMultiScale đúng cỡ gốc (H, W).
    assert nhan["shape"] == (600, 800), f"Ảnh 800×600 phải dò ở cỡ gốc, gặp {nhan['shape']}"
    # Hộp mờ nằm đúng toạ độ gốc — không bị nhân ngược làm lệch.
    trong = _so_sanh_diem_truoc_sau(truoc, sau, [(120, 120), (130, 140)])
    ngoai = _so_sanh_diem_truoc_sau(truoc, sau, [(400, 300), (50, 50)])
    assert all(trong) and not any(ngoai)


def test_toa_do_duoc_nhan_nguoc_dung(monkeypatch) -> None:
    """Chốt chặn chính: hộp do cascade báo trên BẢN THU NHỎ phải rơi đúng chỗ trên ẢNH GỐC.

    Dùng ảnh DỌC 3000×4000 — chỗ ảnh dọc hay lộ lỗi nhân ngược nhất. Mặt giả nằm
    ở (1500, 2000) cỡ 200px trong ảnh gốc; trên bản 768×1024 nó thành (384, 512, 51, 51).
    """
    fake = _FakeCascade([(384, 512, 51, 51)])
    monkeypatch.setattr(image_module, "_get_face_cascade", lambda: fake)

    truoc = _dap_noise(_anh_mau(3000, 4000), 1500, 2000, 200, 200)
    sau, so_mat = blur_faces(truoc)

    assert so_mat == 1
    # Trong hộp (toạ độ gốc) → đổi; ngoài hộp xa → không đổi một điểm ảnh nào.
    trong = _so_sanh_diem_truoc_sau(truoc, sau, [(1600, 2100), (1550, 2050), (1690, 2190)])
    ngoai = _so_sanh_diem_truoc_sau(truoc, sau, [(100, 100), (2900, 3900), (1500, 500)])
    assert all(trong), "Vùng mặt (toạ độ gốc) phải bị làm mờ"
    assert not any(ngoai), "Điểm ngoài hộp không được đổi dù một pixel"


def test_khong_bo_sot_mat_nho(monkeypatch) -> None:
    """Mặt cao 60px trong ảnh GỐC 4000×3000 vẫn bị làm mờ.

    Đây là ca mà cách làm hiển nhiên — thu nhỏ ảnh thật về 512 rồi dò — bỏ sót:
    60px × 0,128 = 7,68px < minSize 28 (bảng ở CONTEXT gói P37). Bản dò ở 1024
    (tỉ lệ 0,256) giữ mặt 60px thành ~15px trên bản dò, nhân ngược về ~60px.
    """
    fake = _FakeCascade([(256, 256, 15, 15)])
    monkeypatch.setattr(image_module, "_get_face_cascade", lambda: fake)

    truoc = _dap_noise(_anh_mau(4000, 3000), 1000, 1000, 60, 60)
    sau, so_mat = blur_faces(truoc)

    assert so_mat == 1
    trong = _so_sanh_diem_truoc_sau(truoc, sau, [(1020, 1020), (1040, 1040)])
    ngoai = _so_sanh_diem_truoc_sau(truoc, sau, [(200, 200), (3900, 2900)])
    assert all(trong) and not any(ngoai)


def test_khong_co_cascade_thi_tra_nguyen(monkeypatch) -> None:
    """Cascade không nạp được (None) → ảnh nguyên vẹn, 0 mặt, không ngoại lệ."""
    monkeypatch.setattr(image_module, "_get_face_cascade", lambda: None)

    truoc = _dap_noise(_anh_mau(800, 600), 100, 100, 50, 50)
    sau, so_mat = blur_faces(truoc)

    assert so_mat == 0
    assert sau is truoc, "Không có cascade thì phải trả về nguyên đối tượng ảnh"


def test_khong_co_mat_thi_tra_nguyen(monkeypatch) -> None:
    """Cascade giả trả danh sách rỗng → ảnh không đổi một điểm ảnh nào."""
    fake = _FakeCascade([])
    monkeypatch.setattr(image_module, "_get_face_cascade", lambda: fake)

    truoc = _dap_noise(_anh_mau(800, 600), 100, 100, 50, 50)
    sau, so_mat = blur_faces(truoc)

    assert so_mat == 0
    assert np.array_equal(np.array(truoc), np.array(sau)), "Không có mặt thì ảnh phải y nguyên"


def test_preprocess_giu_nguyen_hop_dong(monkeypatch, tmp_path: Path) -> None:
    """``preprocess_image`` vẫn trả đủ trường cũ của ``ProcessedImage``, ảnh ra vẫn 512px."""
    fake = _FakeCascade([])
    monkeypatch.setattr(image_module, "_get_face_cascade", lambda: fake)

    media_dir = str(tmp_path / "media")
    result = preprocess_image(_byte_anh(_anh_mau(1200, 900)), media_dir=media_dir, keep_original=False)

    # Toàn bộ trường của hợp đồng cũ phải còn.
    assert result.stored_path and Path(result.stored_path).exists()
    assert result.original_path == ""
    assert isinstance(result.phash, str) and result.phash
    assert result.width > 0 and result.height > 0
    assert result.bytes_size > 0
    assert result.original_width == 1200 and result.original_height == 900
    assert result.original_bytes_size > 0
    assert result.exif_stripped is True
    assert result.faces_blurred == 0
    assert result.removed_fields == []
    assert result.expires_at is not None
    # Ảnh lưu ra vẫn nén đúng cạnh dài của cấu hình.
    assert max(result.width, result.height) == 512


def test_nhanh_hon_dang_ke() -> None:
    """``blur_faces`` trên ảnh 4000×3000 phải dưới 1,0 giây.

    Ngưỡng RỘNG có chủ đích: máy CI chậm hơn máy dev, mục đích là bắt hồi quy
    bậc-độ-lớn (bản cũ ~3,3 s vì dò Haar trên ảnh nguyên vẹn) chứ không phải đo
    hiệu năng chính xác. Đo giá ỔN ĐỊNH: lần gọi đầu tiên của ``detectMultiScale``
    còn nạp nội bộ cascade (~vài giây, chỉ một lần mỗi tiến trình), nên làm nóng
    trước rồi mới bấm giờ — đúng chi phí mỗi ảnh trong vận hành thật.
    """
    blur_faces(_anh_mau(64, 64))  # làm nóng cascade + cv2

    anh_lon = _anh_mau(4000, 3000)
    bat_dau = time.perf_counter()
    blur_faces(anh_lon)
    do_tre = time.perf_counter() - bat_dau

    assert do_tre < 1.0, f"blur_faces mất {do_tre:.2f}s trên ảnh 4000x3000 — hồi quy bậc lớn"
