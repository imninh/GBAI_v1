"use client";

/** Bốn hàng đợi HITL của đơn vị thu gom.
 *
 * Nguyên tắc chung cho cả bốn: **hàng đợi phải nói vì sao mục này rơi vào đây.**
 * Một hàng đợi duyệt mà không nói lý do là hàng đợi vô nghĩa.
 */

import dynamic from "next/dynamic";
import * as React from "react";

import { Button, Card, Chip, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { AnhCoToken } from "@/lib/anh-co-token";
import { KipVaSuCo } from "@/components/manager/kip_va_su_co";
import { api } from "@/lib/api";
import { doTinCay, kg, ngayGioVn, ngayVn, phanTram, soVn } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  IconAi,
  IconCaKho,
  IconCanhBao,
  IconChucMung,
  IconDuyet,
  IconHoanTac,
  IconLamLai,
  IconNhomRac,
  IconSua,
  IconTuChoi,
  IconXeThuGom,
  IconXongHet,
} from "@/lib/icons";
import type { Classification, PickupRequest, PickupRoute, WasteCategory } from "@/lib/types";

// Leaflet chạm thẳng vào `window` nên không dựng được lúc build tĩnh — phải qua
// `next/dynamic` với `ssr:false` (dự án build bằng `output: "export"`). Placeholder
// cao đúng tầm khung bản đồ để thẻ không bị nhảy khi map tải về.
const RouteMap = dynamic(() => import("@/components/manager/route-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

export function PickupQueue() {
  const [ds, setDs] = React.useState<PickupRequest[] | null>(null);
  const [lyDoTuChoi, setLyDoTuChoi] = React.useState<{ code: string; label_vi: string }[]>([]);
  const [dangChon, setDangChon] = React.useState<PickupRequest | null>(null);
  const [moTuChoi, setMoTuChoi] = React.useState(false);
  const [loi, setLoi] = React.useState("");

  const tai = React.useCallback(async () => {
    try {
      const d = await api.pickups({ status: "pending" });
      setDs(d.items);
      setLyDoTuChoi(d.reject_reasons);
      if (d.items.length) setDangChon(await api.pickup(d.items[0].id));
      else setDangChon(null);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Lỗi tải hàng đợi");
    }
  }, []);

  React.useEffect(() => {
    tai();
    const id = setInterval(tai, 30000);
    return () => clearInterval(id);
  }, [tai]);

  async function duyet(action: string, reason = "") {
    if (!dangChon) return;
    await api.reviewPickup(dangChon.id, { action, reason });
    setMoTuChoi(false);
    tai();
  }

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (ds === null) return <Skeleton className="h-96 w-full" />;

  return (
    <>
      <div className="mb-4 flex items-center gap-2.5">
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Duyệt yêu cầu thu gom</div>
        <span className="rounded-lg border border-line-3 bg-console-bg px-2.5 py-1 text-xs font-bold text-muted">
          HITL #1 · AI đề xuất, người chốt
        </span>
      </div>

      {ds.length === 0 ? (
        <EmptyState icon={IconChucMung} title="Chưa có yêu cầu nào cần duyệt hôm nay" />
      ) : (
        <div className="grid items-start gap-4 grid-cols-1 lg:grid-cols-[300px_1fr]">
          <div>
            <div className="mb-2.5 text-xs font-extrabold text-muted">CHỜ DUYỆT ({ds.length})</div>
            {ds.map((yc, _i) => (
<button
                key={yc.id}
                onClick={() => api.pickup(yc.id).then(setDangChon)}
                className={cn(
                  "mb-2.5 w-full cursor-pointer rounded-2xl bg-surface p-3.5 text-left transition-all duration-200 ease-[var(--ease-spring)] active:scale-[0.98]",
                  dangChon?.id === yc.id
                    ? "border-2 border-leaf shadow-[var(--shadow-sm)]"
                    : "border border-line-3 shadow-[var(--shadow-xs)] hover:border-line-2 hover:shadow-[var(--shadow-sm)] hover:-translate-y-0.5",
                  "animate-gbreveal"
                )}
style={{ animationDelay: `${0.06 + _i * 0.06}s`, animationFillMode: "both" }}
              >
                <div className="mb-1 flex justify-between">
                  <span className="text-xs font-extrabold text-bulky">#PR-{String(yc.id).padStart(4, "0")}</span>
                  <span className="rounded-md bg-amber-soft border border-amber-line/60 px-2 py-0.5 text-[11px] font-extrabold text-amber">
                    {kg(yc.est_weight_kg)}
                  </span>
                </div>
                <div className="text-xs font-bold text-ink">
                  {yc.unit} · {yc.resident?.full_name}
                </div>
                <div className="mt-1 text-[11px] font-semibold text-muted">mong muốn {ngayVn(yc.preferred_date)}</div>
              </button>
            ))}
          </div>

          {dangChon && (
            <Card className="overflow-hidden p-0">
              <div className="border-b border-line-4 px-5 py-4">
                <div className="mb-1 flex items-center gap-2.5">
                  <span className="rounded-md bg-amber-soft px-2.5 py-1 text-xs font-extrabold text-amber">CHỜ DUYỆT</span>
                  <span className="text-[15px] font-extrabold text-bulky">#PR-{String(dangChon.id).padStart(4, "0")}</span>
                </div>
                <div className="text-[13px] font-semibold text-muted">
                  {dangChon.resident?.full_name} · Căn {dangChon.unit} · gửi {ngayGioVn(dangChon.created_at)}
                </div>
              </div>

              <div className="px-5 py-4">
                <div className="mb-3.5 rounded-xl bg-console-bg p-3.5">
                  <div className="mb-2.5 text-[13px] font-bold">Vì sao yêu cầu này cần duyệt</div>
                  {dangChon.threshold_hit.map((t) => (
                    <div key={t.rule} className="flex justify-between py-1 text-[13px] font-bold">
                      <span className="text-muted-2">{t.label_vi}</span>
                      <span>
                        {t.value}{" "}
                        <span className="font-semibold text-muted">
                          {t.threshold ? `(ngưỡng ${t.threshold})` : "(luôn cần duyệt)"}
                        </span>{" "}
                        <span className="inline-flex items-center gap-1 text-hazard-dark">
                          <IconCanhBao className="h-3.5 w-3.5" />
                          vượt
                        </span>
                      </span>
                    </div>
                  ))}
                  <div className="flex justify-between py-1 text-[13px] font-bold">
                    <span className="text-muted-2">Cư dân tự ước tính</span>
                    <span>
                      {kg(dangChon.est_weight_kg)}{" "}
                      <span className="font-semibold text-muted">
                        (dung sai {dangChon.weight_min_kg}–{dangChon.weight_max_kg} kg)
                      </span>
                    </span>
                  </div>
                </div>

                <div className="mb-3.5 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {dangChon.items.map((m, i) => (
                    <div key={i}>
                      <div className="mb-1 aspect-square overflow-hidden rounded-xl">
                        <AnhCoToken
                          mediaId={m.media_id}
                          alt={m.name}
                          className="h-full w-full object-cover"
                        />
                      </div>
                      <div className="text-[10px] font-bold">
                        {m.name}
                        {m.qty > 1 ? ` ×${m.qty}` : ""}
                      </div>
                    </div>
                  ))}
                </div>

                {dangChon.resident_history && (
                  <div className="mb-3.5 rounded-xl border border-[var(--color-line-green)] bg-[var(--color-tint-green)] px-3.5 py-3 text-xs font-semibold leading-loose text-ink-soft">
                    Cư dân này: {dangChon.resident_history.so_yeu_cau_truoc} yêu cầu trước,{" "}
                    {dangChon.resident_history.so_lan_hoan_thanh} lần hoàn thành, {dangChon.resident_history.so_lan_huy} lần huỷ
                    <br />
                    Toà {dangChon.building_code}: {dangChon.building_context?.so_yeu_cau} yêu cầu, tổng{" "}
                    {kg(dangChon.building_context?.tong_khoi_luong_kg ?? 0)}
                    <br />
                    Ngày {ngayVn(dangChon.preferred_date)}: {dangChon.capacity_context?.so_yeu_cau_cung_ngay} yêu cầu khác
                    cùng ngày · tải trọng xe {kg(dangChon.capacity_context?.tai_trong_xe_kg ?? 0)}
                  </div>
                )}

                {dangChon.agent_suggestion && (
                  <div className="rounded-xl border-[1.5px] border-dashed border-[var(--color-bulky-line-faint)] bg-[var(--color-bulky-tint)] p-3.5">
                    <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-extrabold text-bulky">
                      <IconAi className="h-3.5 w-3.5" />
                      {dangChon.agent_suggestion.label_vi}
                    </div>
                    <div className="text-[13px] font-semibold leading-relaxed text-ink-soft">
                      {dangChon.agent_suggestion.text_vi}
                    </div>
                  </div>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2.5 border-t border-line-4 bg-cream-soft px-5 py-3.5">
                <Button variant="leaf" onClick={() => duyet("approve")}>
                  <IconDuyet className="h-4 w-4" />
                  Duyệt
                </Button>
                <span className="flex-1" />
                <Button variant="danger" onClick={() => setMoTuChoi((v) => !v)}>
                  <IconTuChoi className="h-4 w-4" />
                  Từ chối
                </Button>
              </div>

              {moTuChoi && (
                <div className="border-t border-line-4 px-5 py-3.5">
                  <div className="mb-2 text-[13px] font-bold">
                    Chọn lý do từ chối — bắt buộc chọn từ danh sách để dữ liệu chảy vào tập cải tiến
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {lyDoTuChoi.map((r) => (
                      <Button key={r.code} size="sm" variant="outline" onClick={() => duyet("reject", r.code)}>
                        {r.label_vi}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )}
        </div>
      )}
    </>
  );
}

export function VerifyQueue() {
  const [du, setDu] = React.useState<Awaited<ReturnType<typeof api.verifyQueue>> | null>(null);
  const [danhMuc, setDanhMuc] = React.useState<WasteCategory[]>([]);
  const [loi, setLoi] = React.useState("");
  // Duyệt hàng loạt: một nhịp xác nhận, tuần tự từng ca, dừng khi gặp lỗi.
  const [xacNhanDuyetNhanh, setXacNhanDuyetNhanh] = React.useState(false);
  const [dangDuyetNhanh, setDangDuyetNhanh] = React.useState(false);
  const [duyetNhanhDaXong, setDuyetNhanhDaXong] = React.useState(0);
  const [loiDuyetNhanh, setLoiDuyetNhanh] = React.useState("");

  const tai = React.useCallback(() => {
    api.verifyQueue().then(setDu).catch((e) => setLoi(e.message));
  }, []);
  React.useEffect(() => {
    tai();
    api.categories().then((d) => setDanhMuc(d.items)).catch(() => setDanhMuc([]));
  }, [tai]);

  /** Khoảng cách từ confidence tới ngưỡng CỦA CHÍNH CA ĐÓ. Âm = còn thiếu dưới
   *  ngưỡng; càng âm càng rủi ro. Ngưỡng nhóm nguy hại cao hơn hẳn, nên đã nằm
   *  sẵn trong chính phép so này — so `confidence` thô giữa hai nhóm là so hai
   *  cái thước khác nhau. */
  function khoangCachNguong(ca: Classification): number {
    return ca.confidence - ca.min_confidence;
  }

  /** Ca phải người duyệt xem TỪNG cái: nguy hại hoặc đã bị từ chối trả lời.
   *  Nhóm này không bao giờ được duyệt hàng loạt — ràng buộc an toàn. */
  function canXemTungCa(ca: Classification): boolean {
    return ca.category?.is_hazardous === true || ca.refused === true;
  }

  /** Ca duyệt hàng loạt được: không nguy hại, không bị từ chối, và CÓ nhãn AI
   *  để chấp nhận (ca `category == null` không có nhãn nào để chấp nhận). */
  function coTheDuyetNhanh(ca: Classification): ca is Classification & { category: WasteCategory } {
    return !canXemTungCa(ca) && ca.category != null;
  }

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (!du) return <Skeleton className="h-96 w-full" />;

  const daXep = [...du.items].sort((a, b) => khoangCachNguong(a) - khoangCachNguong(b));
  const cacCaPhaiXem = daXep.filter(canXemTungCa);
  const cacCaDuyetNhanh = daXep.filter(coTheDuyetNhanh);
  const soCaPhaiXem = cacCaPhaiXem.length;
  const soCaDuyetNhanh = cacCaDuyetNhanh.length;

  async function duyetHangLoat() {
    if (cacCaDuyetNhanh.length === 0) return;
    setDangDuyetNhanh(true);
    setLoiDuyetNhanh("");
    let daXong = 0;
    setDuyetNhanhDaXong(0);
    for (const ca of cacCaDuyetNhanh) {
      try {
        await api.verifyLabel(ca.classification_id, ca.category.code);
        daXong += 1;
        setDuyetNhanhDaXong(daXong);
      } catch (e) {
        setLoiDuyetNhanh(
          `Đã duyệt ${daXong}/${cacCaDuyetNhanh.length} ca rồi dừng lại: ${
            e instanceof Error ? e.message : "lỗi không xác định"
          }. ${cacCaDuyetNhanh.length - daXong} ca còn lại vẫn nằm trong hàng đợi.`,
        );
        break;
      }
    }
    setDangDuyetNhanh(false);
    setXacNhanDuyetNhanh(false);
    tai();
  }

  function TheCa({ ca, danhMuc, tai }: { ca: Classification; danhMuc: WasteCategory[]; tai: () => void }) {
    const thieu = ca.min_confidence - ca.confidence;
    const [mo, setMo] = React.useState(false);
    const [replyText, setReplyText] = React.useState("");
    const [nhanDuocChon, setNhanDuocChon] = React.useState<WasteCategory | null>(ca.category ?? null);
    const [loiLuu, setLoiLuu] = React.useState("");
    const [dangLuu, setDangLuu] = React.useState(false);

    async function xacNhan() {
      if (!nhanDuocChon || dangLuu) return;
      setDangLuu(true);
      setLoiLuu("");
      try {
        await api.verifyLabel(ca.classification_id, nhanDuocChon.code, replyText);
        tai();
      } catch (e) {
        setLoiLuu(e instanceof Error ? e.message : "Không lưu được nhãn.");
      } finally {
        setDangLuu(false);
      }
    }

    return (
      <Card className="p-4 animate-gbreveal">
        {/* Ảnh tải LAZY — mở thẻ mới tải ảnh. Dựng cho mọi thẻ ngay khi hàng
            đợi lên là một `fetch` có token bắn cùng lúc cho từng ca: mở màn 100
            ca là 100 lệnh tải ảnh đồng thời. AnhCoToken tự lo ca hỏi bằng chữ
            (`media_id == null`): 0 lệnh gọi mạng, hiện ô giữ chỗ. */}
        {mo && (
          <div className="mb-3 aspect-[4/3] w-full overflow-hidden rounded-xl bg-cream-soft">
            <AnhCoToken mediaId={ca.media_id} alt="Ảnh cư dân gửi" className="h-full w-full object-cover" />
          </div>
        )}
        <div className="mb-2 text-sm font-extrabold">
          AI đoán: {ca.guess?.item_name || ca.item_name || ca.text_query || "không rõ"} · {doTinCay(ca.confidence)}
        </div>
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <Chip tone="hazard" className="text-[11px]">
            Dưới ngưỡng {doTinCay(ca.min_confidence)}
          </Chip>
          {thieu > 0 && (
            <Chip tone="neutral" className="text-[11px]">
              còn thiếu {phanTram(thieu, 0)}
            </Chip>
          )}
        </div>
        <div className="mb-2 text-[11px] font-semibold text-muted">Lý do từ chối: {ca.refusal_label_vi}</div>

        {/* Bộ chọn nhãn đúng — chips danh mục; mặc định = nhãn AI (đã chọn sẵn). */}
        <div className="mb-1.5 text-xs font-bold text-muted">Nhãn đúng</div>
        <div className="mb-3 flex flex-wrap gap-1.5">
          {danhMuc.map((dm) => {
            const dangChon = nhanDuocChon?.code === dm.code;
            return (
              <button
                key={dm.code}
                type="button"
                onClick={() => setNhanDuocChon(dm)}
                className={cn(
                  "flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-bold transition-all duration-150 active:scale-95",
                  dangChon
                    ? "border-leaf bg-leaf-soft text-leaf-dark"
                    : "border-line-2 bg-surface text-ink-soft hover:border-line-2"
                )}
              >
                <IconNhomRac code={dm.code} className="h-3.5 w-3.5" />
                {dm.name}
              </button>
            );
          })}
        </div>

        {/* Ô ghi chú/lý do — RIÊNG thẻ này, không lây sang thẻ khác. */}
        <div className="mb-1.5 text-xs font-semibold text-muted">Ghi chú / lý do (tuỳ chọn)</div>
        <textarea
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          placeholder="Ví dụ: sai loại rác, xác nhận nhãn AI..."
          className="w-full rounded-xl border border-line-2 bg-surface px-3 py-2 text-base font-medium text-ink-soft outline-none focus:border-leaf resize-y min-h-20"
          rows={3}
        />

        {loiLuu && (
          <div className="mt-2 rounded-xl border border-hazard-light bg-hazard-soft px-3.5 py-2.5 text-[13px] font-bold text-hazard-dark">
            {loiLuu}
          </div>
        )}

        <div className="mt-2 flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setMo((v) => !v)}>
            {mo ? "Thu ảnh" : "Xem ảnh"}
          </Button>
          <span className="flex-1" />
          <Button
            size="sm"
            variant="leaf"
            disabled={!nhanDuocChon || dangLuu}
            onClick={xacNhan}
          >
            <IconDuyet className="h-3.5 w-3.5" />
            {dangLuu ? "Đang lưu…" : "Xác nhận"}
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <>
      <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Xác nhận nhãn nghi ngờ</div>
      <div className="mb-1 text-sm font-semibold text-muted">
        {du.total} ca hệ thống chưa chắc hoặc cư dân báo sai · HITL #2
      </div>
      <div className="mb-4 rounded-xl bg-console-bg px-3.5 py-2.5 text-xs font-semibold leading-loose text-ink-soft">
        Chỉ những ca hệ thống tự thấy chưa chắc mới vào hàng đợi này — phần còn lại
        đã tự trả lời xong. Trong {du.total} ca đang chờ, {soCaPhaiXem} ca cần xem từng cái,
        {soCaDuyetNhanh} ca duyệt hàng loạt được.
      </div>

      {du.hard_cases?.length ? (
        <div className="mb-4 rounded-2xl border border-amber-line bg-amber-soft px-4 py-3.5">
          <div className="mb-2 flex items-center gap-1.5 text-[11px] font-extrabold text-amber">
            <IconCaKho className="h-3.5 w-3.5" />
            CA KHÓ HAY BỊ NHẦM (từ eval)
          </div>
          <div className="flex flex-wrap gap-2 text-xs font-bold text-amber-dark">
            {du.hard_cases.map((c) => (
              <span key={c.pair} className="rounded-lg bg-surface px-2.5 py-1.5" title={c.note}>
                {c.pair}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {du.items.length === 0 ? (
        <EmptyState icon={IconXongHet} title="Hàng đợi trống" hint="Không có ca nào đang chờ người xác nhận." />
      ) : (
        <div className="space-y-5">
          <div>
            <div className="mb-2.5 text-xs font-extrabold text-muted">
              PHẢI XEM TỪNG CA ({soCaPhaiXem})
            </div>
            {soCaPhaiXem === 0 ? (
              <div className="text-[13px] font-semibold text-muted">Không có ca nào cần xem riêng.</div>
            ) : (
              <div className="grid grid-cols-2 gap-3.5">{cacCaPhaiXem.map((ca) => <TheCa key={ca.classification_id} ca={ca} danhMuc={danhMuc} tai={tai} />)}</div>
            )}
          </div>

          <div>
            <div className="mb-2.5 text-xs font-extrabold text-muted">
              CÓ THỂ DUYỆT NHANH ({soCaDuyetNhanh})
            </div>
            {soCaDuyetNhanh === 0 ? (
              <div className="text-[13px] font-semibold text-muted">Không có ca nào duyệt hàng loạt được.</div>
            ) : (
              <>
                {loiDuyetNhanh && (
                  <div className="mb-2 rounded-xl border border-hazard-light bg-hazard-soft px-3.5 py-2.5 text-[13px] font-bold text-hazard-dark">
                    {loiDuyetNhanh}
                  </div>
                )}
                <div className="mb-3 rounded-xl border border-line bg-cream-soft px-3.5 py-2.5">
                  {xacNhanDuyetNhanh ? (
                    <div className="flex flex-wrap items-center gap-2.5">
                      <span className="text-[13px] font-bold text-hazard-dark">
                        Chấp nhận nhãn AI cho {soCaDuyetNhanh} ca và ghi tên người duyệt vào từng ca — chắc chưa?
                      </span>
                      <span className="flex-1" />
                      <Button size="sm" variant="outline" disabled={dangDuyetNhanh} onClick={() => setXacNhanDuyetNhanh(false)}>
                        Không, để lại
                      </Button>
                      <Button size="sm" variant="leaf" disabled={dangDuyetNhanh} onClick={duyetHangLoat}>
                        {dangDuyetNhanh ? `Đang duyệt ${duyetNhanhDaXong}/${soCaDuyetNhanh}…` : "Chấp nhận thật"}
                      </Button>
                    </div>
                  ) : (
                    <Button size="sm" variant="leaf" disabled={dangDuyetNhanh} onClick={() => setXacNhanDuyetNhanh(true)}>
                      <IconDuyet className="h-4 w-4" />
                      Chấp nhận nhãn AI cho {soCaDuyetNhanh} ca
                    </Button>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-3.5">{cacCaDuyetNhanh.map((ca) => <TheCa key={ca.classification_id} ca={ca} danhMuc={danhMuc} tai={tai} />)}</div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export function WeightConfirmQueue() {
  const [ds, setDs] = React.useState<PickupRequest[] | null>(null);
  const [soKg, setSoKg] = React.useState<Record<number, string>>({});
  const [dangGui, setDangGui] = React.useState<number | null>(null);
  const [ketQua, setKetQua] = React.useState<Record<number, { status: string }>>({});
  const [loi, setLoi] = React.useState("");

  const tai = React.useCallback(() => {
    setLoi("");
    api
      .pickups({ status: "da_giao_don_vi" })
      .then((d) => setDs(d.items))
      .catch((e) => setLoi(e instanceof Error ? e.message : "Lỗi tải hàng đợi"));
  }, []);

  React.useEffect(() => {
    tai();
  }, [tai]);

  async function xacNhan(id: number) {
    const so = Number(soKg[id]);
    if (!Number.isFinite(so) || so < 0) return;
    setDangGui(id);
    setLoi("");
    try {
      const ketQua = await api.xacNhanKhoiLuong(id, so);
      setKetQua((cu) => ({ ...cu, [id]: { status: ketQua.status } }));
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không xác nhận được khối lượng");
    } finally {
      setDangGui(null);
    }
  }

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (ds === null) return <Skeleton className="h-96 w-full" />;

  return (
    <>
      <div className="mb-4 flex items-center gap-2.5">
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Chờ xác nhận khối lượng</div>
        <span className="rounded-lg border border-line-3 bg-console-bg px-2.5 py-1 text-xs font-bold text-muted">
          HITL · người cân, hệ thống chốt
        </span>
      </div>

      <div className="mb-4 rounded-2xl border border-leaf-line bg-leaf-soft px-4 py-3 text-[13px] font-bold leading-relaxed text-leaf-dark">
        Điểm thưởng chỉ tính trên khối lượng do người xác nhận, không tính trên con số cư dân tự khai.
        <br />
        Con số dưới đây phải là số đội thu gom đã cân tại chỗ. Chưa có số cân thì để trống —
        đừng ước lượng thay họ, vì chính con số này chốt trạng thái và điểm thưởng.
      </div>

      {ds.length === 0 ? (
        <EmptyState icon={IconChucMung} title="Chưa có kiện nào chờ xác nhận khối lượng" />
      ) : (
        <div className="grid gap-3.5">
          {ds.map((yc, _i) => {
            const daXacNhan = ketQua[yc.id];
            const trangThai = daXacNhan ? daXacNhan.status : "";
            return (
              <Card key={yc.id} className="p-4 animate-gbreveal" style={{ animationDelay: `${0.06 + _i * 0.06}s`, animationFillMode: "both" }}>
                <div className="mb-3 flex items-start gap-3">
                  <div className="flex-1">
                    <div className="mb-1 flex items-center gap-2.5">
                      <span className="rounded-md bg-amber-soft px-2.5 py-1 text-xs font-extrabold text-amber">CHỜ XÁC NHẬN</span>
                      <span className="text-[15px] font-extrabold text-bulky">#PR-{String(yc.id).padStart(4, "0")}</span>
                    </div>
                    <div className="text-[13px] font-semibold text-muted">
                      {yc.resident?.full_name} · Căn {yc.unit} · {yc.building}
                    </div>
                    <div className="mt-1 text-[13px] font-bold text-ink-soft">
                      {yc.items.map((m) => `${m.qty > 1 ? `${m.qty} ` : ""}${m.name}`).join(", ")}
                    </div>
                  </div>
                </div>

                <div className="mb-3 rounded-xl bg-console-bg px-3.5 py-3">
                  <div className="flex justify-between text-[13px] font-bold">
                    <span className="text-muted-2">Cư dân tự khai</span>
                    <span className="text-ink-soft">
                      {yc.weight_min_kg}–{yc.weight_max_kg} kg
                    </span>
                  </div>
                </div>

                {daXacNhan ? (
                  <>
                    {trangThai === "hoan_tat" ? (
                      <div className="flex items-center gap-2 rounded-xl bg-leaf-soft px-4 py-3 text-sm font-extrabold text-leaf-dark">
                        <IconChucMung className="h-5 w-5 flex-none" />
                        Hoàn tất
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 rounded-xl border border-amber-line bg-amber-soft px-4 py-3 text-sm font-extrabold text-[var(--color-amber-deep)]">
                        <IconCanhBao className="h-5 w-5 flex-none" />
                        Tranh chấp — khối lượng thật lệch xa khoảng ước lượng
                      </div>
                    )}
                    <div className="mt-2 text-[11px] font-semibold text-muted">
                      Đã chốt {soKg[yc.id]} kg · Cư dân tự khai {yc.weight_min_kg}–{yc.weight_max_kg} kg
                    </div>
                  </>
                ) : (
                  <div className="flex items-end gap-2.5">
                    <div className="flex-1">
                      <label htmlFor={`khoi-luong-${yc.id}`} className="mb-1 block text-[11px] font-extrabold text-muted">
                        Số cân đội thu gom báo (kg)
                      </label>
                      <input
                        id={`khoi-luong-${yc.id}`}
                        type="number"
                        min={0}
                        step="0.1"
                        inputMode="decimal"
                        value={soKg[yc.id] ?? ""}
                        onChange={(e) => setSoKg((cu) => ({ ...cu, [yc.id]: e.target.value }))}
                        placeholder="vd: 18.5"
                        className="h-12 w-full rounded-xl border border-line-2 bg-surface px-3.5 text-base font-bold text-ink-soft outline-none focus:border-leaf"
                      />
                    </div>
                    <Button
                      variant="leaf"
                      size="lg"
                      disabled={dangGui === yc.id || !Number.isFinite(Number(soKg[yc.id]))}
                      onClick={() => xacNhan(yc.id)}
                    >
                      <IconDuyet className="h-4 w-4" />
                      {dangGui === yc.id ? "Đang xác nhận…" : "Xác nhận"}
                    </Button>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}

export function RouteApproval() {
  const [ds, setDs] = React.useState<PickupRoute[] | null>(null);
  const [tuyen, setTuyen] = React.useState<PickupRoute | null>(null);
  const [boBot, setBoBot] = React.useState<number[]>([]);
  const [loi, setLoi] = React.useState("");
  const [thongBao, setThongBao] = React.useState("");
  // Lỗi khi bấm duyệt, tách khỏi `loi` (lỗi tải) vì hai thứ này hiện ở hai chỗ
  // khác nhau: lỗi tải thay cả màn, lỗi duyệt chỉ là một dải trên đầu.
  const [loiDuyet, setLoiDuyet] = React.useState("");
  // Hành động đang gửi, "" là rảnh. Vừa để khoá nút chống bấm hai lần, vừa để
  // đổi nhãn nút thành "Đang duyệt…" — người dùng phải thấy máy đang làm gì.
  const [dangGui, setDangGui] = React.useState("");
  const [xacNhanHuy, setXacNhanHuy] = React.useState(false);
  // Danh sách "không gộp vào chuyến này" — mặc định đóng, bấm vào mới mở.
  const [moKhongGop, setMoKhongGop] = React.useState(false);

  const tai = React.useCallback(async () => {
    try {
      const d = await api.routes({ status: "proposed" });
      setDs(d.items);
      if (d.items.length) setTuyen(await api.route(d.items[0].id));
      else setTuyen(null);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Lỗi tải tuyến");
    }
  }, []);
  React.useEffect(() => {
    tai();
  }, [tai]);

  async function duyet(action: string) {
    if (!tuyen || dangGui) return;
    setDangGui(action);
    setLoiDuyet("");
    setThongBao("");
    try {
      const ketQua = await api.reviewRoute(tuyen.id, {
        action,
        removed_stops: boBot.length ? boBot : undefined,
      });
      setThongBao(ketQua.message_vi ?? "");
      setBoBot([]);
      setXacNhanHuy(false);
      await tai();
    } catch (e) {
      // Bản cũ KHÔNG bắt lỗi ở đây: backend từ chối (tuyến đã chốt → ROUTE-400,
      // sai quyền → 403) là promise vỡ, nút bấm xong không có gì xảy ra và
      // không báo gì. Đó là kiểu hỏng tệ nhất với người dùng ít kinh nghiệm.
      setLoiDuyet(e instanceof Error ? e.message : "Không gửi được quyết định duyệt, thử lại giúp mình nhé.");
    } finally {
      setDangGui("");
    }
  }

  // So với bản agent đề xuất. CỐ TÌNH không dựa vào cờ `reordered` của backend:
  // nó đòi `sorted(proposed) == sorted(current)` nên chỉ đúng khi KHÔNG có điểm
  // nào bị bỏ — ca vừa bỏ vừa đổi thứ tự sẽ bị giấu mất nửa chuyện. So lại ngay
  // trên giao diện từ `proposed`/`final`/`removed` cho kín.
  const diff = tuyen?.diff;
  const soBo = diff ? (diff.removed ?? []).length : 0;
  const conLai = (diff?.proposed ?? []).filter((id) => !(diff?.removed ?? []).includes(id));
  const doiThuTu = conLai.length > 0 && JSON.stringify(conLai) !== JSON.stringify(diff?.final ?? []);
  const coChinhSua = diff ? Boolean(diff.changed) : false;

  // Câu "Cùng cụm toà S1, S2 (bán kính 0,7 km)" rút gọn thành chip "cùng cụm
  // S1 · S2". Bỏ phần bán kính vì câu tiếng Việt đã tự nói điều đó; chip phải
  // đọc được trong một hơi.
  const cauCum = tuyen?.reasoning?.criteria.find((c) => c.startsWith("Cùng cụm"));
  const cumNgan = cauCum
    ? `cùng cụm ${cauCum.split("toà ")[1]?.split(" (bán kính")[0]?.replace(/, /g, " · ") ?? cauCum}`
    : null;

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (ds === null) return <Skeleton className="h-96 w-full" />;

  return (
    <>
      {/* Header gọn: tên ca + ngày + khung giờ một dòng; chip HITL bên phải. */}
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Duyệt tuyến gộp</div>
          {tuyen && (
            <div className="text-[13px] font-semibold text-muted">
              Chuyến {tuyen.window} · {ngayVn(tuyen.service_date)}
              {tuyen.team ? ` · ${tuyen.team.full_name}` : ""}
            </div>
          )}
        </div>
        <span className="flex-none rounded-lg border border-line-3 bg-console-bg px-2.5 py-1 text-xs font-bold text-muted">
          HITL #3 · agent gộp, người chốt
        </span>
      </div>

      {thongBao && <div className="mb-3 rounded-2xl bg-leaf-soft px-4 py-3 text-sm font-bold text-leaf-dark">{thongBao}</div>}
      {loiDuyet && (
        <div className="mb-3 rounded-2xl border border-hazard-light bg-hazard-soft px-4 py-3 text-sm font-bold text-hazard-dark">
          {loiDuyet}
        </div>
      )}

      {!tuyen ? (
        <EmptyState
          icon={IconXeThuGom}
          title="Chưa có tuyến nào chờ duyệt"
          hint="Agent sẽ đề xuất tuyến khi có đủ yêu cầu đã duyệt cùng ngày và cùng khung giờ."
        />
      ) : (
        <>
          {/* Bản đồ là nhân vật chính — trọn chiều ngang, ngay dưới header. */}
          <div className="mb-4 h-[280px] overflow-hidden rounded-2xl border border-line">
            <RouteMap stops={tuyen.stops ?? []} duong_di={tuyen.duong_di} lo_trinh_meta={tuyen.lo_trinh_meta} route_id={tuyen.id} />
          </div>

          {/* Lý do gộp — hàng chip, không phải đoạn văn bullet. */}
          <div className="mb-1.5 flex flex-wrap gap-2">
            <span className="rounded-full bg-line-4 px-3.5 py-1.5 text-[13px] font-bold text-amber-muted">
              {tuyen.stop_count} chuyến → 1
            </span>
            {tuyen.reasoning?.capacity_kg ? (
              <span className="rounded-full bg-line-4 px-3.5 py-1.5 text-[13px] font-bold text-amber-muted">
                {Math.round(tuyen.total_weight_kg)}/{Math.round(tuyen.reasoning.capacity_kg)} kg
              </span>
            ) : (
              <span className="rounded-full bg-line-4 px-3.5 py-1.5 text-[13px] font-bold text-amber-muted">
                {kg(tuyen.total_weight_kg)}
              </span>
            )}
            {cumNgan && (
              <span className="rounded-full bg-[var(--color-bulky-chip)] px-3.5 py-1.5 text-[13px] font-bold text-purple">
                {cumNgan}
              </span>
            )}
            {/* Hai con số là HAI KHÁI NIỆM, không phải đo hai lần khác kết quả
                (E2E §8): baseline = đi rời lẻ từng chuyến (số điểm × 3,6 km),
                est_distance_km = tuyến GỘP sau tối ưu — số đã lưu, dùng làm số
                hiển thị chuẩn. Thiếu baseline thì chỉ hiện số đã lưu. */}
            <span className="rounded-full bg-leaf-soft px-3.5 py-1.5 text-[13px] font-bold text-leaf-dark">
              {tuyen.reasoning?.baseline_km ? (
                <>rời lẻ ~{soVn(tuyen.reasoning.baseline_km, 1)} km → </>
              ) : null}
              gộp chung ~{soVn(tuyen.est_distance_km, 1)} km
            </span>
          </div>
          {!tuyen.duong_di && (
            <p className="mb-4 text-[11px] font-semibold text-muted">
              Quãng đường ước tính theo đường chim bay — tuyến này chưa có đường đi thật.
            </p>
          )}

          {/* Những yêu cầu KHÔNG gộp vào chuyến này (lệch ngày / lệch khung giờ)
              — người duyệt cần biết thông tin này để hiểu vì sao chuyến chỉ có
              bấy nhiêu điểm. Không có dữ liệu thì không dựng khối rỗng. */}
          {tuyen.reasoning?.excluded?.length ? (
            <div className="mb-4 rounded-lg border border-[var(--color-warn-line)] bg-[var(--color-warn-tint)]">
              <button
                type="button"
                onClick={() => setMoKhongGop((v) => !v)}
                aria-expanded={moKhongGop}
                className="flex w-full cursor-pointer items-center gap-2 px-4 py-3 text-left"
              >
                <IconTuChoi className="h-4 w-4 flex-none text-amber" />
                <span className="flex-1 text-[13px] font-bold text-[var(--color-warn-ink)]">
                  {tuyen.reasoning.excluded.length} yêu cầu không gộp vào chuyến này
                </span>
                <span className="text-[13px] font-bold text-amber">{moKhongGop ? "Thu gọn" : "Xem lý do"}</span>
              </button>
              {moKhongGop && (
                <ul className="gb-hscroll px-4 pb-3">
                  {tuyen.reasoning.excluded.map((e, i) => (
                    <li key={`${e.request_id}-${i}`} className="flex items-start gap-2 border-t border-[var(--color-warn-line)] py-1.5 text-[12px] font-semibold leading-snug">
                      <span className="flex-none font-extrabold text-amber">{e.request_id}</span>
                      {e.unit && <span className="flex-none text-muted">{e.unit}</span>}
                      <span className="min-w-0 flex-1 text-[var(--color-warn-text)]">{e.ly_do}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}

          {/* Danh sách điểm dừng — mỗi điểm MỘT dòng. */}
          <div className="mb-4 rounded-2xl bg-surface px-4 py-2">
            {(tuyen.stops ?? []).map((s, _i) => {
              const laThung = s.stop_kind === "thung";
              const daBo = boBot.includes(s.stop_id);
              const ten = laThung
                ? s.diem_dung_vi || `Thùng ${s.seq}`
                : (s.items ?? []).map((i) => i.name).join(", ") || s.diem_dung_vi || `Điểm ${s.seq}`;
              const phu = laThung
                ? `Đầy ${Math.round(s.fill_percent ?? 0)}%${s.dia_chi ? ` · ${s.dia_chi}` : ""}`
                : `${s.dia_chi || s.unit}${s.resident_name ? ` · ${s.resident_name}` : ""}`;
              return (
                <div
                  key={s.stop_id}
                  className="flex items-center gap-3 border-b border-line py-2.5 last:border-0 animate-gbreveal"
                  style={{ opacity: daBo ? 0.4 : 1, animationDelay: `${0.06 + _i * 0.06}s`, animationFillMode: "both" }}
                >
                  <span
                    className={`flex h-7 w-7 flex-none items-center justify-center rounded-full text-[12px] font-extrabold ${
                      daBo ? "bg-[var(--color-chip-off)] text-muted" : "bg-leaf text-white"
                    }`}
                  >
                    {s.seq}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-[14px] font-bold">{ten}</span>
                      {laThung && (
                        <span className="flex-none rounded-md bg-amber-line px-1.5 py-0.5 text-[10px] font-extrabold text-amber-darker">
                          THÙNG
                        </span>
                      )}
                    </div>
                    {phu && <div className="truncate text-[11px] font-semibold text-muted">{phu}</div>}
                  </div>
                  <span className="flex-none text-[14px] font-extrabold text-recycle">
                    {laThung ? "—" : kg(s.weight_max_kg)}
                  </span>
                  <button
                    onClick={() =>
                      setBoBot((cu) => (daBo ? cu.filter((x) => x !== s.stop_id) : [...cu, s.stop_id]))
                    }
                    className="flex-none cursor-pointer text-muted"
                    title={daBo ? "Giữ lại điểm này" : "Bỏ khỏi tuyến"}
                    aria-label={daBo ? `Giữ lại điểm ${ten}` : `Bỏ điểm ${ten} khỏi tuyến`}
                  >
                    {daBo ? <IconHoanTac className="h-4 w-4" /> : <IconTuChoi className="h-4 w-4" />}
                  </button>
                </div>
              );
            })}

            {/* So với bản agent đề xuất — gọn thành một dòng. Chỉ tính điểm dừng
                là yêu cầu của cư dân (bản agent là danh sách `request_id`), nói
                rõ để không bị hiểu nhầm "bỏ thùng khỏi tuyến không được ghi nhận". */}
            <div className="border-t border-line py-2.5">
              {!coChinhSua ? (
                <div className="flex items-center gap-1.5 text-[12px] font-bold text-leaf-dark">
                  <IconChucMung className="h-4 w-4 flex-none" />
                  Giữ nguyên bản agent đề xuất.
                </div>
              ) : (
                <div className="text-[12px] font-bold leading-loose text-ink-soft">
                  {soBo > 0 && <span>Đã bỏ {soBo} điểm · </span>}
                  {doiThuTu && <span>Đã đổi thứ tự ghé · </span>}
                  {soBo === 0 && !doiThuTu && <span>Đã chỉnh sửa so với bản agent đề xuất · </span>}
                  <span className="font-semibold text-muted">chỉ tính điểm dừng là yêu cầu của cư dân</span>
                </div>
              )}
            </div>
          </div>

          {/* Hai quyết định chính: duyệt xanh đậm chiếm trọn chiều ngang còn lại
              + nút phụ viền mỏng bên cạnh. Huỷ tuyến hiếm dùng nên để nhỏ dưới
              cùng; không lùi lại được nên vẫn phải hỏi lại một nhịp. */}
          <div className="flex gap-2.5">
            {boBot.length === 0 ? (
              <Button size="lg" variant="leaf" className="flex-1" disabled={dangGui !== ""} onClick={() => duyet("approve")}>
                <IconDuyet className="h-5 w-5" />
                {dangGui === "approve" ? "Đang duyệt…" : "Duyệt tuyến này"}
              </Button>
            ) : (
              <Button size="lg" variant="leaf" className="flex-1" disabled={dangGui !== ""} onClick={() => duyet("approve_with_changes")}>
                <IconSua className="h-5 w-5" />
                {dangGui === "approve_with_changes" ? "Đang duyệt…" : `Duyệt, bỏ ${boBot.length} điểm`}
              </Button>
            )}
            <Button size="lg" variant="outline" disabled={dangGui !== ""} onClick={() => duyet("regenerate")}>
              <IconLamLai className="h-4 w-4" />
              {dangGui === "regenerate" ? "Đang xếp lại…" : "Sửa rồi đề xuất lại"}
            </Button>
          </div>

          {boBot.length > 0 && (
            <p className="mt-2 text-[12px] font-semibold text-muted">
              Đang bỏ {boBot.length} điểm — các điểm đó quay về nhóm chờ xếp chuyến khác.
            </p>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2.5">
            {xacNhanHuy ? (
              <>
                <span className="text-[13px] font-bold text-hazard-dark">
                  Huỷ tuyến thì không lấy lại được. Chắc chưa?
                </span>
                <span className="flex-1" />
                <Button size="sm" variant="outline" onClick={() => setXacNhanHuy(false)}>
                  Không, giữ lại
                </Button>
                <Button size="sm" variant="danger" disabled={dangGui !== ""} onClick={() => duyet("cancel")}>
                  {dangGui === "cancel" ? "Đang huỷ…" : "Huỷ thật"}
                </Button>
              </>
            ) : (
              <Button size="sm" variant="danger" disabled={dangGui !== ""} onClick={() => setXacNhanHuy(true)}>
                Huỷ tuyến
              </Button>
            )}
          </div>
        </>
      )}

      {/* Lối vào quản lý kíp & sự cố — gắn với nghiệp vụ tuyến: duyệt xong tuyến
          là xếp kíp cho chuyến, sự cố phát sinh trên chuyến cũng xử lý tại đây.
          Đặt ngay trong màn hàng đợi này thay vì sửa nav console, ai mở tab
          Tuyến gộp cũng thấy, kể cả khi chưa có tuyến nào chờ duyệt. */}
      <KipVaSuCo />
    </>
  );
}
