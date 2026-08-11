# T-075 — Agent phân loại rác thải tái chế

AI Agent hỗ trợ nhận diện, phân loại và cung cấp hướng dẫn xử lý rác thải tái
chế. Dự án được phát triển bởi đội **T-075** trong chương trình VinUni AI20K
Build Phase.

## Mục tiêu

Dự án hướng đến việc giúp người dùng:

- Xác định nhóm rác thải phù hợp.
- Phân biệt rác có thể tái chế và rác không thể tái chế.
- Nhận hướng dẫn làm sạch, phân loại và xử lý trước khi thu gom.
- Giảm tình trạng bỏ sai loại rác vào thùng tái chế.

> Trạng thái: dự án đang trong giai đoạn phát triển.

## Thành viên

Đội **T-075**. Danh sách thành viên và vai trò sẽ được cập nhật theo phân công
chính thức của đội.

## Công nghệ

- Python 3.11+
- FastAPI và Uvicorn
- LangGraph và LangChain
- Pydantic Settings
- Pytest
- Ruff

## Quick Start

### 1. Clone repository

```bash
git clone git@github.com:AI20K-Build-Phase-Cohort-3/P-075.git
cd P-075
```

### 2. Tạo virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Trên Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Cài dependencies

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

### 4. Cấu hình biến môi trường

```bash
cp .env.example .env
```

Mở `.env` và cập nhật các giá trị cần thiết, đặc biệt:

```dotenv
OPENAI_API_KEY=your-api-key
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
```

Không commit file `.env` hoặc API key lên Git.

### 5. Chạy ứng dụng

```bash
make run
```

Hoặc chạy trực tiếp:

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Ứng dụng:

- Swagger UI: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>
- Agent status: <http://localhost:8000/api/v1/status>

Kiểm tra nhanh:

```bash
curl http://localhost:8000/health
```

Kết quả mong đợi:

```json
{"status":"ok","env":"development"}
```

## Kiểm thử và chất lượng code

Chạy test:

```bash
make test
```

Chạy lint:

```bash
make lint
```

Hoặc chạy trực tiếp:

```bash
pytest tests/ -v
ruff check src/ tests/
```

## IoT và mô phỏng Wokwi

Phần IoT Phase 1 gồm firmware ESP32-CAM, PIR, cảm biến siêu âm HC-SR04,
NeoPixel, API nhận ảnh, privacy pipeline và mô phỏng Wokwi.

- Thành viên mới và người demo bắt đầu tại
  [Hướng dẫn IoT và Wokwi bằng tiếng Việt](docs/IOT_WOKWI_GUIDE_VI.md).
- Xem toàn bộ tài liệu tại [Mục lục tài liệu](docs/README.md).
- Xem các kịch bản mô phỏng tại
  [Simulation scenarios](iot/simulation/scenarios/README.md).

Build nhanh firmware Wokwi:

```bash
cd iot/firmware
../../.venv/bin/pio run -e wokwi
```

## Cấu trúc dự án

```text
P-075/
├── src/
│   ├── agents/          # LangGraph agent, nodes và tools
│   ├── api/             # FastAPI routes
│   ├── models/          # Request/response schemas
│   ├── services/        # LLM và business logic
│   ├── config.py        # Cấu hình Pydantic Settings
│   └── main.py          # FastAPI entry point
├── tests/               # Automated tests
├── docs/                # Tài liệu dự án
├── pyproject.toml       # Package metadata và dependencies
├── Makefile             # Các lệnh phát triển thường dùng
└── .env.example         # Mẫu biến môi trường
```

## Git workflow

Mỗi tính năng được phát triển trên một nhánh riêng và gửi Pull Request vào
`develop`. Xem hướng dẫn chi tiết tại
[docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md).

Ví dụ:

```bash
git switch develop
git pull --ff-only origin develop
git switch -c feature/waste-classification
```

## Repository

<https://github.com/AI20K-Build-Phase-Cohort-3/P-075>
