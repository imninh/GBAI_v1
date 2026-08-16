"use client";

import { useEffect, useState } from "react";
import { Battery, MapPin, X } from "lucide-react";
import { api } from "@/lib/api";
import type { Bin, BinReading, NhanVien } from "@/lib/bins";
import { formatLastSeen } from "@/lib/bins";
import { STATUS_BAR, StatusBadge } from "./status";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

const NGUON_LABEL: Record<string, string> = {
  device: "Thiết bị",
  simulator: "Mô phỏng",
  manual: "Nhập tay",
};

export function BinDetail({
  bin,
  nhanVien,
  coQuyenGiao,
  lyDoCam,
  onGanXong,
  onClose,
}: {
  bin: Bin;
  /** `null` = chưa tải xong hoặc không có quyền xem danh sách. */
  nhanVien: NhanVien[] | null;
  coQuyenGiao: boolean;
  /** Câu giải thích của server khi vai này không được giao thùng. */
  lyDoCam: string;
  /** Gọi sau khi giao xong để màn cha tải lại danh sách thùng. */
  onGanXong: () => void;
  onClose: () => void;
}) {
  const stale = bin.status === "mat_ket_noi";
  const [readings, setReadings] = useState<BinReading[] | null>(null);

  const [dangLuu, setDangLuu] = useState(false);
  const [loiGan, setLoiGan] = useState<{ message: string; code: string } | null>(null);

  /** Đổi người được giao. Chuỗi rỗng từ `<select>` nghĩa là **bỏ giao**. */
  async function giao(giaTri: string) {
    setDangLuu(true);
    setLoiGan(null);
    try {
      await api.ganThung(bin.code, giaTri === "" ? null : Number(giaTri));
      onGanXong();
    } catch (err) {
      const e = err as { message?: string; code?: string };
      setLoiGan({ message: e.message ?? "Không giao được thùng.", code: e.code ?? "UNKNOWN" });
    } finally {
      setDangLuu(false);
    }
  }

  useEffect(() => {
    let huy = false;
    setReadings(null);
    api
      .bin(bin.code)
      .then((chiTiet) => {
        if (!huy) setReadings(chiTiet.readings ?? []);
      })
      .catch(() => {
        if (!huy) setReadings([]);
      });
    return () => {
      huy = true;
    };
  }, [bin.code]);

  return (
    <aside className="absolute right-4 top-4 z-[500] w-[320px] rounded-2xl border bg-card p-4 shadow-panel">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-mono text-xs text-muted-foreground">{bin.code}</div>
          <h2 className="text-lg font-semibold">{bin.name}</h2>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Đóng">
          <X className="size-4" />
        </Button>
      </div>

      <div className="mt-2">
        <StatusBadge status={bin.status} />
      </div>

      <p className="mt-3 flex items-start gap-1.5 text-sm text-muted-foreground">
        <MapPin className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        {bin.address}
      </p>

      <div className="mt-4 space-y-3">
        <div>
          <div className="flex items-baseline justify-between text-sm">
            <span className="text-muted-foreground">Mức đầy</span>
            <span
              className={cn(
                "font-display text-xl font-bold tabular-nums",
                stale && "text-muted-foreground/60",
              )}
            >
              {Math.round(bin.fill_percent)}%
            </span>
          </div>
          <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-muted-bg">
            <div
              className={cn("h-full rounded-full", STATUS_BAR[bin.status], stale && "opacity-50")}
              style={{ width: `${Math.min(100, bin.fill_percent)}%` }}
            />
          </div>
        </div>

        <div className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Battery className="size-4" aria-hidden /> Pin
          </span>
          <span className={cn("tabular-nums", bin.status === "het_pin" && "font-semibold text-power")}>
            {Math.round(bin.battery_percent)}%
          </span>
        </div>

        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Báo cáo lần cuối</span>
          <span className="tabular-nums">{formatLastSeen(bin.last_seen_at)}</span>
        </div>
      </div>

      {stale && (
        <p className="mt-3 rounded-lg border border-dashed border-stale/60 bg-stale-soft p-2.5 text-xs text-muted-foreground">
          Thùng này mất kết nối. Con số {Math.round(bin.fill_percent)}% là{" "}
          <strong>số liệu cũ</strong> từ lần báo cuối — không dùng để quyết định đi gom.
        </p>
      )}

      <div className="mt-4 border-t pt-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Giao cho nhân viên
        </h3>

        <select
          className="mt-2 w-full rounded-xl border bg-card px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
          value={bin.assigned_cleaner_id ?? ""}
          disabled={!coQuyenGiao || dangLuu || nhanVien === null}
          title={coQuyenGiao ? undefined : lyDoCam}
          aria-label="Giao thùng này cho nhân viên"
          onChange={(e) => void giao(e.target.value)}
        >
          <option value="">— Chưa giao cho ai —</option>
          {(nhanVien ?? []).map((nv) => (
            <option key={nv.id} value={nv.id}>
              {nv.full_name} · {nv.so_thung_duoc_giao} thùng
            </option>
          ))}
        </select>

        {!coQuyenGiao && (
          <p className="mt-1.5 text-xs text-muted-foreground">{lyDoCam}</p>
        )}
        {dangLuu && <p className="mt-1.5 text-xs text-muted-foreground">Đang lưu…</p>}
        {loiGan && (
          <p className="mt-1.5 text-xs text-destructive">
            {loiGan.message} <span className="text-muted-foreground">({loiGan.code})</span>
          </p>
        )}
      </div>

      <div className="mt-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Lịch sử báo cáo
        </h3>

        {readings === null ? (
          <p className="mt-2 rounded-lg border border-dashed bg-muted-bg/40 p-3 text-xs text-muted-foreground">
            Đang tải lịch sử báo cáo…
          </p>
        ) : readings.length === 0 ? (
          <p className="mt-2 rounded-lg border border-dashed bg-muted-bg/40 p-3 text-xs text-muted-foreground">
            Thùng chưa gửi số liệu nào.
          </p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {readings.map((r, i) => (
              <li
                key={`${r.created_at ?? "?"}-${i}`}
                className="flex items-center justify-between gap-2 rounded-lg border border-line-3 bg-muted-bg/30 px-2.5 py-1.5 text-xs"
              >
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {formatLastSeen(r.created_at)}
                </span>
                <span className="flex shrink-0 items-center gap-2 tabular-nums">
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-leaf" aria-hidden />
                    {Math.round(r.fill_percent)}%
                  </span>
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <Battery className="size-3" aria-hidden />
                    {Math.round(r.battery_percent)}%
                  </span>
                  <span className="w-12 shrink-0 text-right text-muted-foreground">
                    {NGUON_LABEL[r.source] ?? r.source}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
