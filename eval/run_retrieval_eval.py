"""Đo chất lượng truy hồi RAG: **thuần BM25** so với **hybrid BM25 + embedding**.

Đây là phép đo cho PLO 3 (*"RAG vượt naive, có đo lường"*). Trước ngày 02/08/2026
phần embedding tuy có code nhưng **chưa từng được nối dây**, nên câu "hybrid"
trong tài liệu chưa đúng với thực tế. Script này vừa nối vừa chứng minh.

Chỉ số:

``hit@k``
    Trong ``k`` đoạn đầu có ít nhất một đoạn đúng không. Đây là chỉ số hợp lý
    nhất ở đây vì mỗi câu chỉ có 1–2 đoạn đúng.
``MRR``
    Nghịch đảo thứ hạng của đoạn đúng đầu tiên. Nhạy với việc đoạn đúng nằm ở
    hạng 1 hay hạng 3 — thứ ``hit@5`` không phân biệt được.

Cố ý **không** báo ``precision@5``: mỗi câu chỉ có 1–2 đoạn đúng nên chỉ số đó
trần cứng ở 0,2–0,4 và đọc lên chỉ gây hiểu nhầm. ``CLAUDE.md`` mục 7 ghi
precision@5 — nên sửa lại thành hit@k + MRR.

Chạy::

    python eval/run_retrieval_eval.py            # cần API key để nhúng câu hỏi
    python eval/run_retrieval_eval.py --chi-bm25 # không gọi API

Lệnh gọi nhúng câu hỏi **có cache đĩa**, nên chạy lại lần hai gần như không tốn
quota.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from eval.retrieval_questions import CAU_HOI_TRUY_HOI  # noqa: E402
from src.db.models import Building  # noqa: E402
from src.db.session import session_scope  # noqa: E402
from src.services import rag  # noqa: E402

_TOP_K = 5


def _hang_dung(chunks: list, dung: set[str]) -> int:
    """Thứ hạng (1-based) của đoạn đúng đầu tiên. 0 nếu không có đoạn nào đúng."""
    for thu_hang, chunk in enumerate(chunks, start=1):
        if chunk.section in dung:
            return thu_hang
    return 0


def _do(session, dung_embedding: bool) -> dict[str, float]:
    toa = {b.code: b.id for b in session.scalars(select(Building)).all()}
    hang: list[int] = []
    sai: list[tuple[str, str]] = []

    for cau, ma_toa, dap_an in CAU_HOI_TRUY_HOI:
        query_embedding = rag.embed_query(cau) if dung_embedding else []
        chunks = rag.retrieve(
            session, cau, building_id=toa.get(ma_toa), top_k=_TOP_K, query_embedding=query_embedding
        )
        thu_hang = _hang_dung(chunks, dap_an)
        hang.append(thu_hang)
        if thu_hang != 1:
            thuc_te = chunks[0].section if chunks else "(không trả ra gì)"
            sai.append((cau, thuc_te))

    tong = len(hang) or 1
    return {
        "hit@1": sum(1 for h in hang if h == 1) / tong,
        "hit@3": sum(1 for h in hang if 1 <= h <= 3) / tong,
        "hit@5": sum(1 for h in hang if h >= 1) / tong,
        "mrr": sum(1 / h for h in hang if h) / tong,
        "_sai": sai,  # type: ignore[dict-item]
    }


def _quet_trong_so(session) -> None:
    """Quét ``RAG_VECTOR_WEIGHT`` để chọn trọng số dựa trên số đo, không phải cảm tính.

    Đọc kỹ cảnh báo ở cuối: bộ câu hỏi hiện tại thiên vị embedding.
    """
    from src.config import get_settings, reset_settings_cache

    goc = get_settings().rag_vector_weight
    print(f"{'vector':>8s} {'hit@1':>8s} {'hit@3':>8s} {'MRR':>8s}")
    print("-" * 36)
    for trong_so in (0.0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0):
        os.environ["RAG_VECTOR_WEIGHT"] = str(trong_so)
        reset_settings_cache()
        ket_qua = _do(session, dung_embedding=trong_so > 0)
        danh_dau = "  ← đang dùng" if abs(trong_so - goc) < 1e-9 else ""
        print(
            f"{trong_so:8.2f} {ket_qua['hit@1']:8.3f} {ket_qua['hit@3']:8.3f} {ket_qua['mrr']:8.3f}{danh_dau}"
        )
    os.environ.pop("RAG_VECTOR_WEIGHT", None)
    reset_settings_cache()
    print(
        "\n⚠ Bộ câu hỏi hiện tại cố ý viết theo lối nói cư dân, không chép chữ trong\n"
        "  văn bản quy định — tức là thiên vị embedding và bất lợi cho BM25. Đừng chốt\n"
        "  trọng số theo bảng này cho tới khi có đủ ~60 câu, gồm cả câu gõ đúng thuật ngữ."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo truy hồi RAG: BM25 vs hybrid")
    parser.add_argument("--chi-bm25", action="store_true", help="không gọi API nhúng, chỉ đo BM25")
    parser.add_argument("--quet-trong-so", action="store_true", help="quét RAG_VECTOR_WEIGHT từ 0 đến 1")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    with session_scope() as session:
        co, tong_doan = rag.so_doan_co_embedding(session)
        print(f"Kho quy định: {co}/{tong_doan} đoạn có vector · {len(CAU_HOI_TRUY_HOI)} câu hỏi\n")

        if args.quet_trong_so:
            if co == 0:
                print("⚠ Chưa đoạn nào có vector — chạy `python scripts/seed.py --embed` trước.")
                return 1
            _quet_trong_so(session)
            return 0

        bm25 = _do(session, dung_embedding=False)
        hybrid = None
        if not args.chi_bm25:
            if co == 0:
                print("⚠ Chưa đoạn nào có vector — chạy `python scripts/seed.py --embed` trước.\n")
            else:
                hybrid = _do(session, dung_embedding=True)

        print(f"{'Chỉ số':10s} {'BM25':>10s} {'Hybrid':>10s}")
        print("-" * 32)
        for khoa in ("hit@1", "hit@3", "hit@5", "mrr"):
            cot_hybrid = f"{hybrid[khoa]:.3f}" if hybrid else "—"
            print(f"{khoa:10s} {bm25[khoa]:>10.3f} {cot_hybrid:>10s}")

        nguon = hybrid or bm25
        ten = "hybrid" if hybrid else "BM25"
        if nguon["_sai"]:
            print(f"\nCác câu {ten} chưa đưa đoạn đúng lên hạng 1 ({len(nguon['_sai'])} câu):")
            for cau, thuc_te in nguon["_sai"]:  # type: ignore[union-attr]
                print(f"  · {cau!r} → {thuc_te}")
            print("\nĐây là danh sách việc cần làm cho vòng cải tiến sau (PLO 7),")
            print("không phải con số để giấu đi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
