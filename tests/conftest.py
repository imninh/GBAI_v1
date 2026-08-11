"""Fixture dùng chung cho test.

Nguyên tắc: **test không bao giờ gọi API thật.** Mọi lệnh gọi model đều đi qua
:class:`FakeVisionClient` để kết quả xác định trước và chi phí bằng 0.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base, WasteCategory
from src.db.seed_data import WASTE_CATEGORIES
from src.services.vision import CategoryOption, Usage, VisionResult


@pytest_asyncio.fixture
async def client():
    """Client HTTP async để test endpoint."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def db_session() -> Iterator[Session]:
    """CSDL SQLite trong bộ nhớ, đã seed sẵn danh mục rác."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()

    for row in WASTE_CATEGORIES:
        session.add(WasteCategory(**row))
    session.commit()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@dataclass
class FakeVisionClient:
    """Model giả lập — trả về đúng thứ test yêu cầu, không đụng mạng."""

    provider_name: str = "fake"
    results: list[VisionResult] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def _next(self, model: str, kind: str) -> VisionResult:
        self.calls.append((kind, model))
        if not self.results:
            raise AssertionError("FakeVisionClient hết kết quả nhưng vẫn bị gọi thêm")
        result = self.results.pop(0)
        result.model = model
        result.provider = self.provider_name
        return result

    def classify_image(self, image_bytes: bytes, categories: list[CategoryOption], model: str) -> VisionResult:
        return self._next(model, "image")

    def classify_text(self, text: str, categories: list[CategoryOption], model: str) -> VisionResult:
        return self._next(model, "text")


def make_result(
    *,
    item_name: str = "Hộp sữa giấy tráng nhôm",
    category_code: str = "recyclable_paper",
    confidence: float = 0.91,
    suspect_hazardous: bool = False,
    quality_issue: str = "",
    items: list[dict] | None = None,
    tokens_in: int = 800,
    tokens_out: int = 60,
    cost_usd: float = 0.0018,
) -> VisionResult:
    """Tạo nhanh một kết quả model giả lập.

    ``items`` mặc định là **đúng một món khớp với chính nhãn vừa chọn** — đó là
    hành vi của một model tuân thủ prompt, vốn bắt ``items`` không bao giờ rỗng
    (xem ``_SYSTEM_PROMPT``). Muốn giả lập model KHÔNG tuân thủ để kiểm nhánh
    leo tầng thì truyền thẳng ``items=[]``.
    """
    return VisionResult(
        item_name=item_name,
        category_code=category_code,
        confidence=confidence,
        suspect_hazardous=suspect_hazardous,
        quality_issue=quality_issue,
        items=items if items is not None else [
            {"name": item_name, "category_code": category_code, "confidence": confidence}
        ],
        usage=Usage(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd, price_known=True),
    )
