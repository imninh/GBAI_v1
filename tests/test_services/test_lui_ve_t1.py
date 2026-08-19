"""Đi thẳng T2 mà T2 hỏng thì lui về T1 — đừng từ chối thẳng (gói P50e).

Khi ``route_electronics_to_t2`` bật, ``provider_first/model_first`` chính là của
T2 nên ``t2_khac_t1`` thành False và nhánh cứu T1 (vốn gắn cho ca T1 hỏng) không
bao giờ chạy — T2 hỏng là từ chối thẳng. Đây là ca thật của trace #301. T2 chết
thì thử T1 còn hơn bỏ trống: T1 mù đồ điện tử nhưng vẫn ra nhãn để người duyệt.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.config import reset_settings_cache
from src.services.classifier_stages import chay_t1_t2
from src.services.classifier_types import TIER_T1, TIER_T2, ClassifyOutcome
from src.services.vision import CategoryOption, VisionUnavailableError
from tests.conftest import make_result

TIER_MODEL = {"t1": "M_T1", "t2": "M_T2", "text": "M_TEXT"}


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    """``route_electronics_to_t2`` đọc qua ``lru_cache`` — xoá quanh mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


class _KhachLoiRoiOk:
    """Lần gọi đầu ném lỗi, các lần sau trả kết quả — đường cứu phải thử lại."""

    def __init__(self, loi: Exception, ok) -> None:
        self._loi = loi
        self._ok = ok
        self.calls: list[str] = []

    def _goi(self, model: str):
        self.calls.append(model)
        if len(self.calls) == 1:
            raise self._loi
        return self._ok

    def classify_image(self, image_bytes, categories, model):
        return self._goi(model)

    def classify_text(self, text, categories, model):
        return self._goi(model)


class _KhachLoiLuon:
    """Mọi lần gọi đều ném lỗi — cả hai tầng đều chết thì mới được từ chối."""

    def __init__(self, loi: Exception) -> None:
        self._loi = loi
        self.calls: list[str] = []

    def classify_image(self, image_bytes, categories, model):
        self.calls.append(model)
        raise self._loi

    def classify_text(self, text, categories, model):
        self.calls.append(model)
        raise self._loi


def _goi(db_session, client) -> ClassifyOutcome:
    outcome = ClassifyOutcome(prompt_version="test")
    chay_t1_t2(
        db_session,
        outcome,
        image_bytes=b"anh",
        text_query="",
        categories=[CategoryOption(code="recyclable_paper", name="Giấy", is_hazardous=False)],
        started=0.0,
        get_vision_client=lambda _tier: client,
        get_tier_model=lambda tier: TIER_MODEL[tier],
        get_tier_provider=lambda tier: f"prov_{tier}",
        nghi_nguy_hai_local=True,
    )
    return outcome


def test_t2_hong_thi_lui_t1(db_session) -> None:
    """T2 ném lỗi → thử T1 → outcome KHÔNG từ chối, tier T1, có node cứu."""
    client = _KhachLoiRoiOk(
        VisionUnavailableError("T2 chết", code="VISION-500"),
        make_result(confidence=0.91, suspect_hazardous=False),
    )

    outcome = _goi(db_session, client)

    assert client.calls == ["M_T2", "M_T1"], "T2 gọi trước, hỏng rồi mới tới T1"
    assert outcome.refused is False, "T2 hỏng mà T1 sống thì không được từ chối"
    assert outcome.tier == TIER_T1
    cac_node = [n for n in outcome.nodes if n.node == "classify_waste_t1"]
    assert cac_node, "Phải có node classify_waste_t1 ghi việc cứu"
    assert cac_node[0].status == "ok"
    assert cac_node[0].meta.get("ly_do") == "cuu_khi_t2_hong"


def test_ca_hai_hong_thi_moi_tu_choi(db_session) -> None:
    """T2 hỏng, T1 cứu cũng hỏng nốt → từ chối như cũ (MODEL_LOI)."""
    client = _KhachLoiLuon(VisionUnavailableError("mất mạng", code="VISION-500"))

    outcome = _goi(db_session, client)

    assert client.calls == ["M_T2", "M_T1"], "Phải thử T1 trước khi bỏ cuộc"
    assert outcome.refused is True
    assert "model_loi" in outcome.refusal_reason
    cac_node = [n for n in outcome.nodes if n.node == "classify_waste_t1" and n.status == "error"]
    assert cac_node, "T1 cứu thất bại phải ghi node lỗi classify_waste_t1"
    assert cac_node[0].meta.get("ly_do") == "cuu_khi_t2_hong"


def test_nhanh_loi_ghi_dung_tier_khi_di_thang_t2(db_session) -> None:
    """Nhánh lỗi của lệnh gọi ĐẦU phải ghi tier THẬT (T2 khi đi thẳng), không phải T1."""
    client = _KhachLoiLuon(VisionUnavailableError("mất mạng", code="VISION-500"))

    outcome = _goi(db_session, client)

    loi_dau = next(n for n in outcome.nodes if n.node == "classify_waste" and n.status == "error")
    assert loi_dau.meta["tier"] == TIER_T2, (
        f"Đi thẳng T2 mà meta ghi {loi_dau.meta.get('tier')} là nhãn sai — phải là {TIER_T2}"
    )
    assert loi_dau.meta["provider"] == "prov_t2"
    assert loi_dau.meta["model"] == "M_T2"
