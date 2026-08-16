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
