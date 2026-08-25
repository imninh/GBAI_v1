"use client";

import { AlertTriangle, BatteryWarning, Check, HelpCircle, WifiOff } from "lucide-react";
import type { BinStatus } from "@/lib/bins";
import { STATUS_LABEL } from "@/lib/bins";
import { cn } from "@/lib/utils";

const STATUS_ICON = {
  can_gom: AlertTriangle,
  het_pin: BatteryWarning,
  mat_ket_noi: WifiOff,
  binh_thuong: Check,
  chua_trien_khai: HelpCircle,
} as const;

/** Mỗi trạng thái khác nhau ở ít nhất hai chiều: màu + hình (viền/nét/icon). */
const STATUS_CHIP: Record<BinStatus, string> = {
  can_gom: "bg-warn text-warn-foreground border-2 border-warn font-semibold shadow-sm",
  het_pin: "bg-power-soft text-power border-2 border-power/40 font-medium",
  mat_ket_noi: "bg-stale-soft text-stale border border-dashed border-stale/60 font-normal",
  binh_thuong: "bg-ok-soft text-ok border border-ok/20 font-normal",
  // Xám nhạt nét CHẤM — khác hẳn màu stale (nét ĐỨT) của "mất kết nối": chưa
  // triển khai là trạng thái bình thường, không báo động.
  chua_trien_khai: "bg-muted-bg text-muted border border-dotted border-line-faint font-normal",
};

export function StatusBadge({
  status,
  className,
}: {
  status: BinStatus;
  className?: string;
}) {
  const Icon = STATUS_ICON[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs leading-none",
        STATUS_CHIP[status],
        className,
      )}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {STATUS_LABEL[status]}
    </span>
  );
}

export const STATUS_BAR: Record<BinStatus, string> = {
  can_gom: "bg-warn",
  het_pin: "bg-power",
  mat_ket_noi: "bg-stale/50",
  binh_thuong: "bg-ok",
  // Chấm xám nhạt — cụm "chưa triển khai" nhìn là tách ngay khỏi vài thùng
  // "mất kết nối" thật (màu stale nét đứt).
  chua_trien_khai: "bg-line-faint",
};
