"""Điểm vào ứng dụng FastAPI của GreenBin AI."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from src.api.errors import ApiError, api_error_handler, http_error_handler, unhandled_error_handler
from src.api.routes import router
from src.config import get_settings
from src.db.session import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    # Slice 0 tạo bảng trực tiếp; chuyển sang Alembic khi schema ổn định.
    init_db()
    if settings.seed_on_start:
        _nap_du_lieu_nen(demo=settings.seed_demo_on_start)
    if settings.local_model_enabled:
        _nap_truoc_model_local()
    if settings.embed_kb_on_start:
        _nhung_kho_quy_dinh()
    # In cả ba tầng vì chúng có thể nằm ở ba nhà cung cấp khác nhau — nhìn log
    # khởi động là biết ngay tầng nào đang trỏ đi đâu.
    logger.info(
        "GreenBin AI khởi động — môi trường %s · T1=%s(%s) · T2=%s(%s) · text=%s(%s)",
        settings.app_env,
        settings.resolve_provider("t1"),
        settings.resolve_model_for("t1"),
        settings.resolve_provider("t2"),
        settings.resolve_model_for("t2"),
        settings.resolve_provider("text"),
        settings.resolve_model_for("text"),
    )
    yield
    logger.info("GreenBin AI đã dừng")


def _nhung_kho_quy_dinh() -> None:
    """Tính embedding cho kho quy định, chạy nền.

    Máy chủ deploy không có chỗ chạy tay ``scripts/seed.py --embed``, mà kho chỉ
    vài chục đoạn nên một lệnh gọi là xong. Gọi lại nhiều lần vô hại: đoạn nào
    có vector rồi thì bỏ qua. Chạy ở luồng riêng vì nó đụng mạng — không được
    làm chậm lúc máy chủ bật.
    """
    import threading

    def chay() -> None:
        try:
            from src.db.session import session_scope
            from src.services.rag import embed_chunks, so_doan_co_embedding

            with session_scope() as session:
                them = embed_chunks(session)
                co, tong = so_doan_co_embedding(session)
            if them:
                logger.info("Đã nhúng thêm %d đoạn quy định (%d/%d đoạn có vector).", them, co, tong)
            elif co < tong:
                logger.warning(
                    "Không nhúng được kho quy định (%d/%d đoạn có vector) — RAG chạy thuần BM25.", co, tong
                )
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning("Bỏ qua bước nhúng kho quy định: %s. RAG chạy thuần BM25.", exc)

    threading.Thread(target=chay, name="embed-kb", daemon=True).start()


def _nap_truoc_model_local() -> None:
    """Nạp CLIP vào bộ nhớ ngay lúc khởi động, chạy nền.

    Đo được: nạp lần đầu mất ~60 giây, các lần chấm sau chỉ ~650ms. Không nạp
    trước thì **người dùng đầu tiên phải gánh trọn 60 giây đó** và tưởng là
    ứng dụng treo. Chạy ở luồng riêng để máy chủ nhận request được ngay.
    """
    import threading

    def chay() -> None:
        try:
            from src.services.vision import warm_up_local_model

            warm_up_local_model()
        except (ImportError, OSError, RuntimeError):
            # Thiếu torch hoặc không tải được model thì bỏ qua — tầng T0.5 tự
            # nhường cho T1, đây là đường đi bình thường trên bản deploy.
            logger.info("Không nạp được model local — bỏ qua tầng T0.5.")

    threading.Thread(target=chay, name="nap-model-local", daemon=True).start()


def _nap_du_lieu_nen(*, demo: bool) -> None:
    """Nạp danh mục, toà, tài khoản demo ngay lúc khởi động.

    Dùng cho môi trường deploy (Render), nơi không có chỗ chạy tay
    ``scripts/seed.py``. ``bootstrap`` gọi lại nhiều lần vô hại nên restart
    không sinh dữ liệu trùng. Nhập trong hàm để lần khởi động bình thường
    không phải nạp cả module seed.
    """
    from scripts.seed import bootstrap
    from src.db.session import session_scope

    try:
        with session_scope() as session:
            ket_qua = bootstrap(session, demo=demo)
        logger.info("Đã nạp dữ liệu nền lúc khởi động: %s", ket_qua)
    except SQLAlchemyError:
        # Không nạp được dữ liệu nền thì vẫn phải để máy chủ lên — trang lỗi
        # còn đọc được, hơn là cả service chết.
        logger.exception("Nạp dữ liệu nền lúc khởi động thất bại")


app = FastAPI(
    title="GreenBin AI",
    description=(
        "Agent phân loại rác và điều phối thu gom tái chế cho toà chung cư (VHR-17). "
        "Mọi ảnh đều được tước EXIF và làm mờ khuôn mặt trước khi xử lý."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khuôn lỗi thống nhất {error:{code, message_vi, detail}} cho mọi loại lỗi.
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(HTTPException, http_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(router, prefix="/api/v1")


@app.get("/health", tags=["ops"])
def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
