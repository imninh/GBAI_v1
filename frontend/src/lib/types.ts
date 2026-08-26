/** Kiểu dữ liệu khớp hợp đồng API ở `docs/FRONTEND_SPEC.md` mục 7.
 *
 *  Đổi tên trường ở đây thì phải sửa cả backend — hai bên là một bản cam kết.
 */

import type { TrangThaiYeuCau } from "./pickup-states";

export type Role = "resident" | "cleaner" | "manager";

export interface User {
  id: number;
  full_name: string;
  email: string;
  role: Role;
  unit: string;
  building: string;
  building_id: number | null;
  /** Toạ độ toà nhà đăng ký. NULL khi người dùng chưa gắn căn hộ. */
  building_lat: number | null;
  building_lng: number | null;
  green_points: number;
}

export type Permissions = Record<string, { allowed: boolean; reason: string }>;

export interface WasteCategory {
  code: string;
  name: string;
  parent_code: string;
  is_hazardous: boolean;
  min_confidence: number;
  bin_color: string;
  icon: string;
  handling_note: string;
  safety_warning: string;
}

export interface AdviceSource {
  chunk_id: number;
  doc_id: number;
  doc_title: string;
  doc_type: string;
  section: string;
  quote: string;
  source: string;
  needs_verification: boolean;
  score: number;
}

export interface Classification {
  classification_id: number;
  media_id: number | null;
  input_type: "image" | "text";
  text_query: string;
  item_name: string;
  category: WasteCategory | null;
  confidence: number;
  min_confidence: number;
  confidence_level: "chac_chan" | "kha_chac" | "duoi_nguong";
  tier: string;
  tier_label_vi: string;
  model: string;
  refused: boolean;
  refusal_reason: string;
  refusal_label_vi: string;
  refusal_headline_vi?: string;
  escalated_to_human: boolean;
  escalation_reason?: string;
  items: { name: string; category_code: string; confidence: number }[];
  advice: string;
  advice_sources: AdviceSource[];
  safety_warning: string;
  safety_warning_note: string;
  degraded: boolean;
  degraded_note: string;
  human_label: WasteCategory | null;
  verified_by: number | null;
  latency_ms: number;
  cost_usd: number;
  run_id: number | null;
  is_seed: boolean;
  created_at: string;
  guess?: { item_name: string; category_code: string } | null;
  hard_block?: { code: string; label_vi: string; instruction_vi: string } | null;
  schedule_hint?: ScheduleHint;
}

export interface ScheduleHint {
  la_do_cong_kenh?: boolean;
  lich_thu_gom?: { weekdays: number[]; window: string; location: string; category_code: string }[];
  khung_gio_da_co_chuyen?: {
    service_date: string;
    window: string;
    so_diem_dung: number;
    ghi_chu: string;
  }[];
}

export interface PrivacyReport {
  media_id: number;
  exif_stripped: boolean;
  removed_fields: { field: string; label_vi: string; value_before: string }[];
  faces_blurred: number;
  original_size: { width: number; height: number; bytes: number };
  processed_size: { width: number; height: number; bytes: number };
  expires_at: string | null;
  has_original: boolean;
}

export interface ThresholdHit {
  rule: string;
  label_vi: string;
  value: number;
  threshold: number;
}

