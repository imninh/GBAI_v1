"use client";

/** Thẻ "Cài app lên máy" dùng chung cho màn Tôi của cư dân và đội vệ sinh.
 *
 * Tự ẩn khi đang chạy bản đã cài — không ai muốn thấy lời mời cài một thứ mình
 * đang mở.
 */

import * as React from "react";

import { dangChayDangApp, useCaiApp } from "@/components/pwa/register-sw";
import { Card } from "@/components/ui/primitives";
import { IconCaiApp, IconTaiVe, IconTiepTuc } from "@/lib/icons";

export function CaiAppCard({ className }: { className?: string }) {
  const [caiDuoc, cai] = useCaiApp();
  const [daCai, setDaCai] = React.useState(true); // giả định đã cài cho tới khi biết chắc

  React.useEffect(() => setDaCai(dangChayDangApp()), []);

  if (daCai) return null;

  return (
    <Card className={`mb-3.5 overflow-hidden p-0 ${className ?? ""}`}>
      {caiDuoc ? (
        <button
          onClick={cai}
          className="flex w-full cursor-pointer items-center gap-3 border-b border-[#f2ede2] px-4 py-4 text-left"
        >
          <IconCaiApp className="h-[18px] w-[18px] text-leaf" />
          <span className="flex-1">
            <span className="block text-sm font-bold">Cài GreenBin lên máy</span>
            <span className="block text-xs font-semibold text-muted">Mở nhanh hơn, xem lịch được cả khi mất mạng</span>
          </span>
          <IconTiepTuc className="h-[18px] w-[18px] text-[#c3cbc2]" />
        </button>
      ) : null}
      <a href="/tai-app" className="flex items-center gap-3 px-4 py-4">
        <IconTaiVe className="h-[18px] w-[18px] text-muted" />
        <span className="flex-1 text-sm font-bold">Cách cài trên Android / iPhone</span>
        <IconTiepTuc className="h-[18px] w-[18px] text-[#c3cbc2]" />
      </a>
    </Card>
  );
}
