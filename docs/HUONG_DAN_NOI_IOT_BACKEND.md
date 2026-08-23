# Hướng dẫn nối thiết bị IoT vào máy chủ

Tài liệu cho người lắp thùng thông minh: cần cấu hình gì ở hai đầu, gọi endpoint nào,
và những chỗ dễ sai nhất.

Đối tượng: người nạp firmware ESP32-CAM và người đặt biến môi trường trên máy chủ.

---

## 1. Bức tranh tổng thể

Thiết bị nói chuyện với máy chủ qua **ba đường**, và **hai đường đầu dùng một cơ chế
xác thực, đường thứ ba dùng cơ chế khác**. Đây là chỗ sai nhiều nhất — đọc kỹ bảng này
trước khi làm bất cứ việc gì.

| Đường | Việc | Xác thực | Khoá lấy từ đâu |
|---|---|---|---|
| `POST /api/v1/iot/captures` | Gửi ảnh, nhận nhãn + ngăn cần quay | `device_auth` | biến môi trường **`IOT_DEVICE_KEYS`** |
| `POST /api/v1/iot/heartbeat` | Báo còn sống | `device_auth` | biến môi trường **`IOT_DEVICE_KEYS`** |
| `POST /api/v1/bins/{code}/readings` | Báo mức đầy, mức pin | `khoa_thiet_bi` | **băm SHA-256 lưu trong cơ sở dữ liệu** |

Cả ba đều gửi cùng một header:

```
X-Device-Key: <khoá>
```

⚠️ **Nhưng giá trị khoá của hai nhóm là hai thứ khác nhau.** Một thiết bị muốn chạy đủ
cả ba đường thì phải có **hai khoá**, hoặc phải cấu hình sao cho hai bên trùng giá trị.

Đây là di sản của việc gộp hai nhánh mã: nhánh phần cứng dựng `/iot/*` với khoá trong
biến môi trường, nhánh máy chủ dựng `/bins/*/readings` với khoá băm trong cơ sở dữ liệu
(thu hồi được từng thùng). Chưa gộp về một cơ chế.

**Thiết bị không giữ khoá của bất kỳ nhà cung cấp model nào.** Nó chỉ biết bốn thứ: mật
khẩu Wi-Fi, địa chỉ máy chủ, mã thiết bị của nó, và khoá của nó. Mọi lời gọi model đều
xảy ra ở máy chủ.

---

## 2. Trạng thái máy chủ hiện tại — đo trực tiếp 20/08/2026

Gọi thật vào bản đang chạy (`https://greenbin-api-production-d08d.up.railway.app`):

| Đường | Kết quả | Nghĩa là |
|---|---|---|
| `POST /iot/captures` | `401` · *"No device keys configured on the server"* | 🔴 **`IOT_DEVICE_KEYS` chưa được đặt.** Mọi thiết bị đều bị từ chối |
| `POST /iot/heartbeat` | `401` · *"No device keys configured on the server"* | 🔴 Cùng nguyên nhân |
| `POST /bins/{code}/readings` | `401` · `BIN-KEY-401` với khoá sai | ✅ Chạy đúng — từ chối đúng cách |

⚠️ **Việc đầu tiên phải làm để đường ảnh sống được: đặt `IOT_DEVICE_KEYS` trên máy chủ.**
Trước khi có nó thì không thiết bị nào gửi được ảnh, dù firmware đúng hoàn toàn.

**Đội thùng hiện tại:** 50 thùng, **cả 50 đều đã có khoá riêng** (`device_key_hash` khác
rỗng). Nghĩa là khoá chung `BIN_DEVICE_KEY` **không còn mở được thùng nào** — đúng như
thiết kế. Ai còn nhớ ghi chú cũ *"9/50 thùng dùng khoá chung"* thì đó là số liệu đã lỗi
thời, nợ này đã trả xong.

**Mã thùng thật có dạng `BIN_HN_ANLD_01`**, không phải `BIN-001` như trong tệp mẫu
`secrets.example.h` và `iot/docs/api-contract.md`. Gõ `BIN-001` sẽ nhận `404 NF-404`.

