"use client";

import React, { useEffect, useMemo, useState } from "react";
import type { PickupRoute } from "@/lib/types";
import RouteMapBase, { coToaDo } from "@/components/map/route-map-base";
import LiveVehicleMarker, { type LivePosition } from "@/components/map/live-vehicle-marker";
import NavigationMode from "@/components/map/navigation-mode";
import { Button, Card } from "@/components/ui/primitives";
import { IconCanhBao, IconDuyet, IconMonDo } from "@/lib/icons";
import { kg } from "@/lib/format";

interface NavigationMapProps {
  tuyen: PickupRoute;
  onDanhDau: (stopId: number, issue?: string) => Promise<void>;
  onTroLaiDanhSach?: () => void;
  dsSuCo: { code: string; label_vi: string }[];
}

export default function CleanerNavigationMap({
  tuyen,
  onDanhDau,
  onTroLaiDanhSach,
  dsSuCo,
}: NavigationMapProps) {
  const stops = useMemo(() => tuyen.stops ?? [], [tuyen.stops]);
  const diemChuaThu = stops.find((s) => !s.done_at);
  const [selectedStopId, setSelectedStopId] = useState<number | null>(
    diemChuaThu ? diemChuaThu.stop_id : (stops[0]?.stop_id ?? null)
  );
  const [navigating, setNavigating] = useState(true);
  const [followVehicle, setFollowVehicle] = useState(false);
  const [livePos, setLivePos] = useState<LivePosition | null>(null);
  const [dangBaoLoi, setDangBaoLoi] = useState(false);
  const [dangXuLy, setDangXuLy] = useState(false);

  // Khi có điểm dừng hoàn thành, tự động chuyển chọn điểm kế tiếp
  useEffect(() => {
    const nextIncomplete = stops.find((s) => !s.done_at);
    if (nextIncomplete && selectedStopId === null) {
      setSelectedStopId(nextIncomplete.stop_id);
    }
  }, [stops, selectedStopId]);

  const activeStop = stops.find((s) => s.stop_id === selectedStopId) ?? diemChuaThu ?? stops[0];
  const coToaDoActive = activeStop && coToaDo(activeStop);

  const daThuCount = stops.filter((s) => Boolean(s.done_at)).length;

  async function xuLyDanhDau(issue = "") {
    if (!activeStop) return;
    setDangXuLy(true);
    try {
      await onDanhDau(activeStop.stop_id, issue);
      setDangBaoLoi(false);
      // Tự động tìm điểm tiếp theo
      const nextOne = stops.find((s) => s.stop_id !== activeStop.stop_id && !s.done_at);
      if (nextOne) setSelectedStopId(nextOne.stop_id);
    } finally {
      setDangXuLy(false);
    }
  }

  if (navigating && activeStop && coToaDoActive) {
    return (
      <NavigationMode
        dest={activeStop}
        routeId={tuyen.id}
        livePos={livePos}
        stops={stops}
        onComplete={async (stopId, issue) => {
          await onDanhDau(stopId, issue);
          const nextOne = stops.find((s) => s.stop_id !== stopId && !s.done_at);
          if (nextOne) {
            setSelectedStopId(nextOne.stop_id);
          } else {
            setNavigating(false);
          }
        }}
        onExit={() => setNavigating(false)}
        dsSuCo={dsSuCo}
      />
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-140px)] min-h-[500px] w-full relative">
      {/* Header điều khiển bản đồ */}
      <div className="mb-2 flex items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-1.5 text-xs font-bold text-slate-700">
          <span>📍 {daThuCount}/{stops.length} điểm đã thu</span>
          {livePos?.speed_mps != null && (
            <span className="text-[10px] font-extrabold text-emerald-800 bg-emerald-100 px-1.5 py-0.5 rounded">
              {Math.round(livePos.speed_mps * 3.6)} km/h
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setFollowVehicle((prev) => !prev)}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-extrabold transition-colors ${followVehicle
                ? "bg-emerald-600 text-white shadow-sm"
                : "bg-surface text-slate-700 border border-slate-200"
              }`}
          >
            <span className={`inline-block h-2 w-2 rounded-full ${followVehicle ? "bg-surface animate-ping" : "bg-emerald-500"}`} />
            {followVehicle ? "Đang theo xe" : "Bám theo xe"}
          </button>
          {onTroLaiDanhSach && (
            <button
              type="button"
              onClick={onTroLaiDanhSach}
              className="px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-xs font-bold border border-slate-200"
            >
              Xem danh sách
            </button>
          )}
        </div>
      </div>

      {/* Bản đồ chính (chiếm phần lớn không gian trên) */}
      <div className="flex-1 w-full rounded-2xl overflow-hidden shadow-inner border border-slate-200 relative">
        <RouteMapBase
          stops={stops}
          duong_di={tuyen.duong_di}
          lo_trinh_meta={tuyen.lo_trinh_meta}
          activeStopId={selectedStopId}
          disableFitBounds={followVehicle}
          onSelectStop={(stop) => {
            setSelectedStopId(stop.stop_id);
            setFollowVehicle(false);
          }}
          showLegend={false}
          className="h-full w-full"
        >
          <LiveVehicleMarker
            routeId={tuyen.id}
            follow={followVehicle}
            onPositionChange={setLivePos}
          />
        </RouteMapBase>

        {/* Nút bật dẫn đường in-app nổi trên bản đồ */}
        {coToaDoActive && (
          <button
            type="button"
            onClick={() => setNavigating(true)}
            className="absolute top-3 right-3 z-[1000] flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-extrabold px-3 py-2 rounded-xl shadow-lg transition-transform active:scale-95"
          >
            <span className="text-sm">🧭</span>
            Dẫn đường
          </button>
        )}
      </div>

      {/* Thẻ điều hướng điểm dừng kế tiếp (Next-Stop HUD) */}
      {activeStop && (
        <Card className="mt-2.5 p-3.5 bg-surface shadow-md border border-slate-200">
          <div className="flex items-start gap-2.5">
            <span
              className="flex h-9 w-9 flex-none items-center justify-center rounded-xl text-sm font-extrabold shadow-sm"
              style={{
                background: activeStop.done_at ? "var(--color-leaf-soft)" : "var(--color-ink)",
                color: activeStop.done_at ? "var(--color-leaf-dark)" : "var(--color-surface)",
              }}
            >
              {activeStop.seq}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-1">
                <span className="text-sm font-extrabold truncate text-slate-800">
                  {activeStop.diem_dung_vi || activeStop.unit || `Điểm ${activeStop.seq}`}
                </span>
                <span className="font-[family-name:var(--font-display)] text-sm font-extrabold text-recycle flex-none">
                  {activeStop.stop_kind === "thung"
                    ? `${Math.round(activeStop.fill_percent ?? 0)}% đầy`
                    : kg(activeStop.weight_max_kg)}
                </span>
              </div>
              <div className="text-xs font-semibold text-muted truncate">
                {activeStop.stop_kind === "thung"
                  ? activeStop.dia_chi || "Thùng thu gom công cộng"
                  : `${activeStop.resident_name || ""} · ${activeStop.phone_masked || ""}`}
              </div>
              <div className="mt-1 flex items-center gap-1 text-xs font-bold text-bulky-dark truncate">
                <IconMonDo className="h-3.5 w-3.5 flex-none" />
                {activeStop.stop_kind === "thung"
                  ? "Đổ thùng rác"
                  : (activeStop.items ?? []).map((i) => `${i.qty > 1 ? `${i.qty} ` : ""}${i.name}`).join(", ") || "Rác cồng kềnh"}
              </div>
            </div>
          </div>

          {/* Các nút hành động cho điểm dừng */}
          {activeStop.done_at ? (
            <div className="mt-2 flex items-center justify-center gap-1.5 rounded-xl bg-leaf-soft py-2 text-xs font-extrabold text-leaf-dark">
              <IconDuyet className="h-4 w-4 flex-none" />
              Điểm này đã thu gom xong
            </div>
          ) : dangBaoLoi ? (
            <div className="mt-2 flex flex-col gap-1.5">
              <div className="text-xs font-bold text-amber-700">Chọn lý do sự cố:</div>
              <div className="grid grid-cols-2 gap-1.5">
                {dsSuCo.map((su) => (
                  <Button
                    key={su.code}
                    size="sm"
                    variant="outline"
                    disabled={dangXuLy}
                    onClick={() => xuLyDanhDau(su.code)}
                  >
                    {su.label_vi}
                  </Button>
                ))}
              </div>
              <Button size="sm" variant="ghost" onClick={() => setDangBaoLoi(false)}>
                Hủy
              </Button>
            </div>
          ) : (
            <div className="mt-2.5 flex gap-2">
              <Button
                variant="leaf"
                size="md"
                className="flex-1 font-bold text-sm"
                disabled={dangXuLy}
                onClick={() => xuLyDanhDau()}
              >
                <IconDuyet className="h-4 w-4" strokeWidth={2.6} />
                {dangXuLy ? "Đang lưu…" : "ĐÃ THU GOM"}
              </Button>
              {coToaDoActive && (
                <Button
                  variant="outline"
                  size="md"
                  className="border-blue-300 text-blue-700 font-bold text-xs hover:bg-blue-50"
                  onClick={() => setNavigating(true)}
                >
                  <span>🧭</span>
                  Dẫn đường
                </Button>
              )}
              <Button
                variant="outline"
                size="md"
                className="border-amber-line text-amber font-bold text-xs"
                disabled={dangXuLy}
                onClick={() => setDangBaoLoi(true)}
              >
                <IconCanhBao className="h-4 w-4" />
                Báo lỗi
              </Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
