# Hướng dẫn chạy `demo_visual.html`

File: [`iot/simulation/demo_visual.html`](../simulation/demo_visual.html) — mô phỏng trực quan (1 file HTML/CSS/JS
độc lập) toàn bộ quy trình bỏ rác của thiết bị GreenBin AI: từ lúc người dùng đến gần thùng,
xác thực (SKIP/QR), chụp ảnh, cho tới khi rác được servo phân loại vào đúng ngăn.

Đây **không phải giả lập toàn phần**: phần cơ khí (PIR, servo, OLED, camera) là animation
CSS/JS vì không có board thật, nhưng phần gọi AI phân loại và báo mức đầy thùng là request
**thật** (`fetch()`) tới backend FastAPI đang chạy — không có `setTimeout` giả kết quả.

---

## 1. Hệ thống hoạt động như thế nào

### 1.1. Vai trò từng phần

| Khối | Vai trò | Thật hay giả lập |
|---|---|---|
| HC-SR501 (PIR) | Phát hiện người tới gần | Giả lập — bạn tự kéo/bấm icon 🚶 |
| ESP32-S3 + OLED | Hiện màn SKIP/QR, đếm giờ, hiện kết quả | Giả lập (CSS/JS) |
| 2 nút SKIP / QR | Người dùng chọn ẩn danh hay xác thực | Giả lập — nút bấm thật trên UI |
| ESP32-CAM | "Chụp" ảnh rác | Giả lập chỗ chớp đèn flash; **ảnh là file bạn tự chọn** (không dùng webcam) |
| Backend AI (`/iot/captures`) | Phân loại ảnh, trả `label/confidence/route` | **THẬT** — gọi `fetch()` tới FastAPI |
| 3 Servo (cây nhị phân 2 tầng) | Đẩy rác vào đúng ngăn theo `route` backend trả về | Giả lập (CSS transform xoay flap trong SVG) |
| 4× HC-SR04 (đo mức đầy) | Báo mức đầy từng ngăn theo chu kỳ nền | **THẬT** — gọi `fetch()` tới `/bins/{code}/readings`, độc lập với luồng PIR/chụp ảnh |

### 1.2. Luồng chính (theo đúng thứ tự, tất cả các bước chờ đều là thao tác tay của bạn)

```
IDLE
 └─ bạn bấm "▶ Bắt đầu mô phỏng"
      → khởi động vòng lặp báo mức đầy nền (song song, không chặn luồng chính)
 └─ bạn tự KÉO (hoặc bấm) 🚶 lại gần thùng
      → PIR phát hiện → đèn báo sáng
AWAIT_CHOICE
 └─ OLED hiện "Nhấn SKIP hoặc QR"
 └─ bạn BẤM tay 1 trong 2 nút (không có timeout tự động — hệ thống chờ vô hạn)
      ├─ QR  → hiện mã QR mô phỏng → giả lập quét thành công → gắn user_id
      └─ SKIP → tiếp tục ẩn danh, không gắn user_id
TIMER
 └─ đếm ngược cố định 3s (mô phỏng "vào vị trí trước khi chụp")
CAPTURE
 └─ hệ thống dừng lại, MỞ HỘP THOẠI chọn ảnh — bạn chọn 1 file ảnh rác
      (đây là lúc "chụp ảnh" xảy ra — không có ảnh sẽ đứng chờ ở đây)
 └─ chớp đèn flash
UPLOADING
 └─ fetch() POST multipart ảnh thật lên `/iot/captures`
      (thời gian chờ = thời gian mạng thật, không fake delay)
RESULT
 └─ hiện đúng status/label/confidence/route mà backend trả về (không bịa)
SORTING → DROPPING
 └─ Servo1 nghiêng theo route (trái = plastic/metal, phải = paper/other)
 └─ Servo2 (trái) hoặc Servo3 (phải) chọn đúng ngăn cụ thể
 └─ vật rơi vào đúng ngăn, thanh mức đầy dâng lên (đo tại chỗ, cục bộ trên UI)
IDLE (lặp lại)
```

### 1.3. Luồng đo mức đầy — chạy song song, độc lập hoàn toàn

