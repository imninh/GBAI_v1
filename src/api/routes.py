"""Gom toàn bộ router của API v1.

Đường dẫn khớp hợp đồng ở ``docs/FRONTEND_SPEC.md`` mục 7.
"""

from fastapi import APIRouter

from src.api.routers import auth, bins, catalog, classify, media, ops, pickups, routes, tracking
from src.services.vision import provider_status

router = APIRouter()

router.include_router(auth.router)
router.include_router(classify.router)
router.include_router(media.router)
router.include_router(catalog.router)
router.include_router(pickups.router)
router.include_router(routes.router)
router.include_router(ops.router)
router.include_router(bins.router)
router.include_router(tracking.router)


@router.get("/status", tags=["ops"])
def status() -> dict:
    """Trạng thái hệ thống — công khai, không cần đăng nhập.

    Trả về nhà cung cấp model đang dùng và **có key hay chưa**; giá trị key
    không bao giờ được trả ra ngoài.
    """
    return {"status": "ready", "app": "GreenBin AI", "version": "1.0.0", "model": provider_status()}
