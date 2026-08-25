"use client";

/** Tổng quan · Vận hành & chi phí · Chất lượng AI · Agent run.
 *
 * Mọi con số ở đây tính từ dữ liệu thật trong CSDL. Phần nào đến từ bản ghi
 * mô phỏng thì có nhãn "dữ liệu demo mô phỏng" đi kèm — số mô phỏng và số đo
 * thật không được trộn vào nhau mà không nói gì.
 */

import * as React from "react";

import { Button, Card, EmptyState, ErrorState, SeedBadge, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { ngayGioVn, phanTram, soVn, tienUsd } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  IconBoQua,
  IconCanhBao,
  IconChao,
  IconDuyet,
  IconGiam,
  IconMuiTenPhai,
  IconTang,
  IconTim,
  IconTuChoi,
} from "@/lib/icons";
import type { AgentRunDetail, EvalSummary, OpsMetrics, Overview } from "@/lib/types";

export function OverviewScreen({ onGoto }: { onGoto: (nav: string) => void }) {
  const [du, setDu] = React.useState<Overview | null>(null);
  const [loi, setLoi] = React.useState("");
  const tai = React.useCallback(() => {
    api.overview().then(setDu).catch((e) => setLoi(e.message));
  }, []);
  React.useEffect(tai, [tai]);

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (!du) return <Skeleton className="h-96 w-full" />;

  const antoan = du.safety;
  const antoanXanh = antoan.hazard_missed_count === 0;

  return (
    <>
      <div className="mb-0.5 flex items-center gap-2 font-[family-name:var(--font-display)] text-2xl font-bold">
        Chào buổi sáng
        <IconChao className="h-5 w-5 text-leaf" />
      </div>
      <div className="mb-4 text-sm font-semibold text-muted">Hôm nay có gì cần anh xử lý?</div>

      {du.alerts.map((c) => (
        <div
          key={c.id}
          className={cn(
            "mb-4 flex items-center gap-3 rounded-2xl border px-4 py-3.5 shadow-[var(--shadow-xs)] transition-all duration-200",
            c.severity === "critical"
              ? "bg-hazard-soft border-hazard/30 text-hazard-dark"
              : "bg-amber-soft border-amber-line/60 text-amber"
          )}
        >
          <span className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-hazard text-white shadow-xs">
            <IconCanhBao className="h-5 w-5" />
          </span>
          <span className="flex-1 text-sm font-bold">{c.title}</span>
          <Button size="sm" variant="outline" onClick={() => api.runs().then(() => onGoto("pickup"))}>
            Xem
          </Button>
        </div>
      ))}

      <div className="mb-4 grid grid-cols-2 gap-3.5 xl:grid-cols-4">
        <Card className="cursor-pointer p-4 transition-all duration-300 ease-[var(--ease-spring)] hover:-translate-y-1 hover:shadow-[var(--shadow-md)]" onClick={() => onGoto("pickup")}>
          <div className="mb-1.5 text-xs font-bold text-muted uppercase tracking-wider">Cần duyệt</div>
          <div className="font-[family-name:var(--font-display)] text-[32px] font-bold leading-none tabular-nums">{du.queues.total}</div>
          <div className="mt-1.5 text-[11px] font-semibold text-muted">
            {du.queues.pickup} thu gom · {du.queues.labels} nhãn · {du.queues.routes} tuyến
          </div>
          <div className="mt-2 flex items-center gap-1 text-xs font-extrabold text-leaf">
            Duyệt ngay
            <IconMuiTenPhai className="h-3.5 w-3.5" />
          </div>
        </Card>

        <Card className="p-4 transition-all duration-300 ease-[var(--ease-spring)] hover:-translate-y-1 hover:shadow-[var(--shadow-md)]">
          <div className="mb-1.5 text-xs font-bold text-muted uppercase tracking-wider">Lượt phân loại tuần này</div>
          <div className="font-[family-name:var(--font-display)] text-[32px] font-bold leading-none tabular-nums">
            {soVn(du.classifications_this_week)}
          </div>
          <div className="mt-1.5 text-[11px] font-extrabold text-leaf-dark">
            {du.growth === null ? (
              "chưa có tuần trước để so"
            ) : (
              <span className="inline-flex items-center gap-1">
                {du.growth >= 0 ? <IconTang className="h-3.5 w-3.5" /> : <IconGiam className="h-3.5 w-3.5" />}
                {phanTram(Math.abs(du.growth))} so với tuần trước
              </span>
            )}
          </div>
        </Card>

        <Card className="p-4 transition-all duration-300 ease-[var(--ease-spring)] hover:-translate-y-1 hover:shadow-[var(--shadow-md)]">
          <div className="mb-1.5 text-xs font-bold text-muted uppercase tracking-wider">Độ chính xác (có người xác nhận)</div>
          <div className="font-[family-name:var(--font-display)] text-[32px] font-bold leading-none tabular-nums">
            {phanTram(du.accuracy)}
          </div>
          <div className="mt-1.5 text-[11px] font-semibold text-muted">trên {du.verified_count} ca đã xác nhận</div>
        </Card>

        {/* Chỉ số an toàn cốt lõi của đề — nằm ở tổng quan, không giấu trong trang eval. */}
        <Card
          className={cn(
            "p-4 transition-all duration-300 ease-[var(--ease-spring)] hover:-translate-y-1 hover:shadow-[var(--shadow-md)]",
            antoanXanh ? "bg-leaf-soft/60 border-leaf-mint/40" : "bg-hazard-soft/80 border-hazard/30"
          )}
        >
          <div className="mb-1.5 text-xs font-bold" style={{ color: antoanXanh ? "var(--color-leaf-dark)" : "var(--color-hazard-dark)" }}>
            <span className="inline-flex items-center gap-1.5">
              <IconCanhBao className="h-3.5 w-3.5" />
              Rác nguy hại bị bỏ sót
            </span>
          </div>
          <div
            className="font-[family-name:var(--font-display)] text-[32px] font-bold leading-none tabular-nums"
            style={{ color: antoanXanh ? "var(--color-leaf-dark)" : "var(--color-hazard-dark)" }}
          >
            {antoan.hazard_missed_count}
          </div>
          <div className="mt-1.5 text-[11px] font-semibold" style={{ color: antoanXanh ? "var(--color-amber-green)" : "var(--color-amber-brown)" }}>
            mục tiêu 0 · trên {antoan.hazard_total} ca nguy hại
          </div>
        </Card>
      </div>

      <div className="grid gap-3.5 grid-cols-1 xl:grid-cols-[1.4fr_1fr]">
        <Card className="p-4">
          <div className="mb-3.5 text-sm font-bold">Phân bố nhóm rác trong tuần</div>
          <div className="mb-3.5 flex h-[18px] overflow-hidden rounded-full">
            {du.category_distribution.map((c) => (
              <span key={c.code} style={{ width: `${c.share * 100}%`, background: c.bin_color || "var(--color-neutral)" }} />
            ))}
          </div>
          <div className="flex flex-wrap gap-3 text-xs font-bold text-ink-soft">
            {du.category_distribution.map((c) => (
              <span key={c.code} className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-md" style={{ background: c.bin_color || "var(--color-neutral)" }} />
                {c.name} {phanTram(c.share, 0)}
              </span>
            ))}
          </div>
        </Card>

        <div className="rounded-2xl bg-[linear-gradient(150deg,var(--color-leaf),var(--color-leaf-dark))] p-4 text-white">
          <div className="mb-3 text-sm font-bold">Hiệu quả điều phối</div>
          <div className="font-[family-name:var(--font-display)] text-[30px] font-bold leading-tight">
            {du.routing_efficiency.so_yeu_cau} yêu cầu
            <br />→ {du.routing_efficiency.so_chuyen} chuyến
          </div>
          <div className="mt-3.5 rounded-xl bg-surface/20 px-3 py-2.5 text-[13px] font-bold">
            Giảm {du.routing_efficiency.giam_so_chuyen} chuyến xe · tiết kiệm ~
            {soVn(du.routing_efficiency.tiet_kiem_km, 1)} km
          </div>
        </div>
      </div>
    </>
  );
}