Ngay sau khi bấm "Bắt đầu mô phỏng", một vòng lặp nền (`setInterval` mỗi 6 giây) tự POST
mức đầy hiện tại của cả 4 ngăn lên `POST /bins/{code}/readings`. Vòng lặp này **không liên
quan gì tới PIR/OLED/servo ở trên** — đúng như yêu cầu "khoang này đo độc lập".

- Ngăn nào chuyển trạng thái từ `binh_thuong` → `can_gom` (do `fill_percent` vượt ngưỡng
  `BIN_FILL_ALERT_PERCENT`, mặc định 80% — cấu hình ở backend) thì log dòng
  `[BIN] plastic fill=92% -> pickup request sent`.
- Ngăn đã ở trạng thái `can_gom` rồi thì **không gửi lặp lại dòng "pickup request sent"**
  nữa — chỉ log khi có **transition** (đúng nguyên tắc chống gửi trùng của backend thật).
- Có nút "🚚 đã gom" trên mỗi ngăn để bạn tự reset mức đầy về 0% (chỉ đổi state cục bộ
  trên UI để demo lặp lại được nhiều lần, **không gọi backend**).

---

## 2. Setup

### 2.1. Yêu cầu

- Python **>= 3.11** (theo `pyproject.toml`).
- Trình duyệt hiện đại (Chrome/Edge/Firefox) — có hỗ trợ `fetch`, `foreignObject` trong SVG,
  CSS transform trên phần tử SVG.
- Node.js (đã có sẵn `npx`) — chỉ dùng để chạy 1 static server nhỏ phục vụ file demo, và cho
  web thật (`frontend/`, Next.js) nếu bạn muốn chạy song song.

> **Lưu ý về port**: web thật cho doanh nghiệp/cư dân (`frontend/`, Next.js) mặc định chạy ở
> `http://localhost:3000` (`npm run dev` → `next dev -p 3000`). Nếu bạn muốn **mở đồng thời cả
> web thật và demo mô phỏng**, đừng phục vụ file demo ở port 3000 (sẽ đụng port với web thật) —
> dùng port **5173** cho demo (xem mục 3), port đó cũng đã được whitelist sẵn trong
> `CORS_ORIGINS`.

### 2.2. Setup virtualenv (`.venv`) cho backend

Nếu repo **đã có sẵn** thư mục `.venv` (thường vậy), chỉ cần kích hoạt rồi cài lại dependency
cho chắc (an toàn khi chạy lại, không cài trùng):

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

Nếu **chưa có** `.venv` (máy mới, hoặc lỡ xoá), tạo mới từ đầu:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Kiểm tra đã activate đúng chưa: prompt PowerShell sẽ có tiền tố `(.venv)` ở đầu dòng.

> Có thêm `requirements-local-model.txt` nếu bạn bật `LOCAL_MODEL_ENABLED=true` (tầng T0.5
> local) — cài thêm bằng `pip install -r requirements-local-model.txt` khi cần, không bắt buộc
> cho demo này.

### 2.3. Cấu hình `.env`

Backend xác thực thiết bị IoT bằng header `X-Device-Key`, dùng **2 khoá (bin key) khác nhau**
cho 2 endpoint mà demo gọi tới — đây là chỗ dễ nhầm nhất nên đọc kỹ:

| Endpoint | Biến môi trường (đặt trong `.env`) | Giá trị mặc định demo đang dùng | Dùng cho |
|---|---|---|---|
| `POST /api/v1/iot/captures` (chụp + phân loại) | `IOT_DEVICE_KEYS` | `GBIN-001:sim-test-key` | Ô **"Device Key cho /iot/captures"** trên UI demo |
| `POST /api/v1/bins/{code}/readings` (báo mức đầy) | `BIN_DEVICE_KEY` | ví dụ `dev-local-doi-truoc-khi-deploy` | Ô **"Device Key cho /bins/{code}/readings"** trên UI demo |

Mở `.env` ở gốc repo, đảm bảo có đủ 3 dòng:

