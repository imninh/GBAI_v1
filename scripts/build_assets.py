"""Xử lý ảnh linh vật và sinh bộ icon app.

Ba file gốc ở ``assets/`` là ảnh 1536×1024 nền trong suốt, mỗi file ~2,3 MB —
quá nặng để nhúng thẳng vào giao diện. Script này:

1. cắt bỏ phần trong suốt thừa quanh linh vật (bounding box của kênh alpha);
2. xuất WebP ở ba bề rộng cho màn hình thường / màn hình nét cao;
3. sinh bộ icon PWA và icon Android từ tư thế chính.

Chạy một lần sau khi đổi ảnh gốc::

    python scripts/build_assets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NGUON = ROOT / "assets"
DICH_MASCOT = ROOT / "frontend" / "public" / "mascot"
DICH_ICON = ROOT / "frontend" / "public" / "icons"

# Ba tư thế và tên dùng trong code giao diện.
TU_THE = {
    "GBAI_Mascot.png": "mascot",  # onboarding
    "GBAI_Hello.png": "hello",  # màn Hỏi
    "GBAI_KínhLup.png": "magnify",  # màn đang xử lý
}

BE_RONG = (240, 360, 512)

# Icon PWA: 192 và 512 là hai cỡ trình duyệt yêu cầu; bản maskable cần vùng an
# toàn vì Android cắt icon theo hình tròn hoặc bo góc tuỳ máy.
CO_ICON = (192, 512)
VUNG_AN_TOAN_MASKABLE = 0.72  # linh vật chiếm 72% cạnh, còn lại là lề


# Ảnh gốc có một lớp alpha rất mờ (giá trị 1–24) phủ gần kín khung. Nếu lấy
# bounding box theo alpha > 0 thì không cắt được gì, và lớp mờ đó còn hiện thành
# vệt xám khi đặt lên nền màu. Bỏ hẳn mọi pixel dưới ngưỡng này.
NGUONG_ALPHA = 24


def _lam_sach_alpha(image: Image.Image) -> Image.Image:
    """Đưa các pixel gần như trong suốt về trong suốt hoàn toàn."""
    alpha = image.getchannel("A").point(lambda v: 0 if v <= NGUONG_ALPHA else v)
    image.putalpha(alpha)
    return image


def _cat_theo_alpha(image: Image.Image, dem: int = 8) -> Image.Image:
    """Cắt ảnh về đúng phần nhìn thấy được, chừa lại vài pixel đệm."""
    image = _lam_sach_alpha(image)
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        return image
    left, top, right, bottom = bbox
    return image.crop(
        (
            max(0, left - dem),
            max(0, top - dem),
            min(image.width, right + dem),
            min(image.height, bottom + dem),
        )
    )


def _thu_nho(image: Image.Image, be_rong: int) -> Image.Image:
    ty_le = be_rong / image.width
    return image.resize((be_rong, max(1, round(image.height * ty_le))), Image.LANCZOS)


def xuat_mascot() -> list[str]:
    """Xuất ảnh linh vật dạng WebP. Trả về danh sách file đã ghi."""
    DICH_MASCOT.mkdir(parents=True, exist_ok=True)
    da_ghi: list[str] = []

    for ten_file, ten_tu_the in TU_THE.items():
        duong_dan = NGUON / ten_file
        if not duong_dan.exists():
            print(f"  ⚠ thiếu {duong_dan.name}, bỏ qua")
            continue

        goc = _cat_theo_alpha(Image.open(duong_dan).convert("RGBA"))
        for be_rong in BE_RONG:
            dich = DICH_MASCOT / f"{ten_tu_the}-{be_rong}.webp"
            _thu_nho(goc, be_rong).save(dich, format="WEBP", quality=88, method=6)
            da_ghi.append(dich.name)
            print(f"  {dich.name}: {dich.stat().st_size // 1024} KB")
    return da_ghi


def xuat_icon() -> list[str]:
    """Sinh icon PWA / Android từ tư thế chính."""
    DICH_ICON.mkdir(parents=True, exist_ok=True)
    goc_path = NGUON / "GBAI_Mascot.png"
    if not goc_path.exists():
        print("  ⚠ không có GBAI_Mascot.png, bỏ qua phần icon")
        return []

    goc = _cat_theo_alpha(Image.open(goc_path).convert("RGBA"), dem=0)
    da_ghi: list[str] = []

    for canh in CO_ICON:
        # Icon thường: nền màu thương hiệu, linh vật vừa khít khung.
        thuong = _dat_vao_khung(goc, canh, ty_le_noi_dung=0.86)
        ten = f"icon-{canh}.png"
        thuong.save(DICH_ICON / ten, format="PNG")
        da_ghi.append(ten)

        # Icon maskable: linh vật nhỏ hơn để máy nào cắt kiểu gì cũng không cụt.
        maskable = _dat_vao_khung(goc, canh, ty_le_noi_dung=VUNG_AN_TOAN_MASKABLE)
        ten_mask = f"icon-maskable-{canh}.png"
        maskable.save(DICH_ICON / ten_mask, format="PNG")
        da_ghi.append(ten_mask)

    apple = _dat_vao_khung(goc, 180, ty_le_noi_dung=0.82)
    apple.save(DICH_ICON / "apple-touch-icon.png", format="PNG")
    da_ghi.append("apple-touch-icon.png")

    favicon = _dat_vao_khung(goc, 32, ty_le_noi_dung=0.9)
    favicon.save(ROOT / "frontend" / "public" / "favicon.ico", format="ICO", sizes=[(32, 32)])
    da_ghi.append("favicon.ico")

    for ten in da_ghi:
        print(f"  {ten}")
    return da_ghi


def _dat_vao_khung(goc: Image.Image, canh: int, *, ty_le_noi_dung: float) -> Image.Image:
    """Đặt linh vật vào khung vuông nền màu thương hiệu, canh giữa."""
    khung = Image.new("RGBA", (canh, canh), (47, 174, 102, 255))  # #2fae66
    kich_thuoc = round(canh * ty_le_noi_dung)
    ty_le = kich_thuoc / max(goc.width, goc.height)
    noi_dung = goc.resize((max(1, round(goc.width * ty_le)), max(1, round(goc.height * ty_le))), Image.LANCZOS)
    khung.paste(noi_dung, ((canh - noi_dung.width) // 2, (canh - noi_dung.height) // 2), noi_dung)
    return khung


def main() -> int:
    # Console Windows mặc định là cp1252, không in được tiếng Việt có dấu.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not NGUON.exists():
        print(f"Không tìm thấy thư mục {NGUON}")
        return 1
    print("Xuất ảnh linh vật:")
    xuat_mascot()
    print("Sinh icon app:")
    xuat_icon()
    print("Xong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
