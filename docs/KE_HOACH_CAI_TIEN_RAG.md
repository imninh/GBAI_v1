# KẾ HOẠCH CẢI TIẾN HỆ THỐNG RAG CHATBOT (GREENBIN AI / GREENBIN OPS)
> **Mã tài liệu:** `GB-RAG-IMP-2026`  
> **Áp dụng:** Nhóm dự án GreenBin AI (P-075)  
> **Căn cứ kỹ thuật:** Cẩm nang Production RAG `hd.md`, CSDL Pháp luật `docs/LEGAL_KNOWLEDGE_BASE_RAG.md` và Bộ đánh giá chuẩn `eval/chatbot_golden_dataset.json`.

---

## 1. TỔNG QUAN & BỐI CẢNH

Hệ thống Chatbot RAG của GreenBin AI phục vụ 3 nhóm nghiệp vụ trọng tâm:
1. **F1 (Pháp luật & Quy chế):** Tra cứu mức xử phạt vi phạm hành chính (Nghị định 45/2022/NĐ-CP), quy định phân loại 3 nhóm rác bắt buộc (Luật BVMT 2020), hướng dẫn kỹ thuật chi tiết từng loại rác (Công văn 9368/BTNMT-KSONMT) và nội quy tòa nhà.
2. **F2 (Dữ liệu Thùng rác IoT thời gian thực):** Tra cứu các thùng rác thông minh còn chỗ (<70% dung tích), phân loại rác tiếp nhận và tính khoảng cách thực tế từ tọa độ GPS của cư dân.
3. **F3 (Cẩm nang Hướng dẫn Sử dụng App):** Hướng dẫn 5 tab chức năng (Phân loại, Yêu cầu, Lịch, Điểm gửi, Tôi), quy trình chụp ảnh/gõ chữ, đặt lịch thu gom cồng kềnh, hoạt động offline và chính sách bảo mật/quyền riêng tư ảnh.

### Vấn đề tồn tại ở phiên bản hiện tại (Baseline):
- **Phân loại Intent bị nhầm lẫn:** Câu hỏi có yếu tố xử phạt vứt rác chung cư (*QA-03*) bị phân loại nhầm sang `bin_query`. Câu hỏi quy chuẩn kích thước đồ cồng kềnh (*QA-14*) bị phân loại nhầm sang `app_guide`.
- **Chất lượng Retrieval & Dữ liệu Tri thức chưa phủ kín:** Một số câu hỏi pháp lý quan trọng như mức phạt không phân loại tại nguồn (*QA-01*), phân loại 3 nhóm rác (*QA-02*), bóc tách vỏ hộp sữa Tetra Pak (*QA-07*), quyền từ chối tiếp nhận của BQL (*QA-08*) chưa truy hồi được đoạn đúng lên Rank 1, dẫn đến câu trả lời bị ảo giác hoặc trả về thông báo "chưa có thông tin".
- **Độ trễ cao (Latency ~6.88s):** Do phải gọi LLM phân loại intent khi rule-based đơn giản bị trượt.

---

## 2. MỤC TIÊU & CHỈ SỐ KỲ VỌNG (TARGET KPIS)

| Chỉ số / Tiêu chuẩn | Hiện trạng (Baseline) | Mục tiêu sau cải tiến | Phương pháp đo lường |
| :--- | :--- | :--- | :--- |
| **Độ chính xác Intent (Intent Accuracy)** | 88.9% | **100%** | Đánh giá trên 18 câu Golden Dataset |
| **Tỷ lệ chặn Tấn công (Guardrail Defense Rate)** | 100.0% | **100.0%** | Kiểm thử với bộ Adversarial & Jailbreak |
| **Retrieval Hit@1 (MRR)** | 72.2% | **$\ge$ 95.0%** | Đo thứ hạng đoạn văn đúng đầu tiên |
| **Faithfulness (Tính trung thực / Không ảo giác)** | 83.3% | **100.0%** | Không bịa đặt, trích dẫn chuẩn Điều/Khoản |
| **Độ trễ trung bình (Avg Latency)** | 6,877 ms | **$\le$ 2,500 ms** | Đo thời gian phản hồi toàn luồng |
| **CI/CD Quality Gate** | Đạt mức tối thiểu | **Vượt trội toàn diện (PASSED)** | Tự động hóa qua `run_chatbot_eval.py` |

---

## 3. NỘI DUNG & GIẢI PHÁP CẢI TIẾN CHI TIẾT

