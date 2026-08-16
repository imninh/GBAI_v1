/**
 * Module thu thập và gửi toạ độ GPS của người thu gom thời gian thực lên máy chủ.
 *
 * Tính năng:
 * - watchPosition với độ chính xác cao (GPS chip).
 * - Lọc nhiễu: chỉ gửi khi di chuyển >= 5m hoặc sau mỗi 3.5 giây.
 * - Tự động đệm toạ độ (buffer) khi mất mạng 4G và gửi bù khi có mạng.
 */

import { API_URL, getToken } from "@/lib/api";

interface GPSPayload {
  route_id: number;
  lat: number;
  lng: number;
  accuracy_m?: number;
  speed_mps?: number | null;
  heading?: number | null;
  recorded_at: string;
}

let watchId: number | null = null;
let activeRouteId: number | null = null;
let lastSentPosition: { lat: number; lng: number; time: number } | null = null;
const offlineBuffer: GPSPayload[] = [];
let isFlushing = false;

/** Tính khoảng cách Haversine (mét) giữa 2 toạ độ */
function distanceMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000; // Bán kính Trái Đất (m)
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

async function sendGPSPayload(payload: GPSPayload): Promise<boolean> {
  try {
    const token = getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${API_URL}/api/v1/tracking/gps`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      credentials: "include",
    });
    return res.ok;
  } catch (err) {
    console.debug("Lỗi gửi GPS lên server (mất mạng?):", err);
    return false;
  }
}

async function flushOfflineBuffer() {
  if (isFlushing || offlineBuffer.length === 0) return;
  isFlushing = true;

  while (offlineBuffer.length > 0) {
    const payload = offlineBuffer[0];
    const success = await sendGPSPayload(payload);
    if (success) {
      offlineBuffer.shift();
    } else {
      break; // Vẫn chưa có mạng
    }
  }

  isFlushing = false;
}

/**
 * Bắt đầu theo dõi và truyền vị trí GPS xe thu gom
 */
export function startGPSTracker(routeId: number) {
  if (typeof window === "undefined" || !("geolocation" in navigator)) {
    console.warn("Thiết bị hoặc trình duyệt không hỗ trợ Geolocation API");
    return;
  }

  if (watchId !== null && activeRouteId === routeId) {
    return; // Đã đang tracking route này
  }

  stopGPSTracker();
  activeRouteId = routeId;

  // Lắng nghe sự kiện online để xả buffer
  window.addEventListener("online", flushOfflineBuffer);

  watchId = navigator.geolocation.watchPosition(
    async (pos) => {
      const { latitude, longitude, accuracy, speed, heading } = pos.coords;
      const now = Date.now();

      // Kiểm tra bộ lọc khoảng cách và thời gian
      if (lastSentPosition) {
        const dist = distanceMeters(
          lastSentPosition.lat,
          lastSentPosition.lng,
          latitude,
          longitude
        );
        const elapsedMs = now - lastSentPosition.time;

        // Chỉ gửi nếu di chuyển >= 4m HOẶC đã qua 3000ms
        if (dist < 4 && elapsedMs < 3000) {
          return;
        }
      }

      const payload: GPSPayload = {
        route_id: routeId,
        lat: latitude,
        lng: longitude,
        accuracy_m: accuracy || undefined,
        speed_mps: speed != null && !isNaN(speed) ? speed : undefined,
        heading: heading != null && !isNaN(heading) ? heading : undefined,
        recorded_at: new Date(pos.timestamp).toISOString(),
      };

      lastSentPosition = { lat: latitude, lng: longitude, time: now };

      const ok = await sendGPSPayload(payload);
      if (!ok) {
        // Lưu tạm vào offline buffer (tối đa 500 điểm)
        if (offlineBuffer.length < 500) {
          offlineBuffer.push(payload);
        }
      } else {
        // Nếu vừa gửi thành công và có buffer cũ, xả tiếp
        if (offlineBuffer.length > 0) {
          flushOfflineBuffer();
        }
      }
    },
    (err) => {
      console.warn("Lỗi đọc GPS thiết bị:", err.message);
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 2000,
    }
  );
}

/**
 * Dừng theo dõi GPS
 */
export function stopGPSTracker() {
  if (typeof window !== "undefined" && watchId !== null) {
    navigator.geolocation.clearWatch(watchId);
    window.removeEventListener("online", flushOfflineBuffer);
  }
  watchId = null;
  activeRouteId = null;
  lastSentPosition = null;
}

/**
 * Kiểm tra trạng thái tracker
 */
export function isGPSTracking(): boolean {
  return watchId !== null;
}
