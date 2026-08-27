"""Động cơ Idempotency & Deduplication cho Chatbot Tool Execution (HAX G9 & Tool Boundary).

Ngăn chặn gọi trùng lặp tác vụ ghi (đặt lịch thu gom cồng kềnh, báo sự cố thùng)
khi người dùng lặp lại câu hỏi hoặc agent retry.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import ToolExecutionRecord, User
from src.db.models_base import utcnow

# TTL mặc định cho Idempotency Key (120 giây)
DEFAULT_IDEMPOTENCY_TTL_SECONDS = 120


def compute_idempotency_key(
    tool_name: str,
    args: dict[str, Any],
    *,
    user_id: int | None = None,
    session_id: str | None = None,
) -> str:
    """Sinh khóa Idempotency duy nhất từ (tool_name, canonical_args, user_id, session_id)."""
    canonical_args = json.dumps(args, sort_keys=True, ensure_ascii=False)
    raw = f"{tool_name}:{canonical_args}:{user_id or 0}:{session_id or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def execute_tool_idempotent(
    session: Session,
    tool_name: str,
    args: dict[str, Any],
    handler: Callable[..., dict[str, Any]],
    *,
    user: User | None = None,
    session_id: str | None = None,
    ttl_seconds: int = DEFAULT_IDEMPOTENCY_TTL_SECONDS,
) -> tuple[dict[str, Any], bool]:
    """Thực thi tool có bảo vệ Idempotency.

    Returns:
        (result_dict, is_deduplicated)
    """
    user_id = user.id if user else None
    key = compute_idempotency_key(tool_name, args, user_id=user_id, session_id=session_id)
    now = utcnow()
    threshold = now - timedelta(seconds=ttl_seconds)

    # 1. Kiểm tra bản ghi đã thực thi trước đó trong khoảng TTL
    existing = session.scalars(
        select(ToolExecutionRecord)
        .where(
            ToolExecutionRecord.idempotency_key == key,
            ToolExecutionRecord.created_at >= threshold,
        )
        .order_by(ToolExecutionRecord.created_at.desc())
    ).first()

    if existing is not None and existing.result_json:
        cached_result = dict(existing.result_json)
        cached_result["_deduplicated"] = True
        cached_result["_idempotency_key"] = key
        return cached_result, True

    # 2. Thực thi hàm handler nghiệp vụ
    result = handler(session, args, user=user, session_id=session_id)
    result["_deduplicated"] = False
    result["_idempotency_key"] = key

    # 3. Lưu lại bản ghi thực thi
    record = ToolExecutionRecord(
        idempotency_key=key,
        tool_name=tool_name,
        user_id=user_id,
        session_id=session_id,
        status="COMPLETED",
        result_json=result,
        created_at=now,
    )
    session.add(record)
    session.flush()

    return result, False
