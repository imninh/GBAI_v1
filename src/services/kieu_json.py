"""Làm sạch giá trị trước khi ghi cột JSON — nguồn chung cho mọi chỗ ghi.

Sự cố 16–17/08/2026: máy chủ thật trả ``TypeError: Object of type int64 is not
JSON serializable`` khi SQLAlchemy ghi cột JSON. Thư viện numpy trả
``int64``/``float32`` tuỳ **phiên bản**: numpy 2.x cho ``int``, numpy 1.x cho
``int64`` — cùng một dòng mã, máy dev chạy tốt còn máy chủ nổ. Chặn ở biên ghi
dữ liệu thay vì đuổi theo từng field, và giữ ``logger.warning`` nêu rõ cột + khoá
bị đổi để lần ra thủ phạm sinh numpy.

Hai hàm này tách từ ``src.services.runs`` (nơi chỉ bọc mỗi cột
``run_node_metrics.meta``) để mọi chỗ ghi cột JSON dùng chung một cách làm sạch.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def ve_kieu_python(gia_tri: object) -> object:
    """Đổi mọi kiểu vô danh (numpy scalar…) về kiểu Python ghi JSON được.

    Đệ quy qua ``dict`` / ``list`` / ``tuple``; mọi giá trị có ``.item()`` (numpy
    scalar) được đổi về kiểu Python tương đương — kiểu gốc là int thì ra int, là
    float thì ra float, không dùng ``float()``/``int()`` mù quáng. ``None`` giữ
    nguyên (JSON hỗ trợ ``null``); người gọi tự chặn ``None`` ở lớp trên cho cột
    ``NOT NULL``.
    """
    if isinstance(gia_tri, dict):
        return {k: ve_kieu_python(v) for k, v in gia_tri.items()}
    if isinstance(gia_tri, (list, tuple)):
        return [ve_kieu_python(v) for v in gia_tri]
    # numpy scalar có `.item()` trả về giá trị Python tương đương. Nhận diện bằng
    # hasattr thay vì import numpy — máy chạy có thể không cài numpy.
    if hasattr(gia_tri, "item"):
        try:
            return ve_kieu_python(gia_tri.item())
        except (TypeError, ValueError, OverflowError):
            return str(gia_tri)
    if gia_tri is None or isinstance(gia_tri, (bool, int, float, str)):
        return gia_tri
    return str(gia_tri)


def khoa_bi_doi(gia_tri: object, tien_to: str = "") -> list[tuple[str, str]]:
    """Liệt kê chỗ nào trong giá trị sẽ phải đổi kiểu trước khi ghi.

    Returns:
        ``[(đường_dẫn, tên_kiểu_gốc), …]``. Đường dẫn như ``"so_luong"`` hay
        ``"ds[0][\"a\"]"`` để người đọc log tìm ra ngay thủ phạm sinh numpy.
    """
    if isinstance(gia_tri, dict):
        cac_cho: list[tuple[str, str]] = []
        for khoa, con in gia_tri.items():
            duong = f"{tien_to}.{khoa}" if tien_to else str(khoa)
            cac_cho.extend(khoa_bi_doi(con, duong))
        return cac_cho
    if isinstance(gia_tri, (list, tuple)):
        cac_cho = []
        for chi_so, con in enumerate(gia_tri):
            cac_cho.extend(khoa_bi_doi(con, f"{tien_to}[{chi_so}]"))
        return cac_cho
    if gia_tri is not None and not isinstance(gia_tri, (bool, int, float, str)) and hasattr(gia_tri, "item"):
        return [(tien_to, type(gia_tri).__name__)]
    return []


def lam_sach_gia_tri(gia_tri: object, ghi_cho: str) -> object:
    """Làm sạch và log rõ cột + khoá bị đổi — dùng ở biên ghi mọi cột JSON.

    Args:
        ghi_cho: tên cột/bản ghi để log, ví dụ ``"classifications.items"``.
    """
    for duong, loai in khoa_bi_doi(gia_tri):
        logger.warning(
            "%s chứa kiểu %s tại '%s' — đã đổi về kiểu Python trước khi ghi",
            ghi_cho,
            loai,
            duong,
        )
    return ve_kieu_python(gia_tri)
