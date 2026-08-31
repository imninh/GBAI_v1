# Development Journal — GreenBin AI (VHR-17)

> **Deliverable #8.** Nhật ký các quyết định kỹ thuật quan trọng, khó khăn gặp phải
> và cách nhóm giải quyết. Ghi theo mốc phát triển (~6 tuần, 23/07 → 31/08/2026).

---

### Tuần 1 (cuối 07) — Khung & định hướng
Chốt bài toán VHR-17: agent phân loại rác tại nguồn + điều phối thu gom cho toà
chung cư, phục vụ **3 vai** (cư dân · đội vệ sinh · ban quản lý). Dựng khung
FastAPI + Next.js, chọn kiến trúc phân tầng (API → services → db) để mỗi tầng
kiểm thử độc lập được.

### Quyết định 1 — Phân loại AI **4 tầng** thay vì gọi thẳng một model
Vấn đề: gọi cloud LLM cho mọi ảnh vừa chậm vừa tốn quota. Giải pháp: xếp tầng
**T0 cache pHash → T0.5 CLIP chạy tại chỗ → T1/T2 cloud LLM → HITL**. Ảnh trùng
được cache trả ngay; ca dễ CLIP chốt tại chỗ ($0); chỉ ca khó mới leo cloud. Đo
được: T0.5 bản ONNX int8 chỉ **88,7 MB / 185 MB RAM / 56 ms/ảnh**, lọt máy chủ
512 MB — mở đường chạy offline.

### Quyết định 2 — Quyền riêng tư đặt trước, không có đường tắt
Ảnh rác có thể dính **toạ độ GPS (EXIF)** và **khuôn mặt**. Nhóm chốt: mọi ảnh
phải qua `preprocess_image` (tước EXIF + làm mờ mặt + nén) **trước khi rời máy
chủ**; tầng phân loại chỉ nhận `ProcessedImage`, không nhận bytes thô — nên
không thể vô tình gửi ảnh chưa xử lý cho nhà cung cấp. Có test chốt chặn điều này.

### Quyết định 3 — Human-in-the-loop (HITL) cho ca AI không chắc
AI không được tự quyết ca nguy hại/độ tin thấp. Dựng **3 hàng đợi duyệt** cho ban
quản lý (xác nhận nhãn, duyệt yêu cầu, xử lý sự cố). Ngưỡng tin cậy + cờ
`escalated_to_human` đẩy đúng ca cần người vào hàng đợi — vừa an toàn vừa gom được
dữ liệu cải tiến (HITL feedback).

### Quyết định 4 — Tối ưu tuyến thu gom có phương án lui
Dùng **PyVRP** cho bài toán định tuyến; nhưng nếu solver lỗi/hết giờ thì **tự lui
về greedy + nearest-neighbor + 2-opt** thay vì gãy. Test chốt: thuật toán không
làm mất điểm dừng, không dài hơn thứ tự đầu vào, và cho kết quả **xác định**.

### Quyết định 5 — Thùng thông minh IoT (ESP32) coi là client không tin được
Đường thiết bị có xác thực khoá, chống phát lại (HMAC + timestamp), và **idempotency
theo `item_id`** để gửi lại không tạo bản ghi trùng. Firmware không cần biết khái
niệm "phiên" — server tự gắn kết quả vào phiên bỏ rác đang mở của thùng.

### Quyết định 6 — RAG tư vấn đúng quy định
Kho quy định phân loại được truy hồi **hybrid BM25 + embedding**. Đo trên 18 câu:
**hit@5 = 1,000** — model luôn nhận được đoạn quy định đúng trong 5 đoạn đầu. Tự
nhận giới hạn (bộ câu do nhóm viết) và **cố ý không overfit** trọng số vào bộ test
của chính mình.

### Kỷ luật kiểm thử — test là hợp đồng, không phải "cho có"
Xây tới **1367 test tự động**, **0 test gọi API thật** (model thay bằng
`FakeVisionClient` → chi phí chạy test bằng 0, kết quả xác định). Mỗi nhóm test
chốt một lời hứa sản phẩm: quyền riêng tư ảnh, không đường tắt tới "hoàn tất", nhân
viên không đọc được dữ liệu của người khác, client không tự quyết `role`…

### Tuần cuối (cuối 08) — Deploy & vận hành
Đóng gói **Docker multi-stage** (non-root + healthcheck), CI GitHub Actions
(lint Ruff + 1367 test + build frontend), và **deploy production từ repo tổ chức
qua workflow yaml** (FE Vercel + BE Railway) — vượt qua rào org private chặn
Git-connect bằng cách deploy qua CLI + token trên self-hosted runner. Dữ liệu &
ảnh bền vững trên **Supabase** (Postgres + Storage riêng tư), múi giờ pin
Asia/Ho_Chi_Minh, login có rate-limit chống dò mật khẩu.

---

**Bài học lớn nhất:** một con số đo được chỉ có nghĩa khi nói rõ **đo trên cái gì**
— nhóm giữ nguyên tắc này xuyên suốt (xem `evaluation.md`), kể cả khi nó buộc phải
ghi "chưa có giá" thay vì "$0", hay giữ lại một lần chạy hỏng làm bằng chứng cho
cơ chế tự-cảnh-báo của bộ đánh giá.
