# GreenBin AI — Agent Phân loại Rác & Điều phối Thu gom Tái chế

Mã đề **VHR-17** · Nhóm **T-075** · AI20K Build Phase Cohort 3-4

AI Agent phân loại rác qua **ảnh hoặc mô tả bằng chữ** → **tự sinh hành động
trong hệ thống** (cảnh báo rác nguy hại, tạo yêu cầu thu gom, gộp tuyến) →
**người duyệt trước khi chốt**.

Người dùng trung tâm là **cư dân + nhân viên thu gom (ứng dụng)** và **đơn vị
thu gom (web)** ([ADR-0010](docs/decisions/0010-doi-nguoi-dung-trung-tam.md)).
Sản phẩm gồm cả một **thùng thông minh 3 module — chờ · quét · đựng** — nhưng
phần cứng chỉ vào phạm vi **với vai trò nguồn dữ liệu** (cảm biến mức đầy nuôi
quyết định điều phối), không bao giờ là máy phân loại tự động
([ADR-0009](docs/decisions/0009-phan-cung-vao-pham-vi.md)).

Khách hàng chính là **đơn vị thu gom / đơn vị vận hành chuỗi thu gom tái chế**;
actor trực tiếp gồm cư dân, nhân viên thu gom và quản lý đơn vị. Bối cảnh pilot
dự kiến: điểm thu gom tập trung tại chung cư hoặc trường học.

---

## Nhóm T-075

| Thành viên | MSSV | Vai trò |
|---|---|---|
| Trần Phú Nghĩa | 2A202601298 | Trưởng nhóm |
| Trần Hải Quân | 2A202601521 | Cơ khí triển khai · web đơn vị thu gom |
| Đoàn Ngọc Linh | 2A202601762 | Điện tử · firmware · mô phỏng thiết bị |
| Trần Thế Ninh | 2A202602001 | App cư dân · app nhân viên · backend + agent |

Mã nguồn trong repo này là phần **phần mềm** của hệ thống: backend, agent, app
cư dân/nhân viên và web cho đơn vị thu gom.

---

## Chạy thử

```bash
pip install -r requirements.txt
python scripts/seed.py --reset --demo
python -m uvicorn src.main:app --port 8000
```

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Mở http://localhost:3000 · API docs ở http://localhost:8000/docs