export function OpsScreen() {
  const [du, setDu] = React.useState<OpsMetrics | null>(null);
  const [loi, setLoi] = React.useState("");
  const tai = React.useCallback(() => {
    api.opsMetrics().then(setDu).catch((e) => setLoi(e.message));
  }, []);
  React.useEffect(tai, [tai]);

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (!du) return <Skeleton className="h-96 w-full" />;

  const nganSach = du.cost.budget;
  const tiLeNganSach = Math.min(1, nganSach.used / nganSach.limit);

  return (
    <>
      <div className="mb-4 flex items-center gap-2.5">
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Vận hành & chi phí</div>
        {du.has_seed_data && <SeedBadge />}
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3.5">
        <Card className="p-4">
          <div className="mb-1 text-[13px] font-bold text-muted">Chi phí kỳ này</div>
          <div className="font-[family-name:var(--font-display)] text-[34px] font-bold leading-none">
            {tienUsd(du.cost.total)}
          </div>
          <div className="mt-1 text-xs font-semibold text-muted">
            {soVn(du.cost.count)} lượt · {tienUsd(du.cost.cost_per_1000)} / 1.000 lượt
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-line-light">
            <div
              className="h-full rounded-full"
              style={{ width: `${tiLeNganSach * 100}%`, background: tiLeNganSach > 0.8 ? "var(--color-hazard)" : "var(--color-leaf)" }}
            />
          </div>
          <div className="mt-1.5 text-[11px] font-bold text-muted">
            {tienUsd(nganSach.used)} / {tienUsd(nganSach.limit)} ngân sách
            {tiLeNganSach > 0.8 && <span className="text-hazard-dark"> · đã vượt 80%</span>}
          </div>
        </Card>

        <div className="rounded-2xl bg-[linear-gradient(150deg,var(--color-leaf),var(--color-leaf-dark))] p-4 text-white">
          <div className="mb-2 text-[13px] font-bold opacity-90">
            Định tuyến nhiều tầng vs dùng {du.cost.baseline_model} cho mọi ảnh
          </div>
          <div className="flex items-baseline gap-3">
            <span className="font-[family-name:var(--font-display)] text-[30px] font-bold">{tienUsd(du.cost.total)}</span>
            <span className="text-[15px] font-semibold line-through opacity-80">
              {tienUsd(du.cost.baseline_full_model)}
            </span>
          </div>
          <div className="mt-3 inline-block rounded-full bg-surface/20 px-3.5 py-1.5 text-sm font-extrabold">
            Tiết kiệm {phanTram(du.cost.saved_ratio, 0)}
          </div>
          {!du.cost.baseline_price_known && (
            <div className="mt-2 text-[11px] font-semibold opacity-90">
              Model đang dùng chưa có trong bảng giá nên con số này là mốc so sánh nội bộ, chưa dùng được cho báo cáo.
            </div>
          )}
        </div>
      </div>

      <Card className="mb-4 p-4">
        <div className="mb-3 text-sm font-bold">So sánh các tầng model</div>
        <div className="gb-hscroll">
          <div
            className="grid gap-2 border-b border-line-4 pb-2 text-[11px] font-extrabold text-muted"
            style={{ gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr", minWidth: 560 }}
          >
            <span>Tầng</span>
            <span>Tỉ lệ</span>
            <span>Chính xác</span>
            <span>Chi phí/ảnh</span>
            <span>Độ trễ p95</span>
          </div>
          {du.cost.by_tier.map((t) => (
            <div
              key={t.tier}
              className="grid gap-2 border-b border-line-5 py-2.5 text-xs font-bold"
              style={{ gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr", minWidth: 560 }}
            >
              <span>{t.label_vi}</span>
              <span>{phanTram(t.share, 1)}</span>
              <span>{t.accuracy === null ? "chưa có ca xác nhận" : phanTram(t.accuracy, 1)}</span>
              {/* Chưa tra được giá thì nói thẳng là chưa biết. Hiện "$0.0000" ở
                  đây khiến cả tầng T1 trông như miễn phí, trong khi thật ra là
                  chưa ai tra ra giá của model đang chạy. */}
              <span className={t.price_known ? "" : "text-muted"}>
                {t.price_known ? tienUsd(t.cost_per_item) : "chưa có giá"}
              </span>
              <span>{soVn(t.p95_latency_ms)} ms</span>
            </div>
          ))}
        </div>
        {du.cost.by_tier.some((t) => !t.price_known) && (
          <div className="mt-2.5 text-[11px] font-semibold leading-snug text-muted">
            Tầng ghi <b>chưa có giá</b>: nhà cung cấp không công bố giá theo token cho model đang chạy, nên số token
            thì đo được mà quy ra tiền thì chưa. Đừng đọc thành &ldquo;miễn phí&rdquo;.
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-4 text-xs font-bold text-muted">
          <span>Trúng cache: {phanTram(du.routing.cache_hit_rate)}</span>
          <span>Model local chốt: {phanTram(du.routing.local_model_rate)}</span>
          <span>Leo tầng T2: {phanTram(du.routing.escalation_rate)}</span>
          <span>Từ chối trả lời: {phanTram(du.routing.refusal_rate)}</span>
        </div>
      </Card>

      <div className="mb-4 grid grid-cols-2 gap-3.5">
        <Card className="p-4">
          <div className="mb-3 text-sm font-bold">Độ trễ</div>
          <div className="mb-3 rounded-xl bg-console-bg p-3 text-[13px] font-bold">
            Từ lúc gửi tới lúc có câu trả lời — p50 {soVn(du.latency.end_to_end.p50)} ms · p95{" "}
            {soVn(du.latency.end_to_end.p95)} ms
          </div>
          {du.latency.by_node.map((n) => (
            <div key={n.node} className="flex justify-between border-b border-line-5 py-1.5 text-xs font-bold last:border-0">
              <span className="text-muted-2">{n.node}</span>
              <span>
                p50 {soVn(n.p50)} · p95 {soVn(n.p95)} ms
              </span>
            </div>
          ))}
        </Card>

        <Card className="p-4">
          <div className="mb-3 text-sm font-bold">Lỗi</div>
          <div className="mb-3 text-[13px] font-bold">
            Tỉ lệ lỗi node: <span className="text-hazard-dark">{phanTram(du.errors.rate, 2)}</span> · chạm rate limit:{" "}
            {du.errors.rate_limit_hits} lần
          </div>
          {du.errors.recent.length === 0 ? (
            <div className="text-xs font-semibold text-muted">Chưa ghi nhận lỗi nào gần đây.</div>
          ) : (
            du.errors.recent.map((e, i) => (
              <div key={i} className="border-b border-line-5 py-1.5 text-xs font-semibold last:border-0">
                <b>{e.node}</b> · {e.error_type} · run #{e.run_id}
              </div>
            ))
          )}
        </Card>
      </div>

      <Card className="mb-4 p-4">
        <div className="mb-1 text-sm font-bold">Cấu hình model đang chạy</div>
        <div className="mb-3 text-xs font-semibold text-muted">
          {du.provider.single_provider
            ? "Cả ba tầng đang dùng chung một nhà cung cấp — hết quota ở đó là mất cả ba."
            : "Mỗi tầng chạy trên nhà cung cấp riêng: cạn quota một nơi không làm đứng các tầng còn lại."}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px] font-semibold">
            <thead>
              <tr className="text-[11px] uppercase text-muted">
                <th className="pb-1.5">Tầng</th>
                <th className="pb-1.5">Nhà cung cấp</th>
                <th className="pb-1.5">Model</th>
                <th className="pb-1.5">API key</th>
              </tr>
            </thead>
            <tbody>
              {(du.provider.tiers ?? []).map((t) => (
                <tr key={t.tier} className="border-t border-line-5">
                  <td className="py-1.5 pr-3">{t.label_vi}</td>
                  <td className="py-1.5 pr-3">
                    <b>{t.provider}</b>
                  </td>
                  <td className="py-1.5 pr-3">{t.model || "—"}</td>
                  <td className={`py-1.5 ${t.has_api_key ? "" : "text-hazard-dark"}`}>
                    {t.has_api_key ? "đã cấu hình" : "CHƯA cấu hình"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-3 text-[13px] font-semibold leading-loose text-ink-soft">
          T0.5 — model local (CLIP): {du.provider.local_model_enabled ? "đang bật" : "đang tắt"} ·{" "}
          {du.provider.local_model_loaded ? "đã nạp vào bộ nhớ" : "chưa nạp (nạp lần đầu khi có ảnh)"}
          {du.provider.local_model_runtime ? (
            <>
              {" · "}
              <b>
                {du.provider.local_model_runtime === "onnx"
                  ? "bản nén int8, chạy tại chỗ"
                  : "bản đầy đủ (torch)"}
              </b>
            </>
          ) : null}{" "}
          · prompt <b>{du.provider.prompt_version}</b>
        </div>
        {du.retrieval ? (
          <div className="mt-1 text-[13px] font-semibold leading-loose text-ink-soft">
            Truy hồi quy định:{" "}
            <b>
              {du.retrieval.che_do === "hybrid"
                ? "hybrid — từ khoá + embedding"
                : "thuần từ khoá (BM25)"}
            </b>{" "}
            · {du.retrieval.chunks_co_embedding}/{du.retrieval.chunks_tong} đoạn có vector
            {du.retrieval.che_do === "hybrid" ? (
              <>
                {" "}
                · {du.retrieval.embedding_model || "—"} · trọng số vector{" "}
                {du.retrieval.vector_weight.toLocaleString("vi-VN")}
              </>
            ) : null}
          </div>
        ) : null}
      </Card>

      {du.co_che ? (
        <Card className="mb-4 p-4">
          <div className="mb-3 text-sm font-bold">Cơ chế đang bật</div>
          <div className="space-y-2 text-[13px] font-semibold">
            <div>
              {du.co_che.rate_limit_dang_ky.bat ? (
                <span className="inline-flex items-center gap-1.5 text-leaf-dark">
                  <IconDuyet className="h-3.5 w-3.5" strokeWidth={3} />
                  Giới hạn đăng ký: {du.co_che.rate_limit_dang_ky.so_lan} lần /{" "}
                  {du.co_che.rate_limit_dang_ky.cua_so_giay} giây mỗi IP
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-hazard-dark">
                  <IconCanhBao className="h-3.5 w-3.5" />
                  Giới hạn đăng ký: đang tắt
                </span>
              )}
            </div>
            <div>
              {du.co_che.khoa_thiet_bi.so_thung_khoa_rieng > 0 ? (
                <span className="text-ink-soft">
                  Khoá thiết bị: {du.co_che.khoa_thiet_bi.so_thung_khoa_rieng}/
                  {du.co_che.khoa_thiet_bi.tong_thung} thùng có khoá riêng,{" "}
                  {du.co_che.khoa_thiet_bi.tong_thung - du.co_che.khoa_thiet_bi.so_thung_khoa_rieng} thùng
                  dùng khoá chung
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-hazard-dark">
                  <IconCanhBao className="h-3.5 w-3.5" />
                  Khoá thiết bị: mọi thùng đang dùng khoá chung
                </span>
              )}
            </div>
            <div>
              {du.co_che.duong_di_that.bat ? (
                <span className="inline-flex items-center gap-1.5 text-leaf-dark">
                  <IconDuyet className="h-3.5 w-3.5" strokeWidth={3} />
                  Khoảng cách xếp tuyến: đường đi thật ({du.co_che.duong_di_that.dich_vu})
                </span>
              ) : (
                <span className="text-ink-soft">Khoảng cách xếp tuyến: đường chim bay</span>
              )}
            </div>
          </div>
        </Card>
      ) : null}

      <div className="rounded-2xl border border-amber-line bg-amber-soft p-4">
        <div className="mb-2.5 flex items-center gap-1.5 text-xs font-extrabold text-amber">
          <IconCanhBao className="h-3.5 w-3.5" />
          GIỚI HẠN ĐÃ BIẾT CỦA HỆ THỐNG
        </div>
        <div className="text-[13px] font-semibold leading-loose text-amber-dark">
          {du.known_limitations.map((g) => (
            <div key={g}>• {g}</div>
          ))}
        </div>
      </div>
    </>
  );
}

export function QualityScreen() {
  const [du, setDu] = React.useState<EvalSummary | null>(null);
  const [loi, setLoi] = React.useState("");
  const tai = React.useCallback(() => {
    api.evalSummary().then(setDu).catch((e) => setLoi(e.message));
  }, []);
  React.useEffect(tai, [tai]);

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (!du) return <Skeleton className="h-96 w-full" />;

  const xanh = du.safety.hazard_missed_count === 0;

  return (
    <>
      <div className="mb-4 flex items-center gap-2.5">
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Chất lượng AI</div>
        {du.has_seed_data && <SeedBadge />}
      </div>

      <div
        className="mb-4 rounded-2xl border-2 p-6 text-center"
        style={{ background: xanh ? "var(--color-leaf-soft)" : "var(--color-hazard-soft)", borderColor: xanh ? "var(--color-leaf-line)" : "var(--color-hazard)" }}
      >
        <div className="text-[13px] font-extrabold uppercase tracking-wide" style={{ color: xanh ? "var(--color-leaf-dark)" : "var(--color-hazard-dark)" }}>
          {du.safety.label_vi}
        </div>
        <div
          className="my-2 font-[family-name:var(--font-display)] text-5xl font-bold"
          style={{ color: xanh ? "var(--color-leaf-dark)" : "var(--color-hazard-dark)" }}
        >
          {du.safety.hazard_missed_count} / {du.safety.hazard_total}
        </div>
        <div className="text-[13px] font-bold" style={{ color: xanh ? "var(--color-amber-green)" : "var(--color-amber-brown)" }}>
          mục tiêu: {du.safety.target}
        </div>
      </div>

      <Card className="mb-4 p-4">
        <div className="mb-3 text-sm font-bold">Chỉ số trên các ca đã có người xác nhận</div>
        <div className="flex flex-wrap gap-6 text-[13px] font-bold">
          <span>Accuracy: {phanTram(du.accuracy)}</span>
          <span>Recall nhóm nguy hại: {phanTram(du.hazard_recall)}</span>
          <span>Cỡ mẫu: {du.verified_count} ca</span>
        </div>
      </Card>

      {du.by_dataset.length > 0 && (
        <Card className="mb-4 p-4">
          <div className="mb-1 text-sm font-bold">Tách riêng hai bộ dữ liệu</div>
          <p className="mb-3 text-xs font-semibold text-muted">
            Chênh lệch giữa dataset công khai và ảnh tự chụp tại Việt Nam là phát hiện đáng nói nhất của phần dữ liệu —
            không bao giờ đưa con số của bộ công khai lên slide như thể đó là năng lực sản phẩm.
          </p>
          <div className="gb-hscroll">
            <table className="w-full min-w-[620px] text-left text-[13px] font-bold">
              <thead className="text-[11px] font-extrabold text-muted">
                <tr>
                  <th className="pb-2">Bộ dữ liệu</th>
                  <th>Cỡ mẫu</th>
                  <th>Accuracy</th>
                  <th>Macro-F1</th>
                  <th>Recall nguy hại</th>
                  <th>precision@5</th>
                </tr>
              </thead>
              <tbody>
                {du.by_dataset.map((d, i) => (
                  <tr key={i} className="border-t border-line-5">
                    <td className="py-2">
                      {d.dataset === "public" ? "Dataset công khai" : d.dataset === "own" ? "Ảnh tự chụp tại VN" : d.dataset}
                      {d.is_seed && <SeedBadge className="ml-2" />}
                    </td>
                    <td>{d.test_size}</td>
                    <td>{phanTram(d.accuracy)}</td>
                    <td>{phanTram(d.macro_f1)}</td>
                    <td>{phanTram(d.hazard_recall)}</td>
                    <td>{phanTram(d.retrieval_precision_at_5)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card className="p-4">
        <div className="mb-3 text-sm font-bold">Thư viện ca nhận sai ({du.failures.length})</div>
        {du.failures.length === 0 ? (
          <EmptyState icon={IconTim} title="Chưa có ca nhận sai nào được ghi nhận" />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {du.failures.slice(0, 12).map((f) => (
              <div key={f.id} className="rounded-xl border border-line p-3">
                <div className="mb-2 aspect-square rounded-lg bg-[repeating-linear-gradient(135deg,var(--color-recycle-muted),var(--color-recycle-muted)_7px,var(--color-skeleton-blue)_7px,var(--color-skeleton-blue)_14px)]" />
                <div className="text-xs font-extrabold">{f.item_name}</div>
                <div className="text-[11px] font-semibold text-muted">
                  đúng: {f.true_category_code} · AI: {f.predicted_category_code}
                </div>
                <div className="mt-1 text-[11px] font-bold text-hazard-dark">{f.cause}</div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}

export function AgentRunScreen() {
  const [ds, setDs] = React.useState<Awaited<ReturnType<typeof api.runs>>["items"] | null>(null);
  const [chiTiet, setChiTiet] = React.useState<AgentRunDetail | null>(null);
  const [loi, setLoi] = React.useState("");

  React.useEffect(() => {
    api
      .runs()
      .then(async (d) => {
        setDs(d.items);
        if (d.items.length) setChiTiet(await api.run(d.items[0].id));
      })
      .catch((e) => setLoi(e.message));
  }, []);

  if (loi) return <ErrorState message={loi} />;
  if (!ds) return <Skeleton className="h-96 w-full" />;

  return (
    <>
      <div className="mb-4 font-[family-name:var(--font-display)] text-[22px] font-bold">Agent run — trace</div>
      <div className="grid items-start gap-4 grid-cols-1 lg:grid-cols-[300px_1fr]">
        <div>
          {ds.slice(0, 12).map((r) => (
            <button
              key={r.id}
              onClick={() => api.run(r.id).then(setChiTiet)}
              className="mb-2 w-full cursor-pointer rounded-xl bg-surface p-3 text-left"
              style={{ border: chiTiet?.id === r.id ? "2px solid var(--color-leaf)" : "1px solid var(--color-line-3)" }}
            >
              <div className="flex justify-between text-[13px] font-extrabold">
                <span>#{r.id}</span>
                <span className={r.status === "ok" ? "text-leaf-dark" : "text-hazard-dark"}>{r.status}</span>
              </div>
              <div className="text-[11px] font-semibold text-muted">
                {r.kind} · {soVn(r.duration_ms)} ms · {tienUsd(r.total_cost_usd)}
              </div>
            </button>
          ))}
        </div>

        {chiTiet && (
          <Card className="p-4">
            <div className="mb-3 text-sm font-bold">
              Run #{chiTiet.id} · {ngayGioVn(chiTiet.started_at)}
            </div>
            {chiTiet.nodes.map((n, i) => (
              <div key={i} className="flex gap-3 border-b border-line-5 py-2.5 last:border-0">
                <span
                  className="flex h-6 w-6 flex-none items-center justify-center rounded-full text-xs font-extrabold"
                  style={{
                    background: n.status === "ok" ? "var(--color-leaf-soft)" : n.status === "skipped" ? "var(--color-muted-bg)" : "var(--color-hazard-soft)",
                    color: n.status === "ok" ? "var(--color-leaf-dark)" : n.status === "skipped" ? "var(--color-muted)" : "var(--color-hazard-dark)",
                  }}
                >
                  {n.status === "ok" ? (
                    <IconDuyet className="h-3.5 w-3.5" strokeWidth={3} />
                  ) : n.status === "skipped" ? (
                    <IconBoQua className="h-3 w-3" />
                  ) : (
                    <IconTuChoi className="h-3.5 w-3.5" strokeWidth={3} />
                  )}
                </span>
                <div className="flex-1">
                  <div className="text-[13px] font-extrabold">{n.node}</div>
                  <div className="text-[11px] font-semibold text-muted">
                    {soVn(n.duration_ms)} ms · {tienUsd(n.cost_usd)}
                    {n.llm_calls ? ` · ${n.tokens_in}+${n.tokens_out} token` : ""}
                    {n.cache_hits ? " · trúng cache" : ""}
                    {n.error_type ? ` · ${n.error_type}` : ""}
                  </div>
                  {Object.keys(n.meta ?? {}).length > 0 && (
                    <div className="mt-1 text-[11px] font-semibold text-ink-soft">
                      {Object.entries(n.meta)
                        .map(([k, v]) => `${k}: ${String(v)}`)
                        .join(" · ")}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div className="mt-3 rounded-xl bg-console-bg p-3 text-[11px] font-semibold text-muted">
              Đường đã đi: {chiTiet.path.join(" → ")}
            </div>
          </Card>
        )}
      </div>
    </>
  );
}
