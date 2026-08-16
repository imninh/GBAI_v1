"""Đo đường chim bay lệch bao nhiêu so với đường đi thật — chạy tay, cần mạng.

Script trả lời đúng một câu hỏi: **xếp thứ tự ghé bằng đường chim bay thì đi
thật tốn thêm bao nhiêu phần trăm so với xếp bằng đường đi thật?**

Cách đo duy nhất có nghĩa: xếp hai thứ tự (một bằng đường chim bay, một bằng
đường đi thật) rồi chấm **cả hai bằng CÙNG MỘT thước — đường đi thật**, vì xe
chạy trên đường thật dù ta xếp thứ tự bằng gì. Kèm theo là hệ số vòng vèo trung
bình (đường thật / đường chim bay) — con số trả lời "đường chim bay lệch bao
nhiêu so với thực tế ở Hà Nội".

Chạy:

    python eval/do_duong_di_that.py --bat-co
    python eval/do_duong_di_that.py --db-url "sqlite:///data/app.db" --bat-co

Script này **không bao giờ nằm trong pytest**: nó gọi dịch vụ định tuyến thật.
Test cho phép tính nằm ở chỗ khác, chạy bằng ma trận giả.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.config import get_settings, reset_settings_cache  # noqa: E402
from src.db.models import Bin  # noqa: E402
from src.db.session import _them_sslmode, normalize_database_url  # noqa: E402
from src.services import duong_di_that  # noqa: E402
from src.services.route_planner import haversine_km  # noqa: E402
from src.services.toi_uu_tuyen import do_dai, sap_thu_tu  # noqa: E402

THU_MUC_KET_QUA = ROOT / "eval" / "results"

# Bộ điểm cố định dùng khi CSDL trống hoặc không mở được — quanh Hà Nội.
DIEM_MAC_DINH: list[tuple[float, float]] = [
    (21.0285, 105.8542),  # Hồ Gươm
    (21.0245, 105.8417),  # Hàng Bông
    (21.0405, 105.7898),  # Xuân La
    (21.0136, 105.8058),  # Mỹ Đình
    (20.9984, 105.8262),  # Ngã Tư Sở
    (20.9906, 105.8311),  # Văn Quán
    (21.0017, 105.7980),  # Cầu Giấy
]


def _ham_do_chim_bay(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Khoảng cách đường chim bay giữa hai toạ độ ``(lat, lng)``."""
    return haversine_km(a[0], a[1], b[0], b[1])


def _ham_do_tu_ma_tran(
    toa_do: list[tuple[float, float]], ma_tran: list[list[float]]
):
    """Hàm đo khoảng cách tra bảng ma trận đường đi thật, đúng khuôn ``sap_thu_tu`` cần."""

    chi_so = {toa_do[i]: i for i in range(len(toa_do))}

    def _do(a: tuple[float, float], b: tuple[float, float]) -> float:
        i = chi_so.get(a)
        j = chi_so.get(b)
        if i is None or j is None:
            return _ham_do_chim_bay(a, b)
        return ma_tran[i][j]

    return _do


def do_mot_bo(
    toa_do: list[tuple[float, float]], ma_tran: list[list[float]]
) -> dict[str, float]:
    """Đo một bộ điểm: hai thứ tự ghé, chấm CẢ HAI bằng thước đường đi thật.

    ``thu_tu_chim`` xếp bằng đường chim bay (hành vi mặc định của sản phẩm khi
    chưa bật cờ), ``thu_tu_that`` xếp bằng đường đi thật. Cả hai đều được đo
    bằng ma trận đường thật — nếu không, con số chỉ nói lại "đường thật dài hơn
    đường chim bay" chứ không nói gì về chất lượng của thứ tự ghé.
    """
    ham_chim = _ham_do_chim_bay
    ham_that = _ham_do_tu_ma_tran(toa_do, ma_tran)

    thu_tu_chim = sap_thu_tu(toa_do, ham_chim)
    thu_tu_that = sap_thu_tu(toa_do, ham_that)

    km_xep_chim = do_dai(thu_tu_chim, ham_that)
    km_xep_that = do_dai(thu_tu_that, ham_that)
    km_chim_bay = do_dai(thu_tu_chim, ham_chim)

    chenh_km = km_xep_chim - km_xep_that
    chenh_pt = chenh_km / km_xep_that * 100 if km_xep_that > 0 else 0.0
    he_so_vong_veo = km_xep_chim / km_chim_bay if km_chim_bay > 0 else 0.0
    return {
        "so_diem": float(len(toa_do)),
        "km_xep_chim_roi_di_that": km_xep_chim,
        "km_xep_that_roi_di_that": km_xep_that,
        "chenh_km": chenh_km,
        "chenh_pt": chenh_pt,
        "he_so_vong_veo": he_so_vong_veo,
    }