Muốn chạy thêm **tầng T0.5 (model local CLIP)** thì cài riêng — `torch` nặng
1,19 GB nên không nằm trong `requirements.txt`:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-local-model.txt
```

### Tài khoản demo

Màn đăng nhập có **3 nút vào thẳng**, không cần gõ gì. Muốn gõ tay thì có nút
chuyển **Số điện thoại | Email**, mặc định là số điện thoại.

| Vai trò | Số điện thoại | Email | Mật khẩu |
|---|---|---|---|
| Cư dân | `0901000001` | `resident@demo.vn` | `demo1234` |
| Nhân viên thu gom | `0901000002` | `cleaner@demo.vn` | `demo1234` |
| Đơn vị thu gom (web) | `0901000003` | `manager@demo.vn` | `demo1234` |

Số điện thoại được chuẩn hoá trước khi tra, nên `0901000001`, `0901 000 001` và
`+84901000001` là cùng một tài khoản. Người dùng mới đăng ký ngay trên màn đăng
nhập (`POST /auth/register`) — số điện thoại + mật khẩu + tên, căn hộ tuỳ chọn.

⚠️ `/auth/register` là **endpoint công khai duy nhất tạo được dữ liệu**. Nó có
**giới hạn tần suất theo IP** — `REGISTER_RATE_LIMIT` lần mỗi
`REGISTER_RATE_WINDOW_SECONDS` giây, mặc định **10 lần / 10 phút**; đặt `0` để
tắt. Bộ đếm nằm trong bộ nhớ tiến trình nên nhiều worker thì mỗi worker một bộ
đếm — đây là hàng rào chống lạm dụng, không phải cơ chế xác thực. Bước còn thiếu
trước khi mở cho người thật vẫn là **xác thực số điện thoại**.

### Ứng dụng cư dân có gì

| Tab | Nội dung |
|---|---|
| Phân loại | Chụp ảnh hoặc mô tả bằng chữ → nhãn + hướng dẫn có trích nguồn quy định của đúng toà |
| Yêu cầu | Đặt lịch thu gom đồ cồng kềnh, theo dõi 10 trạng thái của yêu cầu |
| Lịch | Lịch thu gom theo toà, **xem được khi không có mạng** |
| Điểm gửi | Bản đồ + danh sách điểm gửi **sắp theo khoảng cách thật**, lọc theo vật liệu, hiện tình trạng còn chỗ / sắp đầy / chưa rõ |
| Tôi | Hồ sơ (đổi tên, đổi căn hộ) · lịch sử theo vật liệu · trang "ảnh của tôi được xử lý thế nào" |

Ở tab **Điểm gửi**, cư dân chọn mốc để tính khoảng cách: *Nơi ở của tôi* (mặc
định), *Vị trí hiện tại* (chỉ xin quyền GPS khi người dùng chạm vào chip, không
xin lúc mở màn hình), hoặc **mốc tự thêm** bằng cách đặt tên gợi nhớ rồi chạm
lên bản đồ. Mốc tự thêm lưu trong `localStorage` của máy người dùng —
**không dùng dịch vụ geocoding nào**, vì địa chỉ ngõ ngách Việt Nam có tỉ lệ
trượt cao còn bản đồ thì đã có sẵn ngay trên màn hình đó.

---

## Cài app

**Cư dân và nhân viên thu gom dùng app trên điện thoại; đơn vị thu gom dùng web
trên máy tính** — console của họ là bảng nhiều cột, thiết kế cho màn hình rộng.
Đăng nhập vai đơn vị thu gom *trong app* sẽ hiện màn chỉ sang web thay vì nhồi
console vào màn 6 inch.

Trang hướng dẫn ngay trong sản phẩm: **`/tai-app`**.

| Máy | Cách cài | Ghi chú |
|---|---|---|
| Android | Tải `.apk` ở [Releases](../../releases/latest) | Bản **debug**, chưa ký để lên Google Play |
| Android (không muốn cài APK) | Mở web bằng Chrome → *Cài ứng dụng* | Cùng một giao diện |
| iPhone / iPad | Safari → Chia sẻ → *Thêm vào MH chính* | |
| Máy tính | Mở thẳng web | |

⚠️ **Không có bản cài cho iPhone.** Nhóm phát triển trên Windows nên không build
được IPA; iPhone đi đường PWA.

APK do GitHub Actions build: đẩy một tag `v*` là workflow
[`android.yml`](.github/workflows/android.yml) build rồi đính file vào Release
của tag đó.

```bash
git tag v0.1.0 && git push origin v0.1.0
```

Trước đó phải đặt hai biến trong *Settings → Secrets and variables → Actions →
Variables*: `NEXT_PUBLIC_API_URL` và `NEXT_PUBLIC_WEB_URL`. **URL bị nướng vào
lúc build**, nên thiếu là APK ra sẽ trỏ vào `localhost` và không chạy trên điện
thoại — workflow dừng sớm với câu lỗi rõ ràng nếu thiếu.

### Xem offline

Service worker (`frontend/public/sw.js`, viết tay) cache vỏ ứng dụng
và **ba endpoint tra cứu công khai** (`/categories`, `/meta/enums`,
`/buildings/*/schedule`) theo kiểu stale-while-revalidate → **màn Lịch thu gom
xem được khi không có mạng**. Hầm để xe và khu thùng rác sóng rất yếu; đó là bối
cảnh sử dụng thật.

**Không bao giờ cache ảnh cư dân hay endpoint có token** — quyền riêng tư đứng
trước tiện lợi.

---

## Deploy

| Phần | Nơi | File cấu hình |
|---|---|---|
| Backend | **Railway** (chính) · Render (đường lui) | [`railway.json`](railway.json) · [`render.yaml`](render.yaml) |
| Cơ sở dữ liệu | **Supabase PostgreSQL** | chuỗi kết nối đặt qua `DATABASE_URL` |
| Frontend (web) | Vercel | thư mục gốc `frontend`, đặt `NEXT_PUBLIC_API_URL` |
| APK | GitHub Actions → Releases | [`android.yml`](.github/workflows/android.yml) |

Cả hai nền tảng đều dựng thẳng từ [`Dockerfile`](Dockerfile) — nó bind vào
`${PORT}` do nền tảng cấp nên không phải sửa gì khi đổi chỗ chạy.

⚠️ **Cơ sở dữ liệu luôn là Supabase, kể cả khi chạy trên Railway.**
`src/db/session.py` ép `sslmode=require` cho mọi DSN không phải SQLite, mà
PostgreSQL nội bộ của Railway đi qua mạng riêng không phục vụ TLS — cắm chuỗi nội
bộ đó vào là chết ngay lúc khởi động. Dùng **chuỗi Session pooler** của Supabase,
không phải chuỗi "Direct connection" (chuỗi trực tiếp chỉ có IPv6).

Thứ tự bắt buộc: **backend trước**, vì URL của nó bị nướng vào lúc build cả web
lẫn APK. Có URL backend rồi mới build hai cái kia; sau khi có domain Vercel thì
quay lại cập nhật `CORS_ORIGINS` của backend — phải chứa cả domain Vercel,
`https://localhost` và `capacitor://localhost`.

Danh sách biến môi trường cần đặt: xem [`render.yaml`](render.yaml) — nó ghi
đầy đủ từng biến kèm lý do, và dùng lại được nguyên vẹn cho Railway.

`CORS_ORIGINS` phải chứa cả `https://localhost` và `capacitor://localhost` —
đó là origin mà app Android đóng gói bằng Capacitor tự dùng. Thiếu là app cài về
gọi API bị chặn.

### Giới hạn của hạ tầng miễn phí

Ba điều dưới đây đã ghi thẳng lên **trang Vận hành của sản phẩm**, không giấu
trong báo cáo:

- **Máy chủ ngủ khi rảnh** (gói free của Render) → request đầu tiên chậm vài chục
  giây. *Trước lúc demo phải mở web một lần cho nó thức dậy.* Bản dùng thử của
  Railway không ngủ, nhưng **hết hạn theo thời gian hoặc theo mức tín dụng** —
  phải kiểm ngày hết hạn còn xa hơn ngày nộp, nếu không thì quay về Render.
- **Đĩa là tạm thời** → ảnh cư dân đã tải lên mất khi service khởi động lại.
- **Không đủ RAM cho `torch`** → tầng T0.5 tắt trên bản deploy
  (`LOCAL_MODEL_ENABLED=false`), ảnh đi thẳng lên T1. Trang Vận hành hiện
  "Model local: đang tắt" nên số liệu vẫn trung thực.

Render tự nạp dữ liệu nền lúc khởi động (`SEED_ON_START=true`) vì ở đó không có
chỗ chạy tay `scripts/seed.py`. Gọi lại nhiều lần vô hại — dữ liệu nền cập nhật
bản ghi cũ, dữ liệu demo bị chặn nếu đã có.

---

## Cấu hình model

**Đổi nhà cung cấp model chỉ bằng sửa `.env`, không sửa code.**

```bash
cp .env.example .env
# VISION_PROVIDER=gemini | openai | openrouter | nvidia | local_only
# rồi điền key tương ứng
```

| Provider | Nhận ảnh? | Ghi chú |
|---|---|---|
| Gemini | ✅ | mặc định |
| OpenAI | ✅ | `gpt-4o-mini` → `gpt-4o`, đúng kiến trúc gốc trong ADR |
| OpenRouter | ✅ | một key vào được nhiều model |
| NVIDIA NIM | ✅ | API tương thích OpenAI |
| DeepSeek | ❌ | **chỉ text** — không dùng được cho phân loại ảnh |

### Trạng thái thật của các tầng AI — cả phần chưa chạy được

- **T0 cache pHash** — chạy, $0. Ảnh trùng/gần trùng không gọi lại API.
- **T0.5 CLIP local** — chạy được ở hai đường (xem mục dưới), **nhưng tắt trên
  bản deploy** vì máy chủ miễn phí không đủ bộ nhớ cho `torch`; ảnh đi thẳng lên
  T1. **`CLIP_ACCEPT_CONFIDENCE` chưa được chuẩn lại** cho bản nén — bản ONNX
  cho điểm cosine lệch 0,970–0,980 so với bản đầy đủ, nên ngưỡng 0,82 đang dùng
  là con số chưa kiểm trên ảnh thật.
- **T1 / T2 đám mây** — định tuyến chạy, mỗi tầng một nhà cung cấp riêng
  (`VISION_PROVIDER_T1/_T2/_TEXT`). **Chưa có model nào nhìn ra đồ điện tử lẫn
  trong ảnh rác thật một cách đáng tin cậy** — hai model NVIDIA đo được 0/6 và
  1/6 trên ảnh rác thật, trong khi Gemini nhận ra 2/2. Phần "nhìn" phần này đang
  được tính chuyển xuống tầng local, và đây là ca được liệt kê trong
  [ADR-0009](docs/decisions/0009-phan-cung-vao-pham-vi.md) và bàn giao 03/08.
- **Điểm thưởng** — **chỉ được trao từ khối lượng THẬT do người xác nhận cân**,
  không bao giờ từ con số AI ước lượng. Xem phần "Vòng đời yêu cầu thu gom" ở dưới.

### Embedding cho RAG

Truy hồi quy định chạy **hybrid BM25 + embedding**. Embedding dùng nhà cung cấp
**riêng**, không bám theo tầng `text`:

```bash
EMBEDDING_PROVIDER=gemini     # đo 02/08: NVIDIA không có endpoint embedding dùng được
EMBEDDING_DIMENSIONS=768      # cắt từ 3072 cho kho vector nhẹ đi 4 lần
```

Nhúng kho quy định (một lệnh gọi cho cả kho, chạy lại vô hại):

```bash
python scripts/seed.py --embed
```

Đo chất lượng truy hồi:

```bash
python eval/run_retrieval_eval.py
```

Kết quả trên 18 câu hỏi có đáp án (chạy thật, lưu ở
`eval/results/report.md`) — hybrid hơn BM25 ở mọi chỉ số, và **hit@5 = 1,000**
nghĩa là model luôn nhận được đoạn quy định đúng:

| | BM25 | Hybrid |
|---|---|---|
| hit@1 | 0,667 | **0,722** |
| hit@5 | 0,944 | **1,000** |
| MRR | 0,792 | **0,838** |

Không có API key thì truy hồi tự chạy **thuần BM25** — mất một phần chất lượng,
không ai bị chặn. Trang Vận hành hiện rõ đang chạy chế độ nào.

### Mỗi tầng một nhà cung cấp

`VISION_PROVIDER` là mặc định chung; ba biến dưới đây ghi đè cho riêng từng tầng
(để trống là dùng mặc định chung):

```bash
VISION_PROVIDER_T1=nvidia     # tầng ăn phần lớn lưu lượng → nơi quota rộng
VISION_PROVIDER_T2=gemini     # chỉ chạy khi ca khó → chịu được quota hẹp
VISION_PROVIDER_TEXT=gemini   # sinh hướng dẫn + hỏi bằng chữ
```

Đo 01/08/2026: free tier `gemini-flash-latest` chỉ **20 request/ngày** và mỗi
lần chụp ảnh tiêu 2 request — dồn cả hệ thống vào một nhà cung cấp thì **10 lần
chụp là hết**. Trải theo tầng thì mất một nguồn chỉ mất một tầng, các tầng còn
lại vẫn trả lời. Trang Vận hành hiện bảng tầng → nhà cung cấp → model → có key
chưa. Chi tiết ở [ADR-0006](docs/decisions/0006-provider-theo-tung-tang.md).

Chưa có API key thì phần chặn cứng, thu gom, tuyến, vận hành **vẫn chạy đầy đủ**;
chỉ luồng nhận diện ảnh cần key.

### Tầng T0.5 — CLIP chạy tại chỗ, hai đường

Tầng T0.5 dùng CLIP zero-shot (`openai/clip-vit-base-patch32`), chọn đường chạy
bằng `CLIP_RUNTIME`:

| | `torch` (máy dev) | `onnx` (máy chủ) |
|---|---|---|
| Cần | torch 1,19 GB | chỉ `onnxruntime` |
| Trọng số | ~605 MB | **88,7 MB** |
| RAM đo được | — | **185 MB** |
| Độ trễ/ảnh | 458 ms | **56 ms** (114 ms tính cả giải mã ảnh) |

Bản `onnx` chỉ giữ **nửa ảnh** của CLIP, đã nén int8; dãy số của 35 câu mô tả
được tính sẵn một lần nên khỏi phải mã hoá lại mỗi tấm ảnh. Nhờ vậy tầng này
chạy được cả trên máy chủ 512 MB. Sinh bộ file:

```bash
python scripts/export_clip_onnx.py --anh data/media/<một-ảnh>.jpg
```

Chạy **một lần**, cần torch — máy yếu thì chạy trên Google Colab bản miễn phí.
Hai file kết quả (~89 MB) **không commit vào repo**: đính vào GitHub Release rồi
trỏ `CLIP_ASSETS_URL` vào đó.

⚠️ Bản nén cho điểm số lệch so với bản đầy đủ (cosine đo được 0,970–0,980), nên
**`CLIP_ACCEPT_CONFIDENCE` phải chuẩn lại trên bộ ảnh thật** — chi tiết và toàn
bộ số đo ở [ADR-0007](docs/decisions/0007-tang-t05-chay-onnx-int8.md).

---

## Kiến trúc

```
Ảnh / mô tả bằng chữ
      ▼
TIỀN XỬ LÝ ẢNH  tước EXIF · làm mờ khuôn mặt · nén 512px · tính pHash
      ▼
classify_waste   T0 cache pHash ($0) → T0.5 CLIP local ($0) → T1 → T2
      ▼
   chặn cứng? / dưới ngưỡng nhóm?  ──►  TỪ CHỐI trả lời + chuyển người
      ▼ không
advise (RAG)  truy hồi quy định của ĐÚNG TOÀ ĐÓ → hướng dẫn có trích nguồn
      ▼
schedule_pickup  vượt ngưỡng → HITL duyệt → gộp tuyến → HITL chốt tuyến
      ▼
xác nhận khối lượng THẬT → hoàn tất hoặc tranh chấp
```

Chi tiết: [ARCHITECTURE.md](ARCHITECTURE.md) · [CLAUDE.md](CLAUDE.md) mục 4

### Vòng đời yêu cầu thu gom — 10 trạng thái

Máy trạng thái định nghĩa ở `src/services/pickup_lifecycle.py`, 10 trạng thái:

`moi_tao` · `cho_duyet` · `cho_nhan` · `da_nhan` · `dang_van_chuyen` ·
`da_giao_don_vi` · `tranh_chap` · `hoan_tat` · `tu_choi` · `da_huy`

Điểm mấu chốt: **khối lượng THẬT do đội vệ sinh cân** khi tới `da_giao_don_vi`
quyết định bước cuối — trong khoảng ước lượng (kèm dung sai
`PICKUP_WEIGHT_TOLERANCE_PERCENT`, mặc định 20%) thì `hoan_tat`; lệch quá thì
`tranh_chap` kèm lý do bằng tiếng Việt. **Điểm thưởng chỉ tính trên con số do
người xác nhận, không bao giờ trên ước lượng của AI.** Các trạng thái được nhân
viên thu gom đẩy từng bước qua endpoint `POST /pickups/{id}/chuyen-trang-thai`,
và hàng đợi "Chờ xác nhận khối lượng" hiện trên web cho đơn vị thu gom duyệt.

### Ba điểm HITL

1. Yêu cầu thu gom vượt ngưỡng → người duyệt duyệt. Ngưỡng so với **cận trên**
   của khoảng khối lượng, vì vision ước lượng kg từ ảnh sai là chuyện bình thường
   và sai số phải nghiêng về phía cần người duyệt.
2. Phân loại confidence thấp / nghi nguy hại → người xác nhận nhãn.
3. Tuyến do agent gộp → người duyệt chốt. **Agent không được tự đổi lịch làm
   việc của con người.** Và khối lượng thật phải được người xác nhận trước khi
   hoàn tất — hệ thống không bao giờ tự chốt dựa trên ước lượng.

### An toàn AI

- Nhóm nguy hại dùng **ngưỡng confidence cao hơn hẳn**; dưới ngưỡng thì từ chối
  trả lời dứt khoát và chuyển người, vẫn hiện phỏng đoán nhưng **không kèm
  hướng dẫn xử lý**.
- **Danh sách chặn cứng** (vật sắc nhọn y tế · bình gas · hoá chất) chặn **trước
  khi gọi model**, bỏ qua confidence.
- Cảnh báo an toàn là **text cố định lấy từ danh mục trong CSDL**, không do LLM
  sinh — UI ghi rõ điều đó.
- Ảnh: tước toàn bộ EXIF (gồm GPS), làm mờ khuôn mặt, nén 512px, có hạn lưu trữ.
  Màn "Ảnh của tôi được xử lý thế nào" cho cư dân xem hệ thống đã xoá những gì.
  Ảnh gốc chỉ đơn vị thu gom mở được và **mỗi lần mở đều ghi audit log**.

---

## Thùng thông minh và bản đồ điều phối

Sản phẩm gồm **một thùng thông minh 3 module — chờ · quét · đựng**
([ADR-0009](docs/decisions/0009-phan-cung-vao-pham-vi.md)). Ranh giới bất di
bất dịch: **phần cứng chỉ là nguồn dữ liệu** — cảm biến mức đầy (fill-level) đổ
số liệu vào quyết định điều phối tuyến. Nó **không bao giờ là cơ chế phân loại
tự động**; module "Quét" giữ ở mức "con người/thiết bị đưa ảnh vào hệ thống,
phần mềm phân loại".

Phía phần mềm đã có đầy đủ từ trước quyết định này và giữ nguyên:

- Mô hình `Bin` / `BinReading` (`src/db/models_bins.py`), dịch vụ
  `src/services/bins.py`.
- Bản đồ điều phối ở **`/dieu-phoi`** (đường dẫn web riêng, chiếm trọn màn hình).
  Bản đồ hiển thị: vị trí từng thùng trên bản đồ, bốn thẻ thống kê tổng
  (tổng / cần gom / hết pin / mất kết nối), trạng thái từng thùng
  (`can_gom` · `het_pin` · `mat_ket_noi` · `binh_thuong`), mức đầy và mức pin,
  bộ lọc "chỉ thùng cần gom", theo dõi trực tiếp làm mới 3 giây một lần, và panel
  chi tiết một thùng kèm **lịch sử readings** (thời gian, mức đầy, pin, nguồn:
  thiết bị / mô phỏng / nhập tay).
- Dữ liệu thùng là **mô phỏng** (`scripts/device_simulator.py` bơm qua endpoint
  xác thực bằng khoá thiết bị); màn hình không bao giờ tự bịa số.
- **Thùng đang đầy trở thành điểm dừng trong tuyến**, gộp chung chuyến với yêu
  cầu thu gom đồ cồng kềnh của cư dân. Tuyến vẫn ở trạng thái `proposed` cho tới
  khi người duyệt bấm.
- **Quản lý giao thùng cho từng nhân viên** (`PATCH /bins/{code}/nhan-vien`, ghi
  audit log mỗi lần giao), và **dữ liệu thùng bị chặn ở hai lớp**: theo **đơn vị
  thu gom** rồi theo **nhân viên trong đơn vị đó**. Nhân viên chỉ thấy thùng được
  giao cho mình; quản lý thấy toàn bộ thùng của đơn vị mình. Thùng chưa gắn đơn vị
  thì mọi người xem đều thấy — chưa gắn là việc phải xử, không phải thứ đem giấu.

### Thứ tự ghé các điểm dừng

Đây là bài toán **TSP đường mở** — "ghé N điểm theo thứ tự nào cho ngắn" — chứ
**không phải** bài toán tìm đường giữa hai điểm, nên **không dùng Dijkstra hay
A\***. Cách làm: **nearest-neighbour rồi 2-opt** trên khoảng cách đường chim bay
(`src/services/toi_uu_tuyen.py`), hoà thì chọn chỉ số nhỏ hơn để cùng đầu vào
luôn cho cùng đáp án.

Đo trên 100 bộ 7 điểm ngẫu nhiên, so với vét cạn `7!`:

| | Tổng quãng đường | Đạt tối ưu tuyệt đối |
|---|---|---|
| Xếp theo tên toà/căn (cách cũ) | 2189,8 | — |
| **Nearest-neighbour + 2-opt** | **1804,8 (−17,6%)** | **88/100 bộ** |

Điểm ghé đầu tiên **không còn bị cố định**: chạy nearest-neighbour từ nhiều điểm
xuất phát rồi giữ bản ngắn nhất (chặn ở 8 điểm xuất phát, vì 2-opt vốn đã `O(n³)`
mỗi vòng), đo được thêm **−6,3%** và lên **97–98/100 bộ đạt tối ưu tuyệt đối**.

Có thêm một đường **tuỳ chọn, mặc định TẮT**: lấy khoảng cách **đường đi thật** từ
OSRM thay cho đường chim bay (`ROUTE_REAL_DISTANCE=true`). Hỏng hay quá hạn thì
rơi êm về đường chim bay, không làm gãy màn duyệt tuyến.

⚠️ Đo trên **10 thùng demo nằm gọn trong bán kính ~1 km** (gần nhất 119 m, trung
bình 501 m): đường đi thật dài **gấp ~4,3 lần** đường chim bay, và xếp thứ tự bằng
chim bay rồi lái thật thì tốn thêm 6,5 km. Con số đó **chỉ đúng cho cụm dày như
vậy** — ở mật độ này chim bay là xấp xỉ tệ. Đừng đọc nó thành "cải thiện 185%".

Ba bài toán "tìm đường" trong sản phẩm này khác nhau, đừng gộp:

| | Bài toán | Cách giải |
|---|---|---|
| A | Cư dân → điểm gửi **gần nhất** | Chỉ **sắp theo khoảng cách**, không cần thuật toán tìm đường |
| B | Cư dân → **đường đi** tới điểm gửi | Cần **đồ thị đường phố** — repo không có, phải gọi dịch vụ ngoài. **Chưa làm** |
| C | Đội thu gom → **thứ tự ghé N điểm** | **TSP/VRP** — nearest-neighbour + 2-opt như trên |

---

## Kiểm thử

```bash
python -m pytest -q                          # 491 test, không test nào gọi API thật
python -m ruff check src/ tests/ eval/ scripts/
```

Model được mock qua `FakeVisionClient` trong `tests/conftest.py` — chi phí test
bằng 0. Có một guard test (`tests/test_di_tru_trang_thai.py`) quét `src/` +
`scripts/` để chặn việc gán lại từ vựng trạng thái cũ cho `PickupRequest`.

---

## Cấu trúc

```
src/
  agents/       graph LangGraph: classify → advise → schedule
  api/          router, dependency, khuôn lỗi, serializer
  db/           models chia theo miền (users · waste · classify · pickup ·
                ops · schedule · eval · bins …), session, dữ liệu nền
  services/     image · vision/ · classifier* · safety · rag · pickup* ·
                route_planner · metrics · auth · runs
frontend/       Next.js 15 + Tailwind v4 — app cư dân + app thu gom + web
  public/sw.js  service worker: vỏ ứng dụng + 3 endpoint tra cứu, xem offline
  android/      khung app Capacitor, GitHub Actions build APK từ đây
scripts/seed.py nạp dữ liệu nền và dữ liệu demo
scripts/device_simulator.py  bơm số liệu thùng thu gom mô phỏng
scripts/build_assets.py  cắt ảnh linh vật, sinh bộ icon PWA
docs/           FRONTEND_SPEC (hợp đồng API) · decisions/ (ADR) · research/
eval/           bộ đo truy hồi và phân loại, kết quả lưu ở eval/results/
tests/          491 test
```

Ba file đáng chú ý vì chúng giữ những ràng buộc dễ vi phạm:

| File | Giữ điều gì |
|---|---|
| `src/db/schema_patch.py` | Bảng `COT_CAN_VA` — **thêm cột vào model thì phải khai một dòng vào đây**, nếu không thì test vẫn xanh mà CSDL production thiếu cột |
| `src/services/pickup_lifecycle.py` | Máy trạng thái 10 bước, chặn mọi đường đi tắt bỏ qua người xác nhận khối lượng |
| `src/services/toi_uu_tuyen.py` | Thứ tự ghé điểm dừng — nearest-neighbour + 2-opt, không biết gì về CSDL nên test được bằng điểm phẳng |

---

## Dữ liệu

**Chỉ dùng dữ liệu công khai, mô phỏng hoặc đã ẩn danh.** Toàn bộ toà nhà, căn
hộ, cư dân trong hệ thống là nhân vật mô phỏng.

Bản ghi sinh bằng `--demo` gắn cờ `is_seed=True`, và UI **hiện nhãn "dữ liệu
demo mô phỏng"** ở mọi nơi chúng xuất hiện — số mô phỏng và số đo thật không
trộn vào nhau mà không nói gì.

⚠️ Các đoạn trích luật trong kho quy định là **diễn giải rút gọn**, có cờ
`needs_verification`. Phải mở văn bản gốc đối chiếu điều khoản và hiệu lực hiện
hành trước khi trích dẫn ra ngoài.

**Nguồn dataset dự kiến cho eval:** TrashNet · RealWaste · TACO · Roboflow
Universe, cộng bộ ảnh tự chụp tại Việt Nam. **Bộ tự chụp là bộ quan trọng nhất**
— model đạt 94% trên TrashNet chỉ còn 41% trên ảnh rác thật
([khảo sát](docs/research/sota-model-nhe-phan-loai-rac.md)). Phải kiểm license
từng dataset và ghi nguồn vào README trước khi đưa vào eval.

---

## Giới hạn đã biết

Khối này hiển thị ngay trên trang Vận hành của sản phẩm, không giấu trong báo cáo:

- Nhận diện tốt nhất với **một món rác, chụp rõ, đủ sáng**.
- **Không nhìn xuyên được túi nilon đục** — rác đã đóng túi kín nằm ngoài phạm
  vi, có chủ đích ([ADR-0003](docs/decisions/0003-phan-tang-rac-va-trong-tam-doi-ve-sinh.md)).
- Không phân biệt được nhựa PET và HDPE khi nhãn bị mờ.
- **Không xác định được rác y tế lây nhiễm** — luôn chuyển người.
- **Các model đám mây đang dùng gần như không nhìn ra đồ điện tử lẫn trong ảnh
  rác thật** (NVIDIA đo 0/6 và 1/6; Gemini 2/2) — đây là ca đang được tính
  chuyển xuống tầng local.
- Quy định khác nhau giữa các toà; hướng dẫn chỉ đúng với toà đang chọn.
- Khối lượng AI ước lượng sai số ±40% — đội vệ sinh cân lại tại chỗ, và **chỉ
  khối lượng đó mới được dùng để chốt điểm**.
- **Bản demo trên hạ tầng miễn phí lưu ảnh trên đĩa tạm** — ảnh đã tải lên mất
  khi máy chủ khởi động lại.
- **Tầng T0.5 tắt trên bản deploy** vì máy chủ miễn phí không đủ bộ nhớ cho
  `torch`; ảnh đi thẳng lên tầng T1. Và **ngưỡng `CLIP_ACCEPT_CONFIDENCE` chưa
  được chuẩn lại** cho bản nén ONNX.
- **Bộ đếm giới hạn tần suất nằm trong bộ nhớ tiến trình.** Chạy nhiều worker thì
  mỗi worker giữ một bộ đếm riêng, nên giới hạn thật lỏng hơn con số cấu hình
  đúng bằng số worker. Bản chặt cần Redis hoặc chặn ở tầng cạnh. Và `/auth/register`
  vẫn **chưa có bước xác thực số điện thoại** — xem mục Tài khoản demo.
- **Khoá thiết bị chưa xoay vòng tự động.** Mỗi thùng đã có khoá riêng và thu hồi
  được bằng tay (`scripts/cap_khoa_thung.py --thu-hoi`), nhưng không có lịch xoay
  vòng, và endpoint ingest **chưa chống replay**.
- **Cơ chế điểm thưởng chưa chốt.** Gate 01 §11.4 đặt tiêu chí *kill*: không có
  đơn vị trả tiền thì bỏ reward marketplace. Hệ thống hiện chỉ **hiện**
  `green_points`, không có catalog quà và không hứa quy đổi.

---

## Hồ sơ Demo Day

| # | Deliverable | Ở đâu | Trạng thái |
|---|---|---|---|
| 1 | Source Code | repo này | ✅ |
| 2 | README | file này | ✅ |
| 3 | Architecture Diagram | [ARCHITECTURE.md](ARCHITECTURE.md) · [docs/architecture_diagram.md](docs/architecture_diagram.md) | ✅ |
| 4 | AI Logs | hook + `scripts/log_hook.py`; log thô không đẩy lên repo, bản trích dẫn đã che ở [docs/ai-logs-trich-dan.md](docs/ai-logs-trich-dan.md) | ✅ |
| 5 | Live URL | Render (backend) · Vercel (web) | ⚠️ bản đang chạy đã cũ |
| 6 | Video Demo | — | ❌ chưa có |
| 7 | Pitch Deck | — | ❌ chưa có |
| 8 | Development Journal | [JOURNAL.md](JOURNAL.md) | ✅ |
| 9 | Worklog | [WORKLOG.md](WORKLOG.md) | ✅ |
| 10 | Evaluation Evidence | [docs/evaluation.md](docs/evaluation.md) | ✅ |

Bảng này cố ý ghi cả phần chưa xong — bốn dòng ⚠️/❌ là việc đang nợ, không phải
chỗ bị bỏ quên.

---

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

## Git workflow

Mỗi tính năng được phát triển trên một nhánh riêng và gửi Pull Request vào
`develop`. Xem hướng dẫn chi tiết tại
[docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md).

## Repository

<https://github.com/AI20K-Build-Phase-Cohort-3/P-075>

