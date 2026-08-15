"""Test API tracking và GPS logging (Giai đoạn 3)."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from src.api.errors import ApiError
from src.api.routers.tracking import (
    GPSIngestRequest,
    get_latest_position,
    get_route_tracking_history,
    ingest_gps,
)
from src.db.models import GPSLog, PickupRoute, User


def _setup_route_and_user(db_session: Session) -> tuple[PickupRoute, User]:
    user = User(
        email="cleaner-gps@test.vn",
        full_name="Nguyễn Văn Lái Xe",
        role="cleaner",
        password_hash="fake",
    )
    db_session.add(user)
    db_session.flush()

    route = PickupRoute(
        service_date=date(2026, 8, 15),
        window="sang",
        team_id=user.id,
        status="approved",
    )
    db_session.add(route)
    db_session.flush()
    return route, user


def test_ingest_gps_thanh_cong(db_session: Session) -> None:
    route, user = _setup_route_and_user(db_session)

    req = GPSIngestRequest(
        route_id=route.id,
        lat=21.0285,
        lng=105.8542,
        accuracy_m=5.0,
        speed_mps=8.5,
        heading=90.0,
    )

    res = ingest_gps(req, db_session, user)

    assert res["status"] == "ok"
    assert res["lat"] == 21.0285
    assert res["lng"] == 105.8542
    assert "id" in res

    # Kiểm tra CSDL đã lưu đúng
    log = db_session.get(GPSLog, res["id"])
    assert log is not None
    assert log.route_id == route.id
    assert log.user_id == user.id
    assert log.speed_mps == 8.5
    assert log.heading == 90.0


def test_ingest_gps_route_khong_ton_tai(db_session: Session) -> None:
    _, user = _setup_route_and_user(db_session)

    req = GPSIngestRequest(
        route_id=99999,
        lat=21.0285,
        lng=105.8542,
    )

    with pytest.raises(ApiError) as exc_info:
        ingest_gps(req, db_session, user)

    assert exc_info.value.status_code == 404


def test_get_latest_position(db_session: Session) -> None:
    route, user = _setup_route_and_user(db_session)

    # Khi chưa có GPS nào
    res_empty = get_latest_position(route.id, db_session, user)
    assert res_empty["route_id"] == route.id
    assert res_empty["position"] is None

    # Gửi 2 điểm GPS liên tiếp
    ingest_gps(
        GPSIngestRequest(route_id=route.id, lat=21.0280, lng=105.8540, recorded_at=datetime(2026, 8, 15, 8, 0, 0)),
        db_session,
        user,
    )
    ingest_gps(
        GPSIngestRequest(route_id=route.id, lat=21.0290, lng=105.8550, recorded_at=datetime(2026, 8, 15, 8, 0, 10)),
        db_session,
        user,
    )

    res_latest = get_latest_position(route.id, db_session, user)
    assert res_latest["position"] is not None
    assert res_latest["position"]["lat"] == 21.0290
    assert res_latest["position"]["lng"] == 105.8550


def test_get_route_tracking_history(db_session: Session) -> None:
    route, user = _setup_route_and_user(db_session)

    ingest_gps(
        GPSIngestRequest(route_id=route.id, lat=21.0280, lng=105.8540, recorded_at=datetime(2026, 8, 15, 8, 0, 0)),
        db_session,
        user,
    )
    ingest_gps(
        GPSIngestRequest(route_id=route.id, lat=21.0290, lng=105.8550, recorded_at=datetime(2026, 8, 15, 8, 0, 10)),
        db_session,
        user,
    )

    res_history = get_route_tracking_history(route.id, db_session, user)
    assert res_history["route_id"] == route.id
    assert res_history["count"] == 2
    assert len(res_history["items"]) == 2
    assert res_history["items"][0]["lat"] == 21.0280
    assert res_history["items"][1]["lat"] == 21.0290
