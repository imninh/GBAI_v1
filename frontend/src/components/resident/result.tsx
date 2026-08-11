"use client";

/** Ba biến thể màn kết quả: bình thường · nhóm nguy hại · "Mình chưa chắc".
 *
 * Ba màn này là nơi câu chuyện an toàn AI của đề hiện ra, nên chúng khác nhau
 * hoàn toàn về mặt thị giác chứ không chỉ đổi màu chip:
 *
 * - nhóm nguy hại: viền đôi, nền cam, cảnh báo lấy nguyên văn từ danh mục
 *   chuẩn trong CSDL và có dòng ghi rõ "không do AI tự viết";
 * - từ chối trả lời: tông xanh trung tính, **không phải màn lỗi** — vẫn hiện
 *   phỏng đoán gần nhất nhưng dán nhãn rõ là phỏng đoán và không kèm hướng dẫn.
 */

import * as React from "react";

import { Button, Card, Chip, DegradedBanner } from "@/components/ui/primitives";
import { ScreenHeader } from "@/components/ui/shell";
import { doTinCay, NHAN_TIN_CAY } from "@/lib/format";
import {
  IconCam,
  IconChupAnh,
  IconChuaChac,
  IconDuyet,
  IconHoiBanQuanLy,
  IconHuuIch,
  IconKhungGio,
  IconMonDo,
  IconNhanh,
  IconNhomRac,
  IconSaiRoi,
  IconSoiKy,
  IconTiepTuc,
  IconViTri,
} from "@/lib/icons";
import type { AdviceSource, Classification } from "@/lib/types";

