"use client";

/** Khung ứng dụng: app cho cư dân + nhân viên thu gom, console cho đơn vị thu gom.
 *
 *  Trước đây hai khung này vẽ **thiết bị giả** — viền điện thoại, đồng hồ 9:41,
 *  thanh URL `console.greenbin.vn`. Đó là bản dựng thiết kế, không phải sản
 *  phẩm. Nay app chiếm trọn khung nhìn thật.
 */

import * as React from "react";

import { IconQuayLai } from "@/lib/icons";
import { cn } from "@/lib/utils";

export function PhoneFrame({
  children,
  bg = "#f4f1ea",
  statusDark = false,
  tabBar,
}: {
  children: React.ReactNode;
  bg?: string;
  statusDark?: boolean;
  tabBar?: React.ReactNode;
}) {
  return (
    // `h-dvh` chứ không phải `h-screen`: `100vh` trên trình duyệt di động tính
    // cả phần bị thanh địa chỉ che, đáy màn sẽ bị cắt mất.
    //
    // Từ `sm` trở lên mới bo góc và kẹp bề ngang lại — trên màn rộng mà để app
    // dàn hết 1920px thì mỗi dòng chữ dài cả gang tay. Đây KHÔNG phải vẽ lại
    // viền điện thoại: không viền đen, không tai thỏ, không đồng hồ giả.
    <div
      data-dark={statusDark || undefined}
      className="mx-auto flex h-dvh w-full flex-col overflow-hidden sm:max-w-[560px] sm:border-x sm:border-line-3 sm:shadow-[var(--shadow-lg)]"
      style={{ background: bg }}
    >
      <div className="gb-scroll flex-1 overflow-y-auto overflow-x-hidden">{children}</div>
      {tabBar}
    </div>
  );
}

export interface TabItem {
  key: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
  /** Nút chụp nổi giữa — tròn, nhô lên khỏi thanh, không có nhãn chữ. */
  raised?: boolean;
}

export function TabBar({
  items,
  active,
  onChange,
  accent = "#2fae66",
}: {
  items: TabItem[];
  active: string;
  onChange: (key: string) => void;
  accent?: string;
}) {
  return (
    <div className="z-30 flex h-[86px] flex-none items-start border-t border-line/60 bg-white/90 px-3 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl shadow-[0_-4px_20px_rgba(22,33,26,0.03)]">
      {items.map((item) => {
        const isActive = item.key === active;
        if (item.raised) {
          return (
            <button
              key={item.key}
              onClick={() => onChange(item.key)}
              aria-label="Chụp món rác"
              className="group relative flex flex-1 cursor-pointer items-start justify-center bg-transparent"
            >
              {/* Nút nổi: tròn, màu xanh, nhô lên khỏi thanh để dễ chạm bằng ngón cái. */}
              <span
                className="flex h-[58px] w-[58px] items-center justify-center rounded-full bg-leaf text-white shadow-[var(--shadow-leaf-glow)] transition-all duration-300 ease-[var(--ease-bounce)] group-hover:scale-105 group-active:scale-95"
                style={{ marginTop: "-18px" }}
                aria-hidden="true"
              >
                {item.icon}
              </span>
            </button>
          );
        }
        return (
          <button
            key={item.key}
            onClick={() => onChange(item.key)}
            className="relative flex flex-1 cursor-pointer flex-col items-center gap-1.5 pt-1.5 bg-transparent transition-all duration-200 ease-[var(--ease-spring)] active:scale-95"
            style={{ color: isActive ? accent : "#8a938a" }}
            aria-current={isActive ? "page" : undefined}
            aria-label={`Điều hướng ${item.label}`}
          >
            {/* Trạng thái chọn: pill mềm nở ra sau icon, icon đậm màu hơn. */}
            <span
              aria-hidden="true"
              className={cn(
                "flex h-8 items-center justify-center rounded-full transition-all duration-300 ease-[var(--ease-spring)]",
                isActive ? "w-[54px] bg-leaf-soft text-leaf-dark shadow-[var(--shadow-xs)]" : "w-8 hover:bg-black/5"
              )}
            >
              {item.icon}
            </span>
            {item.badge ? (
              <span className="absolute right-5 top-1 flex h-4 min-w-4 items-center justify-center rounded-full border border-white bg-hazard px-1 text-[10px] font-extrabold text-white shadow-[var(--shadow-xs)]">
                {item.badge}
              </span>
            ) : null}
            <span className={cn("text-[11px] tracking-tight transition-all", isActive ? "font-extrabold text-ink" : "font-bold text-muted")}>
              {item.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** Khung console — nay là cửa sổ thật, không còn vẽ thanh URL giả.
 *
 *  `h-dvh` chứ không phải `h-screen`: trên trình duyệt di động, `100vh` tính cả
 *  phần bị thanh địa chỉ che, làm đáy màn bị cắt mất.
 */
export function BrowserFrame({ children }: { children: React.ReactNode }) {
  return <div className="flex h-dvh w-full flex-col overflow-hidden bg-console-bg">{children}</div>;
}

export function ScreenHeader({
  title,
  onBack,
  right,
  tone = "muted",
}: {
  title: string;
  onBack?: () => void;
  right?: React.ReactNode;
  tone?: "muted" | "hazard";
}) {
  return (
    <div className="flex items-center gap-2.5 px-5 pb-3 pt-2">
      {onBack && (
        <button
          onClick={onBack}
          aria-label="Quay lại"
          className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border border-line-3 bg-white text-ink shadow-[var(--shadow-xs)] transition-all duration-200 ease-[var(--ease-spring)] hover:scale-105 hover:shadow-[var(--shadow-sm)] active:scale-95"
        >
          <IconQuayLai className="h-5 w-5" />
        </button>
      )}
      <span className={cn("text-sm font-bold tracking-tight", tone === "hazard" ? "text-hazard-dark" : "text-ink-soft")}>{title}</span>
      <span className="flex-1" />
      {right}
    </div>
  );
}
