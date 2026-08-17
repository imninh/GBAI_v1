# Hướng dẫn IoT và Wokwi — GreenBinAI Phase 1

Tài liệu này giúp thành viên mới hiểu phần IoT đã làm, chạy mô phỏng, thực hiện
demo và giải thích kết quả. Các lệnh được chạy từ thư mục gốc `P-075`, trừ khi có
ghi chú khác.

## 1. Hệ thống làm gì?

GreenBinAI phát hiện một sự kiện bỏ rác, chụp ảnh, gửi ảnh đến backend để xử lý
quyền riêng tư và phân loại, sau đó dùng đèn NeoPixel để phản hồi. Cảm biến siêu
âm đồng thời đo mức đầy của thùng.

```text
PIR phát hiện chuyển động
        ↓
HC-SR04 xác nhận khoảng cách giảm
        ↓
Camera chụp JPEG (ảnh mẫu khi chạy Wokwi)
        ↓
ESP32 gửi ảnh và telemetry đến FastAPI
        ↓
Privacy pipeline → Vision/classification → Safety policy
        ↓
NeoPixel báo OK / cảnh báo / nguy hiểm / lỗi mạng
```

## 2. Thành phần và sơ đồ chân

| Thành phần | Mục đích | Chân ESP32 |
|---|---|---:|
| PIR | Phát hiện chuyển động | GPIO13 |
| HC-SR04 TRIG | Phát xung siêu âm | GPIO14 |
| HC-SR04 ECHO | Đọc khoảng cách | GPIO12 |
| NeoPixel DIN | Hiển thị trạng thái | GPIO15 |

`ECHO` của HC-SR04 là tín hiệu 5 V. Mạch thật bắt buộc dùng bộ chia áp 1 kΩ/2 kΩ
trước GPIO12. Không nối trực tiếp ECHO 5 V vào ESP32.

## 3. Cấu trúc mã nguồn

```text
iot/
├── firmware/
│   ├── include/core/       # Logic thuần C++, không phụ thuộc Arduino
│   ├── include/hw/         # Interface phần cứng
│   ├── src/core/           # State machine, fill level, retry, classification
│   ├── src/hw/             # PIR, HC-SR04, camera, NeoPixel, HTTP
│   ├── src/sim/            # Simulator chạy trên máy tính
│   └── test/               # Unit test và 9 kịch bản
├── simulation/             # diagram.json, wokwi.toml, ảnh JPEG mẫu
└── docs/                   # Tài liệu kỹ thuật chi tiết

src/api/iot.py              # API nhận ảnh và telemetry
src/services/               # Auth, privacy, vision, safety, bin readings
```

Logic chính nằm trong `iot/firmware/src/core/` và không gọi trực tiếp GPIO hay
`millis()`. Thiết kế này cho phép chạy unit test trên máy tính mà không cần ESP32.

## 4. Chuẩn bị môi trường

### 4.1 Lấy mã mới nhất

```bash
git clone git@github.com:AI20K-Build-Phase-Cohort-3/P-075.git
cd P-075
git switch main
git pull --ff-only origin main
```

### 4.2 Cài Python và PlatformIO

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install platformio
```

Trên Windows PowerShell, kích hoạt môi trường bằng:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 4.3 Cài VS Code extension

Cài hai extension:

1. `PlatformIO IDE`.
2. `Wokwi Simulator`.

Đăng nhập Wokwi và kích hoạt license khi extension yêu cầu. Mở **toàn bộ thư mục
P-075** bằng VS Code, không chỉ mở riêng file `diagram.json`.

## 5. Chạy kiểm thử nhanh

### Backend

```bash
pytest tests/ -q
ruff check src/ tests/
```

Kết quả tham chiếu: `48 passed`, Ruff không có lỗi.

### Logic firmware

```bash
cd iot/firmware
../../.venv/bin/pio test -e native
cd ../..
```

Kết quả tham chiếu: `31/31 passed`.

## 6. Chạy Wokwi không kết nối backend

Build firmware:

```bash
cd iot/firmware
../../.venv/bin/pio run -e wokwi
cd ../..
```

Trong VS Code:

1. Mở `iot/simulation/diagram.json`.
2. Nhấn nút Play màu xanh.
3. Chờ Serial Monitor xuất hiện `[STATE] IDLE`.
4. Bấm PIR hoặc thay đổi thanh khoảng cách của HC-SR04 để kiểm thử.

Nếu backend không chạy, Wi-Fi vẫn kết nối nhưng upload sẽ thử tối đa ba lần,
báo lỗi mạng bằng NeoPixel rồi quay lại `IDLE`. Đây là kịch bản lỗi mạng hợp lệ.

## 7. Chạy demo đầy đủ với backend

### Terminal 1 — backend dùng AI stub

```bash
IOT_DEVICE_KEYS="GBIN-001:sim-test-key" \
VISION_PROVIDER=stub \
STUB_VISION_LABEL=plastic \
STUB_VISION_CONFIDENCE=0.94 \
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8123
```

AI stub trả về kết quả cố định, không sử dụng API key và không phát sinh chi phí.

### Terminal 2 — build Wokwi

```bash
cd iot/firmware
../../.venv/bin/pio run -e wokwi
```

Sau đó mở `iot/simulation/diagram.json`, bật **Wokwi Private IoT Gateway** và
nhấn Play. Firmware đã được cấu hình để gọi
`http://host.wokwi.internal:8123`.

