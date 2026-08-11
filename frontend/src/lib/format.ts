/** Hàm định dạng dùng chung. Toàn bộ số hiển thị theo quy ước tiếng Việt:
 *  dấu phẩy là dấu thập phân, dấu chấm phân tách hàng nghìn.
 */

import type { LucideIcon } from "lucide-react";

import { IconCam, IconChoDuyet, IconDuyet, IconTuChoi, IconXeThuGom } from "@/lib/icons";

export function soVn(value: number, digits = 0): string {
  return value.toLocaleString("vi-VN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function phanTram(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${soVn(value * 100, digits)}%`;
}

export function tienUsd(value: number): string {
  if (value === 0) return "$0";
  if (value < 0.01) return `$${value.toFixed(4).replace(".", ",")}`;
  return `$${value.toFixed(2).replace(".", ",")}`;
}

export function doTinCay(value: number): string {
  return value.toFixed(2).replace(".", ",");
}

export function kg(value: number): string {
  return `${soVn(value, value % 1 === 0 ? 0 : 1)} kg`;
}

export function dungLuong(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${soVn(bytes / 1024 / 1024, 1)} MB`;
  return `${soVn(Math.round(bytes / 1024))} KB`;
}

export function ngayVn(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function gioVn(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

export function ngayGioVn(iso: string | null | undefined): string {
  if (!iso) return "—";
  return `${ngayVn(iso)} ${gioVn(iso)}`;
}

/** "còn 4 giờ" — chi tiết nhỏ nhưng làm sản phẩm sống hẳn lên. */
export function conBaoLau(iso: string): string {
  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs <= 0) return "đã qua";
  const gio = Math.floor(diffMs / 3_600_000);
  if (gio < 1) return `còn ${Math.max(1, Math.floor(diffMs / 60_000))} phút`;
  if (gio < 24) return `còn ${gio} giờ`;
  return `còn ${Math.floor(gio / 24)} ngày`;
}

/** Nhãn trạng thái yêu cầu thu gom — màu KHÔNG được là kênh thông tin duy nhất,
 *  nên mỗi trạng thái đều có icon riêng đi kèm. Icon lấy từ `@/lib/icons` để cả
 *  app dùng chung một bộ, không phải mỗi màn một kiểu ký hiệu. */
export const TRANG_THAI_YEU_CAU: Record<string, { label: string; icon: LucideIcon; className: string }> = {
  pending: { label: "Chờ duyệt", icon: IconChoDuyet, className: "bg-amber-soft text-amber" },
  approved: { label: "Đã duyệt", icon: IconDuyet, className: "bg-leaf-soft text-leaf-dark" },
  rejected: { label: "Bị từ chối", icon: IconTuChoi, className: "bg-[#eef1ec] text-muted-2" },
  scheduled: { label: "Đã xếp tuyến", icon: IconXeThuGom, className: "bg-recycle-soft text-recycle" },
  done: { label: "Đã thu xong", icon: IconDuyet, className: "bg-[#eef1ec] text-muted-2" },
  cancelled: { label: "Đã huỷ", icon: IconCam, className: "bg-[#eef1ec] text-muted line-through" },
};

export const TRANG_THAI_TUYEN: Record<string, { label: string; className: string }> = {
  proposed: { label: "AI đề xuất — chờ duyệt", className: "bg-amber-soft text-amber" },
  approved: { label: "Đã duyệt", className: "bg-leaf-soft text-leaf-dark" },
  in_progress: { label: "Đang chạy", className: "bg-recycle-soft text-recycle" },
  done: { label: "Hoàn thành", className: "bg-[#eef1ec] text-muted-2" },
  cancelled: { label: "Đã huỷ", className: "bg-[#eef1ec] text-muted" },
};

export const NHAN_TIN_CAY: Record<string, { label: string; className: string }> = {
  chac_chan: { label: "Chắc chắn", className: "bg-leaf-soft text-leaf-dark" },
  kha_chac: { label: "Khá chắc — nên kiểm tra lại", className: "bg-amber-soft text-amber" },
  duoi_nguong: { label: "Chưa đủ chắc", className: "bg-[#eef1ec] text-muted-2" },
};