---

## 3. Nối một thiết bị mới — bốn bước

### Bước 1 — cấp khoá cho đường mức đầy (`/bins/*/readings`)

Khoá được sinh, băm SHA-256 rồi lưu vào cơ sở dữ liệu. **Chuỗi thô chỉ hiện ra một lần
duy nhất** lúc cấp — chép ngay, mất là phải cấp lại.

```bash
python scripts/cap_khoa_thung.py --ma BIN_HN_ANLD_01
```

Thu hồi khi thùng bị mất hoặc khoá bị lộ (cấp khoá mới rồi vứt chuỗi cũ — thùng khoá
chặt lại chứ **không** rơi về khoá chung):

```bash
python scripts/cap_khoa_thung.py --ma BIN_HN_ANLD_01 --thu-hoi
```

### Bước 2 — cấp khoá cho đường ảnh (`/iot/*`)

Đường này đọc từ biến môi trường, không có script cấp phát. Tự đặt chuỗi ngẫu nhiên đủ dài.

Trên Railway, thêm biến:

```
IOT_DEVICE_KEYS=GBIN-001:chuoi-ngau-nhien-1,GBIN-002:chuoi-ngau-nhien-2
```

Quy tắc: các cặp cách nhau bằng dấu phẩy, mỗi cặp là `device_id:khoá`. Khoá **ràng vào
đúng `device_id`** — khoá của `GBIN-001` không dùng để gửi thay `GBIN-002` được.

⚠️ Thêm một thiết bị là phải **sửa lại cả chuỗi và khởi động lại máy chủ**. Đây là hạn
chế thật của cơ chế này so với cơ chế băm trong cơ sở dữ liệu.

Sinh chuỗi ngẫu nhiên:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Bước 3 — cấu hình firmware

```bash
cp iot/firmware/include/secrets.example.h iot/firmware/include/secrets.h
```

`secrets.h` nằm trong `.gitignore` — **không bao giờ commit tệp này**.

```c
#define WIFI_SSID     "ten-wifi"
#define WIFI_PASSWORD "mat-khau-wifi"

#define DEVICE_ID "GBIN-001"              // phải khớp vế trái trong IOT_DEVICE_KEYS
#define BIN_CODE  "BIN_HN_ANLD_01"        // mã thùng THẬT, không phải BIN-001

// Không có dấu / ở cuối.
#define BACKEND_BASE_URL "https://greenbin-api-production-d08d.up.railway.app"

#define DEVICE_KEY "chuoi-ngau-nhien-1"   // khớp vế phải trong IOT_DEVICE_KEYS
```

⚠️ **`DEVICE_KEY` ở đây là khoá của đường ảnh.** Nếu firmware dùng cùng một hằng số cho
cả `/bins/*/readings` thì phải đặt khoá cấp ở Bước 1 **trùng** với khoá đặt ở Bước 2.
Không trùng thì một trong hai đường sẽ 401 — và đây chính là bẫy số 1 ở §6.

### Bước 4 — kiểm trước khi ra hiện trường

Xem §5, kiểm bằng `curl` không cần phần cứng.

---

## 4. Hợp đồng từng đường

### 4.1 · `POST /api/v1/iot/captures`

Gửi ảnh JPEG, nhận nhãn và **ngăn cần quay servo**.

`multipart/form-data`:

| Trường | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `image` | tệp | ✅ | JPEG, tối đa 8 MB |
| `device_id` | chuỗi | ✅ | Phải khớp thiết bị đã xác thực |
| `bin_code` | chuỗi | ✅ | Mã thùng thật, ví dụ `BIN_HN_ANLD_01` |
| `item_id` | chuỗi | — | **Khoá chống trùng.** Gửi lại cùng `item_id` trả về **kết quả cũ**, không tạo bản ghi thứ hai |
| `event_type` | chuỗi | — | Mặc định `waste_detected` |
| `uptime_s` | số nguyên | — | |
| `fill_percent` | số thực | — | **Bỏ hẳn trường này** nếu cảm biến siêu âm đọc lỗi. **Đừng gửi 0** — 0 nghĩa là thùng rỗng |

