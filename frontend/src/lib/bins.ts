/** Kiểu dữ liệu và tiện ích cho thùng thu gom.
 *
 *  Khớp đúng hợp đồng API ở `src/api/routers/bins.py`: `GET /bins`,
 *  `GET /bins/stats`, `GET /bins/{code}`. Đổi tên trường ở một bên thì phải
 *  sửa cả hai nơi cùng lúc.
 */

export type BinStatus = "can_gom" | "het_pin" | "mat_ket_noi" | "binh_thuong";

export type Bin = {
  id: number;
  code: string;
  name: string;
  building_id: number | null;
  address: string;
  /** Mã nhóm rác thùng này nhận, ví dụ `["recyclable_plastic"]`. Có thể rỗng. */
  category_codes: string[];
  lat: number | null;
  lng: number | null;
  fill_percent: number;
  battery_percent: number;
  /** Id nhân viên đang được giao thùng này. `null` = chưa giao cho ai. */
  assigned_cleaner_id: number | null;
  last_seen_at: string | null;
  status: BinStatus;
};

export type BinReading = {
  fill_percent: number;
  battery_percent: number;
  source: string;
  created_at: string;
};

export type BinStats = {
  tong: number;
  can_gom: number;
  mat_ket_noi: number;
  het_pin: number;
};

/** Nhân viên vệ sinh có thể nhận thùng — khớp `GET /bins/nhan-vien`.
 *
 *  `so_thung_duoc_giao` là con số quyết định của người đang giao: giao thêm cho
 *  ai đang nhẹ việc, chứ không phải chọn bừa một cái tên.
 */
export type NhanVien = {
  id: number;
  full_name: string;
  phone: string;
  so_thung_duoc_giao: number;
};

export type TinhTrangDiemGui = "con_cho" | "sap_day" | "chua_ro";

export type DiemGui = {
  code: string;
  name: string;
  address: string;
  lat: number | null;
  lng: number | null;
  category_codes: string[];
  tinh_trang: TinhTrangDiemGui;
  tinh_trang_vi: string;
  /** NULL khi `tinh_trang` là `chua_ro` — số cũ không được hiện cho cư dân. */
  fill_percent: number | null;
};

export const STATUS_LABEL: Record<BinStatus, string> = {
  can_gom: "Cần gom",
  het_pin: "Hết pin",
  mat_ket_noi: "Mất kết nối",
  binh_thuong: "Bình thường",
};

export function computeStats(bins: Bin[]): BinStats {
  return {
    tong: bins.length,
    can_gom: bins.filter((b) => b.status === "can_gom").length,
    mat_ket_noi: bins.filter((b) => b.status === "mat_ket_noi").length,
    het_pin: bins.filter((b) => b.status === "het_pin").length,
  };
}

export function formatLastSeen(iso: string | null): string {
  if (!iso) return "chưa có dữ liệu";
  const d = new Date(iso);
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Ưu tiên gom: cần gom trước, rồi mức đầy giảm dần; mất kết nối xuống cuối.
 *
 *  Thùng mất kết nối bị đẩy xuống cuối **có chủ ý**: con số mức đầy của nó là
 *  số liệu cũ, không dùng để quyết định đi xe được.
 */
export function sortForCollection(bins: Bin[]): Bin[] {
  const rank: Record<BinStatus, number> = {
    can_gom: 0,
    het_pin: 1,
    binh_thuong: 2,
    mat_ket_noi: 3,
  };
  return [...bins].sort((a, b) => rank[a.status] - rank[b.status] || b.fill_percent - a.fill_percent);
}

/** Thùng chưa có toạ độ thì không vẽ lên bản đồ được. */
export function hasCoords(bin: Bin): bin is Bin & { lat: number; lng: number } {
  return typeof bin.lat === "number" && typeof bin.lng === "number";
}

/** Khoảng cách đường chim bay giữa hai điểm, tính bằng km (haversine).
 *
 *  Đây là đường CHIM BAY, không phải quãng đường đi bộ thật — chỗ nào hiện ra
 *  cho người dùng cũng phải nói rõ là "khoảng".
 */
export function khoangCachKm(
  a: { lat: number; lng: number },
  b: { lat: number; lng: number },
): number {
  const banKinh = 6371;
  const dLat = (b.lat - a.lat) * (Math.PI / 180);
  const dLng = (b.lng - a.lng) * (Math.PI / 180);
  const x =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * (Math.PI / 180)) * Math.cos(b.lat * (Math.PI / 180)) * Math.sin(dLng / 2) ** 2;
  return 2 * banKinh * Math.asin(Math.sqrt(x));
}

/** Đổi km thành chuỗi đọc được: `"180 m"`, `"1,2 km"`. `null` → `""`. */
export function dinhDangKhoangCach(km: number | null): string {
  if (km === null) return "";
  if (km < 1) {
    const met = Math.round((km * 1000) / 10) * 10;
    return `${met} m`;
  }
  return `${km.toFixed(1).replace(".", ",")} km`;
}
