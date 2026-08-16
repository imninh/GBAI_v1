"""Test truy hồi quy định và node advise."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Building, KnowledgeChunk, KnowledgeDoc, WasteCategory
from src.services import rag


@pytest.fixture
def kho_quy_dinh(db_session: Session) -> dict[str, int]:
    """Hai toà, mỗi toà một nội quy khác nhau, cộng một tài liệu dùng chung."""
    s1 = Building(code="S1", name="Toà S1")
    s2 = Building(code="S2", name="Toà S2")
    db_session.add_all([s1, s2])
    db_session.flush()

    doc_s1 = KnowledgeDoc(building_id=s1.id, title="Nội quy toà S1", doc_type="building_rule", source="noi-quy-s1")
    doc_s2 = KnowledgeDoc(building_id=s2.id, title="Nội quy toà S2", doc_type="building_rule", source="noi-quy-s2")
    doc_chung = KnowledgeDoc(building_id=None, title="Danh mục rác nguy hại", doc_type="hazard", source="danh-muc")
    db_session.add_all([doc_s1, doc_s2, doc_chung])
    db_session.flush()

    db_session.add_all(
        [
            KnowledgeChunk(
                doc_id=doc_s1.id,
                section="Mục 4.2",
                content="Rác tái chế của toà S1 thu gom thứ Ba, thứ Năm, thứ Bảy khung 18:00-20:00 tại thùng xanh dương.",
            ),
            KnowledgeChunk(
                doc_id=doc_s2.id,
                section="Mục 3.1",
                content="Rác tái chế của toà S2 thu gom thứ Ba và thứ Sáu khung 17:00-19:00.",
            ),
            KnowledgeChunk(
                doc_id=doc_chung.id,
                section="Pin và ắc quy",
                content="Pin và ắc quy chứa kim loại nặng, không làm thủng, không đốt, mang tới điểm thu gom tầng hầm.",
                meta={"needs_verification": False},
            ),
        ]
    )
    db_session.commit()
    return {"s1": s1.id, "s2": s2.id}


def test_truy_hoi_dung_quy_dinh_cua_toa_dang_hoi(db_session: Session, kho_quy_dinh: dict[str, int]) -> None:
    ket_qua = rag.retrieve(db_session, "rác tái chế thu gom lúc mấy giờ", building_id=kho_quy_dinh["s1"])

    assert ket_qua, "Phải truy hồi được ít nhất một đoạn"
    tieu_de = {c.doc_title for c in ket_qua}
    assert "Nội quy toà S1" in tieu_de
    assert "Nội quy toà S2" not in tieu_de, "Trộn quy định toà khác vào là trả lời sai"


def test_tai_lieu_dung_chung_van_duoc_lay_kem(db_session: Session, kho_quy_dinh: dict[str, int]) -> None:
    ket_qua = rag.retrieve(db_session, "pin cũ bỏ ở đâu", building_id=kho_quy_dinh["s1"])

    assert any(c.doc_title == "Danh mục rác nguy hại" for c in ket_qua)


def test_xep_hang_dua_doan_lien_quan_nhat_len_dau(db_session: Session, kho_quy_dinh: dict[str, int]) -> None:
    ket_qua = rag.retrieve(db_session, "pin ắc quy có làm thủng được không", building_id=kho_quy_dinh["s1"])

    assert ket_qua[0].section == "Pin và ắc quy"
    assert ket_qua[0].score > 0


def test_khong_co_tai_lieu_khop_thi_tra_ve_rong(db_session: Session, kho_quy_dinh: dict[str, int]) -> None:
    assert rag.retrieve(db_session, "zzzzz qqqqq", building_id=kho_quy_dinh["s1"]) == []


def test_nguon_tra_ve_du_thong_tin_de_ve_chip(db_session: Session, kho_quy_dinh: dict[str, int]) -> None:
    nguon = rag.retrieve(db_session, "rác tái chế", building_id=kho_quy_dinh["s1"])[0].as_source_dict()

    assert {"doc_title", "section", "quote", "chunk_id", "score"} <= set(nguon)
    assert nguon["quote"], "Chip nguồn bấm vào phải hiện được nguyên văn đoạn trích"


def test_bo_dau_van_khop_tu_khoa() -> None:
    assert rag.tokenize("Thùng rác tái chế") == ["thung", "rac", "tai", "che"]


def test_advise_khong_goi_duoc_model_thi_lui_ve_huong_dan_chuan(
    db_session: Session, kho_quy_dinh: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trạng thái suy giảm một phần: vẫn trả lời được, và nói rõ là đang suy giảm."""
    from src.services.vision import VisionUnavailableError

    def khong_co_key(tier: str = "text"):
        raise VisionUnavailableError("Chưa cấu hình API key", code="VISION-401")

    monkeypatch.setattr("src.services.vision.get_vision_client", khong_co_key)

    category = db_session.scalar(select(WasteCategory).where(WasteCategory.code == "recyclable_paper"))
    ket_qua = rag.advise(
        db_session,
        item_name="Hộp sữa giấy",
        category=category,
        building_id=kho_quy_dinh["s1"],
        query="rác tái chế thu gom lúc nào",
    )

    assert ket_qua.advice, "Suy giảm không có nghĩa là im lặng"
    assert ket_qua.generated_by == "template"
    assert ket_qua.degraded is True
    assert ket_qua.sources, "Vẫn phải chỉ ra được nguồn"


