"""Chỉ báo YOLO trên trang Vận hành — ``yolo_loaded`` / ``yolo_enabled`` (gói P48).

YOLO nạp lazy (chỉ khi phân loại ảnh đầu), nên "không thấy" YOLO hoạt động một
phần vì thiếu chỉ báo. ``/ops/metrics`` là endpoint **chỉ đọc** — nó KHÔNG được
kích hoạt việc tải model (metrics.py đã ghi rõ cho CLIP). Các test ở đây khoá
đúng ràng buộc đó: gọi ``is_loaded()`` không được đổi trạng thái module.
"""

from __future__ import annotations

from src.services.metrics import ops_metrics
from src.services.vision import local_yolo, yolo_loaded


def test_is_loaded_khong_tai() -> None:
    """``is_loaded()`` chỉ đọc ``_session`` — không kích hoạt tải model.

    Trước khi gọi phiên là ``None``; gọi xong vẫn ``None`` — tức hàm không có tác
    dụng phụ, không dựng InferenceSession (~10 MB).
    """
    local_yolo._session = None
    assert local_yolo._session is None
    assert local_yolo.is_loaded() is False
    assert local_yolo._session is None, "is_loaded() không được nạp phiên (chỉ đọc)"


def test_vision_xuat_yolo_loaded() -> None:
    """``__init__.py`` xuất công khai ``yolo_loaded`` (alias của ``is_loaded``)."""
    assert callable(yolo_loaded)
    assert isinstance(yolo_loaded(), bool)


def test_metrics_co_khoa_yolo(db_session) -> None:
    """``ops_metrics`` trả cả hai khoá YOLO trong khối ``provider``."""
    du_lieu = ops_metrics(db_session)
    provider = du_lieu["provider"]

    assert "yolo_loaded" in provider
    assert "yolo_enabled" in provider
    assert isinstance(provider["yolo_enabled"], bool)
    assert isinstance(provider["yolo_loaded"], bool)
