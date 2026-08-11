"""So sánh hai hay nhiều lần chạy eval phân loại rác trên cùng một bộ ảnh.

``eval/run_eval.py`` mỗi lần chạy ghi ra một file JSON trong ``eval/results/``.
Đọc từng file bằng mắt rồi tự so trong đầu là đúng kiểu dẫn tới một kết luận
sai lọt vào báo cáo — đã hai lần một model đứng đầu trên ảnh dễ mà thua trên ảnh
rác thật. Script này in **một bảng** so sánh các lần chạy, và liệt kê những ảnh
có kết quả bị lật giữa hai lần — danh sách đó chính là nguyên liệu cho phân tích
failure case (PLO 7).

Script **không gọi model và không đụng CSDL**: chỉ đọc JSON có sẵn.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

THU_MUC_KET_QUA = ROOT / "eval" / "results"

KHONG_RO_MODEL = "(không rõ model)"

#: Nhãn in làm tiêu đề cột của mỗi lần chạy trong bảng so sánh.
_TIEU_DE_COT = "lần {n}"


def _duong_dan_tu(dai_dien: str) -> Path:
    """Tên trần (không có thư mục) → tìm trong ``eval/results/``.

    Đường dẫn có thư mục (tương đối lẫn tuyệt đối) thì giữ nguyên.
    """
    p = Path(dai_dien)
    if p.is_absolute() or p.parent != Path("."):
        return p
    return THU_MUC_KET_QUA / p


def doc_lan_chay(duong_dan: Path) -> dict:
    """Đọc một file kết quả eval dạng JSON và trả về toàn bộ nội dung.

    Raises:
        ValueError: khi file không có khoá ``tong_hop`` — tức không phải file kết
            quả của ``run_eval.py``.
    """
    du_lieu = json.loads(duong_dan.read_text(encoding="utf-8"))
    if not isinstance(du_lieu, dict) or "tong_hop" not in du_lieu:
        raise ValueError(f"{duong_dan} không có khoá 'tong_hop' — không phải file kết quả của run_eval.py")
    return du_lieu


def nhan_lan_chay(du_lieu: dict) -> str:
    """Tên model đại diện cho một lần chạy.

    Ưu tiên **cấu hình đã ghi** khi có: từ ``run_eval.py`` 08/08/2026, mỗi file
    kết quả tự ghi khối ``cau_hinh`` nên lấy thẳng model của tầng T1 thay vì
    phải suy. Trước đó ``run_eval.py`` không ghi cấu hình, nên vẫn giữ lối suy
    cũ cho các file cũ: đếm ``tung_anh[].model``, lấy tên xuất hiện nhiều nhất.
    Mọi ảnh đều để rỗng thì không suy được, trả về ``(không rõ model)``.
    """
    cau_hinh = du_lieu.get("cau_hinh")
    if isinstance(cau_hinh, dict):
        tang = (cau_hinh.get("tang") or {}).get("t1")
        if isinstance(tang, dict) and tang.get("provider") and tang.get("model"):
            return f"{tang['provider']}/{tang['model']}"

    dem: Counter[str] = Counter()
    for anh in du_lieu.get("tung_anh") or []:
        ten = str(anh.get("model", "")).strip()
        if ten:
            dem[ten] += 1
    if not dem:
        return KHONG_RO_MODEL
    return dem.most_common(1)[0][0]


def _o(gia_tri: object) -> str:
    """Số/chuỗi thành ô trong bảng; ``None`` là "—" (không có số liệu)."""
    return "—" if gia_tri is None else str(gia_tri)


def _phan_tram(gia_tri: object) -> str:
    """Một tỉ lệ dạng số (0–1) thành phần trăm một chữ số thập phân."""
    if gia_tri is None:
        return "—"
    try:
        so = float(gia_tri)
    except (TypeError, ValueError):
        return "—"
    return f"{so * 100:.1f}%"


def _chi_phi(tong: dict | None) -> str:
    """Chi phí USD của một lần chạy, hoặc "chưa có giá" khi không có bảng giá."""
    if tong is None:
        return "—"
    if not tong.get("du_gia", True):
        return "chưa có giá"
    return f"${float(tong.get('tong_chi_phi_usd', 0.0)):.4f}"


def so_sanh(cac_lan: list[dict], bo: str = "cong_khai") -> str:
    """Bảng so sánh các lần chạy trên một bộ ảnh, mỗi lần chạy là một cột.

    Trả về chuỗi để test được mà không cần stdout. Lần chạy nào **không có số
    liệu cho ``bo``** thì toàn cột hiện "—". Chi phí của lần chạy không có bảng
    giá (``du_gia`` = False) in "chưa có giá" — **không bao giờ** in $0 cho một
    model chưa biết giá: cái $0 đó nghĩa là "chưa đo được" chứ không phải "miễn
    phí".
    """
    cac_tong: list[dict | None] = []
    for du_lieu in cac_lan:
        tong_hop = du_lieu.get("tong_hop") or {}
        cac_tong.append(tong_hop.get(bo) if isinstance(tong_hop, dict) else None)

    cac_hang: list[tuple[str, list[str]]] = [
        ("model", [nhan_lan_chay(d) for d in cac_lan]),
        ("số ảnh", [_o((t or {}).get("so_anh")) for t in cac_tong]),
        ("tỉ lệ trả lời", [_phan_tram((t or {}).get("ty_le_tra_loi")) for t in cac_tong]),
        ("accuracy khi trả lời", [_phan_tram((t or {}).get("accuracy_khi_tra_loi")) for t in cac_tong]),
        ("accuracy toàn bộ", [_phan_tram((t or {}).get("accuracy_toan_bo")) for t in cac_tong]),
        ("macro F1", [_phan_tram((t or {}).get("macro_f1")) for t in cac_tong]),
        ("recall nguy hại", [_phan_tram((t or {}).get("recall_nguy_hai")) for t in cac_tong]),
        ("latency p50 (ms)", [_o((t or {}).get("latency_p50_ms")) for t in cac_tong]),
        ("latency p95 (ms)", [_o((t or {}).get("latency_p95_ms")) for t in cac_tong]),
        ("chi phí USD", [_chi_phi(t) for t in cac_tong]),
    ]

    tieu_de = [_TIEU_DE_COT.format(n=i + 1) for i in range(len(cac_lan))]
    do_rong_nhan = max(len(nhan) for nhan, _ in cac_hang)
    do_rong_cot = [max([len(tieu_de[i])] + [len(o[i]) for _, o in cac_hang]) for i in range(len(cac_lan))]

    cac_dong = [" " * (do_rong_nhan + 2) + "  ".join(tieu_de[i].rjust(do_rong_cot[i]) for i in range(len(cac_lan)))]
    cac_dong.append("-" * len(cac_dong[0]))
    for nhan, cac_o in cac_hang:
        cac_dong.append(
            nhan.ljust(do_rong_nhan) + "  " + "  ".join(cac_o[i].rjust(do_rong_cot[i]) for i in range(len(cac_lan)))
        )
    return "\n".join(cac_dong)


def _dung(anh: dict) -> bool:
    """Một ảnh được tính là "trả lời ĐÚNG" trong phép đối chiếu lật kết quả."""
    return (
        not anh.get("tu_choi")
        and not anh.get("loi")
        and str(anh.get("nhan_du_doan", "")).strip() == str(anh.get("nhan_dung", "")).strip()
    )


def doi_ket_qua(lan_a: dict, lan_b: dict) -> tuple[list[dict], list[dict]]:
    """Đối chiếu từng ảnh giữa hai lần chạy, trả về ``(tốt lên, xấu đi)``.

    Nối hai lần chạy theo ``duong_dan``. Ảnh có mặt ở một trong hai lần thì bỏ
    qua — không có mẫu đối chiếu thì không kết luận được gì.

    ⚠️ Hệ thống có BA kết cục chứ không phải hai: ``đúng`` · ``sai`` · ``từ chối``
    (``CLAUDE.md`` mục 5 — từ chối với nhóm nguy hại còn là hành vi đúng). Từ chối
    **không phải** một câu trả lời sai. Hàm này **cố ý** gộp từ chối và lỗi với
    sai, chỉ với mục đích riêng là dò ra ảnh bị lật kết quả giữa hai lần chạy —
    và phần in ra phải nói rõ điều đó, để không ai đọc bảng này như một bảng
    accuracy thường.
    """
    cua_a = {anh["duong_dan"]: anh for anh in lan_a.get("tung_anh") or []}
    cua_b = {anh["duong_dan"]: anh for anh in lan_b.get("tung_anh") or []}

    tot_len: list[dict] = []
    xau_di: list[dict] = []
    for duong_dan in sorted(cua_a.keys() & cua_b.keys()):
        anh_a = cua_a[duong_dan]
        anh_b = cua_b[duong_dan]
        dung_a = _dung(anh_a)
        dung_b = _dung(anh_b)
        if not dung_a and dung_b:
            tot_len.append(
                {
                    "duong_dan": duong_dan,
                    "nhan_dung": str(anh_a.get("nhan_dung", "")),
                    "nhan_a": str(anh_a.get("nhan_du_doan", "")),
                    "nhan_b": str(anh_b.get("nhan_du_doan", "")),
                }
            )
        elif dung_a and not dung_b:
            xau_di.append(
                {
                    "duong_dan": duong_dan,
                    "nhan_dung": str(anh_a.get("nhan_dung", "")),
                    "nhan_a": str(anh_a.get("nhan_du_doan", "")),
                    "nhan_b": str(anh_b.get("nhan_du_doan", "")),
                }
            )
    return tot_len, xau_di


def _in_danh_sach(tieu_de: str, danh_sach: list[dict], cap: int) -> None:
    """In một danh sách ảnh lật kết quả, giới hạn ``cap`` dòng."""
    print(f"\n{tieu_de} ({len(danh_sach)} ảnh):")
    for anh in danh_sach[:cap]:
        o_a = anh["nhan_a"] or "(từ chối / lỗi)"
        o_b = anh["nhan_b"] or "(từ chối / lỗi)"
        print(f"  · {anh['duong_dan']} — đúng {anh['nhan_dung']} · lần 1: {o_a} → lần 2: {o_b}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="So sánh hai hay nhiều lần chạy eval phân loại rác — chọn model bằng số đo",
        epilog=(
            "Ví dụ:  python eval/so_sanh_lan_chay.py "
            "phan_loai-20260808-010203.json phan_loai-20260808-141516.json --so-anh-doi 20"
        ),
    )
    parser.add_argument(
        "tep",
        nargs="+",
        help="các file kết quả eval (tối thiểu 2); tên trần sẽ tìm trong eval/results/",
    )
    parser.add_argument("--bo", default="cong_khai", help="bộ ảnh cần so sánh (mặc định cong_khai)")
    parser.add_argument(
        "--so-anh-doi",
        type=int,
        default=10,
        help="số ảnh đổi kết quả hiện tối đa mỗi danh sách (mặc định 10)",
    )
    tham_so = parser.parse_args()

    if len(tham_so.tep) < 2:
        print("Cần ít nhất hai file kết quả để so sánh — truyền hai đường dẫn hoặc hai tên file.")
        return 1

    cac_lan = [doc_lan_chay(_duong_dan_tu(tep)) for tep in tham_so.tep]

    print(f"So sánh trên bộ ảnh: {tham_so.bo}\n")
    print(so_sanh(cac_lan, bo=tham_so.bo))

    lan_a, lan_b = cac_lan[0], cac_lan[1]
    print("\n--- Đối chiếu ảnh đổi kết quả giữa lần 1 và lần 2 ---")
    print("(Hệ thống có ba kết cục: đúng · sai · từ chối. Từ chối không phải là sai;")
    print(" chỉ trong phần đối chiếu này nó được gộp chung với sai để dò ảnh bị lật —")
    print(" đừng đọc chúng như nhau ở các bảng khác.)")
    tot_len, xau_di = doi_ket_qua(lan_a, lan_b)
    _in_danh_sach("TỐT LÊN — lần 1 sai/từ chối/lỗi, lần 2 trả lời đúng", tot_len, tham_so.so_anh_doi)
    _in_danh_sach("XẤU ĐI — lần 1 đúng, lần 2 sai/từ chối/lỗi", xau_di, tham_so.so_anh_doi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
