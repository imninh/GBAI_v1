"use client";

/** App đội vệ sinh — thiết kế cho **một tay, đeo găng, ngoài nắng**:
 *  nút tối thiểu 48px, chữ ≥16px, tương phản cao.
 */

import * as React from "react";

import { CaiAppCard } from "@/components/pwa/cai-app";
import { Button, Card, Chip, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { doTinCay, gioVn, kg, ngayVn, soVn } from "@/lib/format";
import {
  IconCaKho,
  IconCanhBao,
  IconDoiVeSinh,
  IconDuyet,
  IconLichSuChuyen,
  IconMonDo,
  IconNhomRac,
  IconTuChoi,
  IconXeThuGom,
  IconXongHet,
} from "@/lib/icons";
import {
  BUOC_KE_TIEP,
  NHAN_TRANG_THAI_YEU_CAU,
  TRANG_THAI_KIEN_DANG_THEO,
  trangThaiYeuCau,
} from "@/lib/pickup-states";
import type { Classification, PickupRequest, PickupRoute, User, WasteCategory } from "@/lib/types";

export function RouteTodayScreen() {
  const [tuyen, setTuyen] = React.useState<PickupRoute | null>(null);
  const [dsSuCo, setDsSuCo] = React.useState<{ code: string; label_vi: string }[]>([]);
  const [loi, setLoi] = React.useState("");
  const [dangMoBaoLoi, setDangMoBaoLoi] = React.useState<number | null>(null);

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

  async function danhDau(stopId: number, issue = "") {
    if (!tuyen) return;
    try {
      const moi = await api.completeStop(tuyen.id, stopId, { issue });
      setTuyen(moi);
      setDangMoBaoLoi(null);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không lưu được");
    }
  }

  if (loi) return <div className="p-4 pt-16"><ErrorState message={loi} onRetry={tai} /></div>;

  return (
    <div className="min-h-full bg-crew-bg px-4 pb-[108px] pt-[52px]">
      {!tuyen ? (
        <EmptyState icon={IconXeThuGom} title="Hôm nay chưa có tuyến nào" hint="Tuyến sẽ hiện ở đây sau khi ban quản lý duyệt." />
      ) : (
        (() => {
          const stops = tuyen.stops ?? [];
          const daThu = stops.filter((s) => s.done_at).length;
          return (
            <>
              <div className="mb-3 flex items-center justify-between">
            <div className="font-[family-name:var(--font-display)] text-[21px] font-bold">Tuyến hôm nay</div>
            {tuyen.status === "proposed" && (
              <span className="rounded-full bg-amber-soft px-3 py-1.5 text-xs font-extrabold text-amber">chờ BQL duyệt</span>
            )}
          </div>

          <div className="mb-4 rounded-[20px] bg-ink p-4 text-white">
            <div className="mb-0.5 font-[family-name:var(--font-display)] text-base font-bold">
              Chuyến {tuyen.window} · {ngayVn(tuyen.service_date)}
            </div>
            <div className="mb-3 text-[13px] font-semibold text-[#9fb3a6]">
              {stops.length} điểm · {kg(tuyen.total_weight_kg)} · ~{soVn(tuyen.est_distance_km, 1)} km
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/15">
              <div className="h-full rounded-full bg-leaf" style={{ width: `${stops.length ? (daThu / stops.length) * 100 : 0}%` }} />
            </div>
            <div className="mt-2 text-xs font-extrabold text-leaf-mint">
              {daThu}/{stops.length} điểm đã thu
            </div>
          </div>

          {stops.map((s) => (
            <Card key={s.stop_id} className="mb-3 p-4" style={{ opacity: s.done_at ? 0.7 : 1 }}>
              <div className="mb-3 flex items-start gap-3">
                <span
                  className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-xl text-[15px] font-extrabold"
                  style={{ background: s.done_at ? "#e6f4ea" : "#16211a", color: s.done_at ? "#1f8a4f" : "#fff" }}
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
                <div className="flex items-center justify-center gap-1.5 rounded-xl bg-leaf-soft p-3 text-sm font-extrabold text-leaf-dark">
                  <IconDuyet className="h-4 w-4 flex-none" />
                  Đã thu lúc {gioVn(s.done_at)}
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
              ) : (
                <div className="flex gap-2.5">
                  <Button variant="leaf" size="lg" className="flex-1" onClick={() => danhDau(s.stop_id)}>
                    <IconDuyet className="h-5 w-5" strokeWidth={2.6} />
                    ĐÃ THU
                  </Button>
                  <Button variant="outline" size="lg" className="flex-1 border-amber-line text-amber" onClick={() => setDangMoBaoLoi(s.stop_id)}>
                    <IconCanhBao className="h-5 w-5" />
                    Báo lỗi
                  </Button>
                </div>
              )}
            </Card>
          ))}
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
      return <div className="rounded-xl bg-muted-bg p-3 text-center text-[13px] font-bold text-muted">Chờ đơn vị xác nhận khối lượng</div>;
    }
    return <div className="rounded-xl bg-muted-bg p-3 text-center text-[13px] font-bold text-muted">Đã kết thúc</div>;
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
                <span className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-xl bg-recycle-soft text-[15px] font-extrabold text-recycle">
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

export function VerifyLabelScreen() {
  const [du, setDu] = React.useState<Awaited<ReturnType<typeof api.verifyQueue>> | null>(null);
  const [danhMuc, setDanhMuc] = React.useState<WasteCategory[]>([]);
  const [dangChon, setDangChon] = React.useState<Classification | null>(null);
  const [loi, setLoi] = React.useState("");

  const tai = React.useCallback(() => {
    api.verifyQueue().then(setDu).catch((e) => setLoi(e.message));
  }, []);

  React.useEffect(() => {
    tai();
    api.categories().then((d) => setDanhMuc(d.items)).catch(() => setDanhMuc([]));
  }, [tai]);

  async function xacNhan(id: number, code: string) {
    await api.verifyLabel(id, code, "");
    setDangChon(null);
    tai();
  }

  if (loi) return <div className="p-4 pt-16"><ErrorState message={loi} onRetry={tai} /></div>;

  return (
    <div className="min-h-full bg-crew-bg px-4 pb-[108px] pt-[52px]">
      <div className="font-[family-name:var(--font-display)] text-[21px] font-bold">Xác nhận nhãn</div>
      <p className="m-0 mb-3.5 text-[13px] font-semibold text-muted">Các ca hệ thống chưa chắc hoặc cư dân báo sai.</p>

      {du?.hard_cases?.length ? (
        <div className="mb-4 rounded-2xl border-[1.5px] border-amber-line bg-amber-soft p-3.5">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-extrabold text-amber">
            <IconCaKho className="h-3.5 w-3.5" />
            CA KHÓ HAY BỊ NHẦM
          </div>
          <div className="text-xs font-bold leading-loose text-[#7a5c14]">
            {du.hard_cases.map((c) => (
              <div key={c.pair}>{c.pair}</div>
            ))}
          </div>
        </div>
      ) : null}

      {!du ? (
        <Skeleton className="h-32 w-full" />
      ) : du.items.length === 0 ? (
        <EmptyState icon={IconXongHet} title="Không còn ca nào chờ xác nhận" hint="Hàng đợi trống — hệ thống đang tự tin với các ca gần đây." />
      ) : (
        du.items.map((ca) => (
          <Card key={ca.classification_id} className="mb-3 p-4">
            <div className="mb-3 flex gap-3">
              <div className="h-[70px] w-[70px] flex-none rounded-xl bg-[repeating-linear-gradient(135deg,#e6edf5,#e6edf5_7px,#dce5ef_7px,#dce5ef_14px)]" />
              <div className="flex-1">
                <div className="mb-1 text-sm font-extrabold">
                  AI đoán: {ca.guess?.item_name || ca.item_name || ca.text_query || "không rõ"}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <span className="rounded-lg bg-[#eef1ec] px-2 py-0.5 text-[11px] font-extrabold text-muted-2">
                    {doTinCay(ca.confidence)}
                  </span>
                  <span className="rounded-lg bg-hazard-soft px-2 py-0.5 text-[11px] font-extrabold text-hazard-dark">
                    Dưới ngưỡng {doTinCay(ca.min_confidence)}
                  </span>
                </div>
                <div className="mt-1.5 text-[11px] font-bold text-muted">Lý do: {ca.refusal_label_vi}</div>
              </div>
            </div>

            {dangChon?.classification_id === ca.classification_id ? (
              <div className="flex flex-col gap-2">
                {danhMuc.map((dm) => (
                  <Button key={dm.code} size="lg" variant="outline" block onClick={() => xacNhan(ca.classification_id, dm.code)}>
                    <IconNhomRac code={dm.code} className="h-4 w-4" />
                    {dm.name}
                  </Button>
                ))}
                <Button size="sm" variant="ghost" block onClick={() => setDangChon(null)}>
                  Đóng
                </Button>
              </div>
            ) : (
              <Button block size="lg" onClick={() => setDangChon(ca)}>
                Chọn nhãn đúng & trả lời
              </Button>
            )}
          </Card>
        ))
      )}
    </div>
  );
}

export function CleanerMeScreen({ user, onLogout }: { user: User; onLogout: () => void }) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center bg-crew-bg px-4 pb-[108px] pt-[52px] text-center">
      <div className="mb-3.5 flex h-16 w-16 items-center justify-center rounded-[20px] bg-recycle-soft text-recycle">
        <IconDoiVeSinh className="h-7 w-7" strokeWidth={1.8} />
      </div>
      <div className="mb-1.5 font-[family-name:var(--font-display)] text-[19px] font-bold">{user.full_name}</div>
      <div className="text-[13px] font-semibold text-muted">Tổ vệ sinh · Sunrise Residence</div>
      <div className="mt-5 w-full rounded-2xl bg-white p-4 text-left text-[13px] font-semibold leading-relaxed text-[#5a6b5f]">
        <div className="mb-2 text-xs font-bold text-muted">QUYỀN CỦA ĐỘI VỆ SINH</div>
        <div className="flex flex-col gap-1">
          <span className="flex items-start gap-1.5">
            <IconDuyet className="mt-0.5 h-3.5 w-3.5 flex-none text-leaf" />
            Xem tuyến của mình · đánh dấu đã thu
          </span>
          <span className="flex items-start gap-1.5">
            <IconDuyet className="mt-0.5 h-3.5 w-3.5 flex-none text-leaf" />
            Xác nhận nhãn ca nghi ngờ
          </span>
          <span className="flex items-start gap-1.5 text-[#b0b8ae]">
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
