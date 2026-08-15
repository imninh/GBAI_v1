"use client";

/** Bản đồ tuyến thu gom — vẽ đúng toạ độ thật của từng điểm dừng.
 *
 * Bản cũ dùng SVG vẽ tay, chia đều điểm từ trái sang phải nên KHÔNG mang thông
 * tin địa lý — trông như bản đồ nhưng chỉ là trang trí. Bản này vẽ Leaflet
 * thật, lấy toạ độ từ gói C2a. ``ssr:false`` qua ``next/dynamic`` là bắt buộc vì
 * dự án build ``output: "export"`` mà Leaflet chạm thẳng vào ``window``.
 *
 * Từ gói P26: nhận thêm ``duong_di`` (hình đường đi thật từ OSRM, do backend
 * trả) — có ≥ 2 điểm thì vẽ đường liền nét thay cho nét đứt đường chim bay.
 * Cũng gộp các điểm dừng trùng toạ độ thành một chấm: toạ độ gắn theo toà nhà
 * nên nhiều căn cùng toà chồng khít nhau, dời chấm là bịa vị trí — gộp lại và
 * nói rõ mới là trung thực.
 */

import { useEffect } from "react";
import { MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import type { LoTrinhMeta, RouteStop } from "@/lib/types";
import LiveTracking from "./live-tracking";

/** Backend C2a trả thêm ``lat``/``lng`` cho từng điểm dừng, nhưng interface
 *  ``RouteStop`` dùng chung chưa khai báo hai trường đó. Đọc qua kiểu mở rộng
 *  này để bản đồ dùng được mà không phải sửa type chung. */
interface StopToaDo extends RouteStop {
  lat: number | null;
  lng: number | null;
}

type ToaDoDuongDi = [number, number];

/** Điểm dừng chưa có toạ độ thì không vẽ — không bao giờ thay bằng 0,0. */
function coToaDo(stop: RouteStop): stop is StopToaDo & { lat: number; lng: number } {
  const co = stop as StopToaDo;
  return typeof co.lat === "number" && typeof co.lng === "number";
}

/** Huy hiệu cho một nhóm điểm dừng (một chấm trên bản đồ). Nhiều điểm trùng
 *  toạ độ thì nhãn ghi đủ số thứ tự, vd "1,2". */
function markerIconNhom(nhom: (StopToaDo & { lat: number; lng: number })[]) {
  const laThung = nhom.some((s) => s.stop_kind === "thung");
  const nen = laThung ? "#f0b429" : "#7b5cd6";
  const mau = laThung ? "#5a4410" : "#ffffff";
  const nhan = nhom.map((s) => s.seq).join(",");
  return L.divIcon({
    className: "route-stop-marker",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html: `<div style="display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:999px;background:${nen};color:${mau};font-size:${nhom.length > 1 ? 10 : 12}px;font-weight:800;font-family:var(--font-sans);box-shadow:0 2px 6px rgba(0,0,0,.3);border:2px solid #ffffff">${nhan}</div>`,
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

export default function RouteMap({
  stops,
  duong_di,
  lo_trinh_meta,
  route_id,
}: {
  stops: RouteStop[];
  duong_di?: ToaDoDuongDi[] | null;
  lo_trinh_meta?: LoTrinhMeta | null;
  route_id?: number | null;
}) {
  const cacDiem = [...stops].sort((a, b) => a.seq - b.seq).filter(coToaDo);
  // Không có toạ độ nào thì vẽ hộp trống, không vẽ một bản đồ rỗng.
  if (cacDiem.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center rounded-xl bg-cream-soft px-4 text-center text-sm font-semibold text-muted">
        Tuyến chưa có toạ độ để vẽ bản đồ
      </div>
    );
  }

  // Vẽ đường thật CHỈ khi có ít nhất 2 điểm: OSRM có thể trả một hình đường
  // hợp lệ nhưng chỉ 1 điểm (mọi điểm dừng rơi vào cùng một vị trí). Polyline
  // một điểm vẽ ra không gì, mà bỏ nét đứt đi thì bản đồ trống trơn kèm câu
  // chú giải sai — nên ngưỡng là >= 2, dưới đó vẫn dùng nét đứt và câu chú giải
  // trung thực.
  const hinhDuongDi = Array.isArray(duong_di) ? duong_di : [];
  const coDuongThat = hinhDuongDi.length >= 2;

  // Gộp điểm trùng toạ độ: một chấm cho cả nhóm, nhãn ghi đủ số thứ tự, popup
  // liệt kê tất cả điểm dừng ở đó.
  const nhom: Record<string, (StopToaDo & { lat: number; lng: number })[]> = {};
  for (const diem of cacDiem) {
    const khoa = `${diem.lat},${diem.lng}`;
    (nhom[khoa] ??= []).push(diem);
  }
  const cacNhom = Object.values(nhom);

  return (
    <div className="relative h-full w-full">
      <MapContainer center={[21.0285, 105.8522]} zoom={14} scrollWheelZoom className="h-full w-full">
        <TileLayer
          attribution="&copy; OpenStreetMap, &copy; CARTO"
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        />
        <VuaKhung cacDiem={cacDiem} />
        {coDuongThat ? (
          <Polyline positions={hinhDuongDi} pathOptions={{ color: "#2fae66", weight: 3 }} />
        ) : (
          <Polyline
            positions={cacDiem.map((s) => [s.lat, s.lng] as ToaDoDuongDi)}
            pathOptions={{ color: "#2fae66", weight: 3, dashArray: "6 6" }}
          />
        )}
        {cacNhom.map((nhomDiem) => {
          const [dau] = nhomDiem;
          return (
            <Marker key={dau.stop_id} position={[dau.lat, dau.lng] as ToaDoDuongDi} icon={markerIconNhom(nhomDiem)}>
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
        {route_id != null && <LiveTracking routeId={route_id} />}
      </MapContainer>
      {/* Chú giải ngay dưới bản đồ — nét thẳng mà không nói gì là để người xem
          tự hiểu nhầm xe chạy được như thế. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[1000] rounded-t-lg bg-white/85 px-2 py-0.5 text-center text-[11px] font-semibold text-muted">
        {coDuongThat
          ? lo_trinh_meta
            ? `Đường đi thật theo dữ liệu OSRM · ${lo_trinh_meta.total_km} km · ~${lo_trinh_meta.total_minutes} phút`
            : "Đường đi thật theo dữ liệu OSRM."
          : "Nối thẳng giữa các điểm — chưa phải quãng đường thực tế."}
      </div>
    </div>
  );
}
