"use client";

/** Bản đồ tuyến thu gom — vẽ đúng toạ độ thật của từng điểm dừng.
 *
 * Bản cũ dùng SVG vẽ tay, chia đều điểm từ trái sang phải nên KHÔNG mang thông
 * tin địa lý — trông như bản đồ nhưng chỉ là trang trí. Bản này vẽ Leaflet
 * thật, lấy toạ độ từ gói C2a. ``ssr:false`` qua ``next/dynamic`` là bắt buộc vì
 * dự án build ``output: "export"`` mà Leaflet chạm thẳng vào ``window``.
 */

import { useEffect } from "react";
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import type { RouteStop } from "@/lib/types";

/** Backend C2a trả thêm ``lat``/``lng`` cho từng điểm dừng, nhưng interface
 *  ``RouteStop`` dùng chung chưa khai báo hai trường đó. Đọc qua kiểu mở rộng
 *  này để bản đồ dùng được mà không phải sửa type chung. */
interface StopToaDo extends RouteStop {
  lat: number | null;
  lng: number | null;
}

/** Điểm dừng chưa có toạ độ thì không vẽ — không bao giờ thay bằng 0,0. */
function coToaDo(stop: RouteStop): stop is StopToaDo & { lat: number; lng: number } {
  const co = stop as StopToaDo;
  return typeof co.lat === "number" && typeof co.lng === "number";
}

function markerIcon(stop: StopToaDo & { lat: number; lng: number }) {
  const laThung = stop.stop_kind === "thung";
  const nen = laThung ? "#f0b429" : "#7b5cd6";
  const mau = laThung ? "#5a4410" : "#ffffff";
  return L.divIcon({
    className: "route-stop-marker",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html: `<div style="display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:999px;background:${nen};color:${mau};font-size:12px;font-weight:800;font-family:var(--font-sans);box-shadow:0 2px 6px rgba(0,0,0,.3);border:2px solid #ffffff">${stop.seq}</div>`,
  });
}

function moTaDi(diem: StopToaDo & { lat: number; lng: number }) {
  if (diem.stop_kind === "thung") {
    return `${diem.seq} · ${diem.diem_dung_vi}${diem.fill_percent != null ? ` · đầy ${Math.round(diem.fill_percent)}%` : ""}`;
  }
  return `${diem.seq} · ${diem.diem_dung_vi}`;
}

/** Co bản đồ vừa khít toàn bộ điểm dừng — người duyệt không phải kéo tay. */
function VuaKhung({ cacDiem }: { cacDiem: (StopToaDo & { lat: number; lng: number })[] }) {
  const map = useMap();
  useEffect(() => {
    if (cacDiem.length === 0) return;
    map.fitBounds(L.latLngBounds(cacDiem.map((s) => [s.lat, s.lng] as [number, number])), {
      padding: [32, 32],
      maxZoom: 16,
    });
  }, [cacDiem, map]);
  return null;
}

export default function RouteMap({ stops }: { stops: RouteStop[] }) {
  const cacDiem = [...stops].sort((a, b) => a.seq - b.seq).filter(coToaDo);
  // Không có toạ độ nào thì vẽ hộp trống, không vẽ một bản đồ rỗng.
  if (cacDiem.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center rounded-xl bg-cream-soft px-4 text-center text-sm font-semibold text-muted">
        Tuyến chưa có toạ độ để vẽ bản đồ
      </div>
    );
  }
  return (
    <MapContainer center={[21.0285, 105.8522]} zoom={14} scrollWheelZoom className="h-full w-full">
      <TileLayer
        attribution="&copy; OpenStreetMap, &copy; CARTO"
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
      />
      <VuaKhung cacDiem={cacDiem} />
      <Polyline
        positions={cacDiem.map((s) => [s.lat, s.lng] as [number, number])}
        pathOptions={{ color: "#2fae66", weight: 3, dashArray: "6 6" }}
      />
      {cacDiem.map((s) => (
        <Marker key={s.stop_id} position={[s.lat, s.lng] as [number, number]} icon={markerIcon(s)}>
          <Tooltip direction="top" offset={[0, -16]}>
            {moTaDi(s)}
          </Tooltip>
        </Marker>
      ))}
    </MapContainer>
  );
}
