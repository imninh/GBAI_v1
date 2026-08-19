"use client";

/** Bộ component nền theo lối shadcn/ui, dựng theo đúng ngôn ngữ thị giác của
 *  bản thiết kế: bo góc lớn, viền mảnh, nền kem, chữ Fredoka cho tiêu đề.
 */

import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "@radix-ui/react-slot";
import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { IconCanhBao, IconGapLoi, IconMamXanh } from "@/lib/icons";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-2xl font-bold transition disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer",
  {
    variants: {
      variant: {
        primary: "bg-ink text-white font-[family-name:var(--font-display)] shadow-[0_10px_24px_-10px_rgba(15,30,18,.5)] hover:bg-[#0d1611]",
        leaf: "bg-leaf text-white hover:bg-leaf-dark",
        outline: "bg-white border-[1.5px] border-line-2 text-ink-soft hover:border-muted",
        soft: "bg-leaf-soft border-[1.5px] border-leaf-soft text-leaf-dark hover:bg-[#dcefe3]",
        bulky: "bg-bulky-soft border-[1.5px] border-[#d9cef0] text-bulky-dark",
        danger: "bg-white border-[1.5px] border-[#f6cdb8] text-hazard-dark hover:bg-hazard-soft",
        ghost: "bg-transparent text-ink-soft hover:bg-black/5",
      },
      size: {
        // Đội vệ sinh dùng ngoài nắng, đeo găng: nút tối thiểu 48px, chữ ≥16px.
        lg: "px-5 py-4 text-base min-h-12",
        md: "px-4 py-3 text-sm",
        sm: "px-3 py-2 text-[13px]",
        // Nút vuông chỉ chứa icon (nút đóng panel, nút thu gọn…). Vẫn giữ 36px
        // để ngón tay đeo găng bấm được.
        icon: "size-9 p-0",
      },
      block: { true: "w-full", false: "" },
    },
    defaultVariants: { variant: "primary", size: "md", block: false },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, block, asChild, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size, block }), className)} {...props} />;
  },
);
Button.displayName = "Button";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-[20px] bg-white border border-line", className)} {...props} />;
}

export function Chip({
  className,
  tone = "neutral",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: "neutral" | "leaf" | "amber" | "hazard" | "recycle" | "bulky" }) {
  const tones = {
    neutral: "bg-[#eef1ec] text-muted-2",
    leaf: "bg-leaf-soft text-leaf-dark",
    amber: "bg-amber-soft text-amber",
    hazard: "bg-hazard-soft text-hazard-dark",
    recycle: "bg-recycle-soft text-recycle",
    bulky: "bg-bulky-soft text-bulky-dark",
  } as const;
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-extrabold", tones[tone], className)}
      {...props}
    />
  );
}

export function SectionLabel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("text-[13px] font-bold text-muted mb-2", className)} {...props} />;
}

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-xl bg-black/[0.06]", className)} suppressHydrationWarning {...props} />;
}

/** Trạng thái rỗng — phân biệt "chưa có gì bao giờ" với "không có kết quả sau lọc". */
export function EmptyState({
  icon: Icon = IconMamXanh,
  title,
  hint,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <Icon className="h-8 w-8 text-muted" strokeWidth={1.8} />
      <div className="font-[family-name:var(--font-display)] text-lg font-bold">{title}</div>
      {hint && <p className="max-w-xs text-[13px] font-semibold text-muted">{hint}</p>}
      {action}
    </div>
  );
}

/** Trạng thái lỗi — câu tiếng Việt dễ hiểu, nút thử lại, mã lỗi ngắn để tra log. */
export function ErrorState({ message, code, onRetry }: { message: string; code?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-[#f6cdb8] bg-hazard-soft px-6 py-8 text-center">
      <IconGapLoi className="h-7 w-7 text-hazard-dark" strokeWidth={1.8} />
      <div className="text-sm font-bold text-hazard-dark">{message}</div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Thử lại
        </Button>
      )}
      {code && <div className="text-[11px] font-bold text-muted">mã lỗi: {code}</div>}
    </div>
  );
}

/** Băng cảnh báo suy giảm một phần — pipeline chạy xong nhưng một node lỗi. */
export function DegradedBanner({ note }: { note: string }) {
  return (
    <div className="flex gap-2 rounded-2xl border border-amber-line bg-amber-soft px-4 py-3 text-[13px] font-bold leading-relaxed text-amber">
      <IconCanhBao className="mt-0.5 h-4 w-4 flex-none" />
      <span>{note}</span>
    </div>
  );
}

/** Nhãn cho dữ liệu demo mô phỏng. Số mô phỏng và số đo thật không được trộn
 *  vào nhau mà không nói gì. */
export function SeedBadge({ className }: { className?: string }) {
  return (
    <span className={cn("rounded-md bg-[#eef1ec] px-2 py-0.5 text-[10px] font-extrabold text-muted", className)}>
      dữ liệu demo mô phỏng
    </span>
  );
}
