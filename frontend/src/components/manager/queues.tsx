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
import { api } from "@/lib/api";
import { doTinCay, kg, ngayGioVn, ngayVn, phanTram, soVn } from "@/lib/format";
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
            {ds.map((yc) => (
              <button
                key={yc.id}
                onClick={() => api.pickup(yc.id).then(setDangChon)}
                className="mb-2.5 w-full cursor-pointer rounded-2xl bg-white p-3.5 text-left"
                style={{ border: dangChon?.id === yc.id ? "2px solid #2fae66" : "1px solid #eceae3" }}
              >
                <div className="mb-1 flex justify-between">
                  <span className="text-[13px] font-extrabold text-bulky">#PR-{String(yc.id).padStart(4, "0")}</span>
                  <span className="rounded-md bg-amber-soft px-2 py-0.5 text-[11px] font-extrabold text-amber">
                    {kg(yc.weight_max_kg)}
                  </span>
                </div>
                <div className="text-[13px] font-bold">
                  {yc.unit} · {yc.resident?.full_name}
                </div>
                <div className="mt-1 text-[11px] font-semibold text-muted">mong muốn {ngayVn(yc.preferred_date)}</div>
              </button>
            ))}
          </div>

          {dangChon && (
            <Card className="overflow-hidden p-0">
              <div className="border-b border-[#f2ede2] px-5 py-4">
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
                    <span className="text-muted-2">Khoảng khối lượng ước tính</span>
                    <span>
                      {dangChon.weight_min_kg}–{dangChon.weight_max_kg} kg
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
                  <div className="mb-3.5 rounded-xl border border-[#e6ece6] bg-[#f7f9f7] px-3.5 py-3 text-xs font-semibold leading-loose text-ink-soft">
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
                  <div className="rounded-xl border-[1.5px] border-dashed border-[#cbb8ee] bg-[#faf8fe] p-3.5">
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

              <div className="flex flex-wrap items-center gap-2.5 border-t border-[#f2ede2] bg-cream-soft px-5 py-3.5">
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
                <div className="border-t border-[#f2ede2] px-5 py-3.5">
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
  const [dangMo, setDangMo] = React.useState<number | null>(null);
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

  function theCa(ca: Classification) {
    const thieu = ca.min_confidence - ca.confidence;
    return (
      <Card key={ca.classification_id} className="p-4">
        {/* Ảnh tải LAZY — chỉ dựng `<AnhCoToken>` khi người duyệt mở thẻ
            (`dangMo`). Dựng cho mọi thẻ ngay khi hàng đợi lên là một `fetch`
            có token bắn cùng lúc cho từng ca: mở màn 100 ca là 100 lệnh tải ảnh
            đồng thời vào một máy chủ 512 MB, cộng 100 `blob:` giữ trong bộ nhớ
            trình duyệt. Tải theo yêu cầu khi bấm vào thẻ — ca thứ 101 cũng vô
            hại. AnhCoToken tự lo ca hỏi bằng chữ (`media_id == null`): 0 lệnh
            gọi mạng, hiện ô giữ chỗ. */}
        {dangMo === ca.classification_id && (
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
        <div className="my-2 text-[11px] font-semibold text-muted">Lý do từ chối: {ca.refusal_label_vi}</div>
        {dangMo === ca.classification_id ? (
          <div className="flex flex-wrap gap-1.5">
            {danhMuc.map((dm) => (
              <Button
                key={dm.code}
                size="sm"
                variant="outline"
                onClick={async () => {
                  await api.verifyLabel(ca.classification_id, dm.code);
                  setDangMo(null);
                  tai();
                }}
              >
                <IconNhomRac code={dm.code} className="h-3.5 w-3.5" />
                {dm.name}
              </Button>
            ))}
          </div>
        ) : (
          <Button size="sm" onClick={() => setDangMo(ca.classification_id)}>
            Chọn nhãn đúng & trả lời
          </Button>
        )}
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
          <div className="flex flex-wrap gap-2 text-xs font-bold text-[#7a5c14]">
            {du.hard_cases.map((c) => (
              <span key={c.pair} className="rounded-lg bg-white px-2.5 py-1.5" title={c.note}>
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
              <div className="grid grid-cols-2 gap-3.5">{cacCaPhaiXem.map(theCa)}</div>
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
                  <div className="mb-2 rounded-xl border border-[#f6cdb8] bg-hazard-soft px-3.5 py-2.5 text-[13px] font-bold text-hazard-dark">
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
                <div className="grid grid-cols-2 gap-3.5">{cacCaDuyetNhanh.map(theCa)}</div>
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
        Điểm thưởng chỉ tính trên khối lượng do người xác nhận, không tính trên con số AI ước lượng.
        <br />
        Con số dưới đây phải là số đội thu gom đã cân tại chỗ. Chưa có số cân thì để trống —
        đừng ước lượng thay họ, vì chính con số này chốt trạng thái và điểm thưởng.
      </div>

      {ds.length === 0 ? (
        <EmptyState icon={IconChucMung} title="Chưa có kiện nào chờ xác nhận khối lượng" />
      ) : (
        <div className="grid gap-3.5">
          {ds.map((yc) => {
            const daXacNhan = ketQua[yc.id];
            const trangThai = daXacNhan ? daXacNhan.status : "";
            return (
              <Card key={yc.id} className="p-4">
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
                    <span className="text-muted-2">AI ước lượng</span>
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
                      <div className="flex items-center gap-2 rounded-xl border border-amber-line bg-amber-soft px-4 py-3 text-sm font-extrabold text-[#8a6414]">
                        <IconCanhBao className="h-5 w-5 flex-none" />
                        Tranh chấp — khối lượng thật lệch xa khoảng ước lượng
                      </div>
                    )}
                    <div className="mt-2 text-[11px] font-semibold text-muted">
                      Đã chốt {soKg[yc.id]} kg · AI ước lượng {yc.weight_min_kg}–{yc.weight_max_kg} kg
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
                        className="h-12 w-full rounded-xl border border-line-2 bg-white px-3.5 text-base font-bold text-ink-soft outline-none focus:border-leaf"
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

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (ds === null) return <Skeleton className="h-96 w-full" />;

  return (
    <>
      <div className="mb-3.5 font-[family-name:var(--font-display)] text-[22px] font-bold">Duyệt tuyến gộp</div>
      {thongBao && <div className="mb-3 rounded-xl bg-leaf-soft px-4 py-3 text-sm font-bold text-leaf-dark">{thongBao}</div>}
      {/* Lỗi khi DUYỆT không được phép thay thế cả màn hình như `loi` ở trên:
          tuyến vẫn đang hiện, người duyệt cần đọc lỗi mà không mất ngữ cảnh. */}
      {loiDuyet && (
        <div className="mb-3 rounded-xl border border-[#f6cdb8] bg-hazard-soft px-4 py-3 text-sm font-bold text-hazard-dark">
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
          <div className="mb-4 flex items-center gap-4 rounded-2xl bg-[linear-gradient(150deg,#16211a,#1c3326)] px-5 py-4 text-white">
            <span className="rounded-lg bg-amber-line px-2.5 py-1 text-[11px] font-extrabold text-[#5a4410]">
              AI ĐỀ XUẤT — CHỜ DUYỆT
            </span>
            <div className="flex-1">
              <div className="font-[family-name:var(--font-display)] text-[17px] font-bold">
                Chuyến {tuyen.window} · {ngayVn(tuyen.service_date)}
              </div>
              <div className="text-xs font-semibold text-[#9fb3a6]">
                {tuyen.stop_count} điểm dừng · {kg(tuyen.total_weight_kg)} · ~{soVn(tuyen.est_distance_km, 1)} km
                {tuyen.team ? ` · ${tuyen.team.full_name}` : ""}
              </div>
            </div>
          </div>

          {/* Dưới xl thì bản đồ và danh sách điểm dừng xếp dọc. Ép hai cột trên
              màn 768px cho ra hai cột ~390px — đo thật thì cột phải chỉ còn
              158px, không đọc được. */}
          <div className="grid items-start gap-4 grid-cols-1 xl:grid-cols-2">
            <Card className="p-4">
              <div className="mb-2.5 text-[13px] font-bold text-muted">Điểm dừng</div>
              {(tuyen.stops ?? []).map((s) => {
                // Bỏ điểm khỏi tuyến khớp theo `stop_id` — khoá chính của điểm
                // dừng, có ở CẢ HAI loại. Trước đây khớp theo `request_id` nên
                // điểm dừng loại thùng không bao giờ bỏ được (gói C0b đã sửa).
                const laThung = s.stop_kind === "thung";
                const daBo = boBot.includes(s.stop_id);
                const ten = s.diem_dung_vi || s.unit || `Điểm ${s.seq}`;
                const mota = laThung
                  ? `Thùng đầy ${Math.round(s.fill_percent ?? 0)}%${s.dia_chi ? ` · ${s.dia_chi}` : ""}`
                  : (s.items ?? []).map((i) => i.name).join(", ");
                return (
                  <div
                    key={s.stop_id}
                    className="mb-2 flex items-center gap-3 rounded-xl border border-line bg-cream-soft px-3 py-2.5"
                    style={{ opacity: daBo ? 0.4 : 1 }}
                  >
                    <span className="flex h-[26px] w-[26px] items-center justify-center rounded-lg bg-ink text-xs font-extrabold text-white">
                      {s.seq}
                    </span>
                    <div className="flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[13px] font-extrabold">{ten}</span>
                        {laThung && (
                          <span className="rounded-md bg-amber-line px-1.5 py-0.5 text-[10px] font-extrabold text-[#5a4410]">
                            THÙNG
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] font-semibold text-muted">{mota}</div>
                    </div>
                    <span className="text-[13px] font-extrabold text-recycle">
                      {laThung ? "—" : kg(s.weight_max_kg)}
                    </span>
                    <button
                      onClick={() =>
                        setBoBot((cu) =>
                          daBo ? cu.filter((x) => x !== s.stop_id) : [...cu, s.stop_id],
                        )
                      }
                      className="cursor-pointer text-muted"
                      title={daBo ? "Giữ lại điểm này" : "Bỏ khỏi tuyến"}
                      aria-label={daBo ? `Giữ lại điểm ${ten}` : `Bỏ điểm ${ten} khỏi tuyến`}
                    >
                      {daBo ? <IconHoanTac className="h-4 w-4" /> : <IconTuChoi className="h-4 w-4" />}
                    </button>
                  </div>
                );
              })}

              {/* So với bản agent đề xuất — chỉ hiện trên màn duyệt tuyến. Phần
                  diff này do backend tính sẵn (`route_diff`); frontend chỉ kể lại
                  và luôn kèm chú giải về phạm vi phép so để không bị hiểu nhầm
                  là "bỏ thùng khỏi tuyến không được ghi nhận". */}
              <div className="mt-3 rounded-xl border border-line bg-cream-soft px-3.5 py-3">
                <div className="mb-1.5 text-[12px] font-extrabold">So với bản agent đề xuất</div>
                {!coChinhSua ? (
                  <div className="flex items-center gap-1.5 text-[13px] font-bold text-leaf-dark">
                    <IconChucMung className="h-4 w-4 flex-none" />
                    Giữ nguyên bản agent đề xuất.
                  </div>
                ) : (
                  <div className="text-[13px] font-bold leading-loose">
                    {soBo > 0 && <div>Đã bỏ {soBo} điểm dừng khỏi tuyến</div>}
                    {doiThuTu && <div>Đã đổi thứ tự ghé</div>}
                    {soBo === 0 && !doiThuTu && <div>Đã chỉnh sửa so với bản agent đề xuất</div>}
                  </div>
                )}
                <div className="mt-1.5 text-[11px] font-semibold leading-relaxed text-muted">
                  Phần so sánh này chỉ tính điểm dừng là yêu cầu của cư dân; điểm dừng loại thùng chưa
                  nằm trong bản agent đề xuất.
                </div>
              </div>
            </Card>

            <div>
              <div className="mb-3.5 rounded-2xl border-[1.5px] border-dashed border-[#cbb8ee] bg-[#faf8fe] p-4">
                <div className="mb-2.5 flex items-center gap-1.5 text-[11px] font-extrabold text-bulky">
                  <IconAi className="h-3.5 w-3.5" />
                  AI GIẢI THÍCH — VÌ SAO GỘP THẾ NÀY
                </div>
                <div className="text-xs font-semibold leading-loose text-ink-soft">
                  Tiêu chí gộp:
                  <br />
                  {tuyen.reasoning?.criteria.map((c) => (
                    <React.Fragment key={c}>
                      • {c}
                      <br />
                    </React.Fragment>
                  ))}
                  {tuyen.reasoning?.excluded.slice(0, 3).map((e) => (
                    <React.Fragment key={e.request_id}>
                      • KHÔNG gộp #{e.request_id} ({e.unit}) vì {e.ly_do}
                      <br />
                    </React.Fragment>
                  ))}
                </div>
                <div className="mt-3 rounded-xl bg-leaf-soft px-3 py-2.5 text-[13px] font-bold text-leaf-dark">
                  So với đi lẻ: {tuyen.stop_count} chuyến → 1 chuyến · ~{soVn(tuyen.reasoning?.baseline_km ?? 0, 1)} km
                  → ~{soVn(tuyen.est_distance_km, 1)} km{" "}
                  <b>
                    (giảm{" "}
                    {tuyen.reasoning?.baseline_km
                      ? Math.round((tuyen.reasoning.saved_km / tuyen.reasoning.baseline_km) * 100)
                      : 0}
                    %)
                  </b>
                </div>
                {tuyen.reasoning?.note && (
                  <div className="mt-2 text-[11px] font-semibold text-muted">{tuyen.reasoning.note}</div>
                )}
              </div>

              <Card className="p-4">
                <div className="mb-2.5 text-xs font-bold text-muted">Bản đồ tuyến</div>
                {/* Bản cũ ở đây là một SVG vẽ tay, chia đều điểm dừng trái sang
                    phải — trông như bản đồ nhưng KHÔNG mang thông tin địa lý
                    nào. Trên màn duyệt một chuyến xe thật, thứ đó tệ hơn là
                    không có gì. Toạ độ thật đã có từ gói C2a. */}
                <div className="h-[260px] overflow-hidden rounded-xl">
                  <RouteMap stops={tuyen.stops ?? []} duong_di={tuyen.duong_di} />
                </div>
              </Card>
            </div>
          </div>

          {/* Hai quyết định người duyệt thật sự dùng hằng ngày để to và nằm
              trên; hai việc hiếm đẩy xuống hàng dưới, cỡ nhỏ. Huỷ tuyến không
              lùi lại được nên phải hỏi lại một nhịp. */}
          <div className="mt-5 flex flex-wrap items-center gap-3">
            {boBot.length === 0 ? (
              <Button size="lg" variant="leaf" disabled={dangGui !== ""} onClick={() => duyet("approve")}>
                <IconDuyet className="h-5 w-5" />
                {dangGui === "approve" ? "Đang duyệt…" : "Duyệt tuyến này"}
              </Button>
            ) : (
              <Button size="lg" variant="leaf" disabled={dangGui !== ""} onClick={() => duyet("approve_with_changes")}>
                <IconSua className="h-5 w-5" />
                {dangGui === "approve_with_changes"
                  ? "Đang duyệt…"
                  : `Duyệt, bỏ ${boBot.length} điểm`}
              </Button>
            )}
            <span className="text-[13px] font-semibold text-muted">
              {boBot.length === 0
                ? "Duyệt xong tuyến mới có hiệu lực và báo cho đội xe."
                : `Đang bỏ ${boBot.length} điểm — các điểm đó quay về nhóm chờ xếp chuyến khác.`}
            </span>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2.5">
            <Button size="sm" variant="outline" disabled={dangGui !== ""} onClick={() => duyet("regenerate")}>
              <IconLamLai className="h-4 w-4" />
              {dangGui === "regenerate" ? "Đang xếp lại…" : "Đề xuất lại"}
            </Button>
            <span className="flex-1" />
            {xacNhanHuy ? (
              <>
                <span className="text-[13px] font-bold text-hazard-dark">
                  Huỷ tuyến thì không lấy lại được. Chắc chưa?
                </span>
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
    </>
  );
}
