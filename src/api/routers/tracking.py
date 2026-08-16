"""Router theo dõi vị trí xe thu gom thời gian thực (Giai đoạn 3: OSRM Match & WebSocket)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from src.api.deps import CurrentUser, DbSession
from src.api.errors import not_found
from src.db.models import GPSLog, PickupRoute
from src.db.models_base import utcnow
from src.services import auth, duong_di_that

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tracking", tags=["tracking"])


class GPSIngestRequest(BaseModel):
    """Payload gửi vị trí GPS từ phương tiện thu gom."""

    route_id: int
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)
    accuracy_m: float | None = Field(default=None, ge=0.0)
    speed_mps: float | None = Field(default=None, ge=0.0)
    heading: float | None = Field(default=None, ge=0.0, le=360.0)
    recorded_at: datetime | None = None


class ConnectionManager:
    """Quản lý các kết nối WebSocket đang lắng nghe tracking theo route_id."""

    def __init__(self) -> None:
        self._active: dict[int, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, route_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._active.setdefault(route_id, []).append(websocket)

    async def disconnect(self, route_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            if route_id in self._active:
                self._active[route_id] = [ws for ws in self._active[route_id] if ws != websocket]
                if not self._active[route_id]:
                    del self._active[route_id]

    async def broadcast(self, route_id: int, message: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = list(self._active.get(route_id, []))

        for ws in subscribers:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.debug("Không gửi được qua WS tracking: %s", exc)


ws_manager = ConnectionManager()


@router.post("/gps")
def ingest_gps(
    payload: GPSIngestRequest,
    session: DbSession,
    user: CurrentUser,
) -> dict:
    """Nhận toạ độ GPS thô, snap vào đường thật bằng OSRM Match, lưu và broadcast."""
    route = session.get(PickupRoute, payload.route_id)
    if route is None:
        raise not_found("tuyến thu gom này")

    # Lấy tối đa 4 điểm gần nhất để tạo cửa sổ snap mượt mà (Match API cần chuỗi điểm)
    recent_logs = session.scalars(
        select(GPSLog)
        .where(GPSLog.route_id == payload.route_id)
        .order_by(desc(GPSLog.recorded_at))
        .limit(4)
    ).all()
    recent_points = [(r.lat, r.lng) for r in reversed(recent_logs)]
    recent_points.append((payload.lat, payload.lng))

    snapped_points = duong_di_that.snap_gps(recent_points)
    if snapped_points and len(snapped_points) == len(recent_points):
        snapped_lat, snapped_lng = snapped_points[-1]
    else:
        snapped_lat, snapped_lng = payload.lat, payload.lng

    recorded_time = payload.recorded_at or utcnow()

    gps_entry = GPSLog(
        route_id=payload.route_id,
        user_id=user.id,
        lat=payload.lat,
        lng=payload.lng,
        snapped_lat=snapped_lat,
        snapped_lng=snapped_lng,
        accuracy_m=payload.accuracy_m,
        speed_mps=payload.speed_mps,
        heading=payload.heading,
        recorded_at=recorded_time,
    )
    session.add(gps_entry)
    session.flush()

    msg = {
        "type": "gps_update",
        "route_id": payload.route_id,
        "user_id": user.id,
        "lat": payload.lat,
        "lng": payload.lng,
        "snapped_lat": snapped_lat,
        "snapped_lng": snapped_lng,
        "speed_mps": payload.speed_mps,
        "heading": payload.heading,
        "accuracy_m": payload.accuracy_m,
        "recorded_at": recorded_time.isoformat(),
    }

    # Gửi broadcast cho client WebSocket đang theo dõi
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(ws_manager.broadcast(payload.route_id, msg))
    except RuntimeError:
        pass

    return {
        "status": "ok",
        "id": gps_entry.id,
        "lat": payload.lat,
        "lng": payload.lng,
        "snapped_lat": snapped_lat,
        "snapped_lng": snapped_lng,
    }


@router.get("/{route_id}/latest")
def get_latest_position(
    route_id: int,
    session: DbSession,
    user: CurrentUser,
) -> dict:
    """Vị trí GPS mới nhất của xe trên tuyến."""
    route = session.get(PickupRoute, route_id)
    if route is None:
        raise not_found("tuyến thu gom này")

    latest = session.scalars(
        select(GPSLog)
        .where(GPSLog.route_id == route_id)
        .order_by(desc(GPSLog.recorded_at))
        .limit(1)
    ).first()

    if latest is None:
        return {"route_id": route_id, "position": None}

    return {
        "route_id": route_id,
        "position": {
            "lat": latest.lat,
            "lng": latest.lng,
            "snapped_lat": latest.snapped_lat or latest.lat,
            "snapped_lng": latest.snapped_lng or latest.lng,
            "speed_mps": latest.speed_mps,
            "heading": latest.heading,
            "accuracy_m": latest.accuracy_m,
            "recorded_at": latest.recorded_at.isoformat() if latest.recorded_at else None,
        },
    }


@router.get("/{route_id}/history")
def get_route_tracking_history(
    route_id: int,
    session: DbSession,
    user: CurrentUser,
) -> dict:


    """Toàn bộ lịch sử toạ độ GPS đã ghi nhận trên tuyến."""
    route = session.get(PickupRoute, route_id)
    if route is None:
        raise not_found("tuyến thu gom này")

    logs = session.scalars(
        select(GPSLog)
        .where(GPSLog.route_id == route_id)
        .order_by(GPSLog.recorded_at)
    ).all()

    return {
        "route_id": route_id,
        "count": len(logs),
        "items": [
            {
                "lat": log.lat,
                "lng": log.lng,
                "snapped_lat": log.snapped_lat or log.lat,
                "snapped_lng": log.snapped_lng or log.lng,
                "speed_mps": log.speed_mps,
                "heading": log.heading,
                "accuracy_m": log.accuracy_m,
                "recorded_at": log.recorded_at.isoformat() if log.recorded_at else None,
            }
            for log in logs
        ],
    }


@router.websocket("/ws/{route_id}")
async def ws_route_tracking(
    websocket: WebSocket,
    route_id: int,
    token: str = Query(default=""),
) -> None:
    """Kênh WebSocket truyền vị trí xe thời gian thực cho Ban Quản Lý."""
    # Xác thực token nếu có
    if token:
        try:
            claims = auth.decode_token(token)
            if not claims:
                await websocket.close(code=4001, reason="Token không hợp lệ")
                return
        except Exception:
            await websocket.close(code=4001, reason="Token không hợp lệ")
            return

    await ws_manager.connect(route_id, websocket)
    try:
        while True:
            # Giữ kết nối mở, có thể nhận heartbeat ping/pong từ client
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(route_id, websocket)
    except Exception:
        await ws_manager.disconnect(route_id, websocket)
