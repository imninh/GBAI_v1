"""Điểm nhận thức — tầng thứ hai của hệ điểm, tách bạch khỏi điểm có giá trị (P79).

## ⛔ Luật cứng nhất của dự án

*"Điểm có giá trị chỉ tính trên khối lượng do NGƯỜI CÂN."* Từ đó hệ thống có hai
tầng điểm tách hẳn nhau:

| | Điểm xanh (đã có) | Điểm nhận thức (module này) |
|---|---|---|
| Nguồn | thu gom thật, có cân | chụp ảnh trên app · phiên bỏ rác · nhiệm vụ |
| Ghi vào | cột tổng điểm xanh trên ``users`` + sổ cái điểm thưởng | ``diem_nhan_thuc_log`` |
| Đổi được quà? | Có | **KHÔNG BAO GIỜ** |
| Dùng để | đổi quà, đổi dịch vụ | xếp hạng, huy hiệu, khuyến khích |

Module này **chỉ chạm ``diem_nhan_thuc_log``** và hai bảng nhiệm vụ (P76). Tuyệt
đối không đọc, không ghi cột tổng điểm xanh trên ``users``, không tạo dòng sổ cái
điểm thưởng, không viết hàm quy đổi nào giữa hai loại điểm — vi phạm là đỏ ngay.

Tổng điểm nhận thức của một người tính bằng ``SUM`` trên sổ cái; không có cột tổng.

## Các nguồn điểm trong sổ cái

``chup_anh`` (ảnh phân loại, có trần mỗi ngày) · ``phien_thung`` (phiên bỏ rác tại
thùng, giữ nguyên cách tính ở :mod:`src.services.phien_thung`) · ``nhiem_vu_ngay``
· ``nhiem_vu_tuan`` (nhiệm vụ).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models import (
    Classification,
    DiemNhanThucLog,
    NhiemVu,
    NhiemVuHoanThanh,
    PhienThung,
    PickupRequest,
    User,
)
from src.services.pickup_lifecycle import HOAN_TAT, chuan_hoa

# --- Hằng số, khai TƯỜNG MINH ở đầu file — không rải số khắp nơi --------------

# Chụp ảnh phân loại trên app: 2 điểm/ảnh. Số người duyệt chốt ngày 21/08, chưa
# dựa trên khảo sát — đúng cách dự án đã làm với `DIEM_NHAN_THUC_MOI_VAT`.
DIEM_CHUP_ANH = 2

# Trần MỖI NGÀY cho nguồn chụp ảnh: 10 điểm/ngày (tối đa 5 ảnh). Số người duyệt
# chốt ngày 21/08, chưa dựa trên khảo sát. Trần CHỈ áp cho `chup_anh` — phiên
# thùng và nhiệm vụ không bị trần.
TRAN_CHUP_ANH_MOI_NGAY = 10

# Nhiệm vụ NGÀY — phân loại 3 món: +5 điểm. Số người duyệt chốt ngày 21/08, chưa
# dựa trên khảo sát.
DIEM_NHIEM_VU_NGAY_PHAN_LOAI_3_MON = 5

# Nhiệm vụ TUẦN — 5 ngày có hoạt động: +30 điểm. Số người duyệt chốt ngày 21/08,
# chưa dựa trên khảo sát.
DIEM_NHIEM_VU_TUAN_5_NGAY = 30

# Nhiệm vụ TUẦN — hoàn tất 1 yêu cầu thu gom: +50 điểm.
# Con số 50 do người soạn gói trước tự đặt (chưa dựa trên khảo sát). Người
# duyệt đã xem lại và đồng ý giữ nguyên ngày 22/08, nhưng phải chốt lại
# trước khi có người dùng thật.
DIEM_NHIEM_VU_TUAN_1_YEU_CAU = 50

# --- Giá trị nguồn trong `diem_nhan_thuc_log` (khớp chú thích model P76) ------

NGUON_CHUP_ANH = "chup_anh"
NGUON_PHIEN_THUNG = "phien_thung"
NGUON_NHIEM_VU_NGAY = "nhiem_vu_ngay"
NGUON_NHIEM_VU_TUAN = "nhiem_vu_tuan"

# --- Ba mã điều kiện nhiệm vụ — cài ĐÚNG ba mã, không thêm -------------------

DIEU_KIEN_SO_LAN_PHAN_LOAI = "so_lan_phan_loai_trong_ngay"
DIEU_KIEN_SO_NGAY_HOAT_DONG = "so_ngay_hoat_dong_trong_tuan"
DIEU_KIEN_SO_YEU_CAU_HOAN_TAT = "so_yeu_cau_hoan_tat_trong_tuan"

# Dữ liệu nhiệm vụ ban đầu — nạp bằng hàm THÊM-NẾU-THIẾU (`bao_dam_nhiem_vu_co_san`).
# Cột thứ tự: ma, ten, chu_ky, dieu_kien_ma, dieu_kien_nguong, diem, mo_ta.
_NHIEM_VU_MAC_DINH: list[tuple[str, str, str, str, int, int, str]] = [
    (
        "NGAY_PHAN_LOAI_3_MON",
        "Phân loại 3 món trong ngày",
        "ngay",
        DIEU_KIEN_SO_LAN_PHAN_LOAI,
        3,
        DIEM_NHIEM_VU_NGAY_PHAN_LOAI_3_MON,
        "Chụp ảnh hoặc mô tả 3 món rác được phân loại thành công trong một ngày.",
    ),
    (
        "TUAN_5_NGAY_HOAT_DONG",
        "Có hoạt động 5 ngày trong tuần",
        "tuan",
        DIEU_KIEN_SO_NGAY_HOAT_DONG,
        5,
        DIEM_NHIEM_VU_TUAN_5_NGAY,
        "Phân loại hoặc bỏ rác tại thùng ít nhất 5 ngày khác nhau trong tuần.",
    ),
    (
        "TUAN_HOAN_TAT_1_YEU_CAU",
        "Hoàn tất 1 yêu cầu thu gom trong tuần",
        "tuan",
        DIEU_KIEN_SO_YEU_CAU_HOAN_TAT,
        1,
        DIEM_NHIEM_VU_TUAN_1_YEU_CAU,
        "Hoàn tất ít nhất 1 yêu cầu thu gom trong tuần.",
    ),
]


def ghi_diem_chup_anh(session: Session, *, user: User, classification_id: int, ngay: date) -> dict:
    """Ghi điểm nhận thức cho một ảnh phân loại thành công, áp trần mỗi ngày.

    Trần §3: trước khi ghi, ``SUM(diem)`` trên ``diem_nhan_thuc_log`` với
    ``user_id`` + ``nguon == "chup_anh"`` + ``ngay == <ngày đang xét>``.

    * Đã đủ trần → **không ghi dòng nào**, trả 0 điểm kèm lý do.
    * Còn ít hơn 2 điểm dưới trần → ghi **đúng phần còn lại**, không vượt trần.

    ``ngay`` là **tham số truyền vào** — KHÔNG gọi ``date.today()`` bên trong, để
    test được trần theo từng ngày.

    Returns:
        ``{"diem_da_ghi", "diem_con_lai_hom_nay", "ly_do"}``. ``ly_do`` rỗng khi
        ghi được.
    """
    tong_da_ghi = int(
        session.scalar(
            select(func.coalesce(func.sum(DiemNhanThucLog.diem), 0)).where(
                DiemNhanThucLog.user_id == user.id,
                DiemNhanThucLog.nguon == NGUON_CHUP_ANH,
                DiemNhanThucLog.ngay == ngay,
            )
        )
        or 0
    )
    con_lai = TRAN_CHUP_ANH_MOI_NGAY - tong_da_ghi
    if con_lai <= 0:
        return {
            "diem_da_ghi": 0,
            "diem_con_lai_hom_nay": 0,
            "ly_do": "Đã đạt trần điểm chụp ảnh hôm nay.",
        }
    diem_ghi = min(DIEM_CHUP_ANH, con_lai)
    session.add(
        DiemNhanThucLog(
            user_id=user.id,
            nguon=NGUON_CHUP_ANH,
            diem=diem_ghi,
            ref_bang="classifications",
            ref_id=classification_id,
            ngay=ngay,
            ghi_chu=f"Chụp ảnh phân loại #{classification_id}",
        )
    )
    session.flush()
    return {
        "diem_da_ghi": diem_ghi,
        "diem_con_lai_hom_nay": con_lai - diem_ghi,
        "ly_do": "",
    }


def tong_diem_nhan_thuc(session: Session, *, user_id: int) -> int:
    """Tổng điểm nhận thức của một người — ``SUM`` trên sổ cái.

    ⛔ Không đọc, không ghi cột tổng điểm xanh trên ``users``. Cột tổng là dữ
    liệu nhân bản, sẽ lệch — đã chốt, đừng đề xuất lại.
    """
    return int(
        session.scalar(
            select(func.coalesce(func.sum(DiemNhanThucLog.diem), 0)).where(
                DiemNhanThucLog.user_id == user_id
            )
        )
        or 0
    )


def bao_dam_nhiem_vu_co_san(session: Session) -> None:
    """Nạp danh mục nhiệm vụ nếu chưa có — dò theo ``ma``, gọi nhiều lần vô hại.

    ⛔ Không đụng ``src/db/seed_data.py`` (gói P78 đang giữ) — dữ liệu nhiệm vụ
    nằm trong chính module này.
    """
    for ma, ten, chu_ky, dieu_kien_ma, nguong, diem, mo_ta in _NHIEM_VU_MAC_DINH:
        da_co = session.scalar(select(NhiemVu.id).where(NhiemVu.ma == ma))
        if da_co is not None:
            continue
        session.add(
            NhiemVu(
                ma=ma,
                ten=ten,
                mo_ta=mo_ta,
                chu_ky=chu_ky,
                dieu_kien_ma=dieu_kien_ma,
                dieu_kien_nguong=nguong,
                diem=diem,
            )
        )
    session.flush()


def kiem_va_trao_nhiem_vu(session: Session, *, user: User, ngay: date) -> list[dict]:
    """Kiểm từng nhiệm vụ đang bật, đủ điều kiện thì trao điểm.

    Với mỗi ``nhiem_vu`` đang bật: kiểm điều kiện, đủ thì ghi ``nhiem_vu_hoan_thanh``
    + một dòng ``diem_nhan_thuc_log``.

    * Kỳ của nhiệm vụ ngày = ``YYYY-MM-DD``; kỳ nhiệm vụ tuần = ``YYYY-Www`` (ISO).
    * **Chống trao hai lần**: kiểm ``(user_id, nhiem_vu_id, ky)`` TRƯỚC khi ghi,
      trả thông báo tử tế; ràng buộc duy nhất (P76) là lớp chặn cuối. Bắt
      ``IntegrityError`` phòng hai lời gọi cùng lúc — bắt được thì coi như đã trao,
      không ghi điểm lần hai (dùng savepoint để không mất giao dịch đang dở).

    Returns:
        Danh sách nhiệm vụ vừa hoàn thành trong lần gọi này.
    """
    bao_dam_nhiem_vu_co_san(session)
    da_xong: list[dict] = []
    cac_nhiem_vu = session.scalars(select(NhiemVu).where(NhiemVu.is_active.is_(True))).all()
    for nv in cac_nhiem_vu:
        ky = _ky_cua(nv, ngay)
        da_nhan = (
            session.scalar(
                select(NhiemVuHoanThanh.id).where(
                    NhiemVuHoanThanh.user_id == user.id,
                    NhiemVuHoanThanh.nhiem_vu_id == nv.id,
                    NhiemVuHoanThanh.ky == ky,
                )
            )
            is not None
        )
        if da_nhan:
            continue
        tien_do = _tien_do_nhiem_vu(session, user.id, nv, ngay)
        if tien_do < nv.dieu_kien_nguong:
            continue
        if _trao_mot_nhiem_vu(session, user, nv, ky, ngay):
            da_xong.append(
                {
                    "ma": nv.ma,
                    "ten": nv.ten,
                    "diem": nv.diem,
                    "ky": ky,
                    "tien_do": tien_do,
                }
            )
    return da_xong


def danh_sach_nhiem_vu(session: Session, *, user: User, ngay: date) -> list[dict]:
    """Danh sách nhiệm vụ đang bật kèm tiến độ hiện tại và đã nhận hay chưa."""
    bao_dam_nhiem_vu_co_san(session)
    ds: list[dict] = []
    cac_nhiem_vu = session.scalars(select(NhiemVu).where(NhiemVu.is_active.is_(True))).all()
    for nv in cac_nhiem_vu:
        ky = _ky_cua(nv, ngay)
        tien_do = _tien_do_nhiem_vu(session, user.id, nv, ngay)
        da_nhan = (
            session.scalar(
                select(NhiemVuHoanThanh.id).where(
                    NhiemVuHoanThanh.user_id == user.id,
                    NhiemVuHoanThanh.nhiem_vu_id == nv.id,
                    NhiemVuHoanThanh.ky == ky,
                )
            )
            is not None
        )
        ds.append(
            {
                "ma": nv.ma,
                "ten": nv.ten,
                "mo_ta": nv.mo_ta,
                "chu_ky": nv.chu_ky,
                "dieu_kien_ma": nv.dieu_kien_ma,
                "dieu_kien_nguong": nv.dieu_kien_nguong,
                "diem": nv.diem,
                "tien_do": tien_do,
                "da_nhan": da_nhan,
            }
        )
    return ds


# --- Trợ giúp nội bộ ---------------------------------------------------------


def _ky_cua(nv: NhiemVu, ngay: date) -> str:
    """Kỳ của nhiệm vụ: ``YYYY-MM-DD`` (ngày) hoặc ``YYYY-Www`` ISO (tuần)."""
    if nv.chu_ky == "tuan":
        iso = ngay.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return ngay.isoformat()


def _tien_do_nhiem_vu(session: Session, user_id: int, nv: NhiemVu, ngay: date) -> int:
    """Tiến độ hiện tại theo ``dieu_kien_ma`` — cài đúng ba mã, không thêm."""
    if nv.dieu_kien_ma == DIEU_KIEN_SO_LAN_PHAN_LOAI:
        return _dem_so_lan_phan_loai_trong_ngay(session, user_id, ngay)
    if nv.dieu_kien_ma == DIEU_KIEN_SO_NGAY_HOAT_DONG:
        return _dem_so_ngay_hoat_dong_trong_tuan(session, user_id, ngay)
    if nv.dieu_kien_ma == DIEU_KIEN_SO_YEU_CAU_HOAN_TAT:
        return _dem_so_yeu_cau_hoan_tat_trong_tuan(session, user_id, ngay)
    return 0


def _trao_mot_nhiem_vu(session: Session, user: User, nv: NhiemVu, ky: str, ngay: date) -> bool:
    """Ghi ``nhiem_vu_hoan_thanh`` + một dòng điểm nhận thức. Trả ``True`` nếu trao.

    Dùng ``begin_nested`` (SAVEPOINT) để bắt ``IntegrityError`` mà không rollback
    toàn bộ giao dịch đang dở (ví dụ bản ghi ``Classification`` vừa ghi trong cùng
    request chưa commit).
    """
    try:
        with session.begin_nested():
            session.add(
                NhiemVuHoanThanh(
                    user_id=user.id,
                    nhiem_vu_id=nv.id,
                    ky=ky,
                    diem_da_trao=nv.diem,
                )
            )
            session.flush()
    except IntegrityError:
        # Hai lời gọi cùng lúc — ràng buộc duy nhất (user_id, nhiem_vu_id, ky) chặn
        # dòng thứ hai; coi như đã trao, không ghi điểm lần hai.
        return False
    session.add(
        DiemNhanThucLog(
            user_id=user.id,
            nguon=NGUON_NHIEM_VU_NGAY if nv.chu_ky == "ngay" else NGUON_NHIEM_VU_TUAN,
            diem=nv.diem,
            ref_bang="nhiem_vu",
            ref_id=nv.id,
            ngay=ngay,
            ghi_chu=nv.ten,
        )
    )
    session.flush()
    return True


def _dem_so_lan_phan_loai_trong_ngay(session: Session, user_id: int, ngay: date) -> int:
    """Số ``Classification`` của người đó có ``created_at`` trong ``ngay``."""
    dau, cuoi = _pham_vi_ngay(ngay)
    return int(
        session.scalar(
            select(func.count(Classification.id)).where(
                Classification.asker_id == user_id,
                Classification.created_at >= dau,
                Classification.created_at < cuoi,
            )
        )
        or 0
    )


def _dem_so_ngay_hoat_dong_trong_tuan(session: Session, user_id: int, ngay: date) -> int:
    """Số ngày KHÁC NHAU có ít nhất một hoạt động trong tuần ISO của ``ngay``.

    Hoạt động = một ``Classification`` (phân loại) hoặc một ``PhienThung``
    (phiên bỏ rác tại thùng) của người đó trong khoảng tuần.
    """
    dau, cuoi = _pham_vi_tuan(ngay)
    cac_ngay: set[date] = set()
    moc_phan_loai = session.scalars(
        select(Classification.created_at).where(
            Classification.asker_id == user_id,
            Classification.created_at >= dau,
            Classification.created_at < cuoi,
        )
    ).all()
    for moc in moc_phan_loai:
        cac_ngay.add(moc.date() if isinstance(moc, datetime) else moc)
    moc_phien = session.scalars(
        select(PhienThung.bat_dau).where(
            PhienThung.user_id == user_id,
            PhienThung.bat_dau >= dau,
            PhienThung.bat_dau < cuoi,
        )
    ).all()
    for moc in moc_phien:
        cac_ngay.add(moc.date() if isinstance(moc, datetime) else moc)
    return len(cac_ngay)


def _dem_so_yeu_cau_hoan_tat_trong_tuan(session: Session, user_id: int, ngay: date) -> int:
    """Số ``PickupRequest`` của người đó đã HOÀN TẤT trong tuần ISO của ``ngay``."""
    dau, cuoi = _pham_vi_tuan(ngay)
    cac_yeu_cau = session.scalars(
        select(PickupRequest).where(
            PickupRequest.resident_id == user_id,
            PickupRequest.created_at >= dau,
            PickupRequest.created_at < cuoi,
        )
    ).all()
    return sum(1 for yc in cac_yeu_cau if chuan_hoa(yc.status) == HOAN_TAT)


def _pham_vi_ngay(ngay: date) -> tuple[datetime, datetime]:
    """Khoảng ``[00:00 ngay, 00:00 hôm sau)`` — so sánh với cột DateTime naive UTC."""
    dau = _dau_ngay(ngay)
    return dau, dau + timedelta(days=1)


def _pham_vi_tuan(ngay: date) -> tuple[datetime, datetime]:
    """Khoảng ``[thứ Hai 00:00, thứ Hai tuần sau 00:00)`` — tuần ISO của ``ngay``."""
    thu_hai = ngay - timedelta(days=ngay.weekday())
    dau = _dau_ngay(thu_hai)
    return dau, dau + timedelta(days=7)


def _dau_ngay(ngay: date) -> datetime:
    return datetime(ngay.year, ngay.month, ngay.day)
