# Hướng Dẫn Khởi Chạy Hệ Thống GreenBin AI (VHR-17)

Tài liệu hướng dẫn toàn diện từ A-Z về **Cài đặt (Setup Instructions)**, **Biến Môi Trường (Environment Variables)**, và **Mẫu Truy Vấn API (Sample Queries)** cho toàn bộ hệ thống GreenBin AI (Backend FastAPI, Frontend Next.js, AI LangGraph Agent & Mô phỏng IoT).

---

## 📑 Mục Lục
1. [Yêu cầu Môi Trường & Công cụ](#1-yêu-cầu-môi-trường--công-cụ)
2. [Hướng Dẫn Cài Đặt & Khởi Chạy (Setup Instructions)](#2-hướng-dẫn-cài-đặt--khởi-chạy-setup-instructions)
3. [Danh Sách Biến Môi Trường (Environment Variables)](#3-danh-sách-biến-môi-trường-environment-variables)
4. [Tài Khoản Mẫu & Dữ Liệu Demo](#4-tài-khoản-mẫu--dữ-liệu-demo)
5. [Mẫu Truy Vấn API (Sample Queries & cURL)](#5-mẫu-truy-vấn-api-sample-queries--curl)
6. [Mô Phỏng Thiết Bị IoT & Wokwi](#6-mô-phỏng-thiết-bị-iot--wokwi)
7. [Kiểm Thử & Đảm Bảo Chất Lượng (QA / Testing)](#7-kiểm-thử--đảm-bảo-chất-lượng-qa--testing)

---

## 📌 1. Yêu cầu Môi Trường & Công cụ

* **Hệ điều hành**: Windows 10/11, macOS, hoặc Linux (Ubuntu 20.04+)
* **Python**: `Python 3.10` đến `3.12` (Khuyến nghị 3.11)
* **Node.js**: `Node.js 18+` (Khuyến nghị Node.js 20 LTS) & `npm 9+`
* **Git**: Đã cài đặt Git CLI
* *(Tùy chọn cho IoT)*: PlatformIO Core (`pio`) nếu muốn nạp hoặc build firmware C++ cho ESP32-CAM.

---

## 🚀 2. Hướng Dẫn Cài Đặt & Khởi Chạy (Setup Instructions)

### 🔹 Bước 1: Clone Repository & Chuẩn bị Môi trường Python

```bash
# 1. Clone repository
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-075.git
cd P-075

# 2. Tạo virtual environment
python -m venv venv

# 3. Kích hoạt virtual environment
# Trên Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Trên macOS / Linux:
source venv/bin/activate

# 4. Cài đặt toàn bộ thư viện dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

### 🔹 Bước 2: Thiết lập File Biến Môi Trường `.env`

Tạo file `.env` từ file mẫu `.env.example`:

```bash
# Windows PowerShell:
Copy-Item .env.example .env
# Linux / macOS:
cp .env.example .env
```

Mở file `.env` và cấu hình các API Key tương ứng (xem chi tiết tại [Mục 3](#3-danh-sách-biến-môi-trường-environment-variables)). Dự án hỗ trợ cả các API miễn phí (Gemini, Groq, OpenRouter, NVIDIA NIM) và chế độ chạy Offline hoàn toàn (`VISION_PROVIDER=stub` hoặc `local_only`).

---

### 🔹 Bước 3: Nạp Dữ Liệu Ban Đầu (Seed Database & Vector Embeddings)

Chạy script khởi tạo cơ sở dữ liệu SQLite, tạo danh mục rác, tài khoản demo và tính toán vector embedding cho kho quy định:

```bash
# Nạp dữ liệu nền, các tài khoản demo và tính vector embedding:
python scripts/seed.py --reset --demo --embed
```

---

### 🔹 Bước 4: Khởi Động Backend FastAPI Server

Chạy máy chủ backend bằng lệnh:

```bash
# Cách 1: Chạy qua uvicorn trực tiếp
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Cách 2: Chạy qua file launcher
python -m uvicorn src.main:app --reload --port 8000
```

* **Swagger UI (Interactive Docs)**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
* **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

### 🔹 Bước 5: Khởi Động Frontend Web App (Next.js)

Mở một cửa sổ Terminal mới, chuyển vào thư mục `frontend`:

```bash
cd frontend

# Cài đặt thư viện giao diện
npm install

# Khởi chạy dev server
npm run dev
```

* **Địa chỉ truy cập Ứng dụng**: [http://localhost:3000](http://localhost:3000)

---

## ⚙️ 3. Danh Sách Biến Môi Trường (Environment Variables)

Hệ thống được cấu hình hoàn toàn qua Pydantic Settings trong file [`.env`](file:///d:/P-075/.env).

### 🏷️ 1. Cấu hình Chung (App Core)
| Biến | Kiểu dữ liệu | Mặc định | Ý nghĩa |
| :--- | :--- | :--- | :--- |
| `APP_ENV` | `string` | `development` | Môi trường chạy (`development`, `production`, `test`). |
| `APP_PORT` | `int` | `8000` | Cổng HTTP của backend. |
| `LOG_LEVEL` | `string` | `INFO` | Mức ghi log (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `CORS_ORIGINS` | `string` | `http://localhost:3000,...` | Danh sách domain frontend được phép gọi API (phân cách bằng dấu phẩy). |
| `JWT_SECRET` | `string` | `...` | Chuỗi secret để ký mã JWT token (tối thiểu 32 ký tự). |

### 🧠 2. Cấu hình AI & Định Tuyến 3 Tầng (Multi-Tier Vision Architecture)
| Biến | Kiểu dữ liệu | Mặc định | Ý nghĩa |
| :--- | :--- | :--- | :--- |
| `VISION_PROVIDER` | `string` | `gemini` | Nhà cung cấp mặc định chung (`gemini`, `groq`, `openai`, `openrouter`, `nvidia`, `stub`, `local_only`). |
| `VISION_PROVIDER_T1` | `string` | `groq` | Provider riêng cho Tầng 1 (nhận diện nhanh). |
| `VISION_PROVIDER_T2` | `string` | `gemini` | Provider riêng cho Tầng 2 (xử lý ca khó, rác nguy hại). |
| `VISION_PROVIDER_TEXT` | `string` | `groq` | Provider riêng cho phần hỏi đáp văn bản & tư vấn RAG. |
| `GEMINI_API_KEY` | `string` | `""` | API Key Google Gemini (AI Studio). |
| `GROQ_API_KEY` | `string` | `""` | API Key Groq Cloud. |
| `OPENAI_API_KEY` | `string` | `""` | API Key OpenAI. |
| `OPENROUTER_API_KEY` | `string` | `""` | API Key OpenRouter. |
| `NVIDIA_API_KEY` | `string` | `""` | API Key NVIDIA NIM. |
| `VISION_MAX_OUTPUT_TOKENS` | `int` | `2000` | Giới hạn token output để tránh bị cắt JSON. |
| `VISION_TIMEOUT_SECONDS` | `float` | `15.0` | Timeout gọi model đám mây (giây) trước khi tự động leo tầng. |

### 🛡️ 3. Mô hình Local (T0.5) & Bảo Vệ Riêng Tư (Privacy Pipeline)
| Biến | Kiểu dữ liệu | Mặc định | Ý nghĩa |
| :--- | :--- | :--- | :--- |
| `LOCAL_MODEL_ENABLED` | `bool` | `true` | Bật/tắt tầng T0.5 CLIP Zero-shot local (chạy offline trên CPU). |
| `CLIP_MODEL_NAME` | `string` | `ViT-B/32` | Tên mô hình CLIP. |
| `FACE_BLUR_ENABLED` | `bool` | `true` | Tự động làm mờ khuôn mặt người xuất hiện trong ảnh trước khi phân loại. |
| `MEDIA_MAX_EDGE_PX` | `int` | `512` | Kích thước cạnh dài tối đa khi nén ảnh để tiết kiệm băng thông. |
| `PHASH_MAX_DISTANCE` | `int` | `6` | Khoảng cách Hamming tối đa của pHash để xem là ảnh trùng (Tầng T0). |

### 🔒 4. Quy Tắc An Toàn & HITL (Safety & Human-in-the-Loop)
| Biến | Kiểu dữ liệu | Mặc định | Ý nghĩa |
| :--- | :--- | :--- | :--- |
| `DEFAULT_MIN_CONFIDENCE` | `float` | `0.60` | Ngưỡng độ tin cậy tối thiểu cho rác thông thường. |
| `HAZARDOUS_MIN_CONFIDENCE` | `float` | `0.80` | Ngưỡng độ tin cậy nghiêm ngặt cho rác nguy hại (pin, hóa chất). |
| `LOW_CONFIDENCE_THRESHOLD` | `float` | `0.60` | Ngưỡng cảnh báo độ tin cậy thấp chuyển người duyệt (HITL). |
| `HAZARD_LABELS` | `string` | `battery,chemical...` | Danh sách nhãn nguy hại kích hoạt chốt chặn an toàn ngay lập tức. |
| `HITL_WEIGHT_THRESHOLD_KG` | `float` | `30.0` | Ngưỡng khối lượng rác cồng kềnh kích hoạt duyệt thủ công. |

### 🗺️ 5. Điều Phối Thu Gom & Lộ Trình (VRP & OSRM Routing)
| Biến | Kiểu dữ liệu | Mặc định | Ý nghĩa |
| :--- | :--- | :--- | :--- |
| `ROUTE_REAL_DISTANCE` | `bool` | `true` | Bật tính khoảng cách đường bộ thật qua OSRM (thay vì đường chim bay). |
| `OSRM_BACKEND_URL` | `string` | `http://router.project-osrm.org` | Máy chủ định tuyến OSRM. |
| `VRP_ENABLED` | `bool` | `true` | Bật thuật toán tối ưu hóa lộ trình PyVRP đa xe. |
| `VRP_NUM_VEHICLES` | `int` | `3` | Số lượng xe gom rác tối đa phục vụ điều phối. |
| `VEHICLE_CAPACITY_KG` | `float` | `200.0` | Tải trọng tối đa của mỗi xe thu gom (kg). |

### 📡 6. Thiết Bị IoT Thông Minh
| Biến | Kiểu dữ liệu | Mặc định | Ý nghĩa |
| :--- | :--- | :--- | :--- |
| `IOT_DEVICE_KEYS` | `string` | `GBIN-001:key-one,...` | Danh sách cặp `device_id:key` xác thực thiết bị IoT. |
| `BIN_DEVICE_KEY` | `string` | `""` | Khóa chung cho các thiết bị báo reading nếu không dùng khóa riêng. |
| `BIN_FILL_ALERT_PERCENT` | `int` | `80` | Ngưỡng phần trăm rác đầy để cảnh báo `can_gom`. |

---

## 🔑 4. Tài Khoản Mẫu & Dữ Liệu Demo

Hệ thống có sẵn 3 tài khoản mẫu ứng với 3 vai trò phân quyền:

| Vai trò | Số điện thoại | Email | Mật khẩu | Chức năng chính |
| :--- | :--- | :--- | :--- | :--- |
| **Cư dân (Resident)** | `0901000001` | `resident@demo.vn` | `demo1234` | Phân loại rác (ảnh/text), tra cứu quy định tòa nhà, đặt lịch gom rác cồng kềnh, tích điểm xanh. |
| **Nhân viên (Cleaner)** | `0901000002` | `cleaner@demo.vn` | `demo1234` | Xem lộ trình gom rác tối ưu, dẫn đường Leaflet/OSRM, theo dõi GPS live tracking, ghi nhận đổ thùng. |
| **Quản lý (Manager)** | `0901000003` | `manager@demo.vn` | `demo1234` | Bản đồ giám sát thùng rác thông minh, duyệt ca khó HITL, theo dõi chỉ số tiết kiệm CO2/quãng đường. |

---

## 📡 5. Mẫu Truy Vấn API (Sample Queries & cURL)

Dưới đây là các câu lệnh `cURL` mẫu để tương tác trực tiếp với API backend.

### 🔐 1. Xác thực & Đăng nhập (Authentication)

#### Đăng nhập lấy Bearer JWT Token:
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "0901000001",
    "password": "demo1234"
  }'
```
*Phản hồi mẫu:*
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "full_name": "Nguyễn Văn Cư Dân",
    "email": "resident@demo.vn",
    "phone": "0901000001",
    "role": "resident"
  }
}
```

#### Đăng ký cư dân mới:
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "0987654321",
    "password": "matkhau123",
    "full_name": "Trần Thị Cư Dân",
    "unit_id": 1
  }'
```

---

### ♻️ 2. Phân Loại Rác (AI Waste Classification)

#### Phân loại bằng văn bản & hỏi đáp (Text Query):
```bash
curl -X POST http://localhost:8000/api/v1/classify/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{
    "query": "Hộp sữa chua ăn xong rửa sạch thì bỏ vào thùng rác nào?",
    "building_id": 1
  }'
```

#### Phân loại bằng cách tải ảnh lên (Image Upload):
```bash
curl -X POST http://localhost:8000/api/v1/classify \
  -H "Authorization: Bearer <TOKEN>" \
  -F "file=@./data/sample_waste.jpg" \
  -F "building_id=1"
```
*Phản hồi mẫu:*
```json
{
  "category": {
    "code": "recyclable_plastic",
    "name_vi": "Nhựa tái chế",
    "bin_color": "Vàng",
    "handling_note": "Rửa sạch, làm ráo trước khi cho vào thùng"
  },
  "confidence": 0.94,
  "explanation": "Ảnh chứa chai nhựa PET, thuộc nhóm rác nhựa tái chế.",
  "safety_warning": "",
  "is_hazardous": false,
  "requires_hitl": false
}
```

---

### 📚 3. Tra Cứu Quy Định Tòa Nhà (RAG Knowledge Retrieval)

```bash
curl -X POST http://localhost:8000/api/v1/rag/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{
    "query": "Quy định vứt pin cũ và đồ điện tử hỏng ở tòa nhà S2.01",
    "building_id": 1,
    "top_k": 3
  }'
```

---

### 📷 4. Cổng Kết Nối Thiết Bị IoT (IoT Camera & Sensor Ingest)

#### Thiết bị gửi Heartbeat kiểm tra kết nối:
```bash
curl -X POST http://localhost:8000/api/v1/iot/heartbeat \
  -H "Content-Type: application/json" \
  -H "X-Device-Key: key-one" \
  -d '{
    "device_id": "GBIN-001",
    "status": "online"
  }'
```

#### ESP32-CAM upload ảnh chụp khi phát hiện chuyển động:
```bash
curl -X POST http://localhost:8000/api/v1/iot/captures \
  -H "X-Device-Key: key-one" \
  -F "image=@./iot/simulation/fixtures/sample_waste.jpg" \
  -F "device_id=GBIN-001" \
  -F "bin_code=BIN-001" \
  -F "uptime_s=120"
```
*Phản hồi mẫu (đã tước EXIF và chạy face blur):*
```json
{
  "status": "ok",
  "label": "plastic",
  "confidence": 0.92,
  "requires_review": false,
  "message": "Classified",
  "capture_id": "c92a-...",
  "phash": "f8c0e0c0f0e0c080",
  "image_bytes": 48213,
  "faces_blurred": 0,
  "exif_stripped": true
}
```

#### Cảm biến siêu âm báo mức rác đầy:
```bash
curl -X POST http://localhost:8000/api/v1/bins/BIN-001/readings \
  -H "Content-Type: application/json" \
  -H "X-Device-Key: key-one" \
  -d '{
    "device_id": "GBIN-001",
    "fill_percent": 86.5,
    "is_full": true,
    "uptime_s": 1500
  }'
```

---

### 🚚 5. Đặt Lịch & Điều Phối Thu Gom (Pickups & VRP Routes)

#### Cư dân đặt lịch thu gom rác cồng kềnh:
```bash
curl -X POST http://localhost:8000/api/v1/pickups \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{
    "category_code": "bulky",
    "estimated_weight_kg": 15.0,
    "notes": "Nệm lò xo cũ kèm khung gỗ",
    "address": "Căn hộ 1204 Tòa S2.01 Vinhomes Ocean Park"
  }'
