"use client";

import { Battery, Boxes, HelpCircle, Trash2, WifiOff } from "lucide-react";
import type { BinStats } from "@/lib/bins";
import { Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

type CardDef = {
  key: keyof BinStats | "km";
  label: string;
  icon: typeof Boxes;
  tone: string;
};

const CARDS: CardDef[] = [
  { key: "tong", label: "Tổng số thùng", icon: Boxes, tone: "text-foreground" },
  { key: "can_gom", label: "Cần gom", icon: Trash2, tone: "text-warn" },
  { key: "mat_ket_noi", label: "Mất kết nối", icon: WifiOff, tone: "text-stale" },
  { key: "het_pin", label: "Hết pin", icon: Battery, tone: "text-power" },
  // Chưa triển khai = xám nhạt, trung tính, KHÔNG báo động — đúng token P39 đặt
  // trong status.tsx (HelpCircle / text-muted). Ban quản lý cần THẤY con số này
  // để biết còn bao nhiêu thùng chờ lắp thiết bị, không phải để giật mình.
  { key: "chua_trien_khai", label: "Chưa triển khai", icon: HelpCircle, tone: "text-muted-foreground" },
];

export function StatCards({
  stats,
  loading,
}: {
  stats?: BinStats | undefined;
  loading?: boolean | undefined;
}) {

  return (
    <div className="grid grid-cols-2 gap-3">
      {CARDS.map(({ key, label, icon: Icon, tone }) => (
        <div
          key={key}
          className={cn(
            "rounded-xl border bg-card p-3.5",
            key === "can_gom" && "border-warn/40 bg-warn-soft",
          )}
        >
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Icon className={cn("size-3.5", tone)} aria-hidden />
            {label}
          </div>
          {loading || !stats ? (
            <Skeleton className="mt-2 h-8 w-12" />
          ) : (
            <div className={cn("mt-1 font-display text-3xl font-bold tabular-nums", tone)}>
              {stats[key as keyof BinStats]}
            </div>
          )}
        </div>
      ))}
      <div className="col-span-2 flex items-center justify-between rounded-xl border border-dashed bg-muted-bg/40 px-3.5 py-2.5">
        <span className="text-xs text-muted-foreground">Quãng đường gom — km</span>
        <span className="font-display text-lg text-muted-foreground">—</span>
      </div>
    </div>
  );
}
