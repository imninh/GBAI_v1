"""Hướng A — cắt từng vật rồi CLIP chấm từng crop (gói P50).

Không test nào chạm mạng hay model thật: ``phat_hien_co_hop`` và
``classify_image_local`` đều bị thay bằng giả lập. Trọng tâm:

* nhiều vật khác lớp → trả đủ số món, đúng thứ tự điểm;
* 7 chai cùng lớp → gộp còn 1 món ``so_luong=7``;
* 1 vật → ``None`` để đường cũ chạy;
* đồ điện tử (keyboard) → ``None`` cho cả ảnh;
* CLIP dưới ngưỡng → vật đó bị loại khỏi danh sách;
* hộp YOLO quy về toạ độ ảnh gốc đúng (không cần model).
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from PIL import Image

from src.config import reset_settings_cache
from src.services.phan_loai_nhieu_vat import cat_va_cham_tung_vat
from src.services.vision import CategoryOption, VisionResult, local_yolo

CATEGORIES = [
    CategoryOption(code="recyclable_plastic", name="Nhựa tái chế", is_hazardous=False),
    CategoryOption(code="recyclable_paper", name="Giấy", is_hazardous=False),
    CategoryOption(code="hazardous", name="Nguy hại", is_hazardous=True),
]


@pytest.fixture(autouse=True)
def _don_trang_thai(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cấu hình đọc qua ``lru_cache`` nên phải xoá cache quanh mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


def _anh(rong: int = 800, cao: int = 600, mau: str = "white") -> bytes:
    """Một ảnh JPEG giả trong bộ nhớ — không đụng đĩa."""
    tam = io.BytesIO()
    Image.new("RGB", (rong, cao), mau).save(tam, format="JPEG")
    return tam.getvalue()


def _clip_gia(theo_thu_tu: list[VisionResult]):
    """Trả về một hàm ``classify_image_local`` giả trả kết quả theo đúng thứ tự crop.

    CLIP thật không nhận biết crop nào là crop nào bằng tham số — chỉ nhận một
    mảng pixel. Test giả lập nó bằng cách trả kết quả theo đúng thứ tự hàm được
    gọi, tức theo thứ tự điểm YOLO giảm dần.
    """
    vong_lap = iter(theo_thu_tu)
    mo = Mock()

    def _gia(anh_bytes: bytes, categories: list[CategoryOption]):
        mo(anh_bytes, categories)
        try:
            return next(vong_lap)
        except StopIteration:
            raise AssertionError("CLIP giả hết kết quả nhưng vẫn bị gọi thêm") from None

    return _gia, mo


def _hop(lop: str, diem: float, box: list[float]) -> dict:
    return {"lop": lop, "diem": diem, "box": box}


def test_ba_vat_khac_lop_tra_ba_mon_dung_thu_tu_diem(monkeypatch: pytest.MonkeyPatch) -> None:
    """3 vật khác lớp, CLIP chắc cả 3 → 3 món, sắp theo điểm YOLO giảm dần."""
    cac_hop = [
        _hop("bottle", 0.90, [10, 10, 100, 150]),
        _hop("cup", 0.80, [120, 10, 210, 150]),
        _hop("book", 0.70, [230, 10, 320, 150]),
    ]
    monkeypatch.setattr(local_yolo, "phat_hien_co_hop", lambda anh: cac_hop)
    clip, _ = _clip_gia(
        [
            VisionResult(item_name="Chai nhựa", category_code="recyclable_plastic", confidence=0.95),
            VisionResult(item_name="Cốc giấy", category_code="recyclable_paper", confidence=0.90),
            VisionResult(item_name="Sách", category_code="recyclable_paper", confidence=0.85),
        ]
    )

    ket_qua = cat_va_cham_tung_vat(_anh(), CATEGORIES, classify_image_local=clip)

    assert ket_qua is not None
    assert [m["lop_yolo"] for m in ket_qua] == ["bottle", "cup", "book"], "Đúng thứ tự điểm YOLO"
    assert [m["category_code"] for m in ket_qua] == [
        "recyclable_plastic",
        "recyclable_paper",
        "recyclable_paper",
    ]
    assert all(m["so_luong"] == 1 for m in ket_qua)


def test_bay_chai_gop_con_mot_mon_so_luong_7(monkeypatch: pytest.MonkeyPatch) -> None:
    """7 chai cùng lớp → 1 đại diện điểm cao nhất, ``so_luong=7``."""
    cac_hop = [_hop("bottle", 0.90 - i * 0.01, [10 + i * 10, 10, 60 + i * 10, 100]) for i in range(7)]
    monkeypatch.setattr(local_yolo, "phat_hien_co_hop", lambda anh: cac_hop)
    clip, _ = _clip_gia(
        [VisionResult(item_name="Chai nhựa", category_code="recyclable_plastic", confidence=0.94)]
    )

    ket_qua = cat_va_cham_tung_vat(_anh(), CATEGORIES, classify_image_local=clip)

    assert ket_qua is not None
    assert len(ket_qua) == 1, "7 chai cùng lớp phải gộp thành một món"
    assert ket_qua[0]["so_luong"] == 7
    assert ket_qua[0]["lop_yolo"] == "bottle"


def test_mot_vat_tra_none_de_duong_cu_chay(monkeypatch: pytest.MonkeyPatch) -> None:
    """1 vật → ``None`` — ca một vật không cần đường này, để CLIP toàn ảnh lo."""
    monkeypatch.setattr(local_yolo, "phat_hien_co_hop", lambda anh: [_hop("bottle", 0.90, [10, 10, 100, 150])])
    clip, _ = _clip_gia([])

    ket_qua = cat_va_cham_tung_vat(_anh(), CATEGORIES, classify_image_local=clip)

    assert ket_qua is None


def test_co_ban_phim_thi_tra_none_ca_anh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Đồ điện tử (keyboard) lẫn trong ảnh → ``None`` cả ảnh, rơi về cloud + HITL."""
    cac_hop = [
        _hop("keyboard", 0.92, [10, 10, 200, 100]),
        _hop("bottle", 0.85, [220, 10, 310, 100]),
    ]
    monkeypatch.setattr(local_yolo, "phat_hien_co_hop", lambda anh: cac_hop)
    clip, _ = _clip_gia([])

    ket_qua = cat_va_cham_tung_vat(_anh(), CATEGORIES, classify_image_local=clip)

    assert ket_qua is None, "Có đồ điện tử mà vẫn chốt nhãn local là vứt cờ an toàn"