```env
IOT_DEVICE_KEYS=GBIN-001:sim-test-key
BIN_DEVICE_KEY=dev-local-doi-truoc-khi-deploy
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

- `IOT_DEVICE_KEYS` là danh sách `device_id:key`, phân cách bằng dấu phẩy nếu có nhiều thiết
  bị (ví dụ `GBIN-001:sim-test-key,GBIN-002:key-khac`). Rỗng thì `/iot/captures` **fail closed**
  luôn — trả lỗi "No device keys configured on the server", không phân loại được gì cả.
- `BIN_DEVICE_KEY` là khoá **chung** cho mọi thùng chưa có khoá riêng (`device_key_hash` rỗng
  trong CSDL — đúng trường hợp seed data mẫu). Rỗng thì `/bins/{code}/readings` cũng fail
  closed, trả `503`.
- **2 khoá này độc lập nhau, không thay thế cho nhau được** — nhập nhầm khoá của endpoint này
  sang ô của endpoint kia sẽ ra lỗi `401`.

> Nếu bạn đổi giá trị key trong `.env`, nhớ sửa lại đúng giá trị đó trong khung
> "⚙ Cấu hình backend" trên giao diện demo (2 ô "Device Key" tách riêng cho từng endpoint) —
> rồi **khởi động lại uvicorn** (biến môi trường chỉ được đọc lúc process khởi động, `--reload`
> không tự nạp lại `.env`).

Backend cũng cần các bin có sẵn trong CSDL với mã trùng với cấu hình demo (mặc định
`BIN-01/02/03/04` — đã có sẵn trong seed data mẫu của dự án). Nếu bạn dùng bộ CSDL khác,
sửa 4 ô "Bin code" trong khung cấu hình cho khớp mã thùng thật.

**Vì sao cần đúng 2 khoá và đúng mã bin:** endpoint `/iot/captures` fail closed nếu
`IOT_DEVICE_KEYS` rỗng; endpoint `/bins/{code}/readings` fail closed nếu vừa thiếu
`BIN_DEVICE_KEY` vừa thùng chưa có khoá riêng. Cấu hình sai sẽ thấy dòng `[ERR]` báo
`401`/`503` ngay trong khung console của demo.

### 2.4. CORS

`CORS_ORIGINS` mặc định của backend chỉ cho phép `http://localhost:3000` và
`http://localhost:5173`. Mở file demo trực tiếp bằng `file://` **sẽ bị chặn CORS** — luôn
phục vụ file qua static server ở 1 trong 2 origin trên (xem mục 3).

---

## 3. Cách chạy

Chạy được **đồng thời cả 3 tiến trình** dưới đây, mỗi tiến trình 1 terminal riêng, không đụng
port nhau:

| Terminal | Chạy gì | Port |
|---|---|---|
| 1 | Backend FastAPI (bắt buộc cho cả 2 web) | 8000 |
| 2 | Web thật cho doanh nghiệp/cư dân (`frontend/`, Next.js) | 3000 |
| 3 | Demo mô phỏng thiết bị IoT (`demo_visual.html`) | 5173 |

### Terminal 1 — chạy backend thật

```powershell
.venv\Scripts\activate
python -m uvicorn src.main:app --reload --port 8000
```

Đợi tới khi thấy `Uvicorn running on http://0.0.0.0:8000`. Nếu vừa sửa `.env`
(`IOT_DEVICE_KEYS`, `BIN_DEVICE_KEY`, `CORS_ORIGINS`...), **phải khởi động lại** tiến trình
này để nạp lại cấu hình mới (Ctrl+C rồi chạy lại lệnh trên, hoặc để `--reload` tự áp dụng
khi sửa code — nhưng biến môi trường thì cần restart thủ công).

### Terminal 2 — chạy web thật (tuỳ chọn, chỉ cần khi muốn xem web thật)

```powershell
cd frontend
npm install   # chỉ cần lần đầu
npm run dev
```

Mở `http://localhost:3000` — đây là Next.js dùng thật cho doanh nghiệp/cư dân, tự trỏ API
tới `http://localhost:8000` (đổi qua biến `NEXT_PUBLIC_API_URL` trong `frontend/.env.local`
nếu backend chạy ở nơi khác).

### Terminal 3 — phục vụ file demo qua static server (dùng port 5173, KHÔNG dùng 3000)

```powershell
npx serve iot/simulation -l 5173
```

Mở trình duyệt vào:

```
http://localhost:5173/demo_visual.html
```

