"use client";

/** Khung ứng dụng: app cho cư dân + nhân viên thu gom, console cho đơn vị thu gom.
 *
 *  Trước đây hai khung này vẽ **thiết bị giả** — viền điện thoại, đồng hồ 9:41,
 *  thanh URL `console.greenbin.vn`. Đó là bản dựng thiết kế, không phải sản
 *  phẩm. Nay app chiếm trọn khung nhìn thật.
 *
 *  Responsive:
 *  - < lg (1024px): cột 560px giữa màn, có border-x và shadow, tab bar dưới đáy
 *  - >= lg: full width, sidebar trái 240px, nội dung bên phải, không tab bar
 */

import * as React from "react";

import { IconQuayLai } from "@/lib/icons";
import { cn } from "@/lib/utils";

export function PhoneFrame({
  children,
  bg = "var(--color-cream)",
  statusDark = false,
  tabBar,
  items,
  active,
  onChange,
  accent,
}: {
  children: React.ReactNode;
  bg?: string;
  statusDark?: boolean;
  tabBar?: React.ReactNode;
  items?: TabItem[];
  active?: string;
  onChange?: (key: string) => void;
  accent?: string;
}) {
  return (
    <div
      data-dark={statusDark || undefined}
      className="flex h-dvh w-full flex-col overflow-hidden bg-cream"
      style={{ background: bg }}
    >
      <div className="flex h-dvh w-full flex-col lg:flex-row lg:overflow-hidden">
        {/* Sidebar trái: chỉ dựng khi có điều hướng. Dưới lg ẩn bằng CSS; từ lg
            chiếm 240px. Màn nào ẩn tab bar thì `items` cũng được bỏ đi — khung
            không vẽ sidebar, chỉ còn cột nội dung dàn đầy. */}
        {items && active && onChange ? (
          <aside className="hidden lg:flex lg:w-[240px] lg:flex-none lg:flex-col lg:border-r lg:border-line-3 lg:bg-cream-soft">
            <SideNav
              items={items}
              active={active}
              onChange={onChange}
              accent={accent}
              header={
                <span className="flex items-center gap-2">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src="/logo/chinh.svg"
                    alt=""
                    aria-hidden="true"
                    className="h-7 w-7 object-contain"
                  />
                  <span className="font-[family-name:var(--font-display)] text-base font-bold tracking-tight">
                    GreenBin<span className="text-leaf"> AI</span>
                  </span>
                </span>
              }
            />
          </aside>
        ) : null}

        {/* Cột nội dung — MỘT bản nội dung duy nhất cho mọi bề rộng. Dưới lg:
            cột 560px giữa màn, viền hai bên, tab bar dưới đáy. Từ lg: dàn đầy
            phần còn lại cạnh sidebar, `sm:max-w-[560px]` bị huỷ, không tab bar. */}
        <div className="flex flex-1 flex-col overflow-hidden sm:mx-auto sm:max-w-[560px] sm:border-x sm:border-line-3 sm:shadow-[var(--shadow-lg)] lg:mx-0 lg:max-w-none lg:border-0 lg:shadow-none">
          <div className="gb-scroll flex-1 overflow-y-auto overflow-x-hidden">{children}</div>
          {tabBar ? <div className="flex-none lg:hidden">{tabBar}</div> : null}
        </div>
      </div>
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
  accent = "var(--color-leaf)",
}: {
  items: TabItem[];
  active: string;
  onChange: (key: string) => void;
  accent?: string;
}) {
  return (
    <div className="z-30 flex h-[86px] flex-none items-start border-t border-line/60 bg-surface/90 px-3 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl shadow-[0_-4px_20px_rgba(22,33,26,0.03)]">
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
            style={{ color: isActive ? accent : "var(--color-muted)" }}
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

/** Thanh điều hướng dọc cho desktop (lg trở lên).
 *  Dùng chung kiểu TabItem với TabBar để cùng một mảng tabs cấp cho cả hai.
 *  - raised: trên mobile là nút tròn nổi, trên desktop thành nút bình thường có nhãn
 *  - badge: hiển thị được như TabBar
 *  - aria-current / aria-label: giữ đúng trợ năng
 */
export function SideNav({
  items,
  active,
  onChange,
  accent = "var(--color-leaf)",
  header,
}: {
  items: TabItem[];
  active: string;
  onChange: (key: string) => void;
  accent?: string;
  header?: React.ReactNode;
}) {
  return (
    <>
      {header && (
        <div className="flex h-14 items-center justify-center border-b border-line-3 bg-cream px-3">
          {header}
        </div>
      )}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-1" aria-label="Điều hướng chính">
        {items.map((item) => {
          const isActive = item.key === active;
          if (item.raised) {
            return (
              <button
                key={item.key}
                onClick={() => onChange(item.key)}
                aria-label={item.label}
                className="w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-bold transition-all duration-200 ease-[var(--ease-spring)] select-none cursor-pointer active:scale-[0.98] bg-transparent"
                style={{ color: isActive ? accent : "var(--color-muted)" }}
                aria-current={isActive ? "page" : undefined}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "flex h-8 w-8 flex-none items-center justify-center rounded-full transition-all duration-300 ease-[var(--ease-spring)]",
                    isActive ? "bg-leaf-soft text-leaf-dark shadow-[var(--shadow-xs)]" : "hover:bg-black/5"
                  )}
                >
                  {item.icon}
                </span>
                <span className={cn("flex-1 truncate transition-all", isActive ? "font-extrabold text-ink" : "font-bold text-muted")}>
                  {item.label}
                </span>
                {item.badge ? (
                  <span className="flex-none rounded-md bg-hazard px-2 py-0.5 text-[10px] font-extrabold text-white shadow-xs">
                    {item.badge}
                  </span>
                ) : null}
              </button>
            );
          }
          return (
            <button
              key={item.key}
              onClick={() => onChange(item.key)}
              className="w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-bold transition-all duration-200 ease-[var(--ease-spring)] select-none cursor-pointer active:scale-[0.98] bg-transparent"
              style={{ color: isActive ? accent : "var(--color-muted)" }}
              aria-current={isActive ? "page" : undefined}
              aria-label={`Điều hướng ${item.label}`}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "flex h-8 w-8 flex-none items-center justify-center rounded-full transition-all duration-300 ease-[var(--ease-spring)]",
                  isActive ? "bg-leaf-soft text-leaf-dark shadow-[var(--shadow-xs)]" : "hover:bg-black/5"
                )}
              >
                {item.icon}
              </span>
              <span className={cn("flex-1 truncate transition-all", isActive ? "font-extrabold text-ink" : "font-bold text-muted")}>
                {item.label}
              </span>
              {item.badge ? (
                <span className="flex-none rounded-md bg-hazard px-2 py-0.5 text-[10px] font-extrabold text-white shadow-xs">
                  {item.badge}
                </span>
              ) : null}
            </button>
          );
        })}
      </nav>
    </>
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
          className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border border-line-3 bg-surface text-ink shadow-[var(--shadow-xs)] transition-all duration-200 ease-[var(--ease-spring)] hover:scale-105 hover:shadow-[var(--shadow-sm)] active:scale-95"
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
