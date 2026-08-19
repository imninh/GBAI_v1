"""Lớp mỏng bọc Supabase Storage — cất ảnh cư dân khỏi đĩa tạm của Railway.

Ảnh tải lên đang nằm trên đĩa container (đĩa TẠM — restart là mất). Storage là
nơi ảnh bền vững. Bucket RIÊNG TƯ: ảnh rác của cư dân không được để ai có link
cũng xem — đường đọc duy nhất là qua ``GET /media/{id}`` của chính sản phẩm, nơi
đã có sẵn phép kiểm quyền.

**Khoá nào dùng ở đây:** mọi lệnh ghi/đọc chạy ở MÁY CHỦ đều mang khoá BÍ MẬT
(``supabase_secret_key``, service role) để bỏ qua Row Level Security của bucket
riêng tư. Khoá CÔNG KHAI (``SUPABASE_PUBLISHABLE_KEY``) CHỈ dành cho trình duyệt
và **tuyệt đối không được xuất hiện trong mã máy chủ** — request tới bucket
riêng tư bật RLS mà mang khoá công khai sẽ trả 401/403, ảnh âm thầm không bao
giờ lên được Storage mà không có gì đỏ.

Rơi êm tuyệt đối: cờ tắt / thiếu biến / hỏng mạng / 4xx/5xx → trả ``None``/``False``
và ghi ``logger.warning`` (chỉ mã HTTP + khoá file, KHÔNG ghi header, KHÔNG ghi
khoá bí mật). Không ngoại lệ nào thoát ra.
"""

from __future__ import annotations

import logging

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)

# Ảnh đã nén ~512px vài trăm KB tới ~12 MB; 30 giây đủ cho upload chậm nhất.
_QUA_HAN_GIAY = 30.0


def _cau_hinh() -> tuple[str, str, str] | None:
    """``(url, khoa_bi_mat, bucket)`` hoặc ``None`` khi chưa sẵn sàng."""
    settings = get_settings()
    if not settings.storage_enabled:
        return None
    url = settings.supabase_url.strip().rstrip("/")
    if not url or not settings.supabase_secret_key:
        return None
    return url, settings.supabase_secret_key, settings.supabase_bucket


def tai_len(duong_dan_dia: str, khoa: str) -> str | None:
    """Đẩy một file từ đĩa lên Supabase Storage.

    Args:
        duong_dan_dia: đường dẫn file đã có trên đĩa.
        khoa: khoá trong bucket, ví dụ ``"uploads/2026/08/12/abc.jpg"``.

    Returns:
        ``khoa`` khi thành công, ``None`` khi tắt cờ / hỏng / quá hạn.
        ``None`` là tín hiệu "giữ nguyên đường đĩa như cũ".
    """
    cau_hinh = _cau_hinh()
    if cau_hinh is None or not khoa:
        return None
    url, khoa_bi_mat, bucket = cau_hinh

    try:
        with open(duong_dan_dia, "rb") as tep:
            noi_dung = tep.read()
        with httpx.Client(timeout=_QUA_HAN_GIAY) as khach:
            phan_hoi = khach.post(
                f"{url}/storage/v1/object/{bucket}/{khoa}",
                headers={
                    "Authorization": f"Bearer {khoa_bi_mat}",
                    "apikey": khoa_bi_mat,
                    "Content-Type": "image/jpeg",
                },
                content=noi_dung,
            )
            phan_hoi.raise_for_status()
    except httpx.HTTPStatusError as loi:
        logger.warning(
            "Tải ảnh lên Storage không được — HTTP %s, khoá '%s'. Giữ nguyên đường đĩa.",
            loi.response.status_code,
            khoa,
        )
        return None
    except (httpx.HTTPError, OSError, ValueError) as loi:
        logger.warning(
            "Tải ảnh lên Storage không được (%s) với khoá '%s'. Giữ nguyên đường đĩa.",
            type(loi).__name__,
            khoa,
        )
        return None
    return khoa


