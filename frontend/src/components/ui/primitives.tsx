"use client";

/** Bộ component nền theo lối shadcn/ui, dựng theo đúng ngôn ngữ thị giác của
 *  bản thiết kế: bo góc lớn, viền mảnh, nền kem, chữ Fredoka cho tiêu đề.
 */

import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "@radix-ui/react-slot";
import { type LucideIcon, Loader2 } from "lucide-react";
import * as React from "react";

import { IconCanhBao, IconGapLoi, IconMamXanh } from "@/lib/icons";
import { HoaTiet } from "@/components/ui/pattern";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-[var(--gb-r-md)] font-bold tracking-tight select-none cursor-pointer transition-all duration-250 ease-[var(--ease-spring)] active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none",
  {
    variants: {
      variant: {
        // GOI_FIX / B2 — revert D2: brand green --color-leaf (#548045) + chữ trắng
        // đã đạt WCAG AA (4.61:1). Giữ nền leaf, hover đậm hơn.
        primary: "bg-leaf text-white font-[family-name:var(--font-display)] shadow-[var(--shadow-sm)] hover:bg-leaf-dark hover:shadow-[var(--shadow-md)] hover:-translate-y-0.5",
        leaf: "bg-leaf text-white shadow-[var(--shadow-sm)] hover:bg-leaf-dark hover:shadow-[var(--shadow-leaf-glow)] hover:-translate-y-0.5",
        outline: "bg-surface border-[1.5px] border-line-2 text-ink-soft shadow-[var(--shadow-xs)] hover:border-leaf hover:bg-leaf-soft/30 hover:text-leaf-dark",
        soft: "bg-leaf-soft border-[1.5px] border-leaf-mint/40 text-leaf-dark hover:bg-leaf-soft/80 hover:border-leaf",
        bulky: "bg-bulky-soft border-[1.5px] border-bulky-line text-bulky-dark hover:shadow-[var(--shadow-bulky-glow)] hover:-translate-y-0.5",
        danger: "bg-surface border-[1.5px] border-hazard/30 text-hazard-dark hover:bg-hazard-soft hover:border-hazard",
        ghost: "bg-transparent text-ink-soft hover:bg-black/5 active:bg-black/10",
      },
      size: {
        lg: "px-6 py-4 text-base min-h-[52px]",
        md: "px-4.5 py-3 text-sm min-h-[44px]",
        sm: "px-3.5 py-2 text-xs min-h-[40px]",
        icon: "size-11 p-0 rounded-full",
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
  /** GOI_6 / A7 — hiện spinner + vô hiệu hoá khi đang xử lý. */
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, block, asChild, loading, disabled, children, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        className={cn(
          buttonVariants({ variant, size, block }),
          loading && "opacity-70 cursor-not-allowed",
          className,
        )}
        {...props}
      >
        {asChild ? (
          children
        ) : (
          <>
            {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {children}
          </>
        )}
      </Comp>
    );
  },
);
Button.displayName = "Button";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-[var(--gb-r-lg)] bg-surface border border-line-3 shadow-[var(--shadow-xs)] transition-all duration-300 ease-[var(--ease-spring)] hover:shadow-[var(--shadow-md)] hover:border-line-2",
        className
      )}
      {...props}
    />
  );
}

export function Chip({
  className,
  tone = "neutral",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: "neutral" | "leaf" | "amber" | "hazard" | "recycle" | "bulky" }) {
  const tones = {
    neutral: "bg-muted-bg text-muted-2 border-line-3",
    leaf: "bg-leaf-soft text-leaf-dark border-leaf-mint/40",
    amber: "bg-amber-soft text-amber border-amber-line/60",
    hazard: "bg-hazard-soft text-hazard-dark border-hazard/30",
    recycle: "bg-recycle-soft text-recycle border-recycle/30",
    bulky: "bg-bulky-soft text-bulky-dark border-bulky-line",
  } as const;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[var(--gb-r-full)] px-3 py-1 text-xs font-extrabold tracking-wide border shadow-[0_1px_2px_rgba(28,44,70,0.02)] transition-colors duration-200",
        tones[tone],
        className
      )}
      {...props}
    />
  );
}

export function SectionLabel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("text-xs font-extrabold uppercase tracking-wider text-muted mb-2", className)} {...props} />;
}

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("skeleton-shimmer rounded-xl", className)} suppressHydrationWarning {...props} />;
}

