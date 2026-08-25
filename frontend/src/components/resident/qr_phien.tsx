"use client";

/** Màn mở phiên bỏ rác từ mã QR dán trên thùng.
 *
 *  Người dùng quét QR tới `/?ma=<mã>`; `page.tsx` đọc mã ngay khi vào trang,
 *  giữ qua bước đăng nhập rồi đưa vào đây sau khi đã có user. App chỉ DÙNG
 *  mã — xin mã là việc của thiết bị: đường xin-mã xác thực bằng khoá thiết bị,
 *  app gọi vào luôn 401, nên ở đây chỉ tiêu thụ mã đọc từ URL.
 *
 *  Câu lỗi hiện NGUYÊN VĂN `ApiError.message_vi`, không ánh xạ lại: backend
 *  thêm câu mới thì màn hình tự hiểu, không phải sửa client.
 */

import * as React from "react";

import { Button, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { ngayGioVn } from "@/lib/format";
import { IconKhungGio, IconNhomRacMacDinh } from "@/lib/icons";
import type { PhienBoRac } from "@/lib/types";

/** Chìa khoá sessionStorage giữ mã QR qua bước đăng nhập. sessionStorage chứ
 *  không localStorage: mã dùng MỘT lần, không nên sống sót qua phiên trình duyệt. */
export const KHOA_MA_QR = "greenbin_ma_qr";

export function QrPhienScreen({ ma, onDong }: { ma: string; onDong: () => void }) {
  const [phien, setPhien] = React.useState<PhienBoRac | null>(null);
  const [loi, setLoi] = React.useState<{ message: string; code: string } | null>(null);
  const [dangMo, setDangMo] = React.useState(true);

  React.useEffect(() => {
    let huy = false;
    api
      .batDauPhienBangMa(ma)
      .then((p) => {
        if (!huy) setPhien(p);
      })
      .catch((e) => {
        if (!huy)
          setLoi({
            message: e instanceof ApiError ? e.message : "Có lỗi khi mở phiên.",
            code: e instanceof ApiError ? e.code : "APP-500",
          });
      })
      .finally(() => {
        // Mã đã tiêu — dù thành công hay thất bại — xoá khỏi storage ngay:
        // F5 hay đăng nhập lại sau này đều không tái sử dụng được.
        window.sessionStorage.removeItem(KHOA_MA_QR);
        if (!huy) setDangMo(false);
      });
    return () => {
      huy = true;
    };
  }, [ma]);

  if (dangMo) {
    return (
      <div className="flex min-h-full w-full flex-col items-center justify-center gap-3 px-6 text-center">
        <IconNhomRacMacDinh className="h-9 w-9 animate-pulse text-muted" strokeWidth={1.8} />
        <Skeleton className="h-5 w-44" />
        <Skeleton className="h-4 w-60" />
      </div>
    );
  }

  if (loi || !phien) {
    return (
      <div className="flex min-h-full w-full flex-col items-center justify-center px-6 pb-10 pt-14">
        {/* Không nút Thử lại: mã chỉ dùng một lần, gọi lại chỉ nhận thêm
            "Mã QR đã được sử dụng" vô cớ. */}
        <ErrorState message={loi?.message ?? "Mở phiên không thành công."} code={loi?.code} />
        <Button block variant="outline" className="mt-6" onClick={onDong}>
          Về trang chủ
        </Button>
      </div>
    );
  }

  return (
    <div className="flex min-h-full w-full flex-col items-center justify-center px-6 pb-10 pt-14 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-leaf-soft text-leaf-dark">
        <IconNhomRacMacDinh className="h-7 w-7" strokeWidth={1.8} />
      </div>
      <h1 className="mb-1.5 font-[family-name:var(--font-display)] text-[26px] font-bold leading-tight">
        Phiên bỏ rác đã mở
      </h1>
      <p className="mb-6 text-[13px] font-semibold leading-snug text-muted">
        Phiên đang ghi nhận từng món bạn bỏ vào thùng.
      </p>

      <div className="w-full max-w-xs rounded-2xl border border-line-3 bg-surface p-5 shadow-[var(--shadow-xs)]">
        <div className="text-[11px] font-extrabold uppercase tracking-wider text-muted">Mã phiên</div>
        <div className="mt-0.5 break-all font-mono text-[15px] font-bold">{phien.ma_phien}</div>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="rounded-xl bg-cream px-2 py-2.5">
            <div className="font-[family-name:var(--font-display)] text-lg font-bold leading-tight">{phien.so_vat}</div>
            <div className="text-[10px] font-bold uppercase tracking-wide text-muted">món đã bỏ</div>
          </div>
          <div className="rounded-xl bg-leaf-soft px-2 py-2.5">
            <div className="font-[family-name:var(--font-display)] text-lg font-bold leading-tight text-leaf-dark">
              {phien.diem_nhan_thuc}
            </div>
            <div className="text-[10px] font-bold uppercase tracking-wide text-leaf-dark">điểm nhận thức</div>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-center gap-1.5 text-[12px] font-semibold text-muted">
          <IconKhungGio className="h-3.5 w-3.5" strokeWidth={1.8} />
          Bắt đầu {ngayGioVn(phien.bat_dau)}
        </div>
      </div>

      {/* Điểm nhận thức ≠ điểm xanh: loại điểm này chỉ xếp hạng/huy hiệu, không
          đổi quà. Nói rõ để người dùng không chờ điểm xanh tăng lên oan. */}
      <p className="mt-3 max-w-xs text-[11px] font-semibold leading-relaxed text-muted">
        Điểm nhận thức chỉ phục vụ xếp hạng — điểm xanh đổi quà tính riêng.
      </p>

      <Button block variant="outline" className="mt-6" onClick={onDong}>
        Về trang chủ
      </Button>
    </div>
  );
}
