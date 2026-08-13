"use client";

import { useEffect } from "react";
import { MapContainer, Marker, Polyline, TileLayer, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Bin } from "@/lib/bins";
import { hasCoords, STATUS_LABEL } from "@/lib/bins";

const MARKER_STYLE: Record<Bin["status"], string> = {
  can_gom:
    "background:var(--warn);color:var(--warn-foreground);border:2px solid var(--warn);font-weight:700;box-shadow:0 4px 12px oklch(0.62 0.19 42 / .45)",
  het_pin:
    "background:var(--power-soft);color:var(--power);border:2px solid var(--power);font-weight:600",
  mat_ket_noi:
    "background:var(--stale-soft);color:var(--stale);border:1.5px dashed var(--stale);font-weight:400;opacity:.75",
  binh_thuong:
    "background:oklch(1 0 0);color:var(--ok);border:1px solid var(--ok);font-weight:500",
  // Xám nhạt nét CHẤM — khác hẳn nét ĐỨT của "mất kết nối": chưa triển khai là
  // trạng thái bình thường, không báo động.
  chua_trien_khai:
    "background:#eef1ec;color:#5a6b5f;border:1.5px dotted #c3cbc2;font-weight:400;opacity:.8",
};

function icon(bin: Bin) {
  const label =
    bin.status === "mat_ket_noi" || bin.status === "chua_trien_khai"
      ? "?"
      : `${Math.round(bin.fill_percent)}%`;
  return L.divIcon({
    className: "bin-marker-icon",
    iconSize: [46, 30],
    iconAnchor: [23, 15],
    html: `<div title="${bin.code} · ${STATUS_LABEL[bin.status]}" style="${MARKER_STYLE[bin.status]};display:flex;align-items:center;justify-content:center;width:46px;height:30px;border-radius:999px;font-size:12px;font-family:var(--font-sans)">${label}</div>`,
  });
}

function Recenter({ bin }: { bin: Bin | null }) {
  const map = useMap();
  useEffect(() => {
    // Thùng chưa có toạ độ thì không có gì để bay tới.
    if (bin && hasCoords(bin)) map.setView([bin.lat, bin.lng], 16, { animate: true });
  }, [bin, map]);
  return null;
}

// Chấm người dùng tự đặt. Cố tình khác hẳn marker thùng — không có con số, hình
// giọt nước có mũi nhọn chỉ đúng điểm chạm — để không ai nhầm nó là thùng thật.
const ICON_DANH_DAU = L.divIcon({
  className: "bin-marker-icon",
  iconSize: [22, 22],
  iconAnchor: [11, 22],
  html: `<div style="width:18px;height:18px;margin:2px;border-radius:999px 999px 999px 0;transform:rotate(-45deg);background:var(--color-ink);border:2px solid oklch(1 0 0);box-shadow:0 2px 6px oklch(0 0 0 / .35)"></div>`,
});

// Chấm "vị trí của bạn" — xanh dương có vòng sáng, khác hẳn marker thùng và chấm mốc
// tự đặt, để người dùng nhận ra ngay đâu là mình.
const ICON_VI_TRI_TOI = L.divIcon({
  className: "bin-marker-icon",
  iconSize: [20, 20],
  iconAnchor: [10, 10],
  html: `<div style="width:14px;height:14px;margin:3px;border-radius:999px;background:#1f6feb;border:3px solid oklch(1 0 0);box-shadow:0 0 0 4px oklch(0.55 0.2 255 / .35)"></div>`,
});

/** Bắt cú chạm lên nền bản đồ. Chỉ được gắn khi cha truyền `onMapClick`, nên
 *  bản đồ điều phối không đăng ký listener nào và hành vi của nó không đổi. */
function BatSuKienCham({ onMapClick }: { onMapClick: (lat: number, lng: number) => void }) {
  useMapEvents({
    click: (e) => onMapClick(e.latlng.lat, e.latlng.lng),
  });
  return null;
}

export default function BinMap({
  bins,
  selected,
  onSelect,
  onMapClick,
  diemDanhDau = null,
  viTriNguoiDung = null,
  tuMoc = null,
}: {
  bins: Bin[];
  selected: Bin | null;
  onSelect: (bin: Bin) => void;
  /** Có truyền thì bản đồ bắt cú chạm lên nền. Không truyền thì bản đồ giữ
   *  nguyên hành vi cũ — `/dieu-phoi` không được đổi một chút nào. */
  onMapClick?: (lat: number, lng: number) => void;
  /** Chấm người dùng vừa đặt. KHÔNG phải một cái thùng, chỉ là một điểm. */
  diemDanhDau?: { lat: number; lng: number } | null;
  /** Vị trí GPS của người dùng — chấm "bạn ở đây". Chỉ hiện khi có. */
  viTriNguoiDung?: { lat: number; lng: number } | null;
  /** Điểm gốc để nối đường tới thùng đang chọn (nơi ở / GPS / mốc tự thêm). */
  tuMoc?: { lat: number; lng: number } | null;
}) {
  return (
    <MapContainer
      center={[21.0285, 105.8522]}
      zoom={15}
      scrollWheelZoom
      className="h-full w-full"
    >
      <TileLayer
        attribution='&copy; OpenStreetMap, &copy; CARTO'
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
      />
      {/* Chỉ vẽ thùng đã có toạ độ — `lat`/`lng` được phép null trong API. */}
      {bins.filter(hasCoords).map((bin) => (
        <Marker
          key={bin.code}
          position={[bin.lat, bin.lng]}
          icon={icon(bin)}
          eventHandlers={{ click: () => onSelect(bin) }}
        />
      ))}
      {diemDanhDau && (
        <Marker position={[diemDanhDau.lat, diemDanhDau.lng]} icon={ICON_DANH_DAU} />
      )}
      {viTriNguoiDung && (
        <Marker position={[viTriNguoiDung.lat, viTriNguoiDung.lng]} icon={ICON_VI_TRI_TOI} />
      )}
      {tuMoc && selected && hasCoords(selected) && (
        <Polyline
          positions={[
            [tuMoc.lat, tuMoc.lng],
            [selected.lat, selected.lng],
          ]}
          pathOptions={{ color: "#1f6feb", weight: 4, opacity: 0.7, dashArray: "1 8" }}
        />
      )}
      {onMapClick && <BatSuKienCham onMapClick={onMapClick} />}
      <Recenter bin={selected} />
    </MapContainer>
  );
}