Phản hồi `200` — trường quan trọng nhất là **`route`**:

```json
{
  "status": "ok",
  "label": "recyclable_plastic",
  "confidence": 0.91,
  "route": "plastic",
  "requires_review": false,
  "capture_id": "0f3c…"
}
```

**`label` và `route` là hai thứ khác nhau, cố ý tách:**
- `label` nói *máy chủ nghĩ đó là rác gì*;
- `route` nói *servo phải quay về ngăn nào*.

Ca không chắc trả `label = "UNKNOWN"` **và** `route = "other"`. Gộp hai thứ lại là mất
khả năng đếm số ca không nhận ra được — mà đó là chỉ số chất lượng.

**Bốn giá trị `route`, không có giá trị nào khác:**

```
plastic · metal · paper · other
```

⚠️ **Firmware chỉ được thực thi `route`** (ADR-0012). Không tự đặt ngưỡng tin cậy, không
tự suy nhãn từ `confidence`. Ngưỡng và luật an toàn nằm ở máy chủ — để đổi hành vi thì
đổi một chỗ, không phải nạp lại toàn đội thùng.

⚠️ Gặp `route` lạ (máy chủ mới hơn firmware) thì **quay về ngăn `other`**, đừng đứng im
và đừng đoán.

### 4.2 · `POST /api/v1/bins/{code}/readings`

Báo mức đầy và mức pin. `{code}` là mã thùng thật trên đường dẫn.

```json
{"fill_percent": 41.0, "battery_percent": 88.0}
```

Khoá sai hoặc thiếu → `401` mã `BIN-KEY-401`. Mã thùng không có → `404` mã `NF-404`.

### 4.3 · `POST /api/v1/iot/heartbeat`

Báo còn sống. Dùng chung khoá với `/iot/captures`.

---

## 5. Kiểm không cần phần cứng

Ba lệnh dưới chạy được từ bất kỳ máy nào. Thay `$API`, `$KEY`, `$MA_THUNG` cho đúng.

**Tạo một ảnh JPEG để thử:**

```bash
python -c "from PIL import Image; Image.new('RGB',(64,64),(120,160,90)).save('thu.jpg','JPEG')"
```

**Thử đường ảnh:**

```bash
curl -s -w "\nHTTP=%{http_code}\n" -X POST "$API/api/v1/iot/captures" -H "X-Device-Key: $KEY" -F "image=@thu.jpg;type=image/jpeg" -F "device_id=GBIN-001" -F "bin_code=$MA_THUNG"
```

**Thử đường mức đầy:**

```bash
curl -s -w "\nHTTP=%{http_code}\n" -X POST "$API/api/v1/bins/$MA_THUNG/readings" -H "Content-Type: application/json" -H "X-Device-Key: $KEY" -d '{"fill_percent":41.0,"battery_percent":88.0}'
```

**Thử chống trùng — gửi hai lần cùng `item_id`, phải ra cùng `capture_id`:**

```bash
curl -s -X POST "$API/api/v1/iot/captures" -H "X-Device-Key: $KEY" -F "image=@thu.jpg;type=image/jpeg" -F "device_id=GBIN-001" -F "bin_code=$MA_THUNG" -F "item_id=thu-nghiem-001"
```

Ngoài ra `iot/docs/testing-without-hardware.md` mô tả cách chạy firmware ở chế độ mô
phỏng (Wokwi) và bộ giả lập cảm biến `scripts/device_simulator.py`.

---

## 6. Sáu bẫy đã vấp thật

1. **Hai cơ chế khoá, một cái tên header.** `/iot/*` đọc `IOT_DEVICE_KEYS` từ biến môi
   trường; `/bins/*/readings` đọc băm trong cơ sở dữ liệu. Cùng gửi `X-Device-Key` nhưng
   **giá trị phải khác nhau trừ khi bạn cố ý đặt trùng**. Triệu chứng điển hình: một
   đường 200, đường kia 401, và không hiểu tại sao.

