"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { api } from "@/lib/api";
import { kg } from "@/lib/format";
import { IconCanhBao, IconDuyet, IconMonDo } from "@/lib/icons";
import type { NavigationResult, RouteStop } from "@/lib/types";
import LiveVehicleMarker, { type LivePosition } from "@/components/map/live-vehicle-marker";
import { coToaDo } from "@/components/map/route-map-base";
import { Button, Card } from "@/components/ui/primitives";

export interface NavigationModeProps {
  dest: RouteStop;
  routeId: number;
  livePos?: LivePosition | null;
  stops?: RouteStop[];
  onComplete: (stopId: number, issue?: string) => Promise<void>;
  onExit: () => void;
  dsSuCo?: { code: string; label_vi: string }[];
}

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

function haversineMeters(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function distToSegmentMeters(
  p: [number, number],
  a: [number, number],
  b: [number, number]
): number {
  const x = p[0];
  const y = p[1];
  const x1 = a[0];
  const y1 = a[1];
  const x2 = b[0];
  const y2 = b[1];
  const dx = x2 - x1;
  const dy = y2 - y1;
  if (dx === 0 && dy === 0) {
    return haversineMeters(x, y, x1, y1);
  }
  const t = Math.max(0, Math.min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)));
  const projX = x1 + t * dx;
  const projY = y1 + t * dy;
  return haversineMeters(x, y, projX, projY);
}

function distToPolylineMeters(pos: [number, number], polyline: [number, number][]): number {
  if (polyline.length < 2) return 0;
  let minDist = Infinity;
  for (let i = 0; i < polyline.length - 1; i++) {
    const d = distToSegmentMeters(pos, polyline[i], polyline[i + 1]);
    if (d < minDist) minDist = d;
  }
  return minDist;
}

function calculateRemainingInfo(
  pos: [number, number],
  polyline: [number, number][]
): { km: number; minutes: number } {
  if (polyline.length < 2) return { km: 0, minutes: 0 };

  let minIdx = 0;
  let minDist = Infinity;
  for (let i = 0; i < polyline.length - 1; i++) {
    const d = distToSegmentMeters(pos, polyline[i], polyline[i + 1]);
    if (d < minDist) {
      minDist = d;
      minIdx = i;
    }
  }

  let totalMeters = haversineMeters(pos[0], pos[1], polyline[minIdx + 1][0], polyline[minIdx + 1][1]);
  for (let i = minIdx + 1; i < polyline.length - 1; i++) {
    totalMeters += haversineMeters(polyline[i][0], polyline[i][1], polyline[i + 1][0], polyline[i + 1][1]);
  }

  const km = Math.max(0.1, Math.round((totalMeters / 1000) * 10) / 10);
  const minutes = Math.max(1, Math.round((km / 25) * 60));
  return { km, minutes };
}

function destinationIcon(seq: number, isThung: boolean) {
  const bg = isThung ? "#d97706" : "#dc2626";
  return L.divIcon({
    className: "navigation-dest-marker",
    iconSize: [40, 52],
    iconAnchor: [20, 50],
    html: `
      <div style="position: relative; display: flex; flex-direction: column; align-items: center;">
        <div style="
          width: 40px;
          height: 40px;
          border-radius: 999px;
          background: ${bg};
          color: #ffffff;
          font-weight: 800;
          font-size: 15px;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 0 0 3px #ffffff, 0 4px 14px rgba(0,0,0,0.5);
          animation: pulse-ring 2s infinite;
        ">
          ${seq}
        </div>
        <div style="
          width: 0;
          height: 0;
          border-left: 7px solid transparent;
          border-right: 7px solid transparent;
          border-top: 10px solid ${bg};
          margin-top: -1px;
        "></div>
      </div>
      <style>
        @keyframes pulse-ring {
          0% { box-shadow: 0 0 0 3px #ffffff, 0 0 0 0 rgba(220, 38, 38, 0.6); }
          70% { box-shadow: 0 0 0 3px #ffffff, 0 0 0 10px rgba(220, 38, 38, 0); }
          100% { box-shadow: 0 0 0 3px #ffffff, 0 0 0 0 rgba(220, 38, 38, 0); }
        }
      </style>
    `,
  });
}

