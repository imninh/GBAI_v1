"use client";

import { Play, Route as RouteIcon, Square } from "lucide-react";
import { cn } from "@/lib/utils";

export function ActionPanel({
  running,
  step,
  intervalSeconds,
  onToggle,
}: {
  running: boolean;
  step: number;
  intervalSeconds: number;
  onToggle: () => void;
}) {
  return (
    <div className="space-y-2.5">
      <button
        type="button"
        onClick={onToggle}
        aria-pressed={running}
        className={cn(
          "flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-colors",
          running ? "border-primary bg-accent/60" : "bg-card hover:bg-accent/40",
        )}
      >
        <span
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-lg",
            running ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground",
          )}
        >
          {running ? <Square className="size-4" /> : <Play className="size-4" />}
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-medium">Theo dõi trực tiếp</span>
          <span className="block text-xs text-muted-foreground">
            {running ? (
              <span className="flex items-center gap-1.5">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex size-2 animate-ping rounded-full bg-primary/70" />
                  <span className="relative inline-flex size-2 rounded-full bg-primary" />
                </span>
                đang chạy · làm mới mỗi {intervalSeconds}s · lần {step}
              </span>
            ) : (
              "đang tắt · bật để tự gọi lại API và thấy số liệu thiết bị đổi"
            )}
          </span>
        </span>
      </button>

      <div className="rounded-xl border border-dashed bg-muted-bg/40 p-3">
        <div className="flex items-center gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted-bg text-muted-foreground">
            <RouteIcon className="size-4" />
          </span>
          <span>
            <span className="block text-sm font-medium text-muted-foreground">
              Tối ưu hoá tuyến đường
            </span>
            <span className="block text-xs text-muted-foreground">Chưa có API — sắp ra mắt</span>
          </span>
        </div>
      </div>
    </div>
  );
}
