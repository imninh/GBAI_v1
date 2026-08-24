"""Dọn chunk trùng và sửa số hiệu điều luật trong CSDL production.

    python scripts/don_chunk_trung.py              # chạy khô — in ra sẽ làm gì
    python scripts/don_chunk_trung.py --that --toi-chac-chan   # ghi thật

Mặc định là CHỈ ĐỌC. Chỉ ghi khi có CẢ HAI cờ ``--that`` và ``--toi-chac-chan``.

Trước khi ghi, kiểm tra section của từng id có khớp mô tả ở §2 không.
Không khớp → DỪNG, không ghi gì, báo lại.

⚠️ KHÔNG gọi ``init_db()`` ở bất kỳ nhánh nào. Script này chỉ SELECT/UPDATE/DELETE.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.models import KnowledgeChunk  # noqa: E402
from src.db.session import session_scope  # noqa: E402

# ── Năm dòng会被触碰 ──────────────────────────────────────────────
# Mỗi entry: id, section hiện tại đúng (theo §2), section mới, meta mới.
# Nếu section hiện tại trong CSDL không khớp → DỪNG.

CAP_NHAT = [
    {
        "id": 28,
        "section_hien_tai": "Điều 77 — Nguyên tắc chi trả giá dịch vụ thu gom",
        "section_moi": "Điều 79 — Nguyên tắc chi trả giá dịch vụ thu gom",
        "meta_moi": {"needs_verification": True},
    },
    {
        "id": 29,
        "section_hien_tai": "Điều 79 — Trách nhiệm Ban quản lý chung cư và Chủ đầu tư",
        "section_moi": "Điều 75 — Trách nhiệm Ban quản lý chung cư và Chủ đầu tư",
        "meta_moi": {"needs_verification": True},
    },
    {
        "id": 32,
        "section_hien_tai": "Điều 29 — Phạt vi phạm về quản lý rác nguy hại sinh hoạt",
        "section_moi": "Điều 29 — Phạt vi phạm về quản lý rác nguy hại sinh hoạt",
        "meta_moi": {"needs_verification": True},
    },
]

XOA = [25, 26]


def _in_chunk(chunk: KnowledgeChunk, *, tien: str = "  ") -> None:
    print(f"{tien}id={chunk.id}  section={chunk.section!r}  meta={chunk.meta}")


def chay_kho(session) -> tuple[list[str], list[str]]:
    """Đọc CSDL, kiểm tra, in dự toán. Trả về (danh_sach_loi, danh_sach_hanh_dong)."""
    loi: list[str] = []
    hanh_dong: list[str] = []

    print("\n═══ KIỂM TRA TRƯỚC KHI GHI ═══\n")

    for item in CAP_NHAT:
        chunk = session.get(KnowledgeChunk, item["id"])
        if chunk is None:
            loi.append(f"id {item['id']}: KHÔNG TỒN TẠI trong CSDL")
            continue
        print(f"UPDATE id={item['id']}:")
        _in_chunk(chunk, tien="  TRƯỚC: ")
        print(f"  SAU:  section={item['section_moi']!r}  meta={item['meta_moi']}")
        if chunk.section != item["section_hien_tai"]:
            loi.append(
                f"id {item['id']}: section hiện tại={chunk.section!r} "
                f"KHÔNG KHỚP mô tả={item['section_hien_tai']!r} — CSDL đã đổi so với gói P65"
            )
        if chunk.section == item["section_moi"] and chunk.meta == item["meta_moi"]:
            print("  → ĐÃ ĐÚNG, bỏ qua.")
        else:
            hanh_dong.append(f"UPDATE id={item['id']}")
        print()

    for cid in XOA:
        chunk = session.get(KnowledgeChunk, cid)
        if chunk is None:
            loi.append(f"id {cid}: KHÔNG TỒN TẠI trong CSDL — có thể đã bị xoá")
            continue
        print(f"DELETE id={cid}:")
        _in_chunk(chunk, tien="  SẼ XOÁ: ")
        hanh_dong.append(f"DELETE id={cid}")
        print()

    return loi, hanh_dong


def ghi_that(session) -> int:
    """Thực hiện UPDATE/DELETE. Trả về số dòng bị đụng."""
    dem = 0
    for item in CAP_NHAT:
        chunk = session.get(KnowledgeChunk, item["id"])
        if chunk is None:
            continue
        if chunk.section == item["section_moi"] and chunk.meta == item["meta_moi"]:
            continue
        chunk.section = item["section_moi"]
        chunk.meta = item["meta_moi"]
        dem += 1
        print(f"  OK UPDATE id={item['id']}")

    for cid in XOA:
        chunk = session.get(KnowledgeChunk, cid)
        if chunk is None:
            continue
        session.delete(chunk)
        dem += 1
        print(f"  OK DELETE id={cid}")

    session.flush()
    return dem


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Dọn chunk trùng và sửa số hiệu điều luật")
    parser.add_argument("--that", action="store_true", help="ghi thật (mặc định chỉ đọc)")
    parser.add_argument("--toi-chac-chan", action="store_true", help="xác nhận chắc chắn muốn ghi")
    args = parser.parse_args()

    if args.that and not args.toi_chac_chan:
        print("CAN CẢ HAI cờ --that và --toi-chac-chan để ghi.")
        sys.exit(1)
    if args.toi_chac_chan and not args.that:
        print("  --toi-chac-chan cần đi kèm --that. Đang chạy khô.")
        args.that = False

    print("═" * 56)
    print("  DỌN CHUNK TRÙNG — CHỈ ĐỌC (chạy khô)")
    if args.that:
        print("  CHẾ ĐỘ GHI THẬT")
    print("═" * 56)

    with session_scope() as session:
        loi, hanh_dong = chay_kho(session)

        if loi:
            print("\nDỪNG — phát hiện lỗi dữ liệu:")
            for loi_item in loi:
                print(f"  · {loi_item}")
            print("  Không ghi gì. Kiểm tra lại CSDL.")
            sys.exit(1)

        if not hanh_dong:
            print("Không có gì cần sửa. CSDL đã đúng.")
            return

        if not args.that:
            print(f"\n→ Tổng cộng {len(hanh_dong)} thao tác sẽ thực hiện.")
            print("  Chạy lại với --that --toi-chac-chan để ghi.")
            return

        print("\n═══ GHI THẬT ═══\n")
        dem = ghi_that(session)
        print(f"\nĐã thực hiện {dem} thao tác.")


if __name__ == "__main__":
    main()
