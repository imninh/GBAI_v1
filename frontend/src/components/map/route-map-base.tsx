"use client";

import { useEffect, useMemo, type ReactNode } from "react";
import { MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import type { LoTrinhMeta, RouteStop } from "@/lib/types";

export interface StopToaDo extends RouteStop {
  lat: number | null;
  lng: number | null;
}

export type ToaDoDuongDi = [number, number];

export function coToaDo(stop: RouteStop): stop is StopToaDo & { lat: number; lng: number } {
  const co = stop as StopToaDo;
  return typeof co.lat === "number" && typeof co.lng === "number";
}

/** Huy hiệu cho một nhóm điểm dừng trên bản đồ. */
export function markerIconNhom(
  nhom: (StopToaDo & { lat: number; lng: number })[],
  activeStopId?: number | null
) {
  const laThung = nhom.some((s) => s.stop_kind === "thung");
  const tatCaDaThu = nhom.every((s) => Boolean(s.done_at));
  const coActive = nhom.some((s) => s.stop_id === activeStopId);

  let nen = laThung ? "var(--color-marker-thung)" : "var(--color-marker-bulky)";
  let mau = laThung ? "var(--color-marker-xanh)" : "var(--color-surface)";
  let border = "var(--color-surface)";
  let shadow = "0 2px 6px rgba(0,0,0,.3)";

  if (tatCaDaThu) {
    nen = "var(--color-marker-xanh)";
    mau = "var(--color-surface)";
    if (coActive) {
      border = "var(--color-leaf-line)";
      shadow = "0 0 0 3px rgba(31, 138, 79, 0.3), 0 3px 8px rgba(0,0,0,.3)";
    }
  } else if (coActive) {
    border = "var(--color-leaf-ink)";
    shadow = "0 0 0 4px rgba(42, 90, 58, 0.4), 0 3px 10px rgba(0,0,0,.4)";
  }

  const nhan = nhom.map((s) => s.seq).join(",");
  const iconSize = coActive ? 32 : 28;
  const anchor = iconSize / 2;

  return L.divIcon({
    className: `route-stop-marker ${coActive ? "active-stop-marker" : ""}`,
    iconSize: [iconSize, iconSize],
    iconAnchor: [anchor, anchor],
    html: `<div style="display:flex;align-items:center;justify-content:center;width:${iconSize}px;height:${iconSize}px;border-radius:999px;background:${nen};color:${mau};font-size:${nhom.length > 1 ? 10 : coActive ? 13 : 12}px;font-weight:800;font-family:var(--font-sans);box-shadow:${shadow};border:${coActive ? "3px" : "2px"} solid ${border};transition:all .3s ease">${tatCaDaThu ? `✓ ${nhan}` : nhan}</div>`,
  });
}

export function moTaDi(diem: StopToaDo & { lat: number; lng: number }) {
  if (diem.stop_kind === "thung") {
    return `${diem.seq} · ${diem.diem_dung_vi}${diem.fill_percent != null ? ` · đầy ${Math.round(diem.fill_percent)}%` : ""}`;
  }
  return `${diem.seq} · ${diem.diem_dung_vi}`;
}

export function VuaKhung({
  cacDiem,
  padding = [32, 32],
  disabled = false,
}: {
  cacDiem: (StopToaDo & { lat: number; lng: number })[];
  padding?: [number, number];
  disabled?: boolean;
}) {
  const map = useMap();
  const cacDiemKey = useMemo(
    () => cacDiem.map((s) => `${s.stop_id}:${s.lat},${s.lng}`).join(";"),
    [cacDiem]
  );

  useEffect(() => {
    if (disabled || cacDiem.length === 0) return;
    map.fitBounds(L.latLngBounds(cacDiem.map((s) => [s.lat, s.lng] as [number, number])), {
      padding,
      maxZoom: 16,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacDiemKey, padding, map, disabled]);
  return null;
}

export default function RouteMapBase({
  stops,
  duong_di,
  lo_trinh_meta,
  activeStopId,
  onSelectStop,
  children,
  showLegend = true,
  className = "h-full w-full",
  tileUrl = "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}&hl=vi&gl=VN",
  disableFitBounds = false,
}: {
  stops: RouteStop[];
  duong_di?: ToaDoDuongDi[] | null;
  lo_trinh_meta?: LoTrinhMeta | null;
  activeStopId?: number | null;
  onSelectStop?: (stop: RouteStop) => void;
  children?: ReactNode;
  showLegend?: boolean;
  className?: string;
  tileUrl?: string;
  disableFitBounds?: boolean;
}) {
  const cacDiem = useMemo(
    () => [...stops].sort((a, b) => a.seq - b.seq).filter(coToaDo),
    [stops]
  );

  if (cacDiem.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center rounded-xl bg-cream-soft px-4 text-center text-sm font-semibold text-muted">
        Tuyến chưa có toạ độ để vẽ bản đồ
      </div>
    );
  }

  const hinhDuongDi = Array.isArray(duong_di) ? duong_di : [];
  const coDuongThat = hinhDuongDi.length >= 2;

  // Gộp điểm trùng toạ độ
  const nhom: Record<string, (StopToaDo & { lat: number; lng: number })[]> = {};
  for (const diem of cacDiem) {
    const khoa = `${diem.lat},${diem.lng}`;
    (nhom[khoa] ??= []).push(diem);
  }
  const cacNhom = Object.values(nhom);

  return (
    <div className={`relative ${className} z-0 isolate`}>
      <MapContainer
        center={[cacDiem[0].lat, cacDiem[0].lng]}
        zoom={14}
        scrollWheelZoom
        className="h-full w-full relative z-0 isolate"
      >
        <TileLayer
          attribution='&copy; Google Maps'
          url={tileUrl}
        />
        <VuaKhung cacDiem={cacDiem} disabled={disableFitBounds} />

        {/* Tuyến đường: vẽ đường thật OSRM nếu có, hoặc đường chim bay nét đứt */}
        {coDuongThat ? (
          <Polyline positions={hinhDuongDi} pathOptions={{ color: '#1f8a4f', weight: 4, opacity: 0.9 }} />
        ) : (
          <Polyline
            positions={cacDiem.map((s) => [s.lat, s.lng] as ToaDoDuongDi)}
            pathOptions={{ color: '#1f8a4f', weight: 3, dashArray: "6 6", opacity: 0.7 }}
          />
        )}

        {/* Các điểm dừng */}
        {cacNhom.map((nhomDiem) => {
          const [dau] = nhomDiem;
          return (
            <Marker
              key={dau.stop_id}
              position={[dau.lat, dau.lng] as ToaDoDuongDi}
              icon={markerIconNhom(nhomDiem, activeStopId)}
              eventHandlers={{
                click: () => onSelectStop?.(dau),
              }}
            >
              {nhomDiem.length === 1 ? (
                <Tooltip direction="top" offset={[0, -16]}>
                  {moTaDi(dau)}
                </Tooltip>
              ) : (
                <Popup>
                  <div className="text-xs font-bold">
                    {nhomDiem.length} điểm dừng tại toà này
                    {nhomDiem.map((d) => (
                      <div key={d.stop_id} className="mt-0.5 font-semibold text-slate-600">
                        {moTaDi(d)}
                      </div>
                    ))}
                  </div>
                </Popup>
              )}
            </Marker>
          );
        })}

        {children}
      </MapContainer>

      {showLegend && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[1000] rounded-t-lg bg-surface/90 backdrop-blur px-2.5 py-1 text-center text-[11px] font-semibold text-muted shadow-sm">
          {coDuongThat
            ? lo_trinh_meta
              ? `Đường đi thật OSRM · ${lo_trinh_meta.total_km} km · ~${lo_trinh_meta.total_minutes} phút`
              : "Đường đi thật theo dữ liệu OSRM."
            : "Nối thẳng giữa các điểm — chưa phải quãng đường thực tế."}
        </div>
      )}
    </div>
  );
}