export interface PickupRequest {
  id: number;
  resident: { id: number; full_name: string } | null;
  unit: string;
  building: string;
  building_code: string;
  items: { name: string; category_code: string; qty: number; media_id: number | null }[];
  weight_min_kg: number;
  weight_max_kg: number;
  est_weight_kg: number;
  preferred_date: string | null;
  preferred_window: string;
  note: string;
  requires_hitl: boolean;
  threshold_hit: ThresholdHit[];
  status: TrangThaiYeuCau;
  reject_reason: string;
  review_note: string;
  // Khối lượng THẬT do đội vệ sinh cân — backend trả từ gói P29/P32
  // (serializers.pickup_dict). Tuỳ chọn vì bản rút gọn có thể thiếu.
  weight_confirmed_kg?: number | null;
  confirmed_by?: number | null;
  confirmed_at?: string | null;
  is_seed: boolean;
  created_at: string;
  message_vi?: string;
  timeline?: { kind: string; label_vi: string; at: string; detail: Record<string, unknown> }[];
  route?: { id: number; service_date: string; window: string; status: string; stop_count: number; saved_trips: number } | null;
  resident_history?: { so_yeu_cau_truoc: number; so_lan_hoan_thanh: number; so_lan_huy: number };
  building_context?: { so_yeu_cau: number; tong_khoi_luong_kg: number };
  capacity_context?: { ngay_mong_muon: string; so_yeu_cau_cung_ngay: number; tai_trong_xe_kg: number };
  agent_suggestion?: { label_vi: string; text_vi: string; so_yeu_cau_gop?: number; tong_khoi_luong_kg?: number };
}

export interface RouteStop {
  stop_id: number;
  seq: number;
  /** `yeu_cau` = kiện cồng kềnh của cư dân; `thung` = thùng đầy cần đổ. */
  stop_kind: "yeu_cau" | "thung";
  /** NULL với điểm dừng loại `thung` — luôn chặn trước khi dùng. */
  request_id: number | null;
  bin_id: number | null;
  /** Tên đọc được của điểm dừng; backend đã gộp sẵn cả hai loại. */
  diem_dung_vi: string;
  dia_chi: string;
  /** Mức rác lúc đề xuất tuyến; NULL với điểm dừng loại `yeu_cau`. */
  fill_percent: number | null;
  unit: string;
  resident_name: string;
  phone_masked: string;
  weight_max_kg: number;
  items: { name: string; qty: number }[];
  done_at: string | null;
  issue: string;
  issue_note: string;
  actual_weight_kg: number | null;
  lat?: number | null;
  lng?: number | null;
}

export interface RouteReasoning {
  criteria: string[];
  excluded: { request_id: string; unit: string; ly_do: string }[];
  baseline_km: number;
  saved_km: number;
  saved_trips: number;
  capacity_kg: number;
  note?: string;
  edited_by_human?: boolean;
}

/** So sánh bản agent đề xuất với bản người duyệt đã chốt.
 *
 * ⚠️ Chỉ tính điểm dừng loại `yeu_cau`: bản agent đề xuất là danh sách
 * `request_id`, mà điểm dừng loại `thung` không có `request_id`. Giao diện phải
 * nói rõ điều này thay vì để người xem tự suy ra sai.
 *
 * Lưu ý khi hiển thị: `reordered` của backend chỉ đúng khi KHÔNG có điểm nào bị
 * bỏ (nó đòi `sorted(proposed) == sorted(current)`). Muốn kể đủ chuyện khi vừa
 * bỏ vừa đổi thứ tự thì phải so `proposed`/`final` ngay trên giao diện, đừng chỉ
 * dựa vào cờ này.
 */
export type RouteDiff = {
  proposed: number[];
  final: number[];
  removed: number[];
  reordered: boolean;
  changed: boolean;
};

export interface PickupRoute {
  id: number;
  service_date: string;
  window: string;
  status: "proposed" | "approved" | "in_progress" | "done" | "cancelled";
  total_weight_kg: number;
  est_distance_km: number;
  stop_count: number;
  team: { id: number; full_name: string } | null;
  is_seed: boolean;
  created_at: string;
  stops?: RouteStop[];
  reasoning?: RouteReasoning;
  proposed_stop_order?: number[];
  diff?: RouteDiff;
  /** Hình đường đi thật từ OSRM, `[lat, lng]` theo đúng thứ tự ghé.
   *  `null` khi cờ `ROUTE_REAL_DISTANCE` tắt hoặc chưa tính được — khi đó bản
   *  đồ vẽ nét đứt như cũ. Khoá LUÔN có mặt trong payload (gói P26). */
  duong_di?: [number, number][] | null;
  /** Metadata chi tiết lộ trình đường thật từ OSRM (tổng km, tổng phút, từng chặng). */
  lo_trinh_meta?: LoTrinhMeta | null;
  message_vi?: string;
}

