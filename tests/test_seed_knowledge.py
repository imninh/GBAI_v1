"""Chống tái phát cho kho tri thức: seed trùng, section sai, thiếu nhãn.

Chạy trên SQLite trong bộ nhớ — không đụng CSDL thật.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.seed import seed_knowledge
from src.db.models import Building, KnowledgeChunk, KnowledgeDoc, WasteCategory
from src.db.seed_data import WASTE_CATEGORIES


def _seed_with_buildings(session: Session) -> None:
    """Seed categories + buildings + knowledge — đủ để knowledge có nơi neo vào."""
    for row in WASTE_CATEGORIES:
        if session.scalar(select(WasteCategory).where(WasteCategory.code == row["code"])) is None:
            session.add(WasteCategory(**row))
    session.flush()

    buildings: dict[str, Building] = {}
    for row in [
        {"code": "S1", "name": "S1", "address": "a", "lat": 1.0, "lng": 1.0},
        {"code": "S2", "name": "S2", "address": "b", "lat": 2.0, "lng": 2.0},
        {"code": "S3", "name": "S3", "address": "c", "lat": 3.0, "lng": 3.0},
    ]:
        b = session.scalar(select(Building).where(Building.code == row["code"]))
        if b is None:
            b = Building(**row)
            session.add(b)
        session.flush()
        buildings[b.code] = b

    seed_knowledge(session, buildings)
    session.commit()


def _count_chunks(session: Session) -> int:
    return len(session.scalars(select(KnowledgeChunk)).all())


# --- Test 1: Seed hai lần liên tiếp → số chunk không tăng ---


def test_seed_hai_lan_khong_sinh_trung(db_session: Session) -> None:
    _seed_with_buildings(db_session)
    so_lan_dau = _count_chunks(db_session)

    _seed_with_buildings(db_session)
    so_lan_hai = _count_chunks(db_session)

    assert so_lan_hai == so_lan_dau, f"Seed hai lần: {so_lan_dau} → {so_lan_hai}"


# --- Test 2: Section cũ không nằm trong KNOWLEDGE_DOCS sẽ bị xoá ---


def test_section_cu_bi_xoa(db_session: Session) -> None:
    """Chèn chunk giả có section lạ vào CSDL → seed lại → chunk đó bị xoá."""
    _seed_with_buildings(db_session)

    # Tìm doc law đầu tiên
    doc = db_session.scalar(
        select(KnowledgeDoc).where(KnowledgeDoc.doc_type == "law")
    )
    assert doc is not None, "Cần ít nhất một doc type=law"

    # Chèn chunk giả có section không nằm trong KNOWLEDGE_DOCS
    fake_section = "Điều 99 — Section giả để test dọn dẹp"
    db_session.add(
        KnowledgeChunk(
            doc_id=doc.id,
            content="Nội dung giả",
            section=fake_section,
            meta={},
        )
    )
    db_session.commit()

    # Seed lại — chunk giả phải bị xoá vì section không nằm trong khai báo
    _seed_with_buildings(db_session)

    sections_con_lai = [
        c.section for c in db_session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc.id)
        ).all()
    ]
    assert fake_section not in sections_con_lai, (
        f"Chunk giả section={fake_section!r} vẫn tồn tại sau khi seed lại"
    )


# --- Test 3: Mọi chunk law phải có khoá needs_verification ---


def test_chunk_law_co_needs_verification(db_session: Session) -> None:
    _seed_with_buildings(db_session)

    law_docs = db_session.scalars(
        select(KnowledgeDoc).where(KnowledgeDoc.doc_type == "law")
    ).all()
    assert len(law_docs) > 0, "Cần ít nhất một doc type=law"

    for doc in law_docs:
        chunks = db_session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc.id)
        ).all()
        for chunk in chunks:
            assert "needs_verification" in chunk.meta, (
                f"Chunk id={chunk.id} section={chunk.section!r} thiếu needs_verification"
            )


# --- Test 4: Không chunk nào gán sai số hiệu Điều 77 ---


def test_khong_chunk_dieu77_sai_noi_dung(db_session: Session) -> None:
    _seed_with_buildings(db_session)

    chunks = db_session.scalars(select(KnowledgeChunk)).all()
    for chunk in chunks:
        if chunk.section.startswith("Điều 77 —"):
            assert "chi phí" not in chunk.content.lower() and "thu gom" not in chunk.content.lower(), (
                f"Chunk id={chunk.id} section={chunk.section!r} "
                "có nội dung chi phí thu gom — có thể gán sai số hiệu"
            )


# --- Test 5: doc.source cập nhật khi KNOWLEDGE_DOCS thay đổi source ---


def test_doc_source_cap_nhat_khi_seed_lai(db_session: Session) -> None:
    """Đổi source trong CSDL → seed lại → source phải khớp khai báo."""
    _seed_with_buildings(db_session)

    # Đổi source trong CSDL thành giá trị cũ
    law_doc = db_session.scalar(
        select(KnowledgeDoc).where(KnowledgeDoc.doc_type == "law").limit(1)
    )
    assert law_doc is not None
    original_source = law_doc.source
    law_doc.source = "SOURCE_DA_DOI"
    db_session.commit()

    # Seed lại với KNOWLEDGE_DOCS gốc — source phải được cập nhật về đúng
    _seed_with_buildings(db_session)

    db_session.expire_all()
    law_doc = db_session.scalar(
        select(KnowledgeDoc).where(KnowledgeDoc.id == law_doc.id)
    )
    assert law_doc.source == original_source, (
        f"source={law_doc.source!r}, kỳ vọng {original_source!r}"
    )
