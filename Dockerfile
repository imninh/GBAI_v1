# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

# Cài vào một virtualenv riêng ở /opt/venv thay vì `pip install --user`.
#
# Lý do (đã làm hỏng một lần deploy): `--user` đặt gói vào `/root/.local`, mà
# `/root` trên Debian có quyền 700. Stage sau chạy bằng `appuser` nên không
# đọc được thư mục đó, container bật lên là chết ngay vì không import nổi
# `uvicorn`. Thư mục /opt đọc được với mọi người dùng.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: Production ----
FROM python:3.11-slim

# `opencv-python-headless` (dùng để làm mờ khuôn mặt) vẫn liên kết tới
# libgthread của glib, thứ không có sẵn trong bản `slim`. Thiếu nó thì
# `import cv2` chết lúc khởi động chứ không phải lúc build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Chạy bằng người dùng thường, không phải root.
RUN useradd -m appuser

COPY . .

# Thư mục dữ liệu phải do appuser sở hữu thì mới ghi được ảnh đã xử lý.
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

# Render (và phần lớn nền tảng PaaS) cấp cổng qua biến PORT lúc chạy, không cố
# định 8000. Dùng dạng shell để ${PORT} được thay, có mặc định cho lúc chạy tay.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f\"http://localhost:{os.environ.get('PORT','8000')}/health\")" || exit 1

CMD uvicorn src.main:app --host 0.0.0.0 --port ${PORT}