```

#### Lấy lộ trình tối ưu đa điểm cho nhân viên (PyVRP + OSRM):
```bash
curl -X GET "http://localhost:8000/api/v1/routes/optimal" \
  -H "Authorization: Bearer <CLEANER_TOKEN>"
```

#### Nhân viên gửi tọa độ GPS Live Tracking:
```bash
curl -X POST http://localhost:8000/api/v1/tracking/live \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <CLEANER_TOKEN>" \
  -d '{
    "lat": 21.0285,
    "lng": 105.8540,
    "speed_kmh": 22.5,
    "heading_deg": 90.0
  }'
```

---

## 📟 6. Mô Phỏng Thiết Bị IoT & Wokwi

Thư mục `iot/` chứa firmware PlatformIO cho ESP32-CAM và các kịch bản mô phỏng Wokwi:

```bash
# 1. Chuyển vào thư mục firmware
cd iot/firmware

# 2. Build firmware mô phỏng Wokwi
../../venv/Scripts/pio.exe run -e wokwi

# 3. Chạy script webcam mô phỏng luồng nhận diện:
python ../simulation/webcam_service.py --device-id GBIN-001 --backend http://localhost:8000
```

Tài liệu chi tiết về IoT có tại [docs/IOT_WOKWI_GUIDE_VI.md](docs/IOT_WOKWI_GUIDE_VI.md).

---

## 🧪 7. Kiểm Thử & Đảm Bảo Chất Lượng (QA / Testing)

### Chạy toàn bộ 821 Unit & Integration Test Cases:
```powershell
.\venv\Scripts\pytest
```

### Chạy kiểm tra theo từng module cụ thể:
```powershell
# Kiểm thử Router & API Endpoints
.\venv\Scripts\pytest tests/test_api/

# Kiểm thử An Toàn & Định Tuyến Vision Model
.\venv\Scripts\pytest tests/test_services/test_safety.py tests/test_services/test_vision.py

# Kiểm thử Quyền Riêng Tư Ảnh (EXIF + Face Blur)
.\venv\Scripts\pytest tests/test_services/test_image_privacy.py

# Kiểm thử Điều Phối Tuyến & OSRM
.\venv\Scripts\pytest tests/test_services/test_duong_di_that.py
```

### Kiểm tra Code Style với Ruff:
```powershell
.\venv\Scripts\ruff check src/ tests/
.\venv\Scripts\ruff format --check src/ tests/
```