export interface LoTrinhLeg {
  from_seq: number;
  to_seq: number;
  distance_km: number;
  duration_minutes: number;
}

export interface LoTrinhMeta {
  total_km: number;
  total_minutes: number;
  legs: LoTrinhLeg[];
}

export interface NavigationResult {
  polyline: [number, number][];
  distance_km: number;
  duration_minutes: number;
}

/** Trạng thái thật của ba cơ chế mới — trang Vận hành nói thật về giới hạn. */
export interface CoChe {
  rate_limit_dang_ky: { bat: boolean; so_lan: number; cua_so_giay: number };
  khoa_thiet_bi: { so_thung_khoa_rieng: number; tong_thung: number };
  duong_di_that: { bat: boolean; dich_vu: string };
}

export interface OpsMetrics {
  cost: {
    total: number;
    count: number;
    cost_per_1000: number;
    by_tier: {
      tier: string;
      label_vi: string;
      share: number;
      count: number;
      cost_usd: number;
      cost_per_item: number;
      /** false = model của tầng này chưa có trong bảng giá, nên $0 nghĩa là "chưa biết". */
      price_known: boolean;
      accuracy: number | null;
      p95_latency_ms: number;
    }[];
    by_day: { date: string; cost_usd: number }[];
    baseline_full_model: number;
    baseline_model: string;
    baseline_price_known: boolean;
    saved_usd: number;
    saved_ratio: number;
    budget: { used: number; limit: number };
  };
  latency: { by_node: { node: string; p50: number; p95: number }[]; end_to_end: { p50: number; p95: number } };
  errors: {
    rate: number;
    by_node: { node: string; rate: number; errors: number; total: number }[];
    recent: { node: string; error_type: string; retries: number; run_id: number }[];
    rate_limit_hits: number;
  };
  routing: {
    cache_hit_rate: number;
    local_model_rate: number;
    escalation_rate: number;
    refusal_rate: number;
    total_classifications: number;
  };
  provider: {
    provider: string;
    has_api_key: boolean;
    model_t1: string;
    model_t2: string;
    model_text: string;
    /** Mỗi tầng có thể chạy trên một nhà cung cấp khác nhau. */
    tiers: { tier: string; label_vi: string; provider: string; model: string; has_api_key: boolean }[];
    single_provider: boolean;
    local_model_enabled: boolean;
    local_model_loaded: boolean;
    /** "onnx" = bản nén chạy trên máy chủ · "torch" = bản đầy đủ · "" = chưa nạp. */
    local_model_runtime: string;
    prompt_version: string;
  };
  retrieval: {
    /** "hybrid" = BM25 + embedding · "bm25" = thuần từ khoá. */
    che_do: string;
    chunks_co_embedding: number;
    chunks_tong: number;
    embedding_provider: string;
    embedding_model: string;
    vector_weight: number;
  };
  known_limitations: string[];
  has_seed_data: boolean;
  seed_count: number;
  seed_note: string;
  /** Tuỳ chọn: bản deploy cũ chưa trả khối này thì trang vẫn render bình thường. */
  co_che?: CoChe;
}

export interface EvalSummary {
  safety: { hazard_missed_count: number; hazard_total: number; target: number; label_vi: string };
  accuracy: number | null;
  verified_count: number;
  hazard_recall: number | null;
  confusion_matrix: Record<string, Record<string, number>>;
  by_dataset: {
    dataset: string;
    test_size: number;
    /** Các cột eval trong CSDL đều có thể NULL (chưa chạy eval cho bộ đó). */
    accuracy: number | null;
    macro_f1: number | null;
    hazard_recall: number | null;
    hazard_missed_count: number | null;
    retrieval_precision_at_5: number | null;
    prompt_version: string;
    avg_cost_usd: number | null;
    p95_latency_ms: number | null;
    is_seed: boolean;
  }[];
  failures: {
    id: number;
    media_id: number | null;
    item_name: string;
    true_category_code: string;
    predicted_category_code: string;
    confidence: number;
    cause: string;
    resolved: boolean;
    is_seed: boolean;
  }[];
  has_seed_data: boolean;
}

