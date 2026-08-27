"use client";

/** Trung tâm thông báo in-app — bell + sheet, dùng chung cho 3 vai.
 *
 *  Poll 45s + khi cửa sổ focus; một vòng poll duy nhất cho cả app (module
 *  singleton), mọi `BellButton`/`NotificationSheet` cùng đọc một nguồn. Đánh
 *  dấu đọc xong thì sheet tự `taiLai()` để badge cập nhật ngay.
 */

import * as React from "react";

import { Mascot } from "@/components/resident/onboarding";
import { api } from "@/lib/api";
import { IconChuong, IconTuChoi } from "@/lib/icons";
import { useSession } from "@/lib/session";

export type NotifItem = {
  id: number;
  title: string;
  body: string;
  entity: string;
  entity_id: string;
  read: boolean;
  created_at: string;
};

/** Đích deep-link sau khi chạm một thông báo — null = không có màn tương ứng. */
export type NotifyTarget =
  | "resident:requests"
  | "resident:me"
  | "cleaner:route"
  | "manager:queues"
  | null;

const POLL_MS = 45_000;

/** `entity` → màn đích theo vai (đúng bảng NHAN_DIEN). Chưa biết → null. */
export function notifyTarget(entity: string, role: string | null): NotifyTarget {
  switch (entity) {
    case "pickup_request":
    case "yeu_cau_thu_gom":
      if (role === "manager") return "manager:queues";
      if (role === "cleaner") return null;
      return "resident:requests";
    case "pickup_route":
      if (role === "cleaner") return "cleaner:route";
      if (role === "manager") return null;
      return "resident:requests";
    case "phien_thung":
      return role === "resident" ? "resident:me" : null;
    case "su_co_thu_gom":
      return role === "manager" ? "manager:queues" : null;
    default:
      return null;
  }
}

/** Thời gian relative — "vừa xong · X phút · X giờ · dd/MM". */
export function gioTuongDoi(iso: string): string {
  const thoiDiem = new Date(iso);
  if (Number.isNaN(thoiDiem.getTime())) return "";
  const phut = Math.floor((Date.now() - thoiDiem.getTime()) / 60_000);
  const dd = `${String(thoiDiem.getDate()).padStart(2, "0")}/${String(thoiDiem.getMonth() + 1).padStart(2, "0")}`;
  if (phut < 1) return `vừa xong · ${dd}`;
  if (phut < 60) return `${phut} phút · ${dd}`;
  if (phut < 1440) return `${Math.floor(phut / 60)} giờ · ${dd}`;
  return dd;
}

// --- Bộ nhớ dùng chung (một vòng poll cho cả app) ---------------------------

let _items: NotifItem[] = [];
let _unread = 0;
const _subs = new Set<() => void>();
let _batDau = false;

function _dangKyLai() {
  for (const sub of _subs) sub();
}

async function _tai() {
  try {
    const d = await api.notifications();
    _items = d.items;
    _unread = d.unread;
  } catch {
    // Lỗi mạng — giữ trạng thái cũ, lượt poll sau tự phục hồi.
  }
  _dangKyLai();
}

function _khoiDongPoll() {
  if (_batDau) return;
  _batDau = true;
  void _tai();
  // Một vòng poll duy nhất sống suốt phiên app — không nhân bản theo từng
  // component, nên interval không cần giữ biến để cleanup.
  setInterval(() => void _tai(), POLL_MS);
  const onFocus = () => {
    if (!document.hidden) void _tai();
  };
  window.addEventListener("focus", onFocus);
  document.addEventListener("visibilitychange", onFocus);
}

function useNotificationStore() {
  const [, force] = React.useReducer((x: number) => x + 1, 0);
  React.useEffect(() => {
    _khoiDongPoll();
    _subs.add(force);
    return () => {
      _subs.delete(force);
    };
  }, []);
  const taiLai = React.useCallback(() => void _tai(), []);
  return { items: _items, unread: _unread, taiLai };
}

// --- Bell -------------------------------------------------------------------

