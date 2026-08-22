"""Kiểm thử gom ảnh lỗi thành lô gán nhãn (gói P74).

Chạy trên SQLite trong bộ nhớ — không đụng CSDL thật. Mọi thời điểm trong test
truyền vào (ngày lô, thời điểm đóng, khoảng quét), không dùng ``datetime.now()``.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import (
    BatchGanNhan,
    Classification,
    DiemThuongLog,
    Media,
    User,
    WasteCategory,
)
from src.services.batch_gan_nhan import (
    NGUONG_CAN_GAN_NHAN,
    chi_tiet_batch,
    danh_sach_batch,
    dong_batch,
    quet_anh_can_gan_nhan,
    tao_batch,
)

NGAY_LUU = date(2026, 8, 20)
THOI_DIEM_DONG = datetime(2026, 8, 20, 12, 0, 0)


def _tao_user(session: Session, *, email: str = "nguoitest@sim.vn") -> User:
    user = User(email=email, full_name="Người test", role="manager", password_hash="x")
    session.add(user)
    session.flush()
    return user


def _nhom_rac_dau_tien(session: Session) -> WasteCategory:
    return session.scalars(select(WasteCategory).limit(1)).one()


def _tao_anh(
    session: Session,
    *,
    uploader: User | None = None,
    confidence: float = 0.9,
    predicted_id: int | None = None,
    refused: bool = False,
    escalated: bool = False,
    human_label_id: int | None = None,
    batch_id: int | None = None,
    danh_dau: bool = False,
    created_at: datetime | None = None,
) -> Media:
    """Tạo một ảnh + một lần phân loại gắn vào nó.

    ``danh_dau=True`` mô phỏng ảnh đã qua quét và được đánh dấu ``can_gan_nhan``
    (tương đương gọi ``quet_anh_can_gan_nhan`` trước đó). ``created_at`` truyền
    vào để test filter theo ngày xác định, không dùng ``datetime.now()``.
    """
    media = Media(
        stored_path=f"/tmp/anh_{len(session.scalars(select(Media)).all())}.jpg",
        uploader_id=uploader.id if uploader else None,
        batch_id=batch_id,
        can_gan_nhan=danh_dau,
    )
    session.add(media)
    session.flush()
    cls = Classification(
        media_id=media.id,
        confidence=confidence,
        predicted_category_id=predicted_id,
        refused=refused,
        escalated_to_human=escalated,
        human_label_id=human_label_id,
        created_at=created_at or datetime(2026, 8, 20, 10, 0, 0),
    )
    session.add(cls)
    session.flush()
    return media


# --- 1. Nhãn UNKNOWN → đánh dấu --------------------------------------------

def test_anh_unknown_duoc_danh_dau(db_session: Session) -> None:
    """predicted_category_id IS NULL → can_gan_nhan."""
    _tao_anh(db_session, confidence=0.9, predicted_id=None, created_at=datetime(2026, 8, 20, 10, 0, 0))
    ket_qua = quet_anh_can_gan_nhan(db_session, tu_ngay=NGAY_LUU)
    db_session.commit()

    assert ket_qua["moi_danh_dau"] == 1
    media = db_session.scalars(select(Media)).one()
    assert media.can_gan_nhan is True


def test_anh_refused_duoc_danh_dau(db_session: Session) -> None:
    """refused=True → can_gan_nhan."""
    _tao_anh(db_session, confidence=0.9, predicted_id=1, refused=True)
    ket_qua = quet_anh_can_gan_nhan(db_session)
    db_session.commit()

    assert ket_qua["moi_danh_dau"] == 1
    media = db_session.scalars(select(Media)).one()
    assert media.can_gan_nhan is True


# --- 2. Độ tin cậy dưới ngưỡng → đánh dấu ---------------------------------

def test_anh_do_tin_cay_thap_duoc_danh_dau(db_session: Session) -> None:
    nhom = _nhom_rac_dau_tien(db_session)
    _tao_anh(db_session, confidence=NGUONG_CAN_GAN_NHAN - 0.1, predicted_id=nhom.id)
    ket_qua = quet_anh_can_gan_nhan(db_session)
    db_session.commit()

    assert ket_qua["moi_danh_dau"] == 1
    media = db_session.scalars(select(Media)).one()
    assert media.can_gan_nhan is True


# --- 3. Phân loại tốt, tin cậy cao → KHÔNG đánh dấu -----------------------

def test_anh_tot_khong_danh_dau(db_session: Session) -> None:
    nhom = _nhom_rac_dau_tien(db_session)
    _tao_anh(db_session, confidence=0.9, predicted_id=nhom.id)
    ket_qua = quet_anh_can_gan_nhan(db_session)
    db_session.commit()

    assert ket_qua["moi_danh_dau"] == 0
    media = db_session.scalars(select(Media)).one()
    assert media.can_gan_nhan is False


# --- 4. Ảnh đã có batch_id → quét không đụng -------------------------------

def test_anh_da_co_batch_khong_bi_quet_lai(db_session: Session) -> None:
    _tao_anh(db_session, confidence=0.4, predicted_id=None, danh_dau=True)
    batch = tao_batch(db_session, actor=None, ngay=NGAY_LUU)
    assert batch is not None
    anh = db_session.scalars(select(Media)).one()
    assert anh.batch_id == batch.id

    ket_qua = quet_anh_can_gan_nhan(db_session, gioi_han=100)

    assert ket_qua["bo_qua_da_co_lo"] == 1
    db_session.commit()
    anh_moi = db_session.get(Media, anh.id)
    assert anh_moi.batch_id == batch.id


# --- 5. tao_batch gán đúng batch_id, so_anh khớp ---------------------------

def test_tao_batch_gan_dung_batch_id(db_session: Session) -> None:
    for _ in range(3):
        _tao_anh(db_session, confidence=0.4, predicted_id=None, danh_dau=True)
    db_session.commit()

    batch = tao_batch(db_session, actor=None, ngay=NGAY_LUU)
    assert batch is not None
    db_session.commit()

    anh = db_session.scalars(select(Media).where(Media.batch_id == batch.id)).all()
    assert len(anh) == 3
    assert batch.so_anh == 3
    assert batch.ma == "BATCH-2026-08-20-01"


# --- 6. Không có ảnh → không tạo lô rỗng ----------------------------------

def test_khong_anh_thi_khong_tao_lo_rong(db_session: Session) -> None:
    batch = tao_batch(db_session, actor=None, ngay=NGAY_LUU)

    assert batch is None
    assert len(db_session.scalars(select(BatchGanNhan)).all()) == 0


# --- 7. nguon suy đúng: app · thiết bị · lẫn lộn ---------------------------

def test_nguon_toan_app(db_session: Session) -> None:
    user = _tao_user(db_session)
    _tao_anh(db_session, uploader=user, confidence=0.4, predicted_id=1, danh_dau=True)
    _tao_anh(db_session, uploader=user, confidence=0.5, predicted_id=1, danh_dau=True)
    batch = tao_batch(db_session, actor=user, ngay=NGAY_LUU)
    assert batch is not None
    assert batch.nguon == "app"


def test_nguon_toan_thiet_bi(db_session: Session) -> None:
    _tao_anh(db_session, confidence=0.4, predicted_id=None, danh_dau=True)
    _tao_anh(db_session, confidence=0.5, predicted_id=None, danh_dau=True)
    batch = tao_batch(db_session, actor=None, ngay=NGAY_LUU)
    assert batch is not None
    assert batch.nguon == "thiet_bi"


def test_nguon_lan_lo(db_session: Session) -> None:
    user = _tao_user(db_session)
    _tao_anh(db_session, uploader=user, confidence=0.4, predicted_id=1, danh_dau=True)
    _tao_anh(db_session, confidence=0.5, predicted_id=1, danh_dau=True)
    batch = tao_batch(db_session, actor=None, ngay=NGAY_LUU)
    assert batch is not None
    assert batch.nguon == "hon_hop"


# --- 8. dong_batch lần hai → từ chối ---------------------------------------

def test_dong_batch_hai_lan_tu_choi(db_session: Session) -> None:
    _tao_anh(db_session, confidence=0.4, predicted_id=None, danh_dau=True)
    batch = tao_batch(db_session, actor=None, ngay=NGAY_LUU)
    assert batch is not None

    da_dong = dong_batch(db_session, actor=None, batch_id=batch.id, dong_luc=THOI_DIEM_DONG)
    assert da_dong.trang_thai == "dong"

    try:
        dong_batch(db_session, actor=None, batch_id=batch.id, dong_luc=THOI_DIEM_DONG)
        assert False, "Đóng lần hai phải bị từ chối"
    except ValueError:
        pass


# --- 9. chi_tiet_batch KHÔNG trả uploader_id -------------------------------

def test_chi_tiet_batch_khong_tra_uploader_id(db_session: Session) -> None:
    user = _tao_user(db_session)
    _tao_anh(db_session, uploader=user, confidence=0.4, predicted_id=None, danh_dau=True)
    batch = tao_batch(db_session, actor=user, ngay=NGAY_LUU)
    assert batch is not None

    chi_tiet = chi_tiet_batch(db_session, batch_id=batch.id)
    assert chi_tiet is not None
    assert "uploader_id" not in chi_tiet
    for anh in chi_tiet["anh"]:
        assert "uploader_id" not in anh
        assert "stored_path" in anh
        assert "predicted_category_id" in anh


# --- 10. Không ghi điểm thưởng ---------------------------------------------

def test_khong_ghi_diem_thuong(db_session: Session) -> None:
    user = _tao_user(db_session)
    user.green_points = 120
    db_session.commit()
    _tao_anh(db_session, uploader=user, confidence=0.4, predicted_id=1)
    _tao_anh(db_session, confidence=0.5, predicted_id=None)

    quet_anh_can_gan_nhan(db_session)
    batch = tao_batch(db_session, actor=user, ngay=NGAY_LUU)
    dong_batch(db_session, actor=user, batch_id=batch.id, dong_luc=THOI_DIEM_DONG)
    db_session.commit()

    assert user.green_points == 120
    so_log_diem = len(db_session.scalars(select(DiemThuongLog)).all())
    assert so_log_diem == 0
    assert len(danh_sach_batch(db_session, trang_thai="dong")) == 1