def tai_ve(khoa: str) -> bytes | None:
    """Lấy nội dung một file từ Storage. ``None`` khi tắt cờ / không có / hỏng."""
    cau_hinh = _cau_hinh()
    if cau_hinh is None or not khoa:
        return None
    url, khoa_bi_mat, bucket = cau_hinh

    try:
        with httpx.Client(timeout=_QUA_HAN_GIAY) as khach:
            phan_hoi = khach.get(
                f"{url}/storage/v1/object/{bucket}/{khoa}",
                headers={"Authorization": f"Bearer {khoa_bi_mat}", "apikey": khoa_bi_mat},
            )
            phan_hoi.raise_for_status()
    except httpx.HTTPStatusError as loi:
        logger.warning("Đọc ảnh từ Storage không được — HTTP %s, khoá '%s'.", loi.response.status_code, khoa)
        return None
    except (httpx.HTTPError, OSError, ValueError) as loi:
        logger.warning("Đọc ảnh từ Storage không được (%s) với khoá '%s'.", type(loi).__name__, khoa)
        return None
    return phan_hoi.content


def xoa(khoa: str) -> bool:
    """Xoá một file. Trả ``False`` khi tắt cờ hoặc hỏng — không ném ngoại lệ."""
    cau_hinh = _cau_hinh()
    if cau_hinh is None or not khoa:
        return False
    url, khoa_bi_mat, bucket = cau_hinh

    try:
        with httpx.Client(timeout=_QUA_HAN_GIAY) as khach:
            phan_hoi = khach.delete(
                f"{url}/storage/v1/object/{bucket}/{khoa}",
                headers={"Authorization": f"Bearer {khoa_bi_mat}", "apikey": khoa_bi_mat},
            )
            phan_hoi.raise_for_status()
    except httpx.HTTPStatusError as loi:
        logger.warning("Xoá ảnh trên Storage không được — HTTP %s, khoá '%s'.", loi.response.status_code, khoa)
        return False
    except (httpx.HTTPError, OSError, ValueError) as loi:
        logger.warning("Xoá ảnh trên Storage không được (%s) với khoá '%s'.", type(loi).__name__, khoa)
        return False
    return True


def kiem_tra() -> dict[str, object]:
    """Tự kiểm Storage: thử ghi → đọc → xoá một object nhỏ. Không ném ngoại lệ.

    Dùng cho /ops để NHÌN THẤY Storage có thật sự chạy — thay vì lỗi im lặng rơi
    về đĩa. ``ok=False`` kèm ``chi_tiet`` có mã HTTP để chẩn đúng cấu hình.
    """
    settings = get_settings()
    ket: dict[str, object] = {
        "enabled": settings.storage_enabled,
        "bucket": settings.supabase_bucket,
        "ok": False,
        "chi_tiet": "",
    }
    cau_hinh = _cau_hinh()
    if cau_hinh is None:
        ket["chi_tiet"] = "tắt cờ hoặc thiếu SUPABASE_URL / SUPABASE_SECRET_KEY"
        return ket
    url, khoa_bi_mat, bucket = cau_hinh
    khoa = "healthcheck/ops-ping.txt"
    try:
        with httpx.Client(timeout=10.0) as khach:
            ghi = khach.post(
                f"{url}/storage/v1/object/{bucket}/{khoa}",
                headers={
                    "Authorization": f"Bearer {khoa_bi_mat}",
                    "apikey": khoa_bi_mat,
                    "Content-Type": "text/plain",
                    "x-upsert": "true",
                },
                content=b"ping",
            )
            if ghi.status_code >= 400:
                ket["chi_tiet"] = f"ghi lỗi HTTP {ghi.status_code} — kiểm URL/khoá/bucket"
                return ket
            doc = khach.get(
                f"{url}/storage/v1/object/{bucket}/{khoa}",
                headers={"Authorization": f"Bearer {khoa_bi_mat}", "apikey": khoa_bi_mat},
            )
            if doc.status_code >= 400:
                ket["chi_tiet"] = f"đọc lỗi HTTP {doc.status_code}"
                return ket
            khach.delete(
                f"{url}/storage/v1/object/{bucket}/{khoa}",
                headers={"Authorization": f"Bearer {khoa_bi_mat}", "apikey": khoa_bi_mat},
            )
        ket["ok"] = True
        ket["chi_tiet"] = "ghi/đọc/xoá bucket OK"
    except httpx.HTTPError as loi:
        ket["chi_tiet"] = f"lỗi mạng: {type(loi).__name__}"
    return ket
