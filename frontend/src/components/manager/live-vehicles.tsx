"use client";

/** Màn "Xe đang chạy" (GOI_3 / M5) — bảng các tuyến đang hoạt động kèm vị trí
 *  GPS mới nhất, tự làm mới mỗi 10 giây. Chọn một tuyến để xem bản đồ điểm dừng.
 *
 *  Vị trí lấy từ `GET /tracking/{route_id}/latest`. Marker xe realtime qua
 *  WebSocket nằm ngoài scope này (xem UNKNOWN ở báo cáo GOI_3). */

import dynamic from "next/dynamic";
import * as React from "react";

import { Button, Card, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { IconXeThuGom } from "@/lib/icons";
import { ngayGioVn, ngayVn, soVn } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { PickupRoute } from "@/lib/types";

const RouteMap = dynamic(() => import("@/components/manager/route-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-2xl" />,
});

const TRANG_THAI_LABEL: Record<string, string> = {
  proposed: "Chờ duyệt",
  approved: "Đang chạy",
  in_progress: "Đang chạy",
  done: "Đã xong",
};

type ViTri = { speed_mps: number | null; recorded_at: string | null } | null;

export function LiveVehiclesScreen() {
  const [ds, setDs] = React.useState<PickupRoute[] | null>(null);
  const [vitri, setVitri] = React.useState<Record<number, ViTri>>({});
  const [chonId, setChonId] = React.useState<number | null>(null);
  const [loi, setLoi] = React.useState("");

  const tai = React.useCallback(() => {
    api
      .routes({ status: "proposed,approved,in_progress" })
      .then(async (d) => {
        // List trả bản nhẹ (thiếu team/stops) → lấy bản đầy đủ từng tuyến để
        // hiện đúng tài xế và vẽ map. Số tuyến đang chạy thường rất ít.
        const full = await Promise.all(
          d.items.map((r) => api.route(r.id).catch(() => r))
        );
        setDs(full);
        const moi: Record<number, ViTri> = {};
        await Promise.all(
          full
            .filter((r) => r.status !== "proposed")
            .map(async (r) => {
              try {
                const p = await api.trackingLatest(r.id);
                moi[r.id] = p.position
                  ? { speed_mps: p.position.speed_mps, recorded_at: p.position.recorded_at }
                  : null;
              } catch {
                moi[r.id] = null;
              }
            })
        );
        setVitri(moi);
      })
      .catch((e) => setLoi(e instanceof Error ? e.message : "Lỗi tải danh sách xe"));
  }, []);

  React.useEffect(() => {
    tai();
    const id = setInterval(tai, 10_000);
    return () => clearInterval(id);
  }, [tai]);

  const chon = ds?.find((r) => r.id === chonId) ?? null;

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (ds === null) return <Skeleton className="h-96 w-full" />;

  return (
    <>
      <div className="mb-4 flex items-center gap-2.5">
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Xe đang chạy</div>
        <span className="rounded-lg border border-line-3 bg-console-bg px-2.5 py-1 text-xs font-bold text-muted">
          làm mới mỗi 10s
        </span>
      </div>

      {ds.length === 0 ? (
        <EmptyState icon={IconXeThuGom} title="Chưa có tuyến nào đang hoạt động" />
      ) : (
        <Card className="overflow-hidden p-0">
          <div className="gb-hscroll">
            <table className="w-full min-w-[760px] text-left text-[13px] font-semibold">
              <thead className="text-xs uppercase text-muted">
                <tr className="border-b border-line-3">
                  <th className="px-4 py-2.5">Tuyến</th>
                  <th className="px-4 py-2.5">Tài xế</th>
                  <th className="px-4 py-2.5">Tốc độ</th>
                  <th className="px-4 py-2.5">Cập nhật cuối</th>
                  <th className="px-4 py-2.5">Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {ds.map((r) => {
                  const v = vitri[r.id];
                  const tocDo = v?.speed_mps != null ? `${soVn(v.speed_mps * 3.6, 0)} km/h` : "—";
                  const dangChon = r.id === chonId;
                  return (
                    <tr
                      key={r.id}
                      onClick={() => setChonId(dangChon ? null : r.id)}
                      className={cn(
                        "cursor-pointer border-b border-line-5 transition-colors hover:bg-cream-soft",
                        dangChon && "bg-leaf-soft/60"
                      )}
                    >
                      <td className="px-4 py-3">
                        <div className="font-extrabold text-ink">{r.window}</div>
                        <div className="text-xs font-semibold text-muted">{ngayVn(r.service_date)}</div>
                      </td>
                      <td className="px-4 py-3 text-ink-soft">{r.team?.full_name ?? "—"}</td>
                      <td className="px-4 py-3 tabular-nums text-ink-soft">{tocDo}</td>
                      <td className="px-4 py-3 text-[12px] text-muted">
                        {v?.recorded_at ? ngayGioVn(v.recorded_at) : "chưa có GPS"}
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded-lg bg-amber-soft px-2 py-0.5 text-xs font-extrabold text-amber">
                          {TRANG_THAI_LABEL[r.status] ?? r.status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {chon && (
        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-bold">
              Bản đồ tuyến · {chon.window} · {ngayVn(chon.service_date)}
            </div>
            <Button size="sm" variant="outline" onClick={() => setChonId(null)}>
              Đóng
            </Button>
          </div>
          <div className="h-[420px] overflow-hidden rounded-2xl border border-line">
            <RouteMap
              stops={chon.stops ?? []}
              duong_di={chon.duong_di}
              lo_trinh_meta={chon.lo_trinh_meta}
              route_id={chon.id}
            />
          </div>
        </div>
      )}
    </>
  );
}