### Giai đoạn 1: Nâng cấp Toàn diện Cơ sở Dữ liệu Tri thức (Knowledge Base)
- **Chuẩn hóa cấu trúc tài liệu:** Áp dụng Structure-Aware Chunking từ `docs/LEGAL_KNOWLEDGE_BASE_RAG.md` vào `src/db/seed_data.py`, `data/legal_knowledge_chunks.json`, `data/app_guide_chunks.json`.
- **Làm giàu ngữ cảnh (Chunk Enrichment & Keywords):**
  - Bổ sung `Contextual Prepend` (tên văn bản + điều khoản) vào từng chunk.
  - Bổ sung hệ thống từ khóa phong phú và các thuật ngữ đồng nghĩa: *Tetra Pak, vỏ hộp sữa giấy tráng nhôm, sofa, nệm, giường tủ, đồ cồng kềnh, pin cũ, bóng đèn huỳnh quang, nước tẩy bồn cầu, vứt rác hành lang, chung cư, mức phạt, 500k, 1 triệu, 2 triệu, 10 triệu, người gây ô nhiễm phải trả tiền*.

### Giai đoạn 2: Tối ưu Bộ Định tuyến Intent (Cascade Intent Classifier) & Guardrails
- **Thuật toán Multi-Signal Weighted Rule Scorer:**
  - Thiết lập ma trận trọng số ưu tiên: các từ khóa chứa hành vi pháp lý, chế tài ("bị phạt bao nhiêu", "mức phạt", "quy định", "luật 72", "nghị định 45", "điều 26", "điều 29", "điều 75", "có được phép", "bắt buộc") luôn có điểm số vượt trội so với từ khóa tìm vị trí thùng rác.
  - Phân loại chính xác 100% các câu hỏi thuộc 4 nhóm (`waste_law`, `bin_query`, `app_guide`, `out_of_scope`) trong thời gian $< 1$ms.
- **Input & Output Guardrails:**
  - Bảo toàn bộ lọc Injection, Unicode NFKC normalization, PII scrubber và Canary Token kiểm tra an toàn.

### Giai đoạn 3: Tối ưu Tầng Truy hồi (Enhanced Hybrid Retrieval & RRF)
- **BM25 + Semantic Search + Synonym Normalization:**
  - Chuẩn hóa từ vựng tiếng Việt, ánh xạ từ đồng nghĩa trực tiếp khi tokenize.
  - Tăng trọng số điểm tương đồng cho tiêu đề mục (`section`) và danh sách `keywords`.
  - Hợp nhất xếp hạng RRF (Reciprocal Rank Fusion k=60) hoặc Weighted Normalization đưa đoạn đúng nhất lên Top-1.
  - Áp dụng kỹ thuật Lost-in-the-Middle mitigation (`front + back[::-1]`).

### Giai đoạn 4: Tối ưu Tầng Sinh & Prompt Strict Grounding
- **Prompt Engineering định hướng Chain-of-Evidence:**
  - Yêu cầu LLM ưu tiên trích xuất số liệu cụ thể (mức phạt tiền, kích thước $>0.5m$ hoặc $>10kg$, hạn 31/12/2024, 3 nhóm bắt buộc).
  - Trích dẫn rõ ràng tên văn bản và Điều/Khoản.
  - Triệt tiêu hoàn toàn hiện tượng từ chối nhầm ("chưa có thông tin") khi ngữ cảnh đã có dữ kiện.
- **Tool-Augmented RAG cho Dữ liệu Thùng rác IoT (F2):**
  - Đảm bảo tính toán khoảng cách GPS chính xác và làm mới trạng thái thùng rác demo.

---

## 4. KỊCH BẢN KIỂM TRA & NGHIỆM THU

1. **Bộ câu hỏi kiểm thử (Golden Dataset 18 câu - 4 tầng phân loại):**
   - **Easy (6 câu):** Tra cứu trực tiếp mức phạt NĐ 45, 3 nhóm rác Luật BVMT 2020, chức năng app.
   - **Medium (6 câu):** Vỏ hộp sữa Tetra Pak, quyền từ chối của BQL, chai nước tẩy bồn cầu, đặt lịch cồng kềnh, tính năng offline, màu sắc mức đầy thùng rác.
   - **Hard (3 câu):** Tìm thùng rác gần Đinh Tiên Hoàng theo GPS, quy chuẩn kích thước rác cồng kềnh ($0.5m \times 0.5m \times 0.5m$ / $10$kg), chính sách bảo mật ảnh.
   - **Adversarial (3 câu):** Injection prompt, jailbreak, câu hỏi ngoài phạm vi (thơ bóng đá, xổ số).
2. **Quy trình nghiệm thu:**
   - Chạy `eval/run_chatbot_eval.py` ghi nhận báo cáo chi tiết.
   - Chạy `pytest tests/test_chatbot.py tests/test_services/test_rag.py`.
   - Xuất Báo cáo Đánh giá Kết quả Nghiệm thu tại `docs/BAO_CAO_DANH_GIA_RAG.md`.