function MapController({
  pos,
  dest,
  polyline,
  follow,
}: {
  pos: LivePosition | null;
  dest: { lat: number; lng: number };
  polyline?: [number, number][];
  follow: boolean;
}) {
  const map = useMap();
  const hasCenteredInitial = useRef(false);

  useEffect(() => {
    if (!hasCenteredInitial.current) {
      if (polyline && polyline.length >= 2) {
        const bounds = L.latLngBounds(polyline);
        map.fitBounds(bounds, { padding: [80, 80], maxZoom: 17 });
        hasCenteredInitial.current = true;
      } else if (pos) {
        const bounds = L.latLngBounds([[pos.lat, pos.lng], [dest.lat, dest.lng]]);
        map.fitBounds(bounds, { padding: [80, 80], maxZoom: 17 });
        hasCenteredInitial.current = true;
      } else {
        map.setView([dest.lat, dest.lng], 16);
      }
    }
  }, [pos, dest, polyline, map]);

  useEffect(() => {
    if (follow && pos) {
      const lat = pos.snapped_lat ?? pos.lat;
      const lng = pos.snapped_lng ?? pos.lng;
      map.panTo([lat, lng], { animate: true, duration: 0.6 });
    }
  }, [pos, follow, map]);

  return null;
}

export default function NavigationMode({
  dest,
  routeId,
  livePos: propLivePos,
  stops = [],
  onComplete,
  onExit,
  dsSuCo = [],
}: NavigationModeProps) {
  const [tileMode, setTileMode] = useState<"satellite" | "standard">("satellite");
  const [livePos, setLivePos] = useState<LivePosition | null>(propLivePos ?? null);
  const [navData, setNavData] = useState<NavigationResult | null>(null);
  const [loadingRoute, setLoadingRoute] = useState(true);
  const [isRerouting, setIsRerouting] = useState(false);
  const [followVehicle, setFollowVehicle] = useState(true);
  const [dangBaoLoi, setDangBaoLoi] = useState(false);
  const [dangXuLy, setDangXuLy] = useState(false);

  const rerouteTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastRerouteTimeRef = useRef<number>(0);
  const hasInitializedLivePosRef = useRef(false);

  const destCoords = useMemo(() => {
    if (coToaDo(dest)) {
      return { lat: dest.lat, lng: dest.lng };
    }
    return { lat: 21.0285, lng: 105.8542 };
  }, [dest]);

  // Cập nhật livePos từ props nếu thay đổi
  useEffect(() => {
    if (propLivePos) {
      setLivePos(propLivePos);
    }
  }, [propLivePos]);

  // Gọi API dẫn đường
  const fetchNavigation = useCallback(
    async (originLat: number, originLng: number, isReroute = false) => {
      if (isReroute) setIsRerouting(true);
      else setLoadingRoute(true);

      try {
        const res = await api.navigate(
          { lat: originLat, lng: originLng },
          { lat: destCoords.lat, lng: destCoords.lng }
        );
        setNavData(res);
      } catch (err) {
        console.warn("Lỗi gọi API dẫn đường:", err);
      } finally {
        setLoadingRoute(false);
        setIsRerouting(false);
      }
    },
    [destCoords.lat, destCoords.lng]
  );

  // Tìm toạ độ xuất phát hợp lý nhất
  const getInitialOrigin = useCallback((): { lat: number; lng: number } => {
    if (livePos) {
      return {
        lat: livePos.snapped_lat ?? livePos.lat,
        lng: livePos.snapped_lng ?? livePos.lng,
      };
    }
    // Tìm điểm dừng liền trước
    if (dest.seq > 1 && stops.length > 0) {
      const prevStop = stops.find((s) => s.seq === dest.seq - 1 && coToaDo(s));
      if (prevStop && coToaDo(prevStop)) {
        return { lat: prevStop.lat, lng: prevStop.lng };
      }
    }
    // Điểm dừng đầu tiên nếu khác điểm đích
    const firstWithCoords = stops.find((s) => coToaDo(s) && s.stop_id !== dest.stop_id);
    if (firstWithCoords && coToaDo(firstWithCoords)) {
      return { lat: firstWithCoords.lat, lng: firstWithCoords.lng };
    }
    // Mặc định toạ độ gần đó tại trung tâm Hà Nội
    return { lat: destCoords.lat - 0.003, lng: destCoords.lng - 0.003 };
  }, [livePos, dest.seq, dest.stop_id, stops, destCoords]);

  // Khi component mount hoặc đổi điểm đích
  useEffect(() => {
    const origin = getInitialOrigin();
    fetchNavigation(origin.lat, origin.lng);
  }, [dest.stop_id, destCoords.lat, destCoords.lng, getInitialOrigin, fetchNavigation]);

  // Khi vị trí xe thực tế cập nhật lần đầu
  useEffect(() => {
    if (livePos && !hasInitializedLivePosRef.current) {
      hasInitializedLivePosRef.current = true;
      const lat = livePos.snapped_lat ?? livePos.lat;
      const lng = livePos.snapped_lng ?? livePos.lng;
      fetchNavigation(lat, lng);
    }
  }, [livePos, fetchNavigation]);

  // Re-route khi lệch đường > 50m (debounce 5s)
  useEffect(() => {
    if (!livePos || !navData?.polyline || navData.polyline.length < 2 || isRerouting) {
      return;
    }

    const currentPos: [number, number] = [
      livePos.snapped_lat ?? livePos.lat,
      livePos.snapped_lng ?? livePos.lng,
    ];

    const dist = distToPolylineMeters(currentPos, navData.polyline);

    if (dist > 50) {
      const now = Date.now();
      if (now - lastRerouteTimeRef.current > 5000) {
        if (rerouteTimeoutRef.current) clearTimeout(rerouteTimeoutRef.current);
        rerouteTimeoutRef.current = setTimeout(() => {
          lastRerouteTimeRef.current = Date.now();
          fetchNavigation(currentPos[0], currentPos[1], true);
        }, 1000);
      }
    }

    return () => {
      if (rerouteTimeoutRef.current) clearTimeout(rerouteTimeoutRef.current);
    };
  }, [livePos, navData?.polyline, isRerouting, fetchNavigation]);

  // Tính toán khoảng cách & thời gian còn lại theo thời gian thực (client-side)
  const remaining = useMemo(() => {
    if (!navData) return null;
    if (!livePos) {
      return { km: navData.distance_km, minutes: navData.duration_minutes };
    }
    const currentPos: [number, number] = [
      livePos.snapped_lat ?? livePos.lat,
      livePos.snapped_lng ?? livePos.lng,
    ];
    return calculateRemainingInfo(currentPos, navData.polyline);
  }, [navData, livePos]);

  const speedKmh = livePos?.speed_mps != null ? Math.round(livePos.speed_mps * 3.6) : null;

  async function handleComplete(issue = "") {
    setDangXuLy(true);
    try {
      await onComplete(dest.stop_id, issue);
      setDangBaoLoi(false);
    } finally {
      setDangXuLy(false);
    }
  }

  const polylineCoords = navData?.polyline ?? [];
  const initialCenter: [number, number] = livePos
    ? [livePos.lat, livePos.lng]
    : [destCoords.lat, destCoords.lng];

  return (
    <div className="relative h-[calc(100vh-140px)] min-h-[550px] w-full overflow-hidden rounded-2xl border border-slate-700 bg-slate-950 shadow-2xl">
      {/* Top Floating HUD: Nút Thoát, Thông tin lộ trình, Vệ tinh toggle */}
      <div className="absolute inset-x-0 top-3 z-[1000] flex items-center justify-between gap-2 px-3">
        {/* Nút thoát */}
        <button
          type="button"
          onClick={onExit}
          className="flex items-center gap-1.5 rounded-xl bg-slate-900/90 px-3 py-2 text-xs font-extrabold text-white shadow-lg backdrop-blur border border-slate-700 hover:bg-slate-800 transition-all active:scale-95"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6" />
          </svg>
          Thoát
        </button>

        {/* HUD Chỉ số trung tâm (Khoảng cách · Thời gian · Tốc độ) */}
        <div className="flex items-center gap-2 rounded-2xl bg-slate-900/95 px-3.5 py-2 text-white shadow-2xl backdrop-blur border border-slate-700/80">
          <div className="flex items-center gap-1.5 text-xs font-extrabold">
            <span className="text-sm">🚛</span>
            {loadingRoute ? (
              <span className="text-slate-400 animate-pulse">Đang tính đường…</span>
            ) : isRerouting ? (
              <span className="text-amber-400 animate-pulse">Đang tìm lại đường…</span>
            ) : (
              <span>
                <strong className="text-emerald-400">{remaining?.km ?? navData?.distance_km ?? 0} km</strong>
                <span className="mx-1 text-slate-400">·</span>
                <span className="text-slate-200">~{remaining?.minutes ?? navData?.duration_minutes ?? 0} phút</span>
              </span>
            )}
          </div>
          {speedKmh != null && (
            <div className="flex items-center gap-1 border-l border-slate-700 pl-2 text-[11px] font-extrabold text-emerald-400">
              <span>⚡</span>
              <span>{speedKmh} km/h</span>
            </div>
          )}
        </div>

        {/* Nút bật/tắt Vệ tinh & Bám xe */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setTileMode((m) => (m === "satellite" ? "standard" : "satellite"))}
            className={`flex items-center gap-1 rounded-xl px-2.5 py-2 text-xs font-bold shadow-lg backdrop-blur border transition-all ${
              tileMode === "satellite"
                ? "bg-emerald-700/90 text-white border-emerald-500"
                : "bg-slate-900/90 text-slate-200 border-slate-700 hover:bg-slate-800"
            }`}
            title="Đổi kiểu bản đồ"
          >
            <span>{tileMode === "satellite" ? "🛰" : "🗺"}</span>
            <span className="hidden sm:inline">{tileMode === "satellite" ? "Vệ tinh" : "Phố"}</span>
          </button>
          <button
            type="button"
            onClick={() => setFollowVehicle((f) => !f)}
            className={`flex items-center justify-center h-8 w-8 rounded-xl shadow-lg backdrop-blur border transition-all ${
              followVehicle
                ? "bg-emerald-600 text-white border-emerald-400 shadow-emerald-900/50"
                : "bg-slate-900/90 text-slate-400 border-slate-700"
            }`}
            title={followVehicle ? "Đang khóa tâm xe" : "Bật bám theo xe"}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <circle cx="12" cy="12" r="3" fill="currentColor" />
            </svg>
          </button>
        </div>
      </div>

      {/* Bản đồ chính */}
      <MapContainer
        center={initialCenter}
        zoom={16}
        scrollWheelZoom
        className="h-full w-full"
      >
        {tileMode === "satellite" ? (
          <TileLayer
            attribution='&copy; Google Maps'
            url="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}&hl=vi&gl=VN"
            maxZoom={19}
          />
        ) : (
          <TileLayer
            attribution='&copy; Google Maps'
            url="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}&hl=vi&gl=VN"
          />
        )}

        <MapController
          pos={livePos}
          dest={destCoords}
          polyline={polylineCoords}
          follow={followVehicle}
        />

        {/* Lộ trình màu xanh Google (#4285F4) với hiệu ứng glow */}
        {polylineCoords.length >= 2 && (
          <>
            <Polyline
              positions={polylineCoords}
              pathOptions={{
                color: "#1a73e8",
                weight: 9,
                opacity: 0.35,
              }}
            />
            <Polyline
              positions={polylineCoords}
              pathOptions={{
                color: "#4285F4",
                weight: 6,
                opacity: 0.95,
                lineCap: "round",
                lineJoin: "round",
              }}
            />
          </>
        )}

        {/* Marker xe thu gom Realtime */}
        <LiveVehicleMarker
          routeId={routeId}
          follow={followVehicle}
          onPositionChange={(pos) => setLivePos(pos)}
        />

        {/* Marker điểm đích thu gom */}
        <Marker
          position={[destCoords.lat, destCoords.lng]}
          icon={destinationIcon(dest.seq, dest.stop_kind === "thung")}
          zIndexOffset={900}
        >
          <Tooltip direction="top" offset={[0, -48]} permanent>
            <span className="inline-flex items-center gap-1 rounded bg-red-600 px-1.5 py-0.5 text-[11px] font-extrabold text-white shadow-md">
              📍 Đích: {dest.diem_dung_vi || `Điểm ${dest.seq}`}
            </span>
          </Tooltip>
          <Popup>
            <div className="text-xs">
              <div className="font-bold text-red-600">Điểm dừng #{dest.seq}</div>
              <div className="mt-1 font-semibold">{dest.diem_dung_vi}</div>
              <div className="text-slate-500">{dest.dia_chi}</div>
            </div>
          </Popup>
        </Marker>
      </MapContainer>

      {/* Bottom Floating Card: Thông tin điểm đến & Nút hành động */}
      <div className="absolute inset-x-3 bottom-3 z-[1000]">
        <Card className="p-3.5 bg-slate-900/95 text-white shadow-2xl border border-slate-700/80 backdrop-blur-md">
          <div className="flex items-start gap-2.5">
            <span
              className="flex h-10 w-10 flex-none items-center justify-center rounded-xl text-base font-extrabold shadow-md"
              style={{
                background: dest.stop_kind === "thung" ? "#d97706" : "#dc2626",
                color: "#ffffff",
              }}
            >
              {dest.seq}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-1">
                <span className="text-sm font-extrabold truncate text-slate-100">
                  {dest.diem_dung_vi || dest.unit || `Điểm ${dest.seq}`}
                </span>
                <span className="text-xs font-extrabold text-emerald-400 flex-none">
                  {dest.stop_kind === "thung"
                    ? `${Math.round(dest.fill_percent ?? 0)}% đầy`
                    : kg(dest.weight_max_kg)}
                </span>
              </div>
              <div className="text-xs font-semibold text-slate-300 truncate">
                {dest.stop_kind === "thung"
                  ? dest.dia_chi || "Thùng thu gom công cộng"
                  : `${dest.resident_name || ""} · ${dest.phone_masked || ""}`}
              </div>
              <div className="mt-1 flex items-center gap-1 text-xs font-bold text-slate-300 truncate">
                <IconMonDo className="h-3.5 w-3.5 flex-none text-amber-400" />
                {dest.stop_kind === "thung"
                  ? "Đổ thùng rác đầy"
                  : (dest.items ?? []).map((i) => `${i.qty > 1 ? `${i.qty} ` : ""}${i.name}`).join(", ") || "Rác cồng kềnh"}
              </div>
            </div>
          </div>

          {/* Action buttons */}
          {dangBaoLoi ? (
            <div className="mt-3 flex flex-col gap-1.5 border-t border-slate-700/80 pt-2.5">
              <div className="text-xs font-bold text-amber-400">Chọn lý do sự cố:</div>
              <div className="grid grid-cols-2 gap-1.5">
                {dsSuCo.map((su) => (
                  <button
                    key={su.code}
                    type="button"
                    disabled={dangXuLy}
                    onClick={() => handleComplete(su.code)}
                    className="rounded-lg border border-slate-700 bg-slate-800/90 py-1.5 px-2 text-xs font-bold text-slate-200 hover:bg-slate-700 hover:border-slate-600 transition-colors text-center disabled:opacity-50"
                  >
                    {su.label_vi}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setDangBaoLoi(false)}
                className="mt-1 py-1 text-center text-xs font-bold text-slate-400 hover:text-white"
              >
                Hủy bỏ
              </button>
            </div>
          ) : (
            <div className="mt-3 flex gap-2 border-t border-slate-700/80 pt-2.5">
              <Button
                variant="leaf"
                size="md"
                className="flex-1 font-extrabold text-sm bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg"
                disabled={dangXuLy}
                onClick={() => handleComplete()}
              >
                <IconDuyet className="h-4 w-4" strokeWidth={2.6} />
                {dangXuLy ? "Đang lưu…" : "ĐÃ THU GOM"}
              </Button>
              <Button
                variant="outline"
                size="md"
                className="border-amber-600/80 text-amber-400 hover:bg-amber-950/40 font-bold text-xs"
                disabled={dangXuLy}
                onClick={() => setDangBaoLoi(true)}
              >
                <IconCanhBao className="h-4 w-4" />
                Báo lỗi
              </Button>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
