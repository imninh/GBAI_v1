"use client";

/** App đội vệ sinh — thiết kế cho **một tay, đeo găng, ngoài nắng**:
 *  nút tối thiểu 48px, chữ ≥16px, tương phản cao.
 */

import dynamic from "next/dynamic";
import * as React from "react";

import { CaiAppCard } from "@/components/pwa/cai-app";
import { BellButton, NotificationSheet, type NotifyTarget } from "@/components/ui/notifications";
import { Button, Card, Chip, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { startGPSTracker, stopGPSTracker } from "@/lib/gps-tracker";
import { gioVn, kg, ngayVn, soVn } from "@/lib/format";
import {
  IconCanhBao,
  IconDuyet,
  IconLichSuChuyen,
  IconMonDo,
  IconTuChoi,
  IconXeThuGom,
} from "@/lib/icons";
import {
  BUOC_KE_TIEP,
  NHAN_TRANG_THAI_YEU_CAU,
  TRANG_THAI_KIEN_DANG_THEO,
  trangThaiYeuCau,
} from "@/lib/pickup-states";
import type { PickupRequest, PickupRoute, User } from "@/lib/types";

const CleanerNavigationMap = dynamic(() => import("@/components/cleaner/navigation-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-[500px] w-full rounded-2xl" />,
});

/** Bốn loại sự cố backend chấp nhận — nguồn sự thật là ``LOAI_HOP_LE`` trong
 *  ``src/services/su_co_thu_gom.py``, giá trị ngoài danh sách bị từ chối 400.
 *  Nhãn hiển thị nằm ở đây chứ không mượn enum của việc khác. */
const LOAI_SU_CO: { code: string; label: string }[] = [
  { code: "phan_loai_sai", label: "Phân loại sai" },
  { code: "thung_day", label: "Thùng đầy / quá tải" },
  { code: "khong_tiep_can", label: "Không tiếp cận được điểm dừng" },
  { code: "khac", label: "Khác" },
];

export function RouteTodayScreen({
  onXemLichSu,
  onThongBaoNavigate,
}: {
  onXemLichSu?: () => void;
  onThongBaoNavigate?: (target: NotifyTarget) => void;
}) {
  const [tuyen, setTuyen] = React.useState<PickupRoute | null>(null);
  const [dsSuCo, setDsSuCo] = React.useState<{ code: string; label_vi: string }[]>([]);
  const [loi, setLoi] = React.useState("");
  const [dangMoBaoLoi, setDangMoBaoLoi] = React.useState<number | null>(null);
  // WS-3: lỗi HIỆN TRƯỜNG (chốt/đánh dấu thất bại) hiện banner trên đầu, không
  // thay cả màn như lỗi tải (`loi`). Tách riêng để người dùng không mất ngữ cảnh.
  const [loiHienTruong, setLoiHienTruong] = React.useState("");
  const [dangChotId, setDangChotId] = React.useState<number | null>(null);
  const [cheDo, setCheDo] = React.useState<"danh-sach" | "ban-do">("danh-sach");
  // Khối lượng thật (kg) đội vệ sinh cân tại chỗ, theo từng điểm dừng — chỉ
  // điểm loại yêu cầu mới cân; thùng đổ thì không. Số này do NGƯỜI nhập, lưu
  // thật qua `completeStop({ actual_weight_kg })`, không tự bịa.
  const [soKg, setSoKg] = React.useState<Record<number, string>>({});
  // Báo sự cố cả chuyến (api.baoSuCo): khác với nút "Báo lỗi" từng điểm dừng —
  // cái đó gắn issue vào điểm dừng khi hoàn thành, cái này là sự cố tự do của
  // chuyến đang làm (xe hỏng, đường chặn…), ban quản lý xử lý riêng.
  const [moBaoSuCo, setMoBaoSuCo] = React.useState(false);
  const [loaiSuCo, setLoaiSuCo] = React.useState("");
  const [moTaSuCo, setMoTaSuCo] = React.useState("");
  const [dangGuiSuCo, setDangGuiSuCo] = React.useState(false);
  const [thongBaoSuCo, setThongBaoSuCo] = React.useState("");
  const [moThongBao, setMoThongBao] = React.useState(false);

  const tai = React.useCallback(() => {
    api
      .routes()
      .then(async (d) => {
        const dangChay = d.items.find((r) => r.status !== "done") ?? d.items[0];
        if (!dangChay) return setTuyen(null);
        setTuyen(await api.route(dangChay.id));
      })
      .catch((e) => setLoi(e.message));
  }, []);

  React.useEffect(() => {
    tai();
    api.enums().then((e) => setDsSuCo(e.stop_issues)).catch(() => setDsSuCo([]));
  }, [tai]);

  // Tự động thu thập & truyền toạ độ GPS khi xe đang trên tuyến
  React.useEffect(() => {
    if (tuyen?.id && tuyen.status !== "done") {
      startGPSTracker(tuyen.id);
    }
    return () => {
      stopGPSTracker();
    };
  }, [tuyen?.id, tuyen?.status]);

  async function danhDau(stopId: number, issue = "") {
    if (!tuyen) return;
    setDangChotId(stopId);
    setLoiHienTruong("");
    try {
      const moi = await api.completeStop(tuyen.id, stopId, { issue });
      setTuyen(moi);
      setDangMoBaoLoi(null);
    } catch {
      // B5: lỗi ngoài trời thường là mất mạng — nói rõ hướng xử lý, đừng để nút
      // treo im. Số cân đã nhập không bị mất (chỉ xoá sau khi lưu thành công).
      setLoiHienTruong("Chưa gửi được — kiểm tra mạng rồi thử lại. Số liệu đã nhập vẫn được giữ.");
    } finally {
      setDangChotId(null);
    }
  }

  /** Chốt điểm thu gom kèm khối lượng THẬT (kg) do đội vệ sinh cân tại chỗ. */
  async function chotDiem(stopId: number, weightKg: number) {
    if (!tuyen) return;
    setDangChotId(stopId);
    setLoiHienTruong("");
    try {
      const moi = await api.completeStop(tuyen.id, stopId, { actual_weight_kg: weightKg });
      setTuyen(moi);
      setSoKg((cu) => {
        const sau = { ...cu };
        delete sau[stopId];
        return sau;
      });
      setDangMoBaoLoi(null);
    } catch {
      setLoiHienTruong("Chưa chốt được — kiểm tra mạng rồi thử lại. Số kg đã nhập vẫn được giữ.");
    } finally {
      setDangChotId(null);
    }
  }

  async function guiBaoSuCo() {
    if (!tuyen || !loaiSuCo || dangGuiSuCo) return;
    setDangGuiSuCo(true);
    setThongBaoSuCo("");
    try {
      const sc = await api.baoSuCo({
        route_id: tuyen.id,
        loai: loaiSuCo,
        mo_ta: moTaSuCo.trim() || undefined,
      });
      setThongBaoSuCo(`Đã báo sự cố #${sc.id} — ban quản lý sẽ xử lý.`);
      setMoBaoSuCo(false);
      setLoaiSuCo("");
      setMoTaSuCo("");
    } catch (e) {
      setThongBaoSuCo(e instanceof Error ? e.message : "Không gửi được báo cáo sự cố.");
    } finally {
      setDangGuiSuCo(false);
    }
  }

  if (loi) return <div className="p-4 pt-16"><ErrorState message={loi} onRetry={tai} /></div>;

  return (
    <div className="min-h-full bg-crew-bg px-4 pb-[108px] pt-[52px]">
      {!tuyen ? (
        <EmptyState
          icon={IconXeThuGom}
          title="Hôm nay chưa có tuyến nào"
          hint="Tuyến sẽ hiện ở đây sau khi ban quản lý duyệt."
          action={
            onXemLichSu ? (
              <Button variant="outline" onClick={onXemLichSu}>
                Xem lịch sử ca trước
              </Button>
            ) : undefined
          }
        />
      ) : (
        (() => {
          const stops = tuyen.stops ?? [];
          const daThu = stops.filter((s) => s.done_at).length;
          return (
            <>
              <div className="mb-3 flex items-center justify-between">
                <div className="font-[family-name:var(--font-display)] text-[21px] font-bold">Tuyến hôm nay</div>
                <div className="flex flex-none items-center gap-2">
                  <BellButton onOpen={() => setMoThongBao(true)} />
                  {tuyen.status === "proposed" ? (
                    <span className="rounded-full bg-amber-soft px-3 py-1.5 text-xs font-extrabold text-amber">chờ BQL duyệt</span>
                  ) : daThu === stops.length && stops.length > 0 ? (
                    <span className="rounded-full bg-leaf-soft px-3 py-1.5 text-xs font-extrabold text-leaf-dark">✓ Đã hoàn tất</span>
                  ) : null}
                </div>
              </div>

              {moThongBao && (
                <NotificationSheet
                  onClose={() => setMoThongBao(false)}
                  onNavigate={(target) => {
                    setMoThongBao(false);
                    onThongBaoNavigate?.(target);
                  }}
                />
              )}

              {/* Bộ chuyển đổi Danh sách <-> Bản đồ dẫn đường */}
              <div className="mb-3 flex rounded-2xl bg-slate-200/80 p-1">
                <button
                  type="button"
                  onClick={() => setCheDo("danh-sach")}
                  className={`flex-1 py-1.5 text-xs font-extrabold rounded-lg transition-all ${cheDo === "danh-sach"
                    ? "bg-surface text-slate-900 shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                    }`}
                >
                  Danh sách điểm dừng
                </button>
                <button
                  type="button"
                  onClick={() => setCheDo("ban-do")}
                  className={`flex-1 py-1.5 text-xs font-extrabold rounded-lg transition-all flex items-center justify-center gap-1 ${cheDo === "ban-do"
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                    }`}
                >
                  Bản đồ dẫn đường
                  <span className="inline-block h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                </button>
              </div>

              {cheDo === "ban-do" ? (
                <CleanerNavigationMap
                  tuyen={tuyen}
                  onDanhDau={danhDau}
                  onTroLaiDanhSach={() => setCheDo("danh-sach")}
                  dsSuCo={dsSuCo}
                />
              ) : (
                <>
                  <div className="mb-4 rounded-2xl bg-ink p-4 text-white">
                    <div className="mb-0.5 font-[family-name:var(--font-display)] text-base font-bold">
                      Chuyến {tuyen.window} · {ngayVn(tuyen.service_date)}
                    </div>
                    <div className="mb-3 text-[13px] font-semibold text-bulky-muted">
                      {stops.length} điểm · {kg(tuyen.total_weight_kg)} · ~{soVn(tuyen.est_distance_km, 1)} km
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-surface/15">
                      <div className="h-full rounded-full bg-leaf" style={{ width: `${stops.length ? (daThu / stops.length) * 100 : 0}%` }} />
                    </div>
                    <div className="mt-2 text-xs font-extrabold text-leaf-mint">
                      {daThu === stops.length && stops.length > 0 ? `Đã thu gom hoàn tất toàn bộ ${stops.length}/${stops.length} điểm` : `${daThu}/${stops.length} điểm đã thu`}
                    </div>
                  </div>

                  {/* Nút báo sự cố cho cả chuyến đang làm — chỉ hiện khi chuyến
                      chưa kết thúc; xong tuyến rồi thì không còn gì để báo. */}
                  {tuyen.status !== "done" && (
                    <div className="mb-4">
                      <Button
                        variant="outline"
                        size="lg"
                        block
                        className="border-amber-line text-amber"
                        onClick={() => setMoBaoSuCo((v) => !v)}
                      >
                        <IconCanhBao className="h-5 w-5" />
                        Báo sự cố chuyến này
                      </Button>
                      {moBaoSuCo && (
                        <Card className="mt-2.5 p-4">
                          <div className="mb-2 text-[13px] font-bold">Loại sự cố</div>
                          <div className="grid grid-cols-1 gap-2">
                            {LOAI_SU_CO.map((ls) => {
                              const dangChon = loaiSuCo === ls.code;
                              return (
                                <button
                                  key={ls.code}
                                  type="button"
                                  onClick={() => setLoaiSuCo(ls.code)}
                                  className={`flex items-center gap-3 rounded-2xl border px-3.5 py-3 text-left text-[14px] font-bold transition-all ${
                                    dangChon ? "border-leaf bg-leaf-soft" : "border-line bg-surface hover:border-line-2"
                                  }`}
                                >
                                  <span
                                    className={`flex h-5 w-5 flex-none items-center justify-center rounded-lg border ${
                                      dangChon ? "border-leaf bg-leaf text-white" : "border-line-2"
                                    }`}
                                  >
                                    {dangChon && <IconDuyet className="h-3.5 w-3.5" />}
                                  </span>
                                  {ls.label}
                                </button>
                              );
                            })}
                          </div>
                          <label htmlFor="mo-ta-su-co" className="mb-1 mt-3 block text-[11px] font-extrabold text-muted">
                            Mô tả thêm (tuỳ chọn)
                          </label>
                          <input
                            id="mo-ta-su-co"
                            value={moTaSuCo}
                            onChange={(e) => setMoTaSuCo(e.target.value)}
                            placeholder="vd: đường xuống hố, xe không qua được"
                            className="h-12 w-full rounded-2xl border border-line-2 bg-surface px-3.5 text-base font-bold text-ink-soft outline-none focus:border-leaf"
                          />
                          <Button
                            variant="leaf"
                            size="lg"
                            block
                            className="mt-3"
                            disabled={!loaiSuCo || dangGuiSuCo}
                            onClick={guiBaoSuCo}
                          >
                            {dangGuiSuCo ? "Đang gửi…" : "Gửi báo cáo sự cố"}
                          </Button>
                        </Card>
                      )}
                      {thongBaoSuCo && (
                        <div className="mt-2.5 rounded-2xl bg-leaf-soft px-4 py-3 text-[13px] font-bold leading-relaxed text-leaf-dark">
                          {thongBaoSuCo}
                        </div>
                      )}
                    </div>
                  )}

                  {loiHienTruong && (
                    <div className="mb-3 rounded-2xl border border-hazard-light bg-hazard-soft px-4 py-3 text-[13px] font-bold text-hazard-dark">
                      {loiHienTruong}
                    </div>
                  )}

                  <div className="lg:grid lg:grid-cols-2 lg:gap-3">
                  {stops.map((s) => (
                    <Card key={s.stop_id} className="mb-3 p-4 lg:mb-0" style={{ opacity: s.done_at ? 0.7 : 1 }}>
                      <div className="mb-3 flex items-start gap-3">
                        <span
                          className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-2xl text-[15px] font-extrabold"
                          style={{ background: s.done_at ? "var(--color-leaf-soft)" : "var(--color-ink)", color: s.done_at ? "var(--color-leaf-dark)" : "var(--color-surface)" }}
                        >
                          {s.seq}
                        </span>
                        <div className="flex-1">
                          <div className="flex justify-between">
                            <span className="text-base font-extrabold">
                              {s.diem_dung_vi || s.unit || `Điểm ${s.seq}`}
                            </span>
                            <span className="font-[family-name:var(--font-display)] text-base font-extrabold text-recycle">
                              {s.stop_kind === "thung" ? `${Math.round(s.fill_percent ?? 0)}%` : kg(s.weight_max_kg)}
                            </span>
                          </div>
                          <div className="text-[13px] font-semibold text-muted">
                            {s.stop_kind === "thung"
                              ? s.dia_chi || "Thùng thu gom"
                              : `${s.resident_name} · ${s.phone_masked}`}
                          </div>
                          <div className="mt-1 flex items-start gap-1.5 text-[13px] font-bold text-bulky-dark">
                            <IconMonDo className="mt-0.5 h-4 w-4 flex-none" />
                            {s.stop_kind === "thung"
                              ? "Đổ thùng — xong là mức rác về 0"
                              : (s.items ?? []).map((i) => `${i.qty > 1 ? `${i.qty} ` : ""}${i.name}`).join(", ")}
                          </div>
                        </div>
                      </div>

                      {s.done_at ? (
                        <div className="flex items-center justify-center gap-1.5 rounded-2xl bg-leaf-soft p-3 text-sm font-extrabold text-leaf-dark">
                          <IconDuyet className="h-4 w-4 flex-none" />
                          Đã thu lúc {gioVn(s.done_at)}
                          {s.actual_weight_kg != null ? ` · cân ${kg(s.actual_weight_kg)}` : ""}
                          {s.issue ? ` · ${s.issue}` : ""}
                        </div>
                      ) : dangMoBaoLoi === s.stop_id ? (
                        <div className="flex flex-col gap-2">
                          {dsSuCo.map((su) => (
                            <Button key={su.code} size="lg" variant="outline" block onClick={() => danhDau(s.stop_id, su.code)}>
                              {su.label_vi}
                            </Button>
                          ))}
                          <Button size="sm" variant="ghost" block onClick={() => setDangMoBaoLoi(null)}>
                            Đóng
                          </Button>
                        </div>
                      ) : s.stop_kind === "thung" ? (
                        <div className="flex gap-2.5">
                          <Button variant="leaf" size="lg" className="flex-1" disabled={dangChotId === s.stop_id} onClick={() => danhDau(s.stop_id)}>
                            <IconDuyet className="h-5 w-5" strokeWidth={2.6} />
                            {dangChotId === s.stop_id ? "Đang lưu…" : "ĐÃ THU"}
                          </Button>
                          <Button variant="outline" size="lg" className="flex-1 border-amber-line text-amber" onClick={() => setDangMoBaoLoi(s.stop_id)}>
                            <IconCanhBao className="h-5 w-5" />
                            Báo lỗi
                          </Button>
                        </div>
                      ) : (
                        <div>
                          <label htmlFor={`can-${s.stop_id}`} className="mb-1 block text-[11px] font-extrabold text-muted">
                            Khối lượng thật (kg) — cân tại chỗ
                          </label>
                          <div className="flex items-end gap-2.5">
                            <input
                              id={`can-${s.stop_id}`}
                              type="number"
                              min={0}
                              step="0.1"
                              inputMode="decimal"
                              value={soKg[s.stop_id] ?? ""}
                              onChange={(e) => setSoKg((cu) => ({ ...cu, [s.stop_id]: e.target.value }))}
                              placeholder="vd: 18.5"
                              className="h-12 w-full flex-1 rounded-lg border border-line-2 bg-surface px-3.5 text-base font-bold text-ink-soft outline-none focus:border-leaf"
                            />
                            <Button
                              variant="leaf"
                              size="lg"
                              className="flex-none"
                              disabled={
                                dangChotId === s.stop_id ||
                                !(soKg[s.stop_id]?.trim()) ||
                                !Number.isFinite(Number(soKg[s.stop_id])) ||
                                Number(soKg[s.stop_id]) < 0
                              }
                              onClick={() => chotDiem(s.stop_id, Number(soKg[s.stop_id]))}
                            >
                              <IconDuyet className="h-5 w-5" strokeWidth={2.6} />
                              {dangChotId === s.stop_id ? "Đang chốt…" : "Chốt điểm"}
                            </Button>
                          </div>
                          <Button variant="outline" size="sm" block className="mt-2 border-amber-line text-amber" onClick={() => setDangMoBaoLoi(s.stop_id)}>
                            <IconCanhBao className="h-4 w-4" />
                            Báo lỗi thay vì chốt
                          </Button>
                        </div>
                      )}
                    </Card>
                  ))}
                  </div>
                </>
              )}
            </>
          );
        })()
      )}

      <KienDangTheoSection />
    </div>
  );
}

function KienDangTheoSection() {
  const [kien, setKien] = React.useState<PickupRequest[] | null>(null);
  const [loi, setLoi] = React.useState("");
  const [dangChuyen, setDangChuyen] = React.useState<number | null>(null);

  const tai = React.useCallback(() => {
    setLoi("");
    api
      .pickups()
      .then((d) => setKien(d.items.filter((k) => TRANG_THAI_KIEN_DANG_THEO.has(k.status))))
      .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được kiện đang theo"));
  }, []);

  React.useEffect(() => {
    tai();
  }, [tai]);

  async function buocTiep(k: PickupRequest) {
    const trangThai = trangThaiYeuCau(k.status);
    const buoc = trangThai ? BUOC_KE_TIEP[trangThai] : null;
    if (!buoc) return;
    setDangChuyen(k.id);
    setLoi("");
    try {
      await api.chuyenTrangThaiYeuCau(k.id, buoc.den);
      await tai();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không chuyển được trạng thái");
    } finally {
      setDangChuyen(null);
    }
  }

  function traiThai(k: PickupRequest) {
    const tt = trangThaiYeuCau(k.status);
    if (!tt) return null;
    const buoc = BUOC_KE_TIEP[tt];
    if (buoc) {
      return (
        <Button
          size="lg"
          variant="leaf"
          block
          disabled={dangChuyen === k.id}
          onClick={() => buocTiep(k)}
        >
          {dangChuyen === k.id ? "Đang cập nhật…" : buoc.nhan}
        </Button>
      );
    }
    if (tt === "da_giao_don_vi") {
      return <div className="rounded-2xl bg-muted-bg p-3 text-center text-[13px] font-bold text-muted">Chờ đơn vị xác nhận khối lượng</div>;
    }
    return <div className="rounded-2xl bg-muted-bg p-3 text-center text-[13px] font-bold text-muted">Đã kết thúc</div>;
  }

  return (
    <section className="mt-7">
      <div className="mb-2 font-[family-name:var(--font-display)] text-lg font-bold">Kiện đang theo</div>

      {loi && <ErrorState message={loi} onRetry={tai} />}

      {!kien ? (
        <Skeleton className="h-24 w-full" />
      ) : kien.length === 0 ? (
        <EmptyState icon={IconXeThuGom} title="Chưa có kiện nào được giao" />
      ) : (
        kien.map((k) => {
          const trangThai = trangThaiYeuCau(k.status);
          return (
            <Card key={k.id} className="mb-3 p-4">
              <div className="mb-3 flex items-start gap-3">
                <span className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-2xl bg-recycle-soft text-[15px] font-extrabold text-recycle">
                  <IconMonDo className="h-4 w-4" />
                </span>
                <div className="flex-1">
                  <div className="flex justify-between gap-2">
                    <span className="text-base font-extrabold">{k.building} · {k.unit}</span>
                    <span className="text-[13px] font-extrabold text-muted">{kg(k.weight_max_kg)}</span>
                  </div>
                  <div className="text-[13px] font-semibold text-muted">
                    {k.resident?.full_name ?? ""}
                    {k.preferred_window ? ` · ${k.preferred_window}` : ""}
                  </div>
                  <div className="mt-1 text-[13px] font-bold text-bulky-dark">
                    {k.items.map((i) => `${i.qty > 1 ? `${i.qty} ` : ""}${i.name}`).join(", ")}
                  </div>
                </div>
              </div>

              <div className="mb-3">
                <Chip tone={trangThai === "da_giao_don_vi" ? "amber" : "neutral"}>
                  {trangThai ? NHAN_TRANG_THAI_YEU_CAU[trangThai] : k.status}
                </Chip>
              </div>

              {traiThai(k)}
            </Card>
          );
        })
      )}
    </section>
  );
}

export function CleanerMeScreen({ user, onLogout }: { user: User; onLogout: () => void }) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center bg-crew-bg px-4 pb-[108px] pt-[52px] text-center">
      <div className="mb-3.5 flex h-16 w-16 items-center justify-center overflow-hidden rounded-2xl bg-recycle-soft">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/avatar/ve-sinh.svg" alt="Avatar đội vệ sinh" className="h-16 w-16 object-contain" />
      </div>
      <div className="mb-1.5 font-[family-name:var(--font-display)] text-[19px] font-bold">{user.full_name}</div>
      <div className="text-[13px] font-semibold text-muted">Tổ vệ sinh · Sunrise Residence</div>
      <div className="mt-5 w-full rounded-2xl bg-surface p-4 text-left text-[13px] font-semibold leading-relaxed text-ink-faint">
        <div className="mb-2 text-xs font-bold text-muted">QUYỀN CỦA ĐỘI VỆ SINH</div>
        <div className="flex flex-col gap-1">
          <span className="flex items-start gap-1.5">
            <IconDuyet className="mt-0.5 h-3.5 w-3.5 flex-none text-leaf" />
            Xem tuyến của mình · đánh dấu đã thu
          </span>
          <span className="flex items-start gap-1.5 text-ink-disabled">
            <IconTuChoi className="mt-0.5 h-3.5 w-3.5 flex-none" />
            Duyệt yêu cầu thu gom · duyệt tuyến gộp · trang vận hành
          </span>
        </div>
      </div>
      <div className="mt-3.5 w-full text-left">
        <CaiAppCard />
      </div>
      <Button variant="danger" className="mt-5" onClick={onLogout}>
        Đăng xuất
      </Button>
    </div>
  );
}

export function CleanerHistoryScreen() {
  const [items, setItems] = React.useState<PickupRoute[] | null>(null);
  React.useEffect(() => {
    api.routes({ status: "done" }).then((d) => setItems(d.items)).catch(() => setItems([]));
  }, []);

  return (
    <div className="min-h-full bg-crew-bg px-4 pb-[108px] pt-[52px]">
      <div className="mb-3.5 font-[family-name:var(--font-display)] text-[21px] font-bold">Lịch sử chuyến</div>
      {items === null ? (
        <Skeleton className="h-24 w-full" />
      ) : items.length === 0 ? (
        <EmptyState icon={IconLichSuChuyen} title="Chưa có chuyến nào hoàn thành" />
      ) : (
        items.map((r) => (
          <Card key={r.id} className="mb-3 p-4">
            <div className="text-[15px] font-bold">
              {ngayVn(r.service_date)} · {r.window}
            </div>
            <div className="text-[13px] font-semibold text-muted">
              {r.stop_count} điểm · {kg(r.total_weight_kg)} · ~{soVn(r.est_distance_km, 1)} km
            </div>
          </Card>
        ))
      )}
    </div>
  );
}