(không double-click mở file trực tiếp — sẽ bị chặn CORS như đã nói ở mục 2.4. Cũng đừng dùng
lại port 3000 cho demo nếu Terminal 2 đang chạy — 2 process sẽ giành port của nhau.)

### 3.1. Kiểm tra cấu hình trước khi chạy demo

Bấm nút "⚙ Cấu hình backend" ở góc phải trên trang demo, kiểm tra:

- **Backend base URL**: `http://localhost:8000/api/v1` (khớp port đang chạy ở Terminal 1).
- **Device ID** / **Device Key cho /iot/captures**: khớp `IOT_DEVICE_KEYS` trong `.env`.
- **Device Key cho /bins/{code}/readings**: khớp `BIN_DEVICE_KEY` trong `.env`.
- 4 **Bin code**: khớp mã thùng thật trong CSDL.

### 3.2. Chạy 1 lượt demo

1. Bấm **"▶ Bắt đầu mô phỏng"**.
2. **Tự kéo** icon 🚶 lại gần thùng trên thanh track (hoặc bấm vào icon để nó tự đi tới) —
   kéo đủ xa mới kích hoạt PIR.
3. OLED hiện màn chọn — **bấm tay** nút **SKIP** hoặc **QR** (hệ thống chờ vô hạn, không tự
   động chọn hộ bạn).
4. Đợi đếm ngược 3 giây.
5. Tới bước **CAPTURE**, hộp thoại chọn file tự mở — **chọn 1 ảnh rác thật** (jpg/png bất kỳ,
   càng giống rác thật càng cho kết quả AI có ý nghĩa).
6. Xem khung console bên phải: dòng `[NET]` (đang gọi), rồi `[AI] status=... label=...
   confidence=...` — đây là **kết quả thật** từ backend.
7. Xem servo xoay theo `route` thật, vật rơi đúng ngăn, thanh mức đầy tăng lên.
8. Về lại IDLE — bấm "Bắt đầu mô phỏng" để chạy lượt tiếp theo (mỗi lượt phải chọn ảnh mới).

Nút **"↺ Reset toàn bộ"**: xoá log + đưa mọi ngăn về 0% (chỉ reset cục bộ trên UI, không
gọi backend).

---

## 4. Pipeline (chi tiết kỹ thuật)

### 4.1. Sơ đồ tổng quát

```
┌─────────────┐   drag/click 🚶   ┌──────────────┐   bấm SKIP/QR   ┌─────────────┐
│    IDLE     │ ───────────────► │ AWAIT_CHOICE │ ──────────────► │   (QR/SKIP  │
│ (chờ tay)   │                  │  (chờ tay)   │                 │   xử lý)    │
└─────────────┘                  └──────────────┘                 └──────┬──────┘
                                                                          │ 3s đếm ngược
                                                                          ▼
┌─────────────┐   fetch() thật   ┌──────────────┐  chọn file ảnh  ┌─────────────┐
│   RESULT    │ ◄─────────────── │  UPLOADING   │ ◄────────────── │   CAPTURE   │
│ (servo xoay,│  POST /iot/      │ (chờ network │  + flash        │ (chờ tay)   │
│  vật rơi)   │  captures        │  thật)       │                 └─────────────┘
└──────┬──────┘                  └──────────────┘
       │ về IDLE
       ▼
     IDLE (lặp)

// song song, độc lập hoàn toàn với sơ đồ trên:
setInterval(6s) ──► POST /bins/{code}/readings (x4 ngăn) ──► log [BIN] + cập nhật badge "ĐẦY"
```

### 4.2. Request/response thật — `POST {base}/iot/captures`

- **Auth**: header `X-Device-Key` (không cần JWT người dùng — đây là API cho thiết bị).
- **Body**: `multipart/form-data`
  - `image`: file ảnh bạn chọn ở bước CAPTURE
  - `device_id`: theo cấu hình (mặc định `GBIN-001`)
  - `bin_code`: mã thùng dùng để gắn phiên bỏ rác (demo dùng mã ngăn "Other" làm bin_code
    chung cho request này)
  - `event_type`: `waste_detected`
  - `uptime_s`: giây kể từ khi trang tải (giả lập uptime thiết bị)
  - `item_id` *(tuỳ chọn)*: chỉ gửi khi có `user_id` từ bước QR — dùng cho idempotency
