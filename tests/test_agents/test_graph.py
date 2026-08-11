"""Test graph agent: đi đúng nhánh và mọi node đều để lại số liệu."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from src.agents.graph import GRAPH_SHAPE, agent
from src.services import classifier
from tests.conftest import FakeVisionClient, make_result


@pytest.fixture(autouse=True)
def _tat_model_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(classifier, "classify_image_local", lambda *a, **k: None)


@pytest.fixture
def _khong_goi_llm_khi_tu_van(monkeypatch: pytest.MonkeyPatch) -> None:
    """Node advise lui về hướng dẫn chuẩn thay vì gọi model thật."""
    from src.services.vision import VisionUnavailableError

    monkeypatch.setattr(
        "src.services.vision.get_vision_client",
        lambda tier="t1": (_ for _ in ()).throw(VisionUnavailableError("test khong goi model")),
    )


def _dung_model_gia(monkeypatch: pytest.MonkeyPatch, *results) -> FakeVisionClient:
    fake = FakeVisionClient(results=list(results))
    models = {"t1": "model-t1", "t2": "model-t2", "text": "model-text"}
    monkeypatch.setattr(classifier, "get_vision_client", lambda tier="t1": fake)
    monkeypatch.setattr(classifier, "get_tier_model", lambda tier="t1": models[tier])
    monkeypatch.setattr(classifier, "get_tier_provider", lambda tier="t1": "fake")
    return fake


def test_tra_loi_duoc_thi_di_qua_advise(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, _khong_goi_llm_khi_tu_van
) -> None:
    _dung_model_gia(monkeypatch, make_result(confidence=0.91))

    state = agent.invoke(
        {"session": db_session, "image_bytes": b"anh", "image_phash": "1234123412341234", "building_id": None}
    )

    tram = {n.node: n.status for n in state["nodes"]}
    assert tram["advise"] in {"ok", "degraded"}
    assert tram["schedule_pickup"] == "skipped"
    assert state["outcome"].refused is False


def test_tu_choi_tra_loi_thi_bo_qua_advise(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Từ chối rồi mà vẫn đi tra quy định là vừa tốn tiền vừa sai thông điệp."""
    _dung_model_gia(monkeypatch)  # không nạp kết quả — bị chặn cứng trước khi gọi model

    state = agent.invoke({"session": db_session, "text_query": "mình có kim tiêm cũ", "building_id": None})

    tram = {n.node: n.status for n in state["nodes"]}
    assert state["outcome"].refused is True
    assert tram["advise"] == "skipped"
    assert all(n.llm_calls == 0 for n in state["nodes"])


def test_do_cong_kenh_thi_chay_tiep_node_goi_y_lich(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, _khong_goi_llm_khi_tu_van
) -> None:
    _dung_model_gia(monkeypatch, make_result(item_name="Tủ gỗ cũ", category_code="bulky", confidence=0.88))

    state = agent.invoke(
        {"session": db_session, "image_bytes": b"anh", "image_phash": "5678567856785678", "building_id": None}
    )

    tram = {n.node: n.status for n in state["nodes"]}
    assert tram["schedule_pickup"] == "ok"
    assert state["schedule_hint"]["la_do_cong_kenh"] is True


def test_moi_node_deu_de_lai_ban_ghi_de_dung_man_trace(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, _khong_goi_llm_khi_tu_van
) -> None:
    _dung_model_gia(monkeypatch, make_result(confidence=0.91))

    state = agent.invoke(
        {"session": db_session, "image_bytes": b"anh", "image_phash": "9012901290129012", "building_id": None}
    )

    ten_node = [n.node for n in state["nodes"]]
    assert ten_node.count("classify_waste") == 1
    assert {
        "safety_precheck",
        "cache_lookup",
        "classify_waste",
        "safety_check",
        "advise",
        "schedule_pickup",
    } <= set(ten_node)


def test_so_do_graph_khai_bao_khop_voi_graph_that() -> None:
    ten_node = {n["id"] for n in GRAPH_SHAPE["nodes"]}
    assert ten_node == {"classify_waste", "advise", "skip_advise", "schedule_pickup", "skip_schedule"}
    for canh in GRAPH_SHAPE["edges"]:
        assert canh["from"] in ten_node and canh["to"] in ten_node
