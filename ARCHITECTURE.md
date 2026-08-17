# Kiến trúc hệ thống — GreenBin AI (VHR-17)

> **Agent Phân loại Rác & Điều phối Thu gom Tái chế** — mã đề VHR-17, nhóm T-075,
> AI20K Build Phase Cohort 3.
>
> Tài liệu này là **deliverable #3 (Architecture diagram)**. Nó mô tả hệ thống
> *như đang có trong repo này*, không phải hệ thống mong muốn. Chỗ nào chưa làm
> thì ghi thẳng là chưa làm — xem mục 21.
>
> **Cập nhật:** 16/08/2026 · 

---

## Mục lục

| # | Mục | # | Mục |
|---|---|---|---|
| 1 | [Số liệu chốt](#1-số-liệu-chốt) | 12 | [Luồng D — thùng thu gom](#12-luồng-d--thùng-thu-gom-thông-minh) |
| 2 | [Bài toán và 3 vai trò](#2-bài-toán-và-ba-vai-trò) | 13 | [Mô hình dữ liệu](#13-mô-hình-dữ-liệu-23-bảng) |
| 3 | [Nguyên tắc kiến trúc](#3-sáu-nguyên-tắc-kiến-trúc) | 14 | [Bề mặt API và phân quyền](#14-bề-mặt-api-và-phân-quyền) |
| 4 | [Sơ đồ ngữ cảnh](#4-sơ-đồ-ngữ-cảnh-c4--mức-1) | 15 | [Quyền riêng tư ảnh](#15-quyền-riêng-tư-ảnh) |
| 5 | [Sơ đồ container](#5-sơ-đồ-container-c4--mức-2) | 16 | [Quan sát và đo đạc](#16-quan-sát-và-đo-đạc) |
| 6 | [Thành phần backend](#6-thành-phần-backend-c4--mức-3) | 17 | [Xử lý lỗi và suy giảm](#17-xử-lý-lỗi-và-suy-giảm-có-kiểm-soát) |
| 7 | [Luồng A — phân loại](#7-luồng-a--phân-loại-rác-đường-găng) | 18 | [Kiến trúc frontend](#18-kiến-trúc-frontend) |
| 8 | [Định tuyến 4 tầng](#8-định-tuyến-model-bốn-tầng) | 19 | [Triển khai và CI/CD](#19-triển-khai-và-cicd) |
| 9 | [Agent LangGraph](#9-agent-langgraph) | 20 | [Ánh xạ tiêu chí chấm và PLO](#20-ánh-xạ-tiêu-chí-chấm-và-plo) |
| 10 | [Guardrails và HITL](#10-guardrails-và-ba-điểm-hitl) | 21 | [Chỉ mục ADR](#22-chỉ-mục-adr) |
| 11 | [Luồng B/C — RAG, thu gom](#11-luồng-b-và-c--tra-quy-định-và-điều-phối-tuyến) | 

---

## 1. Số liệu chốt

Đo trực tiếp, không ước lượng. **Cập nhật 16/08/2026:**

```
pytest -q                              → 791 passed
ruff check src/ tests/ eval/ scripts/  → All checks passed!
số route khai báo                      → 69 (gồm cả WebSocket theo dõi xe)
frontend: npm run lint                 → 0 lỗi
frontend: npm --prefix frontend run typecheck → sạch
```

| Chỉ số | Giá trị |
|---|---|
| Mã Python | **76 file** trong `src/` |
| Mã test | **93 file** trong `tests/` — **574 hàm test → 791 ca** (có parametrize) |
| Bảng CSDL | **26** |
| Endpoint HTTP | **69 route** khai báo (nghiệp vụ dưới `/api/v1` + `/health` + WebSocket) |
| Vai trò người dùng | 3 · **19 quyền** trong ma trận |
| Điểm HITL | 3 |
| Tầng định tuyến model | 4 (T0 · T0.5 · T1 · T2) |
| Nhà cung cấp model đấu nối | 5 + 1 local (Gemini · OpenAI · OpenRouter · NVIDIA · Groq · CLIP ONNX) |

Ba quyền thêm sau bản 06/08: `view_diem_gui` (cư dân xem điểm gửi),
`edit_own_profile` (tự sửa hồ sơ), `assign_bin` (quản lý giao thùng cho nhân
viên). Ma trận quyền ở `src/services/auth.py` là **bản chép lại** của bảng trong
`docs/FRONTEND_SPEC.md` mục 1 — sửa một bên thì phải sửa cả hai, và **ba quyền
này chưa được chép sang spec**, đang nợ.

---

## 2. Bài toán và ba vai trò

BQL toà nhà **có nghĩa vụ pháp lý** phân loại rác tại nguồn (Luật BVMT 2020,
NĐ 45/2022). Thực tế việc đó dồn hết lên đội vệ sinh: họ bới lại toàn bộ rác
bằng tay, kể cả pin và rác nguy hại cư dân vứt lẫn. Đăng ký và điều phối thu gom
đồ cồng kềnh vẫn làm thủ công qua tin nhắn.

GreenBin AI là **lớp vận hành** đặt lên trên việc đó. Nguyên tắc xuyên suốt
([ADR-0002](docs/decisions/0002-chuyen-trong-tam-sang-van-hanh.md)):

> **Mỗi kết quả AI phải sinh ra một hành động hoặc một bản ghi trong hệ thống.**
> Không được dừng ở một màn hình trả lời.

| Vai trò | Người thật là ai | Làm gì trong hệ thống |
|---|---|---|
| `resident` | Cư dân | Chụp/mô tả rác · đăng ký thu gom đồ cồng kềnh · xem lịch · xem ảnh mình đã bị xoá gì |
| `cleaner` | Đội vệ sinh tại phòng rác tầng | Phân loại tại chỗ tập kết · **xác nhận nhãn** (HITL #2) · chạy tuyến · đánh dấu điểm dừng xong · xem bản đồ thùng |
| `manager` | Ban quản lý / đơn vị thu gom | **Duyệt yêu cầu vượt ngưỡng** (HITL #1) · **duyệt tuyến agent đề xuất** (HITL #3) · sửa danh mục · xem Vận hành, Chất lượng AI, Agent Run · xem ảnh gốc (có ghi log) |

**Phạm vi rác đi qua AI** ([ADR-0003](docs/decisions/0003-phan-tang-rac-va-trong-tam-doi-ve-sinh.md)):
chỉ **luồng B** — tái chế, cồng kềnh, nguy hại. Luồng A (rác ướt đóng túi nilon
đục) **nằm ngoài phạm vi có chủ đích**: vision không nhìn xuyên túi, và nhãn của
nó không ai tranh chấp.

---

## 3. Sáu nguyên tắc kiến trúc

Mỗi nguyên tắc dưới đây đều đọc được thành code cụ thể, không phải khẩu hiệu.

| # | Nguyên tắc | Thể hiện trong code |
|---|---|---|
| 1 | **Không chắc thì không trả lời** | `_refuse()` xoá luôn nhãn và hướng dẫn, chỉ giữ lại "phỏng đoán" có dán nhãn — `classifier.py:127` |
| 2 | **Rẻ trước, đắt sau** | 4 tầng: cache pHash → CLIP local → T1 → T2. Hai tầng đầu $0 |
| 3 | **Mất một nguồn chỉ mất một tầng** | Provider khai riêng từng tầng `VISION_PROVIDER_T1/_T2/_TEXT`; T1 hỏng thì T2 cứu ([ADR-0006](docs/decisions/0006-provider-theo-tung-tang.md)) |
| 4 | **Con số phải đo, không được đoán** | `price_known=False` khi nhà cung cấp không công bố giá → UI hiện "chưa có giá" thay vì "$0" |
| 5 | **Người quyết định việc rủi ro** | 3 điểm HITL, lý do từ chối chọn từ danh sách cố định để chảy ngược vào tập cải tiến |
| 6 | **Đường không đi cũng phải nhìn thấy** | Nhánh `skip_*` của graph vẫn ghi `RunNodeMetric` với `status="skipped"` kèm lý do |

---

## 4. Sơ đồ ngữ cảnh (C4 — mức 1)

```mermaid
graph TB
    R["Cư dân · resident"]
    C["Đội vệ sinh · cleaner"]
    M["Ban quản lý · manager"]
    D["Thùng thu gom<br/>thiết bị / bộ mô phỏng"]

    S["GreenBin AI<br/>Phân loại rác · tra quy định<br/>điều phối thu gom · giám sát thùng"]

    G["Google Gemini<br/>vision + embedding"]
    N["NVIDIA NIM<br/>llama vision"]
    O["OpenAI / OpenRouter<br/>tuỳ chọn"]
    P["Phoenix AI-log<br/>ai-logs.note.transformerlabs.ai"]

    R -->|"ảnh · mô tả · đăng ký thu gom"| S
    C -->|"xác nhận nhãn · chạy tuyến"| S
    M -->|"duyệt yêu cầu · duyệt tuyến · xem vận hành"| S
    D -->|"POST readings + X-Device-Key"| S

    S -->|"HTTPS · ảnh đã tước EXIF + làm mờ mặt"| G
    S -->|"HTTPS"| N
    S -.->|"khi đổi cấu hình"| O
    S -->|"nhật ký phiên code AI"| P

    style S fill:#0f766e,color:#fff
    style D fill:#475569,color:#fff
```

**Điểm cần nhớ:** ảnh **không bao giờ** rời máy chủ ở dạng gốc. Mọi mũi tên đi ra
nhà cung cấp model đều mang ảnh đã tước EXIF, làm mờ mặt, nén 512px — xem mục 15.

---

## 5. Sơ đồ container (C4 — mức 2)

```mermaid
graph TB
    subgraph client["Thiết bị người dùng"]
        PWA["PWA / Web<br/>Next.js 15 · export tĩnh"]
        APK["App Android<br/>Capacitor 7"]
        SIM["device_simulator.py<br/>thay phần cứng chưa có"]
    end

    subgraph edge["Vercel — CDN tĩnh"]
        OUT["frontend/out/<br/>HTML + JS + service worker"]
    end

    subgraph server["Render — Docker · Singapore · free 512 MB"]
        API["FastAPI + Uvicorn<br/>src/main.py"]
        AG["Agent LangGraph<br/>src/agents/"]
        SVC["Lớp nghiệp vụ<br/>src/services/"]
        CLIP["Model local ONNX int8<br/>CLIP · 88 MB · 185 MB RAM"]
        DISK["Đĩa tạm<br/>data/media/"]
    end

    subgraph data["Dữ liệu"]
        PG[("PostgreSQL<br/>Render free")]
        SQ[("SQLite<br/>khi dev")]
    end

    subgraph ext["Bên ngoài"]
        LLM["Nhà cung cấp vision<br/>Gemini · NVIDIA · OpenAI"]
    end

    PWA --> OUT
    APK --> OUT
    OUT -->|"REST · JWT Bearer"| API
    SIM -->|"X-Device-Key"| API

    API --> AG --> SVC
    SVC --> CLIP
    SVC --> DISK
    SVC -->|"SQLAlchemy 2.x"| PG
    SVC -.->|"đổi DATABASE_URL"| SQ
    SVC -->|"HTTPS"| LLM

    style server fill:#ecfdf5
    style edge fill:#eff6ff
```

**Vì sao tách Vercel / Render:** `output: "export"` cho ra thư mục `out/` tĩnh
thuần. Cùng một thư mục đó vừa để Vercel phục vụ, vừa để Capacitor đóng gói APK,
vừa để service worker cache — một bản build dùng cho ba kênh phân phối
([ADR-0005](docs/decisions/0005-pwa-va-capacitor-thay-vi-viet-lai-native.md)).
Đây là lý do màn `/dieu-phoi` **không được** đổi sang TanStack Start dù bản thiết
kế Lovable viết bằng nó.

---

## 6. Thành phần backend (C4 — mức 3)

```mermaid
graph LR
    subgraph api["src/api/ — lớp HTTP"]
        A2["classify"]
        A3["media"]
        A5["pickups"]
        A6["routes"]
        A7["ops"]
        A8["bins"]
        DEP["deps.py<br/>DbSession · CurrentUser · require()"]
        ERR["errors.py<br/>khuôn lỗi thống nhất"]
    end

    subgraph agents["src/agents/ — điều phối"]
        GR["graph.py · StateGraph"]
        ND["nodes/classify_node.py"]
    end

    subgraph svc["src/services/ — nghiệp vụ"]
        IM["image.py<br/>EXIF · mờ mặt · 512px · pHash"]
        CL["classifier.py<br/>định tuyến 4 tầng"]
        SF["safety.py<br/>chặn cứng · ngưỡng · từ chối"]
        RG["rag.py<br/>BM25 + embedding hybrid"]
        PK["pickup.py + pickup_lifecycle.py"]
        RP["route_planner.py · gộp tuyến"]
        BN["bins.py · 4 trạng thái thùng"]
        MT["metrics.py<br/>chi phí · độ trễ · lỗi"]
        RN["runs.py · ghi AgentRun"]
        VS["vision/<br/>gemini · openai_compat · local_clip"]
    end

    subgraph db["src/db/"]
        MD["models.py — 26 bảng"]
        SS["session.py"]
    end

    A2 --> GR --> ND
    ND --> CL --> VS
    ND --> RG
    ND --> PK
    CL --> SF
    A5 --> PK
    A6 --> RP
    A8 --> BN
    A7 --> MT
    A2 --> IM
    A2 --> RN
    api --> DEP
    api --> ERR
    svc --> MD
    MD --> SS
```

**Quy tắc phân tầng được giữ nghiêm:** router **không** chứa logic nghiệp vụ, chỉ
nối HTTP ↔ service. Ngược lại `pickup_lifecycle.py` là module **thuần** — không
import gì từ `src.db`, test được mà không cần session.

---

## 7. Luồng A — phân loại rác (đường găng)

Đây là luồng quan trọng nhất, cũng là luồng demo chính.

```mermaid
sequenceDiagram
    autonumber
    actor U as Cư dân / đội vệ sinh
    participant FE as Frontend
    participant API as POST /api/v1/classify
    participant IMG as image.py
    participant AG as LangGraph agent
    participant CLS as classifier.py
    participant V as Nhà cung cấp vision
    participant RAG as rag.py
    participant DB as CSDL

    U->>FE: chụp ảnh / gõ mô tả
    FE->>API: multipart + JWT Bearer
    API->>API: kiểm rỗng · tối đa 12 MB
    API->>IMG: preprocess_image(raw)
    IMG-->>API: tước EXIF · mờ mặt · nén 512px · pHash
    API->>DB: INSERT media + flush
    API->>AG: agent.invoke(state)

    AG->>CLS: classify_waste()
    CLS->>CLS: chặn cứng theo câu chữ
    CLS->>DB: T0 — dò pHash trong 300 bản ghi gần nhất
    alt trúng cache
        CLS-->>AG: tier=t0_cache · $0
    else trượt
        CLS->>CLS: T0.5 — CLIP ONNX trên CPU
        alt rất chắc và không nguy hại
            CLS-->>AG: tier=t0_5_local · $0
        else
            CLS->>V: T1 — provider riêng của T1
            V-->>CLS: JSON nhãn + items + confidence
            opt conf thấp / nghi nguy hại / nhiều vật
                CLS->>V: T2 — provider riêng của T2
            end
        end
    end
    CLS->>CLS: _finalize — chặn cứng · nhiều nhóm · ngưỡng
    CLS-->>AG: ClassifyOutcome, có thể refused=True

    alt trả lời được
        AG->>RAG: advise — truy hồi quy định của TOÀ ĐÓ
        RAG-->>AG: hướng dẫn + nguồn trích dẫn
        opt nhóm bulky
            AG->>AG: schedule_pickup — gợi ý khung giờ
        end
    else đã từ chối
        AG->>AG: skip_advise, vẫn ghi node
    end

    AG-->>API: state
    API->>DB: INSERT classification + run_node_metrics
    API-->>FE: JSON kèm nguồn, chi phí, độ trễ, tier
    FE-->>U: thẻ kết quả / màn "chưa đủ chắc"
```

**Ba chi tiết dễ bỏ sót:**

1. **Tiền xử lý đứng trước mọi lệnh gọi model** — không có đường tắt nào bỏ qua
   `preprocess_image`. Điều này được khẳng định bằng test.
2. **`refused=True` là kết quả hợp lệ, không phải lỗi.** Nó vẫn ghi bản ghi, vẫn
   đẩy vào hàng đợi HITL #2, vẫn tính vào chỉ số.
3. `classify_waste` nhận **ảnh đã xử lý**, không bao giờ nhận ảnh gốc — ghi rõ
   trong docstring của hàm.

---

## 8. Định tuyến model bốn tầng

Đây là điểm ăn PLO 1 và là phần trả lời ràng buộc "tối ưu chi phí" của đề.

```mermaid
flowchart TD
    S([ảnh đã tiền xử lý]) --> HB{"chặn cứng theo câu chữ?<br/>vật sắc nhọn y tế · bình gas · hoá chất"}
    HB -->|trúng| REF["TỪ CHỐI + chuyển người<br/>refusal_reason=chan_cung"]
    HB -->|không| T0{"T0 — pHash<br/>khoảng cách nhỏ hơn hoặc bằng 6?"}

    T0 -->|trúng| OUT0["tier=t0_cache · $0<br/>lấy lại nhãn cũ"]
    T0 -->|trượt| T05{"T0.5 — CLIP ONNX int8<br/>đủ chắc VÀ không dính nguy hại?"}

    T05 -->|đạt| OUT05["tier=t0_5_local · $0<br/>56 ms ở máy dev"]
    T05 -->|"không đạt / chưa sẵn sàng"| T1["T1 — vision rẻ<br/>VISION_PROVIDER_T1"]

    T1 -->|lỗi| RESC{"T2 khác provider?"}
    RESC -->|có| T2R["T2 cứu — tier=t2_full<br/>escalation_reason='T1 lỗi'"]
    RESC -->|không| REFM["TỪ CHỐI · refusal=model_loi"]

    T1 -->|ok| ESC{"escalate?<br/>conf dưới ngưỡng nhóm<br/>HOẶC nghi nguy hại<br/>HOẶC nhiều vật / ảnh kém"}
    ESC -->|không| FIN
    ESC -->|có| T2["T2 — vision mạnh<br/>VISION_PROVIDER_T2"]
    T2 -->|lỗi| KEEP["giữ kết quả T1<br/>KHÔNG âm thầm nâng độ tin cậy"]
    T2 -->|ok| FIN
    KEEP --> FIN
    T2R --> FIN

    FIN["_finalize — cửa an toàn cuối"] --> OK([kết quả])

    style REF fill:#fee2e2
    style REFM fill:#fee2e2
    style OUT0 fill:#dcfce7
    style OUT05 fill:#dcfce7
```

| Tầng | Chạy ở đâu | Dùng khi | Chi phí | Độ trễ đo được |
|---|---|---|---|---|
| **T0** cache pHash | CSDL | ảnh trùng/gần trùng đã phân loại | **$0** | vài ms |
| **T0.5** CLIP ONNX int8 | CPU máy chủ | rất chắc **và** không dính nhóm nguy hại | **$0** | 56 ms dev · **2.595 ms trên Render** |
| **T1** vision rẻ | NVIDIA `llama-3.2-90b-vision` | phần lớn lưu lượng | credit | 10–28 s |
| **T2** vision mạnh | Gemini flash | conf thấp · **nghi nguy hại** · nhiều vật | quota 20 req/ngày | p95 ~40 s trên deploy |

**Ba quyết định kiến trúc nằm trong bảng này:**

- **Escalate lên T2 phải gồm cả "nghi rác nguy hại", không chỉ confidence thấp.**
  Một model tự tin sai về cục pin nguy hiểm hơn một model lưỡng lự.
- **T0.5 không bao giờ được chốt nhãn nhóm nguy hại** (`local_never_decides_hazardous=True`).
  Model rẻ có quyền nói "chắc chắn là chai nhựa", không có quyền nói "chắc chắn
  không phải pin".
- **Mỗi tầng một nhà cung cấp riêng.** Free tier Gemini chỉ 20 request/ngày, mỗi
  lần chụp tiêu 2 → dồn cả hệ thống vào một nguồn thì 10 lần chụp là đứng máy
  ([ADR-0006](docs/decisions/0006-provider-theo-tung-tang.md)).

> ⚠️ **Con số trong báo cáo phải là con số đo trên deploy.** Render free chỉ có
> ~0,1 CPU chia sẻ: CLIP chạy 56 ms ở máy dev thành 2.595 ms trên Render —
> **chậm 46 lần**. Đừng bao giờ mang số của máy dev lên slide.

---

## 9. Agent LangGraph

### 9.1 Hình dạng graph

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

Hai nhánh `skip_*` tồn tại **có chủ đích**, không phải cho đẹp sơ đồ: chúng vẫn
sinh `RunNodeMetric` với `status="skipped"` kèm lý do, nên màn Agent Run hiện
được **cả đường đã đi lẫn đường không đi** — đúng yêu cầu "trace và debug được"
của chương trình.

Hình dạng graph còn được xuất ra hằng `GRAPH_SHAPE` trong `agents/graph.py` để
frontend vẽ đúng sơ đồ đó — **một nguồn sự thật** cho cả hai phía.

### 9.2 State

```python
class GreenBinState(TypedDict, total=False):
    # đầu vào
    session, image_bytes, image_phash, text_query, building_id, user_id
    # kết quả từng node — node sau đọc kết quả node trước rồi bồi thêm
    outcome: ClassifyOutcome
    advice: AdviceResult
    schedule_hint: dict
    # vận hành
    nodes: list[NodeMetric]
    error: str
```

Đây chính là thứ làm workflow "có trạng thái" theo đúng nghĩa của chương trình:
state đi qua `classify → advise → schedule`, và toàn bộ hành trình ghi lại được
trong `nodes` để dựng lại màn Agent Run sau này.

### 9.3 Các node ghi lại

Mỗi bước — kể cả bước không gọi model — đều sinh một `NodeMetric`:

| `node` | Ghi lại gì |
|---|---|
| `safety_precheck` | có trúng luật chặn cứng không |
| `cache_lookup` | trúng/trượt · `phash_distance` · id bản ghi nguồn |
| `local_model` | confidence · ngưỡng · có chốt nhãn không · **có bị chặn vì nghi nguy hại không** |
| `classify_waste` | tier · provider · model · token vào/ra · token ảnh · chi phí |
| `classify_waste_t2` | lý do escalate · confidence mới · hoặc lỗi của T2 |
| `safety_check` | luật chặn cứng lần cuối · số luật đang áp |
| `advise` / `skip_advise` | nguồn đã truy hồi · chế độ hybrid hay thuần BM25 |
| `schedule_pickup` / `skip_schedule` | gợi ý khung giờ · hoặc lý do bỏ qua |

---

## 10. Guardrails và ba điểm HITL

### 10.1 Cửa an toàn cuối — `_finalize()`

Thứ tự **là một phần của thiết kế**, không phải ngẫu nhiên:

```mermaid
flowchart TD
    A([kết quả model]) --> B{"chặn cứng?"}
    B -->|trúng| R1["chan_cung"]
    B -->|không| C{"có nhận ra nhóm nào không?"}
    C -->|không| R2["khong_nhan_ra"]
    C -->|có| D{"nhiều nhóm khác nhau<br/>VÀ trong đó có nhóm nguy hại?"}
    D -->|có| R3["nhieu_vat<br/>bất kể confidence"]
    D -->|không| E{"model khai 'nhiều vật'<br/>nhưng KHÔNG liệt kê món nào?"}
    E -->|có| R4["nhieu_vat"]
    E -->|không| F{"confidence dưới ngưỡng của nhóm?"}
    F -->|không| OK([trả lời + hướng dẫn])
    F -->|có| G{"vì chất lượng ảnh?"}
    G -->|có| R5["anh_toi / mo / vat_bi_che"]
    G -->|không| H{"nhóm nguy hại?"}
    H -->|có| R6["nghi_nguy_hai"]
    H -->|không| R7["duoi_nguong"]

    style R1 fill:#fee2e2
    style R3 fill:#fee2e2
    style R6 fill:#fecaca
    style OK fill:#dcfce7
```

**Vì sao chặn cứng đứng trước:** nó **bỏ qua confidence hoàn toàn**. Bình gas thì
model có tự tin 99% cũng không được phép hướng dẫn.

**Vì sao "nhiều nhóm" kiểm trước ngưỡng:** bước so ngưỡng chỉ chạy khi confidence
thấp. Đặt sau sẽ bỏ lọt đúng ca nguy hiểm nhất — ảnh có cả bình giữ nhiệt lẫn củ
sạc, model tự tin 0,85 về bình giữ nhiệt và **âm thầm bỏ qua cục sạc**. Đây là
failure case thật, bản ghi id 185 trên deploy.

**Từ chối ≠ vô dụng.** Khi từ chối, hệ thống vẫn hiện phỏng đoán nhưng **dán nhãn
rõ là phỏng đoán và không kèm hướng dẫn xử lý**. Đó là ranh giới giữa "thận
trọng" và "vô dụng".

### 10.2 Ba điểm HITL

```mermaid
flowchart LR
    subgraph H1["HITL #1 — yêu cầu thu gom"]
        P1["Yêu cầu mới"] --> P2{"vượt ngưỡng?<br/>trên 30 kg · trên 3 món<br/>· CÓ MÓN NGUY HẠI"}
        P2 -->|có| P3["cho_duyet — BQL duyệt"]
        P2 -->|không| P4["cho_nhan tự động"]
    end
    subgraph H2["HITL #2 — nhãn phân loại"]
        Q1["conf thấp / nghi nguy hại"] --> Q2["verify-queue<br/>đội vệ sinh xác nhận"]
        Q2 --> Q3["lý do chọn từ danh sách cố định<br/>chảy vào tập cải tiến"]
    end
    subgraph H3["HITL #3 — tuyến thu gom"]
        R1["Agent gộp tuyến"] --> R2["status=proposed"]
        R2 --> R3["Đội trưởng duyệt / sửa"]
        R3 --> R4["route_diff: bản AI ↔ bản người sửa"]
    end
```

**HITL #3 là điểm quan trọng nhất về mặt nguyên tắc:** agent **không được tự đổi
lịch làm việc của người**. Tuyến do agent đề xuất luôn ra đời ở trạng thái
`proposed`, và `route_diff()` cho phép so bản AI đề xuất với bản người đã sửa —
vừa là guardrail vừa là nguồn dữ liệu cải tiến.

**Nhóm nguy hại luôn cần người duyệt bất kể khối lượng** — nhóm đó có quy trình
xử lý riêng, không đi cùng chuyến đồ cồng kềnh.

---

## 11. Luồng B và C — tra quy định và điều phối tuyến

### 11.1 RAG hybrid (`advise`)

```mermaid
flowchart LR
    Q["câu hỏi + nhãn rác + building_id"] --> F["LỌC THEO TOÀ<br/>trước khi xếp hạng"]
    F --> B["BM25<br/>thuần Python · luôn chạy được"]
    F --> V["Embedding cosine<br/>có cache đĩa"]
    B --> M["gộp điểm<br/>RAG_VECTOR_WEIGHT=0.35"]
    V --> M
    M --> TOP["top-k đoạn + điểm từng nguồn"]
    TOP --> ADV["hướng dẫn CÓ TRÍCH NGUỒN"]
    V -.->|"mất API key / lỗi mạng"| DEG["lui về thuần BM25<br/>degraded=True + ghi lý do"]
    DEG --> M
```

Ba điểm khiến phần này **vượt naive RAG** (PLO 3):

1. **Hybrid thật** — BM25 chạy thuần Python nên hệ thống vẫn truy hồi được khi
   chưa có API key; embedding chỉ là phần cộng thêm.
2. **Lọc theo toà trước khi xếp hạng** — quy định mỗi toà mỗi khác, trộn tài liệu
   toà khác vào là *trả lời sai*, không phải "hơi lệch".
3. **Đo được.** Trên 18 câu ở `eval/retrieval_questions.py`:

   | Chỉ số | BM25 thuần | Hybrid |
   |---|---|---|
   | hit@1 | 0,667 | **0,722** |
   | hit@5 | 0,944 | **1,000** |
   | MRR | 0,792 | **0,838** |

   > Dùng hit@k + MRR **thay cho precision@5**: mỗi câu chỉ có 1–2 đoạn đúng nên
   > precision@5 trần cứng ở 0,2–0,4, đọc lên gây hiểu nhầm là hệ thống dở.

**Mọi câu trả lời đều phải chỉ ra được nguồn.** Khối UI nào đưa kết luận mà không
có đường dẫn về văn bản gốc là khối thiết kế sai.

### 11.2 Gộp tuyến (`route_planner.py`)

```mermaid
flowchart TD
    A["yêu cầu đã duyệt<br/>cùng ngày + khung giờ"] --> B["neo vào toà của yêu cầu đầu"]
    B --> C{"trong bán kính cụm 0,8 km?"}
    C -->|không| X1["loại — too_far"]
    C -->|có| D{"còn tải trọng?<br/>mặc định 200 kg"}
    D -->|không| X2["loại — over_capacity"]
    D -->|có| E["nhận vào tuyến"]
    E --> F["sắp thứ tự ghé: nearest-neighbour + 2-opt"]
    F --> G["ước km và so BASELINE<br/>3,6 km mỗi chuyến lẻ"]
    G --> H["criteria[] — khối 'vì sao gộp thế này'"]
    H --> I["status=proposed — vào HITL #3"]
```

**Có chủ đích không dùng OR-Tools.** VRP đầy đủ là cái bẫy nuốt hết thời gian mà
không thêm cột điểm nào; gộp theo cụm toà + khung giờ đã đủ tạo ra con số "tiết
kiệm bao nhiêu km" để đưa lên báo cáo. Điều bắt buộc phải có là khối `criteria[]`
giải thích **vì sao** gộp như vậy — quyết định của agent phải đọc được bởi người.

#### Thứ tự ghé điểm dừng — `toi_uu_tuyen.py` (10/08)

Bản trước xếp điểm dừng theo **tên toà rồi mã căn** — tức theo bảng chữ cái, một
thứ tự không liên quan gì tới quãng đường. Nay là **TSP đường mở**:
nearest-neighbour dựng thứ tự ban đầu, rồi 2-opt đảo từng đoạn con để gỡ các nét
cắt chéo, lặp tới khi một vòng quét trọn vẹn không cải thiện gì.

Ba ràng buộc thiết kế:

- **Đường mở, không đóng vòng.** `estimate_route_km` đã cộng riêng 1,2 km cố định
  cho chặng đi/về khỏi khu tập kết, nên hàm đo độ dài chỉ cộng các cặp liền kề.
- **Kết quả xác định.** Hoà thì chọn chỉ số nhỏ hơn — cùng đầu vào luôn cho cùng
  thứ tự, nếu không thì không ai kiểm chứng được gì.
- **Không biết gì về CSDL.** Module nhận một danh sách bất kỳ và một hàm đo
  khoảng cách, nên test được bằng điểm phẳng Euclid, không cần dựng CSDL.

Đo trên 100 bộ 7 điểm ngẫu nhiên, đối chiếu với vét cạn `7!`:

| | Tổng quãng đường | Đạt tối ưu tuyệt đối |
|---|---|---|
| Xếp theo bảng chữ cái (bản cũ) | 2189,8 | — |
| **Nearest-neighbour + 2-opt** | **1804,8 (−17,6%)** | **88/100 bộ** |

⚠️ **Không gọi đây là Dijkstra hay A\*.** Hai thuật toán đó trả lời câu hỏi "đi
từ A tới B đường nào" và cần đồ thị đường phố — thứ repo này không có. Câu hỏi ở
đây là "ghé N điểm theo thứ tự nào cho ngắn", đó là TSP/VRP.

Giới hạn còn lại: điểm ghé **đầu tiên** bị cố định vào phần tử đầu danh sách,
trong khi chặng đi/về là hằng số nên không có lý do gì phải cố định. Thả ra
(chạy nearest-neighbour từ cả N điểm đầu, lấy bản ngắn nhất) đo được thêm −6,3%
và lên 98/100 bộ tối ưu — đã ghi vào nợ kỹ thuật, chưa làm.

### 11.3 ⚠️ Hai bộ từ vựng trạng thái dùng chung ba từ

Đây là cạm bẫy nguy hiểm nhất của codebase hiện tại:

```
PickupRequest.status : pending · approved · scheduled · done · cancelled · rejected
PickupRoute.status   : proposed · approved · done · in_progress · cancelled
```

> 🚨 **Tìm-thay thế mù chuỗi `"approved"` trên cả repo sẽ phá state machine của
> tuyến đường, và test có thể không bắt được.** Danh sách các dòng thuộc về TUYẾN
> nằm trong comment ngay trên `TU_TRANG_THAI_CU` ở `src/services/pickup_lifecycle.py`.

Đang có một **cuộc di trú dở dang** sang máy trạng thái mới 10 bước:

```mermaid
stateDiagram-v2
    [*] --> moi_tao
    moi_tao --> cho_duyet: vượt ngưỡng HITL
    moi_tao --> cho_nhan: dưới ngưỡng
    moi_tao --> da_huy
    cho_duyet --> cho_nhan: BQL duyệt
    cho_duyet --> tu_choi: BQL từ chối
    cho_nhan --> da_nhan: nhân viên nhận
    cho_nhan --> da_huy
    da_nhan --> dang_van_chuyen
    da_nhan --> da_huy
    dang_van_chuyen --> da_giao_don_vi
    da_giao_don_vi --> hoan_tat: đơn vị xác nhận khối lượng THẬT
    da_giao_don_vi --> tranh_chap
    tranh_chap --> hoan_tat
    hoan_tat --> [*]
    tu_choi --> [*]
    da_huy --> [*]
```

**Điểm thiết kế đáng chú ý:** một yêu cầu **chỉ tích điểm ở `hoan_tat`**, và
`hoan_tat` chỉ tới được qua `da_giao_don_vi` — nơi một người ở đơn vị thu gom xác
nhận khối lượng thật. Hệ thống **không bao giờ trao điểm dựa trên ước lượng khối
lượng của AI**.

Trạng thái di trú (tính tới 05/08): chỗ **đọc** đã lật xong, chỗ **ghi** còn
nguyên từ vựng cũ (`pickup.py:235,261,288` · `route_planner.py:280,291,321,423` ·
`routes.py:127` · default cột trong `models.py` · ~13 chỗ trong `seed.py`).
`chuan_hoa()` chịu **cả hai chiều** chính là để cho phép tình trạng dở dang này
chạy được.

---

## 12. Luồng D — thùng thu gom thông minh

Phần mới nhất, dựng trong phiên 05/08. Đây là chỗ **phần cứng vào phạm vi** —
nhưng chỉ với vai trò **nguồn dữ liệu cho phần mềm**, không làm cơ cấu phân loại
tự động (quyết định này còn nợ ADR-0009).

```mermaid
sequenceDiagram
    autonumber
    participant D as Thiết bị / device_simulator.py
    participant API as POST /bins/:code/readings
    participant S as services/bins.py
    participant DB as bins + bin_readings
    participant FE as Màn /dieu-phoi

    D->>API: fill_percent · battery_percent · source + X-Device-Key
    API->>API: BIN_DEVICE_KEY rỗng thì trả 503 — FAIL CLOSED
    API->>API: hmac.compare_digest trên BYTES
    API->>API: source thuộc device / simulator / manual
    API->>S: ghi_nhan_reading(...)
    S->>S: kiểm fill và battery trong 0–100
    S->>DB: INSERT reading + cập nhật số mới nhất trên Bin
    S-->>API: trạng thái tính NGAY trên đối tượng vừa ghi
    API-->>D: status = can_gom / het_pin / ...

    FE->>API: GET /bins và GET /bins/stats — song song, nhịp 3 giây
    API-->>FE: danh sách + 4 con số
    FE->>FE: bản đồ Leaflet · ssr:false
```

### Bốn trạng thái và thứ tự ưu tiên **bắt buộc**

```
mat_ket_noi  >  het_pin  >  can_gom  >  binh_thuong
```

**Mất kết nối phải thắng.** Một thùng offline 3 ngày vẫn còn lưu con số 85% của
lần báo cuối; nếu xét `can_gom` trước thì đội xe chạy tới một thùng mà **không ai
biết thực sự đầy bao nhiêu**. Cũng phải xét trước `het_pin`: mất kết nối nghĩa là
không biết tình trạng pin hiện tại ra sao.

### Bốn quyết định kỹ thuật trong luồng này

| Quyết định | Vì sao |
|---|---|
| **Fail closed** — `BIN_DEVICE_KEY` rỗng thì chặn hết, trả 503 | Endpoint này ghi các con số mà quyết định điều phối dựa vào. Một hàng ingest hở cho phép bất kỳ ai đánh lừa đội xe chạy tới thùng rỗng, hoặc **giấu một thùng đang đầy** |
| `hmac.compare_digest` trên **bytes** | Chống tấn công timing; và chuỗi có dấu tiếng Việt làm hàm này ném `TypeError` → **500 thay vì 401**, làm bẩn cột "lỗi hệ thống" của trang Vận hành |
| Chuẩn hoá aware/naive **tại chỗ so sánh** | Cột `DateTime` không có `timezone=True` nên SQLite trả naive, còn `utcnow()` của dự án là aware. Đưa việc chuẩn hoá lên caller là rải lỗi ra mọi chỗ gọi |
| `/bins/stats` khai **trước** `/bins/{code}` | FastAPI chọn endpoint theo thứ tự khai báo — đặt sau thì `"stats"` bị coi là một mã thùng và 4 con số trên dashboard biến mất |

> ⚠️ **Bẫy demo:** `BIN_OFFLINE_MINUTES = 30` mà `last_seen_at` của thùng seed tính
> lúc chạy seed. Seed lúc 11:47, mở lúc 14:07 → cả 10 thùng đều "Mất kết nối".
> Cách chữa đúng là **chạy `device_simulator.py` trong lúc demo** — đó vốn là lý
> do nó tồn tại. Đừng nới `BIN_OFFLINE_MINUTES` cho vừa buổi trình bày; đó là bẻ
> cong sản phẩm.

---

## 13. Mô hình dữ liệu (26 bảng)

```mermaid
erDiagram
    users ||--o{ media : "tải lên"
    users ||--o{ classifications : "hỏi"
    users }o--|| units : "ở"
    units }o--|| buildings : "thuộc"
    buildings ||--o{ collection_schedules : "có lịch"
    buildings ||--o{ knowledge_docs : "quy định riêng"
    buildings ||--o{ bins : "đặt tại"

    media ||--o| classifications : "được phân loại"
    waste_categories ||--o{ classifications : "nhãn dự đoán"
    classifications ||--o{ classification_feedback : "phản hồi"
    classifications }o--|| agent_runs : "sinh bởi"

    knowledge_docs ||--o{ knowledge_chunks : "cắt thành"

    pickup_requests ||--o{ pickup_events : "timeline"
    pickup_requests ||--o{ route_stops : "được xếp vào"
    pickup_routes ||--o{ route_stops : "gồm"

    agent_runs ||--o{ run_node_metrics : "từng node"

    bins ||--o{ bin_readings : "báo về"

    eval_runs ||--o{ failure_cases : "ca sai"
```

### Nhóm bảng

| Nhóm | Bảng | Ghi chú thiết kế |
|---|---|---|
| Danh tính | `users` `buildings` `units` | PBKDF2 hash, không lưu mật khẩu thô |
| Danh mục | `waste_categories` | 9 nhóm · `min_confidence` **riêng từng nhóm** · `is_hazardous` · `clip_prompts` |
| Ảnh | `media` | `phash` · `exif_stripped` · `faces_blurred` · **`removed_fields`** · `expires_at` · `kept_for_eval` |
| Phân loại | `classifications` `classification_feedback` | `items` JSON nhiều món · `refused` + `refusal_reason` · `tier` `model` `prompt_version` · `advice_sources` · `latency_ms` `cost_usd` |
| Tri thức | `knowledge_docs` `knowledge_chunks` | `embedding` là JSON list cho SQLite → đổi sang kiểu `vector` của pgvector khi lên Postgres, phần còn lại giữ nguyên |
| Thu gom | `pickup_requests` `pickup_events` `pickup_routes` `route_stops` | **khối lượng là KHOẢNG** `weight_min`/`weight_max`; ngưỡng HITL so với **cận trên** |
| Vận hành | `agent_runs` `run_node_metrics` `audit_log` `alerts` `notifications` `collection_schedules` | mỗi node đi qua để lại một bản ghi, không ngoại lệ |
| Chất lượng | `eval_runs` `failure_cases` | |
| Thùng | `bins` `bin_readings` | số mới nhất nằm trên `bins` cho màn điều phối; lịch sử đầy đủ ở `bin_readings` |

**Hai quy ước xuyên suốt:**

- **`is_seed`** — mọi bản ghi demo đều gắn cờ, và trang Vận hành **tách riêng** số
  liệu seed khỏi số liệu thật. Không bao giờ để dữ liệu mô phỏng trộn vào chỉ số
  đưa lên báo cáo.
- **Khối lượng là khoảng, không phải một số.** Vision ước lượng kg từ ảnh sai vài
  lần là bình thường; sai số phải nghiêng về phía **cần người duyệt**
  ([ADR-0003](docs/decisions/0003-phan-tang-rac-va-trong-tam-doi-ve-sinh.md)).

---

## 14. Bề mặt API và phân quyền

51 route, tiền tố `/api/v1`. Khuôn lỗi thống nhất cho **mọi** loại lỗi:

```json
{"error": {"code": "VISION-500", "message_vi": "…", "detail": {}}}
```

| Nhóm | Route tiêu biểu | Quyền |
|---|---|---|
| Xác thực | `POST /login` · `GET /me` · `GET /demo-accounts` | công khai / đã đăng nhập |
| Phân loại | `POST /classify` · `POST /classify/text` · `GET /classifications` · `POST /classifications/{id}/feedback` | `classify` |
| HITL #2 | `GET /verify-queue` · `POST /classifications/{id}/verify` | `verify_label` — cleaner + manager |
| Ảnh | `GET /media/{id}` · `GET /media/{id}/privacy` · `GET /media/{id}/original` · `DELETE /media/{id}` | `view_original_media` — **manager, và mỗi lần xem ghi `AuditLog`** |
| Danh mục | `GET /categories` · `PATCH /categories/{code}` · `GET /buildings/{id}/schedule` · `POST /knowledge/test-retrieval` | `edit_catalog` cho PATCH |
| HITL #1 | `POST /pickups` · `POST /pickups/{id}/review` | `review_pickup` — chỉ manager |
| HITL #3 | `POST /routes/propose` · `POST /routes/{id}/review` · `POST /routes/{id}/stops/{id}/done` | `review_route` — chỉ manager |
| Thùng | `GET /bins` · `GET /bins/stats` · `GET /bins/{code}` | `view_bins` — cleaner + manager |
| Giao thùng | `PATCH /bins/{code}/nhan-vien` | `assign_bin` — **chỉ manager**, ghi `AuditLog` mỗi lần giao |
| Điểm gửi (cư dân) | `GET /bins/diem-gui` | `view_diem_gui` — bản thu gọn, **không kèm dữ liệu vận hành** |
| Hồ sơ cá nhân | `PATCH /auth/me` · `GET /auth/me/history` · `GET /buildings/{id}/units` | `edit_own_profile` — `email` và `role` không nằm trong schema sửa |
| Đăng ký | `POST /auth/register` | **công khai** — vai trò luôn là `resident`, client không tự chọn được. ⚠️ chưa có rate limit |
| Ingest thiết bị | `POST /bins/{code}/readings` | **không JWT** — `X-Device-Key`, fail closed |
| Vận hành | `GET /ops/metrics` · `GET /runs` · `GET /runs/{id}` · `GET /eval/summary` · `GET /alerts` | `view_ops` `view_runs` `view_eval` — manager |
| Công khai | `GET /health` · `GET /api/v1/status` | không cần đăng nhập |

**Ma trận 19 quyền × 3 vai trò** ở `src/services/auth.py:PERMISSIONS`. Nguyên tắc
UI đi kèm: vai trò không có quyền thì **hiện mờ kèm tooltip giải thích, không ẩn
hẳn** — để ranh giới phân quyền nhìn thấy được, thay vì để người dùng đoán.

`GET /api/v1/status` trả provider từng tầng và **có key hay chưa**; **giá trị key
không bao giờ được trả ra ngoài**.

---

## 15. Quyền riêng tư ảnh

Đây là phần mạnh nhất của đề về mặt an toàn AI, và **không được cắt**.

```mermaid
flowchart LR
    A["ảnh gốc từ điện thoại"] --> B["tước TOÀN BỘ EXIF<br/>GPS chính xác tới mét"]
    B --> C["làm mờ khuôn mặt<br/>OpenCV Haar cascade"]
    C --> D["nén cạnh dài tối đa 512px"]
    D --> E["tính pHash"]
    E --> F["lưu 2 bản: đã xử lý + gốc"]
    F --> G["chỉ bản ĐÃ XỬ LÝ đi ra API model"]
    F --> H["bản gốc: chỉ manager mở được<br/>mỗi lần mở ghi AuditLog"]
    F --> I["removed_fields[] — màn<br/>'ảnh của tôi đã bị xoá gì'"]
    F --> J["expires_at — tự xoá"]

    style G fill:#dcfce7
    style H fill:#fef3c7
```

**Vì sao nghiêm đến thế:** ảnh thùng rác có thể chứa khuôn mặt, biển số xe, số căn
hộ, **hoá đơn/giấy tờ có tên và địa chỉ**, nhãn thuốc. Và mọi ảnh chụp bằng điện
thoại đều mang EXIF chứa toạ độ GPS chính xác tới mét.

Có **test khẳng định EXIF đã sạch** sau tiền xử lý — đây là loại bảo đảm phải
kiểm bằng test, không phải bằng review code.

Service worker của PWA **không bao giờ cache ảnh cư dân hay endpoint có token**.

---

## 16. Quan sát và đo đạc

### 16.1 Đo hệ thống

```mermaid
flowchart LR
    N["mỗi node của agent"] --> NM["NodeMetric<br/>duration · tokens · cost · error"]
    NM --> RN["runs.finish_run()"]
    RN --> DB[("agent_runs<br/>run_node_metrics")]
    DB --> MT["metrics.py"]
    MT --> M1["cost_metrics<br/>kèm price_known từng tầng"]
    MT --> M2["latency_metrics<br/>p50/p95 theo node"]
    MT --> M3["error_metrics"]
    MT --> M4["routing_metrics<br/>tỉ lệ trúng từng tầng"]
    M1 --> UI["Trang Vận hành"]
    M2 --> UI
    M3 --> UI
    M4 --> UI
```

Trạng thái một lần chạy có **ba** giá trị, không phải hai:

| `AgentRun.status` | Nghĩa |
|---|---|
| `ok` | mọi node xanh |
| `degraded` | **có node lỗi nhưng pipeline vẫn ra kết quả** — ví dụ T1 hỏng, T2 cứu |
| `error` | không ra được kết quả |

Tách `degraded` ra để trang Vận hành đếm đúng: một hệ thống tự cứu được không nên
bị tính là hỏng, nhưng cũng không được giả vờ là hoàn toàn khoẻ.

**"$0 vì chưa tra được giá" ≠ "$0 thật".** NVIDIA không công bố giá $/1M token cho
`llama-3.2-90b-vision` (tier developer chạy bằng credit + giới hạn nhịp), nên
`cost_metrics` trả thêm `price_known` từng tầng và UI hiện **"chưa có giá"**. Tầng
chạy trên máy mình (T0, T0.5) vẫn là $0 thật. **Không điền số mò vào bảng giá** —
làm thế là biến cột chi phí thành số bịa.

---

## 17. Xử lý lỗi và suy giảm có kiểm soát

Yêu cầu bắt buộc của chương trình: *"xử lý lỗi và cảnh báo giới hạn của hệ thống"*.

| Hỏng cái gì | Hệ thống làm gì | Người dùng thấy gì |
|---|---|---|
| T1 lỗi / JSON hỏng | **T2 cứu** nếu khác provider | kết quả bình thường · run `degraded` |
| T1 và T2 cùng hỏng | từ chối, `refusal_reason=model_loi` | "Hệ thống nhận diện đang gặp sự cố" |
| T2 lỗi khi escalate | **giữ kết quả T1**, để cửa ngưỡng phán | không âm thầm nâng độ tin cậy |
| Cạn quota Gemini | chỉ mất tầng dùng Gemini | các tầng khác vẫn chạy |
| Mất API embedding | RAG **lui về thuần BM25** | `degraded=True` + ghi rõ lý do trên UI |
| Model local chưa nạp xong | bỏ qua T0.5, `status="skipped"` | không ai biết, chỉ chậm hơn |
| Chưa có `BIN_DEVICE_KEY` | ingest thùng **fail closed** 503 | thông báo nói rõ phải đặt biến nào |
| Ảnh quá 12 MB / không đọc được | `IMG-413` / `IMG-415` | thông báo tiếng Việt |
| Nạp dữ liệu nền thất bại lúc khởi động | **vẫn để máy chủ lên** | trang lỗi còn đọc được, hơn là cả service chết |

**Nguyên tắc chung:** mọi mã lỗi đều có `message_vi` viết cho người thật đọc, và
mọi trạng thái suy giảm đều **hiện ra trên UI** thay vì im lặng.

---

## 18. Kiến trúc frontend

```
frontend/src/
├─ app/
│  ├─ page.tsx          ← SPA theo vai trò: resident · cleaner · manager
│  ├─ dieu-phoi/        ← màn Điều phối thùng (bản đồ Leaflet)
│  └─ tai-app/          ← trang tải APK / cài PWA
├─ components/
│  ├─ resident/  ask · onboarding · personal · pickup-wizard · result
│  ├─ cleaner/   screens
│  ├─ manager/   console · insights · queues
│  ├─ bins/      6 file từ bản thiết kế Lovable
│  ├─ pwa/       cai-app · register-sw
│  └─ ui/        primitives · shell
└─ lib/  api · bins · format · icons · platform · session · types · utils
```

**Ba ràng buộc kiến trúc frontend:**

1. **`output: "export"` là bất khả xâm phạm.** Nó là điều kiện để cùng một bản
   build phục vụ Vercel + Capacitor + service worker. Đây là lý do Leaflet phải
   nạp bằng `dynamic(..., {ssr: false})`, và là lý do **không đổi sang TanStack
   Start** dù bản thiết kế Lovable viết bằng nó.
2. **Camera gói trong `lib/platform.ts`** — một chỗ duy nhất biết đang chạy trên
   web hay trong app native.
3. ⚠️ **Hai hệ design token đụng nhau, đã xử lý bằng lớp ánh xạ trong
   `globals.css`.** Tên shadcn (`bg-card`, `text-muted-foreground`, `bg-warn`…)
   trỏ về màu thương hiệu GreenBin, **không sửa một className nào** trong 55 chỗ
   của bản thiết kế. Muốn chỉnh tông màn `/dieu-phoi` thì sửa đúng chỗ đó.

   Đặc biệt: `--color-muted` của shadcn là màu **nền**, còn repo đã dùng nó làm
   màu **chữ phụ** ở 102 chỗ → đã tách thành `--color-muted-bg`. Định nghĩa đè lên
   sẽ làm toàn bộ chữ phụ hoá gần trắng trên nền sáng.

**Màn `/dieu-phoi` không bao giờ tự bịa số:** nhịp làm mới 3 giây chỉ gọi lại API;
số chỉ đổi khi có thiết bị thật — hoặc bộ mô phỏng — đang bơm dữ liệu vào.

### 18.1 Chỉ có ba đường dẫn thật — phần còn lại là trạng thái trong ứng dụng

Sản phẩm là **một ứng dụng trang đơn**: việc chuyển tab (Phân loại · Yêu cầu ·
Lịch · Điểm gửi · Tôi, và các hàng đợi của đơn vị thu gom) là **trạng thái React**,
không phải đường dẫn trình duyệt. Toàn hệ thống chỉ export đúng ba trang:

| Đường dẫn | Nội dung | Đo trên bản chạy thật |
|---|---|---|
| `/` | Ứng dụng theo vai trò: cư dân · nhân viên thu gom · đơn vị thu gom | HTTP 200 |
| `/tai-app/` | Hướng dẫn cài APK / PWA | HTTP 200 |
| `/dieu-phoi/` | Bản đồ điều phối thùng, chiếm trọn màn hình | HTTP 200 |

Hệ quả cần biết khi kiểm thử: **mọi đường dẫn khác trả 404, và đó là hành vi
đúng** chứ không phải lỗi định tuyến. Ví dụ `/pickups`, `/auth/login` không tồn
tại vì hai màn đó nằm bên trong `/`; còn `/classify/text` là **đường API của máy
chủ**, không phải một trang web. Bản export tĩnh sinh sẵn file HTML cho từng
trang thật nên deep-link và F5 đều chạy — **không cần `vercel.json` rewrite**.

Đánh đổi có chủ đích của mô hình này: đường dẫn không mô tả được vị trí người
dùng đang đứng, nên **không chia sẻ được link tới một tab cụ thể** và nút Back
của trình duyệt không đi ngược từng tab. Chấp nhận được với một ứng dụng dùng
trên điện thoại là chính; muốn đổi thì phải bỏ `output: "export"` — xem ràng
buộc 1 ở trên.

---

## 19. Triển khai và CI/CD

```mermaid
flowchart TB
    DEV["máy dev<br/>SQLite + torch đầy đủ"] -->|git push| GH["GitHub<br/>AI20K-Build-Phase-Cohort-3/P-075"]

    GH --> CI["CI — .github/workflows/ci.yml"]
    CI --> CI1["ruff check src/ tests/"]
    CI --> CI2["pytest"]
    CI --> CI3["npm run lint"]
    CI --> CI4["tsc --noEmit"]
    CI --> CI5["next build"]

    GH -->|"tag v*"| APK["android.yml<br/>build APK, đính vào Release"]
    GH -->|"auto deploy"| RD["Render — Docker<br/>backend + PostgreSQL"]
    GH -->|"auto deploy"| VC["Vercel — out/ tĩnh"]

    RD -.->|"CLIP_ASSETS_URL"| REL["GitHub Release<br/>2 file ONNX · 89 MB"]

    style CI fill:#eff6ff
```

| Hạng mục | Cấu hình |
|---|---|
| Backend | Render web service · Docker · Singapore · plan free (**512 MB RAM**) · `healthCheckPath: /health` |
| CSDL | Render PostgreSQL free |
| Frontend | Vercel, phục vụ `frontend/out/` |
| Khởi động | `SEED_ON_START` tự nạp dữ liệu nền; `bootstrap()` gọi lại nhiều lần vô hại |
| Model local | Nạp trước ở **luồng nền** lúc khởi động, không chặn máy chủ lên |
| Nhúng kho quy định | `EMBED_KB_ON_START` chạy ở luồng riêng vì nó đụng mạng |

**Ràng buộc 512 MB là ràng buộc thiết kế thật, không phải chi tiết vận hành.** Nó
là lý do CLIP phải nén xuống ONNX int8 (185 MB RAM), và là lý do khi làm YOLO thì
**YOLO phải THAY CLIP chứ không cộng thêm** — chạy cả hai là chạm trần và Render
**giết tiến trình chứ không cảnh báo**.

> ⚠️ Bản deploy đang chạy (`greenbin-api-hozl.onrender.com` /
> `test-gbai-gray.vercel.app`) là của **repo cá nhân** `imninh/Test_GBAI`. Repo
> nhóm **chưa được deploy** — xem mục 21.

---

## 20. Ánh xạ tiêu chí chấm và PLO

| PLO | Nội dung | Thể hiện ở đâu trong kiến trúc này |
|---|---|---|
| 1 | Kiến trúc agent, model routing | Định tuyến 4 tầng (mục 8) · provider theo tầng |
| 2 | Multi-agent, trace được | Graph `classify → advise → schedule` · nhánh skip vẫn ghi node · màn Agent Run |
| 3 | RAG vượt naive, có đo lường | Hybrid BM25 + embedding · lọc theo toà · hit@k + MRR (mục 11.1) |
| 4 | Giá trị kinh doanh | Giảm phí xử lý rác · giảm số chuyến xe (so `baseline_km`) · nền pháp lý |
| 5 | Hạ tầng, giám sát độ trễ/lỗi/chi phí | `metrics.py` + trang Vận hành · `price_known` (mục 16.1) |
| 6 | Guardrails, HITL, chống rò rỉ dữ liệu | `_finalize` 7 cửa · 3 điểm HITL · pipeline ảnh (mục 10, 15) |
| 7 | Eval pipeline, failure → cải tiến | `eval/run_eval.py` + `run_retrieval_eval.py` · lý do từ chối chọn từ danh sách cố định |
| 8 | Vibe coding có kiểm soát | AI logging → Phoenix · `JOURNAL.md` · `WORKLOG.md` · 8 ADR |

| Tiêu chí chấm | Bằng chứng trong repo |
|---|---|
| **Product/Business** | 3 vai trò thật · mỗi kết quả AI sinh hành động hoặc bản ghi · nền pháp lý NĐ 45/2022 |
| **System Design** | 4 tầng model · provider theo tầng · 2 state machine · suy giảm có kiểm soát |
| **UX/UI** | 21+ màn · từ chối có giải thích · quyền hiện mờ kèm tooltip · lịch thu gom xem được offline |
| **DevOps** | CI kiểm cả Python lẫn frontend · build APK theo tag · `render.yaml` khai cả web lẫn CSDL |
| **Code Quality** | ruff sạch · type hints hàm public · không bare `except` · 277 test · module thuần tách khỏi I/O |

---

---

## Phụ lục — chạy tại chỗ

```bash
cd C:/P-075
python scripts/seed.py --reset --demo                        # dữ liệu nền + 10 thùng demo
python -m uvicorn src.main:app --port 8000                   # backend · docs ở /docs
npm --prefix frontend run dev                                # frontend ở :3000
python scripts/device_simulator.py --steps 20 --interval 3   # cho thùng "sống"
```

Tài khoản demo: `resident@demo.vn` · `cleaner@demo.vn` · `manager@demo.vn`,
mật khẩu chung `demo1234`. Đăng nhập được cả bằng **số điện thoại**
(`0901000001` · `0901000002` · `0901000003`). Màn đăng nhập có 3 nút vào thẳng.
Màn `/dieu-phoi` cần vai `cleaner` hoặc `manager`.

Tầng T0.5 cần cài thêm: `pip install -r requirements-local-model.txt`
(torch 1,19 GB đã tách khỏi `requirements.txt` để bản deploy nhẹ).
