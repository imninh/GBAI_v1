# Sơ đồ kiến trúc — GreenBin AI (VHR-17)

> 📖 **Tài liệu kiến trúc đầy đủ nằm ở [`../ARCHITECTURE.md`](../ARCHITECTURE.md)** —
> 22 mục, 14 sơ đồ, kèm số đo thật và danh sách giới hạn đã biết.
> File này là bản một trang để xem nhanh.

---

## 1. Toàn cảnh hệ thống

```mermaid
graph TB
    R["Cư dân"] --> FE
    C["Đội vệ sinh"] --> FE
    M["Ban quản lý"] --> FE
    D["Thùng thu gom<br/>thiết bị / mô phỏng"] -->|X-Device-Key| API

    FE["Frontend Next.js 15<br/>export tĩnh · PWA · APK Capacitor"] -->|"REST + JWT"| API

    API["FastAPI · 51 route<br/>khuôn lỗi thống nhất"] --> AG["Agent LangGraph<br/>classify → advise → schedule"]
    API --> IMG["Tiền xử lý ảnh<br/>EXIF · mờ mặt · 512px · pHash"]

    AG --> CLS["Định tuyến 4 tầng<br/>T0 cache · T0.5 local · T1 · T2"]
    AG --> RAG["RAG hybrid<br/>BM25 + embedding, lọc theo toà"]
    AG --> PK["Thu gom + gộp tuyến"]

    CLS --> LOCAL["CLIP ONNX int8<br/>local · $0"]
    CLS --> EXT["Gemini · NVIDIA · OpenAI<br/>provider RIÊNG từng tầng"]

    RAG --> DB
    PK --> DB
    CLS --> DB[("PostgreSQL / SQLite<br/>23 bảng")]

    style API fill:#0f766e,color:#fff
    style LOCAL fill:#dcfce7
```

## 2. Luồng agent

```mermaid
stateDiagram-v2
    [*] --> classify_waste
    classify_waste --> skip_advise: đã từ chối trả lời
    classify_waste --> advise: trả lời được
    advise --> schedule_pickup: nhóm bulky
    advise --> skip_schedule: còn lại
    skip_advise --> [*]
    schedule_pickup --> [*]
    skip_schedule --> [*]
```

Hai nhánh `skip_*` **vẫn ghi bản ghi node** với `status="skipped"` kèm lý do —
màn Agent Run nhìn thấy cả đường đã đi lẫn đường không đi.

## 3. Định tuyến model 4 tầng

```mermaid
flowchart LR
    A([ảnh đã tiền xử lý]) --> T0{"T0<br/>cache pHash"}
    T0 -->|trúng| Z(["$0"])
    T0 -->|trượt| T05{"T0.5<br/>CLIP local"}
    T05 -->|"đủ chắc và không nguy hại"| Z
    T05 -->|không| T1["T1 — vision rẻ<br/>NVIDIA"]
    T1 --> E{"conf thấp HOẶC<br/>nghi nguy hại?"}
    E -->|có| T2["T2 — vision mạnh<br/>Gemini"]
    E -->|không| F["cửa an toàn cuối"]
    T2 --> F
    F --> OK(["trả lời + trích nguồn"])
    F --> NO(["TỪ CHỐI + chuyển người"])

    style Z fill:#dcfce7
    style NO fill:#fee2e2
```

## 4. Ba điểm HITL

| # | Điểm | Ai duyệt | Kích hoạt khi |
|---|---|---|---|
| 1 | Yêu cầu thu gom | Ban quản lý | trên 30 kg · trên 3 món · **có món nguy hại** |
| 2 | Nhãn phân loại | Đội vệ sinh + BQL | confidence thấp · nghi nguy hại |
| 3 | Tuyến agent đề xuất | Đội trưởng / BQL | **luôn luôn** — agent không tự đổi lịch làm việc của người |

## 5. Thành phần

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| Frontend | Next.js 15 · Tailwind v4 · `output: "export"` | 3 vai trò · PWA · APK Capacitor |
| Backend | FastAPI + SQLAlchemy 2.x | 51 route · khuôn lỗi `{error:{code,message_vi}}` |
| Agent | LangGraph `StateGraph` | `classify → advise → schedule` có trace |
| Model | Gemini · NVIDIA · OpenAI-compatible · **CLIP ONNX local** | provider khai **riêng từng tầng** |
| CSDL | SQLite khi dev → PostgreSQL khi deploy | 23 bảng |
| Vector | JSON list trong SQLite → pgvector | truy hồi **hybrid** BM25 + embedding |
| Ảnh | Pillow + OpenCV + imagehash | tước EXIF · làm mờ mặt · nén · pHash |
| Triển khai | Render (Docker + Postgres) + Vercel | 512 MB RAM là ràng buộc thiết kế |
