/** Lớp gọi API. Mọi lỗi đều được quy về `ApiError` có `message_vi` và `code`
 *  để màn hình nào cũng hiện được câu tiếng Việt dễ hiểu kèm mã tra log.
 */

import type { Bin, BinReading, BinStats, DiemGui, NhanVien } from "./bins";
import { nenAnh } from "./nen_anh";
import type {
  AgentRunDetail,
  ChatbotResponse,
  Classification,
  EvalSummary,
  NavigationResult,
  OpsMetrics,
  Overview,
  Permissions,
  PickupRequest,
  PickupRoute,
  PrivacyReport,
  User,
  WasteCategory,
} from "./types";

/** Địa chỉ backend, **đã cắt dấu `/` thừa ở cuối**.
 *
 * Người điền biến môi trường trên Vercel gần như luôn dán kèm dấu `/` cuối, và
 * chuỗi nối thẳng khi đó sinh ra `https://host//api/v1/auth/me` — Starlette coi
 * đó là đường dẫn khác nên trả 404 cho **toàn bộ** API, kể cả lệnh khôi phục
 * phiên lúc mở app. `redirect_slashes` của FastAPI chỉ lo dấu `/` thừa ở cuối
 * đường dẫn, không lo dấu thừa ở đầu. Chuẩn hoá ngay tại nguồn thì lần sau ai
 * dán kiểu gì cũng không hỏng.
 */
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const TOKEN_KEY = "greenbin_token";

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(messageVi: string, code: string, status: number) {
    super(messageVi);
    this.code = code;
    this.status = status;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers });
  } catch {
    // Hầm để xe và khu thùng rác sóng rất yếu — đây là bối cảnh sử dụng thật.
    throw new ApiError("Không kết nối được tới máy chủ. Thử lại khi có mạng nhé.", "NET-503", 0);
  }

  if (!response.ok) {
    let code = `HTTP-${response.status}`;
    let message = "Có lỗi xảy ra, bạn thử lại giúp mình nhé.";
    try {
      const body = await response.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message_vi ?? message;
      }
    } catch {
      /* giữ nguyên câu mặc định */
    }
    throw new ApiError(message, code, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Đường dẫn ảnh — luôn qua endpoint có kiểm quyền, kèm token trong query
 *  chỉ khi thẻ `<img>` không gửi được header. */
export function mediaUrl(mediaId: number): string {
  return `${API_URL}/api/v1/media/${mediaId}`;
}

export const api = {
  // --- Auth ---
  login: (email: string, password: string) =>
    request<{ token: string; user: User; permissions: Permissions }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  /** Đăng nhập bằng số điện thoại. Cùng một endpoint với `login`, chỉ khác
   *  trường gửi lên — tách làm hai hàm để chỗ gọi không phải tự đoán. Server tự
   *  chuẩn hoá "0912 345 678" và "+84912345678", client không cần xử lý chuỗi. */
  loginPhone: (phone: string, password: string) =>
    request<{ token: string; user: User; permissions: Permissions }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ phone, password }),
    }),
  /** Đăng ký cư dân mới. Server LUÔN gán vai trò `resident` và tự sinh email nội
   *  bộ — đừng gửi `role`, `email` hay `green_points`, chúng bị bỏ qua. */
  register: (payload: { phone: string; password: string; full_name: string; unit_id?: number | null }) =>
    request<{ token: string; user: User; permissions: Permissions }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  me: () => request<{ user: User; permissions: Permissions }>("/auth/me"),
  /** Sửa hồ sơ của chính mình. Không gửi `unit_id` nghĩa là giữ nguyên căn hộ;
   *  muốn bỏ căn hộ phải gửi `xoa_can_ho: true`. */
  updateMe: (payload: { full_name?: string; unit_id?: number; xoa_can_ho?: boolean }) =>
    request<{ user: User; permissions: Permissions }>("/auth/me", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  /** Lịch sử theo vật liệu của chính mình. CỐ TÌNH không có kg theo từng vật
   *  liệu — cân nặng chỉ ước lượng ở mức cả yêu cầu, xem `ghi_chu`. */
  meHistory: () =>
    request<{
      tong: {
        so_yeu_cau: number;
        so_yeu_cau_da_thu: number;
        khoi_luong_min_kg: number;
        khoi_luong_max_kg: number;
      };
      theo_vat_lieu: {
        category_code: string;
        category_name: string;
        bin_color: string;
        icon: string;
        so_mon: number;
        so_yeu_cau: number;
        so_lan_hoi: number;
      }[];
      ghi_chu: string;
    }>("/auth/me/history"),
  demoAccounts: () =>
    request<{
      password: string;
      accounts: { email: string; full_name: string; role: string; unit: string; description: string }[];
      notice: string;
    }>("/auth/demo-accounts"),

  // --- Phân loại ---
  classifyText: (textQuery: string, buildingId?: number | null) =>
    request<Classification>("/classify/text", {
      method: "POST",
      body: JSON.stringify({ text_query: textQuery, building_id: buildingId ?? null }),
    }),
  classifyImage: async (file: File, buildingId?: number | null) => {
    const form = new FormData();
    // Nén ngay trên máy người dùng trước khi gửi — ảnh 3–6 MB xuống ~250–400 KB.
    form.append("image", await nenAnh(file));
    if (buildingId) form.append("building_id", String(buildingId));
    return request<Classification>("/classify", { method: "POST", body: form });
  },
  classifications: (params: Record<string, string | number | boolean> = {}) =>
    request<{ items: Classification[]; total: number }>(`/classifications?${new URLSearchParams(
      Object.entries(params).map(([k, v]) => [k, String(v)]),
    )}`),
  classification: (id: number) => request<Classification>(`/classifications/${id}`),
  feedback: (id: number, isCorrect: boolean, suggested = "") =>
    request<{ ok: boolean }>(`/classifications/${id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ is_correct: isCorrect, suggested_category_code: suggested }),
    }),
  verifyQueue: () =>
    request<{ items: Classification[]; total: number; hard_cases: { pair: string; note: string }[] }>("/verify-queue"),
  verifyLabel: (id: number, categoryCode: string, replyText = "") =>
    request<Classification>(`/classifications/${id}/verify`, {
      method: "POST",
      body: JSON.stringify({ category_code: categoryCode, reply_text: replyText }),
    }),

  // --- Ảnh ---
  privacy: (mediaId: number) => request<PrivacyReport>(`/media/${mediaId}/privacy`),
  deleteMedia: (mediaId: number) => request<{ ok: boolean }>(`/media/${mediaId}`, { method: "DELETE" }),
  /** Tải một ảnh (server tước EXIF + làm mờ mặt + nén), trả media_id để đính vào
   *  món của yêu cầu thu gom. Nén sẵn trên máy trước khi gửi. */
  uploadMedia: async (file: File) => {
    const form = new FormData();
    form.append("image", await nenAnh(file));
    return request<{ media_id: number }>("/media", { method: "POST", body: form });
  },

  // --- Danh mục ---
  categories: () => request<{ items: WasteCategory[] }>("/categories"),
  buildings: () => request<{ items: { id: number; code: string; name: string }[] }>("/buildings"),
  units: (buildingId: number) =>
    request<{ items: { id: number; code: string; building_id: number }[] }>(`/buildings/${buildingId}/units`),
  schedule: (buildingId: number) =>
    request<{
      building: { id: number; code: string; name: string };
      items: {
        category_code: string;
        category_name: string;
        bin_color: string;
        icon: string;
        weekdays: number[];
        weekdays_vi: string[];
        window: string;
        location: string;
      }[];
    }>(`/buildings/${buildingId}/schedule`),
  knowledge: (params: Record<string, string | number> = {}) =>
    request<{ items: { id: number; title: string; doc_type: string; chunk_count: number; needs_verification: boolean }[] }>(
      `/knowledge?${new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))}`,
    ),
  chunk: (id: number) =>
    request<{ id: number; content: string; section: string; needs_verification: boolean; doc: { title: string; source: string } | null }>(
      `/knowledge/chunks/${id}`,
    ),
  enums: () =>
    request<{
      pickup_reject_reasons: { code: string; label_vi: string }[];
      stop_issues: { code: string; label_vi: string }[];
      known_limitations: string[];
      weekdays_vi: string[];
    }>("/meta/enums"),

  // --- Thu gom ---
  createPickup: (payload: Record<string, unknown>) =>
    request<PickupRequest>("/pickups", { method: "POST", body: JSON.stringify(payload) }),
  pickups: (params: Record<string, string | number> = {}) =>
    request<{ items: PickupRequest[]; total: number; reject_reasons: { code: string; label_vi: string }[] }>(
      `/pickups?${new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))}`,
    ),
  /** Yêu cầu đã duyệt, đang chờ xếp tuyến — nguyên liệu của màn Xếp tuyến. */
  pickupsChoNhan: () =>
    request<{ items: PickupRequest[]; total: number; reject_reasons: { code: string; label_vi: string }[] }>(
      "/pickups?status=cho_nhan",
    ),
  pickup: (id: number) => request<PickupRequest>(`/pickups/${id}`),
  reviewPickup: (id: number, payload: Record<string, unknown>) =>
    request<PickupRequest>(`/pickups/${id}/review`, { method: "POST", body: JSON.stringify(payload) }),
  cancelPickup: (id: number) => request<PickupRequest>(`/pickups/${id}`, { method: "DELETE" }),
  chuyenTrangThaiYeuCau: (id: number, den: string, ghiChu = "") =>
    request<PickupRequest>(`/pickups/${id}/chuyen-trang-thai`, {
      method: "POST",
      body: JSON.stringify({ den, ghi_chu: ghiChu }),
    }),
  xacNhanKhoiLuong: (id: number, weightKg: number) =>
    request<PickupRequest>(`/pickups/${id}/xac-nhan-khoi-luong`, {
      method: "POST",
      body: JSON.stringify({ weight_confirmed_kg: weightKg }),
    }),

  // --- Tuyến ---
  /** Gộp các yêu cầu chờ xếp tuyến thành một tuyến đề xuất. Kết quả luôn ở
   *  trạng thái ``proposed`` — màn Duyệt tuyến mới có quyền chốt. */
  proposeRoute: (payload: {
    service_date: string;
    window: string;
    team_id?: number | null;
    capacity_kg?: number | null;
  }) =>
    request<PickupRoute>("/routes/propose", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** Hình đường đi thật (OSRM) nối mốc → điểm gửi. `duong_di` null khi backend
   *  tắt OSRM hoặc gọi hỏng — khi đó vẽ đường thẳng như cũ. */
  duongDiToiDiem: (diem: { lat: number; lng: number }[]) =>
    request<{ duong_di: [number, number][] | null }>("/routes/duong-di", {
      method: "POST",
      body: JSON.stringify({ diem }),
    }),
  /** Lộ trình dẫn đường từ vị trí xe/người dùng tới điểm dừng qua OSRM */
  navigate: (origin: { lat: number; lng: number }, dest: { lat: number; lng: number }) =>
    request<NavigationResult>("/routes/navigate", {
      method: "POST",
      body: JSON.stringify({
        origin_lat: origin.lat,
        origin_lng: origin.lng,
        dest_lat: dest.lat,
        dest_lng: dest.lng,
      }),
    }),
  routes: (params: Record<string, string> = {}) =>
    request<{ items: PickupRoute[] }>(`/routes?${new URLSearchParams(params)}`),
  route: (id: number) => request<PickupRoute>(`/routes/${id}`),
  reviewRoute: (id: number, payload: Record<string, unknown>) =>
    request<PickupRoute>(`/routes/${id}/review`, { method: "POST", body: JSON.stringify(payload) }),
  completeStop: (routeId: number, stopId: number, payload: Record<string, unknown> = {}) =>
    request<PickupRoute>(`/routes/${routeId}/stops/${stopId}/done`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // --- Vận hành ---
  overview: () => request<Overview>("/overview"),
  opsMetrics: () => request<OpsMetrics>("/ops/metrics"),
  evalSummary: () => request<EvalSummary>("/eval/summary"),
  runs: () => request<{ items: { id: number; kind: string; status: string; duration_ms: number; total_cost_usd: number; started_at: string }[] }>("/runs"),
  run: (id: number) => request<AgentRunDetail>(`/runs/${id}`),
  notifications: () =>
    request<{ items: { id: number; title: string; body: string; created_at: string }[]; unread: number }>("/notifications"),

  // --- Thùng thu gom ---
  // Ba endpoint đọc; đường ghi (`POST /bins/{code}/readings`) xác thực bằng khoá
  // thiết bị nên **không gọi từ trình duyệt** — để lộ khoá ra client là mở toang
  // cổng ghi số liệu điều phối. Việc bơm số liệu do `scripts/device_simulator.py`
  // làm ở phía máy chủ.
  bins: (onlyNeedsCollection = false) =>
    request<{ items: Bin[] }>(`/bins?only_needs_collection=${onlyNeedsCollection}`),
  diemGui: () => request<{ items: DiemGui[] }>("/bins/diem-gui"),
  binStats: () => request<BinStats>("/bins/stats"),
  bin: (code: string, readingsLimit = 20) =>
    request<Bin & { readings: BinReading[] }>(`/bins/${encodeURIComponent(code)}?readings_limit=${readingsLimit}`),
  /** Nhân viên có thể nhận thùng. Chỉ ban quản lý gọi được — vai khác nhận 403,
   *  nên chỗ gọi phải kiểm quyền TRƯỚC thay vì bắt lỗi 403 làm luồng bình thường. */
  nhanVien: () => request<{ items: NhanVien[] }>("/bins/nhan-vien"),
  /** Giao thùng cho một nhân viên. Truyền `null` để **bỏ giao** — server phân
   *  biệt `null` (bỏ giao) với một id, đừng gửi `0`. */
  ganThung: (code: string, cleanerId: number | null) =>
    request<{ code: string; assigned_cleaner_id: number | null; assigned_cleaner_name: string }>(
      `/bins/${encodeURIComponent(code)}/nhan-vien`,
      { method: "PATCH", body: JSON.stringify({ cleaner_id: cleanerId }) },
    ),

  // --- Chatbot RAG ---
  chatbotAsk: (payload: { question: string; building_id?: number | null; lat?: number | null; lng?: number | null }) =>
    request<ChatbotResponse>("/chatbot/ask", { method: "POST", body: JSON.stringify(payload) }),
  chatbotFeedback: (payload: { question: string; answer: string; intent: string; rating: number; comment?: string }) =>
    request<{ status: string; message: string }>("/chatbot/feedback", { method: "POST", body: JSON.stringify(payload) }),
  chatbotSuggestions: () =>
    request<{ suggestions: { category: string; label: string; question: string }[] }>("/chatbot/suggested-questions"),
};