export interface Overview {
  queues: { pickup: number; labels: number; routes: number; total: number };
  classifications_this_week: number;
  classifications_last_week: number;
  growth: number | null;
  accuracy: number | null;
  verified_count: number;
  safety: { hazard_missed_count: number; hazard_total: number; target: number; label_vi: string };
  category_distribution: { code: string; name: string; bin_color: string; count: number; share: number }[];
  routing_efficiency: { so_yeu_cau: number; so_chuyen: number; giam_so_chuyen: number; tiet_kiem_km: number };
  alerts: { id: number; severity: string; title: string; threshold: string; triggered_at: string; ack: boolean }[];
  /** Tuỳ chọn: bản deploy cũ chưa trả khối này thì trang vẫn render bình thường. */
  co_che?: CoChe;
}

export interface AgentRunDetail {
  id: number;
  kind: string;
  status: string;
  duration_ms: number;
  total_cost_usd: number;
  started_at: string;
  nodes: {
    node: string;
    status: string;
    duration_ms: number;
    tokens_in: number;
    tokens_out: number;
    cost_usd: number;
    cache_hits: number;
    llm_calls: number;
    error_type: string;
    meta: Record<string, unknown>;
  }[];
  graph: { nodes: { id: string; label: string }[]; edges: { from: string; to: string; label: string }[] };
  path: string[];
}

export interface ApiErrorBody {
  error: { code: string; message_vi: string; detail: Record<string, unknown> };
}

// --- Chatbot RAG ---
export interface ChatbotSource {
  doc_title: string;
  section: string;
  quote: string;
  doc_type: string;
  source: string;
  score: number;
}

export interface ViableBinCard {
  id: number;
  code: string;
  name: string;
  address: string;
  category_codes: string[];
  category_names: string[];
  fill_percent: number;
  battery_percent: number;
  status: string;
  status_label_vi: string;
  is_viable: boolean;
  distance_meters: number | null;
  lat: number | null;
  lng: number | null;
}

export interface ChatbotResponse {
  answer: string;
  intent: "waste_law" | "bin_query" | "app_guide" | "out_of_scope";
  confidence_level: "High" | "Medium" | "Low";
  confidence_score: number;
  source_badge: string;
  sources: ChatbotSource[];
  viable_bins: ViableBinCard[];
  fallback_level: number;
  generated_by: string;
  tokens_used: number;
  cost_usd: number;
}

// --- Phiên bỏ rác tại thùng ---

/** Một phiên bỏ rác tại thùng thông minh. Mở bằng mã QR đọc từ tham số `?ma=`
 *  của link in trên thùng — app chỉ DÙNG mã, việc xin mã là của thiết bị. */
export interface PhienBoRac {
  ma_phien: string;
  trang_thai: string;
  so_vat: number;
  /** Điểm nhận thức tạm tính của phiên — xem cảnh báo ở `TongQuanDiemNhanThuc`. */
  diem_nhan_thuc: number;
  bat_dau: string;
  ket_thuc: string | null;
  /** Mốc hết hạn phiên (UTC ISO) — server tính từ bat_dau + 10 phút. */
  het_han_luc: string;
}

// --- Điểm nhận thức & nhiệm vụ ---

/** ⚠️ ĐIỂM NHẬN THỨC — KHÔNG PHẢI ĐIỂM XANH.
 *
 *  Điểm nhận thức chỉ phục vụ xếp hạng và huy hiệu trong app, **không đổi được
 *  quà**. Điểm xanh (`User.green_points`) mới là điểm cân thật, có giá trị đổi
 *  quà. Hai loại điểm sống ở hai bảng khác nhau và không bao giờ cộng dồn —
 *  đừng gộp chúng vào một kiểu chung hay một biến đếm duy nhất.
 */
