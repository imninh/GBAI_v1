# CLAUDE.md — Bối cảnh dự án GreenBin AI

> File này được nạp tự động vào mỗi session mới. Giữ nó **luôn cập nhật**.
> Khi có quyết định mới hoặc hoàn thành một mốc, sửa mục "Trạng thái hiện tại"
> và "Việc tiếp theo" ở cuối file. Nhật ký chi tiết theo ngày ghi ở `WORKLOG.md`.

**Cập nhật lần cuối:** 05/08/2026

> 📌 **NƠI LÀM VIỆC ĐÃ ĐỔI.** Từ 05/08 việc thật diễn ra ở **repo nhóm
> `C:\P-075`** (`AI20K-Build-Phase-Cohort-3/P-075`). Repo cá nhân
> `C:\AI20K\P-075-main` (`imninh/Test_GBAI`) từ nay chỉ là kho lưu — **đừng sửa
> gì trong đó nữa**.
>
> 📌 **ĐỌC [`docs/BAN_GIAO_2026-08-05.md`](docs/BAN_GIAO_2026-08-05.md) TRƯỚC.**
> Nó ghi trạng thái thật hiện nay, cách làm việc với OpenCode, 6 cạm bẫy đã phát
> hiện, và **2 test đang đỏ cần sửa đầu tiên**. Mục 10 và 11 phía dưới của file
> này là ảnh chụp ngày 03/08, đã lạc hậu về phần "nơi làm việc" và "việc tiếp
> theo".

---

## 1. Dự án là gì

**GreenBin AI — Agent Phân loại Rác & Điều phối Thu gom Tái chế**
Mã đề: **VHR-17** · Nhóm ngành: BĐS X – App Ứng dụng cư dân

**Bối cảnh:** BQL toà nhà có nghĩa vụ phân loại rác tại nguồn theo luật, nhưng trên thực tế việc đó đang đổ hết lên vai đội vệ sinh — họ phân loại lại toàn bộ rác bằng tay, kể cả pin và rác nguy hại cư dân vứt lẫn vào. Việc đăng ký và điều phối thu gom đồ cồng kềnh vẫn làm thủ công.

**Sản phẩm:** Lớp vận hành cho toà nhà. AI Agent phân loại rác qua **ảnh hoặc mô tả bằng chữ** → **tự sinh hành động trong hệ thống** (cảnh báo rác nguy hại, tạo yêu cầu thu gom, gộp tuyến, ghi sổ tuân thủ) → **người duyệt trước khi chốt**.

**Người dùng chính là BQL và đội vệ sinh, không phải cư dân** — xem [ADR-0002](docs/decisions/0002-chuyen-trong-tam-sang-van-hanh.md). Cư dân là vai trò thứ ba, chạm nhẹ, **không nằm trên đường găng**: hệ thống phải vận hành đầy đủ ngay cả khi không có cư dân nào dùng.

**Nguyên tắc xuyên suốt (ADR-0002):** mỗi kết quả AI phải sinh ra **một hành động hoặc một bản ghi** trong hệ thống, không được dừng ở một màn hình trả lời.

**Phạm vi rác đi qua AI ([ADR-0003](docs/decisions/0003-phan-tang-rac-va-trong-tam-doi-ve-sinh.md)):** chỉ **luồng B** — tái chế, cồng kềnh, nguy hại. **Luồng A** (rác ướt đóng túi nilon đục) **nằm ngoài phạm vi, có chủ đích** — vision không nhìn xuyên túi, và nhãn của nó không ai tranh chấp. **Người thao tác trung tâm là đội vệ sinh tại phòng rác tầng / khu tập kết**, không phải cư dân tại bàn bếp. Luồng cư dân vẫn giữ (thẻ đề yêu cầu ở mục "Cơ bản") nhưng không ai được phụ thuộc vào nó.

