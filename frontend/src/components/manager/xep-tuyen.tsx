"use client";

/** Màn "Xếp tuyến" của BQL — nơi nhìn thấy nhóm yêu cầu ``cho_nhan`` và gọi
 *  agent gộp thành tuyến đề xuất.
 *
 *  Khoảng trống cũ: yêu cầu dưới ngưỡng (``cho_nhan``) không hiện ở màn BQL nào —
 *  hàng đợi duyệt chỉ lọc ``cho_duyet``, còn bước xếp tuyến (``POST /routes/propose``)
 *  không có nút nào trong UI. Cư dân + đội vệ sinh thấy được, BQL thì không.
 *
 *  Màn này CHỈ tạo tuyến ở trạng thái ``proposed`` — đúng ADR-0003: agent không
 *  được tự đổi lịch làm việc của con người. Duyệt tuyến vẫn nằm ở màn Duyệt tuyến.
 */

import * as React from "react";

import { Button, Card, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { kg, ngayVn, soVn } from "@/lib/format";
import { IconDuyet, IconXeThuGom } from "@/lib/icons";
import type { PickupRequest, PickupRoute } from "@/lib/types";

const KHUNG_GIO = [
  { value: "08:00-10:00", label: "Sáng (08:00–10:00)" },
  { value: "14:00-16:00", label: "Chiều (14:00–16:00)" },
];

export function XepTuyen() {
  const [ds, setDs] = React.useState<PickupRequest[] | null>(null);
  const [loi, setLoi] = React.useState("");
  const [ngay, setNgay] = React.useState("");
  const [khung, setKhung] = React.useState("08:00-10:00");
  const [maDoi, setMaDoi] = React.useState("");
  const [taiTrong, setTaiTrong] = React.useState("");
  const [dangXep, setDangXep] = React.useState(false);
  const [loiXep, setLoiXep] = React.useState("");
  const [ketQua, setKetQua] = React.useState<PickupRoute | null>(null);

  const tai = React.useCallback(async () => {
    try {
      const d = await api.pickupsChoNhan();
      setDs(d.items);
      // Mặc định ngày xếp tuyến là ngày mong muốn sớm nhất của nhóm chờ xếp —
      // người dùng ít kinh nghiệm không phải tự đoán. Không chạm vào nếu BQL đã
      // chọn một ngày khác.
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

  React.useEffect(() => {
    tai();
  }, [tai]);

  async function xepTuyen() {
    if (!ngay || dangXep) return;
    setDangXep(true);
    setLoiXep("");
    setKetQua(null);
    try {
      const tuyến = await api.proposeRoute({
        service_date: ngay,
        window: khung,
        team_id: maDoi ? Number(maDoi) : null,
        capacity_kg: taiTrong ? Number(taiTrong) : null,
      });
      setKetQua(tuyến);
      await tai();
    } catch (e) {
      setLoiXep(e instanceof Error ? e.message : "Không xếp được tuyến, thử lại giúp mình nhé.");
    } finally {
      setDangXep(false);
    }
  }

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (ds === null) return <Skeleton className="h-96 w-full" />;

  return (
    <>
      <div className="mb-4 flex items-center gap-2.5">
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Xếp tuyến thu gom</div>
        <span className="rounded-lg border border-line-3 bg-console-bg px-2.5 py-1 text-xs font-bold text-muted">
          HITL #3 · agent gộp, BQL duyệt sau
        </span>
      </div>

      <div className="grid items-start gap-4 grid-cols-1 lg:grid-cols-[340px_1fr]">
        <div>
          <div className="mb-2.5 text-xs font-extrabold text-muted">CHỜ XẾP TUYẾN ({ds.length})</div>
          {ds.length === 0 ? (
            <EmptyState icon={IconXeThuGom} title="Chưa có yêu cầu nào chờ xếp tuyến" />
          ) : (
            <div className="space-y-2.5">
              {ds.map((yc) => (
                <Card key={yc.id} className="p-3.5">
                  <div className="mb-1 flex justify-between">
                    <span className="text-[13px] font-extrabold text-bulky">#PR-{String(yc.id).padStart(4, "0")}</span>
                    <span className="rounded-lg bg-amber-soft px-2 py-0.5 text-[11px] font-extrabold text-amber">
                      {yc.weight_min_kg}–{yc.weight_max_kg} kg
                    </span>
                  </div>
                  <div className="text-[13px] font-bold">
                    {yc.unit} · {yc.resident?.full_name}
                  </div>
                  <div className="mt-0.5 text-[11px] font-semibold text-muted">
                    {yc.items.map((m) => `${m.qty > 1 ? `${m.qty} ` : ""}${m.name}`).join(", ")}
                  </div>
                  <div className="mt-1 text-[11px] font-semibold text-muted">
                    mong muốn {yc.preferred_date ? ngayVn(yc.preferred_date) : "chưa rõ"}
                    {yc.preferred_window ? ` · ${yc.preferred_window}` : ""}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <div className="mb-3 font-[family-name:var(--font-display)] text-[16px] font-bold">
              Gộp thành tuyến đề xuất
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="xt-ngay" className="mb-1 block text-[11px] font-extrabold text-muted">
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
                <label htmlFor="xt-khung" className="mb-1 block text-[11px] font-extrabold text-muted">
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
                <label htmlFor="xt-doi" className="mb-1 block text-[11px] font-extrabold text-muted">
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
                <label htmlFor="xt-tai-trong" className="mb-1 block text-[11px] font-extrabold text-muted">
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

          {ketQua && (
            <Card className="overflow-hidden p-0">
              <div className="flex items-center gap-3 rounded-t-[20px] bg-[linear-gradient(150deg,var(--color-ink),var(--color-ink-forest))] px-5 py-4 text-white">
                <span className="rounded-lg bg-amber-line px-2.5 py-1 text-[11px] font-extrabold text-amber-darker">
                  AI ĐỀ XUẤT — CHỜ DUYỆT
                </span>
                <div className="flex-1">
                  <div className="font-[family-name:var(--font-display)] text-[17px] font-bold">
                    Chuyến {ketQua.window} · {ngayVn(ketQua.service_date)}
                  </div>
                  <div className="text-xs font-semibold text-bulky-muted">
                    {ketQua.stop_count} điểm dừng · {kg(ketQua.total_weight_kg)} · ~{soVn(ketQua.est_distance_km, 1)} km
                    {ketQua.team ? ` · ${ketQua.team.full_name}` : ""}
                  </div>
                </div>
              </div>
              <div className="px-5 py-4">
                <div className="mb-1.5 text-[13px] font-bold text-muted">Thứ tự ghé</div>
                <ol className="space-y-1.5">
                  {(ketQua.stops ?? []).map((s) => (
                    <li key={s.stop_id} className="flex items-center gap-2.5 text-[13px] font-bold text-ink-soft">
                      <span className="flex h-[26px] w-[26px] flex-none items-center justify-center rounded-lg bg-ink text-xs font-extrabold text-white">
                        {s.seq}
                      </span>
                      {s.diem_dung_vi || s.unit}
                    </li>
                  ))}
                </ol>
                <div className="mt-3.5 rounded-2xl bg-leaf-soft px-3.5 py-2.5 text-[13px] font-bold text-leaf-dark">
                  Tuyến ở trạng thái đề xuất, cần bấm duyệt ở màn Duyệt tuyến.
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
