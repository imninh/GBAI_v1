/** Từ vựng trạng thái của một yêu cầu thu gom (PickupRequest).

 *  Định nghĩa **một lần duy nhất ở đây** và tái dùng ở mọi màn hình — không rải
 *  chuỗi tiếng Việt trạng thái rải rác trong component. Khớp với
 *  ``NHAN_VI`` / ``CHUYEN_TIEP`` ở ``src/services/pickup_lifecycle.py``.
 *
 *  ⚠️ Đây là máy trạng thái của YÊU CẦU, không phải của TUYẾN
 *  (``PickupRoute.status`` giữ nguyên ``proposed | approved | in_progress |
 *  done | cancelled`` và **không** nằm trong bảng này).
 */

export type TrangThaiYeuCau =
  | "cho_duyet"
  | "cho_nhan"
  | "da_nhan"
  | "dang_van_chuyen"
  | "da_giao_don_vi"
  | "hoan_tat"
  | "tranh_chap"
  | "tu_choi"
  | "da_huy";

export const NHAN_TRANG_THAI_YEU_CAU: Record<TrangThaiYeuCau, string> = {
  cho_duyet: "Chờ duyệt",
  cho_nhan: "Chờ nhận",
  da_nhan: "Đã nhận",
  dang_van_chuyen: "Đang vận chuyển",
  da_giao_don_vi: "Đã giao đơn vị",
  hoan_tat: "Hoàn tất",
  tranh_chap: "Tranh chấp",
  tu_choi: "Từ chối",
  da_huy: "Đã huỷ",
};

/** Bước đi hợp lệ tiếp theo của đội vệ sinh, theo đúng ``CHUYEN_TIEP``.
 *  Trạng thái không có bước đi (terminal, hoặc chờ đơn vị xác nhận) là ``null``. */
export const BUOC_KE_TIEP: Record<TrangThaiYeuCau, { den: TrangThaiYeuCau; nhan: string } | null> = {
  cho_duyet: null,
  cho_nhan: { den: "da_nhan", nhan: "Nhận kiện" },
  da_nhan: { den: "dang_van_chuyen", nhan: "Bắt đầu vận chuyển" },
  dang_van_chuyen: { den: "da_giao_don_vi", nhan: "Đã giao đơn vị" },
  da_giao_don_vi: null,
  hoan_tat: null,
  tranh_chap: null,
  tu_choi: null,
  da_huy: null,
};

export function trangThaiYeuCau(label: string): TrangThaiYeuCau | null {
  return label in NHAN_TRANG_THAI_YEU_CAU ? (label as TrangThaiYeuCau) : null;
}

// --- GOI_P0 — gộp 9 trạng thái PickupRequest về 5 nhóm HIỂN THỊ (không đổi
//     máy trạng thái backend; chỉ lớp trình bày). Chuỗi vận chuyển cồng kềnh
//     (Nhận→Vận chuyển→Giao đơn vị) giữ làm THANH TIẾN ĐỘ CON trong nhóm ③. ---

export type NhomHienThi = "can_lam" | "da_nhan" | "dang_xu_ly" | "da_xong" | "co_van_de";

export const NHAN_NHOM: Record<NhomHienThi, string> = {
  can_lam: "Cần làm",
  da_nhan: "Đã nhận",
  dang_xu_ly: "Đang xử lý",
  da_xong: "Đã xong",
  co_van_de: "Có vấn đề",
};

export const NHOM_CUA_YEU_CAU: Record<TrangThaiYeuCau, NhomHienThi> = {
  cho_duyet: "can_lam",
  cho_nhan: "can_lam",
  da_nhan: "da_nhan",
  dang_van_chuyen: "dang_xu_ly",
  da_giao_don_vi: "dang_xu_ly",
  hoan_tat: "da_xong",
  tranh_chap: "co_van_de",
  tu_choi: "co_van_de",
  da_huy: "co_van_de",
};

/** Tiến độ con cho đồ cồng kềnh (chỉ nhóm ③). Trả bước hiện tại 1..3, hoặc
 *  null nếu không thuộc chuỗi vận chuyển. 1=Nhận ✓, 2=Vận chuyển, 3=Giao đơn vị. */
export const BUOC_VAN_CHUYEN: Record<TrangThaiYeuCau, number | null> = {
  cho_duyet: null,
  cho_nhan: null,
  da_nhan: 1,
  dang_van_chuyen: 2,
  da_giao_don_vi: 3,
  hoan_tat: null,
  tranh_chap: null,
  tu_choi: null,
  da_huy: null,
};

/** Các trạng thái nằm trong luồng của đội vệ sinh — "kiện đang theo".
 *  Loại ``cho_duyet`` vì nó còn nằm chờ BQL duyệt, chưa phải việc của đội. */
export const TRANG_THAI_KIEN_DANG_THEO: ReadonlySet<string> = new Set([
  "cho_nhan",
  "da_nhan",
  "dang_van_chuyen",
  "da_giao_don_vi",
  "hoan_tat",
  "tranh_chap",
  "tu_choi",
  "da_huy",
]);
