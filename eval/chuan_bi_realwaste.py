"""Chép mẫu từ bộ RealWaste vào đúng khuôn thư mục mà ``eval/run_eval.py`` quét.

RealWaste đặt tên thư mục theo vật liệu ("Cardboard", "Food Organics"…), còn hệ
thống dùng mã nhóm rác trong CSDL ("recyclable_paper", "organic"…). Script này
làm đúng một việc: ánh xạ tên thư mục và chép một mẫu **có chọn lọc đều** sang
``data/eval/cong_khai/<mã nhóm>/``.

Chép mẫu chứ không chép hết: 4.752 ảnh là quá nhiều cho một lần đo, và
``data/`` nằm trong ``.gitignore`` nên phần chép ra không làm phình repo.

    python eval/chuan_bi_realwaste.py --liet-ke
    python eval/chuan_bi_realwaste.py --so-anh 20

⚠️ RealWaste **không có lớp rác nguy hại** — không pin, không bóng đèn, không
thiết bị điện tử. Bộ này đo được phần phân loại vật liệu thông thường và
KHÔNG đo được nhánh an toàn của hệ thống. Bộ ảnh tự chụp vẫn là bộ bắt buộc.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DUOI_ANH = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

#: Tên thư mục RealWaste → mã nhóm rác trong CSDL. Hai lớp gộp về một mã là có
#: chủ đích: hệ thống không phân biệt bìa với giấy, cũng không phân biệt rác
#: thực phẩm với rác vườn.
ANH_XA_LOP: dict[str, str] = {
    "Cardboard": "recyclable_paper",
    "Paper": "recyclable_paper",
    "Plastic": "recyclable_plastic",
    "Metal": "recyclable_metal",
    "Glass": "recyclable_glass",
    "Food Organics": "organic",
    "Vegetation": "organic",
    "Miscellaneous Trash": "other",
    "Textile Trash": "other",
}

NGUON_MAC_DINH = ROOT / "realwaste-main" / "RealWaste"
DICH_MAC_DINH = ROOT / "data" / "eval" / "cong_khai"


def _lay_mau_deu(tep: list[Path], so_anh: int) -> list[Path]:
    """Chọn ``so_anh`` ảnh rải đều trên cả thư mục, không phải ``so_anh`` ảnh đầu.

    Ảnh trong bộ thường xếp theo thứ tự chụp, nên lấy N ảnh đầu là lấy trọn một
    buổi chụp — cùng ánh sáng, cùng phông nền. Rải đều cho mẫu đa dạng hơn mà
    vẫn tất định: chạy lại luôn ra đúng bộ ảnh cũ.
    """
    if so_anh <= 0 or len(tep) <= so_anh:
        return tep
    buoc = len(tep) / so_anh
    return [tep[int(i * buoc)] for i in range(so_anh)]


def chuan_bi(nguon: Path, dich: Path, so_anh: int, xoa_truoc: bool, chi_liet_ke: bool) -> int:
    """Chép mẫu và in bảng tổng kết. Trả về mã thoát cho ``main``."""
    if not nguon.is_dir():
        print(f"Không thấy thư mục nguồn: {nguon}")
        return 1

    thieu = [ten for ten in ANH_XA_LOP if not (nguon / ten).is_dir()]
    thua = [p.name for p in sorted(nguon.iterdir()) if p.is_dir() and p.name not in ANH_XA_LOP]
    for ten in thieu:
        print(f"⚠️  thiếu thư mục '{ten}' trong bộ nguồn")
    for ten in thua:
        print(f"⚠️  thư mục '{ten}' không có trong bảng ánh xạ — đã bỏ qua")

    if xoa_truoc and dich.exists() and not chi_liet_ke:
        shutil.rmtree(dich)

    tong_nguon = 0
    tong_chep = 0
    print(f"\n{'LỚP REALWASTE':<24} {'MÃ NHÓM':<20} {'CÓ':>6} {'LẤY':>6}")
    print("-" * 60)
    for ten_lop, ma_nhom in ANH_XA_LOP.items():
        thu_muc = nguon / ten_lop
        if not thu_muc.is_dir():
            continue
        tep = sorted(p for p in thu_muc.iterdir() if p.suffix.lower() in DUOI_ANH)
        chon = _lay_mau_deu(tep, so_anh)
        tong_nguon += len(tep)
        tong_chep += len(chon)
        print(f"{ten_lop:<24} {ma_nhom:<20} {len(tep):>6} {len(chon):>6}")

        if chi_liet_ke:
            continue
        thu_muc_dich = dich / ma_nhom
        thu_muc_dich.mkdir(parents=True, exist_ok=True)
        for p in chon:
            # Giữ tên lớp gốc trong tên tệp: hai lớp gộp về một mã nên tên có
            # thể trùng, và khi soi failure case còn biết ảnh đến từ đâu.
            shutil.copy2(p, thu_muc_dich / f"{ten_lop.replace(' ', '_')}__{p.name}")

    print("-" * 60)
    print(f"{'TỔNG':<45} {tong_nguon:>6} {tong_chep:>6}")
    if chi_liet_ke:
        print("\n(chỉ liệt kê — chưa chép tệp nào)")
    else:
        print(f"\nĐã chép vào: {dich}")
        print("Chạy tiếp:  python eval/run_eval.py --bo cong_khai --liet-ke")
    return 0


def main() -> int:
    # Console Windows mặc định là cp1252, không in được tiếng Việt — đổi sang
    # UTF-8 như scripts/seed.py đang làm, nếu không bảng tổng kết nổ ở dòng đầu.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Dựng bộ ảnh eval công khai từ RealWaste")
    parser.add_argument("--nguon", type=Path, default=NGUON_MAC_DINH, help="thư mục RealWaste")
    parser.add_argument("--dich", type=Path, default=DICH_MAC_DINH, help="thư mục đích")
    parser.add_argument("--so-anh", type=int, default=20, help="số ảnh lấy mỗi lớp (mặc định 20)")
    parser.add_argument("--xoa-truoc", action="store_true", help="xoá thư mục đích trước khi chép")
    parser.add_argument("--liet-ke", action="store_true", help="chỉ đếm, không chép tệp nào")
    tham_so = parser.parse_args()
    return chuan_bi(tham_so.nguon, tham_so.dich, tham_so.so_anh, tham_so.xoa_truoc, tham_so.liet_ke)


if __name__ == "__main__":
    raise SystemExit(main())
