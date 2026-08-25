/** Hoạ tiết nền tái dùng (F4.4b).
 *
 *  Chỉ là lớp trang trí: ``absolute`` · ``pointer-events-none`` · ``aria-hidden``,
 *  opacity thấp sẵn, và phải được đặt **dưới** nội dung (gọi trước khối chữ trong
 *  cùng container, hoặc dùng ``-z-10``). Không bao giờ nằm lên chữ đang đọc.
 */

import { cn } from "@/lib/utils";

const FILE: Record<string, string> = {
  rings: "/pattern/growth-rings.svg",
  blob: "/pattern/contour-blob.svg",
  dots: "/pattern/organic-dots.svg",
};

/** Opacity mặc định theo loại — nhạt, quiet (NHAN_DIEN §8). */
const OPACITY: Record<string, string> = {
  rings: "opacity-[0.05]",
  blob: "opacity-[0.10]",
  dots: "opacity-[0.35]",
};

export function HoaTiet({
  loai,
  className,
}: {
  loai: "rings" | "blob" | "dots";
  className?: string;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={FILE[loai]}
      alt=""
      aria-hidden="true"
      className={cn("pointer-events-none absolute select-none", OPACITY[loai], className)}
    />
  );
}