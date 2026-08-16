/** Gamification — MẦM / CHỒI / CÂY / RỪNG.
 *
 * Hai nguồn dữ liệu TRUNG THỰC, không bịa:
 * - Cấp độ tính từ `green_points` (con số thật từ server).
 * - Streak "ngày liên tiếp" đếm từ các ngày người dùng THỰC SỰ phân loại
 *   thành công trên máy này (lưu localStorage). Không có hoạt động thì streak
 *   là 0 — không tự vẽ số ảo lên màn hình.
 */

const KHOAC = "greenbin_hoat_dong_ngay";

/** Lấy danh sách các ngày có hoạt động, dạng `YYYY-MM-DD` (giờ máy). */
function docNgay(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(window.localStorage.getItem(KHOAC) ?? "[]") as string[];
  } catch {
    return [];
  }
}

function ghiNgay(ds: string[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KHOAC, JSON.stringify(ds));
  } catch {
    /* localStorage chặn (private mode) — bỏ qua, không chết màn hình */
  }
}

/** Ngày hôm nay theo giờ máy, `YYYY-MM-DD`. */
export function homNay(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function ngayTruoc(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() - n);
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** Gọi mỗi lần phân loại thành công — ghi nhận ngày hôm nay. */
export function ghiHoatDong() {
  const hoy = homNay();
  const ds = docNgay();
  if (!ds.includes(hoy)) {
    ds.push(hoy);
    ds.sort();
    ghiNgay(ds);
  }
}

/** Số ngày liên tiếp TÍNH TỪ HÔM NAY (hoặc hôm qua nếu hôm nay chưa chụp). */
export function tinhStreak(): number {
  const ds = new Set(docNgay());
  if (!ds.has(homNay())) {
    // Hôm nay chưa có hoạt động: chuỗi còn sống nếu hôm qua có.
    if (!ds.has(ngayTruoc(homNay(), 1))) return 0;
  }
  let n = 0;
  let day = homNay();
  while (ds.has(day)) {
    n += 1;
    day = ngayTruoc(day, 1);
  }
  return n;
}

/** Bậc cấp độ — ngưỡng điểm là quy ước màn hình, ghi rõ để dễ đổi. */
export const CAP_DO = [
  { ten: "Mầm", tu: 0, den: 99, icon: "🌱" },
  { ten: "Chồi", tu: 100, den: 399, icon: "🌿" },
  { ten: "Cây", tu: 400, den: 999, icon: "🌳" },
  { ten: "Rừng", tu: 1000, den: Infinity, icon: "🌲" },
] as const;

export interface CapHienTai {
  ten: string;
  icon: string;
  phanTram: number; // 0..100
  conThieu: number; // điểm còn thiếu để lên cấp kế tiếp; 0 nếu đã tối đa
  cuaCapDo: string; // "Chồi (100-399)" cho màn Điểm xanh
}

export function tinhCap(diem: number): CapHienTai {
  const idx = CAP_DO.findIndex((c) => diem <= c.den);
  const c = CAP_DO[idx === -1 ? CAP_DO.length - 1 : idx];
  const tiep = CAP_DO[idx + 1];
  let phanTram = 100;
  let conThieu = 0;
  if (tiep) {
    const khoang = tiep.tu - c.tu;
    phanTram = Math.min(100, Math.round(((diem - c.tu) / khoang) * 100));
    conThieu = Math.max(0, tiep.tu - diem);
  }
  return {
    ten: c.ten,
    icon: c.icon,
    phanTram,
    conThieu,
    cuaCapDo: `${c.ten} (${c.tu}–${Number.isFinite(c.den) ? c.den : "∞"})`,
  };
}