/** Trạng thái rỗng — phân biệt "chưa có gì bao giờ" với "không có kết quả sau lọc". */
export function EmptyState({
  icon: Icon = IconMamXanh,
  title,
  hint,
  action,
  minhHoa,
}: {
  icon?: LucideIcon;
  title: string;
  hint?: string;
  action?: React.ReactNode;
  /** Minh hoạ tuỳ chọn (vd mascot Bini pose `nup-la`) — hiện thay cho icon. */
  minhHoa?: React.ReactNode;
}) {
  return (
    <div className="relative flex flex-col items-center justify-center gap-2.5 overflow-hidden px-6 py-12 text-center animate-gbfade">
      {/* Hoạ tiết nền — ở rìa, dưới nội dung, không nhận sự kiện chuột. */}
      <HoaTiet loai="rings" className="inset-0 h-full w-full" />
      <HoaTiet loai="dots" className="right-6 bottom-5 h-16 w-16" />
      <div className="relative z-10 flex flex-col items-center gap-2.5">
        {minhHoa ? (
          <div className="mb-1">{minhHoa}</div>
        ) : (
          <div className="flex h-16 w-16 items-center justify-center rounded-[var(--gb-r-lg)] bg-cream-soft shadow-[var(--shadow-xs)]">
            <Icon className="h-8 w-8 text-muted" strokeWidth={1.8} />
          </div>
        )}
        <div className="font-[family-name:var(--font-display)] text-lg font-bold tracking-tight">{title}</div>
        {hint && <p className="max-w-xs text-xs font-semibold leading-relaxed text-muted">{hint}</p>}
        {action && <div className="mt-2">{action}</div>}
      </div>
    </div>
  );
}

/** Trạng thái lỗi — câu tiếng Việt dễ hiểu, nút thử lại, mã lỗi ngắn để tra log. */
export function ErrorState({ message, code, onRetry }: { message: string; code?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-[var(--gb-r-lg)] border border-hazard/30 bg-hazard-soft px-6 py-8 text-center shadow-[var(--shadow-xs)] animate-gbfade">
      <div className="flex h-12 w-12 items-center justify-center rounded-[var(--gb-r-md)] bg-surface shadow-[var(--shadow-xs)]">
        <IconGapLoi className="h-6 w-6 text-hazard-dark" strokeWidth={1.8} />
      </div>
      <div className="text-sm font-bold text-hazard-dark">{message}</div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Thử lại
        </Button>
      )}
      {code && <div className="text-xs font-bold tracking-wider text-muted">mã lỗi: {code}</div>}
    </div>
  );
}

/** Băng cảnh báo suy giảm một phần — pipeline chạy xong nhưng một node lỗi. */
export function DegradedBanner({ note }: { note: string }) {
  return (
    <div className="flex gap-2.5 rounded-2xl border border-amber-line bg-amber-soft px-4 py-3 text-xs font-bold leading-relaxed text-amber shadow-[var(--shadow-xs)]">
      <IconCanhBao className="mt-0.5 h-4 w-4 flex-none" />
      <span>{note}</span>
    </div>
  );
}

/** Nhãn cho dữ liệu demo mô phỏng. Số mô phỏng và số đo thật không được trộn
 *  vào nhau mà không nói gì. */
export function SeedBadge({ className }: { className?: string }) {
  return (
    <span className={cn("rounded-md bg-muted-bg border border-line-3 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-muted", className)}>
      dữ liệu demo mô phỏng
    </span>
  );
}

/** GOI_6 / A6 — Input primitive thay thế style inline rải rác.
 *  Quy ước: cao 48px, viền line-2, focus ring xanh, lỗi chuyển hazard. */
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
  label?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ error, label, className, id, ...props }, ref) => {
    const reactId = React.useId();
    const inputId = id || `input-${reactId}`;
    return (
      <div className="flex flex-col gap-1">
        {label && (
          <label htmlFor={inputId} className="text-sm font-semibold text-ink">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "h-12 w-full rounded-[var(--gb-r-md)] border-[1.5px] border-line-2 bg-surface px-4 text-[15px] font-semibold text-ink outline-none transition-shadow",
            "focus:ring-2 focus:ring-leaf focus:border-leaf placeholder:text-ink/40",
            error && "border-hazard focus:ring-hazard",
            className,
          )}
          {...props}
        />
      </div>
    );
  },
);
Input.displayName = "Input";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ error, className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "w-full rounded-[var(--gb-r-md)] border-[1.5px] border-line-2 bg-surface px-4 py-3 text-[15px] font-semibold text-ink outline-none transition-shadow min-h-[120px] resize-none",
        "focus:ring-2 focus:ring-leaf focus:border-leaf placeholder:text-ink/40",
        error && "border-hazard focus:ring-hazard",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";
