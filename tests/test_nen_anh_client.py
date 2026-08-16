"""Nén ảnh phía client trước khi upload (gói P36) — guard test quét frontend.

Không test nào chạm trình duyệt hay mạng. Đúng khuôn ``test_anh_va_vi_tri.py``:
quét dưới dạng văn bản các file frontend, vì ba lỗi của gói này (nén quá tay,
tỉ lệ chia nhầm cạnh, gửi Blob không đuôi) đều lọt qua lint + typecheck.
"""

from __future__ import annotations

import re
from pathlib import Path

GOC_DU_AN = Path(__file__).resolve().parents[1]

API_TS = GOC_DU_AN / "frontend" / "src" / "lib" / "api.ts"
NEN_ANH_TS = GOC_DU_AN / "frontend" / "src" / "lib" / "nen_anh.ts"


def _than_classify_image() -> str:
    """Thân khối khai báo ``classifyImage: async (…) => { … }``, cân bằng ngoặc."""
    noi_dung = API_TS.read_text(encoding="utf-8")
    bat = noi_dung.find("classifyImage:")
    if bat == -1:
        return ""
    mo = noi_dung.find("{", bat)
    do_sau = 0
    for i in range(mo, len(noi_dung)):
        ky_tu = noi_dung[i]
        if ky_tu == "{":
            do_sau += 1
        elif ky_tu == "}":
            do_sau -= 1
            if do_sau == 0:
                return noi_dung[mo : i + 1]
    return ""


def test_classify_image_co_nen_truoc_khi_gui() -> None:
    """Thân ``classifyImage`` phải gọi ``nenAnh`` và KHÔNG còn gửi file gốc trần."""
    than = _than_classify_image()
    assert than, "Không tìm thấy khối classifyImage trong api.ts"
    assert "nenAnh" in than, "classifyImage phải nén trước khi gửi"
    assert 'form.append("image", file)' not in than, "Không được gửi file gốc trần"
    assert 'form.append("image", await nenAnh(file))' in than


def test_khong_nen_xuong_512() -> None:
    """`CANH_DAI_TOI_DA` phải ≥ 1024.

    Máy chủ còn giữ một bản "ảnh gốc" cho ban quản lý mở khi có tranh chấp
    (``Media.original_path``). 512px không còn là bằng chứng gì; 1600px vẫn đọc
    được — hơn cả Full HD.
    """
    noi_dung = NEN_ANH_TS.read_text(encoding="utf-8")
    mo = re.search(r"CANH_DAI_TOI_DA\s*=\s*(\d+)", noi_dung)
    assert mo is not None, "Không tìm thấy CANH_DAI_TOI_DA"
    assert int(mo.group(1)) >= 1024, f"CANH_DAI_TOI_DA = {mo.group(1)} — phải ≥ 1024 để giữ bản ảnh gốc cho BQL"


def test_ti_le_thu_nho_dung_canh_dai() -> None:
    """Chốt chặn chính: ``tiLe`` phải chia cho CẠNH DÀI (`Math.max`), không phải cạnh ngắn.

    `CANH_DAI_TOI_DA` là cạnh DÀI tối đa. Chia cho cạnh ngắn (`Math.min`) thì cạnh
    dài sau thu nhỏ còn ``1600 × (dài/ngắn)`` — ảnh 4000×3000 ra 2133×1600 thay vì
    1600×1200, tức to hơn ý định ~78% số điểm ảnh, và không làm hỏng gì nhìn thấy
    được — đúng thứ gói này sinh ra để cắt.
    """
    noi_dung = NEN_ANH_TS.read_text(encoding="utf-8")
    mo = re.search(r"CANH_DAI_TOI_DA\s*/\s*(Math\.[a-z]+)\(rong, cao\)", noi_dung)
    assert mo is not None, "Không tìm thấy biểu thức tính tiLe"
    assert mo.group(1) == "Math.max", f"tiLe phải chia cho cạnh DÀI (Math.max), đang dùng {mo.group(1)}"
    assert "Math.min(rong, cao)" not in noi_dung


def test_hong_thi_tra_lai_file_goc() -> None:
    """Mọi lỗi nén đều phải trả lại file gốc trong nhánh ``catch``, không ném ra ngoài."""
    noi_dung = NEN_ANH_TS.read_text(encoding="utf-8")
    assert "try {" in noi_dung and "catch {" in noi_dung, "Phải có khối try/catch"
    vi_tri = noi_dung.find("catch {")
    doan_catch = noi_dung[vi_tri : vi_tri + 500]
    assert "return file" in doan_catch, "Nhánh lỗi phải trả về file gốc"


def test_dung_file_co_duoi_jpg() -> None:
    """`FormData` phải nhận `File` có tên đuôi `.jpg`, không phải `Blob` trần."""
    noi_dung = NEN_ANH_TS.read_text(encoding="utf-8")
    assert "new File(" in noi_dung, "Phải bọc kết quả trong new File(...)"
    assert ".jpg" in noi_dung, "File kết quả phải có đuôi .jpg"
    than = _than_classify_image()
    assert "Blob" not in than, "form.append phải nhận File, không phải Blob trần (sẽ gửi filename=\"blob\")"


def test_co_thu_hoi_object_url() -> None:
    """Mọi `createObjectURL` phải có `revokeObjectURL` đứng đối — không rò blob URL (bài học P27)."""
    noi_dung = NEN_ANH_TS.read_text(encoding="utf-8")
    so_tao = noi_dung.count("URL.createObjectURL")
    so_thu_hoi = noi_dung.count("URL.revokeObjectURL")
    assert so_tao <= so_thu_hoi, f"createObjectURL {so_tao} lần nhưng revokeObjectURL chỉ {so_thu_hoi} — rò bộ nhớ"
