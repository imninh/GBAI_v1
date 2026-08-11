"""Trích dẫn AI log đã che dữ liệu nhạy cảm — deliverable #4 của chương trình.

Log thô ở ``.ai-log/archive/*.jsonl`` chứa nguyên văn prompt và nội dung file
(tổng vài MB) nên **cố ý không đẩy lên repo**. Script này rút ra một bản trích
dẫn Markdown: vài trace tiêu biểu, đã che khoá/token, chuỗi kết nối, đường dẫn
máy cá nhân và địa chỉ liên hệ ngoài danh sách tài khoản demo — đủ để người chấm
thấy quy trình làm việc với AI mà không phải đọc vài MB JSON.

    python scripts/trich_dan_ai_log.py --ra <file kết quả>.md --so-trace 8

Thà che nhầm còn hơn bỏ sót: bản này sẽ nằm trên một repo công khai, nên bộ lọc
nghiêng về phía che nhiều.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Console Windows mặc định cp1252, in tiếng Việt thẳng ra là vỡ. Giữ guard vì
# pytest thay stdout bằng đối tượng không có ``reconfigure``.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_CHE_VAO = "«đã che»"

# Tài khoản demo đã công bố trong README.md — không được che.
DEMO_EMAILS = ("resident@demo.vn", "cleaner@demo.vn", "manager@demo.vn")
DEMO_PHONES = ("0901000001", "0901000002", "0901000003")

# Giới hạn độ dài của một giá trị khi dựng báo cáo — không cần đọc cả vài MB.
_TOI_DA_KY_TU = 600


def _gioi_thieu_trace(trace: dict) -> str:
    """Một câu người viết giải thích trace này cho thấy điều gì."""
    event = trace.get("event", "")
    tool_name = trace.get("tool_name", "")
    if event == "tool.execute.after":
        return (
            f"Trace của một lần agent dùng công cụ '{tool_name or '?'}': minh hoạ việc agent "
            "hành động được trên repo (đọc/ghi/kiểm tra), không chỉ trả lời bằng chữ."
        )
    if event in ("chat.message", "message.completed"):
        return (
            "Trace của một lượt hội thoại: cho thấy cách agent nhận lệnh và trả lời bằng "
            "ngôn ngữ tự nhiên trong phiên làm việc."
        )
    if event == "UserPromptSubmit":
        return "Trace của một lần người dùng gửi lệnh: đầu vào người thật khởi đầu một phiên làm việc."
    return f"Trace sự kiện '{event or '?'}': minh hoạ một bước trong phiên làm việc với AI."


# --- Che bí mật -------------------------------------------------------------


def che_bi_mat(van_ban: str) -> str:
    """Che khoá, token, chuỗi kết nối, đường dẫn cá nhân trong một đoạn văn bản.

    Thà che nhầm còn hơn bỏ sót: bản trích dẫn này sẽ nằm trên một repo công khai.
    Tài khoản demo đã công bố trong README được bảo vệ bằng cách thay bằng "thẻ"
    trước khi che rồi khôi phục sau cùng — để bộ lọc không đụng tới chúng.
    """
    giu_lai: dict[str, str] = {}
    for chi_so, email in enumerate(DEMO_EMAILS):
        the = f"«DEMO_EMAIL_{chi_so}»"
        if email in van_ban:
            van_ban = van_ban.replace(email, the)
            giu_lai[the] = email
    for chi_so, sdt in enumerate(DEMO_PHONES):
        the = f"«DEMO_PHONE_{chi_so}»"
        if sdt in van_ban:
            van_ban = van_ban.replace(sdt, the)
            giu_lai[the] = sdt

    for khuon_mau, thay_the in _CAC_PHEP_CHE:
        van_ban = khuon_mau.sub(thay_the, van_ban)

    for the, gia_tri in giu_lai.items():
        van_ban = van_ban.replace(the, gia_tri)
    return van_ban


# Các phép che, chạy theo đúng thứ tự. Chuỗi kết nối chạy TRƯỚC nhóm "tên biến"
# để `DATABASE_URL=postgresql://...` còn giữ lại phần `postgresql://` cho dễ đọc.
_CAC_PHEP_CHE: list[tuple[re.Pattern[str], str]] = [
    # 1. Chuỗi kết nối CSDL — che phần sau dấu //.
    (re.compile(r"(postgres(?:ql)?://|sqlite:///)[^\s\"'\)]+"), r"\1«đã che»"),
    # 2. Khoá/token có tiền tố đã biết.
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), _CHE_VAO),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"), _CHE_VAO),
    (re.compile(r"\bhf_[A-Za-z0-9]{8,}"), _CHE_VAO),
    (re.compile(r"\bghp_[A-Za-z0-9]{8,}"), _CHE_VAO),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=\-]{8,}"), "Bearer «đã che»"),
    # 3. Chuỗi hex dài ≥ 32 — có thể là khoá; che nhầm mã băm (pHash,
    #    device_key_hash) chấp nhận được, còn hơn sót một khoá thật.
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), _CHE_VAO),
    # 4. Đường dẫn máy cá nhân — chỉ che tên người dùng, giữ nguyên phần còn lại.
    (re.compile(r"(?i)(C:\\Users\\)([^\\\s\"']+)"), r"\1<user>"),
    # 5. Giá trị sau tên biến nhạy cảm (dạng TEN=giá_trị). Loại trừ chuỗi kết nối
    #    đã xử lý ở bước 1 để không che mất phần tiền tố dễ đọc.
    (
        re.compile(
            r"\b([A-Za-z_][A-Za-z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|DSN|DATABASE_URL))\s*=\s*"
            r"(?!postgres(?:ql)?://|sqlite:///)([^\s,;\"']+)",
            re.IGNORECASE,
        ),
        r"\1=«đã che»",
    ),
    # 6. Giá trị sau khoá JSON nhạy cảm (dạng "ten": "giá trị").
    (
        re.compile(r'"([^"]*(?:KEY|SECRET|TOKEN|PASSWORD|DSN|DATABASE_URL)[^"]*)":\s*"[^"]*"', re.IGNORECASE),
        r'"\1": "«đã che»"',
    ),
    # 7. Địa chỉ email ngoài danh sách demo.
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), _CHE_VAO),
    # 8. Số điện thoại Việt Nam dạng 0xxxxxxxxx ngoài danh sách demo.
    (re.compile(r"\b0\d{9}\b"), _CHE_VAO),
]


# --- Đọc và chọn trace -------------------------------------------------------


def doc_trace(duong_dan: Path) -> list[dict]:
    """Đọc một file .jsonl, bỏ qua dòng hỏng thay vì chết cả file."""
    ket_qua: list[dict] = []
    if not duong_dan.exists():
        return ket_qua
    with open(duong_dan, encoding="utf-8") as tep:
        for dong in tep:
            dong = dong.strip()
            if not dong:
                continue
            try:
                du_lieu = json.loads(dong)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(du_lieu, dict):
                ket_qua.append(du_lieu)
    return ket_qua


def chon_trace(cac_dong: list[dict], so_luong: int) -> list[dict]:
    """Chọn các trace tiêu biểu, trải đều theo ngày và theo loại công cụ.

    Trải đều quan trọng hơn lấy nhiều: tám trace của cùng một ngày, cùng một
    công cụ thì không cho người chấm thấy được quy trình.
    """
    if so_luong <= 0 or not cac_dong:
        return []
    if len(cac_dong) <= so_luong:
        return list(cac_dong)

    theo_ngay: dict[str, list[dict]] = {}
    for dong in cac_dong:
        ngay = (dong.get("ts") or "")[:10] or "?"
        theo_ngay.setdefault(ngay, []).append(dong)
    cac_ngay = sorted(theo_ngay)

    ket_qua: list[dict] = []
    dem_loai: dict[tuple[str, str], int] = {}
    vong = 0
    while len(ket_qua) < so_luong:
        nhom = theo_ngay[cac_ngay[vong % len(cac_ngay)]]
        vong += 1
        ung_vien = [d for d in nhom if d not in ket_qua]
        if not ung_vien:
            continue
        # Ưu tiên loại (công cụ, tên công cụ) chưa xuất hiện: chat thường trống
        # tool_name, còn trace dùng công cụ (write/read/edit) có tool_name — thứ
        # cho người chấm thấy agent hành động thật trên repo.
        ung_vien.sort(
            key=lambda d: (
                dem_loai.get((d.get("tool", ""), d.get("tool_name", "")), 0),
                d.get("ts", ""),
            )
        )
        chon = ung_vien[0]
        nhom_loai = (chon.get("tool", ""), chon.get("tool_name", ""))
        dem_loai[nhom_loai] = dem_loai.get(nhom_loai, 0) + 1
        ket_qua.append(chon)
    return ket_qua


# --- Dựng báo cáo ------------------------------------------------------------


def _che_cat_ngan(gia_tri: object) -> str:
    """Tuần tự hoá một giá trị (có thể là dict lồng nhau), che rồi cắt ngắn."""
    if gia_tri is None:
        return ""
    if isinstance(gia_tri, str):
        van_ban = gia_tri
    else:
        van_ban = json.dumps(gia_tri, ensure_ascii=False, indent=2)
    van_ban = che_bi_mat(van_ban)
    if len(van_ban) > _TOI_DA_KY_TU:
        van_ban = van_ban[: _TOI_DA_KY_TU - 1] + "…"
    return van_ban


def _mo_ta_gia_tri(gia_tri: object) -> str:
    """Một giá trị dạng đọc được trong một dòng Markdown, đã che và cắt ngắn."""
    if gia_tri is None or gia_tri == "" or gia_tri == [] or gia_tri == {}:
        return "_(trống)_"
    return _che_cat_ngan(gia_tri).replace("\n", " ")


def dung_bao_cao(cac_trace: list[dict], *, tong_dong: int = 0) -> str:
    """Dựng file Markdown: mỗi trace một mục, có ngày, model, công cụ, đầu vào
    (đã che, cắt ngắn), đầu ra (đã che, cắt ngắn), và một câu người viết giải
    thích trace đó cho thấy điều gì."""
    cac_dong = [
        "# Trích dẫn AI log — bản đã che dữ liệu nhạy cảm",
        "",
        "Đây là **bản trích dẫn** phục vụ deliverable \"AI Logs\" của chương trình. "
        "Log thô KHÔNG được đẩy lên repo vì chúng chứa nguyên văn prompt và nội dung file "
        "(tổng vài MB JSON). "
        f"Bản này trích {len(cac_trace)} trace trên tổng {tong_dong} dòng log.",
        "",
        "**Đã che:** khoá/token API, chuỗi kết nối CSDL, đường dẫn máy cá nhân, địa chỉ email "
        "và số điện thoại ngoài danh sách tài khoản demo đã công bố trong README.",
        "",
        "---",
        "",
    ]
    for chi_so, trace in enumerate(cac_trace, start=1):
        cac_dong.append(f"## Trace {chi_so} — {trace.get('event', '?')} ({trace.get('tool', '?')})")
        cac_dong.append("")
        cac_dong.append(f"- **Ngày:** {(trace.get('ts') or '?')[:19].replace('T', ' ')}")
        cac_dong.append(f"- **Model:** {trace.get('model') or '—'}")
        cac_dong.append(f"- **Công cụ:** {trace.get('tool') or '—'}")
        if trace.get("tool_name"):
            cac_dong.append(f"- **Tên công cụ:** {trace.get('tool_name')}")
        cac_dong.append(f"- **Lệnh:** {_mo_ta_gia_tri(trace.get('prompt'))}")
        cac_dong.append(f"- **Đầu vào:** {_mo_ta_gia_tri(trace.get('tool_input'))}")
        cac_dong.append(f"- **Đầu ra:** {_mo_ta_gia_tri(trace.get('tool_response'))}")
        cac_dong.append("")
        cac_dong.append(f"> {_gioi_thieu_trace(trace)}")
        cac_dong.append("")
        if chi_so < len(cac_trace):
            cac_dong.append("---")
            cac_dong.append("")
    return "\n".join(cac_dong) + "\n"


# --- Chạy --------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Trích dẫn AI log đã che dữ liệu nhạy cảm.")
    parser.add_argument("--nguon", default=".ai-log/archive", help="thư mục log (mặc định .ai-log/archive)")
    parser.add_argument("--ra", required=True, help="file kết quả Markdown (BẮT BUỘC truyền)")
    parser.add_argument("--so-trace", type=int, default=8, help="số trace muốn lấy (mặc định 8)")
    tham_so = parser.parse_args()

    nguon = Path(tham_so.nguon)
    cac_dong: list[dict] = []
    for tep in sorted(nguon.glob("*.jsonl")):
        cac_dong.extend(doc_trace(tep))

    cac_trace = chon_trace(cac_dong, tham_so.so_trace)
    bao_cao = dung_bao_cao(cac_trace, tong_dong=len(cac_dong))
    so_lan_che = bao_cao.count(_CHE_VAO)

    Path(tham_so.ra).write_text(bao_cao, encoding="utf-8")

    print(f"Đã đọc {len(cac_dong)} dòng log từ {nguon}.")
    print(f"Đã chọn {len(cac_trace)} trace.")
    print(f"Số lần che: {so_lan_che}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