export function BellButton({ onOpen }: { onOpen: () => void }) {
  const { unread } = useNotificationStore();
  return (
    <button
      type="button"
      aria-label="Thông báo"
      onClick={onOpen}
      className="relative flex h-11 w-11 flex-none cursor-pointer items-center justify-center rounded-full border border-line bg-surface shadow-[0_2px_8px_rgba(20,40,25,.06)]"
    >
      <IconChuong className="h-5 w-5 text-ink" />
      {unread > 0 && (
        <span className="absolute right-2.5 top-2.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-hazard px-1 text-[10px] font-extrabold text-white ring-2 ring-white">
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </button>
  );
}

// --- Sheet ------------------------------------------------------------------

export function NotificationSheet({
  onClose,
  onNavigate,
}: {
  onClose: () => void;
  onNavigate: (target: NotifyTarget) => void;
}) {
  const { items, unread, taiLai } = useNotificationStore();
  const { user } = useSession();
  const [dangGui, setDangGui] = React.useState(false);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function danhDauHet() {
    if (dangGui || unread === 0) return;
    setDangGui(true);
    try {
      await api.notificationsRead(null);
      await taiLai();
    } finally {
      setDangGui(false);
    }
  }

  async function moItem(item: NotifItem) {
    try {
      await api.notificationsRead([item.id]);
    } catch {
      // Đọc lỗi vẫn cho đi tiếp — thông báo là nguồn phụ, không chặn hành động.
    }
    await taiLai();
    onNavigate(notifyTarget(item.entity, user?.role ?? null));
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-end justify-center bg-black/40 backdrop-blur-xs sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Thông báo"
      onClick={onClose}
    >
      <div
        className="animate-gbappear flex max-h-[85dvh] w-full max-w-[480px] flex-col overflow-hidden rounded-t-2xl bg-surface sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* đầu sheet */}
        <div className="flex flex-none items-center gap-2 border-b border-line px-5 py-3.5">
          <span className="flex-1 font-[family-name:var(--font-display)] text-[18px] font-bold text-ink">
            Thông báo
          </span>
          {unread > 0 && (
            <button
              type="button"
              onClick={() => void danhDauHet()}
              disabled={dangGui}
              className="cursor-pointer rounded-full bg-leaf-soft px-3 py-1.5 text-[12px] font-bold text-leaf-dark disabled:opacity-50"
            >
              Đánh dấu tất cả đã đọc
            </button>
          )}
          <button
            type="button"
            aria-label="Đóng thông báo"
            onClick={onClose}
            className="flex h-9 w-9 flex-none cursor-pointer items-center justify-center rounded-full border border-line-3 bg-surface text-ink"
          >
            <IconTuChoi className="h-4 w-4" />
          </button>
        </div>

        {/* danh sách */}
        <div className="gb-scroll flex-1 overflow-y-auto">
          {items.length === 0 ? (
            <div className="px-6 py-10 text-center">
              <Mascot size={120} tuThe="nup-la" className="mx-auto mb-3" />
              <p className="text-sm font-semibold text-muted">Không có thông báo nào</p>
            </div>
          ) : (
            items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => void moItem(item)}
                className={`flex w-full cursor-pointer items-start gap-3 border-b border-line/60 px-5 py-3.5 text-left transition-colors hover:bg-cream-soft active:scale-[0.99] ${
                  item.read ? "" : "bg-leaf-soft/25"
                }`}
              >
                <span
                  className={`mt-1.5 h-2 w-2 flex-none rounded-full ${item.read ? "bg-transparent" : "bg-leaf"}`}
                />
                <span className="min-w-0 flex-1">
                  <span
                    className={`block ${item.read ? "text-[14px] font-semibold text-ink-soft" : "text-[14px] font-bold text-ink"}`}
                  >
                    {item.title}
                  </span>
                  {item.body ? (
                    <span className="mt-0.5 block text-[13px] font-medium leading-snug text-ink-soft">{item.body}</span>
                  ) : null}
                  <span className="mt-1 block text-[11px] font-semibold text-muted">
                    {gioTuongDoi(item.created_at)}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}