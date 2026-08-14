"use client";

/** Wizard đăng ký thu gom đồ cồng kềnh — 3 bước + màn xác nhận.
 *
 * Hai chi tiết không được cắt:
 * - bước 2 đánh dấu khung giờ **đã có chuyến của toà**, kèm câu nói rõ chọn
 *   khung đó tiết kiệm được một chuyến xe (giá trị kinh doanh hiện ra trước
 *   mắt người dùng, không giấu trong báo cáo);
 * - bước 3 nói **ngưỡng bằng con số cụ thể** trước khi bấm gửi, để người dùng
 *   hiểu vì sao mình phải chờ.
 */

import * as React from "react";

import { Button, Card } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { kg, ngayVn } from "@/lib/format";
import { IconAi, IconChoDuyet, IconDuyet, IconQuayLai, IconTuChoi, IconXeThuGom } from "@/lib/icons";
import type { Classification, PickupRequest, ScheduleHint } from "@/lib/types";

interface MonRac {
  name: string;
  category_code: string;
  qty: number;
  est_weight_kg: number;
}

const NGUONG_KG_MAC_DINH = 30;

export function PickupWizard({
  goiYTuKetQua,
  scheduleHint,
  onBack,
  onDone,
}: {
  goiYTuKetQua?: Classification | null;
  scheduleHint?: ScheduleHint;
  onBack: () => void;
  onDone: (yeuCau: PickupRequest) => void;
}) {
  const [buoc, setBuoc] = React.useState(1);
  const [mon, setMon] = React.useState<MonRac[]>(() =>
    goiYTuKetQua?.category
      ? [
          {
            name: goiYTuKetQua.item_name || goiYTuKetQua.category.name,
            category_code: goiYTuKetQua.category.code,
            qty: 1,
            est_weight_kg: 30,
          },
        ]
      : [],
  );
  const [ngay, setNgay] = React.useState("");
  const [khungGio, setKhungGio] = React.useState("");
  const [ghiChu, setGhiChu] = React.useState("");
  const [daTick, setDaTick] = React.useState(false);
  const [dangGui, setDangGui] = React.useState(false);
  const [loi, setLoi] = React.useState("");
  const [ketQua, setKetQua] = React.useState<PickupRequest | null>(null);

  const tongKg = mon.reduce((s, m) => s + m.est_weight_kg * m.qty, 0);
  const vuotNguong = tongKg * 1.4 > NGUONG_KG_MAC_DINH;

  const khungGoiY = React.useMemo(() => {
    // `?? []` phải nằm TRONG useMemo: đặt ở ngoài thì mỗi lần render lại sinh
    // một mảng rỗng mới, dependency đổi liên tục và useMemo mất tác dụng.
    const chuyenDaCo = scheduleHint?.khung_gio_da_co_chuyen ?? [];
    const tuChuyen = chuyenDaCo.map((c) => ({
      key: `${c.service_date}|${c.window}`,
      ngay: c.service_date,
      window: c.window,
      daCoChuyen: true,
      ghiChu: c.ghi_chu,
    }));
    const homSau = new Date();
    homSau.setDate(homSau.getDate() + 3);
    const macDinh = ["08:00-10:00", "14:00-16:00"].map((w) => ({
      key: `${homSau.toISOString().slice(0, 10)}|${w}`,
      ngay: homSau.toISOString().slice(0, 10),
      window: w,
      daCoChuyen: false,
      ghiChu: "",
    }));
    const gop = [...tuChuyen, ...macDinh];
    return gop.filter((g, i) => gop.findIndex((x) => x.key === g.key) === i);
  }, [scheduleHint?.khung_gio_da_co_chuyen]);

  async function gui() {
    setDangGui(true);
    setLoi("");
    try {
      const yeuCau = await api.createPickup({
        items: mon,
        est_weight_kg: tongKg,
        preferred_date: ngay || null,
        preferred_window: khungGio,
        note: ghiChu,
        confirmed_no_hazardous: daTick,
      });
      setKetQua(yeuCau);
      setBuoc(4);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không gửi được yêu cầu.");
    } finally {
      setDangGui(false);
    }
  }

  const nhanNut = buoc === 1 ? "Tiếp tục" : buoc === 2 ? "Xem lại" : "Gửi yêu cầu";
  const choPhepTiep = buoc === 1 ? mon.length > 0 : buoc === 2 ? Boolean(khungGio) : daTick;

  return (
    <div className="min-h-full bg-cream pb-10 pt-11">
      <div className="flex items-center gap-3 px-[18px] pb-3.5 pt-1.5">
        <button
          onClick={() => (buoc === 1 ? onBack() : setBuoc((b) => b - 1))}
          className="flex h-[38px] w-[38px] cursor-pointer items-center justify-center rounded-full bg-white shadow-[0_2px_8px_rgba(20,40,25,.08)]"
          aria-label="Quay lại bước trước"
        >
          <IconQuayLai className="h-5 w-5" />
        </button>
        <div className="flex flex-1 gap-1.5">
          {[1, 2, 3].map((b) => (
            <span key={b} className="h-[5px] flex-1 rounded-full" style={{ background: buoc >= b ? "#7c5cdf" : "#e0ded4" }} />
          ))}
        </div>
      </div>

      <div className="px-[18px]">
        {buoc === 1 && (
          <>
            <div className="mb-1 text-[13px] font-bold text-bulky">Bước 1/3</div>
            <h1 className="m-0 mb-1 font-[family-name:var(--font-display)] text-[26px] font-bold">Món cần thu gom</h1>
            <p className="m-0 mb-4 text-[13px] font-semibold text-muted">
              AI điền sẵn tên, nhóm và ước lượng khối lượng — bạn kiểm tra lại giúp mình.
            </p>
            {mon.map((m, i) => (
              <Card key={i} className="mb-2.5 flex gap-3 p-3.5">
                <div className="h-16 w-16 flex-none rounded-xl bg-[repeating-linear-gradient(135deg,#ece7f6,#ece7f6_7px,#e3daf3_7px,#e3daf3_14px)]" />
                <div className="flex-1">
                  <input
                    value={m.name}
                    onChange={(e) => setMon((cu) => cu.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
                    className="w-full bg-transparent text-[15px] font-extrabold outline-none"
                  />
                  <div className="my-1.5 flex items-center gap-1.5">
                    <span className="rounded-lg bg-bulky-soft px-2 py-0.5 text-[11px] font-extrabold text-bulky-dark">
                      {m.category_code}
                    </span>
                    <input
                      type="number"
                      value={m.est_weight_kg}
                      min={1}
                      onChange={(e) =>
                        setMon((cu) => cu.map((x, j) => (j === i ? { ...x, est_weight_kg: Number(e.target.value) } : x)))
                      }
                      className="w-16 rounded-lg bg-[#f2ede2] px-2 py-0.5 text-[11px] font-bold text-[#8a7a5a] outline-none"
                    />
                    <span className="text-[11px] font-bold text-[#8a7a5a]">kg</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] font-bold text-[#b58a2a]">
                    <IconAi className="h-3.5 w-3.5" />
                    AI ước lượng — kiểm tra lại giúp mình
                  </div>
                </div>
                {mon.length > 1 && (
                  <button
                    onClick={() => setMon((cu) => cu.filter((_, j) => j !== i))}
                    className="cursor-pointer text-muted"
                    aria-label={`Bỏ món ${m.name}`}
                  >
                    <IconTuChoi className="h-4 w-4" />
                  </button>
                )}
              </Card>
            ))}
            <button
              onClick={() => setMon((cu) => [...cu, { name: "Món mới", category_code: "bulky", qty: 1, est_weight_kg: 10 }])}
              className="w-full cursor-pointer rounded-2xl border-[1.5px] border-dashed border-[#cbb8ee] bg-white p-3.5 text-sm font-bold text-bulky-dark"
            >
              + Thêm món
            </button>
            <div className="mx-0.5 mt-4 flex items-center justify-between text-sm font-bold">
              <span className="text-muted">Tổng ước tính</span>
              <span className="font-[family-name:var(--font-display)] text-lg font-extrabold">{kg(tongKg)}</span>
            </div>
          </>
        )}

        {buoc === 2 && (
          <>
            <div className="mb-1 text-[13px] font-bold text-bulky">Bước 2/3</div>
            <h1 className="m-0 mb-4 font-[family-name:var(--font-display)] text-[26px] font-bold">Chọn thời gian</h1>
            <div className="mb-2 text-[13px] font-bold text-muted">Khung giờ khả dụng</div>
            {khungGoiY.map((k) => {
              const dangChon = khungGio === k.window && ngay === k.ngay;
              return (
                <button
                  key={k.key}
                  onClick={() => {
                    setKhungGio(k.window);
                    setNgay(k.ngay);
                  }}
                  className="mb-2.5 w-full cursor-pointer rounded-2xl p-4 text-left"
                  style={{
                    background: dangChon ? "#e6f4ea" : "#fff",
                    border: dangChon ? "2px solid #2fae66" : "1.5px solid #e0ded4",
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[15px] font-extrabold">
                      {ngayVn(k.ngay)} · {k.window}
                    </span>
                    {dangChon && (
                      <span className="flex h-[22px] w-[22px] items-center justify-center rounded-full bg-leaf text-white">
                        <IconDuyet className="h-3.5 w-3.5" strokeWidth={3} />
                      </span>
                    )}
                  </div>
                  {k.daCoChuyen && (
                    <div className="mt-2 flex items-center gap-1.5 text-xs font-bold text-leaf-dark">
                      <IconXeThuGom className="h-4 w-4 flex-none" />
                      {k.ghiChu}
                    </div>
                  )}
                </button>
              );
            })}
            <textarea
              value={ghiChu}
              onChange={(e) => setGhiChu(e.target.value)}
              placeholder="Ghi chú thêm (VD: để ở sảnh tầng 1)"
              className="mt-2 min-h-[70px] w-full resize-none rounded-2xl border-[1.5px] border-line-2 p-3 text-sm font-semibold outline-none focus:border-leaf"
            />
          </>
        )}

        {buoc === 3 && (
          <>
            <div className="mb-1 text-[13px] font-bold text-bulky">Bước 3/3</div>
            <h1 className="m-0 mb-4 font-[family-name:var(--font-display)] text-[26px] font-bold">Xác nhận</h1>
            <Card className="mb-3 p-4">
              <Dong nhan="Số món" gia={`${mon.length} món`} />
              <Dong nhan="Tổng khối lượng" gia={kg(tongKg)} dam />
              <Dong nhan="Thời gian" gia={`${ngayVn(ngay)} · ${khungGio}`} />
            </Card>

            {vuotNguong && (
              <div className="mb-3 rounded-2xl border-[1.5px] border-amber-line bg-amber-soft p-4">
                <div className="flex gap-2.5">
                  <IconChoDuyet className="mt-0.5 h-[18px] w-[18px] flex-none text-amber" />
                  <div>
                    <div className="mb-1 text-sm font-extrabold text-amber">Cần ban quản lý duyệt</div>
                    <div className="text-[13px] font-semibold leading-relaxed text-[#7a5c14]">
                      Khối lượng ước tính <b>{kg(tongKg)}</b> (sai số ±40% nên cận trên tới{" "}
                      <b>{kg(Math.round(tongKg * 1.4))}</b>) vượt ngưỡng tự động <b>({NGUONG_KG_MAC_DINH} kg)</b>, nên
                      cần BQL duyệt trước khi lên lịch. Bạn sẽ nhận thông báo trong vòng 1 ngày làm việc.
                    </div>
                  </div>
                </div>
              </div>
            )}

            <label className="flex cursor-pointer items-start gap-2.5 rounded-2xl bg-white p-3.5 text-[13px] font-semibold leading-snug text-ink-soft">
              <input type="checkbox" checked={daTick} onChange={(e) => setDaTick(e.target.checked)} className="mt-0.5 h-5 w-5 accent-[#2fae66]" />
              Tôi xác nhận các món trên không chứa rác nguy hại (pin, hoá chất, bóng đèn, thuốc).
            </label>
            {loi && <div className="mt-3 text-[13px] font-bold text-hazard-dark">{loi}</div>}
          </>
        )}

        {buoc === 4 && ketQua && (
          <>
            <div className="py-6 text-center">
              <div className="mx-auto mb-4 flex h-[74px] w-[74px] items-center justify-center rounded-full bg-leaf-soft text-leaf">
                <IconDuyet className="h-9 w-9" strokeWidth={2.6} />
              </div>
              <h1 className="m-0 mb-1 font-[family-name:var(--font-display)] text-[25px] font-bold">Đã gửi yêu cầu!</h1>
              <div className="mb-4 text-[15px] font-extrabold text-bulky">#PR-{String(ketQua.id).padStart(4, "0")}</div>
            </div>
            <Card className="p-4">
              {(ketQua.timeline ?? []).map((moc, i) => (
                <div key={i} className="mb-3.5 flex gap-3 last:mb-0">
                  <span className="flex h-[22px] w-[22px] flex-none items-center justify-center rounded-full bg-leaf text-white">
                    <IconDuyet className="h-3 w-3" strokeWidth={3} />
                  </span>
                  <div className="text-[13px] font-bold">
                    <span className="font-semibold text-muted">{new Date(moc.at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })} · </span>
                    {moc.label_vi}
                  </div>
                </div>
              ))}
              {ketQua.status === "cho_duyet" && (
                <div className="flex gap-3">
                  <span className="flex h-[22px] w-[22px] flex-none items-center justify-center rounded-full bg-amber-line text-amber">
                    <IconChoDuyet className="h-3 w-3" />
                  </span>
                  <div className="text-[13px] font-bold text-amber">Chờ ban quản lý duyệt</div>
                </div>
              )}
            </Card>
            <Button block size="lg" className="mt-4" onClick={() => onDone(ketQua)}>
              Xem yêu cầu của tôi
            </Button>
          </>
        )}
      </div>

      {buoc < 4 && (
        <div className="px-[18px] pt-4">
          <Button
            block
            size="lg"
            disabled={!choPhepTiep || dangGui}
            onClick={() => (buoc === 3 ? gui() : setBuoc((b) => b + 1))}
          >
            {dangGui ? "Đang gửi…" : nhanNut}
          </Button>
        </div>
      )}
    </div>
  );
}

function Dong({ nhan, gia, dam }: { nhan: string; gia: string; dam?: boolean }) {
  return (
    <div className="flex justify-between py-1 text-sm font-bold">
      <span className="text-muted">{nhan}</span>
      <span className={dam ? "font-extrabold" : ""}>{gia}</span>
    </div>
  );
}