**Đề bài gốc chép lại ở `docs/DE_BAI_VHR-17.md`** — đọc file đó thay vì OCR lại ảnh trong `C:\AI20K\Screenshot_Infor\`. Mục 4 của file liệt kê 4 chỗ nhóm chủ động lệch khỏi thẻ đề và lý do.

**Ràng buộc gốc của đề (bắt buộc thể hiện trên sản phẩm):**
1. HITL — đăng ký thu gom khối lượng lớn cần BQL/đội vệ sinh xác nhận
2. Bảo mật thông tin và ảnh cư dân
3. Chính xác trong phân loại — tránh hướng dẫn sai
4. Tối ưu chi phí vận chuyển và lịch thu gom

---

## 2. Chương trình và cách chấm điểm

**AI20K Build Phase — Cohort 2 (VinUni).** Repo này fork từ template chính thức.
Guidebook: `docs/guide/` (10 chương) hoặc https://phoenix.note.transformerlabs.ai/technical-book

### Yêu cầu tối thiểu của sản phẩm
- Web/app **deploy online**
- **Ít nhất 2 vai trò** người dùng
- Workflow **agentic có trạng thái và tool-use**
- **HITL** cho hành động rủi ro
- **Xử lý lỗi và cảnh báo giới hạn** của hệ thống

### Quy định dữ liệu
Chỉ dùng dữ liệu **công khai, mô phỏng, hoặc đã ẩn danh**. Không đưa dữ liệu cá nhân/nhạy cảm thật vào hệ thống.

### Yêu cầu đánh giá sản phẩm
Kịch bản demo chính **và tình huống lỗi** · eval/benchmark cho phần AI · phân tích failure case · theo dõi tối thiểu **độ trễ, lỗi, chi phí** · nêu rõ giới hạn, rủi ro, hướng cải tiến.

### 10 deliverables
Source code · README · Architecture diagram · AI logs (LangSmith + hook tự động) · Live URL · Video demo ≤5 phút · Pitch deck · `JOURNAL.md` · `WORKLOG.md` · `eval/results/report.md`

Thêm trong hồ sơ bàn giao: **dữ liệu mẫu, tài khoản demo, nhật ký quyết định quan trọng** (`docs/decisions/`).

### 5 tiêu chí chấm (1–10 mỗi tiêu chí, mục tiêu 35+/50)
Product/Business · System Design · UX/UI · DevOps · Code Quality

**Bài học từ Cohort 1** (`docs/guide/anti-patterns/`): DevOps và Code Quality là hai cột điểm thấp nhất; 0/12 đội có CI/CD dù template cho sẵn; chỉ 2/12 đội có eval evidence. Bare `except`, thiếu type hints, file 500+ dòng là các lỗi phổ biến.

### 8 PLO và cách đề này chạm tới
| PLO | Nội dung | Thể hiện ở đâu |
|---|---|---|
| 1 | Kiến trúc agent, model routing | Định tuyến 3 tầng T0/T1/T2 (mục 4) |
| 2 | Multi-agent, trace được | Graph `classify → advise → schedule`, màn Agent Run |
| 3 | RAG vượt naive, có đo lường | Kho quy định phân loại, hybrid + filter theo toà. **Đo được 02/08:** hybrid hơn BM25 ở mọi chỉ số (hit@1 0,722 vs 0,667 · hit@5 **1,000** vs 0,944 · MRR 0,838 vs 0,792) trên 18 câu ở `eval/retrieval_questions.py`. Dùng hit@k + MRR thay cho precision@5 vì mỗi câu chỉ có 1–2 đoạn đúng |
| 4 | Giá trị kinh doanh | Giảm phí xử lý rác, giảm số chuyến xe, có nền pháp lý |
| 5 | Hạ tầng, giám sát độ trễ/lỗi/chi phí | Trang Ops |
| 6 | Guardrails, HITL, chống rò rỉ dữ liệu | Xử lý ảnh + từ chối trả lời khi không chắc (mục 5) |
| 7 | Eval pipeline, failure → cải tiến | Tập test ảnh giữ riêng, confusion matrix |
| 8 | Vibe coding có kiểm soát | AI logging hooks, `JOURNAL.md`, ADR |

---

## 3. Quyết định đã chốt

Chi tiết đầy đủ ở `docs/decisions/`. Tóm tắt:

| Quyết định | Chốt | Lý do |
|---|---|---|
| Đề tài | **VHR-17 GreenBin** | Dataset dễ nhất, demo trực quan nhất, câu chuyện an toàn AI mạnh nhất trong 4 đề đã cân nhắc |
| Người dùng chính | **BQL + đội vệ sinh**, cư dân là vai phụ | Phỏng vấn 28/07: cư dân ở phân khúc có dịch vụ trọn gói không có pain point. 3/4 ràng buộc gốc của đề vốn đã nói về vận hành (ADR-0002) |
| Phạm vi rác qua AI | **Chỉ luồng B** (tái chế / cồng kềnh / nguy hại); rác ướt đóng túi kín ngoài phạm vi | Vision không nhìn xuyên túi nilon đục; nhãn rác ướt không ai tranh chấp. Phần còn lại đúng là phần sinh tiền, sinh rủi ro pháp lý và rủi ro sức khoẻ (ADR-0003) |
| Người thao tác trung tâm | **Đội vệ sinh tại phòng rác tầng / khu tập kết** | Rác chỉ mở túi ở đó; đó là nơi việc phân loại bằng tay đang thực sự diễn ra (ADR-0003) |
| Khối lượng đồ cồng kềnh | **Lưu thành khoảng** `weight_min`–`weight_max`; ngưỡng HITL so với cận trên | Vision ước lượng kg từ ảnh sai vài lần là bình thường; sai số phải nghiêng về phía cần người duyệt (ADR-0003) |
| Tem QR định danh nguồn phát sinh | **P1**, mục đích là bản ghi truy vết — không dùng để phạt cư dân | Nền cho báo cáo tuân thủ theo tháng (ADR-0003) |
| Phần cứng / IoT / robot | **Không làm** | Chương trình chấm trên 5 cột phần mềm; phần cứng không có cột điểm nhưng nuốt hết thời gian (ADR-0002) |
| Model nhẹ tự train (tầng T0.5) | **P1, quyết sau** | Khảo sát ở `docs/research/sota-model-nhe-phan-loai-rac.md`. Chỉ có giá trị khi đã có eval + T1 để làm mốc so sánh |
| Database | **SQLite khi dev**, PostgreSQL khi deploy | Không cần Docker lúc dev; viết qua SQLAlchemy nên đổi `DATABASE_URL` là xong |
| Vision model | **Lớp provider tách rời, đổi bằng `.env`** — mặc định Gemini, sẵn sàng OpenAI/OpenRouter/NVIDIA | Nhóm chưa có key OpenAI. **DeepSeek không nhận ảnh** nên không dùng được cho T1/T2. Định tuyến vẫn theo confidence và mức nguy hại, không đổi (01/08) |
| Provider **theo từng tầng** | **T1 = NVIDIA · T2 = Gemini flash · advise = Gemini flash-lite** (`VISION_PROVIDER_T1/_T2/_TEXT`) | Free tier `gemini-flash-latest` chỉ **20 request/ngày**, mỗi lần chụp tiêu 2 → dồn cả hệ thống vào một nguồn thì 10 lần chụp là đứng. Trải theo tầng: mất một nguồn chỉ mất một tầng (ADR-0006) |
| Tầng T0.5 model local | **CLIP zero-shot**, chạy CPU offline, không bao giờ chốt nhãn nhóm nguy hại | Không cần train, không cần dữ liệu gán nhãn; dùng đúng vai trò một cổng chặn rẻ đứng trước API trả phí (01/08) |
| T0.5 trên bản deploy | **Nén còn nửa ảnh, int8** (`CLIP_RUNTIME=onnx`); bản torch đầy đủ giữ ở máy dev làm mốc đối chiếu | 88,7 MB · **185 MB RAM · 56 ms/ảnh** — vừa máy chủ 512 MB. Nửa chữ của CLIP tính sẵn một lần nên khỏi mã hoá lại mỗi ảnh. Đổi lại điểm số lệch (cosine 0,970–0,980) nên **ngưỡng phải chuẩn lại** (ADR-0007) |
| Cache tầng 0 | **pHash ảnh** | Trong chung cư cùng loại vỏ hộp được chụp lại rất nhiều |
| Điều phối tuyến | **Gộp theo toà + khung giờ** (P0), OR-Tools chỉ nếu dư thời gian | VRP đầy đủ là bẫy nuốt thời gian |
| Gamification | **P2** | Vui nhưng không chứng minh năng lực AI |
| Frontend | Next.js, **thiết kế riêng bằng công cụ design rồi mang về** | Cách làm việc của chủ dự án |
| Deploy | **Render** (backend + PostgreSQL) + Vercel (frontend) | Đề gợi ý Railway; đổi sang Render vì `render.yaml` khai được cả web service lẫn CSDL trong một file (ADR-0005) |
| Phân phối | **PWA + APK qua Capacitor**, một bản build dùng chung | Không viết lại native: `output: "export"` chạy sạch nên `out/` vừa cho Vercel phục vụ vừa cho Capacitor gói. iPhone đi đường PWA vì không build được IPA trên Windows (ADR-0005) |

### Đã cân nhắc và loại
- **BDSO2O-18 VoiceOfCustomer** — tốt, nhưng gán nhãn text tốn công hơn nhiều. Kế hoạch và `docs/FRONTEND_SPEC.md` của đề này vẫn còn trong repo để tham khảo cấu trúc; code riêng của nó nằm ở `attic/voc/`.
- **BDSO2O-16 ResaleValuer** — loại vì **không có giá chốt thực**, mà đó lại là chỉ số eval cốt lõi của đề.
- **AIP-20 Prompt Optimization** — trần điểm cao nhưng chi phí API cao và demo khó hấp dẫn.

⚠️ **`docs/Gemini_GBAI.md` là tài liệu brainstorm, KHÔNG phải kế hoạch.** Ba insight có giá trị của nó đã được rút vào ADR-0003. Phần còn lại **đã bị bác**: nó lấy cư dân làm trung tâm (ADR-0002 bác), bỏ toàn bộ phần an toàn AI và eval, chỉ có 1 điểm HITL, và **bảng roadmap Giai đoạn 1 tick `[x]` toàn bộ là sai thực tế** — đừng bao giờ copy bảng đó vào báo cáo. Bản kế hoạch duy nhất là `CLAUDE.md` + `docs/decisions/`.

---

## 4. Kiến trúc

```
Cư dân chụp ảnh / mô tả bằng chữ
        ▼
