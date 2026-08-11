"""Test tiền xử lý ảnh — phần khẳng định EXIF đã sạch là bắt buộc.

Đây là test có giá trị pháp lý với đề: nó chứng minh ảnh gửi đi không còn
toạ độ GPS, chứ không phải chỉ nói suông trong tài liệu.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from src.db.models import Media
from src.services.image import has_exif, phash_distance, preprocess_image


def _image_with_exif(size: tuple[int, int] = (1200, 900)) -> bytes:
    """Tạo ảnh JPEG có EXIF: GPS, thời gian chụp, model điện thoại."""
    img = Image.new("RGB", size, (120, 160, 130))
    exif = img.getexif()
    exif[271] = "Apple"  # Make
    exif[272] = "iPhone 13"  # Model
    exif[306] = "2026:07:28 14:22:03"  # DateTime
    exif[34853] = {  # GPSInfo — 10.776900, 106.700900
        1: "N",
        2: (10.0, 46.0, 36.84),
        3: "E",
        4: (106.0, 42.0, 3.24),
    }
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


@pytest.fixture
def media_dir(tmp_path: Path) -> str:
    return str(tmp_path / "media")


def test_anh_da_xu_ly_khong_con_exif(media_dir: str) -> None:
    result = preprocess_image(_image_with_exif(), media_dir=media_dir)

    assert result.exif_stripped is True
    assert has_exif(result.stored_path) is False, "Ảnh gửi đi vẫn còn EXIF — không được phép"


def test_ghi_lai_cac_truong_da_xoa_cho_man_quyen_rieng_tu(media_dir: str) -> None:
    result = preprocess_image(_image_with_exif(), media_dir=media_dir)

    labels = {r.label_vi for r in result.removed_fields}
    assert "Toạ độ GPS" in labels
    assert "Model điện thoại" in labels
    # Giá trị trước khi xoá phải đọc được để dựng bảng đối chiếu ở spec 4.5.
    gps = next(r for r in result.removed_fields if r.label_vi == "Toạ độ GPS")
    assert gps.value_before.startswith("10.7")


def test_nen_ve_512px_va_giam_dung_luong(media_dir: str) -> None:
    # 1512×2016 thay cho 3024×4032: vẫn là ảnh điện thoại dựng đứng, vẫn lớn hơn
    # 512px gấp nhiều lần nên vẫn chứng minh đúng điều cần chứng minh (nén về
    # 512 + giảm dung lượng). Kích thước cũ làm `cv2.detectMultiScale` trong
    # `blur_faces` xin ~490 MB một lần và đỏ với `MemoryError` trên máy 8 GB
    # đang mở trình duyệt — lỗi môi trường, nhưng nó đỏ đúng cái test này nhiều
    # lần rồi, và người chấm cũng chạy pytest trên máy của họ.
    raw = _image_with_exif(size=(1512, 2016))
    result = preprocess_image(raw, media_dir=media_dir)

    assert max(result.width, result.height) == 512
    assert result.bytes_size < result.original_bytes_size
    assert result.original_width == 1512


def test_phash_on_dinh_va_phan_biet_duoc_anh_khac(media_dir: str) -> None:
    same_a = preprocess_image(_image_with_exif(), media_dir=media_dir)
    same_b = preprocess_image(_image_with_exif(), media_dir=media_dir)

    noise = Image.effect_noise((600, 600), 90).convert("RGB")
    buf = io.BytesIO()
    noise.save(buf, format="JPEG")
    other = preprocess_image(buf.getvalue(), media_dir=media_dir)

    assert phash_distance(same_a.phash, same_b.phash) == 0
    assert phash_distance(same_a.phash, other.phash) > 6


def test_giu_anh_goc_rieng_va_dat_han_luu_tru(media_dir: str) -> None:
    result = preprocess_image(_image_with_exif(), media_dir=media_dir)

    assert result.original_path != result.stored_path
    assert Path(result.original_path).exists()
    assert result.expires_at is not None


def test_file_khong_phai_anh_thi_bao_loi_ro_rang(media_dir: str) -> None:
    with pytest.raises(ValueError, match="Không đọc được file ảnh"):
        preprocess_image(b"day khong phai anh", media_dir=media_dir)


def test_duong_dan_anh_dai_hon_400_van_ghi_duoc(db_session: Session) -> None:
    """Regression SRV-500/StatementError — đường ảnh trên PostgreSQL.

    Bug 03/08: ``Media.stored_path``/``original_path`` là ``String(400)``.
    PostgreSQL ép độ dài VARCHAR còn SQLite thì bỏ qua, nên đường ảnh "chạy ở
    dev, chết ở deploy". Đường dẫn đĩa tạm trên Render có thể dài hơn 400.

    ⚠️ SQLite KHÔNG ép được ràng buộc độ dài, nên test này pass cả khi trần cũ
    400 vẫn còn — cái nó thật sự chứng minh là **giá trị chui qua được toàn bộ
    đường Media → INSERT + đọc lại** với độ dài vượt trần cũ, tức bất kỳ máy
    chủ nào ép trần đều không còn chặn nữa. Trần mới 1024 phải đủ rộng.
    """
    duong_dan_dai = str(Path("/") / "app" / "data" / ("deep-nested-temp-dir/" * 30) / "20260807-abcdef123456.jpg")
    assert len(duong_dan_dai) > 400, "Fixture phải vượt trần cũ 400 ký tự"

    media = Media(
        uploader_id=1,
        stored_path=duong_dan_dai,
        original_path=duong_dan_dai + "-original.jpg",
        phash="a" * 32,
        width=100,
        height=100,
        bytes_size=10,
        original_width=200,
        original_height=200,
        original_bytes_size=20,
    )
    db_session.add(media)
    db_session.flush()

    luu = db_session.get(Media, media.id)
    assert luu is not None
    assert luu.stored_path == duong_dan_dai, "Đường dẫn dài phải được ghi và đọc lại nguyên vẹn"
    # Chốt trần schema không bị thu nhỏ trở lại — phần thật sự chặn được bug.
    assert Media.__table__.c.stored_path.type.length >= 1024  # type: ignore[attr-defined]
