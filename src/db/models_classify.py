"""Ảnh và phân loại: media, bản ghi phân loại, phản hồi nhãn."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models_base import Base, utcnow


class Media(Base):
    """Ảnh do cư dân tải lên. Chịu trách nhiệm về quyền riêng tư.

    Ảnh gốc KHÔNG bao giờ được gửi tới API khi chưa qua tiền xử lý: tước EXIF
    (chứa toạ độ GPS), làm mờ khuôn mặt, nén về 512px.
    """

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL = ảnh do THIẾT BỊ gửi lên, không phải người dùng — thùng ESP32 không
    # có tài khoản nên không có ai để trỏ tới. Cột này đã được nới trên CSDL
    # production ngày 17/08/2026 (`ALTER TABLE media ALTER COLUMN uploader_id
    # DROP NOT NULL`); dòng này chỉ để model khớp với CSDL thật — thiếu nó thì
    # test dựng SQLite từ model vẫn ra NOT NULL và đường ảnh thiết bị không chạy.
    uploader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    # Đường dẫn TUYỆT ĐỐI tới file trên đĩa. Trần 400 là quá nhỏ: PostgreSQL ép
    # độ dài VARCHAR còn SQLite bỏ qua, nên đường ảnh "chạy tốt ở dev, chết ở
    # deploy" — SRV-500/StatementError trên `INSERT INTO media`. Đường dẫn đĩa
    # tạm trên Render có thể sâu tới hàng trăm ký tự tuỳ biến `MEDIA_DIR`, và
    # Linux cho phép đường dẫn tới 4096 ký tự. 1024 là biên an toàn: dư ~980 ký
    # tự so với đường dẫn mặc định (~41) mà vẫn đủ cho mọi lồng thư mục thật.
    stored_path: Mapped[str] = mapped_column(String(1024))
    # Ảnh gốc chưa xử lý. Chỉ BQL được mở, và mỗi lần mở đều ghi AuditLog.
    original_path: Mapped[str] = mapped_column(String(1024), default="")
    # Khoá trong Supabase Storage. Rỗng nghĩa là ảnh này vẫn chỉ nằm trên đĩa —
    # bản ghi cũ và mọi ảnh tạo ra khi cờ storage tắt đều rơi vào diện đó.
    storage_key: Mapped[str] = mapped_column(String(1024), default="")
    original_storage_key: Mapped[str] = mapped_column(String(1024), default="")
    # Băm tri giác — dùng làm cache tầng 0, ảnh trùng/gần trùng không gọi lại API.
    phash: Mapped[str] = mapped_column(String(32), index=True, default="")
    width: Mapped[int] = mapped_column(default=0)
    height: Mapped[int] = mapped_column(default=0)
    bytes_size: Mapped[int] = mapped_column(default=0)
    original_width: Mapped[int] = mapped_column(default=0)
    original_height: Mapped[int] = mapped_column(default=0)
    original_bytes_size: Mapped[int] = mapped_column(default=0)

    exif_stripped: Mapped[bool] = mapped_column(default=False)
    faces_blurred: Mapped[int] = mapped_column(default=0)  # số khuôn mặt đã làm mờ
    # Các trường metadata đã bị xoá, dạng [{field, value_before}] — đây là dữ
    # liệu cho màn "Ảnh của tôi đã được xử lý thế nào" (spec 4.5).
    removed_fields: Mapped[list] = mapped_column(JSON, default=list)
    # Hạn lưu trữ. Job dọn dẹp xoá ảnh quá hạn; ảnh dùng cho eval tách riêng.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    kept_for_eval: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Classification(Base):
    """Một lần phân loại rác — từ ảnh hoặc từ mô tả bằng chữ."""

    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id"), nullable=True, index=True)
    text_query: Mapped[str] = mapped_column(Text, default="")
    # Khoá do THIẾT BỊ sinh (CP2) — dùng để gửi lại cùng ảnh không tạo bản ghi
    # thứ hai. Cất ở cột riêng thay vì nhét vào `text_query`: `text_query` là câu
    # hỏi bằng chữ của cư dân, đi thẳng ra frontend; chuỗi `item_id:` lọt vào đó
    # là rò dữ liệu nội bộ ra màn duyệt.
    item_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    input_type: Mapped[str] = mapped_column(String(10), default="image")  # image | text
    asker_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    building_id: Mapped[int | None] = mapped_column(ForeignKey("buildings.id"), nullable=True)
    item_name: Mapped[str] = mapped_column(String(200), default="")  # tên món AI nhận ra
    # Khi ảnh có nhiều món: [{name, category_code, confidence}] (spec 4.3 ⑦).
    items: Mapped[list] = mapped_column(JSON, default=list)

    predicted_category_id: Mapped[int | None] = mapped_column(ForeignKey("waste_categories.id"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # t0_cache | t1_mini | t2_full | local — chứng minh hiệu quả định tuyến 3 tầng.
    tier: Mapped[str] = mapped_column(String(20), default="", index=True)
    model: Mapped[str] = mapped_column(String(60), default="")
    prompt_version: Mapped[str] = mapped_column(String(20), default="")

    # Hệ thống từ chối trả lời khi dưới ngưỡng an toàn — ghi lại để đo tỉ lệ.
    refused: Mapped[bool] = mapped_column(default=False)
    refusal_reason: Mapped[str] = mapped_column(String(120), default="")
    escalated_to_human: Mapped[bool] = mapped_column(default=False)
    # Vì sao phải leo từ T1 lên T2: "confidence thấp" hoặc "nghi rác nguy hại".
    escalation_reason: Mapped[str] = mapped_column(String(160), default="")
    # Suy giảm một phần: nhận ra món rác nhưng node advise lỗi (spec mục 6.4).
    degraded: Mapped[bool] = mapped_column(default=False)
    degraded_note: Mapped[str] = mapped_column(String(200), default="")

    # Nhãn đúng do người xác nhận. Nguồn dữ liệu cho eval và cải tiến.
    human_label_id: Mapped[int | None] = mapped_column(ForeignKey("waste_categories.id"), nullable=True)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    advice: Mapped[str] = mapped_column(Text, default="")
    advice_sources: Mapped[list] = mapped_column(JSON, default=list)  # id các chunk đã trích dẫn

    latency_ms: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    # Bản ghi mô phỏng để trang Vận hành / Chất lượng AI có hình dạng lúc demo.
    # UI BẮT BUỘC hiện nhãn "dữ liệu demo mô phỏng" cho các bản ghi này.
    is_seed: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ClassificationFeedback(Base):
    """Phản hồi 👍/👎 của người dùng về một lần phân loại.

    Bấm 👎 sẽ đẩy ca đó vào hàng đợi xác nhận nhãn của BQL (HITL #2) và chảy
    ngược vào tập cải tiến (PLO 7).
    """

    __tablename__ = "classification_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    classification_id: Mapped[int] = mapped_column(ForeignKey("classifications.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_correct: Mapped[bool] = mapped_column(default=True)
    suggested_category_code: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
