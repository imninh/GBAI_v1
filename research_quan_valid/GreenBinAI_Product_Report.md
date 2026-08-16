# 🌿 GreenBin AI (VHR-17)

## BÁO CÁO TOÀN DIỆN SẢN PHẨM & KIẾN TRÚC HỆ THỐNG
### Agent Phân Loại Rác & Điều Phối Thu Gom Tái Chế Thông Minh

> **Hệ sinh thái đồng bộ:** Thiết bị IoT 3 khối module · App mobile cư dân/nhân viên (Capacitor/PWA) · Web quản lý đơn vị thu gom (Next.js/Vercel) · Backend Agentic AI (FastAPI/LangGraph/Render)

---

## Mục Lục

1. [Tầm nhìn & Bối cảnh Pháp lý Việt Nam](#1-tầm-nhìn--bối-cảnh-pháp-lý-việt-nam)
2. [Bài toán Sản phẩm & Ba Vai trò Hệ thống](#2-bài-toán-sản-phẩm--ba-vai-trò-hệ-thống)
3. [Kiến trúc Tổng quan Hệ thống (C4 Model)](#3-kiến-trúc-tổng-quan-hệ-thống-c4-model)
4. [Định tuyến AI 4 Tầng Tối ưu Chi phí (4-Tier Model Routing)](#4-định-tuyến-ai-4-tầng-tối-ưu-chi-phí-4-tier-model-routing)
5. [Agent LangGraph, 3 Điểm HITL & Guardrails](#5-agent-langgraph-3-điểm-hitl--guardrails)
6. [Bảo mật & Quyền riêng tư Ảnh (Privacy-Preserving AI)](#6-bảo-mật--quyền-riêng-tư-ảnh-privacy-preserving-ai)
7. [Thiết bị IoT Phần cứng — 3 Khối Module & 4 Giải pháp](#7-thiết-bị-iot-phần-cứng--3-khối-module--4-giải-pháp)
8. [Luồng Nghiệp vụ RAG Hybrid & Thuật toán Gộp tuyến](#8-luồng-nghiệp-vụ-rag-hybrid--thuật-toán-gộp-tuyến)
9. [Giám sát IoT Thùng rác Thông minh & Đo đạc Hệ thống](#9-giám-sát-iot-thùng-rác-thông-minh--đo-đạc-hệ-thống)
10. [Quy trình Tiếp nhận Rác Tái chế & Chứng từ Pháp lý](#10-quy-trình-tiếp-nhận-rác-tái-chế--chứng-từ-pháp-lý)
11. [Mô hình Dữ liệu (23 Bảng CSDL) & Bề mặt API (51 Routes)](#11-mô-hình-dữ-liệu-23-bảng-csdl--bề-mặt-api-51-routes)
12. [Hướng dẫn Build Demo Bìa Các-tông](#12-hướng-dẫn-build-demo-bìa-các-tông)
14. [Phân Tích Thị Trường & Nền Tảng Cạnh Tranh](#14-phân-tích-thị-trường--nền-tảng-cạnh-tranh)
13. [Giới hạn Kỹ thuật, Bài học Thực nghiệm & Lộ trình Triển khai](#13-giới-hạn-kỹ-thuật-bài-học-thực-nghiệm--lộ-trình-triển-khai)

---

# 1. Tầm Nhìn & Bối Cảnh Pháp Lý Việt Nam

## 1.1. Vấn đề Thực tế
Theo quy định bắt buộc của **Luật Bảo vệ Môi trường 2020**, từ ngày 01/01/2025, tất cả hộ gia đình và tổ chức tại Việt Nam phải thực hiện phân loại rác tại nguồn. Tuy nhiên:
- 🔴 **Ban quản lý (BQL) & Đội vệ sinh:** Chịu áp lực pháp lý nặng nề nhưng phải phân loại rác thủ công bằng tay tại phòng rác tầng, dốc rác nguy hại lẫn lộn.
- 🔴 **Cư dân:** Thiếu công cụ hướng dẫn trực quan, đăng ký thu gom đồ cồng kềnh/rác nguy hại tự phát qua tin nhắn thủ công.
- 🔴 **Đơn vị thu gom:** Thiếu số liệu minh bạch về lượng rác phát sinh, không có hạ tầng số đáp ứng báo cáo EPR (Extended Producer Responsibility).

## 1.2. Giải pháp GreenBin AI (VHR-17)
**GreenBin AI** là lớp vận hành số hóa (Operational Layer) ứng dụng AI Agentic kết hợp IoT nhằm **tự động hóa phân loại rác tái chế, định tuyến thu gom thông minh và minh bạch hóa dữ liệu môi trường**.

> [!IMPORTANT]
> **Nguyên tắc xuyên suốt (ADR-0002):** *Mỗi kết quả AI phải sinh ra một hành động hoặc một bản ghi trong hệ thống. Không được dừng ở một màn hình trả lời văn bản thuần túy.*

## 1.3. Căn cứ Pháp lý Việt Nam

| Văn bản pháp luật | Nội dung bắt buộc | Tác động tới hệ thống GreenBin AI |
|-------------------|------------------|------------------------------------|
| **Luật BVMT 2020** (72/2020/QH14) | Bắt buộc phân loại rác tại nguồn thành 3 nhóm lớn (Tái chế, Thực phẩm, Còn lại). | Định hình luồng phân loại & RAG truy vấn quy định tòa nhà. |
| **NĐ 45/2022/NĐ-CP** | Phạt 500.000 – 1.000.000 VNĐ đối với hộ gia đình không phân loại rác. | Cung cấp công cụ chụp ảnh tra cứu & xác nhận bằng chứng vi phạm. |
| **NĐ 08/2022/NĐ-CP & TT 02/2022** | Quy định quản lý chứng từ chất thải nguy hại (CTNH Mẫu 04 - 4 liên). | Số hóa quy trình bàn giao chứng từ giữa nhà máy & đơn vị thu gom. |
| **NĐ 110/2026/NĐ-CP** | Quy định trách nhiệm tái chế bao bì của nhà sản xuất (EPR). | Tự động tổng hợp dữ liệu khối lượng tái chế xuất báo cáo Cổng EPR. |

---

# 2. Bài Toán Sản Phẩm & Ba Vai Trò Hệ Thống

Hệ thống được thiết kế xoay quanh ma trận phân quyền 3 vai trò người dùng thực tế (`resident`, `cleaner`, `manager`):


![Sơ đồ luồng 1](diagrams/GreenBinAI_Product_Report_diagram_1.png)


### Chi tiết phân công công việc:

| Vai trò | Người thật là ai | Hành động chính trong hệ thống |
|---------|------------------|--------------------------------|
| `resident` | Cư dân tòa nhà / khu đô thị | Chụp/mô tả rác · Đăng ký thu gom đồ cồng kềnh · Xem lịch thu gom · Xem ảnh cá nhân đã bị tước EXIF/mờ mặt · Tìm thùng rác gần nhất. |
| `cleaner` | Đội vệ sinh phòng rác tầng | Phân loại tại chỗ tập kết · Xác nhận nhãn AI khi conf thấp hoặc nghi nguy hại (**HITL #2**) · Chạy tuyến thu gom · Đánh dấu điểm dừng đã xong · Xem bản đồ thùng rác. |
| `manager` | BQL tòa nhà / Đơn vị thu gom | Duyệt yêu cầu thu gom vượt ngưỡng khối lượng/kích thước (**HITL #1**) · Duyệt tuyến thu gom do agent đề xuất (**HITL #3**) · Quản lý danh mục & chất lượng AI · Xem ảnh gốc (có ghi AuditLog). |

> [!NOTE]
> **Phạm vi rác xử lý bởi AI (ADR-0003):** AI tập trung xử lý **Luồng B** (rác tái chế, đồ cồng kềnh, rác nguy hại). **Luồng A** (rác ướt thực phẩm đóng túi nilon đục) nằm ngoài phạm vi vision vì camera không nhìn xuyên túi.

---

# 3. Kiến Trúc Tổng Quan Hệ Thống (C4 Model)

GreenBin AI sử dụng kiến trúc phân tầng chuẩn hóa C4 Model nhằm tách biệt môi trường trình diễn tĩnh và hạ tầng tính toán AI backend.

## 3.1. Sơ đồ Ngữ cảnh (C4 Level 1)


![Sơ đồ luồng 2](diagrams/GreenBinAI_Product_Report_diagram_2.png)


## 3.2. Sơ đồ Container (C4 Level 2)

Hệ thống được thiết kế theo nguyên tắc **Single Build / Multi-Distribution (ADR-0005)**:


![Sơ đồ luồng 3](diagrams/GreenBinAI_Product_Report_diagram_3.png)


## 3.3. Sơ đồ Phân tầng Backend (C4 Level 3)

Backend áp dụng nguyên tắc phân tầng nghiêm ngặt: **Router không chứa logic nghiệp vụ, chỉ nối HTTP ↔ Service**.

```text
src/
├── api/            # Lớp HTTP Routers (classify, media, pickups, routes, ops, bins)
├── agents/         # Điều phối workflow LangGraph (graph.py, nodes/classify_node.py)
├── services/       # Lớp Nghiệp vụ thuần (classifier.py, rag.py, pickup.py, route_planner.py, metrics.py)
├── db/             # CSDL SQLAlchemy 2.x (models.py - 23 bảng, session.py)
└── vision/         # Providers đấu nối AI (gemini, openai_compat, local_clip)
```

---

# 4. Định Tuyến AI 4 Tầng Tối Ưu Chi Phí (4-Tier Model Routing)

Để vừa đạt thời gian phản hồi nhanh, vừa tiết kiệm chi phí API, hệ thống triển khai cơ chế định tuyến 4 tầng (PLO 1 & PLO 5):


![Sơ đồ luồng 4](diagrams/GreenBinAI_Product_Report_diagram_4.png)


### Bảng thông số kỹ thuật 4 tầng:

| Tầng | Tên công nghệ | Chạy ở đâu | Điều kiện kích hoạt | Chi phí | Độ trễ đo thực tế |
|------|---------------|------------|---------------------|---------|-------------------|
| **T0** | Cache pHash | CSDL PostgreSQL | Ảnh trùng / gần trùng đã phân loại trước đó (Khoảng cách Hamming ≤ 6). | **$0** | Vài ms |
| **T0.5** | CLIP ONNX int8 | CPU Máy chủ backend | Rất chắc chắn VÀ không dính nhóm rác nguy hại (`local_never_decides_hazardous=True`). | **$0** | 56 ms (dev) / 2.595 ms (Render free) |
| **T1** | Llama-3.2-90b Vision | NVIDIA NIM / OpenRouter | Phần lớn lưu lượng nghiệp vụ thông thường. | **Credit** | 10 – 28 s |
| **T2** | Gemini Flash | Google Vision API | Confidence thấp, nghi ngờ rác nguy hại, hoặc phát hiện nhiều vật thể phức tạp. | **Quota 20 req/ngày** | P95 ~40 s (Deploy) |

> [!WARNING]
> **Quy tắc An toàn T0.5:** T0.5 local **không bao giờ được phép chốt nhãn rác nguy hại**. Model rẻ có quyền nói *"chắc chắn là chai nhựa"*, nhưng không bao giờ có quyền tự chốt *"chắc chắn không phải là pin"*.

---

# 5. Agent LangGraph, 3 Điểm HITL & Guardrails

## 5.1. Cấu trúc State Graph
Hệ thống sử dụng **LangGraph** để xây dựng workflow phân loại có trạng thái (Stateful Multi-Agent Workflow):


![Sơ đồ luồng 5](diagrams/GreenBinAI_Product_Report_diagram_5.png)


State của Agent được lưu giữ qua cấu trúc `GreenBinState`:
```python
class GreenBinState(TypedDict, total=False):
    # Đầu vào
    session: str
    image_bytes: bytes
    image_phash: str
    text_query: str
    building_id: str
    user_id: str
    # Kết quả từng node
    outcome: ClassifyOutcome
    advice: AdviceResult
    schedule_hint: dict
    # Vận hành & Metrics
    nodes: list[NodeMetric]
    error: str
```

## 5.2. Ba Điểm Can Thiệp Con Người (HITL Checkpoints)


![Sơ đồ luồng 6](diagrams/GreenBinAI_Product_Report_diagram_6.png)


## 5.3. Cửa An Toàn Cuối (`_finalize()`)
Trước khi trả kết quả cho client, dữ liệu bắt buộc đi qua hàm `_finalize()`:
1. **Chặn cứng lần cuối:** Kiểm tra xem kết quả có chứa vật sắc nhọn, y tế, hóa chất hay không.
2. **Từ chối hợp lệ (`refused=True`):** Từ chối không phải là lỗi hệ thống mà là kết quả an toàn. Hệ thống vẫn lưu bản ghi, đẩy vào hàng đợi HITL #2 và ghi nhận chỉ số.

---

# 6. Bảo Mật & Quyền Riêng Tư Ảnh (Privacy-Preserving AI)

Do ảnh chụp rác tại hộ gia đình có thể vô tình chứa khuôn mặt, biển số xe, hóa đơn có địa chỉ cá nhân hoặc vị trí GPS nhạy cảm, GreenBin AI áp dụng quy trình bảo vệ quyền riêng tư 5 bước nghiêm ngặt (**ADR-0004 & Section 15**):


![Sơ đồ luồng 7](diagrams/GreenBinAI_Product_Report_diagram_7.png)


> [!CAUTION]
> **Quy tắc An toàn Dữ liệu:** Ảnh gốc **không bao giờ rời khỏi máy chủ**. Mọi request gửi ra nhà cung cấp Vision AI bên ngoài đều sử dụng ảnh đã tước EXIF, mờ mặt và nén 512px. Service Worker trên PWA không bao giờ cache ảnh cư dân.

---

# 7. Thiết Bị IoT Phần Cứng — 3 Khối Module & 4 Giải Pháp

## 7.1. Kiến trúc 3 Khối Module Phần cứng
Dự án thiết kế mô hình thiết bị thu gom thông minh gồm 3 khối module nối tiếp:


![Sơ đồ luồng 8](diagrams/GreenBinAI_Product_Report_diagram_8.png)


## 7.2. So sánh 4 Giải pháp Phần cứng Đề xuất

| Tiêu chí | 🅰️ Solution A (Sensor-Only) | 🅱️ Solution B (Edge AI Basic) | 🅲 Solution C (Sensor Fusion + DL) ⭐ | 🅳 Solution D (Gamified Gravity) |
|----------|-----------------------------|------------------------------|--------------------------------------|-----------------------------------|
| **Chi phí ước tính** | ~400.000 VNĐ | ~500.000 VNĐ | **~3.300.000 VNĐ** | ~2.300.000 VNĐ |
| **Thiết bị chính** | Arduino Uno + Cảm biến | ESP32-CAM + Arduino Nano | **Raspberry Pi 4 + Pi Cam + Cảm biến** | ESP32-CAM + Khung đứng Plinko |
| **Thuật toán** | Cảm biến ngưỡng cứng | Edge Impulse TFLite | **YOLOv8 + Sensor Fusion + Cloud** | TFLite + App Tích điểm |
| **Số ngăn phân loại** | 2 – 3 ngăn | 3 – 4 ngăn | **5 ngăn (Nhựa, Giấy, Kim loại, Hữu cơ, Khác)** | 5 ngăn |
| **Độ chính xác** | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Kết nối IoT** | Không | Tùy chọn | **Wi-Fi / MQTT Cloud Dashboard** | Bluetooth / App Mobile |

---

# 8. Luồng Nghiệp Vụ RAG Hybrid & Thuật Toán Gộp Tuyến

## 8.1. RAG Hybrid Tra cứu Quy định Tòa nhà (`advise`)
Để trả lời các câu hỏi về quy định xử lý rác của từng tòa nhà, hệ thống kết hợp thuật toán **BM25 (thuần Python)** và **Vector Embedding (Cosine Similarity)**:


![Sơ đồ luồng 9](diagrams/GreenBinAI_Product_Report_diagram_9.png)


### Kế quả đo lường thuật toán RAG (trên 18 bộ câu hỏi kiểm thử):

| Chỉ số đánh giá | BM25 Thuần | RAG Hybrid (BM25 + Embedding) |
|-----------------|------------|-------------------------------|
| **Hit@1** | 0.667 | **0.722** (+8.2%) |
| **Hit@5** | 0.944 | **1.000** (100% tìm thấy) |
| **MRR (Mean Reciprocal Rank)** | 0.792 | **0.838** |

## 8.2. Thuật toán Gộp tuyến Thu gom (`route_planner.py`)
Agent thu gom gom nhóm các yêu cầu thu gom đồ cồng kềnh theo thuật toán gom cụm khoảng cách:
- **Cụm neo:** Neo vào tòa nhà của yêu cầu đầu tiên.
- **Bán kính gom:** Trong bán kính cụm **0.8 km** và cùng khung giờ.
- **Tải trọng tối đa:** Mặc định **200 kg** / chuyến.
- **Minh bạch quyết định:** Mỗi tuyến gộp đều tạo mảng `criteria[]` giải thích rõ lý do gộp cho Manager đọc.

---

# 9. Giám Sát IoT Thùng Rác Thông Minh & Đo Đạc Hệ Thống

## 9.1. Ingest Dữ liệu Cảm biến Thùng rác (`/api/v1/bins/{code}/readings`)
Hệ thống tiếp nhận dữ liệu mức đầy (`fill_percent`) và pin (`battery_percent`) từ các thùng rác thông minh qua cơ chế xác thực **HMAC-SHA256 (`X-Device-Key`)**.

### Thứ tự ưu tiên 4 trạng thái thùng rác (Bắt buộc):
```text
mat_ket_noi  >  het_pin  >  can_gom  >  binh_thuong
```
> [!IMPORTANT]
> **Trạng thái Mất kết nối phải thắng:** Một thùng rác offline 3 ngày vẫn hiển thị 85% ở lần báo cuối. Nếu xét `can_gom` trước, xe thu gom sẽ chạy tới một thùng mà không ai biết thực sự đã tràn hay chưa.

## 9.2. Hệ thống Đo đạc Metrics (Observability)
Mỗi lượt chạy qua các node AI đều ghi lại bản ghi `NodeMetric`:
- `duration`: Thời gian xử lý từng node (ms).
- `tokens`: Số lượng token input/output.
- `cost`: Chi phí USD tính toán dựa trên bảng giá thực tế.
- `price_known`: Đánh dấu `False` nếu provider không công bố giá công khai (hiện *"chưa có giá"* thay vì tự bịa ` $0 `).

---

# 10. Quy Trình Tiếp Nhận Rác Tái Chế & Chứng Từ Pháp Lý

Quy trình 6 bước tiếp nhận rác tái chế quy mô công nghiệp tại nhà máy/đơn vị thu gom:


![Sơ đồ luồng 10](diagrams/GreenBinAI_Product_Report_diagram_10.png)


### Bảng tổng hợp chứng từ pháp lý từng bước:

| Bước | Hoạt động | Chứng từ / Tài liệu bắt buộc | Bên lập / Lưu trữ |
|------|-----------|------------------------------|-------------------|
| **1. Thu mua** | Ký kết hợp đồng & chứng minh năng lực | Hợp đồng thu gom phế liệu · Giấy phép môi trường (GP-MT) · Đăng ký kinh doanh | Cả 2 bên |
| **2. Tiếp nhận cổng** | Kiểm tra xe & phân loại chất thải | **Chứng từ CTNH Mẫu 04** (4 liên với rác nguy hại) · Biên bản bàn giao chất thải thông thường | Bảo vệ cổng & Xe chở |
| **3. Cân & KCS** | Cân xe Gross/Tare & kiểm tra tạp chất | **Phiếu cân điện tử** (Gross, Tare, Net) · Biên bản kiểm tra KCS · Biên bản trừ hao tạp chất | NV Trạm cân & KCS |
| **4. Phân loại & Kho** | Phân lô lưu kho theo mã nhựa/kim loại | Phiếu nhập kho (PNK) · Biên bản nghiệm thu bàn giao · Sổ kho | Thủ kho |
| **5. Tái chế** | Băm nghiền, đùn hạt, rửa sạch | Nhật ký vận hành máy · Phiếu QC sản phẩm đầu ra · Sổ theo dõi khí/nước thải | Bộ phận Sản xuất |
| **6. Báo cáo & Bán** | Bán thương phẩm & Báo cáo cơ quan | Hóa đơn GTGT điện tử · Phiếu xuất kho · **Báo cáo định kỳ Cổng EPR Quốc gia** | Kế toán & Cán bộ MT |
| *Mua ve chai* | Thu mua từ cá nhân không có hóa đơn | **Bảng kê thu mua Mẫu 01/TNDN** (Ghi rõ CCCD, địa chỉ, số tiền) | Kế toán |

---

# 11. Mô Hình Dữ Liệu (23 Bảng CSDL) & Bề Mặt API (51 Routes)

## 11.1. Sơ đồ Thực thể CSDL (23 Bảng)

Hệ thống quản lý 23 bảng dữ liệu chia thành 9 nhóm chức năng chính:

```text
[Danh tính]         users, buildings, units
[Danh mục]          waste_categories (9 nhóm, min_confidence riêng)
[Ảnh & Privacy]     media (phash, exif_stripped, faces_blurred)
[Phân loại AI]      classifications, classification_feedback
[Tri thức RAG]      knowledge_docs, knowledge_chunks (embedding list)
[Thu gom]           pickup_requests, pickup_events, pickup_routes, route_stops
[Vận hành System]   agent_runs, run_node_metrics, audit_log, alerts, notifications, collection_schedules
[Đánh giá AI]       eval_runs, failure_cases
[IoT Thùng rác]     bins, bin_readings
```

## 11.2. Bề mặt API (51 HTTP Endpoints)
Tất cả 51 route đều chuẩn hóa dưới tiền tố `/api/v1` với cấu trúc lỗi thống nhất:
```json
{
  "error": {
    "code": "VISION-500",
    "message_vi": "Không thể kết nối tới nhà cung cấp Vision AI",
    "detail": {}
  }
}
```

Ma trận phân quyền 15 quyền chính được kiểm soát chặt chẽ qua middleware JWT Bearer. Mọi hành động xem ảnh gốc của Manager đều tự động kích hoạt ghi `AuditLog`.

---

# 12. Hướng Dẫn Build Demo Bìa Các-Tông

Để phục vụ họp nhóm chốt giải pháp phần cứng, mô hình mô phỏng bìa các-tông không cần hoạt động điện thật nhưng phải thể hiện rõ luồng vận hành 3 khối:

```text
Kích thước tổng thể: 50 cm (Dài) × 30 cm (Rộng) × 25 cm (Cao)
```


![Sơ đồ luồng 11](diagrams/GreenBinAI_Product_Report_diagram_11.png)


- **Khối 1 (Chờ):** Máng nghiêng bìa các-tông góc 30° có thành ngăn chai lăn ngược.
- **Khối 2 (Quét):** Hộp kín có cửa sổ nhựa trong quan sát, mô hình webcam gỗ/nhựa ghi chữ "AI CAMERA".
- **Khối 3 (Đựng):** 5 cốc giấy dán 5 nhãn màu (🟡 Nhựa, 🔵 Giấy, ⚪ Kim loại, 🟢 Hữu cơ, 🔴 Khác). Phía trên có cửa sập buộc dây chỉ: **kéo dây = mở cửa sập (mô phỏng servo)**.

---



---

# 14. Phân Tích Thị Trường & Nền Tảng Cạnh Tranh

## 14.1. Tổng quan Thị trường Giải pháp Rác thải
Hiện nay trên thế giới và tại Việt Nam có hơn 20 nền tảng và doanh nghiệp công nghệ đang tham gia giải quyết bài toán phân loại rác, thùng rác thông minh và quản lý môi trường. Các giải pháp được chia thành 4 nhóm chính:


![Sơ đồ luồng 1](diagrams/GreenBinAI_Product_Report_diagram_1.png)


### Chi tiết các nhóm giải pháp:

1. **Thùng rác AI tại điểm xả (Point-of-Disposal Smart Bins):**
   - **Bin-e (Ba Lan):** Thùng rác AI cho văn phòng, tự phân loại & nén rác, gửi báo cáo mức đầy. Chi phí cao ($2.000–$5.000/thùng).
   - **TrashBot (CleanRobotics - Mỹ):** Thùng rác AI dùng Vision & cảm biến phân loại rác sân bay, bệnh viện với độ chính xác >90%.
   - **Oscar Sort (Intuitive AI - Canada):** Trợ lý AI có màn hình hiển thị hướng dẫn người dùng bỏ rác đúng ngăn.
   - **DaNa Green (Việt Nam):** Dự án nghiên cứu của sinh viên ĐH Đà Nẵng thử nghiệm thùng rác AI phân loại tại chỗ.
   - **Bigbelly (Mỹ):** Thùng nén rác năng lượng mặt trời tích hợp IoT báo đầy *(không phân loại AI)*.

2. **AI & Robot Phân loại Công nghiệp (MRFs):**
   - **AMP Robotics (Mỹ) & Recycleye (Anh):** Tay robot gắp rác AI tốc độ cao trên băng tải nhà máy tái chế.
   - **Greyparrot (Anh):** Camera AI giám sát thành phần rác trên băng tải nhà máy real-time phục vụ kiểm toán tái chế.

3. **Phần mềm SaaS & IoT Logistics Thu gom:**
   - **Sensoneo (Slovakia):** Cảm biến IoT đo mức đầy thùng + phần mềm tối ưu tuyến đường động (Dynamic Route Optimization).
   - **Rubicon (Mỹ):** Marketplace kết nối phát sinh rác ↔ nhà xe thu gom, báo cáo ESG doanh nghiệp.
   - **AMCS Group (Ailen):** Hệ thống ERP toàn diện quản lý trạm cân, phế liệu và đội xe.

4. **Nền tảng Số hóa & EPR tại Việt Nam:**
   - **GRAC (Grac.vn):** SaaS số hóa thu gom, thu tiền rác online và module Digital PRO giúp doanh nghiệp FMCG làm báo cáo **EPR**.
   - **mGreen:** App di động *"Đổi rác lấy quà"* (Loyalty Program) tạo động lực phân loại rác cho cư dân.

---

## 14.2. Ma trận So Sánh Đối Thủ & Vị Thế GreenBin AI

| Nền tảng / Doanh nghiệp | Xuất xứ | Phần cứng AI | App Cư dân | Web Quản lý | Tối ưu tuyến | Báo cáo EPR (Luật VN) | Điểm hạn chế chính so với GreenBin AI |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Bin-e / TrashBot** | Ba Lan / Mỹ | ✅ | ❌ | ✅ | ❌ | ❌ | Giá quá đắt ($2.000–$5.000/thùng), thiết bị đơn lẻ, khó phủ rộng khu đô thị. |
| **Sensoneo / Rubicon** | Châu Âu / Mỹ | ❌ | ❌ | ✅ | ✅ | ✅ (ESG) | Rất mạnh về logistics & cảm biến IoT báo đầy, nhưng **không có AI phân loại tại nguồn**. |
| **GRAC (Grac.vn)** | Việt Nam | ❌ | ✅ | ✅ | ✅ | ✅ (NĐ 08/2022) | Rất mạnh về quản lý hành chính & báo cáo EPR, nhưng **thiếu AI Agent & phần cứng IoT**. |
| **mGreen** | Việt Nam | ❌ | ✅ (Loyalty) | ❌ | ❌ | ❌ | Tập trung vào tích điểm đổi quà, không có AI phân loại & phần mềm ERP cho đơn vị thu gom. |
| 🌿 **GreenBin AI (VHR-17)** | **Việt Nam** | **✅ (3 Khối)** | **✅ (PWA/APK)** | **✅ (Vercel)** | **✅ (VRP 0.8km)** | **✅ (NĐ 110/2026)** | **Hệ sinh thái khép kín:** AI Agent 4 tầng (LangGraph) + Phần cứng 3 khối + Web/App đồng bộ + Số hóa chứng từ Mẫu 01/04 BVMT Việt Nam. |

---

## 14.3. Ưu Thế Cạnh Tranh Đột Phá Của GreenBin AI
1. **Kiến trúc AI 4 Tầng (4-Tier Routing) Tối ưu Chi phí:** Sử dụng pHash cache ($0) và CLIP ONNX local ($0) giải quyết bài toán chi phí API — điểm yếu chí mạng của các thùng rác AI truyền thống.
2. **Cơ chế Can thiệp Con người (3 HITL Checkpoints):** Đảm bảo an toàn pháp lý & chính xác (bản ghi rác nguy hại luôn bắt buộc duyệt thủ công).
3. **Bảo mật Quyền riêng tư Ảnh (Privacy-Preserving AI):** Tước EXIF, mờ mặt bằng OpenCV trước khi ra khỏi máy chủ — phù hợp môi trường chung cư hộ gia đình.
4. **Bản địa hóa Chứng từ BVMT Việt Nam:** Tích hợp số hóa Bảng kê thu mua ve chai (Mẫu 01/TNDN) và Chứng từ CTNH (Mẫu 04 - 4 liên).


# 13. Giới Hạn Kỹ Thuật, Bài Học Thực Nghiệm & Lộ Trình Triển Khai

## 13.1. Cảnh báo Kỹ thuật & Bài học Thực nghiệm (ADR-0011)

> [!WARNING]
> **Không sử dụng độ chính xác TrashNet để quảng cáo sản phẩm!**
> Kết quả thử nghiệm thực tế cho thấy:
> - Model đạt **94.18%** độ chính xác trên dataset công khai TrashNet.
> - Nhưng giảm xuống chỉ còn **41.04%** khi thử nghiệm trên dataset **RealWaste** (ảnh rác thực tế tại bãi rác Việt Nam).
> 
> **Kết luận:** Bộ ảnh rác tự chụp thực tế tại địa phương là tài sản quan trọng nhất, không phải các dataset lý thuyết.

## 13.2. Lộ trình Triển khai Dự án (Gantt Chart)


![Sơ đồ luồng 12](diagrams/GreenBinAI_Product_Report_diagram_12.png)


---
*Báo cáo được tổng hợp và đồng bộ tự động từ tài liệu Kiến trúc Hệ thống VHR-17 & Hồ sơ Sản phẩm GreenBin AI.*
