"use client";

/** Màn Trang chủ (Hỏi phân loại) + màn đang xử lý.
 *
 * Màn xử lý là **màn ăn điểm về minh bạch AI**: nó cho người xem thấy quyền
 * riêng tư được xử lý *trước khi* ảnh rời máy, chứ không phải một lời hứa suông.
 * Các bước tích dần theo tiến trình thật của request, và khi có kết quả thì
 * số liệu hiển thị lấy từ báo cáo quyền riêng tư thật của ảnh đó.
 */

import * as React from "react";
import NumberFlow from "@number-flow/react";

import { Mascot } from "@/components/resident/onboarding";
import { Button } from "@/components/ui/primitives";
import { tinhCap, tinhStreak, homNay } from "@/lib/gamification";
import { IconChonAnh, IconDuyet, IconMoTaChu, IconChuong, IconMamXanh, IconXeThuGom } from "@/lib/icons";
import { Flame } from "lucide-react";
import { chonAnh, chupAnh } from "@/lib/platform";
import { useSession } from "@/lib/session";
import type { Classification } from "@/lib/types";
import { cn } from "@/lib/utils";

const GOI_Y_NHANH = [
  { label: "Hộp sữa giấy", query: "hộp sữa giấy tráng nhôm", tone: "" },
  { label: "Ly trà sữa", query: "ly nhựa trà sữa có màng dán miệng", tone: "" },
  { label: "Pin cũ", query: "pin tiểu AA đã dùng hết", tone: "hazard" },
  { label: "Hộp xốp", query: "hộp xốp đựng cơm đã dùng", tone: "" },
  { label: "Chai hoá chất", query: "chai nước tẩy bồn cầu còn nửa", tone: "unsure" },
];

/** Lời chào theo giờ — "Chào buổi sáng/chiều/tối". */
function loiChao(): string {
  const gio = new Date().getHours();
  if (gio < 11) return "Chào buổi sáng,";
  if (gio < 18) return "Chào buổi chiều,";
  return "Chào buổi tối,";
}

/** Ngày thứ trong tuần tiếng Việt ngắn — dùng cho thẻ lịch gom. */
function tenThu(): string {
  const THU = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"];
  return THU[new Date().getDay()];
}

