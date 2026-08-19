"""Chặn kiểu numpy rò lên cột JSON ``classifications.items`` — sự cố 17/08/2026.

Máy chủ thật vẫn trả HTTP 500 ở ``POST /api/v1/classify``: log lấy lúc 22:10 cho
thấy ảnh đã lên Storage (200), model đã trả lời (200), rồi SQLAlchemy nổ
``TypeError: Object of type int64 is not JSON serializable`` khi ghi một cột JSON.

Cột ``run_node_metrics.meta`` đã được bọc từ trước; cột duy nhất còn lại trong
đường /classify nhận dữ liệu model/CLIP/YOLO là ``classifications.items`` (đi qua
``outcome.items`` — xem Bước 1 của gói P57). File này tái hiện đúng đường đó bằng
giá trị numpy THẬT (``numpy.int64`` / ``numpy.float32``), không phải lớp giả.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.routers.classify import _run_pipeline
from src.db.models import Classification, User, WasteCategory
from src.services.classifier_types import TIER_T1, ClassifyOutcome
from src.services.kieu_json import lam_sach_gia_tri, ve_kieu_python


class _FakeAgent:
    """Đóng vai ``agent.invoke`` — trả về state đã có outcome, không chạy graph."""

    def __init__(self, outcome: ClassifyOutcome) -> None:
        self._outcome = outcome

    def invoke(self, state: dict) -> dict:
        return {
            "outcome": self._outcome,
            "advice": None,
            "nodes": [],
            "schedule_hint": {},
        }


def _danh_muc(db_session: Session) -> WasteCategory:
    danh_muc = db_session.scalar(select(WasteCategory).where(WasteCategory.code == "recyclable_plastic"))
    assert danh_muc is not None, "db_session phải seed sẵn nhóm recyclable_plastic"
    return danh_muc


def _outcome_numpy(danh_muc: WasteCategory) -> ClassifyOutcome:
    """Kết quả phân loại mang items có giá trị numpy thật — như máy chủ gặp."""
    return ClassifyOutcome(
        item_name="Chai nhựa",
        category=danh_muc,
        confidence=0.87,
        tier=TIER_T1,
        model="fake",
        provider="fake",
        items=[
            {
                "name": "Chai nhựa",
                "category_code": "recyclable_plastic",
                "confidence": np.float32(0.87),
                "so_luong": np.int64(3),
            }
        ],
    )


def _user(db_session: Session) -> User:
    user = User(
        email="numpy-that@demo.vn",
        phone="0900000999",
        full_name="Người dùng test numpy",
        role="resident",
        password_hash="x",
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_ghi_items_numpy_that_vao_csdl_khong_no(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Đường ghi thật của /classify: items numpy phải ghi được, không ném TypeError."""
    danh_muc = _danh_muc(db_session)
    user = _user(db_session)
    monkeypatch.setattr("src.api.routers.classify.agent", _FakeAgent(_outcome_numpy(danh_muc)))

    with caplog.at_level(logging.WARNING, logger="src.services.kieu_json"):
        data = _run_pipeline(
            db_session,
            user=user,
            image_bytes=None,
            media=None,
            text_query="chai nhựa",
            building_id=None,
        )

    # Không ném TypeError là điều kiện tiên quyết; dữ liệu phải đúng cả giá trị.
    assert data["items"] == [
        {
            "name": "Chai nhựa",
            "category_code": "recyclable_plastic",
            "confidence": float(np.float32(0.87)),
            "so_luong": 3,
        }
    ]

    ghi = db_session.scalar(select(Classification).where(Classification.asker_id == user.id))
    assert ghi is not None
    mon = ghi.items[0]
    assert type(mon["so_luong"]) is int
    assert mon["so_luong"] == 3
    assert type(mon["confidence"]) is float
    assert mon["confidence"] == float(np.float32(0.87))

    # Logger phải chỉ rõ cột nào, khoá nào bị đổi — thứ duy nhất lần ra thủ phạm.
    loi_ghi = [r for r in caplog.records if r.name == "src.services.kieu_json"]
    assert loi_ghi, "Phải có logger.warning khi phải đổi kiểu numpy"
    noi_dung = " | ".join(r.getMessage() for r in loi_ghi)
    assert "classifications.items" in noi_dung, "log phải nêu tên cột"
    assert "so_luong" in noi_dung and "confidence" in noi_dung, "log phải nêu khoá bị đổi"
    assert "int64" in noi_dung and "float32" in noi_dung, "log phải nêu kiểu gốc numpy"


def test_items_none_khong_loi_xuong_cot_not_null(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``outcome.items = None`` phải được chặn ở biên ghi, không đụng cột NOT NULL."""
    danh_muc = _danh_muc(db_session)
    user = _user(db_session)
    outcome = ClassifyOutcome(
        item_name="Chai nhựa",
        category=danh_muc,
        confidence=0.87,
        tier=TIER_T1,
        items=None,  # type: ignore[arg-type]  — cố tình đưa None vào
    )
    monkeypatch.setattr("src.api.routers.classify.agent", _FakeAgent(outcome))

    _run_pipeline(
        db_session,
        user=user,
        image_bytes=None,
        media=None,
        text_query="chai nhựa",
        building_id=None,
    )

    ghi = db_session.scalar(select(Classification).where(Classification.asker_id == user.id))
    assert ghi is not None
    assert ghi.items == []


def test_lam_sach_gia_tri_giu_dung_kieu_python_goc() -> None:
    """numpy int64 → int, float32 → float — không dùng int()/float() mù quáng."""
    items = [
        {
            "name": "Chai nhựa",
            "category_code": "recyclable_plastic",
            "confidence": np.float32(0.87),
            "so_luong": np.int64(3),
        }
    ]
    sach = lam_sach_gia_tri(items, "classifications.items")

    assert type(sach[0]["so_luong"]) is int
    assert sach[0]["so_luong"] == 3
    assert type(sach[0]["confidence"]) is float
    assert sach[0]["confidence"] == float(np.float32(0.87))

    import json

    json.dumps(sach)  # không ném TypeError


def test_ve_kieu_python_gop_dict_list_de_qui() -> None:
    """Hàm gốc đệ quy qua dict/list/tuple, đổi từng lá numpy."""
    lon_xon = {
        "ds": [{"diem": np.float32(0.5), "so_luong": np.int64(2)}, ("x", np.int64(7))],
        "so_vat": np.int64(1),
    }
    sach = ve_kieu_python(lon_xon)
    assert type(sach["so_vat"]) is int
    assert sach["so_vat"] == 1
    assert type(sach["ds"][0]["so_luong"]) is int
    assert sach["ds"][1][1] == 7