- **Response thật** (dùng nguyên văn, không sửa/bịa):
  ```json
  {
    "status": "ok | hazard | refused",
    "label": "recyclable_plastic | recyclable_metal | ... | UNKNOWN",
    "confidence": 0.91,
    "route": "plastic | metal | paper | other",
    "review_required": false,
    "message": "...",
    "capture_id": "...",
    "model_version": "..."
  }
  ```
- `route` chính là trường backend đã tính sẵn cho firmware — demo **dùng thẳng** giá trị
  này để quay servo, không tự suy luận nhãn → ngăn.

### 4.3. Request/response thật — `POST {base}/bins/{code}/readings`

- **Auth**: header `X-Device-Key` (khoá `BIN_DEVICE_KEY`, khác khoá ở mục 4.2).
- **Body** (JSON):
  ```json
  {
    "fill_percent": 92,
    "battery_percent": 100,
    "source": "simulator",
    "device_id": "GBIN-001",
    "uptime_s": 123
  }
  ```
- **Response thật**: trả về bản ghi thùng kèm `status` đã tính (`binh_thuong` /
  `can_gom` / `het_pin` / `mat_ket_noi`). Demo chỉ log dòng "pickup request sent" khi
  `status` chuyển sang `can_gom` **lần đầu tiên** (so với lần đọc trước đó).

### 4.4. Ánh xạ `route` → servo (cây nhị phân 2 tầng)

```
                    route
                      │
        ┌─────────────┴─────────────┐
   plastic/metal                paper/other
        │                             │
   Servo1 = TRÁI                 Servo1 = PHẢI
        │                             │
   ┌────┴────┐                  ┌─────┴─────┐
plastic     metal              paper       other
Servo2=T    Servo2=P            Servo3=T    Servo3=P
  ngăn 1     ngăn 2              ngăn 3      ngăn 4
```

### 4.5. Các state trong code (biến `statePill` trên UI)

`IDLE → PIR_DETECT → AWAIT_CHOICE → (QR_SCAN) → TIMER → CAPTURE → UPLOADING → RESULT →
SORTING → DROPPING → IDLE`. Mỗi state đổi màu pill tương ứng (xám = chờ tay, vàng = đang
chờ hệ thống/mạng, xanh = đang chạy animation, đỏ = lỗi thật từ backend).

---

## 5. Xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân | Cách fix |
|---|---|---|
| `[ERR] Gọi backend thất bại: Failed to fetch` | Backend chưa chạy, sai port, hoặc CORS chặn | Kiểm tra Terminal 1 còn chạy; mở demo qua `localhost:5173`, không mở bằng `file://` |
| Web thật (`npm run dev`) báo lỗi port 3000 đang bận / tự nhảy sang 3001 | Demo đang được phục vụ ở port 3000 (đụng port với `frontend/`) | Đổi demo sang port 5173 (`npx serve iot/simulation -l 5173`), giữ port 3000 riêng cho `frontend/` |
| `[ERR] HTTP 401 ...` ở `/iot/captures` | `IOT_DEVICE_KEYS` chưa set hoặc sai khớp Device ID/Key | Set lại `.env`, restart uvicorn, sửa lại 2 ô Device ID/Key trong cấu hình demo |
| `[ERR] HTTP 401` hoặc `503` ở `/bins/.../readings` | `BIN_DEVICE_KEY` sai hoặc rỗng | Sửa ô "Device Key cho /bins/{code}/readings" khớp `.env` |
| `[ERR] HTTP 404` ở `/bins/{code}/readings` | Mã bin trong cấu hình demo không tồn tại trong CSDL | Sửa 4 ô "Bin code" khớp mã thùng thật |
| Bấm SKIP/QR không có phản ứng | Chưa tới bước `AWAIT_CHOICE` (còn đang chờ kéo 🚶) | Kéo/bấm icon 🚶 lại gần thùng trước |
| Hộp thoại chọn ảnh không tự mở ở bước CAPTURE | Trình duyệt chặn `input.click()` lập trình (hiếm) | Refresh lại trang và chạy lại từ đầu |
