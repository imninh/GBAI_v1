"""In kết quả eval ra bảng Markdown dán thẳng được vào ``eval/results/report.md``.

Tách khỏi :mod:`eval.run_eval` cho gọn — module này chỉ định dạng, không tính
toán và không chạm vào CSDL.
"""

from __future__ import annotations

from collections.abc import Callable

from eval.metrics import NHAN_TU_CHOI, TongHop


def _pt(x: float) -> str:
    """Số phần trăm theo lối viết Việt Nam (dấu phẩy thập phân)."""
    return f"{x * 100:.1f}".replace(".", ",") + "%"


def _so(x: float) -> str:
    """Số thập phân 3 chữ số, dấu phẩy kiểu Việt Nam."""
    return f"{x:.3f}".replace(".", ",")


def in_bao_cao(tong: dict[str, TongHop], ma_nguy_hai: set[str]) -> None:
    """In bảng tổng hợp, hai bộ ảnh **tách cột** chứ không gộp một con số."""
    bo_list = list(tong)
    if not bo_list:
        return

    print("\n## Tổng hợp\n")
    print("| Chỉ số | " + " | ".join(bo_list) + " |")
    print("|---|" + "---|" * len(bo_list))

    dong: list[tuple[str, Callable[[TongHop], str]]] = [
        ("Số ảnh", lambda t: str(t.so_anh)),
        ("Tỉ lệ trả lời", lambda t: _pt(t.ty_le_tra_loi)),
        ("Accuracy (trên ảnh đã trả lời)", lambda t: _pt(t.accuracy_khi_tra_loi)),
        ("Accuracy (trên mọi ảnh)", lambda t: _pt(t.accuracy_toan_bo)),
        ("Macro-F1", lambda t: _so(t.macro_f1)),
        ("Recall nhóm nguy hại", lambda t: _pt(t.recall_nguy_hai) if t.so_anh_nguy_hai else "— (không có ảnh)"),
        (
            "**Nguy hại → rác thường** (mục tiêu 0%)",
            lambda t: f"**{_pt(t.ty_le_nguy_hai_thanh_thuong)}**" if t.so_anh_nguy_hai else "— (không có ảnh)",
        ),
        ("Rác thường → nguy hại (báo động nhầm)", lambda t: _pt(t.ty_le_thuong_thanh_nguy_hai)),
        ("Độ trễ p50", lambda t: f"{t.latency_p50_ms} ms"),
        ("Độ trễ p95", lambda t: f"{t.latency_p95_ms} ms"),
        ("Chi phí", lambda t: f"${t.tong_chi_phi_usd:.4f}" + ("" if t.du_gia else " (thiếu giá)")),
        ("Ảnh lỗi", lambda t: str(t.so_loi)),
    ]
    for ten, lay in dong:
        print(f"| {ten} | " + " | ".join(lay(tong[bo]) for bo in bo_list) + " |")

    print("\n> Đọc `Accuracy` mà bỏ qua `Tỉ lệ trả lời` là đọc sai: từ chối 90% số ảnh")
    print("> thì accuracy 100% cũng vô nghĩa. Từ chối là hành vi có chủ ý, không phải lỗi.")

    for bo in bo_list:
        t = tong[bo]
        if not t.so_anh:
            continue
        print(f"\n### Theo nhóm rác — {bo}\n")
        print("| Nhóm | Số ảnh | Precision | Recall | F1 |")
        print("|---|---|---|---|---|")
        for cs in t.theo_nhom:
            if not cs.support:
                continue
            dau = " ⚠" if cs.nhan in ma_nguy_hai else ""
            print(
                f"| `{cs.nhan}`{dau} | {cs.support} | {_so(cs.precision)} | {_so(cs.recall)} | {_so(cs.f1)} |"
            )
        if t.theo_tier:
            phan_bo = " · ".join(f"{tier} {so}" for tier, so in sorted(t.theo_tier.items()))
            print(f"\nTầng đã dùng: {phan_bo}")
        if t.ly_do_tu_choi:
            ly_do = " · ".join(f"{ly} {so}" for ly, so in sorted(t.ly_do_tu_choi.items(), key=lambda kv: -kv[1]))
            print(f"Lý do từ chối: {ly_do}")


def in_ma_tran(matran: dict[str, dict[str, int]], nhan_list: list[str]) -> None:
    """In ma trận nhầm lẫn. Hàng = nhãn đúng, cột = nhãn hệ thống trả ra.

    Chỉ in các hàng có ảnh, để bảng không loãng vì những nhóm chưa chụp được ảnh nào.
    """
    co_anh = [nhan for nhan in nhan_list if sum(matran.get(nhan, {}).values()) > 0]
    if not co_anh:
        return
    cot = [*co_anh, NHAN_TU_CHOI]

    def _ngan(ten: str) -> str:
        return ten if len(ten) <= 10 else ten[:9] + "…"

    print()
    print("| đúng ↓ / đoán → | " + " | ".join(_ngan(c) for c in cot) + " |")
    print("|---|" + "---|" * len(cot))
    for hang in co_anh:
        o = [str(matran[hang].get(c, 0)) if matran[hang].get(c, 0) else "·" for c in cot]
        print(f"| `{hang}` | " + " | ".join(o) + " |")
