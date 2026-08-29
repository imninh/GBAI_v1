/**
 * Hàng đợi hành động offline cho luồng đội vệ sinh (GOI_1: C2/C3).
 *
 * Khi mất mạng, các hành động "đánh dấu đã thu" (COMPLETE_STOP) và "báo sự cố"
 * (REPORT_INCIDENT) được lưu vào localStorage và gửi bù khi có mạng trở lại.
 * Mô phỏng theo pattern đệm GPS trong `gps-tracker.ts` (flush tuần tự, không
 * gửi song song để tránh race). Không đổi logic nghiệp vụ — chỉ là lớp truyền bù.
 */

import { api } from "@/lib/api";

const OFFLINE_ACTIONS_KEY = "greenbin_offline_actions";
const MAX_RETRY = 3;

export interface OfflineAction {
  id: string;
  type: "COMPLETE_STOP" | "REPORT_INCIDENT";
  payload: Record<string, unknown>;
  retryCount: number;
  createdAt: number;
}

function readAll(): OfflineAction[] {
  try {
    return JSON.parse(localStorage.getItem(OFFLINE_ACTIONS_KEY) || "[]");
  } catch {
    return [];
  }
}

function writeAll(actions: OfflineAction[]) {
  localStorage.setItem(OFFLINE_ACTIONS_KEY, JSON.stringify(actions));
}

export function queueAction(action: OfflineAction) {
  const all = readAll();
  all.push(action);
  writeAll(all);
}

function removeAction(id: string) {
  writeAll(
    readAll().filter((a) => a.id !== id)
  );
}

let flushing = false;

/** Gửi bù toàn bộ hành động đang chờ. An toàn gọi nhiều lần (guard re-entrancy). */
export async function flushOfflineActions() {
  if (flushing) return;
  const actions = readAll();
  if (actions.length === 0) return;

  flushing = true;
  try {
    for (const action of actions) {
      try {
        if (action.type === "COMPLETE_STOP") {
          const p = action.payload;
          await api.completeStop(
            p.route_id as number,
            p.stop_id as number,
            (p.data as Record<string, unknown>) ?? {}
          );
        } else if (action.type === "REPORT_INCIDENT") {
          await api.baoSuCo(action.payload as unknown as Parameters<typeof api.baoSuCo>[0]);
        }
        removeAction(action.id);
      } catch {
        action.retryCount += 1;
        if (action.retryCount >= MAX_RETRY) {
          // Bỏ sau 3 lần thử — tránh kẹt vĩnh viễn (vd: dữ liệu hỏng).
          removeAction(action.id);
        } else {
          writeAll(actions);
        }
      }
    }
  } finally {
    flushing = false;
  }
}

let registered = false;

/** Gắn listener 'online' một lần để tự động đồng bộ khi có mạng lại. */
export function registerOfflineFlush() {
  if (registered || typeof window === "undefined") return;
  registered = true;
  window.addEventListener("online", () => {
    void flushOfflineActions();
  });
}
