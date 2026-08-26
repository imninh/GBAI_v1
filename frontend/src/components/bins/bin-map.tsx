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
    "background:var(--color-muted-bg);color:var(--color-ink-faint);border:1.5px dotted var(--color-line-faint);font-weight:400;opacity:.8",
};

function icon(bin: Bin) {
  // WS-4: không còn "?" — thùng nào cũng hiện nhãn thật (phần trăm đầy, hoặc
  // "–" khi chưa có số liệu). "Mất kết nối / số liệu cũ" được phân biệt bằng
  // style (nét đứt + nhạt) và title, không phải bằng dấu hỏi.
  const label =
    bin.fill_percent != null
      ? `${Math.round(bin.fill_percent)}%`
      : bin.status === "chua_trien_khai"
        ? "chưa"
        : "–";
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
  html: `<div style="width:14px;height:14px;margin:3px;border-radius:999px;background:var(--color-noi-thung);border:3px solid oklch(1 0 0);box-shadow:0 0 0 4px oklch(0.55 0.2 255 / .35)"></div>`,
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
  duongDi = null,
  loiDuongDi = null,
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
  /** Hình đường đi thật để vẽ; null thì vẽ đoạn thẳng mốc→thùng như cũ. */
  duongDi?: [number, number][] | null;
  /** Thông báo lỗi đường đi (OSRM tắt/hỏng, hoặc bin chưa có toạ độ). Khi có,
   *  KHÔNG vẽ đường thẳng giả — chỉ hiện banner (E2E-03b: không im lặng). */
  loiDuongDi?: string | null;
}) {
  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={[21.0285, 105.8522]}
        zoom={15}
        scrollWheelZoom
        className="h-full w-full relative z-0 isolate"
      >
        <TileLayer
          attribution='&copy; Google Maps'
          url="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}&hl=vi&gl=VN"
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
        {/* Có lỗi đường đi → KHÔNG vẽ đường giả, chỉ hiện banner (xử lý phía
            dưới). Có几何 thật (≥2 điểm) → vẽ polyline OSRM. Không có gì cả (chưa
            xin xong) → vẽ đoạn thẳng nét đứt mốc→thùng làm bản xem trước. */}
        {!loiDuongDi && duongDi && duongDi.length >= 2 ? (
          <Polyline positions={duongDi} pathOptions={{ color: '#1f6feb', weight: 4, opacity: 0.85 }} />
        ) : (
          !loiDuongDi &&
          tuMoc &&
          selected &&
          hasCoords(selected) && (
            <Polyline
              positions={[
                [tuMoc.lat, tuMoc.lng],
                [selected.lat, selected.lng],
              ]}
              pathOptions={{ color: '#1f6feb', weight: 4, opacity: 0.7, dashArray: "1 8" }}
            />
          )
        )}
        {onMapClick && <BatSuKienCham onMapClick={onMapClick} />}
        <Recenter bin={selected} />
      </MapContainer>
      {loiDuongDi && (
        <div className="pointer-events-none absolute left-1/2 top-3 z-[500] -translate-x-1/2 rounded-full bg-hazard-soft px-3 py-1.5 text-[12px] font-bold text-hazard-dark shadow-[0_4px_14px_rgba(0,0,0,.18)]">
          {loiDuongDi}
        </div>
      )}
    </div>
  );
}
