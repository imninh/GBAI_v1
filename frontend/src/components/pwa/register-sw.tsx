"use client";

/** Đăng ký service worker + bắt sự kiện "cài được app".
 *
 * `beforeinstallprompt` bắn **một lần và rất sớm**, thường trước khi màn Tôi
 * hay trang /tai-app kịp mount. Nên sự kiện được giữ ở biến cấp module do
 * `RegisterSW` (mount trong layout, sống suốt phiên) bắt lấy, còn các màn khác
 * đọc qua `useCaiApp`.
 */

import * as React from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let suKienCai: BeforeInstallPromptEvent | null = null;
const nguoiNghe = new Set<() => void>();

function baoThayDoi() {
  nguoiNghe.forEach((fn) => fn());
}

/** Đang chạy ở chế độ đã cài (standalone) hay còn trong tab trình duyệt. */
export function dangChayDangApp(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    // iOS Safari không theo chuẩn display-mode, dùng cờ riêng.
    (window.navigator as { standalone?: boolean }).standalone === true
  );
}

/**
 * Trả về `[caiDuoc, cai]`. `caiDuoc` false khi trình duyệt chưa cho cài
 * (iOS Safari, hoặc app đã cài rồi) — lúc đó màn hình nên chỉ dẫn thủ công.
 */
export function useCaiApp(): [boolean, () => Promise<void>] {
  const caiDuoc = React.useSyncExternalStore(
    (onChange) => {
      nguoiNghe.add(onChange);
      return () => nguoiNghe.delete(onChange);
    },
    () => suKienCai !== null,
    () => false, // phía máy chủ luôn coi như chưa cài được
  );

  const cai = React.useCallback(async () => {
    if (!suKienCai) return;
    await suKienCai.prompt();
    await suKienCai.userChoice;
    // Sự kiện chỉ dùng được một lần.
    suKienCai = null;
    baoThayDoi();
  }, []);

  return [caiDuoc, cai];
}

export function RegisterSW() {
  React.useEffect(() => {
    const batCai = (e: Event) => {
      // Chặn thanh gợi ý mặc định để tự đặt nút vào đúng chỗ trong giao diện.
      e.preventDefault();
      suKienCai = e as BeforeInstallPromptEvent;
      baoThayDoi();
    };
    const daCai = () => {
      suKienCai = null;
      baoThayDoi();
    };

    window.addEventListener("beforeinstallprompt", batCai);
    window.addEventListener("appinstalled", daCai);

    // Chỉ đăng ký khi chạy thật: bản dev của Next thay đổi tài nguyên liên tục,
    // cache-first sẽ phục vụ file cũ và làm việc sửa giao diện trở nên khó hiểu.
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Không đăng ký được thì app vẫn chạy bình thường, chỉ mất phần offline.
      });
    }

    return () => {
      window.removeEventListener("beforeinstallprompt", batCai);
      window.removeEventListener("appinstalled", daCai);
    };
  }, []);

  return null;
}
