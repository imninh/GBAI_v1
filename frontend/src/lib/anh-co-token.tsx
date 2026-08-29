"use client";

/** Ảnh lấy từ endpoint CÓ XÁC THỰC.
 *
 *  `GET /api/v1/media/{id}` đòi header `Authorization: Bearer …`
 *  (`src/api/routers/media.py:36`). Thẻ `<img>` **không bao giờ** gửi header
 *  đó, nên mọi chỗ gắn thẳng `mediaUrl(id)` vào `src` của thẻ `<img>` đều nhận
 *  401 và hiện ảnh vỡ. Đo trên bản deploy thật ngày 11/08: `/api/v1/media/1`
 *  không token → HTTP 401.
 *
 *  Vì vậy phải tải bằng `fetch` kèm token, đổi ra `blob:` rồi mới gắn vào `src`.
 */

import * as React from "react";

import { API_URL, ApiError, getToken } from "@/lib/api";

// Nền giữ chỗ dùng lại đúng token sọc đang có ở màn "Ảnh của bạn được xử lý thế
// nào" (personal.tsx) — không đặt màu mới.
const NEN_SOC = "bg-[repeating-linear-gradient(135deg,var(--color-skeleton),var(--color-skeleton)_8px,var(--color-skeleton-deep)_8px,var(--color-skeleton-deep)_16px)]";
const NOI_THAT = "flex h-full w-full items-center justify-center p-2 text-center text-xs font-semibold";

function cauLoi(status: number): string {
  if (status === 401 || status === 403) return "Không xem được ảnh này.";
  if (status === 410) return "Ảnh đã hết hạn lưu trữ và được xoá tự động.";
  return "Không tải được ảnh.";
}

export function AnhCoToken({
  mediaId,
  alt,
  className,
}: {
  mediaId: number | null;
  alt: string;
  className?: string;
}): React.ReactElement {
  const [nguon, setNguon] = React.useState<string | null>(null);
  const [loi, setLoi] = React.useState("");
  // URL blob: đang hiển thị. Trình duyệt giữ nguyên cả blob trong bộ nhớ cho tới
  // khi ai đó `revokeObjectURL` — không theo dõi nó thì mỗi lần tải là một lần rò.
  const nguonCu = React.useRef<string | null>(null);

  React.useEffect(() => {
    if (mediaId == null) return;
    let huy = false;
    setLoi("");
    fetch(`${API_URL}/api/v1/media/${mediaId}`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    })
      .then(async (res) => {
        if (!res.ok) throw new ApiError(cauLoi(res.status), "IMG", res.status);
        return res.blob();
      })
      .then((blob) => {
        if (huy) return;
        const moi = URL.createObjectURL(blob);
        // Thứ tự bắt buộc: thu hồi URL CŨ đúng lúc thay bằng URL mới, trong cùng
        // một nhịp microtask với `setNguon` — trình duyệt không kịp vẽ một khung
        // trắng giữa chừng. Thu hồi vào chỗ khác (như cleanup chạy khi mediaId
        // đổi) sẽ làm ảnh đang hiện trắng; còn không thu hồi thì mỗi lần làm mới
        // lại rò một blob trong bộ nhớ.
        if (nguonCu.current) URL.revokeObjectURL(nguonCu.current);
        nguonCu.current = moi;
        setNguon(moi);
      })
      .catch((e) => {
        if (!huy) setLoi(e instanceof Error ? e.message : "Không tải được ảnh.");
      });
    // Cờ `huy` đã chặn setState sau khi rời màn. Riêng URL blob phải thu hồi —
    // cái cuối cùng chỉ còn trong tay ref, và lúc này component đã tháo khỏi DOM
    // nên không còn thẻ `<img>` nào trỏ tới nó để làm trắng.
    return () => {
      huy = true;
      if (nguonCu.current) URL.revokeObjectURL(nguonCu.current);
      nguonCu.current = null;
    };
  }, [mediaId]);

  if (mediaId == null) {
    // Không có id thì không có gì để tải — không gọi mạng một lần nào.
    return <div className={`${NOI_THAT} bg-muted-bg text-muted`}>Không có ảnh để xem</div>;
  }
  if (loi) {
    return <div className={`${NOI_THAT} ${NEN_SOC} text-ink-faint`}>{loi}</div>;
  }
  if (!nguon) {
    return <div className={`h-full w-full ${NEN_SOC}`} />;
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={nguon} alt={alt} className={className} />;
}