2. **`IOT_DEVICE_KEYS` rỗng thì mọi thiết bị nhận 401** kèm câu *"No device keys
   configured on the server"* — không phải "khoá sai". Thấy câu này là biết máy chủ chưa
   cấu hình, đừng đi tìm lỗi ở firmware.

3. **Mã thùng trong tệp mẫu là mã giả.** `secrets.example.h` và `api-contract.md` viết
   `BIN-001`; mã thật có dạng `BIN_HN_ANLD_01`. Sai mã → `404`, không phải `401`.

4. **`fill_percent = 0` không giống với "không đo được".** Cảm biến lỗi thì **bỏ hẳn
   trường**, đừng gửi 0 — 0 nghĩa là thùng rỗng, và điều phối sẽ tin.

5. **Đổi địa chỉ máy chủ là phải dựng lại APK.** Địa chỉ được nướng vào lúc build, không
   đọc lúc chạy. Việc này áp cho ứng dụng, nhưng cùng một logic với `BACKEND_BASE_URL`
   nướng vào firmware.

6. **Chưa chống phát lại.** Mỗi thùng có khoá riêng và thu hồi được, nhưng một request
   bắt được vẫn phát lại được. Cần nonce và mốc thời gian. **Đây là nợ đã biết**, ghi rõ
   ở `ARCHITECTURE.md` mục 21 — không phải lỗi mới.

---

## 7. Thiết bị không cần biết "phiên bỏ rác"

Có một luồng gọi là *phiên bỏ rác tại thùng*: cư dân xác thực mình đang đứng trước thùng,
hệ thống đếm số vật và cộng điểm nhận thức.

**Firmware không phải sửa một dòng nào cho luồng này.** `/iot/captures` vốn đã gửi kèm
`bin_code`, nên máy chủ tự ghép ảnh vào phiên đang mở của thùng đó. Hệ quả:

- không ai quét mã thì thùng vẫn chạy như thường, chỉ là không cộng điểm cho ai;
- phần tính điểm hỏng cũng không làm hỏng phản hồi phân loại — cả khối được bọc lại, lỗi
  thì ghi log và vẫn trả kết quả phân loại bình thường.

---

## 8. Còn thiếu gì

| Việc | Ghi chú |
|---|---|
| **Đặt `IOT_DEVICE_KEYS` trên máy chủ** | Chưa làm. Đường ảnh **đang chết hoàn toàn** trên bản chạy thật |
| Gộp hai cơ chế xác thực về một | Đường ảnh nên chuyển sang dùng khoá băm trong cơ sở dữ liệu như đường mức đầy — thu hồi được từng thùng, thêm thiết bị không phải khởi động lại máy chủ |
| Chống phát lại | nonce + mốc thời gian + lịch xoay vòng khoá |
| Sửa mã thùng mẫu trong tài liệu và `secrets.example.h` | Đang ghi `BIN-001`, không có thùng nào tên vậy |
| Màn hình OLED trên thùng | Bốn chân dùng được đã bị bốn cảm biến chiếm hết (`iot/docs/pin-map.md` mục 6.1). Firmware chỉ bật màn ở môi trường mô phỏng |

---

## 9. Đọc thêm

| Tệp | Nội dung |
|---|---|
| `iot/docs/api-contract.md` | Hợp đồng đầy đủ từng trường |
| `iot/docs/pin-map.md` | Sơ đồ chân, mục 6.1 giải thích vì sao không lắp được màn |
| `iot/docs/state-machine.md` | Máy trạng thái của firmware |
| `iot/docs/hardware-setup.md` | Lắp đặt phần cứng |
| `iot/docs/testing-without-hardware.md` | Chạy thử không cần board |
| `ARCHITECTURE.md` mục 12.1 | Đường phân loại cho thiết bị |
| `ARCHITECTURE.md` mục 12.2 | Phiên bỏ rác tại thùng |
