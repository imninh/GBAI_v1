"""Tầng T0.5b — YOLO giơ cờ đồ điện tử (gói P33).

Không test nào chạm mạng, không test nào cần file model thật — `phat_hien` bị
thay bằng giả lập, đúng khuôn `test_clip_remote.py`. Trọng tâm:

* cờ tắt / không có ảnh → **0 lệnh gọi model**;
* YOLO chỉ GIƠ CỜ, không bao giờ chốt nhãn;
* cờ đó phải sống tới `should_escalate_to_t2` — đây là sợi dây từng bị đứt.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.config import get_settings, reset_settings_cache
from src.services import classifier_helpers, safety
from src.services.classifier_stages import chay_t05_yolo, chay_t1_t2
from src.services.classifier_types import ClassifyOutcome
from src.services.vision import Usage, VisionResult, local_yolo

GOC_DU_AN = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _don_trang_thai(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cấu hình đọc qua ``lru_cache`` nên phải xoá cache quanh mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


def _bat_yolo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOLO_ENABLED", "true")
    reset_settings_cache()


def test_tat_co_thi_khong_goi_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """`yolo_enabled=False` → trả `False`, không gọi model, không thêm NodeMetric nào."""
    dem = [0]

    def _phat_hien(anh: bytes) -> list[dict]:
        dem[0] += 1
        return [{"lop": "cell phone", "diem": 0.9}]

    monkeypatch.setattr(local_yolo, "phat_hien", _phat_hien)
    outcome = ClassifyOutcome(prompt_version=get_settings().prompt_version)

    assert chay_t05_yolo(outcome, image_bytes=b"anh") is False
    assert dem[0] == 0, "Cờ tắt thì không được gọi model một lần nào"
    assert outcome.nodes == [], "Cờ tắt thì không được thêm NodeMetric nào"


def test_khong_co_anh_thi_khong_goi_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_yolo(monkeypatch)
    dem = [0]

    def _phat_hien(anh: bytes) -> list[dict]:
        dem[0] += 1
        return []

    monkeypatch.setattr(local_yolo, "phat_hien", _phat_hien)
    outcome = ClassifyOutcome(prompt_version=get_settings().prompt_version)

    assert chay_t05_yolo(outcome, image_bytes=None) is False
    assert dem[0] == 0, "Hỏi bằng chữ (không có ảnh) thì không được gọi model"


def test_phat_hien_dien_thoai_thi_gio_co(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_yolo(monkeypatch)
    monkeypatch.setattr(local_yolo, "phat_hien", lambda anh: [{"lop": "cell phone", "diem": 0.9}])
    outcome = ClassifyOutcome(prompt_version=get_settings().prompt_version)

    assert chay_t05_yolo(outcome, image_bytes=b"anh") is True
    node = outcome.nodes[0]
    assert node.node == "local_yolo"
    assert node.meta["nghi_do_dien_tu"] is True
    assert node.meta["cac_lop_phat_hien"] == ["cell phone"]


def test_vat_thuong_thi_khong_gio_co(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_yolo(monkeypatch)
    monkeypatch.setattr(local_yolo, "phat_hien", lambda anh: [{"lop": "chair", "diem": 0.95}])
    outcome = ClassifyOutcome(prompt_version=get_settings().prompt_version)

    assert chay_t05_yolo(outcome, image_bytes=b"anh") is False
    assert outcome.nodes[0].meta["nghi_do_dien_tu"] is False


def test_duoi_nguong_thi_bo_qua(monkeypatch: pytest.MonkeyPatch) -> None:
    """Điểm dưới `yolo_confidence` thì không tính — kể cả khi nó là đồ điện tử."""
    _bat_yolo(monkeypatch)
    # `phat_hien` giả lập trả thẳng một phát hiện DƯỚI ngưỡng (như thể nó lơ là
    # lọc) — cờ phải tự loại nó đi, không tin mù đầu vào.
    monkeypatch.setattr(local_yolo, "phat_hien", lambda anh: [{"lop": "cell phone", "diem": 0.2}])
    outcome = ClassifyOutcome(prompt_version=get_settings().prompt_version)

    assert chay_t05_yolo(outcome, image_bytes=b"anh") is False


def test_model_hong_thi_khong_no(monkeypatch: pytest.MonkeyPatch) -> None:
    """`phat_hien` ném ngoại lệ → trả `False`, không ngoại lệ nào thoát ra."""
    _bat_yolo(monkeypatch)

    def _phat_hien_hong(anh: bytes) -> list[dict]:
        raise RuntimeError("model vỡ giữa chừng")

    monkeypatch.setattr(local_yolo, "phat_hien", _phat_hien_hong)
    outcome = ClassifyOutcome(prompt_version=get_settings().prompt_version)

    assert chay_t05_yolo(outcome, image_bytes=b"anh") is False
    assert outcome.nodes[0].meta["nghi_do_dien_tu"] is False


def test_co_gio_thi_ep_leo_t2(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chốt chặn chính: cờ YOLO phải ép leo T2 dù T1 mù.

    Giả lập T1 MÙ đồ điện tử: `suspect_hazardous=False`, confidence cao, items
    đầy đủ — tự nó KHÔNG leo T2 (kiểm chứng ở dòng đầu). Cờ
    `nghi_nguy_hai_local=True` từ T0.5 phải được `chay_t1_t2` OR vào
    `should_escalate_to_t2` để chuỗi lý do khác rỗng và T2 được hỏi. Đây chính
    là sợi dây từng bị đứt mà gói P33 vá.
    """
    khong_leo = safety.should_escalate_to_t2(
        0.91,
        0.6,
        False,  # T1 mù — tự nó không nghi gì
        "",
        items=[{"name": "chai nhựa", "category_code": "recyclable_plastic", "confidence": 0.9}],
        co_anh=True,
    )
    assert khong_leo == "", "T1 mù + confidence cao + có items thì không được tự leo T2"

    class _KhachGia:
        def __init__(self) -> None:
            self.so_lan = 0

        def classify_image(self, image_bytes, categories, model):
            self.so_lan += 1
            return VisionResult(
                item_name="chai nhựa",
                category_code="recyclable_plastic",
                confidence=0.91,
                suspect_hazardous=False,
                items=[{"name": "chai nhựa", "category_code": "recyclable_plastic", "confidence": 0.91}],
                usage=Usage(cost_usd=0.001, price_known=True),
            )

        def classify_text(self, text, categories, model):
            return self.classify_image(b"", categories, model)

    khach = _KhachGia()
    outcome = ClassifyOutcome(prompt_version=get_settings().prompt_version)
    categories = classifier_helpers.load_category_options(db_session)

    chay_t1_t2(
        db_session,
        outcome,
        image_bytes=b"anh",
        text_query="",
        categories=categories,
        started=time.perf_counter(),
        get_vision_client=lambda tier="t1": khach,
        get_tier_model=lambda tier="t1": f"model-{tier}",
        get_tier_provider=lambda tier="t1": f"provider-{tier}",
        nghi_nguy_hai_local=True,
    )

    assert outcome.escalation_reason != "", "Cờ YOLO phải ép ra chuỗi lý do leo T2"
    assert khach.so_lan == 2, "T2 phải được hỏi thêm đúng một lần (T1 1 lần + T2 1 lần)"


