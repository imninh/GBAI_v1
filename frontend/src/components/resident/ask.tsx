"use client";

/** Màn hỏi phân loại + màn đang xử lý.
 *
 * Màn xử lý là **màn ăn điểm về minh bạch AI**: nó cho người xem thấy quyền
 * riêng tư được xử lý *trước khi* ảnh rời máy, chứ không phải một lời hứa suông.
 * Các bước tích dần theo tiến trình thật của request, và khi có kết quả thì
 * số liệu hiển thị lấy từ báo cáo quyền riêng tư thật của ảnh đó.
 */

import * as React from "react";

import { Mascot } from "@/components/resident/onboarding";
import { Button } from "@/components/ui/primitives";
import { IconChonAnh, IconDuyet, IconMoTaChu } from "@/lib/icons";
import { chonAnh, chupAnh } from "@/lib/platform";
import type { Classification } from "@/lib/types";

const GOI_Y_NHANH = [
  { label: "Hộp sữa giấy", query: "hộp sữa giấy tráng nhôm", tone: "" },
  { label: "Ly trà sữa", query: "ly nhựa trà sữa có màng dán miệng", tone: "" },
  { label: "Pin cũ", query: "pin tiểu AA đã dùng hết", tone: "hazard" },
  { label: "Hộp xốp", query: "hộp xốp đựng cơm đã dùng", tone: "" },
  { label: "Chai hoá chất", query: "chai nước tẩy bồn cầu còn nửa", tone: "unsure" },
];