export interface DongSoCaiDiemNhanThuc {
  nguon: string;
  diem: number;
  ref_bang: string;
  /** Bảng nguồn có thể không định danh dòng cụ thể → null. */
  ref_id: number | null;
  ngay: string;
  ghi_chu: string;
  created_at: string;
}

export interface TongQuanDiemNhanThuc {
  tong_diem_nhan_thuc: number;
  hom_nay: string;
  gan_day: DongSoCaiDiemNhanThuc[];
}

/** Chu kỳ của một nhiệm vụ nhận thức: theo ngày hoặc theo tuần ISO. */
export type ChuKyNhiemVu = "ngay" | "tuan";

export interface NhiemVuDiemNhanThuc {
  ma: string;
  ten: string;
  mo_ta: string;
  chu_ky: ChuKyNhiemVu;
  dieu_kien_ma: string;
  dieu_kien_nguong: number;
  diem: number;
  tien_do: number;
  da_nhan: boolean;
}

export interface DanhSachNhiemVu {
  ngay: string;
  items: NhiemVuDiemNhanThuc[];
}

/** Một nhiệm vụ vừa được trao điểm trong lần bấm "kiểm nhiệm vụ". */
export interface NhiemVuVuaHoanThanh {
  ma: string;
  ten: string;
  diem: number;
  /** Kỳ trao điểm: `YYYY-MM-DD` (theo ngày) hoặc `YYYY-Www` ISO (theo tuần). */
  ky: string;
  tien_do: number;
}

export interface KetQuaKiemNhiemVu {
  ngay: string;
  da_hoan_thanh: NhiemVuVuaHoanThanh[];
  tong_diem_nhan_thuc: number;
}

// --- Kíp thu gom ---

/** Nhân viên thu gom khả dụng để xếp kíp. Backend CỐ Ý chỉ trả ba trường này —
 *  không trả số điện thoại, không trả email; đừng khai thêm. */
export interface NhanVienKhaDung {
  id: number;
  full_name: string;
  role: string;
}

export interface ThanhVienKip {
  id: number;
  full_name: string;
  vai_tro: "truong_kip" | "thanh_vien";
}

export interface DanhSachKip {
  items: ThanhVienKip[];
}

export interface GanKipPayload {
  user_ids: number[];
  /** Bỏ trống thì trưởng kíp là người đầu tiên trong `user_ids`. */
  truong_kip_id?: number | null;
}

export interface KetQuaGanKip {
  route_id: number;
  user_ids: number[];
  truong_kip_id: number;
}

/** Kết quả lên lịch cả tuần — đếm số liệu để trang báo cáo nói thật. */
export interface KetQuaTaoLichTuan {
  so_ngay_xet: number;
  so_chuyen_tao: number;
  so_chuyen_da_gan_kip: number;
  so_chuyen_chua_gan_kip: number;
  so_lich_bo_vi_da_co: number;
  so_lich_bo_vi_khong_yeu_cau: number;
}

// --- Sự cố thu gom ---

export type TrangThaiSuCoThuGom = "cho_xu_ly" | "da_xu_ly" | "tu_choi";

export interface SuCoThuGom {
  id: number;
  route_id: number;
  stop_id: number | null;
  nguoi_bao_id: number;
  /** Mã loại sự cố, tối đa 40 ký tự — nhãn hiển thị lấy từ enum phía màn hình. */
  loai: string;
  mo_ta: string;
  anh_media_id: number | null;
  trang_thai: TrangThaiSuCoThuGom;
  nguoi_xu_ly_id: number | null;
  ghi_chu_xu_ly: string;
  xu_ly_luc: string | null;
  created_at: string | null;
}

export interface BaoSuCoPayload {
  route_id: number;
  stop_id?: number | null;
  loai: string;
  mo_ta?: string;
  anh_media_id?: number | null;
}

export interface XuLySuCoPayload {
  chap_nhan: boolean;
  ghi_chu?: string;
}