TIỀN XỬ LÝ ẢNH: tước EXIF/GPS · làm mờ khuôn mặt · nén 512px · tính pHash
        ▼
classify_waste  →  T0 cache pHash ($0) → T1 gpt-4o-mini → T2 gpt-4o
        ▼
   confidence < ngưỡng của nhóm?  ──yes──►  TỪ CHỐI trả lời + chuyển BQL
        ▼ no
advise (RAG): truy hồi quy định + lịch thu gom của TOÀ ĐÓ → hướng dẫn có trích nguồn
        ▼
   đồ cồng kềnh / khối lượng lớn?
        ▼ yes
schedule_pickup: tạo yêu cầu → gợi ý khung giờ → gộp tuyến
        ▼
   vượt ngưỡng?  ──yes──►  HITL: BQL/đội vệ sinh xác nhận
        ▼
   Chốt lịch, thông báo hai phía
```

### Định tuyến model 3 tầng (đây là điểm ăn PLO 1 + mục tối ưu chi phí)
| Tầng | Dùng khi | Chi phí |
|---|---|---|
| T0 — cache pHash | ảnh trùng/gần trùng đã phân loại | $0 |
| T1 — gpt-4o-mini vision | ảnh rõ, vật đơn lẻ (~75–85% lượng) | thấp |
| T2 — gpt-4o vision | confidence thấp, nhiều vật, **hoặc nghi rác nguy hại** | cao |

**Quan trọng:** điều kiện escalate lên T2 phải gồm cả "nghi ngờ rác nguy hại", không chỉ confidence thấp.

**Chi phí vision phải ĐO, không được đoán.** Việc đầu tiên khi chạm phần vision: chạy thử 50 ảnh, đọc `usage` trả về từ API, ghi lại token thật/ảnh cho cả `detail: "low"` và `"high"`, rồi mới nhân lên. Con số đo được đó đưa thẳng vào báo cáo.

---

## 5. An toàn AI — phần mạnh nhất của đề này, không được cắt

### Rủi ro 1 — Ảnh cư dân nhạy cảm hơn tưởng
Ảnh thùng rác có thể chứa khuôn mặt, biển số xe, số căn hộ, **hoá đơn/giấy tờ có tên và địa chỉ**, nhãn thuốc. Mọi ảnh điện thoại đều mang **EXIF chứa GPS chính xác tới mét**.

Bắt buộc ở bước tiền xử lý: tước toàn bộ EXIF · làm mờ khuôn mặt (OpenCV Haar cascade là đủ) · nén 512px · đặt hạn lưu trữ và tự xoá · không đặt đường dẫn ảnh vào URL công khai đoán được.

Có màn hình cho cư dân xem "hệ thống đã xoá gì khỏi ảnh của tôi" — ảnh gốc và ảnh đã xử lý đặt cạnh nhau.

### Rủi ro 2 — Hướng dẫn sai về rác nguy hại là nguy hiểm thật
Pin lithium, bóng đèn huỳnh quang, thuốc hết hạn, hoá chất — sai ở đây gây hại thật.
- Nhóm nguy hại dùng **ngưỡng confidence cao hơn** (`waste_categories.min_confidence`)
- Dưới ngưỡng → **từ chối trả lời chắc chắn**, chuyển người, ghi `refused=True`
- Cảnh báo an toàn cho nhóm nguy hại là **text cố định**, không để LLM tự sinh
- Danh sách chặn cứng: vật sắc nhọn y tế, bình gas, hoá chất → luôn chuyển người

### 3 điểm HITL
1. Yêu cầu thu gom vượt ngưỡng → BQL/đội vệ sinh duyệt
2. Phân loại confidence thấp / nghi nguy hại → nhân viên xác nhận
3. **Lịch thu gom do agent gộp tuyến → đội trưởng duyệt trước khi chốt** (agent không được tự đổi lịch làm việc của người)

Lý do từ chối phải chọn từ danh sách cố định → chảy ngược vào tập cải tiến (PLO 7).

---

## 6. Dữ liệu

| Tầng | Nguồn | Quy mô |
|---|---|---|
| 1 | TrashNet, **RealWaste**, TACO, Garbage Classification (Kaggle), Roboflow Universe | 2.000–5.000 ảnh |
| 2 | **Tự chụp** rác sinh hoạt Việt Nam: hộp xốp, ly trà sữa có màng, túi nilon đen, hộp sữa tráng nhôm, khay cơm dính dầu | 300–500 ảnh |
| 3 | Kho tri thức RAG: quy định pháp luật + nội quy toà + lịch thu gom + danh mục nguy hại | 20–40 trang |

**Kiểm tra license từng dataset và ghi nguồn vào README.**
Ảnh tự chụp thì mình sở hữu — sạch tuyệt đối về tuân thủ, và chênh lệch accuracy giữa hai bộ là một phát hiện đáng đưa vào báo cáo.

**Khoảng cách miền là có thật và rất lớn.** TrashNet chụp từng món rác sạch, đơn lẻ, trên nền bìa trắng. Nghiên cứu 2026 cho thấy model đạt **94,18% trên TrashNet chỉ còn 41,04% trên RealWaste** (ảnh rác thật tại bãi rác). Vì vậy: (1) không bao giờ đưa con số accuracy của dataset công khai lên slide như thể đó là năng lực sản phẩm, (2) bộ ảnh tự chụp ở tầng 2 là bộ dữ liệu **quan trọng nhất**, không phải bộ bổ sung. Chi tiết ở `docs/research/sota-model-nhe-phan-loai-rac.md`.

Nền pháp lý cho phần "vì sao bây giờ": Luật Bảo vệ môi trường 2020 yêu cầu phân loại rác tại nguồn, Nghị định 45/2022/NĐ-CP có mức phạt. **Tra cứu lại điều khoản và hiệu lực hiện hành trước khi trích dẫn trong slide.**

---

## 7. Eval

- **Tập test 300–400 ảnh giữ riêng tuyệt đối**, không dùng để chỉnh prompt lần nào
- Báo cáo **tách riêng** nhóm dataset công khai vs nhóm ảnh tự chụp
- Chỉ số: accuracy · **macro-F1** · confusion matrix · **recall riêng cho nhóm nguy hại**
- **Chỉ số an toàn: tỉ lệ rác nguy hại bị phân loại thành rác thường — mục tiêu 0%.** In to trên slide.
- Bảng so sánh 3 tầng: accuracy × chi phí/ảnh × độ trễ p95
- Retrieval: **hit@1 · hit@5 · MRR** trên ~60 câu hỏi "bỏ đâu khi nào".
  ⚠️ Sửa so với bản đầu: **không dùng precision@5** — mỗi câu chỉ có 1–2 đoạn
  đúng nên chỉ số đó trần cứng ở 0,2–0,4, đọc lên gây hiểu nhầm là hệ thống dở.
  Đã có 18/60 câu ở `eval/retrieval_questions.py`, chạy bằng
  `python eval/run_retrieval_eval.py`
- Failure case: trình chiếu được **ảnh thật bị nhận sai** — lợi thế demo lớn nhất của đề này

Ca khó thật cần có trong tập test: hộp sữa giấy tráng nhôm ↔ giấy · ly nhựa có màng ↔ nhựa tái chế · khay cơm dính dầu ↔ rác thực phẩm.

---

## 8. Tech stack

| Layer | Chọn |
|---|---|
| Agent | LangGraph (`classify_waste → advise → schedule_pickup`) |
| LLM | **Lớp provider tách rời** ở `src/services/vision/` — Gemini · OpenAI-compatible (OpenAI/OpenRouter/NVIDIA) · CLIP local. Đổi bằng `VISION_PROVIDER`; **khai riêng từng tầng** bằng `VISION_PROVIDER_T1/_T2/_TEXT` (ADR-0006) |
| Backend | FastAPI + SQLAlchemy 2.x |
| Auth | Tự làm: PBKDF2 + JWT (ADR-0004) |
| DB | SQLite khi dev → PostgreSQL khi deploy |
| Vector | JSON list trong SQLite → pgvector khi lên Postgres; truy hồi hybrid BM25 + embedding. Embedding có **provider riêng** (`EMBEDDING_PROVIDER`) vì nơi sinh văn bản tốt chưa chắc có endpoint embedding dùng được |
| Ảnh | Pillow (EXIF, nén) + OpenCV (làm mờ mặt) + imagehash (pHash) |
| Frontend | Next.js 15 + Tailwind v4 + shadcn-style, ở `frontend/` |
| Tracing | LangSmith (deliverable #4) |
| Deploy | Render (backend + PostgreSQL) + Vercel (frontend) |
| App | Capacitor → APK Android; PWA cho iPhone và máy tính |
| Test | pytest + pytest-asyncio |

---

## 9. Quy ước làm việc

- **Ngôn ngữ:** docstring, comment, UI, tài liệu đều **tiếng Việt**. Tên biến/hàm tiếng Anh.
- **Code style:** ruff (`line-length 120`, double quotes, target py311). Type hints ở mọi hàm public. **Không dùng bare `except`.** Hàm giữ ngắn, tách file khi vượt ~300 dòng.
- **Kiểm soát chi phí:** mọi script chạy hàng loạt phải có `--limit` mặc định nhỏ (50–200) và in dự toán chi phí trước khi chạy. Cache mọi lệnh gọi LLM theo hash đầu vào. Mock LLM trong test — test không bao giờ gọi API thật.
- **Ngân sách:** ~1,5 triệu VND cho cả dự án. Đặt hard limit **$25/tháng** trên OpenAI platform + email cảnh báo ở 80%.
- **Quyết định quan trọng** → ghi ADR ngắn (~10 dòng) vào `docs/decisions/` **ngay lúc quyết định**, không viết bù sau.
- **Ghi `WORKLOG.md` mỗi ngày** và `JOURNAL.md` mỗi tuần — là deliverable, không phải việc phụ.
- **AI logging hooks** phải chạy `scripts/setup_hooks.ps1` một lần; thay `AI_LOG_API_KEY` trong `.env` bằng key riêng từ link mời của BTC (giá trị trong `.env.example` chỉ là placeholder).

---

## 10. Trạng thái hiện tại

> ⚠️ **Mục 10 và 11 dưới đây là ảnh chụp ngày 03/08 ở repo cá nhân.** Trạng thái
> thật của repo nhóm nằm ở [`docs/BAN_GIAO_2026-08-05.md`](docs/BAN_GIAO_2026-08-05.md).
> Tóm tắt nhanh tính tới 05/08: **277 test pass / 2 đỏ** · **51 route** · ruff
> sạch · frontend lint + tsc + build đều xanh · đường dữ liệu thùng thu gom đã
> liền mạch từ bảng tới bản đồ (`/dieu-phoi`) · máy trạng thái kiện tái chế đã
> dựng, đang di trú dở (còn bước cuối là lật các chỗ **ghi**) · **82 file chưa
> commit**.

**Cập nhật 03/08/2026 (buổi 2) — hai lỗi chặn của ngày 02/08 ĐÃ SỬA XONG, và
buổi 2 trả xong ba món nợ deliverable: `eval/run_eval.py`, ESLint cho frontend,
ADR-0008 đính chính phạm vi. Đọc
[BAN_GIAO_2026-08-03.md](docs/BAN_GIAO_2026-08-03.md), trong đó có **đặc tả YOLO
kèm số đo đã chạy thật** và một lỗi đang mở (`StatementError` ở đường ảnh).**

⛔ **Việc chặn lớn nhất hiện nay là bộ 100 ảnh tự chụp** — không có nó thì eval
không chạy được, ngưỡng T0.5 không chuẩn lại được, và YOLO không chứng minh được
là tốt hơn. Xem mục 11 việc 1.

Backend FastAPI 44 route · agent LangGraph có trace · frontend Next.js 21 màn ·
**139 test pass** · ruff sạch (3 cảnh báo còn lại nằm ở file mẫu của template và
`attic/`) · **ESLint 0 lỗi** (mới bật 03/08) · `tsc` sạch · export tĩnh ra `out/`
sạch · **repo đã `git init`**.

**Định tuyến nay chạy đa nhà cung cấp:** T1 NVIDIA `llama-3.2-90b-vision` ·
T2 Gemini flash · advise NVIDIA `llama-3.1-8b` (ADR-0006). Trang Vận hành hiện
bảng tầng → nhà cung cấp → model → có key chưa.

⚠️ **Không model NVIDIA nào nhìn ra đồ điện tử lẫn trong ảnh** — đo 03/08 trên
ảnh rác thật: llama-90b **0/6**, nemotron-12b 1/6, Gemini 2/2, **YOLO11n local
4/4 trong ~100ms và $0**. Chỉ số an toàn "rác nguy hại bị xếp thành rác thường"
vì thế đang trượt trên ảnh có đồ điện tử. Đây là lý do phần "nhìn" đang được
tính chuyển xuống tầng local — bàn giao 03/08 mục 3.

**Tầng T0.5 vừa được máy chủ 512 MB** nhờ bản CLIP nén int8: 185 MB RAM ·
56 ms/ảnh, nhanh hơn bản torch 8 lần (ADR-0007). Ngưỡng chấp nhận **chưa chuẩn
lại** — chờ bộ 100 ảnh tự chụp.

**RAG nay chạy hybrid thật.** Trước 02/08 phần embedding có code nhưng chưa
từng được nối: `embed_chunks()` không được gọi ở đâu, 0/13 đoạn có vector, và
`advise()` không truyền `query_embedding` — tức tài liệu ghi "hybrid" mà thực tế
là thuần BM25. Nay đã nối, đo được, và trang Vận hành hiện rõ đang chạy chế độ
nào.

Toàn bộ `docs/PLAN_APP_DEPLOY.md` đã thực hiện xong phần code (ADR-0005). Phần
còn lại là việc cần tài khoản của chủ dự án — xem mục 11.

### Cách chạy

```bash
python scripts/seed.py --reset --demo          # dữ liệu nền + dữ liệu demo
python -m uvicorn src.main:app --port 8000     # backend, docs ở /docs
npm --prefix frontend run dev                  # frontend ở :3000
```

Tầng T0.5 cần cài thêm: `pip install -r requirements-local-model.txt` (torch
1,19 GB đã tách khỏi `requirements.txt` để bản deploy nhẹ).

Tài khoản demo: `resident@demo.vn` · `cleaner@demo.vn` · `manager@demo.vn`,
mật khẩu chung `demo1234`. Màn đăng nhập có 3 nút vào thẳng.

### Đã có

| Phần | File | Ghi chú |
|---|---|---|
| Schema | `src/db/models.py` | 21 bảng · khối lượng thành **khoảng** `weight_min/max` (ADR-0003) · cờ `is_seed` |
| Dữ liệu nền | `src/db/seed_data.py`, `scripts/seed.py` | 9 nhóm rác, 3 toà, 8 tài khoản, lịch thu gom, 5 tài liệu quy định |
| Ảnh | `src/services/image.py` | tước EXIF, làm mờ mặt (Haar), nén 512px, pHash · **có test khẳng định EXIF đã sạch** |
| Model | `src/services/vision/` | Gemini · OpenAI-compatible (OpenAI/OpenRouter/NVIDIA) · CLIP local — đổi provider chỉ bằng `.env` |
| Định tuyến | `src/services/classifier.py` | T0 cache pHash → T0.5 CLIP → T1 → T2; escalate cả khi **nghi nguy hại**; **mỗi tầng một nhà cung cấp riêng** (ADR-0006) |
| An toàn | `src/services/safety.py` | 3 nhóm chặn cứng, ngưỡng riêng nhóm nguy hại, lý do từ chối chọn từ danh sách cố định |
| RAG | `src/services/rag.py` | hybrid BM25 + embedding, **lọc theo toà trước khi xếp hạng**, chạy được khi chưa có API key. Nhúng câu hỏi **có cache đĩa**; mất API thì tự lui về thuần BM25 |
| Eval truy hồi | `eval/run_retrieval_eval.py`, `eval/retrieval_questions.py` | 18 câu có đáp án · hit@k + MRR · so BM25 với hybrid · quét được trọng số vector |
| Thu gom + tuyến | `src/services/pickup.py`, `route_planner.py` | 3 điểm HITL, khối "vì sao gộp thế này", diff bản AI đề xuất ↔ bản người sửa |
| Agent | `src/agents/` | graph `classify → advise → schedule`, nhánh skip vẫn ghi node để trace thấy đường không đi |
| Vận hành | `src/services/metrics.py` | chi phí/độ trễ/lỗi tính từ dữ liệu thật, tách riêng bản ghi `is_seed` |
| API | `src/api/` | đúng hợp đồng `FRONTEND_SPEC.md` mục 7, khuôn lỗi `{error:{code,message_vi}}` |
| Frontend | `frontend/` | Next.js 15 + Tailwind v4 + shadcn-style, design token rút từ `original/GreenBin AI.dc.html` |
| ADR | `docs/decisions/0004-...md` → `0008-...md` | tự làm auth thay Supabase · PWA + Capacitor thay vì viết lại native · provider theo từng tầng · T0.5 chạy ONNX int8 · đính chính phạm vi cư dân/đồ cồng kềnh |
| Eval phân loại | `eval/run_eval.py`, `eval/metrics.py`, `eval/report_writer.py` | chạy đúng đường sản phẩm · hai bộ ảnh tách rời · accuracy + macro-F1 + confusion matrix + **chỉ số an toàn** · `--limit` 50 và in dự toán trước khi tiêu quota |
| Lint frontend | `frontend/eslint.config.mjs` | flat config ESLint 9, CI chạy `npm run lint` cùng tsc và build |
| T0.5 dạng nén | `scripts/export_clip_onnx.py`, `src/services/vision/local_clip.py` | xuất một lần trên máy có torch (hoặc Colab) → 2 file 89 MB đính GitHub Release; máy chủ tải qua `CLIP_ASSETS_URL`. Mã băm bộ câu mô tả chốt chặn việc dùng nhầm dãy số cũ |
| Linh vật | `scripts/build_assets.py`, `frontend/public/mascot/` | 3 tư thế × 3 bề rộng WebP (2,3 MB → 22–80 KB) · `Mascot` nhận prop `tuThe`, giữ SVG làm ảnh dự phòng |
| PWA | `frontend/public/sw.js`, `manifest.webmanifest` | service worker viết tay · **lịch thu gom xem được offline** · không bao giờ cache ảnh cư dân hay endpoint có token |
| App Android | `frontend/capacitor.config.ts`, `frontend/android/` | `output: "export"` → `out/` → Capacitor · camera gói trong `src/lib/platform.ts` |
| CI/CD | `.github/workflows/ci.yml`, `android.yml` | CI kiểm cả Python lẫn frontend · đẩy tag `v*` là build APK và đính vào Release |
| Sẵn sàng deploy | `render.yaml`, `Dockerfile` | Dockerfile nghe `$PORT` · `SEED_ON_START` tự nạp dữ liệu nền · seed gọi lại nhiều lần vô hại |

### Chưa có / đang chặn

- ✅ **Đã có key Gemini và NVIDIA** trong `.env` máy dev; luồng chụp ảnh chạy
  thật. **DeepSeek không nhận ảnh** nên vẫn không dùng được cho T1/T2.
  ✅ **Render nay đã đủ key và đủ ba biến `VISION_PROVIDER_*`** — đo 02/08 qua
  `ops/metrics`: `single_provider: false`, T1 nvidia · T2 gemini · text nvidia,
  cả ba `has_api_key: true`. Việc chặn này đã xong.
- ✅ **`VISION-500` đã sửa (03/08).** Nguyên nhân gốc **không phải** "model 11B
  quá nhỏ để bám JSON" như chẩn đoán 02/08, mà là **`max_tokens: 700` quá nhỏ
  nên JSON bị cắt cụt** (`finish_reason: "length"`). Nay trần 2000 + prompt v3
  gộp món trùng. T1 đổi sang `llama-3.2-90b-vision` sau khi đo trên ảnh thật.
- ✅ **`nhieu_vat` đã sửa (03/08).** Nay chỉ từ chối khi trong các nhóm phát hiện
  được **có nhóm nguy hại**; nhựa + giấy + thuỷ tinh vẫn trả lời bình thường.
  Đây là **bản vá tạm** có chủ đích — cách gốc là hướng A (thôi ép một nhãn duy
  nhất), đặc tả ở [BAN_GIAO_2026-08-02.md](docs/BAN_GIAO_2026-08-02.md) mục 4.
- ⛔ **`SRV-500 / StatementError` khi gửi ảnh lên bản deploy** — chỉ ở đường ảnh,
  chỉ trên PostgreSQL, đường chữ vẫn chạy tốt. Đã loại trừ 9 giả thuyết; cần log
  Render để chốt. [BAN_GIAO_2026-08-03.md](docs/BAN_GIAO_2026-08-03.md) mục 5.
- ✅ **Chi phí T1 đã hết hiện sai (03/08).** Tra ra là NVIDIA **không công bố giá
  $/1M token** cho `llama-3.2-90b-vision` và `llama-3.1-8b` — tier developer chạy
  bằng credit + giới hạn nhịp. Nên **không điền số mò** vào
  `MODEL_PRICES_USD_PER_MTOK`; thay vào đó `cost_metrics` trả thêm `price_known`
  từng tầng và trang Vận hành hiện **"chưa có giá"** thay vì "$0". Tầng chạy trên
  máy mình (T0, T0.5) vẫn là $0 thật. Lý do đầy đủ ở comment trong `src/config.py`.
- Repo GitHub đã có, `.env` đã có. Chưa chạy `scripts/setup_hooks.ps1` → AI
  logging (deliverable #4) vẫn chưa chạy.
- ✅ **`eval/run_eval.py` đã viết xong (03/08)** — chạy đúng đường sản phẩm, tách
  hai bộ ảnh, `--limit` mặc định 50 và phải `--dong-y` mới gọi model. **Chưa có
  ảnh để chạy.** Ba quy ước đếm (từ chối ≠ sai · từ chối không vào tử số chỉ số
  an toàn · `model_loi` là lỗi chứ không phải từ chối) ghi ở
  `eval/results/report.md` mục 3.
- ⛔ **Vẫn chưa có bộ 100 ảnh tự chụp** → số liệu trang Chất lượng AI hiện đang là
  **dữ liệu demo mô phỏng**, có gắn nhãn rõ trên UI. Đây là thứ đang chặn nhiều
  việc nhất: eval phân loại, chuẩn lại ngưỡng T0.5, và việc chứng minh YOLO tốt
  hơn thay vì chỉ nói là tốt hơn.
- Chưa phỏng vấn lao công + BQL — vẫn là chỗ yếu nhất của ADR-0002/0003.
- ✅ **Đã đính chính phạm vi bằng [ADR-0008](docs/decisions/0008-dinh-chinh-pham-vi-cu-dan-do-cong-kenh.md)
  (03/08).** 4 bài đăng nhóm cư dân (01/08) cho thấy cư dân **có** pain point rõ ở
  đồ cồng kềnh. **Không lật ADR-0002** — chỉ thu hẹp câu "cư dân không có pain
  point" thành "không có ở rác hằng ngày, **có** ở đồ cồng kềnh", và nâng luồng
  đăng ký thu gom từ "chạm nhẹ" lên **đầu vào chính của bài toán điều phối**.
  Không đổi dòng code nào. ADR ghi kèm 4 giới hạn của bằng chứng — **cấm suy ra
  tỉ lệ nào** từ 4 bài đó. Ảnh gốc có tên thật và số căn hộ nên **không đưa vào
  repo**, giữ ở `C:\AI20K\Thực trạng\`.
- ✅ Đã deploy Render + Vercel (**đổi từ Railway sang Render**, ADR-0005) và CI
  đã chạy xanh — xem mục 11. **Chưa ai cầm máy Android thử APK.**

---

## 11. Việc tiếp theo (theo thứ tự)

> 📌 **ĐỌC TRƯỚC: [`docs/BAN_GIAO_2026-08-03.md`](docs/BAN_GIAO_2026-08-03.md)**
> — bàn giao phiên 03/08, **mới nhất**: nguyên nhân gốc thật của `VISION-500` ·
> **đặc tả YOLO kèm số đo đã chạy thật trên ảnh rác** · một lỗi đang mở
> (`StatementError`) · 4 chỗ đã đoán sai.
>
> ⚠️ Hai chỗ trong bàn giao đó **đã lạc hậu**: (1) nó ghi "2 commit chưa push",
> thực tế có **6 commit chưa push** tính cả phiên buổi 2; (2) nó dặn "viết
> ADR-0008 cho YOLO" — số 0008 nay đã dùng cho ADR đính chính phạm vi, nên **ADR
> của YOLO là 0009**. Và mục 8 của nó ghi `WORKLOG.md` "trống hoàn toàn" là sai:
> file có đủ 27/07 → 03/08, chỉ còn sót block mẫu ở cuối (đã dọn).
>
> Bàn giao phiên trước: [`docs/BAN_GIAO_2026-08-02.md`](docs/BAN_GIAO_2026-08-02.md)
> — 5 commit, **đặc tả hướng A "một ảnh nhiều món"** (vẫn là kế hoạch đang dùng),
> kỹ thuật gỡ lỗi trên bản deploy · [`docs/BAN_GIAO_2026-08-01.md`](docs/BAN_GIAO_2026-08-01.md)
> — 10 lỗi đã sửa kèm nguyên nhân, số đo token/quota thật.
>
> ✅ **`docs/PLAN_APP_DEPLOY.md` đã xong** (ADR-0005) và **đã deploy thật**:
> backend https://greenbin-api-hozl.onrender.com · web https://test-gbai-gray.vercel.app
> · repo https://github.com/imninh/Test_GBAI · CI xanh.
>
> ✅ **Bản deploy nay chạy đúng provider theo từng tầng** (ADR-0006) — việc chặn
> `NVIDIA_API_KEY` + `VISION_PROVIDER_*` đã xong, đo 02/08. Còn lại:
> `CLIP_ASSETS_URL` trỏ vào bộ ONNX đính trong GitHub Release → T0.5 sống lại
> (ADR-0007, các bước ở `docs/HUONG_DAN_DEPLOY.md`).

0. **Push 6 commit đang nằm local.** Sau đó `ops/metrics` mới báo
   `prompt_version: v3`, và CI mới chạy bước lint frontend vừa thêm.
1. ⛔ **Chụp 100 ảnh tự chụp + 1 dataset công khai.** Đây là thứ **chặn nhiều
   việc nhất**, và không ai làm hộ được: nó chặn eval phân loại, chặn việc chuẩn
   lại `CLIP_ACCEPT_CONFIDENCE` cho bản ONNX, và chặn cả việc **chứng minh** YOLO
   tốt hơn thay vì chỉ nói là tốt hơn. Bộ tự chụp là bộ **quan trọng nhất**,
   không phải bộ bổ sung. Nhớ có **ảnh nhiều món** — đó là ca khó thật của đề.
2. **Chạy `eval/run_eval.py`** (script đã sẵn sàng từ 03/08). Xếp ảnh vào
   `data/eval/<cong_khai|tu_chup>/<mã nhóm>/`, chạy `--liet-ke` để kiểm, rồi
   `--dong-y`. Chép bảng kết quả vào `eval/results/report.md` mục 3, thay dữ liệu
   `is_seed` trên trang Chất lượng AI bằng số đo thật.
3. **Chạy `scripts/setup_hooks.ps1`** — AI logging là deliverable #4, đang trống.
   Nhớ thay `AI_LOG_API_KEY` trong `.env` bằng key riêng từ link mời của BTC.
4. Phỏng vấn **1 lao công + 1 người BQL** — chỗ yếu nhất của ADR-0002 và ADR-0003.
   ADR-0008 **không vá được** chỗ này: nó là tiếng nói cư dân, không phải người
   vận hành.
5. **Làm YOLO ở T0.5** theo đặc tả `docs/BAN_GIAO_2026-08-03.md` mục 3 —
   **ADR-0009** (không phải 0008), và **tách `classifier.py` trước** (đang 564
   dòng, `classify_waste` 272 dòng, vượt ngưỡng ~300 dòng/file của mục 9).
   Ràng buộc dễ quên nhất: **YOLO THAY CLIP, không cộng thêm** — Render chỉ có
   512 MB.
6. **Lấy log Render cho `SRV-500 / StatementError`** (mục 5 bàn giao 03/08).
   Nghi ngờ hàng đầu: `stored_path`/`original_path` là `String(400)`, Postgres ép
   độ dài còn SQLite thì bỏ qua. **Đừng sửa mò khi chưa có 2 dòng log đó.**
7. Đi xuống phòng rác tầng chụp ảnh — 10 phút, kiểm ràng buộc "2–3 thùng".
8. Xin số liệu khối lượng rác theo loại từ BQL để thay con số "80%" chưa kiểm.
9. Viết tiếp bộ câu hỏi truy hồi từ 18 lên ~60 câu rồi mới chốt `RAG_VECTOR_WEIGHT`.
10. Cập nhật `docs/BAO_CAO_MENTOR_2026-07-29.md` theo ADR-0003 + ADR-0004.
11. Viết lại mục 0 `FRONTEND_SPEC.md` theo góc vận hành (ADR-0002 việc 12/18).
12. *(P1)* Màn Báo cáo tuân thủ theo tháng cho BQL.
13. *(P1)* Fine-tune model T0.5 trên ảnh tự chụp — chỉ làm sau khi việc 1 và 2 xong.

**Lưu ý khi làm backend:** hợp đồng API ở mục 7 của `docs/FRONTEND_SPEC.md` là bản cam kết với frontend. Đổi tên trường hay đường dẫn thì sửa cả hai nơi cùng lúc.

---

## 12. Ghi chú cho session sau

- Chủ dự án là **học viên AI20K, làm việc bằng tiếng Việt**, muốn được tư vấn kỹ trước khi code, và **tự làm thử một mình trước** rồi mới chia việc cho nhóm 4 người.
- Frontend **không code trong session này** — chủ dự án tự thiết kế bằng công cụ design rồi mang code về.
- Khi tư vấn: nêu rõ đánh đổi, đưa khuyến nghị cụ thể chứ không liệt kê hết lựa chọn, và **luôn gắn việc đang làm với tiêu chí chấm/PLO** để biết việc nào đáng làm.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **P-075** (1715 symbols, 2054 relationships, 17 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/P-075/context` | Codebase overview, check index freshness |
| `gitnexus://repo/P-075/clusters` | All functional areas |
| `gitnexus://repo/P-075/processes` | All execution flows |
| `gitnexus://repo/P-075/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
