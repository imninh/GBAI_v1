"""Phiên bỏ rác tại thùng — quét mã → đếm vật → cộng điểm nhận thức (P63).

Toàn bộ luật nghiệp vụ của phiên nằm ở đây; router chỉ lo HTTP.

## Luồng đã chốt

1. Cư dân quét QR trên thùng → app đọc ``bin_code``.
2. ``mo_phien`` mở phiên, trả ``ma_phien`` với hạn 10 phút.
3. Thùng ESP32 chụp, gọi ``/iot/captures`` — Y NGUYÊN như hôm nay. Máy chủ tự tra
   phiên đang mở của thùng đó và gắn kết quả vào (xem ``src/api/iot.py``).
4. Mỗi vật được chấp nhận → cộng vào ``so_vat``.
5. Bấm xong / hết hạn → ``dong_phien`` → tính điểm nhận thức → sinh thông báo.

## ⚠️ Luật điểm — quy tắc nhóm đã chốt

*"Điểm có giá trị chỉ tính trên khối lượng người cân; lớp điểm nhận thức tách
bạch, không quy đổi."* Phiên thùng không có ai cân, nên:

* ⛔ KHÔNG cộng vào ``users.green_points``.
* ⛔ KHÔNG ghi vào ``diem_thuong_log`` (bảng đó dành cho điểm có giá trị).
* ✅ Chỉ ghi vào ``phien_thung.diem_nhan_thuc``.

**Vì sao đếm được phép mà cân thì không:** thùng **đếm thật** từng vật đi qua —
đó là con số máy ghi nhận. Ước lượng khối lượng từ ảnh mới là đoán.

⚠️ Và phải nói rõ với người dùng: đếm là **"số vật đã phân loại"**, không phải
"số rác đã bỏ" — một túi 20 vỏ chai thùng vẫn tính là 1. Câu chữ trong thông báo
phải đúng như vậy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Bin, Notification, PhienThung, User
from src.services.hop_dong_thiet_bi import dung_phan_hoi

# --- Hằng số, khai TƯỜNG MINH ở đầu file — không rải số khắp nơi --------------

# Hạn của một phiên bỏ rác: 10 phút kể từ `bat_dau`.
THOI_GIAN_TOI_DA_GIAY = 10 * 60

# Mỗi vật được phân loại VÀ được chấp nhận = N điểm nhận thức. Không quy đổi,
# không cộng vào green_points — đây chỉ là con số khuyến khích thói quen.
DIEM_NHAN_THUC_MOI_VAT = 5

# Trạng thái phiên — khớp `PhienThung.trang_thai`.
DANG_MO = "dang_mo"
DA_DONG = "da_dong"
HET_HAN = "het_han"
LOI = "loi"

# Lý do đóng phiên (tham số `ly_do` của `dong_phien`) → câu thông báo người dùng đọc.
# Gộp chung thành "lỗi" là người dùng đứng ngơ ngác trước cái thùng.
_THONG_BAO_THEO_LY_DO: dict[str, tuple[str, str]] = {
    DA_DONG: (
        "Phiên bỏ rác đã kết thúc",
        "Bạn đã phân loại {so_vat} vật. Điểm nhận thức: {diem} — điểm nhận thức "
        "tách bạch, không đổi quà được.",
    ),
    HET_HAN: (
        "Phiên đã đóng vì quá thời gian",
        "Phiên đã đóng, quét lại mã để tiếp tục. Đã lưu {so_vat} vật phân loại "
        "(điểm nhận thức {diem}).",
    ),
    "mat_ket_noi": (
        "Thùng mất kết nối",
        "Thùng mất kết nối, phiên đã lưu phần đã bỏ. {so_vat} vật phân loại "
        "(điểm nhận thức {diem}).",
    ),
    "ngan_day": (
        "Ngăn thu gom đã đầy",
        "Ngăn đã đầy, đơn vị thu gom đã được báo. {so_vat} vật phân loại "
        "(điểm nhận thức {diem}).",
    ),
    "khong_nhan_dien": (
        "Chưa nhận ra vật",
        "Chưa nhận ra món này, thử đặt lại cho gọn trong khay. Đã lưu "
        "{so_vat} vật phân loại (điểm nhận thức {diem}).",
    ),
}


def mo_phien(session: Session, user: User, bin_code: str) -> PhienThung:
    """Mở một phiên bỏ rác cho ``user`` tại thùng ``bin_code``.

    Một thùng chỉ được có MỘT phiên ``dang_mo`` tại một thời điểm:

    * Đã có phiên của NGƯỜI KHÁC đang mở → từ chối (ValueError).
    * Đã có phiên của CHÍNH NGƯỜI ĐÓ đang mở → trả lại phiên cũ, không đẻ phiên
      thứ hai.
    * Chưa có phiên nào → tạo mới.

    Raises:
        ValueError: thùng không tồn tại, hoặc thùng đang có người khác sử dụng.
    """
    thung = session.scalar(select(Bin).where(Bin.code == bin_code))
    if thung is None:
        raise ValueError(f"Không tìm thấy thùng có mã '{bin_code}'.")

    phien = phien_dang_mo_cua_thung(session, thung.id)
    if phien is not None:
        if phien.user_id != user.id:
            raise ValueError("Thùng đang có người sử dụng — quét lại sau vài phút.")
        return phien

    phien = PhienThung(
        ma_phien=str(uuid4()),
        user_id=user.id,
        bin_id=thung.id,
        trang_thai=DANG_MO,
        so_vat=0,
        diem_nhan_thuc=0,
    )
    session.add(phien)
    session.flush()
    return phien


def phien_dang_mo_cua_thung(session: Session, bin_id: int) -> PhienThung | None:
    """Phiên còn hiệu lực của một thùng, hoặc ``None``.

    Quá 10 phút kể từ ``bat_dau`` thì **tự đánh dấu ``het_han``** (ghi ``ket_thuc``
    và lý do) rồi trả ``None`` — thùng được tự do mở phiên mới.
    """
    phien = session.scalar(
        select(PhienThung)
        .where(PhienThung.bin_id == bin_id, PhienThung.trang_thai == DANG_MO)
        .order_by(PhienThung.bat_dau.desc())
        .limit(1)
    )
    if phien is None:
        return None

    # Cột `DateTime` không kèm múi giờ nên giá trị đọc lại từ SQLite là naive
    # (ngầm hiểu UTC); chuẩn hoá cả hai vế về naive UTC trước khi trừ.
    bat_dau_naive = phien.bat_dau.replace(tzinfo=None) if phien.bat_dau.tzinfo else phien.bat_dau
    da_qua_han = (datetime.now(UTC).replace(tzinfo=None) - bat_dau_naive).total_seconds() > THOI_GIAN_TOI_DA_GIAY
    if da_qua_han:
        phien.trang_thai = HET_HAN
        phien.ket_thuc = datetime.now(UTC)
        phien.ghi_chu = "hết hạn sau 10 phút"
        session.flush()
        return None
    return phien


def ghi_nhan_vat(session: Session, phien: PhienThung, outcome) -> None:
    """Cộng ``so_vat`` khi vật được nhận diện VÀ được chấp nhận.

    Ca bị từ chối, ca ``UNKNOWN``, ca nguy hại cần người duyệt → **không cộng**.
    Đây là chốt chặn chống chụp bừa lấy điểm.

    Dùng ``dung_phan_hoi`` làm một nguồn sự thật: ``review_required == False``
    đúng khi và chỉ khi có nhãn, đủ tự tin, không nguy hại.
    """
    phan_hoi = dung_phan_hoi(outcome)
    if phan_hoi["review_required"]:
        return
    if phien.trang_thai != DANG_MO:
        return
    phien.so_vat += 1
    session.flush()


def dong_phien(session: Session, phien: PhienThung, ly_do: str = DA_DONG) -> PhienThung:
    """Chốt phiên: tính điểm nhận thức, đánh dấu đóng, sinh thông báo.

    ``ly_do`` là một trong các khoá của ``_THONG_BAO_THEO_LY_DO`` (mặc định
    ``da_dong``). Phiên đóng vì **hết hạn hoặc lỗi** mà đã có vật được chấp nhận →
    **vẫn cộng điểm cho phần đã bỏ** — không phạt người dùng vì thiết bị hỏng.

    Raises:
        ValueError: phiên đã đóng (trạng thái ``da_dong`` / ``loi``) hoặc không tồn tại.
    """
    if phien.trang_thai in {DA_DONG, LOI}:
        raise ValueError("Phiên này đã đóng rồi.")

    phien.diem_nhan_thuc = phien.so_vat * DIEM_NHAN_THUC_MOI_VAT
    phien.ket_thuc = datetime.now(UTC)
    if ly_do == HET_HAN:
        phien.trang_thai = HET_HAN
        phien.ghi_chu = "hết hạn sau 10 phút"
    elif ly_do == DA_DONG:
        phien.trang_thai = DA_DONG
        phien.ghi_chu = "cư dân bấm xong"
    else:
        phien.trang_thai = LOI
        phien.ghi_chu = ly_do
    session.flush()

    _thong_bao(session, phien, ly_do)
    return phien


def _thong_bao(session: Session, phien: PhienThung, ly_do: str) -> None:
    """Tạo bản ghi thông báo TRONG APP — gói này KHÔNG gửi thông báo đẩy.

    Đúng khuôn ``Notification`` mà ``src/services/pickup.py`` đang dùng. Nội dung
    nêu: số vật đã phân loại, điểm nhận thức, và nói rõ đó là điểm nhận thức
    không đổi quà được.
    """
    tieu_de, noi_dung = _THONG_BAO_THEO_LY_DO.get(ly_do, _THONG_BAO_THEO_LY_DO[DA_DONG])
    body = noi_dung.format(so_vat=phien.so_vat, diem=phien.diem_nhan_thuc)
    session.add(
        Notification(
            user_id=phien.user_id,
            title=tieu_de,
            body=body,
            entity="phien_thung",
            entity_id=phien.ma_phien,
        )
    )
    session.flush()