export function AskScreen({
  unit,
  onAskText,
  onPickImage,
}: {
  unit: string;
  onAskText: (query: string) => void;
  onPickImage: (file: File) => void;
}) {
  const [moTa, setMoTa] = React.useState("");
  const [dangGoMoTa, setDangGoMoTa] = React.useState(false);
  const [loiAnh, setLoiAnh] = React.useState("");

  async function layAnh(nguon: "camera" | "thu-vien") {
    setLoiAnh("");
    try {
      const file = nguon === "camera" ? await chupAnh() : await chonAnh();
      if (file) onPickImage(file);
    } catch {
      // Hay gặp nhất là người dùng từ chối quyền camera trong app cài về.
      setLoiAnh("Không mở được camera. Kiểm tra quyền truy cập camera của app, hoặc chọn ảnh có sẵn nhé.");
    }
  }

  return (
    <div className="flex min-h-full flex-col bg-[linear-gradient(180deg,#eaf6ee_0%,#f2f4ec_40%)] px-5 pb-[108px] pt-[54px]">
      <div className="mb-0.5 flex items-center justify-between">
        <div className="whitespace-nowrap font-[family-name:var(--font-display)] text-[22px] font-bold tracking-tight">
          GreenBin<span className="text-leaf"> AI</span>
        </div>
        <div className="flex items-center gap-2 rounded-full bg-white py-1.5 pl-1.5 pr-3 shadow-[0_2px_8px_rgba(20,40,25,.06)]">
          <span className="flex h-[26px] w-[26px] items-center justify-center rounded-full bg-leaf-soft">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2fae66" strokeWidth="2.4">
              <path d="M3 21V9l9-6 9 6v12" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="text-[13px] font-bold">{unit || "Chưa gắn căn hộ"}</span>
        </div>
      </div>

      <div className="relative mt-3.5 flex flex-col items-center">
        <div className="absolute top-0.5 z-10 rounded-[20px_20px_20px_6px] bg-white px-4 py-2.5 font-[family-name:var(--font-display)] text-[15px] font-bold shadow-[0_6px_18px_-6px_rgba(20,40,25,.2)]">
          Đưa mình xem món rác nhé!
        </div>
        <div className="mt-9 flex h-[190px] w-[250px] items-end justify-center bg-[radial-gradient(circle_at_50%_60%,#d8f0e0_0%,rgba(216,240,224,0)_68%)]">
          <Mascot size={180} tuThe="hello" className="animate-gbfloat drop-shadow-[0_16px_20px_rgba(30,80,50,.22)]" />
        </div>
      </div>

      {loiAnh && (
        <div className="mt-2 rounded-2xl border-[1.5px] border-[#f6cdb8] bg-hazard-soft px-4 py-3 text-[13px] font-bold text-hazard-dark">
          {loiAnh}
        </div>
      )}

      <Button block size="lg" className="mt-1.5 rounded-[20px] text-lg" onClick={() => layAnh("camera")}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 8a2 2 0 0 1 2-2h1l1.2-2h5.6L16 6h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z" transform="translate(1 0)" />
          <circle cx="12" cy="13" r="3.4" />
        </svg>
        Chụp món rác
      </Button>

      <div className="mt-2.5 flex gap-2.5">
        <Button variant="outline" className="flex-1 rounded-2xl border-leaf-soft" onClick={() => layAnh("thu-vien")}>
          <IconChonAnh className="h-4 w-4" />
          Chọn ảnh
        </Button>
        <Button variant="outline" className="flex-1 rounded-2xl border-leaf-soft" onClick={() => setDangGoMoTa((v) => !v)}>
          <IconMoTaChu className="h-4 w-4" />
          Mô tả chữ
        </Button>
      </div>

      {dangGoMoTa && (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (moTa.trim()) onAskText(moTa.trim());
          }}
        >
          <input
            autoFocus
            value={moTa}
            onChange={(e) => setMoTa(e.target.value)}
            placeholder="VD: hộp sữa giấy có lớp bạc bên trong"
            className="flex-1 rounded-2xl border-[1.5px] border-line-2 bg-white px-4 py-3 text-sm font-semibold outline-none focus:border-leaf"
          />
          <Button type="submit" variant="leaf" disabled={!moTa.trim()}>
            Hỏi
          </Button>
        </form>
      )}

      <div className="mx-0.5 mb-2.5 mt-6 text-[13px] font-bold text-muted">Hỏi nhanh không cần chụp</div>
      <div className="flex flex-wrap gap-2">
        {GOI_Y_NHANH.map((g) => (
          <button
            key={g.label}
            onClick={() => onAskText(g.query)}
            className={
              g.tone === "hazard"
                ? "cursor-pointer rounded-full border-[1.5px] border-[#f6cdb8] bg-hazard-soft px-4 py-2.5 text-[13px] font-bold text-hazard-dark"
                : g.tone === "unsure"
                  ? "cursor-pointer rounded-full border-[1.5px] border-[#d9e0ec] bg-[#eef1f6] px-4 py-2.5 text-[13px] font-bold text-[#4a5568]"
                  : "cursor-pointer rounded-full border-[1.5px] border-leaf-soft bg-white px-4 py-2.5 text-[13px] font-bold text-ink"
            }
          >
            {g.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export interface ProcessingStep {
  label: string;
  detail: string;
}

export function ProcessingScreen({
  buoc,
  cacBuoc,
  onCancel,
}: {
  buoc: number;
  cacBuoc: ProcessingStep[];
  onCancel: () => void;
}) {
  return (
    <div className="flex min-h-full flex-col bg-[linear-gradient(180deg,#0c0f0c,#12211a)] px-[26px] pb-8 pt-16 text-white">
      <div className="mb-2 text-[13px] font-bold uppercase tracking-wide text-leaf-mint">Đang xem giúp bạn…</div>
      <h1 className="m-0 mb-1.5 font-[family-name:var(--font-display)] text-[28px] font-bold leading-tight">
        Mình xử lý ảnh
        <br />
        ngay trên máy chủ trước
      </h1>
      <p className="m-0 mb-6 text-[13px] font-semibold text-[#9fb3a6]">Quyền riêng tư được lo trước khi ảnh tới model.</p>

      <div className="mb-6 flex h-[190px] items-center justify-center self-center bg-[radial-gradient(circle_at_50%_55%,rgba(127,215,164,.22)_0%,rgba(127,215,164,0)_68%)]">
        <Mascot size={175} tuThe="magnify" className="animate-gbfloat drop-shadow-[0_12px_18px_rgba(0,0,0,.35)]" />
      </div>

      <div className="flex flex-col gap-4">
        {cacBuoc.map((step, index) => {
          const xong = index < buoc;
          const dangChay = index === buoc;
          return (
            <div key={step.label} className="flex items-center gap-3.5" style={{ opacity: xong || dangChay ? 1 : 0.35 }}>
              <span className="flex h-[26px] w-[26px] flex-none items-center justify-center">
                {xong ? (
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-leaf text-white">
                    <IconDuyet className="h-3.5 w-3.5" strokeWidth={3} />
                  </span>
                ) : dangChay ? (
                  <span className="animate-gbspin h-[22px] w-[22px] rounded-full border-[2.5px] border-[rgba(127,215,164,.3)] border-t-leaf-mint" />
                ) : (
                  <span className="h-5 w-5 rounded-full border-2 border-white/20" />
                )}
              </span>
              <span className="flex-1 text-[15px] font-bold" style={{ color: xong || dangChay ? "#fff" : "#9fb3a6" }}>
                {step.label}
              </span>
              {xong && <span className="text-xs font-semibold text-leaf-mint">{step.detail}</span>}
            </div>
          );
        })}
      </div>

      <div className="flex-1" />
      <button
        onClick={onCancel}
        className="w-full cursor-pointer rounded-full border border-white/20 bg-white/10 py-4 text-[15px] font-bold text-white"
      >
        Huỷ
      </button>
    </div>
  );
}

/** Các bước mặc định, dùng khi chưa có báo cáo quyền riêng tư thật của ảnh. */
export const BUOC_MAC_DINH: ProcessingStep[] = [
  { label: "Đang nén ảnh…", detail: "xong" },
  { label: "Xoá thông tin vị trí…", detail: "đã xoá EXIF" },
  { label: "Làm mờ khuôn mặt…", detail: "xong" },
  { label: "Nhận diện món rác…", detail: "xong" },
  { label: "Tra quy định của toà…", detail: "xong" },
];

/** Dựng lại các bước từ kết quả thật để phần "detail" là số đo, không phải chữ chung chung. */
export function buocTuKetQua(ketQua: Classification, privacy?: { removed_fields: unknown[]; faces_blurred: number; original_size: { bytes: number }; processed_size: { bytes: number } }): ProcessingStep[] {
  const nen = privacy
    ? `${Math.round(privacy.original_size.bytes / 1024)} KB → ${Math.round(privacy.processed_size.bytes / 1024)} KB`
    : "xong";
  return [
    { label: "Đang nén ảnh…", detail: nen },
    { label: "Xoá thông tin vị trí…", detail: privacy ? `đã xoá ${privacy.removed_fields.length} trường` : "đã xoá EXIF" },
    { label: "Làm mờ khuôn mặt…", detail: privacy ? `đã mờ ${privacy.faces_blurred} khuôn mặt` : "xong" },
    { label: "Nhận diện món rác…", detail: ketQua.tier_label_vi || "xong" },
    { label: "Tra quy định của toà…", detail: `${ketQua.advice_sources.length} nguồn` },
  ];
}
