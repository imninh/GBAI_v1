"use client";

import { Battery, ChevronRight } from "lucide-react";
import type { Bin } from "@/lib/bins";
import { formatLastSeen } from "@/lib/bins";
import { STATUS_BAR, StatusBadge } from "./status";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/primitives";

export function BinRow({
  bin,
  active,
  onSelect,
}: {
  bin: Bin;
  active?: boolean;
  onSelect: (bin: Bin) => void;
}) {
  const stale = bin.status === "mat_ket_noi";
  return (
    <button
      type="button"
      onClick={() => onSelect(bin)}
      aria-current={active ? "true" : undefined}
      className={cn(
        "group w-full rounded-2xl border bg-card p-3 text-left transition-colors hover:border-primary/40 hover:bg-accent/40",
        active && "border-primary ring-2 ring-ring/25",
        bin.status === "can_gom" && "border-warn/50",
        stale && "border-dashed",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">{bin.code}</span>
            <StatusBadge status={bin.status} />
          </div>
          <div className={cn("mt-1 truncate font-medium", stale && "text-muted-foreground")}>
            {bin.name}
          </div>
        </div>
        <ChevronRight className="mt-1 size-4 shrink-0 text-muted-foreground" aria-hidden />
      </div>

      <div className="mt-2.5 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted-bg">
          <div
            className={cn("h-full rounded-full", STATUS_BAR[bin.status], stale && "opacity-50")}
            style={{ width: `${Math.min(100, bin.fill_percent)}%` }}
          />
        </div>
        <span
          className={cn(
            "w-12 text-right font-display text-sm font-semibold tabular-nums",
            stale && "text-muted-foreground/60 line-through decoration-dotted",
          )}
        >
          {Math.round(bin.fill_percent)}%
        </span>
        <span
          className={cn(
            "flex w-14 items-center justify-end gap-1 text-xs tabular-nums text-muted-foreground",
            bin.status === "het_pin" && "font-semibold text-power",
          )}
        >
          <Battery className="size-3.5" aria-hidden />
          {Math.round(bin.battery_percent)}%
        </span>
      </div>

      {stale && (
        <p className="mt-2 text-xs text-muted-foreground">
          Số liệu cũ — cập nhật lần cuối {formatLastSeen(bin.last_seen_at)}
        </p>
      )}
    </button>
  );
}

export function BinListSkeleton() {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-[92px] w-full rounded-2xl" />
      ))}
    </div>
  );
}