function NguonChips({ sources, onOpen }: { sources: AdviceSource[]; onOpen: (s: AdviceSource) => void }) {
  if (!sources.length) return null;
  return (
    <div className="mt-3.5">
      <div className="mx-0.5 mb-2 text-[13px] font-bold text-muted">Nguồn hướng dẫn</div>
      <div className="flex flex-wrap gap-2">
        {sources.map((s) => (
          <button
            key={s.chunk_id}
            onClick={() => onOpen(s)}
            className="flex cursor-pointer items-center gap-1.5 rounded-xl border-[1.5px] border-line-2 bg-white px-3 py-2 text-xs font-bold text-ink-soft"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2fae66" strokeWidth="2">
              <path d="M6 3h9l4 4v14H6z" />
              <path d="M14 3v5h5" />
            </svg>
            {s.doc_title} · {s.section}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SourceSheet({ source, onClose }: { source: AdviceSource | null; onClose: () => void }) {
  if (!source) return null;
  return (
    <div className="absolute inset-0 z-50 flex items-end bg-black/40" onClick={onClose}>
      <div className="max-h-[70%] w-full overflow-y-auto rounded-t-[28px] bg-white p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-line-2" />
        <div className="text-[11px] font-extrabold uppercase tracking-wide text-muted">{source.doc_type}</div>
        <div className="mt-1 font-[family-name:var(--font-display)] text-lg font-bold">{source.doc_title}</div>
        <div className="mb-3 text-[13px] font-bold text-leaf-dark">{source.section}</div>
        <p className="text-sm font-semibold leading-relaxed text-ink-soft">{source.quote}</p>
        {source.needs_verification && (
          <div className="mt-3 rounded-xl border border-amber-line bg-amber-soft p-3 text-xs font-bold leading-relaxed text-amber">
            Đoạn này là diễn giải rút gọn của văn bản pháp luật. Phải đối chiếu văn bản gốc và hiệu lực hiện hành trước
            khi trích dẫn ra ngoài.
          </div>
        )}
        {source.source && <div className="mt-3 text-[11px] font-semibold text-muted">Nguồn: {source.source}</div>}
        <Button block variant="outline" className="mt-4" onClick={onClose}>
          Đóng
        </Button>
      </div>
    </div>
  );
}

export function ResultScreen({
  ketQua,
  onBack,
  onPrivacy,
  onPickup,
  onFeedback,
}: {
  ketQua: Classification;
  onBack: () => void;
  onPrivacy: () => void;
  onPickup: () => void;
  onFeedback: (isCorrect: boolean) => void;
}) {
  const [nguon, setNguon] = React.useState<AdviceSource | null>(null);
  const [daPhanHoi, setDaPhanHoi] = React.useState<"" | "up" | "down">("");
  const category = ketQua.category!;
  const mucTinCay = NHAN_TIN_CAY[ketQua.confidence_level];
  const lichThuGom = ketQua.schedule_hint?.lich_thu_gom?.[0];

  return (
    <div className="min-h-full bg-cream pb-10 pt-11">
      <ScreenHeader title="Kết quả phân loại" onBack={onBack} />
      <div className="px-4">
        {ketQua.degraded && ketQua.degraded_note && (
          <div className="mb-3">
            <DegradedBanner note={ketQua.degraded_note} />
          </div>
        )}

        <div
          className="animate-gbfade rounded-3xl p-5 text-white shadow-[0_16px_30px_-14px_rgba(47,127,224,.7)]"
          style={{ background: `linear-gradient(155deg, ${category.bin_color}, ${category.bin_color}dd)` }}
        >
          <div className="mb-4 flex items-center gap-2.5">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/20">
              <IconNhomRac code={category.code} className="h-6 w-6" />
            </span>
            <div>
              <div className="text-xs font-bold tracking-wider opacity-85">BỎ VÀO</div>
              <div className="font-[family-name:var(--font-display)] text-[22px] font-bold leading-tight">
                {category.name}
              </div>
            </div>
          </div>
          <div className="mb-3 text-[17px] font-bold">{ketQua.item_name}</div>
          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-leaf-soft px-3 py-1.5 text-xs font-extrabold text-leaf-dark">
              <span className="h-2 w-2 flex-none rounded-full bg-current" />
              {mucTinCay.label} · {doTinCay(ketQua.confidence)}
            </span>
            {ketQua.tier_label_vi && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/25 px-3 py-1.5 text-xs font-bold text-white">
                {ketQua.tier === "t2_full" ? <IconSoiKy className="h-3.5 w-3.5" /> : <IconNhanh className="h-3.5 w-3.5" />}
                {ketQua.tier_label_vi}
              </span>
            )}
          </div>
        </div>

        {category.handling_note && (
          <Card className="mt-3.5 p-4">
            <div className="mb-3 text-[15px] font-bold">Làm nhanh trước khi bỏ</div>
            <div className="flex flex-col gap-2.5">
              {category.handling_note.split("·").map((viec, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <span className="flex h-[22px] w-[22px] flex-none items-center justify-center rounded-lg bg-leaf-soft text-xs font-extrabold text-leaf">
                    {i + 1}
                  </span>
                  <span className="text-sm font-semibold leading-snug">{viec.trim()}</span>
                </div>
              ))}
            </div>
          </Card>
        )}

        {ketQua.advice && (
          <Card className="mt-3 p-4 text-sm font-semibold leading-relaxed text-ink-soft">{ketQua.advice}</Card>
        )}

        {lichThuGom && (
          <Card className="mt-3 p-4">
            <div className="mb-3 flex items-start gap-2.5">
              <span className="flex h-8 w-8 flex-none items-center justify-center rounded-xl bg-recycle-soft text-recycle">
                <IconViTri className="h-4 w-4" />
              </span>
              <span className="text-sm font-semibold leading-snug">
                <b className="font-extrabold">{lichThuGom.location}</b>
              </span>
            </div>
            <div className="flex items-start gap-2.5">
              <span className="flex h-8 w-8 flex-none items-center justify-center rounded-xl bg-leaf-soft text-leaf-dark">
                <IconKhungGio className="h-4 w-4" />
              </span>
              <span className="text-sm font-semibold leading-snug">
                Thu gom: <b className="font-extrabold">{lichThuGom.window}</b>
              </span>
            </div>
          </Card>
        )}

        <NguonChips sources={ketQua.advice_sources} onOpen={setNguon} />

        <div className="mt-4 flex gap-2">
          <Button
            variant="soft"
            className="flex-1"
            disabled={daPhanHoi !== ""}
            onClick={() => {
              setDaPhanHoi("up");
              onFeedback(true);
            }}
          >
            <IconHuuIch className="h-4 w-4" />
            {daPhanHoi === "up" ? "Cảm ơn bạn" : "Hữu ích"}
          </Button>
          <Button
            variant="outline"
            className="flex-1"
            disabled={daPhanHoi !== ""}
            onClick={() => {
              setDaPhanHoi("down");
              onFeedback(false);
            }}
          >
            <IconSaiRoi className="h-4 w-4" />
            {daPhanHoi === "down" ? "Đã chuyển BQL" : "Sai rồi"}
          </Button>
        </div>
        {daPhanHoi === "down" && (
          <p className="mt-2 text-center text-xs font-semibold text-muted">
            Ca này đã vào hàng đợi xác nhận nhãn của ban quản lý.
          </p>
        )}

        <Button block variant="bulky" className="mt-2" onClick={onPickup}>
          <IconMonDo className="h-4 w-4" />
          Món này cồng kềnh — đặt lịch thu gom
          <IconTiepTuc className="h-4 w-4" />
        </Button>
        {ketQua.media_id && (
          <button onClick={onPrivacy} className="mt-3 w-full cursor-pointer text-[13px] font-bold text-[#5a6b5f] underline">
            Ảnh của bạn được xử lý thế nào?
          </button>
        )}
      </div>
      <SourceSheet source={nguon} onClose={() => setNguon(null)} />
    </div>
  );
}

export function HazardResultScreen({
  ketQua,
  onBack,
  onPickup,
}: {
  ketQua: Classification;
  onBack: () => void;
  onPickup: () => void;
}) {
  const category = ketQua.category!;
  const canhBao = ketQua.safety_warning || category.safety_warning;
  const khong = canhBao
    .split(",")
    .filter((c) => c.trim().toUpperCase().startsWith("KHÔNG"))
    .map((c) => c.trim());
  const nen = canhBao
    .split(".")
    .map((c) => c.trim())
    .filter((c) => c && !c.toUpperCase().startsWith("KHÔNG"))
    .join(". ");

  return (
    <div className="min-h-full bg-hazard-bg pb-10 pt-11">
      <ScreenHeader title="Kết quả phân loại" onBack={onBack} tone="hazard" />
      <div className="px-4">
        <div className="animate-gbfade rounded-[22px] border-[3px] border-hazard bg-white p-5 shadow-[0_0_0_5px_rgba(224,90,43,.12)]">
          <div className="mb-3.5 flex items-center gap-3">
            <span className="flex h-[46px] w-[46px] flex-none items-center justify-center rounded-2xl bg-hazard">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 3L2 20h20z" />
                <path d="M12 10v4M12 17v.5" />
              </svg>
            </span>
            <div>
              <div className="text-xs font-extrabold tracking-wider text-hazard-dark">RÁC NGUY HẠI — KHÔNG BỎ CHUNG</div>
              <div className="font-[family-name:var(--font-display)] text-xl font-bold">{ketQua.item_name}</div>
            </div>
          </div>

          {khong.length > 0 && (
            <div className="mb-3 rounded-2xl bg-hazard-bg p-3.5">
              <div className="mb-2 flex items-center gap-1.5 text-[13px] font-extrabold text-hazard-dark">
                <IconCam className="h-4 w-4" />
                Tuyệt đối KHÔNG
              </div>
              <div className="text-sm font-bold leading-relaxed text-[#7a3418]">
                {khong.map((c, i) => (
                  <div key={i}>• {c}</div>
                ))}
              </div>
            </div>
          )}

          {nen && (
            <div className="rounded-2xl bg-leaf-soft p-3.5">
              <div className="mb-1.5 flex items-center gap-1.5 text-[13px] font-extrabold text-leaf-dark">
                <IconDuyet className="h-4 w-4" />
                Nên làm
              </div>
              <div className="text-sm font-bold leading-relaxed text-[#2a5a3a]">{nen}</div>
            </div>
          )}

          <div className="mt-3 flex items-center gap-2 rounded-xl bg-[#f7f2ea] px-2.5 py-2">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8a7a5a" strokeWidth="2">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 8v5M12 16v.5" strokeLinecap="round" />
            </svg>
            <span className="text-[11px] font-bold text-[#8a7a5a]">
              {ketQua.safety_warning_note || "Cảnh báo an toàn theo danh mục chuẩn — không do AI tự viết."}
            </span>
          </div>
        </div>

        <Button block size="lg" className="mt-3.5" onClick={onPickup}>
          Đăng ký đội vệ sinh tới nhận
          <IconTiepTuc className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export function UnsureScreen({
  ketQua,
  onBack,
  onRetake,
  onAskManager,
}: {
  ketQua: Classification;
  onBack: () => void;
  onRetake: () => void;
  onAskManager: () => void;
}) {
  const [daHoi, setDaHoi] = React.useState(false);
  const chanCung = ketQua.hard_block;

  return (
    <div className="min-h-full bg-[linear-gradient(180deg,#e6edf5,#eef1f5)] pb-10 pt-11">
      <ScreenHeader title="" onBack={onBack} />
      <div className="px-[22px]">
        <div className="mb-4 flex h-[66px] w-[66px] items-center justify-center rounded-[22px] bg-[#dbe6f2] text-[#4a5568]">
          <IconChuaChac className="h-8 w-8" strokeWidth={1.8} />
        </div>
        <h1 className="m-0 mb-3 font-[family-name:var(--font-display)] text-[27px] font-bold leading-tight text-[#243244]">
          {ketQua.refusal_headline_vi || "Mình chưa đủ chắc để hướng dẫn món này"}
        </h1>

        <p className="m-0 mb-4 text-[15px] font-semibold leading-relaxed text-[#4a5568]">
          {chanCung ? (
            <>
              Món này thuộc nhóm <b>{chanCung.label_vi}</b>. {chanCung.instruction_vi}
            </>
          ) : ketQua.guess?.item_name ? (
            <>
              Đoán gần nhất: <b>có thể là {ketQua.guess.item_name}</b> — nhưng nhóm này nếu hướng dẫn sai thì nguy hiểm,
              nên mình không đoán bừa.
            </>
          ) : (
            "Mình chưa nhận ra món này thuộc nhóm nào nên không hướng dẫn."
          )}
        </p>

        <Card className="mb-5 p-4">
          <div className="mb-2 text-[13px] font-bold text-[#64748b]">Vì sao chưa chắc</div>
          <div className="flex flex-wrap gap-1.5">
            <Chip tone={ketQua.refusal_reason.includes("nguy_hai") || chanCung ? "hazard" : "neutral"} className="text-xs">
              {ketQua.refusal_label_vi}
            </Chip>
            {ketQua.confidence > 0 && (
              <Chip className="text-xs">
                Độ chắc {doTinCay(ketQua.confidence)} · ngưỡng nhóm {doTinCay(ketQua.min_confidence)}
              </Chip>
            )}
          </div>
        </Card>

        <Button block size="lg" className="mb-2.5 bg-[#243244]" onClick={onRetake}>
          <IconChupAnh className="h-4 w-4" />
          Chụp lại rõ hơn
        </Button>
        <Button
          block
          size="lg"
          variant="outline"
          className="mb-2.5 border-[#cbd5e1]"
          disabled={daHoi}
          onClick={() => {
            setDaHoi(true);
            onAskManager();
          }}
        >
          <IconHoiBanQuanLy className="h-4 w-4" />
          {daHoi ? "Đã gửi cho ban quản lý" : "Hỏi ban quản lý"}
        </Button>
        <p className="m-0 mt-2 text-center text-xs font-semibold text-[#7a8798]">
          Thường được trả lời trong vòng 2 giờ làm việc.
        </p>
      </div>
    </div>
  );
}
