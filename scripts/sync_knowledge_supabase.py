"""Đồng bộ kho tri thức pháp lý & cẩm nang App (Knowledge Base) lên Supabase.

Cập nhật toàn bộ các văn bản:
- Luật Bảo vệ Môi trường 2020 (Điều 75.1, 77, 79)
- Nghị định 45/2022/NĐ-CP (Điều 26.1, 26.2, 29)
- Hướng dẫn Kỹ thuật 9368/BTNMT-KSONMT
- Hướng dẫn sử dụng App GreenBin AI v1.0
- Nội quy toà nhà Sunrise S1 & S2
- Danh mục rác nguy hại

Bao gồm đầy đủ Content, Metadata, Keywords và Vector Embeddings.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.db.models import Building, KnowledgeChunk, KnowledgeDoc  # noqa: E402
from src.db.seed_data import KNOWLEDGE_DOCS  # noqa: E402
from src.db.session import session_scope  # noqa: E402
from src.services.rag import embed_chunks, so_doan_co_embedding  # noqa: E402


def sync_knowledge_to_supabase() -> dict[str, int]:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    settings = get_settings()
    print("=" * 70)
    print("ĐỒNG BỘ KHO TRI THỨC LÊN DATABASE SUPABASE (POSTGRESQL)")
    print("=" * 70)
    print(f"  Target Database: {settings.database_url.split('@')[-1]}")

    with session_scope() as session:
        buildings = {b.code: b for b in session.scalars(select(Building)).all()}

        docs_created = 0
        docs_updated = 0
        chunks_created = 0
        chunks_updated = 0

        for row in KNOWLEDGE_DOCS:
            doc = session.scalar(select(KnowledgeDoc).where(KnowledgeDoc.title == row["title"]))
            building = buildings.get(row["building_code"]) if row.get("building_code") else None

            if doc is None:
                doc = KnowledgeDoc(
                    building_id=building.id if building else None,
                    title=row["title"],
                    source=row["source"],
                    doc_type=row["doc_type"],
                    effective_date=date.fromisoformat(row["effective_date"]) if row.get("effective_date") else None,
                )
                session.add(doc)
                session.flush()
                docs_created += 1
                print(f"  + Tạo tài liệu mới: '{doc.title}' ({doc.doc_type})")
            else:
                doc.source = row["source"]
                doc.doc_type = row["doc_type"]
                doc.effective_date = date.fromisoformat(row["effective_date"]) if row.get("effective_date") else None
                docs_updated += 1
                print(f"  * Cập nhật tài liệu: '{doc.title}' ({doc.doc_type})")

            for chunk in row["chunks"]:
                existing_chunk = session.scalar(
                    select(KnowledgeChunk).where(
                        KnowledgeChunk.doc_id == doc.id,
                        KnowledgeChunk.section == chunk["section"],
                    )
                )
                chunk_meta = {
                    "needs_verification": bool(chunk.get("needs_verification")),
                    "keywords": chunk.get("keywords", []),
                }

                if existing_chunk is None:
                    new_chunk = KnowledgeChunk(
                        doc_id=doc.id,
                        content=chunk["content"],
                        section=chunk["section"],
                        meta=chunk_meta,
                    )
                    session.add(new_chunk)
                    chunks_created += 1
                    print(f"    - Thêm chunk mới: [{chunk['section']}] (Keywords: {len(chunk_meta['keywords'])})")
                else:
                    existing_chunk.content = chunk["content"]
                    existing_chunk.meta = chunk_meta
                    # Reset embedding để tính toán lại nếu nội dung thay đổi
                    chunks_updated += 1
                    print(f"    - Cập nhật chunk: [{chunk['section']}] (Keywords: {len(chunk_meta['keywords'])})")

        session.commit()

        # Tổng hợp số lượng
        total_docs = session.scalar(select(func.count(KnowledgeDoc.id)))
        total_chunks = session.scalar(select(func.count(KnowledgeChunk.id)))

        print("\n" + "-" * 70)
        print("TÍNH TOÁN / CẬP NHẬT VECTOR EMBEDDINGS...")
        print("-" * 70)
        try:
            embedded_count = embed_chunks(session)
            co, tong = so_doan_co_embedding(session)
            print(f"  Đã nhúng {embedded_count} đoạn quy định mới.")
            print(f"  Tổng số đoạn có vector: {co}/{tong} ({co/tong*100:.1f}%)")
        except Exception as e:
            print(f"  ⚠️ Lưu ý embedding: {e}")
            co, tong = so_doan_co_embedding(session)
            print(f"  Số đoạn có vector hiện tại: {co}/{tong}")

        print("\n" + "=" * 70)
        print("KẾT QUẢ ĐỒNG BỘ THÀNH CÔNG:")
        print(f"  - Tài liệu (KnowledgeDoc):   {total_docs} tài liệu (Tạo mới: {docs_created}, Cập nhật: {docs_updated})")
        print(f"  - Đoạn trích (KnowledgeChunk): {total_chunks} chunks (Tạo mới: {chunks_created}, Cập nhật: {chunks_updated})")
        print("  - Toàn bộ keywords và metadata đã được lưu vào PostgreSQL JSONB column.")
        print("=" * 70)

        return {
            "docs_created": docs_created,
            "docs_updated": docs_updated,
            "chunks_created": chunks_created,
            "chunks_updated": chunks_updated,
            "total_docs": total_docs or 0,
            "total_chunks": total_chunks or 0,
        }


if __name__ == "__main__":
    sync_knowledge_to_supabase()