def test_advise_khong_truy_hoi_duoc_thi_bao_suy_giam(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.services.vision import VisionUnavailableError

    monkeypatch.setattr(
        "src.services.vision.get_vision_client",
        lambda tier="text": (_ for _ in ()).throw(VisionUnavailableError("khong co key")),
    )
    category = db_session.scalar(select(WasteCategory).where(WasteCategory.code == "organic"))

    ket_qua = rag.advise(db_session, item_name="Vỏ chuối", category=category, building_id=None)

    assert ket_qua.degraded is True
    assert "hướng dẫn chung" in ket_qua.degraded_note or "danh mục" in ket_qua.degraded_note


# --- Phần embedding của RAG (nối dây ngày 02/08) -------------------------


@pytest.fixture
def _cache_rieng(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Cache embedding ghi vào thư mục tạm, không đụng cache thật của máy."""
    from src.config import reset_settings_cache

    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_khong_co_model_embedding_thi_tra_rong_chu_khong_goi_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider không có endpoint embedding dùng được (đo được: NVIDIA).

    Phải im lặng lui về BM25, không gọi rồi hỏng liên tục mỗi request.
    """
    from src.config import reset_settings_cache

    monkeypatch.setenv("EMBEDDING_PROVIDER", "nvidia")
    monkeypatch.setenv("EMBEDDING_MODEL", "")
    reset_settings_cache()

    def khong_duoc_goi(*args, **kwargs):
        raise AssertionError("Không có model embedding mà vẫn dựng client là tốn quota vô ích")

    monkeypatch.setattr("src.services.vision.build_client_for", khong_duoc_goi)

    assert rag.embed_texts(["pin cũ bỏ ở đâu"]) == []
    reset_settings_cache()


def test_nhung_cau_hoi_co_cache_dia(monkeypatch: pytest.MonkeyPatch, _cache_rieng) -> None:
    """CLAUDE.md mục 9: cache mọi lệnh gọi LLM theo hash đầu vào.

    Trong chung cư cùng một món rác bị hỏi đi hỏi lại rất nhiều lần.
    """
    dem = {"n": 0}

    def gia(texts: list[str]) -> list[list[float]]:
        dem["n"] += 1
        return [[0.1, 0.2, 0.3]]

    monkeypatch.setattr(rag, "embed_texts", gia)

    a = rag.embed_query("pin cũ bỏ ở đâu")
    b = rag.embed_query("pin cũ bỏ ở đâu")

    assert a == b == [0.1, 0.2, 0.3]
    assert dem["n"] == 1, "Hỏi lại cùng một câu mà vẫn gọi API lần nữa"


def test_cau_hoi_khac_nhau_thi_khong_dung_nham_cache(
    monkeypatch: pytest.MonkeyPatch, _cache_rieng
) -> None:
    ket_qua = {"pin cũ bỏ ở đâu": [1.0, 0.0], "hộp sữa giấy": [0.0, 1.0]}
    monkeypatch.setattr(rag, "embed_texts", lambda texts: [ket_qua[texts[0]]])

    assert rag.embed_query("pin cũ bỏ ở đâu") == [1.0, 0.0]
    assert rag.embed_query("hộp sữa giấy") == [0.0, 1.0]


def test_kho_chua_nhung_thi_advise_khong_goi_embedding(
    db_session: Session, kho_quy_dinh: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Không có vector nào để so thì nhúng câu hỏi chỉ là đốt quota."""

    def khong_duoc_goi(*args, **kwargs):
        raise AssertionError("Kho chưa có vector mà vẫn nhúng câu hỏi")

    monkeypatch.setattr(rag, "embed_query", khong_duoc_goi)
    monkeypatch.setattr(
        "src.services.vision.get_vision_client",
        lambda tier="text": (_ for _ in ()).throw(rag.VisionUnavailableError("khong goi model")),
    )
    category = db_session.scalar(select(WasteCategory).where(WasteCategory.code == "recyclable_paper"))

    ket_qua = rag.advise(
        db_session,
        item_name="Hộp sữa giấy",
        category=category,
        building_id=kho_quy_dinh["s1"],
        query="rác tái chế thu gom lúc nào",
    )

    assert ket_qua.sources, "Vẫn phải truy hồi được bằng BM25"


def test_kho_da_nhung_thi_advise_co_dung_embedding(
    db_session: Session, kho_quy_dinh: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    for chunk in db_session.scalars(select(KnowledgeChunk)).all():
        chunk.embedding = [0.0, 1.0]
    db_session.commit()

    da_goi = {"n": 0}

    def gia(text: str) -> list[float]:
        da_goi["n"] += 1
        return [0.0, 1.0]

    monkeypatch.setattr(rag, "embed_query", gia)
    monkeypatch.setattr(
        "src.services.vision.get_vision_client",
        lambda tier="text": (_ for _ in ()).throw(rag.VisionUnavailableError("khong goi model")),
    )
    category = db_session.scalar(select(WasteCategory).where(WasteCategory.code == "recyclable_paper"))

    rag.advise(db_session, item_name="Hộp sữa giấy", category=category, building_id=kho_quy_dinh["s1"])

    assert da_goi["n"] == 1


def test_nhung_kho_quy_dinh_goi_lai_nhieu_lan_vo_hai(
    db_session: Session, kho_quy_dinh: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rag, "embed_texts", lambda texts: [[0.5, 0.5] for _ in texts])

    lan_dau = rag.embed_chunks(db_session)
    lan_hai = rag.embed_chunks(db_session)

    assert lan_dau == 3
    assert lan_hai == 0, "Chạy lại phải bỏ qua đoạn đã có vector"
    assert rag.so_doan_co_embedding(db_session) == (3, 3)


def test_trong_so_vector_doi_duoc_thu_hang(
    db_session: Session, kho_quy_dinh: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trọng số phải thật sự có tác dụng — nếu không thì phép quét trong eval là vô nghĩa."""
    from src.config import reset_settings_cache

    doan = db_session.scalars(select(KnowledgeChunk)).all()
    for chunk in doan:
        chunk.embedding = [1.0, 0.0] if chunk.section == "Pin và ắc quy" else [0.0, 1.0]
    db_session.commit()

    def xep_hang(trong_so: float) -> str:
        monkeypatch.setenv("RAG_VECTOR_WEIGHT", str(trong_so))
        reset_settings_cache()
        ket_qua = rag.retrieve(
            db_session, "rác tái chế thu gom lúc mấy giờ", building_id=kho_quy_dinh["s1"],
            query_embedding=[1.0, 0.0],
        )
        return ket_qua[0].section if ket_qua else ""

    thuan_tu_khoa = xep_hang(0.0)
    thuan_vector = xep_hang(1.0)
    reset_settings_cache()

    assert thuan_tu_khoa != thuan_vector
    assert thuan_vector == "Pin và ắc quy", "Trọng số vector = 1 phải cho đoạn khớp vector lên đầu"


def test_khong_co_vector_thi_van_xep_hang_duoc_bang_bm25(
    db_session: Session, kho_quy_dinh: dict[str, int]
) -> None:
    """Mất API vẫn phải truy hồi được — đây là lý do BM25 không bị bỏ."""
    ket_qua = rag.retrieve(
        db_session, "pin cũ", building_id=kho_quy_dinh["s1"], query_embedding=[]
    )

    assert ket_qua
    assert all(c.vector_score == 0.0 for c in ket_qua)
