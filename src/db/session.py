"""Quản lý kết nối cơ sở dữ liệu.

Dùng SQLAlchemy để lớp còn lại của hệ thống không phụ thuộc SQLite. Khi
deploy chỉ cần đổi ``DATABASE_URL`` sang PostgreSQL, không sửa code.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings
from src.db.models import Base
from src.db.schema_patch import va_cot_thieu

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _sqlite_path(url: str) -> Path | None:
    """Trích đường dẫn file từ DSN sqlite, trả về None nếu không phải sqlite."""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    return Path(url[len(prefix) :])


def normalize_database_url(url: str) -> str:
    """Sửa DSN cho SQLAlchemy hiểu được.

    Nhiều dịch vụ lưu trữ (Render, Heroku…) phát DSN mở đầu bằng ``postgres://``,
    còn SQLAlchemy 2.x chỉ nhận ``postgresql://``. Không đổi thì máy chủ chết
    ngay lúc khởi động với một câu lỗi khó đoán.
    """
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _them_sslmode(url: str) -> str:
    """Ép ``sslmode=require`` cho mọi URL không phải sqlite nếu chưa có.

    Supabase yêu cầu TLS; DSN chép ra mà thiếu ``sslmode`` sẽ lỗi kiểu khó đoán
    ("server does not support SSL" / "connection requires a valid client
    certificate"). Chèn ``sslmode=require`` vào cuối — dùng ``&`` nếu URL đã có
    query string. SQLite không có khái niệm TLS nên bỏ qua.
    """
    if url.startswith("sqlite"):
        return url
    phan_tach = "&" if "?" in url else "?"
    if "sslmode" in url:
        return url
    return f"{url}{phan_tach}sslmode=require"


def get_engine() -> Engine:
    """Trả về engine dùng chung, tạo lần đầu nếu chưa có."""
    global _engine
    if _engine is not None:
        return _engine

    url = _them_sslmode(normalize_database_url(get_settings().database_url))
    path = _sqlite_path(url)
    connect_args: dict[str, object] = {}
    ky_thuat: dict[str, object] = {}
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # FastAPI chạy handler ở thread khác nhau nên phải tắt kiểm tra thread.
        connect_args["check_same_thread"] = False
    else:
        # Máy chủ miễn phí ngủ khi rảnh và cắt kết nối rỗi; kiểm tra trước mỗi
        # lần dùng để request đầu tiên sau khi thức dậy không chết vì kết nối cũ.
        ky_thuat["pool_pre_ping"] = True

    _engine = create_engine(url, connect_args=connect_args, future=True, **ky_thuat)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


def init_db() -> None:
    """Tạo toàn bộ bảng nếu chưa tồn tại, rồi vá những cột thêm sau.

    Slice 0 dùng cách này cho nhanh. Khi schema ổn định sẽ chuyển sang Alembic
    migration — xem ``docs/decisions/`` để biết lý do hoãn.

    Bước vá cột là bắt buộc: ``create_all`` tạo bảng còn thiếu nhưng không sửa
    bảng đã có, nên CSDL production (Supabase) sẽ thiếu mọi cột được thêm sau
    lần deploy đầu. Trên Render không có chỗ chạy lệnh tay, vá lúc khởi động là
    cách duy nhất chắc chắn chạy.
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    va_cot_thieu(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager tự commit khi thành công, rollback khi có lỗi."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Xoá engine đang cache. Dùng trong test khi đổi DATABASE_URL."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