def _lay_toa_do_tu_csdl(db_url: str) -> list[tuple[float, float]] | None:
    """Toạ độ các thùng đang hoạt động; ``None`` khi không mở được CSDL."""
    try:
        if db_url:
            engine = create_engine(_them_sslmode(normalize_database_url(db_url)), future=True)
        else:
            from src.db.session import get_engine

            engine = get_engine()
        with sessionmaker(bind=engine)() as phien:
            cac_thung = phien.scalars(select(Bin).where(Bin.is_active.is_(True))).all()
        return [(t.lat, t.lng) for t in cac_thung if t.lat is not None and t.lng is not None]
    except Exception as loi:
        print(f"Không mở được CSDL ({type(loi).__name__}: {loi}).")
        return None


def _in_bang(ket_qua: dict[str, float]) -> None:
    print(f"\nPhép đo với {ket_qua['so_diem']:.0f} điểm dừng, đơn vị ki-lô-mét:")
    print(f"  Xếp bằng đường chim bay, rồi ĐI THẬT:   {ket_qua['km_xep_chim_roi_di_that']:8.3f}")
    print(f"  Xếp bằng đường đi thật, rồi ĐI THẬT:     {ket_qua['km_xep_that_roi_di_that']:8.3f}")
    print(f"  Chênh lệch:                              {ket_qua['chenh_km']:+8.3f} km ({ket_qua['chenh_pt']:+.2f}%)")
    print(f"  Hệ số vòng vèo trung bình (thật / chim bay): {ket_qua['he_so_vong_veo']:.3f}")


def _ghi_bao_cao(ket_qua: dict[str, float], nguon_toa_do: str, dich_vu: str) -> Path:
    THU_MUC_KET_QUA.mkdir(parents=True, exist_ok=True)
    duong = THU_MUC_KET_QUA / "duong_di_that.md"
    noi_dung = f"""# Đo chênh lệch đường chim bay so với đường đi thật

- **Ngày đo:** {datetime.now(UTC).strftime("%d/%m/%Y %H:%M UTC")}
- **Số điểm:** {ket_qua['so_diem']:.0f}
- **Nguồn toạ độ:** {nguon_toa_do}
- **Dịch vụ:** {dich_vu}

| Cách xếp thứ tự ghé | Tổng km khi đi thật |
|---|---|
| Đường chim bay (mặc định của sản phẩm) | {ket_qua['km_xep_chim_roi_di_that']:.3f} |
| Đường đi thật (OSRM) | {ket_qua['km_xep_that_roi_di_that']:.3f} |

- Chênh lệch: {ket_qua['chenh_km']:+.3f} km ({ket_qua['chenh_pt']:+.2f}%)
- Hệ số vòng vèo trung bình (đường thật / đường chim bay): {ket_qua['he_so_vong_veo']:.3f}

Cả hai thứ tự ghé đều được chấm bằng CÙNG một thước — đường đi thật — vì xe chạy
trên đường thật dù ta xếp thứ tự bằng gì. Con số chênh lệch là chi phí phải trả
khi xếp thứ tự theo đường chim bay.
"""
    duong.write_text(noi_dung, encoding="utf-8")
    return duong


def main() -> int:
    # PHẢI đứng trước `ArgumentParser`: `--help` in mô tả tiếng Việt rồi thoát
    # ngay trong `parse_args()`, đặt sau là quá muộn — console Windows mã cp1252
    # sẽ nổ `UnicodeEncodeError` trước khi dòng chỉnh mã kịp chạy (gói P5).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Đo đường chim bay lệch bao nhiêu so với đường đi thật — chạy tay, cần mạng"
    )
    parser.add_argument("--db-url", default="", help="DSN cần dùng. Bỏ trống thì dùng DATABASE_URL của ứng dụng.")
    parser.add_argument(
        "--bat-co",
        action="store_true",
        help="tạm bật ROUTE_REAL_DISTANCE=true cho lần chạy này, không sửa .env",
    )
    args = parser.parse_args()

    if args.bat_co:
        os.environ["ROUTE_REAL_DISTANCE"] = "true"
        reset_settings_cache()

    toa_do = _lay_toa_do_tu_csdl(args.db_url)
    nguon_toa_do = "CSDL (thùng đang hoạt động)"
    if not toa_do:
        toa_do = DIEM_MAC_DINH
        nguon_toa_do = f"bộ điểm cố định ({len(DIEM_MAC_DINH)} điểm quanh Hà Nội)"
        print(f"⚠ Không có toạ độ thật từ CSDL — dùng {nguon_toa_do}.")

    ma_tran = duong_di_that.ma_tran_km(toa_do)
    if ma_tran is None:
        print(
            "\nKhông lấy được ma trận đường đi thật — ROUTE_REAL_DISTANCE chưa bật"
            " (thêm --bat-co hoặc đặt trong .env), hoặc OSRM không trả lời (mạng hỏng).\n"
            "Không in bảng số rỗng, không bịa số. Sửa xong rồi chạy lại."
        )
        return 1

    ket_qua = do_mot_bo(toa_do, ma_tran)
    _in_bang(ket_qua)

    dich_vu = get_settings().osrm_base_url
    duong = _ghi_bao_cao(ket_qua, nguon_toa_do, dich_vu)
    print(f"\nĐã ghi báo cáo: {duong.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