export function AskScreen({
  unit,
  lanChup = 0,
  onXemLich,
  onDatLich,
  onAskText,
  onPickImage,
}: {
  unit: string;
  /** Nút Chụp nổi ở tab bar tăng con số này → mở camera ngay khi mount/đổi. */
  lanChup?: number;
  onXemLich: () => void;
  /** Tuỳ chọn: lối vào đặt lịch thu gom đồ cồng kềnh. Nếu không truyền, khung không hiện. */
  onDatLich?: () => void;
  onAskText: (query: string) => void;
  onPickImage: (file: File) => void;
}) {
  const { user } = useSession();
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

  // Nút Chụp nổi giữa (tab bar) tăng `lanChup` → tự mở camera. Chỉ chạy khi
  // người dùng chủ động bấm nút Chụp, không tự mở khi màn vừa dựng (lanChup = 0).
  const lanChupRef = React.useRef(0);
  React.useEffect(() => {
    if (lanChup > 0 && lanChup !== lanChupRef.current) {
      lanChupRef.current = lanChup;
      void layAnh("camera");
    }
  }, [lanChup]); // eslint-disable-line react-hooks/exhaustive-deps

  // Điểm và cấp độ tính từ số thật `green_points`; streak từ hoạt động thật.
  const diem = user?.green_points ?? 0;
  const cap = tinhCap(diem);
  const [streak, setStreak] = React.useState(0);
  const [greeting, setGreeting] = React.useState("Chào bạn,");
  const [scheduleText, setScheduleText] = React.useState("");

  React.useEffect(() => {
    setStreak(tinhStreak());
    setGreeting(loiChao());
    setScheduleText(`${tenThu()}, ${homNay()}`);
  }, []);

  return (
    <div className="relative flex min-h-full flex-col overflow-hidden bg-cream px-5 pb-[120px] pt-[54px] lg:mx-auto lg:max-w-[960px]">
      {/* ── Background Banner Hoạt Cảnh Mới (Thay thế hoàn toàn background cũ được khoanh đỏ) ── */}
      <div className="pointer-events-none absolute inset-x-0 -top-8 h-[325px] z-0 overflow-hidden">
        <img
          src="/Background.svg"
          alt="GreenBin City Background"
          className="w-full h-full object-cover object-bottom select-none"
        />
        {/* Lớp chuyển sắc mềm mượt ở đáy nối vào nền kem bên dưới */}
        <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-cream via-cream/70 to-transparent pointer-events-none" />
      </div>

      {/* ── header: lời chào + chuông ── */}
      <div className="relative z-10 flex items-center justify-between">
        <div className="min-w-0">
          <div className="text-xs font-bold text-ink-soft">{greeting}</div>
          <div className="mt-0.5 truncate font-[family-name:var(--font-display)] text-[26px] font-extrabold leading-none tracking-tight text-ink">
            {user?.full_name?.split(" ").pop() ?? "Bạn"} <IconMamXanh className="ml-0.5 inline h-6 w-6 text-leaf" strokeWidth={1.9} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-surface px-3 py-1.5 text-[13px] font-bold text-ink-soft shadow-[0_2px_8px_rgba(20,40,25,.06)]">
            {unit || "Chưa gắn căn hộ"}
          </span>
          <button
            type="button"
            aria-label="Thông báo"
            className="relative flex h-11 w-11 items-center justify-center rounded-full border border-line bg-surface shadow-[0_2px_8px_rgba(20,40,25,.06)]"
          >
            <IconChuong className="h-5 w-5 text-ink" />
            <span className="absolute right-2.5 top-2.5 h-2 w-2 rounded-full bg-hazard ring-2 ring-white" />
          </button>
        </div>
      </div>

      {/* ── hero: scan chính ── */}
      <div className="relative z-10 mt-[210px]">
        <h1 className="mb-4 max-w-[240px] font-[family-name:var(--font-display)] text-[30px] font-bold leading-[1.04] tracking-tight text-ink">
          Không biết bỏ
          <br />
          vào thùng nào?
        </h1>
        <Button block size="lg" className="rounded-2xl p-0 py-6 text-left" onClick={() => void layAnh("camera")}>
          <span className="flex w-full items-center gap-4 px-6">
            <span className="flex h-[54px] w-[54px] flex-none items-center justify-center rounded-lg bg-surface/20">
              <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z" />
                <circle cx="12" cy="13" r="3.5" />
              </svg>
            </span>
            <span>
              <span className="block font-[family-name:var(--font-display)] text-[20px] font-bold leading-none">Chụp món rác</span>
              <span className="mt-1.5 block text-[13px] font-semibold opacity-85">Bini nhận ra ngay trong 3 giây</span>
            </span>
          </span>
        </Button>
        <div className="mt-3 flex gap-2.5">
          <Button variant="outline" className="flex-1 rounded-2xl border-line bg-surface" onClick={() => void layAnh("thu-vien")}>
            <IconChonAnh className="h-4 w-4" />
            Chọn ảnh
          </Button>
          <Button variant="outline" className="flex-1 rounded-2xl border-line bg-surface" onClick={() => setDangGoMoTa((v) => !v)}>
            <IconMoTaChu className="h-4 w-4" />
            Mô tả chữ
          </Button>
        </div>
      </div>

      {dangGoMoTa && (
        <form
          className="relative z-10 mt-3 flex gap-2"
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
            className="flex-1 rounded-2xl border-[1.5px] border-line-2 bg-surface px-4 py-3 text-sm font-semibold outline-none focus:border-leaf"
          />
          <Button type="submit" variant="leaf" disabled={!moTa.trim()} aria-label="Gửi câu hỏi phân loại">
            Hỏi
          </Button>
        </form>
      )}

      {loiAnh && (
        <div className="relative z-10 mt-3 rounded-2xl border-[1.5px] border-hazard-light bg-hazard-soft px-4 py-3 text-[13px] font-bold text-hazard-dark">
          {loiAnh}
        </div>
      )}

      {/* ── thẻ tiến độ hôm nay (điểm + streak + cấp) ── */}
      <div className="relative z-10 mt-5 rounded-2xl border border-line bg-surface p-4 shadow-[0_2px_10px_rgba(20,40,25,.05)]">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-[15px] font-bold">Hôm nay của bạn</span>
          <span className="text-[13px] font-bold text-leaf-dark">Điểm xanh</span>
        </div>
        <div className="flex gap-2.5">
          <div className="flex-1 rounded-2xl bg-leaf-soft px-3 py-3">
            <div className="font-[family-name:var(--font-display)] text-2xl font-bold leading-none text-leaf-dark tabular-nums">
              <NumberFlow value={diem} locales="vi-VN" />
            </div>
            <div className="mt-1 flex items-center gap-1 text-[11px] font-bold text-ink-soft"><IconMamXanh className="h-3.5 w-3.5" strokeWidth={2} /> Điểm xanh</div>
          </div>
          <div className="flex-1 rounded-2xl bg-amber-soft px-3 py-3">
            <div className="font-[family-name:var(--font-display)] text-2xl font-bold leading-none text-amber tabular-nums">
              {streak}
            </div>
            <div className="mt-1 flex items-center gap-1 text-[11px] font-bold text-ink-soft"><Flame className="h-3.5 w-3.5" strokeWidth={2} /> Ngày liên tiếp</div>
          </div>
        </div>
        <div className="mt-3">
          <div className="mb-1.5 flex justify-between text-[11px] font-bold text-ink-soft">
            <span>
              Cấp {cap.ten} {cap.icon}
            </span>
            <span>
              {cap.conThieu > 0 ? `còn ${cap.conThieu} điểm để lên cấp kế tiếp` : "đã đạt cấp cao nhất"}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-leaf-soft">
            <div className="animate-gbfill h-full rounded-full bg-gradient-to-r from-leaf to-leaf-mint" style={{ width: `${cap.phanTram}%` }} />
          </div>
        </div>
      </div>

      {/* ── thẻ lịch thu gom kế tiếp → vào màn Lịch đầy đủ ── */}
      <button
        type="button"
        onClick={onXemLich}
        className="relative z-10 mt-3.5 flex items-center gap-3 rounded-2xl bg-recycle-soft border border-recycle/20 px-4 py-3.5 text-left shadow-[var(--shadow-xs)] transition-all duration-200 ease-[var(--ease-spring)] hover:shadow-[var(--shadow-sm)] hover:-translate-y-0.5 active:scale-[0.98] cursor-pointer group"
      >
        <span className="flex h-11 w-11 flex-none items-center justify-center rounded-lg bg-surface shadow-xs">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#2f7fe0" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="3" />
            <path d="M3 10h18M8 2v4M16 2v4" />
          </svg>
        </span>
        <span className="flex-1">
          <span className="block text-sm font-bold text-ink">Lịch thu gom của toà</span>
          <span className="mt-0.5 block text-xs font-semibold text-ink-soft">
            {scheduleText || "Hôm nay"} · xem cả khi không có mạng
          </span>
        </span>
        <span className="text-xl font-bold text-recycle transition-transform group-hover:translate-x-1">›</span>
      </button>

      {/* ── thẻ đặt lịch thu gom đồ cồng kềnh (tông bulky, cặp với thẻ lịch) ── */}
      {onDatLich && (
        <button
          type="button"
          onClick={onDatLich}
          className="relative z-10 mt-3.5 flex items-center gap-3 rounded-2xl bg-bulky-soft border border-bulky/20 px-4 py-3.5 text-left shadow-[var(--shadow-xs)] transition-all duration-200 ease-[var(--ease-spring)] hover:shadow-[var(--shadow-sm)] hover:-translate-y-0.5 active:scale-[0.98] cursor-pointer group"
        >
          <span className="flex h-11 w-11 flex-none items-center justify-center rounded-lg bg-surface shadow-xs">
            <IconXeThuGom className="h-[22px] w-[22px] text-bulky-dark" />
          </span>
          <span className="flex-1">
            <span className="block text-sm font-bold text-ink">Đặt lịch thu gom đồ cồng kềnh</span>
            <span className="mt-0.5 block text-xs font-semibold text-ink-soft">
              Sofa, nệm, tủ cũ · đội thu gom tới tận nơi
            </span>
          </span>
          <span className="text-xl font-bold text-bulky transition-transform group-hover:translate-x-1">›</span>
        </button>
      )}

      {/* ── hỏi nhanh không cần chụp ── */}
      <div className="relative z-10 mt-5">
        <div className="mb-2.5 text-xs font-extrabold uppercase tracking-wider text-muted">Hỏi nhanh</div>
        <div className="flex flex-wrap gap-2">
          {GOI_Y_NHANH.map((g) => (
            <button
              key={g.label}
              onClick={() => onAskText(g.query)}
              className={cn(
                "cursor-pointer rounded-full px-4 py-2 text-xs font-bold shadow-[var(--shadow-xs)] transition-all duration-200 ease-[var(--ease-spring)] hover:scale-105 active:scale-95",
                g.tone === "hazard"
                  ? "border border-hazard/30 bg-hazard-soft text-hazard-dark hover:border-hazard"
                  : g.tone === "unsure"
                    ? "border border-line-2 bg-chip-bg text-ink-muted hover:border-muted"
                    : "border border-line-2 bg-surface text-ink hover:border-leaf hover:bg-leaf-soft/40"
              )}
            >
              {g.label}
            </button>
          ))}
        </div>
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
    <div className="flex min-h-full flex-col bg-[linear-gradient(180deg,var(--color-ink-dark),var(--color-nen-camera))] px-[26px] pb-8 pt-16 text-white">
      <div className="mb-2 text-[13px] font-bold uppercase tracking-wide text-leaf-mint">Đang xem giúp bạn…</div>
      <h1 className="m-0 mb-1.5 font-[family-name:var(--font-display)] text-[28px] font-bold leading-tight">
        Mình xử lý ảnh
        <br />
        ngay trên máy chủ trước
      </h1>
      <p className="m-0 mb-6 text-[13px] font-semibold text-bulky-muted">Quyền riêng tư được lo trước khi ảnh tới model.</p>

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
              <span className="flex-1 text-[15px] font-bold" style={{ color: xong || dangChay ? "var(--color-surface)" : "var(--color-on-dark-faint)" }}>
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
        className="w-full cursor-pointer rounded-full border border-white/20 bg-surface/10 py-4 text-[15px] font-bold text-white"
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