def test_clip_duoi_nguong_thi_vat_do_bi_loai(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLIP dưới ngưỡng chấp nhận → vật đó bị bỏ khỏi danh sách, không bịa nhãn."""
    cac_hop = [
        _hop("bottle", 0.90, [10, 10, 100, 150]),
        _hop("cup", 0.80, [120, 10, 210, 150]),
    ]
    monkeypatch.setattr(local_yolo, "phat_hien_co_hop", lambda anh: cac_hop)
    clip, _ = _clip_gia(
        [
            VisionResult(item_name="Chai nhựa", category_code="recyclable_plastic", confidence=0.95),
            VisionResult(item_name="Cốc mờ quá", category_code="recyclable_paper", confidence=0.30),
        ]
    )

    ket_qua = cat_va_cham_tung_vat(_anh(), CATEGORIES, classify_image_local=clip)

    assert ket_qua is not None
    assert len(ket_qua) == 1
    assert ket_qua[0]["lop_yolo"] == "bottle", "Chỉ còn món CLIP chắc; cốc mờ bị loại"


def test_crop_nghi_nguy_hai_thi_tra_none_ca_anh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Một crop CLIP nghi nguy hại → ``None`` CẢ ảnh, đừng trả lời các món còn lại."""
    cac_hop = [
        _hop("bottle", 0.90, [10, 10, 100, 150]),
        _hop("cup", 0.80, [120, 10, 210, 150]),
    ]
    monkeypatch.setattr(local_yolo, "phat_hien_co_hop", lambda anh: cac_hop)
    clip, _ = _clip_gia(
        [
            VisionResult(item_name="Chai nhựa", category_code="recyclable_plastic", confidence=0.95),
            VisionResult(
                item_name="Lọ hoá chất",
                category_code="hazardous",
                confidence=0.91,
                suspect_hazardous=True,
            ),
        ]
    )

    ket_qua = cat_va_cham_tung_vat(_anh(), CATEGORIES, classify_image_local=clip)

    assert ket_qua is None, "Crop nguy hại mà vẫn trả lời món an toàn là câu trả lời sai"


def test_quy_doi_toa_do_anh_goc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hộp YOLO (hệ 640) quy về đúng pixel ảnh gốc.

    Ảnh 800×600: ``ti_le = 640/800 = 0.8`` → resize 640×480, dán xuống giữa nền
    640×640 → ``pad_y = (640-480)//2 = 80``, ``pad_x = 0``. Hộp giữa ảnh trong
    hệ 640 là ``[270, 270, 370, 370]`` (tâm 320, kích thước 100). Toạ độ gốc:
    ``x = (x640 - 0)/0.8``, ``y = (y640 - 80)/0.8``.
    """
    import numpy as np

    # Output thô của YOLO: 1 vật ``bottle`` ở tâm, kích thước 100×100.
    output = [np.zeros((1, 84), dtype=np.float32)]
    output[0][0, 0] = 320.0  # cx
    output[0][0, 1] = 320.0  # cy
    output[0][0, 2] = 100.0  # w
    output[0][0, 3] = 100.0  # h
    output[0][0, 4 + local_yolo.COCO_NAMES.index("bottle")] = 0.9

    session = Mock()
    session.run.return_value = output
    monkeypatch.setattr(local_yolo, "_load", lambda: session)
    monkeypatch.setenv("YOLO_ENABLED", "true")
    reset_settings_cache()

    cac_hop = local_yolo.phat_hien_co_hop(_anh(800, 600))

    assert cac_hop is not None
    x1, y1, x2, y2 = cac_hop[0]["box"]
    # Ảnh gốc 800×600: vật ở giữa ảnh → tâm (400, 300), kích thước 100/0.8=125.
    assert x1 == pytest.approx(270.0 / 0.8)
    assert y1 == pytest.approx((270.0 - 80.0) / 0.8)
    assert x2 == pytest.approx(370.0 / 0.8)
    assert y2 == pytest.approx((370.0 - 80.0) / 0.8)
    # Crop ra đúng vùng giữa ảnh gốc: cắt rồi mở lại không lỗi, kích thước khớp.
    crop = Image.open(io.BytesIO(_anh(800, 600))).crop((int(x1), int(y1), int(x2), int(y2)))
    assert crop.size == (125, 125)


def test_may_hong_thi_khong_no(monkeypatch: pytest.MonkeyPatch) -> None:
    """``phat_hien_co_hop`` ném ngoại lệ → không ngoại lệ nào thoát ra ngoài."""
    monkeypatch.setattr(
        local_yolo,
        "phat_hien_co_hop",
        lambda anh: (_ for _ in ()).throw(RuntimeError("model vỡ giữa chừng")),
    )
    clip, _ = _clip_gia([])

    ket_qua = cat_va_cham_tung_vat(_anh(), CATEGORIES, classify_image_local=clip)

    assert ket_qua is None
