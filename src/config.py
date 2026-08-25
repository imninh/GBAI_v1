"""Cấu hình toàn hệ thống GreenBin AI.

Nguyên tắc: **đổi nhà cung cấp model chỉ bằng sửa ``.env``, không sửa code.**
Nhóm chưa có API key OpenAI nên tầng T1/T2 tạm chạy trên Gemini / OpenRouter /
NVIDIA NIM; khi có key OpenAI thì đổi ``VISION_PROVIDER=openai`` là xong, kiến
trúc định tuyến 3 tầng ở ``CLAUDE.md`` mục 4 giữ nguyên.

**Provider khai được theo từng tầng.** ``VISION_PROVIDER`` là mặc định chung;
``VISION_PROVIDER_T1`` / ``_T2`` / ``_TEXT`` ghi đè cho riêng một tầng. Lý do:
mỗi nhà cung cấp miễn phí có một kiểu hạn mức khác nhau (Gemini tính theo số
request rất ít, NVIDIA tính theo credit rộng hơn, CLIP local thì không tốn gì),
nên trộn chúng lại thì cạn quota một chỗ không làm chết cả sản phẩm.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Mọi tên mà hệ thống thực sự dùng được, lấy từ `build_client_for` trong
# `src/services/vision/__init__.py` (gemini, openai, openrouter, nvidia, deepseek,
# groq, mistral, local_only) cộng `stub` — tên của đường `get_vision_model` (IoT).
# `local_only` dựng được qua nhánh riêng (ném `VisionUnavailableError` mã
# VISION-LOCAL); `stub` không nằm trong `build_client_for` — nó do `get_vision_model`
# phục vụ (bẫy đã báo trong báo cáo gói P55).
#
# Đừng hạ xuống `str`: gõ sai tên provider sẽ không ai phát hiện cho tới lúc gọi
# model và nhận VISION-400 — lỗi đã tốn hai ngày tuần trước.
VisionProvider = Literal[
    "gemini", "groq", "openai", "openrouter", "nvidia", "deepseek", "mistral", "local_only", "stub"
]

# Ba tầng có gọi model đám mây. T0 (cache pHash) và T0.5 (CLIP local) không gọi
# nên không nằm ở đây.
ModelTier = Literal["t1", "t2", "text"]

_TIER_INDEX: dict[str, int] = {"t1": 0, "t2": 1, "text": 2}

# Điểm cuối của các nhà cung cấp dùng giao thức tương thích OpenAI.
OPENAI_COMPATIBLE_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
}

# Phiên bản prompt phân loại. **Một nguồn sự thật duy nhất** — nâng ở đây mỗi khi
# sửa `_SYSTEM_PROMPT` trong `src/services/vision/base.py`.
#
# Trước 03/08/2026 con số này nằm ở BA chỗ rời nhau: hằng số `PROMPT_VERSION`
# trong `base.py` (prompt thật), trường `Settings.prompt_version` (cái được ghi
# vào bản ghi và hiện trên trang Vận hành), và mặc định của `ClassifyOutcome`.
# Nâng prompt lên v3 mà `ops/metrics` vẫn báo "v2" khiến việc chẩn đoán đi sai
# hướng: tưởng Render chưa nhận code mới, trong khi nó đã nhận từ lâu.
#
# `base.py` đã import từ file này nên đặt hằng số ở đây là chiều import đúng.
PROMPT_VERSION = "v3"

# Giá tham chiếu USD / 1 triệu token ``(vào, ra)``, dùng để ước tính chi phí khi
# nhà cung cấp không trả về giá. Số token thật vẫn lấy từ ``usage`` của API —
# xem ``src/services/vision/base.py``.
#
# ⚠️ **Model không có trong bảng này bị tính $0 và gắn ``price_known=False``.**
# Đừng đọc $0 đó là "miễn phí" — nó nghĩa là *chưa biết giá*. Mọi chỗ hiển thị
# phải kiểm cờ ``price_known`` trước khi in con số ra.
#
# **Vì sao KHÔNG có model NVIDIA nào ở đây** (tra ngày 03/08/2026): tier
# developer của ``integrate.api.nvidia.com`` chạy bằng credit + giới hạn nhịp,
# NVIDIA **không công bố** bảng giá $/1M token cho
# ``meta/llama-3.2-90b-vision-instruct`` và ``meta/llama-3.1-8b-instruct``.
# Các trang tổng hợp giá bên thứ ba hoặc không có hai model này, hoặc chép giá
# của nhà cung cấp khác. Điền một con số mò vào đây sẽ biến "chi phí" trên
# trang Vận hành thành số bịa — tệ hơn hẳn so với việc nói thẳng là chưa biết.
#
# Muốn có con số chi phí thật cho báo cáo thì đường đúng là: đo số token thật
# (đã có), rồi nhân với giá của **một nhà cung cấp có công bố giá** cho cùng
# model, và ghi rõ đó là giá quy đổi tham chiếu chứ không phải tiền đã tiêu.
MODEL_PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o": (2.50, 10.00),
    "text-embedding-3-small": (0.02, 0.0),
}

# Model mặc định ``(T1, T2, text)`` của từng nhà cung cấp, dùng khi ``.env``
# không khai tên model cụ thể.
PROVIDER_DEFAULT_MODELS: dict[str, tuple[str, str, str]] = {
    "openai": ("gpt-4o-mini", "gpt-4o", "gpt-4o-mini"),
    "openrouter": ("openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-4o-mini"),
    # T1 = llama-3.2-90b-vision, chốt ngày 03/08/2026 **trên ảnh rác thật**.
    #
    # Catalog NIM thật của tài khoản có 102 model và **không có model Qwen nào**
    # (họ Qwen đã end-of-life 27/07, gọi tới trả HTTP 410). Chỉ 5 model nhận ảnh,
    # trong đó phi-3-vision trả 404 với tài khoản này. Nên lựa chọn thực tế chỉ
    # còn ba dòng dưới đây.
    #
    # Đo lần đầu trên ảnh artwork linh vật (MỘT vật, nền phẳng) cho kết quả
    # NGƯỢC LẠI và suýt dẫn tới chọn sai model:
    #
    #   llama-3.2-11b-vision    parse 0/4 · 16,4s
    #   llama-3.2-90b-vision    parse 4/4 · 10,2s
    #   nemotron-nano-12b-v2-vl parse 4/4 ·  8,8s   ← nhanh nhất, tưởng là tốt nhất
    #
    # Đo lại trên hai ảnh rác thật (nhiều vật, lộn xộn, có đồ điện tử lẫn vào),
    # 3 lần mỗi model, ở trần token 2500:
    #
    #   nemotron-12b   ảnh A: nhãn SAI ("túi giấy") · ảnh B: hỏng 3/3 (lặp vô tận)
    #   llama-90b      ảnh A: đúng "chai nhựa"      · ảnh B: đúng "chai nhựa"
    #
    # Bài học ghi lại để khỏi lặp: **ảnh một vật nền phẳng là proxy tồi** cho
    # ảnh rác thật; model nhỏ chỉ lộ điểm yếu khi khung hình có nhiều vật.
    #
    # ⚠️ Cả hai model NVIDIA đều **gần như không nhìn ra đồ điện tử** lẫn trong
    # ảnh (90b: 0/6 lần · nemotron: 1/6), trong khi Gemini nhìn ra 2/2. Đây là
    # lý do phần "nhìn" đang được tính chuyển xuống tầng local — xem ADR-0008.
    "nvidia": (
        "meta/llama-3.2-90b-vision-instruct",
        "meta/llama-3.2-90b-vision-instruct",
        "meta/llama-3.1-8b-instruct",
    ),
    # Google đã đóng ``gemini-2.5-flash`` và ``gemini-2.5-pro`` với key tạo mới
    # ("no longer available to new users", HTTP 404) — chúng vẫn hiện trong danh
    # sách ``/models`` nên chỉ lộ ra lúc gọi thật. Bí danh ``*-latest`` không bị
    # khoá và tự trỏ sang bản mới nhất.
    # Đo ngày 01/08/2026: `pro-latest` và `2.0-flash` trả 429 ngay từ lần gọi đầu
    # trên free tier, nên T2 dùng `flash-latest`.
    # Model sinh hướng dẫn dùng bản `lite`: hạn free tier của `gemini-flash-latest`
    # (hiện trỏ tới gemini-3.6-flash) chỉ **20 request**, cạn sau vài phút thử.
    # Bước advise chạy sau MỌI lần phân loại thành công nên nó là chỗ tiêu quota
    # nhanh nhất — để nó ở model đắt là hết quota giữa buổi demo.
    "gemini": ("gemini-flash-lite-latest", "gemini-flash-latest", "gemini-flash-lite-latest"),
    # Groq — đo ngày 08/08/2026 bằng header `x-ratelimit-*` của chính tài khoản:
    # 1.000 request/ngày (Gemini free chỉ 20) nhưng **8.000 token/phút**, và một
    # ảnh 512px tốn ~1.865 token vào → khoảng 4 lượt chụp mỗi phút. Trần theo
    # phút mới là nút thắt thật, không phải trần theo ngày.
    #
    # `qwen/qwen3.6-27b` là model DUY NHẤT của Groq nhận ảnh, nên T1 và T2 cùng
    # tên; thực tế T2 vẫn để ở Gemini (xem .env) để mất một nhà cung cấp thì chỉ
    # mất một tầng — ADR-0006.
    "groq": ("qwen/qwen3.6-27b", "qwen/qwen3.6-27b", "openai/gpt-oss-120b"),
    # Mistral — model vision "pixtral", KHÔNG phải reasoning nên nhanh hơn qwen.
    # ⚠️ Tên dưới đây là ứng viên, PHẢI đối chiếu trang model của Mistral trước
    # khi chạy thật — tên model đổi thường xuyên.
    "mistral": ("pixtral-12b-2409", "pixtral-large-latest", "mistral-small-latest"),
    "local_only": ("", "", ""),
}

# Model embedding mặc định của từng nhà cung cấp. NVIDIA để trống vì đo ngày
# 02/08/2026 không endpoint nào qua đường OpenAI-compatible trả về vector —
# để trống thì RAG tự chạy thuần BM25 thay vì gọi hỏng liên tục.
PROVIDER_DEFAULT_EMBEDDING_MODELS: dict[str, str] = {
    "gemini": "gemini-embedding-001",
    "openai": "text-embedding-3-small",
    "openrouter": "openai/text-embedding-3-small",
    "nvidia": "",
    # Groq **không bán model embedding** — catalog ngày 08/08/2026 có 15 model,
    # không có cái nào sinh vector. Để trống thì RAG tự lui về BM25 thuần, nên
    # EMBEDDING_PROVIDER phải giữ ở `gemini` nếu muốn giữ phần hybrid.
    "groq": "",
    "local_only": "",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App -------------------------------------------------------------
    app_name: str = "GreenBin AI"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # ``https://localhost`` và ``capacitor://localhost`` là origin mà app Android
    # đóng gói bằng Capacitor tự dùng khi phục vụ giao diện từ trong máy. Thiếu
    # hai dòng này thì app cài về gọi API bị CORS chặn.
    cors_origins: str = (
        "https://gbai-v1.vercel.app,http://localhost:3000,http://localhost:3001,http://localhost:5173,"
        "http://127.0.0.1:3000,http://127.0.0.1:5173,https://localhost,capacitor://localhost"
    )

    # Địa chỉ gốc của ứng dụng WEB (bản xuất tĩnh) — nơi mã QR trỏ tới. KHÁC
    # ``cors_origins`` (danh sách origin được phép gọi API): hai thứ tình cờ hay
    # trùng nhau chứ không phải một. Mặc định để giá trị thật — biến rỗng là hỏng
    # câm (mã QR sinh ra sẽ trỏ về chính thiết bị quét), y như bài học
    # ``IOT_DEVICE_KEYS``.
    web_app_base_url: str = "https://gbai-v1.vercel.app"

    # Máy chủ tự nạp dữ liệu nền khi khởi động. Bật trên Render vì ở đó không có
    # chỗ chạy tay ``scripts/seed.py``; để tắt khi dev cho khỏi bất ngờ.
    seed_on_start: bool = False
    # Kèm dữ liệu demo mô phỏng (mọi bản ghi đều gắn cờ ``is_seed``) để trang
    # Vận hành / Chất lượng AI của bản deploy không trống trơn.
    seed_demo_on_start: bool = True

    # --- Xác thực --------------------------------------------------------
    # Hệ thống demo tự làm auth thay vì Supabase — xem ADR-0004.
    jwt_secret: str = "greenbin-dev-secret-doi-truoc-khi-deploy"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=60 * 12, ge=5)

    # Giới hạn tần suất cho `POST /auth/register` — endpoint công khai duy nhất
    # tạo được dữ liệu. Đặt `0` để TẮT hẳn (dùng khi cần diễn thử tạo nhiều tài
    # khoản liên tiếp trước giám khảo). Bộ đếm nằm trong bộ nhớ tiến trình:
    # nhiều worker thì mỗi worker một bộ đếm — xem docstring của
    # `src/services/gioi_han_tan_suat.py`.
    register_rate_limit: int = Field(default=10, ge=0)
    register_rate_window_seconds: int = Field(default=600, ge=1)

    # --- Thiết bị IoT -----------------------------------------------------
    # Chống phát lại cho đường thiết bị (captures / heartbeat / readings):
    # firmware gửi kèm ``X-Device-Timestamp`` (Unix giây) và
    # ``X-Device-Signature`` = HMAC-SHA256(khoá_thô, "{device_id}.{timestamp}").
    # MẶC ĐỊNH TẮT: firmware ngoài hiện trường chưa biết gửi hai header mới,
    # cờ tắt ⇒ đường đi giữ nguyên như cũ; bật lên thì request kiểu cũ bị 401.
    iot_chong_phat_lai: bool = False
    iot_cua_so_thoi_gian_s: int = Field(default=300, ge=1)

    # --- Khoảng cách đường đi thật (G3) ----------------------------------
    # Mặc định TẮT (để test chạy offline nhanh không đụng mạng). Bật qua ROUTE_REAL_DISTANCE=true trong .env.
    route_real_distance: bool = False
    osrm_base_url: str = "https://router.project-osrm.org"
    osrm_timeout_seconds: float = Field(default=4.0, gt=0)

    # --- Nhà cung cấp model vision ---------------------------------------
    # Mặc định chung cho mọi tầng.
    vision_provider: VisionProvider = "gemini"

    # Ghi đè cho riêng từng tầng. Để trống = dùng ``vision_provider``.
    # Cấu hình đang khuyến nghị (mỗi nguồn miễn phí lo phần nó khoẻ nhất):
    #   T1   → nvidia  (~1.000 credit, đủ cho phần lớn lưu lượng)
    #   T2   → gemini  (quota nhỏ nhưng chỉ tiêu vào ca khó)
    #   text → gemini  (bản lite, quota còn dư)
    vision_provider_t1: str = ""
    vision_provider_t2: str = ""
    vision_provider_text: str = ""

    openai_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    nvidia_api_key: str = ""
    deepseek_api_key: str = ""
    groq_api_key: str = ""
    mistral_api_key: str = ""

    # Tên model từng tầng. Mặc định điền theo provider trong ``resolve_models``
    # nếu để trống, nên thường không cần đụng tới.
    vision_model_t1: str = ""
    vision_model_t2: str = ""
    text_model: str = ""

    # Trần token đầu ra cho một lần gọi phân loại.
    #
    # 700 từng là nguyên nhân gốc của VISION-500 (đo 03/08/2026: JSON bị cắt,
    # `finish_reason: "length"`). 2000 đủ cho model thường, nhưng **model suy
    # luận thì không**: đo 08/08/2026 trên Groq, `qwen/qwen3.6-27b` tiêu hết
    # trần vào khối `<think>` rồi mới tới JSON. Để chỉnh được bằng .env thay vì
    # phải sửa code khi đổi model.
    vision_max_output_tokens: int = 2000
    # Timeout (giây) cho MỘT lệnh gọi model đám mây qua httpx. Trước đây hardcode
    # 60s trong openai_compat.py — trace production 13/08 cho thấy T1 treo hết 60s
    # rồi mới rơi xuống T2, ăn ~60s vào đường nóng. 15s đủ cho ảnh 512px detail=low;
    # ca treo thì fail-fast để leo tầng ngay. ⚠️ KHÔNG hạ dưới ~10s — T2 (reasoning)
    # cần vài giây thật để sinh JSON.
    vision_timeout_seconds: float = Field(default=15.0, gt=0)

    # T0.5 (YOLO) đã giơ cờ đồ điện tử thì hỏi T1 (mù đồ điện tử — đo 03/08 0/6; và
    # đo 13/08: p50 ~25s, 94% vẫn leo T2) chỉ tốn một lượt gọi chậm. Bật cờ này để đi
    # THẲNG T2 khi T0.5 đã nghi nguy hại — cắt lượt T1 vô ích. Tắt để về hành vi cũ.
    route_electronics_to_t2: bool = True

    # Giữ tên cũ để code/template cũ không gãy.
    model_name: str = "gpt-4o-mini"
    model_fast: str = "gpt-4o-mini"
    model_smart: str = "gpt-4o"
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    # --- Embedding cho RAG ------------------------------------------------
    # Tách khỏi tầng ``text``: nhà cung cấp giỏi sinh văn bản chưa chắc có
    # endpoint embedding dùng được. Đo ngày 02/08/2026: NVIDIA không nhận model
    # embedding nào qua đường OpenAI-compatible, còn `text-embedding-004` của
    # Google đã chết như các model 2.5 — chỉ `gemini-embedding-001` còn chạy.
    embedding_provider: str = ""  # trống = theo ``vision_provider``
    embedding_model: str = ""  # trống = mặc định của provider
    # ``gemini-embedding-001`` trả 3072 chiều; cắt còn 768 để kho vector nhẹ đi
    # 4 lần mà chất lượng gần như không đổi (Matryoshka). Đã kiểm API chấp nhận.
    embedding_dimensions: int = Field(default=768, ge=64, le=4096)
    # Tự nhúng kho quy định lúc khởi động. Bật trên Render vì ở đó không có chỗ
    # chạy tay `scripts/seed.py --embed`; để tắt khi dev cho khỏi tốn quota mỗi
    # lần khởi động lại máy chủ.
    embed_kb_on_start: bool = False
    # Trọng số của điểm embedding khi trộn với BM25 (0 = thuần từ khoá).
    # Quét thử ngày 02/08/2026 trên 18 câu hỏi ở ``eval/retrieval_questions.py``
    # cho thấy đẩy lên 0,8 thì hit@1 tăng từ 0,722 lên 0,833 — NHƯNG bộ câu đó
    # cố ý viết theo lối nói cư dân, tức thiên vị embedding, và 18 câu là quá ít
    # để chốt. Giữ 0,35 cho tới khi có bộ ~60 câu như CLAUDE.md mục 7 yêu cầu;
    # quét lại bằng `python eval/run_retrieval_eval.py --quet-trong-so`.
    rag_vector_weight: float = Field(default=0.35, ge=0.0, le=1.0)

    # Mặc định bám theo hằng số PROMPT_VERSION ở trên. Vẫn cho phép đè bằng biến
    # môi trường để so sánh A/B hai phiên bản prompt trên cùng một bản deploy.
    prompt_version: str = PROMPT_VERSION

    # --- Tầng T0.5: model local chạy offline trên CPU ---------------------
    local_model_enabled: bool = True
    # CLIP zero-shot: không cần train, không cần dữ liệu gán nhãn. Tải một lần
    # (~350MB) rồi chạy hoàn toàn offline.
    clip_model_name: str = "openai/clip-vit-base-patch32"
    # Đường chạy tầng T0.5 (ADR-0007):
    #   auto  — có bộ ONNX int8 thì dùng, không thì lui về torch
    #   onnx  — chỉ ONNX; máy chủ 512 MB dùng cái này
    #   torch — chỉ bản đầy đủ, giữ làm mốc đối chiếu khi chạy eval
    #   remote— gọi HTTP sang Hugging Face Space chạy cùng bộ ONNX (H1).
    #           KHÔNG nằm trong `auto`: `auto` là chọn tại chỗ, còn remote là
    #           quyết định có chủ đích đưa model ra ngoài.
    clip_runtime: Literal["auto", "onnx", "torch", "remote"] = "auto"
    clip_onnx_dir: str = "./assets/clip"
    # Máy chủ miễn phí dùng đĩa tạm nên file model mất sau mỗi lần khởi động
    # lại. Trỏ vào file .tar.gz trên GitHub Release để nó tự tải lại khi thiếu.
    clip_assets_url: str = ""
    # Đường chạy `remote` (gói H1): URL gốc của Space, ví dụ
    # `https://ten-don-vi-greenbin.hf.space`. Space CPU free NGỦ khi rảnh nên
    # request đầu chậm — timeout giữ nhỏ để ảnh rơi lên T1 nhanh thay vì treo
    # người dùng. `CLIP_RUNTIME=remote` mà URL rỗng thì tầng T0.5 tự tắt, không
    # nổ lúc khởi động.
    clip_remote_url: str = ""
    clip_remote_timeout_seconds: float = 8.0
    # Dưới ngưỡng này thì T0.5 không dám kết luận và đẩy lên T1.
    clip_accept_confidence: float = Field(default=0.82, ge=0.0, le=1.0)
    # Nhóm nguy hại không bao giờ được chốt bởi model local — luôn đẩy lên
    # tầng có khả năng suy luận. Xem CLAUDE.md mục 5.
    local_never_decides_hazardous: bool = True

    # --- Tầng T0.5b: YOLO phát hiện đồ điện tử ---------------------------
    # MẶC ĐỊNH TẮT. Bật lên thì mỗi ảnh chạy thêm ~100 ms trên CPU, đổi lại bịt
    # được chỗ mù đồ điện tử của T1 (đo 03/08: llama-90b 0/6, YOLO11n 4/4).
    yolo_enabled: bool = False
    yolo_assets_url: str = ""
    yolo_onnx_dir: str = "./assets/yolo"
    # Ngưỡng điểm của một hộp phát hiện. Thấp quá thì báo động giả, cao quá thì
    # bỏ sót — 0,35 là mức khởi điểm, CHƯA chuẩn lại trên ảnh rác thật.
    yolo_confidence: float = Field(default=0.35, ge=0.0, le=1.0)

    # --- Tầng T0.5d: cắt từng vật rồi CLIP chấm từng crop (hướng A) ----------
    # MẶC ĐỊNH TẮT — chưa đo xong trên ảnh rác thật. Bật lên thì ảnh nhiều vật
    # được cắt riêng từng crop, mỗi crop chỉ có một vật nên CLIP chấm cao hơn
    # hẳn → chốt được tại chỗ, $0, không leo cloud (Groq free tier chỉ
    # 8.000 token/phút — gọi cloud cho từng vật là bất khả thi).
    phan_loai_tung_vat: bool = False
    # Tối đa số vật cắt và chấm trong một ảnh; điểm cao được ưu tiên trước.
    so_vat_toi_da: int = 4

    # --- Tầng T0: cache pHash --------------------------------------------
    # Khoảng cách Hamming tối đa giữa 2 pHash để coi là cùng một món rác.
    phash_max_distance: int = Field(default=6, ge=0, le=64)

    # --- Ngưỡng an toàn và HITL ------------------------------------------
    # So với cận TRÊN của khoảng khối lượng (ADR-0003): sai số nghiêng về phía
    # cần người duyệt.
    hitl_weight_threshold_kg: float = Field(default=30.0, gt=0)
    hitl_item_count_threshold: int = Field(default=3, gt=0)
    # Sai số cho phép giữa khối lượng THẬT và khoảng ước lượng của AI khi chốt
    # yêu cầu thu gom (xem pickup_flow.xac_nhan_khoi_luong). Trong khoảng hoặc
    # lệch dưới ngưỡng này (so với cận trên/cận dưới) thì chốt ``hoan_tat``,
    # lệch nhiều hơn thì rơi vào ``tranh_chap``.
    pickup_weight_tolerance_percent: float = Field(default=20.0, ge=0.0)
    # Ngưỡng mặc định khi nhóm rác chưa khai báo ``min_confidence`` riêng.
    default_min_confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    hazardous_min_confidence: float = Field(default=0.80, ge=0.0, le=1.0)

    # --- Điều phối tuyến --------------------------------------------------
    vehicle_capacity_kg: float = Field(default=200.0, gt=0)
    # Quãng đường ước tính cho một chuyến đi lẻ tới một điểm, dùng làm baseline
    # để tính phần tiết kiệm. Con số minh hoạ, có ghi rõ trên UI.
    baseline_km_per_standalone_trip: float = Field(default=3.6, gt=0)
    vrp_enabled: bool = False
    vrp_num_vehicles: int = Field(default=3, gt=0)
    vrp_max_runtime_seconds: float = Field(default=5.0, gt=0)
    vrp_depot_lat: float = 21.0285
    vrp_depot_lng: float = 105.854

    # --- Thùng thu gom thông minh ------------------------------------------
    # Ngưỡng quyết định trạng thái điều phối của thùng đặt ngoài hiện trường
    # (xem ``src/services/bins.py``). Là field của Settings như các ngưỡng HITL
    # phía trên chứ không phải hằng số module, để đè được bằng biến môi trường;
    # env ``BIN_FILL_ALERT_PERCENT`` tự khớp field ``bin_fill_alert_percent``.
    bin_fill_alert_percent: int = Field(default=80, ge=0, le=100)
    bin_offline_minutes: int = Field(default=30, gt=0)
    bin_low_battery_percent: int = Field(default=15, ge=0, le=100)
    # Khoá dùng chung cho mọi thiết bị báo reading. Rỗng = CHẶN hết (fail closed),
    # không bao giờ là "mở cho tất cả" — xem comment ở /bins/{code}/readings.
    bin_device_key: str = ""

    # --- Ảnh và quyền riêng tư -------------------------------------------
    media_dir: str = "./data/media"
    media_max_edge_px: int = Field(default=512, ge=128)
    media_retention_days: int = Field(default=30, ge=1)
    face_blur_enabled: bool = True

    # --- Supabase Storage cho ảnh ----------------------------------------
    # MẶC ĐỊNH TẮT. Tắt thì ảnh vẫn nằm trên đĩa như hôm nay — không gãy gì.
    storage_enabled: bool = False
    supabase_url: str = ""
    # Khoá BÍ MẬT (service role). Bỏ qua Row Level Security nên CHỈ dùng ở máy
    # chủ; không bao giờ gửi xuống trình duyệt, không bao giờ ghi vào log.
    supabase_secret_key: str = ""
    supabase_publishable_key: str = ""
    supabase_bucket: str = "greenbin"

    # --- Kiểm soát chi phí ------------------------------------------------
    llm_batch_size: int = Field(default=25, ge=1, le=100)
    budget_limit_usd: float = Field(default=25.0, gt=0)
    llm_cache_dir: str = "./data/cache"

    # --- Database ---------------------------------------------------------
    database_url: str = "sqlite:///./data/app.db"
    chroma_persist_dir: str = "./data/chroma"
    cho_phep_ghi_db_xa: bool = False

    # Vision / classification (IoT compatibility)
    vision_model_name: str = "gpt-4o-mini"
    vision_base_url: str = ""
    stub_vision_label: str = "plastic"
    stub_vision_confidence: float = Field(default=0.91, ge=0.0, le=1.0)
    low_confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    hazard_labels: str = "battery,chemical,medical,sharps,e-waste,paint,aerosol"

    # IoT devices — "device_id:key" pairs, comma separated. Never commit real keys.
    iot_device_keys: str = ""

    # --- Langfuse: theo dõi hệ AI (P87, bước 1: chatbot + advise) ----------
    # MẶC ĐỊNH TẮT. Bật qua ``LANGFUSE_ENABLED=true`` trong ``.env``. Thiếu
    # khoá cũng coi như tắt — tuyệt đối không làm hỏng câu trả lời người dùng
    # chỉ vì Langfuse chết / hết ngạch / đứt mạng.
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    # Host Langfuse. Mặc định cloud; để trống cũng lấy cloud.langfuse.com.
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # --- Tiện ích ---------------------------------------------------------

    @property
    def is_openai_compatible(self) -> bool:
        """Provider hiện tại có dùng giao thức OpenAI không."""
        return self.vision_provider in OPENAI_COMPATIBLE_BASE_URLS

    @property
    def provider_base_url(self) -> str:
        return OPENAI_COMPATIBLE_BASE_URLS.get(self.vision_provider, "")

    @property
    def provider_api_key(self) -> str:
        """Key của provider mặc định chung. Theo tầng thì dùng :meth:`api_key_for`."""
        return self.api_key_for(self.vision_provider)

    def api_key_for(self, provider: str) -> str:
        """API key của một nhà cung cấp bất kỳ, không phụ thuộc provider đang chọn."""
        keys = {
            "openai": self.openai_api_key,
            "openrouter": self.openrouter_api_key,
            "nvidia": self.nvidia_api_key,
            "gemini": self.gemini_api_key,
            "deepseek": self.deepseek_api_key,
            "groq": self.groq_api_key,
            "mistral": self.mistral_api_key,
            "local_only": "",
        }
        return keys.get(provider, "")

    def base_url_for(self, provider: str) -> str:
        """Điểm cuối của provider dùng giao thức OpenAI. Rỗng nếu không phải."""
        return OPENAI_COMPATIBLE_BASE_URLS.get(provider, "")

    def resolve_provider(self, tier: ModelTier) -> str:
        """Nhà cung cấp phụ trách một tầng.

        Khai riêng trong ``.env`` thì lấy khai báo riêng, không thì lui về
        ``VISION_PROVIDER`` chung.
        """
        rieng = {
            "t1": self.vision_provider_t1,
            "t2": self.vision_provider_t2,
            "text": self.vision_provider_text,
        }
        return (rieng[tier] or self.vision_provider).strip()

    def resolve_model_for(self, tier: ModelTier) -> str:
        """Tên model của một tầng, theo đúng provider phụ trách tầng đó.

        Thứ tự ưu tiên: tên model khai thẳng trong ``.env`` → mặc định của
        provider phụ trách tầng.
        """
        khai_bao = {"t1": self.vision_model_t1, "t2": self.vision_model_t2, "text": self.text_model}[tier]
        if khai_bao:
            return khai_bao
        defaults = PROVIDER_DEFAULT_MODELS.get(self.resolve_provider(tier), ("", "", ""))
        return defaults[_TIER_INDEX[tier]]

    def resolve_models(self) -> tuple[str, str, str]:
        """``(model_t1, model_t2, model_text)`` — lớp bọc quanh :meth:`resolve_model_for`."""
        return (self.resolve_model_for("t1"), self.resolve_model_for("t2"), self.resolve_model_for("text"))

    def resolve_embedding_provider(self) -> str:
        """Nhà cung cấp lo phần embedding của RAG."""
        return (self.embedding_provider or self.vision_provider).strip()

    def resolve_embedding_model(self) -> str:
        """Model embedding. Rỗng nghĩa là provider đó không dùng được → RAG chạy thuần BM25."""
        if self.embedding_model:
            return self.embedding_model
        return PROVIDER_DEFAULT_EMBEDDING_MODELS.get(self.resolve_embedding_provider(), "")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Xoá cache cấu hình. Dùng trong test khi đổi biến môi trường."""
    get_settings.cache_clear()
