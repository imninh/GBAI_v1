"use client";

import { useEffect, useState } from "react";
import { Marker, Popup, Tooltip, useMap } from "react-leaflet";
import L from "leaflet";
import { API_URL, getToken } from "@/lib/api";
import { IconXeThuGom } from "@/lib/icons";

export interface LivePosition {
  lat: number;
  lng: number;
  snapped_lat?: number;
  snapped_lng?: number;
  speed_mps?: number | null;
  heading?: number | null;
  recorded_at?: string | null;
}

export function vehicleIcon(heading: number | null | undefined) {
  const rotation = heading != null ? heading : 0;
  return L.divIcon({
    className: "live-vehicle-marker",
    iconSize: [44, 44],
    iconAnchor: [22, 22],
    html: `
      <div style="position: relative; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center;">
        <div style="
          position: absolute;
          width: 44px;
          height: 44px;
          border-radius: 999px;
          background: rgba(22, 163, 74, 0.4);
          animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;
        "></div>
        <div style="
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 36px;
          height: 36px;
          border-radius: 999px;
          background: var(--color-marker-xanh);
          color: var(--color-surface);
          box-shadow: 0 0 0 3px var(--color-surface), 0 3px 10px rgba(0,0,0,0.4);
          transform: rotate(${rotation}deg);
          transition: transform 0.4s ease;
        ">
          <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/>
            <path d="M15 18H9"/>
            <path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14"/>
            <circle cx="17" cy="18" r="2"/>
            <circle cx="7" cy="18" r="2"/>
          </svg>
        </div>
      </div>
      <style>
        @keyframes ping {
          75%, 100% {
            transform: scale(1.8);
            opacity: 0;
          }
        }
      </style>
    `,
  });
}

/** Tự động bám theo xe nếu bật chế độ theo dõi */
function FollowVehicle({ pos, follow }: { pos: LivePosition | null; follow?: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (follow && pos) {
      const lat = pos.snapped_lat ?? pos.lat;
      const lng = pos.snapped_lng ?? pos.lng;
      map.panTo([lat, lng], { animate: true, duration: 0.8 });
    }
  }, [pos, follow, map]);
  return null;
}

export default function LiveVehicleMarker({
  routeId,
  follow = false,
  onPositionChange,
}: {
  routeId: number;
  follow?: boolean;
  onPositionChange?: (pos: LivePosition) => void;
}) {
  const [pos, setPos] = useState<LivePosition | null>(null);

  // 1. Fetch vị trí mới nhất & fallback polling
  useEffect(() => {
    let unmounted = false;
    const fetchLatest = async () => {
      try {
        const token = getToken();
        const headers: Record<string, string> = {};
        if (token) headers["Authorization"] = `Bearer ${token}`;

        const res = await fetch(`${API_URL}/api/v1/tracking/${routeId}/latest`, {
          headers,
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          if (!unmounted && data.position) {
            setPos(data.position);
            onPositionChange?.(data.position);
          }
        }
      } catch (err) {
        console.debug("Không lấy được vị trí GPS mới nhất:", err);
      }
    };

    fetchLatest();
    const pollTimer = setInterval(fetchLatest, 2500);

    return () => {
      unmounted = true;
      clearInterval(pollTimer);
    };
  }, [routeId, onPositionChange]);

  // 2. Mở kết nối WebSocket lắng nghe toạ độ realtime tức thì
  useEffect(() => {
    const wsUrl = API_URL.replace(/^http/, "ws") + `/api/v1/tracking/ws/${routeId}`;
    let ws: WebSocket | null = null;
    let pingInterval: NodeJS.Timeout | null = null;

    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        pingInterval = setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 15000);
      };

      ws.onmessage = (evt) => {
        try {
          if (evt.data === "pong") return;
          const msg = JSON.parse(evt.data);
          if (msg.type === "gps_update") {
            const nextPos: LivePosition = {
              lat: msg.lat,
              lng: msg.lng,
              snapped_lat: msg.snapped_lat,
              snapped_lng: msg.snapped_lng,
              speed_mps: msg.speed_mps,
              heading: msg.heading,
              recorded_at: msg.recorded_at,
            };
            setPos(nextPos);
            onPositionChange?.(nextPos);
          }
        } catch (e) {
          console.debug("Lỗi đọc message WS tracking:", e);
        }
      };

      ws.onerror = (e) => {
        console.debug("WebSocket tracking lỗi:", e);
      };
    } catch (err) {
      console.debug("Không thể tạo kết nối WebSocket tracking:", err);
    }

    return () => {
      if (pingInterval) clearInterval(pingInterval);
      if (ws) {
        ws.close();
      }
    };
  }, [routeId, onPositionChange]);

  if (!pos) return null;

  const displayLat = pos.snapped_lat ?? pos.lat;
  const displayLng = pos.snapped_lng ?? pos.lng;
  const speedKmh = pos.speed_mps != null ? Math.round(pos.speed_mps * 3.6) : 30;

  return (
    <>
      <FollowVehicle pos={pos} follow={follow} />
      <Marker position={[displayLat, displayLng]} icon={vehicleIcon(pos.heading)} zIndexOffset={1000}>
        <Tooltip direction="top" offset={[0, -22]} permanent>
          <span className="inline-flex items-center gap-1 rounded bg-surface/95 px-1.5 py-0.5 text-[11px] font-extrabold text-emerald-800 shadow">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-500"></span>
            Xe thu gom ({speedKmh} km/h)
          </span>
        </Tooltip>
        <Popup>
          <div className="text-xs">
            <div className="flex items-center gap-1.5 font-bold text-emerald-700">
              <IconXeThuGom className="h-4 w-4" strokeWidth={1.9} /> Xe thu gom (Live Tracking)
            </div>
            <div className="mt-1 font-semibold text-slate-700">
              Tốc độ: {speedKmh} km/h
            </div>
            {pos.heading != null && (
              <div className="text-slate-600">Hướng di chuyển: {pos.heading}°</div>
            )}
            {pos.recorded_at && (
              <div className="mt-1 text-[10px] text-slate-400">
                Cập nhật: {new Date(pos.recorded_at).toLocaleTimeString("vi-VN")}
              </div>
            )}
          </div>
        </Popup>
      </Marker>
    </>
  );
}
