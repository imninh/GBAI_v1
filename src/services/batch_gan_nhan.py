"""Gom ảnh lỗi thành lô để gán nhãn và huấn luyện lại (gói P74).

Ảnh lỗi: máy không ra được nhãn, cần người xem lại, độ tin cậy dưới ngưỡng,
hoặc người xác nhận nhãn khác nhãn máy đoán. Ảnh được đánh dấu
``can_gan_nhan = True`` rồi gom vào ``batch_gan_nhan`` để huấn luyện lại.

**Quyền riêng tư (§3):** lô ảnh KHÔNG mang danh tính người tải lên — mọi phản
hồi ra ngoài không trả ``uploader_id``; ảnh vào lô KHÔNG sinh điểm thưởng, không
đụng ``users.green_points`` hay ``diem_thuong_log``. Ảnh đã qua tiền xử lý (tước
EXIF, làm mờ mặt, nén 512px) là việc của ``services/image_privacy.py`` — gói này
không đụng vào, cũng không bỏ qua.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.db.models import BatchGanNhan, Classification, Media, User
from src.services.auth import write_audit

# Ngưỡng dưới thì ảnh cần gán nhãn lại. Số ĐẶT TẠM, chưa có căn cứ đo đạc — đúng
# tinh thần dự án đã làm với `DIEM_NHAN_THUC_MOI_VAT`.
NGUONG_CAN_GAN_NHAN = 0.60

# Nhãn của lô: có người tải lên / thiết bị / lẫn lộn.
NGUON_APP = "app"
NGUON_THIET_BI = "thiet_bi"
NGUON_HON_HOP = "hon_hop"


def _la_anh_loi(cls: Classification) -> bool:
    """Đúng nếu ít nhất một trong bốn điều kiện "ảnh lỗi" ở §2.

    Tên trường đối chiếu trực tiếp với ``src/db/models_classify.py``:
    ``predicted_category_id`` · ``refused`` · ``escalated_to_human`` ·
    ``confidence`` · ``human_label_id``. ``Classification`` KHÔNG có trường
    ``label`` hay ``requires_review``.
    """
    # 1. Máy không ra được nhãn (tương đương UNKNOWN): không có nhãn dự đoán,
    #    hoặc hệ thống từ chối trả lời.
    if cls.predicted_category_id is None or cls.refused:
        return True
    # 2. Cần người xem lại.
    if cls.escalated_to_human:
        return True
    # 3. Độ tin cậy dưới ngưỡng.
    if cls.confidence < NGUONG_CAN_GAN_NHAN:
        return True
    # 4. Người xác nhận nhãn khác nhãn máy đoán.
    if cls.human_label_id is not None and cls.human_label_id != cls.predicted_category_id:
        return True
    return False


def quet_anh_can_gan_nhan(
    session: Session,
    *,
    tu_ngay: date | None = None,
    den_ngay: date | None = None,
    gioi_han: int = 500,
) -> dict[str, int]:
    """Quét ``Classification``, đặt ``media.can_gan_nhan = True`` cho ảnh lỗi.

    Trả về ``{"da_quet", "moi_danh_dau", "bo_qua_da_co_lo"}``.

    - Không đặt lại cờ cho ảnh đã có ``batch_id`` — ảnh đã vào lô thì để yên.
    - ``tu_ngay`` / ``den_ngay`` truyền vào, không gọi ``datetime.now()``.
    """
    stmt = select(Classification).where(Classification.media_id.is_not(None))
    if tu_ngay is not None:
        stmt = stmt.where(Classification.created_at >= tu_ngay)
    if den_ngay is not None:
        stmt = stmt.where(Classification.created_at <= den_ngay)
    stmt = stmt.limit(gioi_han)

    da_quet = 0
    moi_danh_dau = 0
    bo_qua_da_co_lo = 0

    for cls in session.scalars(stmt).all():
        da_quet += 1
        media = session.get(Media, cls.media_id)
        if media is None:
            continue
        if media.batch_id is not None:
            bo_qua_da_co_lo += 1
            continue
        if not media.can_gan_nhan and _la_anh_loi(cls):
            media.can_gan_nhan = True
            moi_danh_dau += 1

    session.flush()
    return {
        "da_quet": da_quet,
        "moi_danh_dau": moi_danh_dau,
        "bo_qua_da_co_lo": bo_qua_da_co_lo,
    }


def _dem_so_thu_tu_trong_ngay(session: Session, ngay: date) -> int:
    """Số batch đã có trong ngày (theo tiền tố ``BATCH-YYYY-MM-DD-``)."""
    tien_to = f"BATCH-{ngay.isoformat()}-"
    cac_ma = session.scalars(select(BatchGanNhan.ma)).all()
    return sum(1 for ma in cac_ma if ma.startswith(tien_to))


def _suy_nguon(session: Session, batch: BatchGanNhan) -> str:
    """Tự suy ``nguon`` từ ``uploader_id`` của ảnh trong lô — không bắt người
    gọi khai. Ảnh từ thiết bị vốn có ``uploader_id = NULL``."""
    media_list = session.scalars(select(Media).where(Media.batch_id == batch.id)).all()
    if not media_list:
        return NGUON_HON_HOP
    co_uploader = sum(1 for m in media_list if m.uploader_id is not None)
    if co_uploader == 0:
        return NGUON_THIET_BI
    if co_uploader == len(media_list):
        return NGUON_APP
    return NGUON_HON_HOP


def tao_batch(
    session: Session,
    *,
    actor: User | None,
    ngay: date,
    nguon: str = NGUON_HON_HOP,
    so_anh_toi_da: int = 200,
    ghi_chu: str = "",
) -> BatchGanNhan | None:
    """Gom ảnh ``can_gan_nhan = True`` và ``batch_id IS NULL`` thành một lô.

    - Không có ảnh nào → KHÔNG tạo lô rỗng, trả ``None``.
    - ``ma`` theo khuôn ``BATCH-YYYY-MM-DD-NN``; ``ngay`` truyền vào (không gọi
      ``datetime.now()``), ``NN`` là số thứ tự trong ngày.
    - ``nguon`` tự suy từ ``uploader_id`` của ảnh — tham số ``nguon`` chỉ là giá
      trị nền, luôn bị ghi đè bằng kết quả suy.
    """
    media_list = session.scalars(
        select(Media)
        .where(Media.can_gan_nhan.is_(True), Media.batch_id.is_(None))
        .limit(so_anh_toi_da)
    ).all()
    if not media_list:
        return None

    ma = f"BATCH-{ngay.isoformat()}-{_dem_so_thu_tu_trong_ngay(session, ngay) + 1:02d}"
    batch = BatchGanNhan(
        ma=ma,
        trang_thai="mo",
        nguon=nguon,
        so_anh=0,
        ghi_chu=ghi_chu,
        nguoi_tao_id=actor.id if actor else None,
    )
    session.add(batch)
    session.flush()

    for media in media_list:
        media.batch_id = batch.id
    session.flush()

    batch.so_anh = len(media_list)
    batch.nguon = _suy_nguon(session, batch)
    session.flush()

    write_audit(
        session,
        actor=actor,
        action="tao_batch_gan_nhan",
        entity="batch_gan_nhan",
        entity_id=str(batch.id),
        detail={"ma": ma, "so_anh": batch.so_anh, "nguon": batch.nguon},
    )
    return batch


def dong_batch(
    session: Session,
    *,
    actor: User | None,
    batch_id: int,
    dong_luc: datetime | None = None,
) -> BatchGanNhan:
    """Đóng một lô: ``mo`` → ``dong``, ghi ``dong_luc``.

    Đã đóng (trạng thái khác ``mo``) → từ chối, không ghi đè. ``dong_luc`` là
    tham số truyền vào; khi không truyền mới lấy thời điểm hiện tại.
    """
    batch = session.get(BatchGanNhan, batch_id)
    if batch is None:
        raise ValueError("Lô không tồn tại")
    if batch.trang_thai != "mo":
        raise ValueError(f"Lô đang ở trạng thái {batch.trang_thai!r}, không đóng lại được")

    batch.trang_thai = "dong"
    batch.dong_luc = dong_luc if dong_luc is not None else datetime.now(UTC)
    session.flush()

    write_audit(
        session,
        actor=actor,
        action="dong_batch_gan_nhan",
        entity="batch_gan_nhan",
        entity_id=str(batch.id),
        detail={"ma": batch.ma},
    )
    return batch


def danh_sach_batch(
    session: Session,
    *,
    trang_thai: str | None = None,
    limit: int = 50,
) -> list[BatchGanNhan]:
    """Danh sách lô, mới nhất trước."""
    stmt = select(BatchGanNhan)
    if trang_thai:
        stmt = stmt.where(BatchGanNhan.trang_thai == trang_thai)
    stmt = stmt.order_by(desc(BatchGanNhan.created_at)).limit(limit)
    return list(session.scalars(stmt).all())


def chi_tiet_batch(session: Session, *, batch_id: int) -> dict | None:
    """Thông tin lô + danh sách ảnh trong lô.

    **Danh sách ảnh KHÔNG chứa ``uploader_id`` hay bất kỳ trường danh tính nào**
    (§3). Chỉ trả ``media.id``, đường dẫn, thời điểm, và nhãn máy đoán.
    """
    batch = session.get(BatchGanNhan, batch_id)
    if batch is None:
        return None

    media_list = session.scalars(
        select(Media).where(Media.batch_id == batch.id).order_by(Media.id)
    ).all()

    anh: list[dict] = []
    for media in media_list:
        cls = session.scalars(
            select(Classification)
            .where(Classification.media_id == media.id)
            .order_by(desc(Classification.id))
            .limit(1)
        ).first()
        anh.append(
            {
                "id": media.id,
                "stored_path": media.stored_path,
                "created_at": media.created_at.isoformat() if media.created_at else None,
                "predicted_category_id": cls.predicted_category_id if cls else None,
                "item_name": cls.item_name if cls else "",
                "confidence": cls.confidence if cls else 0.0,
            }
        )

    return {
        "id": batch.id,
        "ma": batch.ma,
        "trang_thai": batch.trang_thai,
        "nguon": batch.nguon,
        "so_anh": batch.so_anh,
        "ghi_chu": batch.ghi_chu,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "dong_luc": batch.dong_luc.isoformat() if batch.dong_luc else None,
        "anh": anh,
    }