def test_yolo_khong_bao_gio_chot_nhan() -> None:
    """`local_yolo.py` không được chứa chuỗi `VisionResult`.

    YOLO trong sản phẩm này là một CẢM BIẾN CẢNH BÁO, không phải tầng phân loại.
    Viết hàm trả `VisionResult` là mời người sau cắm nó vào đường chốt nhãn —
    đúng thứ luật `local_never_decides_hazardous` cấm.
    """
    noi_dung = (GOC_DU_AN / "src" / "services" / "vision" / "local_yolo.py").read_text(encoding="utf-8")
    assert "VisionResult" not in noi_dung, "local_yolo.py không được nhắc tới VisionResult"


def test_bang_anh_xa_khong_chua_lop_mo_ho() -> None:
    """`MAP_COCO_RAC` không chứa `bottle`/`cup`.

    Một hộp COCO gắn nhãn `bottle` chỉ nói HÌNH DẠNG cái chai, không nói chất
    liệu — danh mục có CẢ `recyclable_plastic` lẫn `recyclable_glass`, gắn thẳng
    sang nhựa là bịa số và sai với mọi chai thuỷ tinh. Lớp mơ hồ để CLIP/T1 phân
    xử vì chúng nhìn được chất liệu, YOLO thì không.
    """
    assert "bottle" not in local_yolo.MAP_COCO_RAC, "bottle có thể là chai thuỷ tinh — không gắn cứng sang nhựa"
    assert "cup" not in local_yolo.MAP_COCO_RAC, "cup có thể là cốc giấy/nhựa/thuỷ tinh — không gắn cứng"