## 8. Bốn tình huống demo quan trọng

### 8.1 Người đi ngang — không có rác mới

1. Đặt HC-SR04 ở 50 cm.
2. Kích hoạt PIR.
3. Giữ nguyên khoảng cách.

Kết quả:

```text
[PIR] detected
[STATE] PRESENCE_DETECTED
[STATE] VERIFY_OBJECT
[ULTRASONIC] before=50.4 after=50.4 delta=0.0
[EVENT] false_trigger
[STATE] IDLE
```

Không có dòng chụp camera vì hệ thống đã loại bỏ false trigger.

### 8.2 Bỏ rác hợp lệ

1. Đặt khoảng cách ban đầu ở 50 cm.
2. Kích hoạt PIR.
3. Ngay sau đó giảm khoảng cách xuống khoảng 44 cm, trước lần đo xác nhận.

Kết quả mong đợi:

```text
[EVENT] waste_confirmed
[CAMERA] jpeg_bytes=...
[HTTP] upload status=200
[AI] status=ok label=plastic confidence=0.94
[LED] OK
```

### 8.3 Thùng đầy

Đặt HC-SR04 ở 12 cm và chờ chu kỳ đo tiếp theo. Mức đầy xấp xỉ 96%, hệ thống
phát sự kiện `full=1` và NeoPixel sáng đỏ liên tục.

### 8.4 Thùng được làm rỗng

Sau tình huống thùng đầy, tăng khoảng cách lên 55 cm. Khi mức đầy xuống dưới
75%, trạng thái đầy được xóa và đèn đỏ liên tục tắt.

## 9. Ý nghĩa màu NeoPixel

| Trạng thái | Hiển thị |
|---|---|
| Phân loại thành công | Xanh lá khoảng 3 giây |
| Độ tin cậy thấp hoặc AI từ chối | Đỏ, nháy nhanh 2 lần |
| Rác nguy hiểm | Đỏ nhấp nháy khoảng 5 giây |
| Lỗi mạng/backend | Cam |
| Thùng đầy | Đỏ liên tục |

## 10. Camera trong Wokwi

Wokwi không có linh kiện ESP32-CAM/OV2640. Sơ đồ dùng ESP32 DevKit và
`MockCameraService` trả về ảnh JPEG mẫu tại
`iot/simulation/fixtures/sample_waste.jpg`.

```text
[CAMERA] mock camera active — NOT real hardware
```

Dòng log trên là đúng thiết kế. Mô phỏng kiểm tra được luồng capture → upload →
privacy → classification, nhưng không kiểm tra cảm biến camera, PSRAM hoặc chất
lượng ảnh thật.

## 11. Khắc phục lỗi thường gặp

### `wokwi.toml config file not found in workspace`

1. Mở thư mục gốc `P-075` trong VS Code.
2. Build bằng environment `wokwi` trước.
3. Mở đúng `iot/simulation/diagram.json`.
4. Kiểm tra `iot/simulation/wokwi.toml` tồn tại cùng thư mục.
5. Chạy lệnh `Wokwi: Start Simulator` từ Command Palette nếu nút Play không chạy.

### Wi-Fi kết nối nhưng upload thất bại

Kiểm tra backend đang nghe cổng 8123 và Private IoT Gateway đã bật. Không dùng
`localhost:8123` trong firmware Wokwi; simulator phải gọi
`host.wokwi.internal:8123`.

### PIR báo `false_trigger`

Đây không phải lỗi nếu khoảng cách trước và sau bằng nhau. Muốn mô phỏng bỏ rác,
hãy giảm khoảng cách ít nhất 4 cm trước lần đo xác nhận.

### Không thấy hình ảnh camera

Đúng thiết kế: Wokwi chỉ sử dụng ảnh JPEG mẫu và không cung cấp màn hình camera
trực tiếp.

## 12. Phạm vi đã xác minh và giới hạn

Đã xác minh bằng phần mềm:

- Backend tests: 48 test.
- Firmware native tests: 31 test.
- Host end-to-end simulator: 22/22 check.
- Firmware `esp32cam`, mock và Wokwi build thành công.
- Wokwi diagram lint không có lỗi.

Chưa được xác minh bằng phần cứng thật:

- Camera OV2640 và PSRAM.
- Điện áp, nguồn và nhiễu cảm biến.
- GPIO12 khi ESP32-CAM khởi động.
- Chất lượng phân loại với ảnh thực tế.

## 13. Tài liệu đọc thêm

- [Kiến trúc IoT](../iot/docs/architecture.md).
- [State machine](../iot/docs/state-machine.md).
- [Pin map và cảnh báo phần cứng](../iot/docs/pin-map.md).
- [Hợp đồng API](../iot/docs/api-contract.md).
- [Kiểm thử không cần phần cứng](../iot/docs/testing-without-hardware.md).
- [Đầy đủ 9 kịch bản Wokwi](../iot/simulation/scenarios/README.md).
