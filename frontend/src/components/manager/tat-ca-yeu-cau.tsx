"use client";

/** Liệt kê MỌI yêu cầu thu gom — không giới hạn trạng thái.
 *
 *  Hàng đợi duyệt (PickupQueue) và màn Xếp tuyến mỗi cái chỉ hiện một lát cắt
 *  của máy trạng thái; yêu cầu ở `da_nhan`/`hoan_tat`/`da_giao_don_vi` không màn
 *  nào hiện, nên người quản lý tưởng là mất. Màn này là chỗ nhìn toàn bộ: chip
 *  lọc trạng thái + phân trang đều đổ qua `api.pickups` đã có sẵn — không thêm
 *  endpoint mới.
 */

import * as React from "react";

import { Card, Chip, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { kg, ngayGioVn, TRANG_THAI_YEU_CAU } from "@/lib/format";
import { IconXeThuGom } from "@/lib/icons";
import { NHAN_TRANG_THAI_YEU_CAU, type TrangThaiYeuCau } from "@/lib/pickup-states";
import type { PickupRequest } from "@/lib/types";

const PAGE_SIZE = 20;

/** Chip lọc — "Tất cả" là chuỗi rỗng để không gửi tham số `status` lên server. */
const LOC_TRANG_THAI: { key: TrangThaiYeuCau | ""; label: string }[] = [
  { key: "", label: "Tất cả" },
  { key: "cho_duyet", label: NHAN_TRANG_THAI_YEU_CAU.cho_duyet },
  { key: "cho_nhan", label: NHAN_TRANG_THAI_YEU_CAU.cho_nhan },
  { key: "da_nhan", label: NHAN_TRANG_THAI_YEU_CAU.da_nhan },
  { key: "dang_van_chuyen", label: NHAN_TRANG_THAI_YEU_CAU.dang_van_chuyen },
  { key: "da_giao_don_vi", label: NHAN_TRANG_THAI_YEU_CAU.da_giao_don_vi },
  { key: "tranh_chap", label: NHAN_TRANG_THAI_YEU_CAU.tranh_chap },
  { key: "hoan_tat", label: NHAN_TRANG_THAI_YEU_CAU.hoan_tat },
  { key: "tu_choi", label: NHAN_TRANG_THAI_YEU_CAU.tu_choi },
  { key: "da_huy", label: NHAN_TRANG_THAI_YEU_CAU.da_huy },
];

function BadgeTrangThai({ status }: { status: TrangThaiYeuCau }) {
  const tt = TRANG_THAI_YEU_CAU[status];
  const Icon = tt.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-extrabold ${tt.className}`}>
      <Icon className="h-3.5 w-3.5" />
      {NHAN_TRANG_THAI_YEU_CAU[status]}
    </span>
  );
}

export function TatCaYeuCau() {
  const [loc, setLoc] = React.useState<TrangThaiYeuCau | "">("");
  const [trang, setTrang] = React.useState(1);
  const [du, setDu] = React.useState<{ items: PickupRequest[]; total: number } | null>(null);
  const [loi, setLoi] = React.useState("");

  const tai = React.useCallback(() => {
    setLoi("");
    const thamSo: Record<string, string | number> = { page: trang, page_size: PAGE_SIZE };
    if (loc) thamSo.status = loc;
    api
      .pickups(thamSo)
      .then((d) => setDu({ items: d.items, total: d.total }))
      .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được danh sách yêu cầu."));
  }, [loc, trang]);

  React.useEffect(() => {
    setDu(null);
    tai();
  }, [tai]);

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (du === null) return <Skeleton className="h-96 w-full" />;

  const tongTrang = Math.max(1, Math.ceil(du.total / PAGE_SIZE));

  return (
    <>
      <div className="mb-3 flex items-center gap-2.5">
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Tất cả yêu cầu</div>
        <span className="rounded-lg border border-line-3 bg-console-bg px-2.5 py-1 text-xs font-bold text-muted">
          {du.total} yêu cầu
        </span>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {LOC_TRANG_THAI.map((m) => (
          <button
            key={m.key || "tat-ca"}
            onClick={() => {
              setLoc(m.key);
              setTrang(1);
            }}
            className="cursor-pointer rounded-full"
            aria-pressed={loc === m.key}
          >
            <Chip tone={loc === m.key ? "leaf" : "neutral"}>{m.label}</Chip>
          </button>
        ))}
      </div>

      {du.items.length === 0 ? (
        <EmptyState
          icon={IconXeThuGom}
          title="Không có yêu cầu nào"
          hint={loc ? "Chưa có yêu cầu nào ở trạng thái này." : "Chưa có yêu cầu thu gom nào."}
        />
      ) : (
          <Card className="overflow-hidden p-0 lg:max-h-[calc(100vh-16rem)] lg:overflow-y-auto">
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-line bg-cream-soft text-[11px] font-extrabold uppercase tracking-wide text-muted lg:sticky lg:top-0 lg:z-10">
                <th className="px-4 py-2.5">Mã</th>
                <th className="px-4 py-2.5">Cư dân</th>
                <th className="px-4 py-2.5">Căn / địa chỉ</th>
                <th className="px-4 py-2.5">Khối lượng</th>
                <th className="px-4 py-2.5">Trạng thái</th>
                <th className="px-4 py-2.5">Ngày gửi</th>
              </tr>
            </thead>
            <tbody>
              {du.items.map((yc) => (
                <tr key={yc.id} className="border-b border-line last:border-b-0 hover:bg-cream-soft">
                  <td className="px-4 py-3 font-extrabold text-bulky tabular-nums">#PR-{String(yc.id).padStart(4, "0")}</td>
                  <td className="px-4 py-3 font-bold">{yc.resident?.full_name ?? "—"}</td>
                  <td className="px-4 py-3 font-semibold text-muted">
                    {yc.unit ? `Căn ${yc.unit} · ` : ""}
                    {yc.building || "—"}
                  </td>
                  <td className="px-4 py-3 font-extrabold tabular-nums">{kg(yc.est_weight_kg)}</td>
                  <td className="px-4 py-3">
                    <BadgeTrangThai status={yc.status} />
                  </td>
                  <td className="px-4 py-3 text-[12px] font-semibold text-muted tabular-nums">{ngayGioVn(yc.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex items-center justify-between border-t border-line bg-cream-soft px-4 py-3">
            <span className="text-[12px] font-bold text-muted">
              Trang {trang}/{tongTrang} · tổng {du.total} yêu cầu
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setTrang((t) => Math.max(1, t - 1))}
                disabled={trang <= 1}
                className="cursor-pointer rounded-2xl border border-line-2 bg-surface px-3 py-1.5 text-[12px] font-bold text-ink-soft disabled:cursor-not-allowed disabled:opacity-40"
              >
                ‹ Trước
              </button>
              <button
                onClick={() => setTrang((t) => Math.min(tongTrang, t + 1))}
                disabled={trang >= tongTrang}
                className="cursor-pointer rounded-2xl border border-line-2 bg-surface px-3 py-1.5 text-[12px] font-bold text-ink-soft disabled:cursor-not-allowed disabled:opacity-40"
              >
                Sau ›
              </button>
            </div>
          </div>
        </Card>
      )}
    </>
  );
}
