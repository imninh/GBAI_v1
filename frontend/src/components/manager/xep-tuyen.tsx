"use client";

/** Màn "Xếp tuyến" của BQL — WS-2: trung tâm điều phối hai cột.
 *
 *  Cột trái là BẢN ĐỒ tuyến tối ưu (polyline từ `duong_di` PyVRP; thiếu đường
 *  thật thì nối thẳng và ghi rõ "tuyến ước lượng"). Cột phải là BẢNG ĐIỀU KHIỂN:
 *  thẻ thông số tuyến + form gộp tuyến + danh sách điểm theo thứ tự tối ưu + nút
 *  duyệt. Một chỗ vừa THẤY vừa XẾP/DUYỆT — không nhảy 3 nơi.
 *
 *  Màn này CHỈ tạo tuyến ở trạng thái ``proposed`` — đúng ADR-0003: agent không
 *  được tự đổi lịch làm việc của con người. Duyệt tuyến nằm ở màn Duyệt tuyến.
 */

import dynamic from "next/dynamic";
import * as React from "react";

import { Button, Card, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { kg, ngayVn, soVn } from "@/lib/format";
import { IconDuyet, IconMuiTenPhai, IconXeThuGom } from "@/lib/icons";
import type { PickupRequest, PickupRoute } from "@/lib/types";

// Leaflet chạm thẳng vào `window` nên phải dynamic `ssr:false` (build `output: export`).
const RouteMap = dynamic(() => import("@/components/manager/route-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

const KHUNG_GIO = [
  { value: "08:00-10:00", label: "Sáng (08:00–10:00)" },
  { value: "14:00-16:00", label: "Chiều (14:00–16:00)" },
];

export function XepTuyen({ onDuyetTuyen }: { onDuyetTuyen?: () => void }) {
  const [ds, setDs] = React.useState<PickupRequest[] | null>(null);
  const [tuyen, setTuyen] = React.useState<PickupRoute | null>(null);
  const [loi, setLoi] = React.useState("");
  const [ngay, setNgay] = React.useState("");
  const [khung, setKhung] = React.useState("08:00-10:00");
  const [maDoi, setMaDoi] = React.useState("");
  const [taiTrong, setTaiTrong] = React.useState("");
  const [dangXep, setDangXep] = React.useState(false);
  const [loiXep, setLoiXep] = React.useState("");

  const tai = React.useCallback(async () => {
    try {
      const d = await api.pickupsChoNhan();
      setDs(d.items);
      // Ngày xếp tuyến mặc định = ngày mong muốn sớm nhất của nhóm chờ xếp.
      setNgay((cu) => {
        if (cu) return cu;
        const ngayNhoNhat = d.items
          .map((y) => y.preferred_date)
          .filter((n): n is string => Boolean(n))
          .sort()[0];
        return ngayNhoNhat ?? new Date().toISOString().slice(0, 10);
      });
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Lỗi tải yêu cầu chờ xếp tuyến");
    }
  }, []);

  // Tuyến đang hiển thị trên bản đồ: tuyến đề xuất gần nhất chưa hoàn thành.
  const taiTuyen = React.useCallback(() => {
    api
      .routes()
      .then(async (d) => {
        const dangChay = d.items.find((r) => r.status === "proposed" || r.status === "approved" || r.status === "in_progress");
        setTuyen(dangChay ? await api.route(dangChay.id) : null);
      })
      .catch(() => setTuyen(null));
  }, []);

  React.useEffect(() => {
    tai();
    taiTuyen();
  }, [tai, taiTuyen]);

  async function xepTuyen() {
    if (!ngay || dangXep) return;
    setDangXep(true);
    setLoiXep("");
    try {
      const tuyến = await api.proposeRoute({
        service_date: ngay,
        window: khung,
        team_id: maDoi ? Number(maDoi) : null,
        capacity_kg: taiTrong ? Number(taiTrong) : null,
      });
      setTuyen(tuyến);
      await tai();
    } catch (e) {
      setLoiXep(e instanceof Error ? e.message : "Không xếp được tuyến, thử lại giúp mình nhé.");
    } finally {
      setDangXep(false);
    }
  }

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (ds === null) {
    // WS-2/B2: skeleton đúng hình command-center (map trái + bảng phải) thay vì
    // màn trắng khi Leaflet đang mount / dữ liệu đang tải. `.gb-skeleton` chỉ
    // opacity, tôn trọng prefers-reduced-motion.
    return (
      <div className="lg:grid lg:grid-cols-[1.6fr_1fr] lg:items-start lg:gap-4">
        <div className="mb-4 lg:mb-0">
          <div className="h-[360px] overflow-hidden rounded-2xl border border-line bg-cream-soft gb-skeleton lg:h-[calc(100vh-10rem)]" />
        </div>
        <div className="space-y-4">
          <div className="h-44 w-full rounded-2xl bg-cream-soft gb-skeleton" />
          <div className="h-64 w-full rounded-2xl bg-cream-soft gb-skeleton" />
        </div>
      </div>
    );
  }

  const loTrinh = tuyen?.lo_trinh_meta;
  const tongKm = loTrinh ? loTrinh.total_km : tuyen?.est_distance_km;

  return (
    <>
      <div className="mb-4 flex items-center gap-2.5">
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Điều phối tuyến</div>
        <span className="rounded-lg border border-line-3 bg-console-bg px-2.5 py-1 text-xs font-bold text-muted">
          HITL #3 · agent gộp, BQL duyệt sau
        </span>
      </div>

      {/* WS-2: hai cột ≥ lg — trái bản đồ tuyến tối ưu, phải bảng điều khiển. */}
      <div className="lg:grid lg:grid-cols-[1.6fr_1fr] lg:items-start lg:gap-4">
        {/* Cột trái — BẢN ĐỒ */}
        <div className="mb-4 lg:sticky lg:top-4 lg:mb-0">
          <div className="h-[360px] overflow-hidden rounded-2xl border border-line lg:h-[calc(100vh-10rem)]">
            {tuyen ? (
              <RouteMap
                stops={tuyen.stops ?? []}
                duong_di={tuyen.duong_di}
                lo_trinh_meta={tuyen.lo_trinh_meta}
                route_id={tuyen.id}
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center rounded-2xl bg-cream-soft px-4 text-center text-sm font-semibold text-muted">
                Chưa có tuyến nào để vẽ — gộp tuyến ở cột bên phải.
              </div>
            )}
          </div>
          {tuyen && !tuyen.duong_di && (
            <p className="mt-2 text-xs font-semibold text-muted">
              Tuyến ước lượng — chưa có đường đi thật nên bản đồ nối thẳng giữa các điểm.
            </p>
          )}
        </div>

        {/* Cột phải — BẢNG ĐIỀU KHIỂN */}
        <div className="space-y-4">
          {tuyen && (
            <Card className="p-4">
              <div className="mb-2 flex items-center gap-2.5">
                <span className="rounded-lg bg-amber-line px-2.5 py-1 text-xs font-extrabold text-amber-darker">
                  AI ĐỀ XUẤT — CHỜ DUYỆT
                </span>
                <div className="font-[family-name:var(--font-display)] text-[16px] font-bold">
                  Chuyến {tuyen.window} · {ngayVn(tuyen.service_date)}
                </div>
              </div>
              <div className="mb-3 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-2xl bg-console-bg px-2 py-2">
                  <div className="font-[family-name:var(--font-display)] text-lg font-bold">{soVn(tongKm ?? 0, 1)}</div>
                  <div className="text-[10.5px] font-bold text-muted">km</div>
                </div>
                <div className="rounded-2xl bg-console-bg px-2 py-2">
                  <div className="font-[family-name:var(--font-display)] text-lg font-bold">
                    {loTrinh ? soVn(loTrinh.total_minutes, 0) : "—"}
                  </div>
                  <div className="text-[10.5px] font-bold text-muted">phút</div>
                </div>
                <div className="rounded-2xl bg-console-bg px-2 py-2">
                  <div className="font-[family-name:var(--font-display)] text-lg font-bold">{tuyen.stop_count}</div>
                  <div className="text-[10.5px] font-bold text-muted">điểm</div>
                </div>
              </div>
              <div className="mb-1 text-xs font-bold text-muted">Thứ tự ghé (số = thứ tự tối ưu)</div>
              <ol className="space-y-1.5">
                {(tuyen.stops ?? []).map((s) => (
                  <li key={s.stop_id} className="flex items-center gap-2.5 text-[13px] font-bold text-ink-soft">
                    <span className="flex h-[26px] w-[26px] flex-none items-center justify-center rounded-lg bg-ink text-xs font-extrabold text-white">
                      {s.seq}
                    </span>
                    <span className="min-w-0 flex-1 truncate">{s.diem_dung_vi || s.unit}</span>
                    {s.stop_kind === "yeu_cau" && (
                      <span className="flex-none text-[12px] font-extrabold text-recycle">{kg(s.weight_max_kg)}</span>
                    )}
                  </li>
                ))}
              </ol>
              {onDuyetTuyen && (
                <Button size="lg" variant="leaf" block className="mt-3" onClick={onDuyetTuyen}>
                  <IconMuiTenPhai className="h-4 w-4" />
                  Đến màn duyệt tuyến
                </Button>
              )}
            </Card>
          )}

          <Card className="p-4">
            <div className="mb-3 font-[family-name:var(--font-display)] text-[16px] font-bold">
              Gộp thành tuyến đề xuất
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="xt-ngay" className="mb-1 block text-xs font-extrabold text-muted">
                  Ngày thu gom
                </label>
                <input
                  id="xt-ngay"
                  type="date"
                  value={ngay}
                  onChange={(e) => setNgay(e.target.value)}
                  className="h-12 w-full rounded-2xl border border-line-2 bg-surface px-3.5 text-base font-bold text-ink-soft outline-none focus:border-leaf"
                />
              </div>
              <div>
                <label htmlFor="xt-khung" className="mb-1 block text-xs font-extrabold text-muted">
                  Khung giờ
                </label>
                <select
                  id="xt-khung"
                  value={khung}
                  onChange={(e) => setKhung(e.target.value)}
                  className="h-12 w-full rounded-2xl border border-line-2 bg-surface px-3.5 text-base font-bold text-ink-soft outline-none focus:border-leaf"
                >
                  {KHUNG_GIO.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="xt-doi" className="mb-1 block text-xs font-extrabold text-muted">
                  Mã đội (tuỳ chọn)
                </label>
                <input
                  id="xt-doi"
                  type="number"
                  min={1}
                  inputMode="numeric"
                  value={maDoi}
                  onChange={(e) => setMaDoi(e.target.value)}
                  placeholder="để trống nếu chưa chốt đội"
                  className="h-12 w-full rounded-2xl border border-line-2 bg-surface px-3.5 text-base font-bold text-ink-soft outline-none focus:border-leaf"
                />
              </div>
              <div>
                <label htmlFor="xt-tai-trong" className="mb-1 block text-xs font-extrabold text-muted">
                  Tải trọng xe (kg, tuỳ chọn)
                </label>
                <input
                  id="xt-tai-trong"
                  type="number"
                  min={1}
                  step="0.1"
                  inputMode="decimal"
                  value={taiTrong}
                  onChange={(e) => setTaiTrong(e.target.value)}
                  placeholder="mặc định theo cấu hình"
                  className="h-12 w-full rounded-2xl border border-line-2 bg-surface px-3.5 text-base font-bold text-ink-soft outline-none focus:border-leaf"
                />
              </div>
            </div>

            {loiXep && (
              <div className="mb-3 mt-3 rounded-2xl border border-hazard-light bg-hazard-soft px-3.5 py-2.5 text-[13px] font-bold text-hazard-dark">
                {loiXep}
              </div>
            )}

            <div className="mt-3.5 flex flex-wrap items-center gap-2.5">
              <Button size="lg" variant="leaf" disabled={!ngay || dangXep} onClick={xepTuyen}>
                <IconDuyet className="h-5 w-5" />
                {dangXep ? "Đang xếp…" : "Xếp tuyến"}
              </Button>
              <span className="text-[13px] font-semibold text-muted">
                Tuyến tạo ra chỉ ở trạng thái đề xuất — agent không tự đổi lịch người.
              </span>
            </div>
          </Card>

          <div className="mb-2.5 text-xs font-extrabold text-muted">CHỜ XẾP TUYẾN ({ds.length})</div>
          {ds.length === 0 ? (
            <EmptyState icon={IconXeThuGom} title="Chưa có yêu cầu nào chờ xếp tuyến" />
          ) : (
            <div className="space-y-2.5">
              {ds.map((yc) => (
                <Card key={yc.id} className="p-3.5">
                  <div className="mb-1 flex justify-between">
                    <span className="text-[13px] font-extrabold text-bulky">#PR-{String(yc.id).padStart(4, "0")}</span>
                    <span className="rounded-lg bg-amber-soft px-2 py-0.5 text-xs font-extrabold text-amber">
                      {yc.weight_min_kg}–{yc.weight_max_kg} kg
                    </span>
                  </div>
                  <div className="text-[13px] font-bold">
                    {yc.unit} · {yc.resident?.full_name}
                  </div>
                  <div className="mt-0.5 text-xs font-semibold text-muted">
                    {yc.items.map((m) => `${m.qty > 1 ? `${m.qty} ` : ""}${m.name}`).join(", ")}
                  </div>
                  <div className="mt-1 text-xs font-semibold text-muted">
                    mong muốn {yc.preferred_date ? ngayVn(yc.preferred_date) : "chưa rõ"}
                    {yc.preferred_window ? ` · ${yc.preferred_window}` : ""}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
