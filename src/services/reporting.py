"""Báo cáo tuân thủ theo tháng — bảng thu gom và vận hành cho ban quản lý.

Đây là hiện thân rõ nhất của nguyên tắc "mỗi kết quả AI phải sinh ra một bản
ghi" (ADR-0002): báo cáo được **tính từ dữ liệu thật trong CSDL**, không phải
con số viết tay.

Mọi con số đều tách riêng ``is_seed`` để dữ liệu demo mô phỏng không bao giờ
lẫn vào báo cáo thật. Chỗ gọi UI phải hiện nhãn "dữ liệu demo mô phỏng" cho
khối seed, giống các trang vận hành khác.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import Classification, PickupRequest, WasteCategory
from src.services.classifier import TIER_T2
from src.services.pickup_lifecycle import trang_thai_tuong_duong

NGAY_DAU_THANG = 1


def _thang_range(thang: str) -> tuple[datetime, datetime]:
    """Chặn trước một chuỗi ``YYYY-MM`` thành khoảng ``[đầu tháng, đầu tháng sau)``.

    Raises:
        ValueError: chuỗi không đúng định dạng hoặc không phải một tháng hợp lệ.
    """
    try:
        dau = datetime.strptime(thang, "%Y-%m")
    except ValueError as exc:
        raise ValueError(f"Tháng '{thang}' không hợp lệ — dùng định dạng YYYY-MM.") from exc
    if dau.month == 12:
        cuoi = datetime(dau.year + 1, NGAY_DAU_THANG, 1)
    else:
        cuoi = datetime(dau.year, dau.month + 1, NGAY_DAU_THANG, 1)
    return dau.replace(day=NGAY_DAU_THANG, hour=0, minute=0, second=0), cuoi


def _phan_bo_khoi_luong(items: list[dict], weight_confirmed_kg: float) -> dict[str, float]:
    """Chia khối lượng xác nhận của một yêu cầu cho các nhóm rác trong ``items``.

    Một yêu cầu có thể chứa nhiều món thuộc nhiều nhóm khác nhau, mà hệ thống chỉ
    lưu **một** con số ``weight_confirmed_kg`` cho cả yêu cầu. Chia theo tỉ trọng
    số lượng (``qty``) giữa các món, để tổng khối lượng theo nhóm vẫn bằng đúng
    khối lượng xác nhận — không có chuyện một kg bị đếm hai lần.
    """
    tong_qty = sum(int(m.get("qty") or 1) for m in items)
    phan_bo: dict[str, float] = defaultdict(float)
    if tong_qty <= 0:
        return phan_bo
    for mon in items:
        code = str(mon.get("category_code") or "khong_xac_dinh")
        phan = weight_confirmed_kg * (int(mon.get("qty") or 1) / tong_qty)
        phan_bo[code] += phan
    return dict(phan_bo)


def _dien_tich_trang_thai(session: Session, thang: str) -> dict[str, dict[str, int]]:
    """Số yêu cầu thu gom theo trạng thái, tách riêng ``is_seed``.

    Trạng thái lấy theo **từ vựng mới** qua ``trang_thai_tuong_duong`` để cả
    hàng còn giữ giá trị cũ cũng được đếm đúng nhóm.
    """
    from src.services.pickup_lifecycle import CHUYEN_TIEP

    dau, cuoi = _thang_range(thang)
    rows = session.scalars(
        select(PickupRequest).where(PickupRequest.created_at >= dau, PickupRequest.created_at < cuoi)
    ).all()

    ket_qua: dict[str, dict[str, int]] = {}
    for trang_thai in CHUYEN_TIEP:
        nhom_cu = set(trang_thai_tuong_duong(trang_thai))
        real = 0
        seed = 0
        for row in rows:
            if row.status in nhom_cu:
                if row.is_seed:
                    seed += 1
                else:
                    real += 1
        ket_qua[trang_thai] = {"real": real, "seed": seed}
    return ket_qua


def _classification_stats(session: Session, thang: str) -> dict[str, dict[str, int]]:
    """Lượt phân loại AI: tổng, bị từ chối, leo lên T2 — tách ``is_seed``."""
    dau, cuoi = _thang_range(thang)
    rows = session.scalars(
        select(Classification).where(Classification.created_at >= dau, Classification.created_at < cuoi)
    ).all()

    stats: dict[str, dict[str, int]] = {"total": {"real": 0, "seed": 0}}
    for row in rows:
        nhom = "seed" if row.is_seed else "real"
        stats["total"][nhom] += 1
        if row.refused:
            stats.setdefault("refused", {"real": 0, "seed": 0})[nhom] += 1
        if row.tier == TIER_T2 or row.escalated_to_human:
            stats.setdefault("escalated", {"real": 0, "seed": 0})[nhom] += 1
    return stats


def _khong_luong_theo_nhom(session: Session, thang: str) -> dict[str, dict[str, float]]:
    """Khối lượng THẬT đã xác nhận theo nhóm rác, tách ``is_seed``.

    Chỉ tính các yêu cầu đã có ``weight_confirmed_kg`` — con số do người xác
    nhận cân, không bao giờ là ước lượng của AI.
    """
    dau, cuoi = _thang_range(thang)
    rows = session.scalars(
        select(PickupRequest).where(PickupRequest.created_at >= dau, PickupRequest.created_at < cuoi)
    ).all()

    ket_qua: dict[str, dict[str, float]] = defaultdict(lambda: {"real": 0.0, "seed": 0.0})
    for row in rows:
        if row.weight_confirmed_kg is None:
            continue
        nhom = "seed" if row.is_seed else "real"
        phan_bo = _phan_bo_khoi_luong(row.items or [], float(row.weight_confirmed_kg))
        for code, kg in phan_bo.items():
            ket_qua[code][nhom] += kg
    return {code: {"real": round(v["real"], 1), "seed": round(v["seed"], 1)} for code, v in ket_qua.items()}


def _hazardous_detections(session: Session, thang: str) -> dict[str, int]:
    """Số lượt phát hiện rác nguy hại — theo nhãn đúng do người xác nhận.

    Đếm các ca có ``human_label_id`` trỏ vào nhóm nguy hại, tách ``is_seed``.
    Con số này đo "AI đã bắt gặp nguy hại bao nhiêu lần" chứ không đo model
    dự đoán, vì nhãn do người xác nhận là nguồn sự thật.
    """
    dau, cuoi = _thang_range(thang)
    ma_nguy_hai = set(
        session.scalars(select(WasteCategory.id).where(WasteCategory.is_hazardous.is_(True))).all()
    )
    rows = session.scalars(
        select(Classification).where(Classification.created_at >= dau, Classification.created_at < cuoi)
    ).all()

    ket_qua = {"real": 0, "seed": 0}
    for row in rows:
        if row.human_label_id is not None and row.human_label_id in ma_nguy_hai:
            nhom = "seed" if row.is_seed else "real"
            ket_qua[nhom] += 1
    return ket_qua


def bao_cao_tuan_thu(session: Session, thang: str) -> dict[str, Any]:
    """Báo cáo tuân thủ một tháng, định dạng ``YYYY-MM``.

    Một tháng không có dữ liệu trả về **báo cáo đầy đủ số 0** — đó là một câu
    trả lời hợp lệ, không phải lỗi 404.

    Raises:
        ValueError: ``thang`` không phải định dạng ``YYYY-MM``.
    """
    dau, cuoi = _thang_range(thang)

    return {
        "thang": thang,
        "from": dau.isoformat(),
        "to": cuoi.isoformat(),
        "confirmed_weight_by_category": _khong_luong_theo_nhom(session, thang),
        "hazardous_detections": _hazardous_detections(session, thang),
        "pickup_requests_by_state": _dien_tich_trang_thai(session, thang),
        "ai_classifications": _classification_stats(session, thang),
        "has_seed_data": session.scalar(
            select(func.count(Classification.id)).where(
                Classification.created_at >= dau,
                Classification.created_at < cuoi,
                Classification.is_seed.is_(True),
            )
        )
        > 0,
    }
