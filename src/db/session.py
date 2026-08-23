"""Quản lý kết nối cơ sở dữ liệu.

Dùng SQLAlchemy để lớp còn lại của hệ thống không phụ thuộc SQLite. Khi
deploy chỉ cần đổi ``DATABASE_URL`` sang PostgreSQL, không sửa code.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings
from src.db.models import Base
from src.db.schema_patch import va_cot_thieu

# Các host được coi là MÁY CỤC BỘ — kết nối tới chúng không phải CSDL xa.
_CAC_HOST_DIA_PHUONG = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

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


def _la_csdl_xa(url: str) -> bool:
    """CSDL XA = không phải sqlite VÀ host không thuộc nhóm máy cục bộ."""
    if url.startswith("sqlite"):
        return False
    host = (urlparse(url).hostname or "").lower()
    return host not in _CAC_HOST_DIA_PHUONG


def chan_khong_ghi_csdl_xa() -> None:
    """Chốt chặn: từ chối tự tạo/vá bảng trên CSDL xa khi chưa deploy production.

    Được gọi ở dòng đầu của :func:`init_db`, TRƯỚC ``create_all``. Trước đây
    ``.env`` trên máy phát triển trỏ thẳng vào Supabase production, nên chỉ cần
    chạy app (hoặc một script dùng ``.env`` mặc định) là bảng tự mọc trên CSDL
    thật — đã xảy ra với bốn bảng mới đợt vừa qua. Chốt này chặn đường đó.

    Luật:
        CSDL XA = database_url không bắt đầu bằng "sqlite"
                   VÀ host không thuộc {localhost, 127.0.0.1, ::1, 0.0.0.0}.

        TỪ CHỐI (ném RuntimeError) khi: là CSDL XA
                                  VÀ app_env != "production"
                                  VÀ biến môi trường CHO_PHEP_GHI_DB_XA != "1".

    Cửa thoát hai lớp ``CHO_PHEP_GHI_DB_XA=1`` là CỐ Ý — đi đúng khuôn dự án đã
    dùng cho ``--reset`` (``CHO_PHEP_XOA_DB=1``): người vận hành muốn vá lược đồ
    production bằng tay vẫn làm được, nhưng phải gõ thêm một biến, không lỡ tay.

    Raises:
        RuntimeError: khi phát hiện nguy hiểm. Thông báo viết tiếng Việt, che mật
        khẩu (không in ``user:pass``), không in nguyên chuỗi kết nối.
    """
    settings = get_settings()
    url = settings.database_url
    if not _la_csdl_xa(url):
        return
    if settings.app_env == "production":
        return
    if os.environ.get("CHO_PHEP_GHI_DB_XA") == "1":
        return

    host = urlparse(url).hostname or "?"
    cong = urlparse(url).port or ""
    thong_bao = (
        f"CHỐT CHẶN: không được tự tạo/vá bảng trên CSDL xa ({host}:{cong}) "
        f"khi APP_ENV={settings.app_env!r}. Chỉ bản deploy production được phép "
        f"làm việc này. Nếu thật sự muốn mở khoá để vá lược đồ bằng tay, đặt "
        f"biến môi trường CHO_PHEP_GHI_DB_XA=1 rồi chạy lại."
    )
    raise RuntimeError(thong_bao)


def init_db() -> None:
    """Tạo toàn bộ bảng nếu chưa tồn tại, rồi vá những cột thêm sau.

    Slice 0 dùng cách này cho nhanh. Khi schema ổn định sẽ chuyển sang Alembic
    migration — xem ``docs/decisions/`` để biết lý do hoãn.

    Bước vá cột là bắt buộc: ``create_all`` tạo bảng còn thiếu nhưng không sửa
    bảng đã có, nên CSDL production (Supabase) sẽ thiếu mọi cột được thêm sau
    lần deploy đầu. Trên Render không có chỗ chạy lệnh tay, vá lúc khởi động là
    cách duy nhất chắc chắn chạy.
    """
    # Chốt chặn phải chạy TRƯỚC create_all: không được để bảng mọc lên CSDL xa.
    chan_khong_ghi_csdl_xa()
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
