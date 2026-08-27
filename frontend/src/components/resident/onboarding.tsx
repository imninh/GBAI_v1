"use client";

/** Onboarding + đăng nhập.
 *
 * Linh vật "Bini" là ba file PNG ở `assets/`, được `scripts/build_assets.py` cắt
 * và xuất thành WebP ba bề rộng trong `public/mascot/`. Bản SVG vẽ tay vẫn giữ
 * nguyên làm ảnh dự phòng: nếu file ảnh lỗi hoặc chưa build thì giao diện vẫn
 * có linh vật thay vì một ô trống.
 */

import * as React from "react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/primitives";
import { HoaTiet } from "@/components/ui/pattern";
import { api, ApiError } from "@/lib/api";
import { IconChao, IconChupAnh, IconMamXanh, IconManHinhRong, IconTiepTuc, IconXeThuGom } from "@/lib/icons";
import { useSession } from "@/lib/session";

/** Tư thế Bini — 6 pose SVG (NHAN_DIEN §6). Hai tên cũ giữ cho tương thích. */
export type TuTheMascot =
  | "mascot"
  | "hello"
  | "magnify"
  | "om-tim"
  | "nup-la"
  | "nham-mat-cuoi"
  | "may-anh";

/** Map tư thế → file SVG. `mascot`/`hello` chung pose trung tính. */
const FILE_TU_THE: Record<TuTheMascot, string> = {
  mascot: "binh-thuong.svg",
  hello: "binh-thuong.svg",
  magnify: "kinh-lup.svg",
  "om-tim": "om-tim.svg",
  "nup-la": "nup-la.svg",
  "nham-mat-cuoi": "nham-mat-cuoi.svg",
  "may-anh": "may-anh.svg",
};

const MO_TA_TU_THE: Record<TuTheMascot, string> = {
  mascot: "Bini — linh vật GreenBin",
  hello: "Bini hạt mầm, tư thế thường",
  magnify: "Bini đang soi món rác bằng kính lúp",
  "om-tim": "Bini ôm trái tim, vui mừng",
  "nup-la": "Bini nấp sau lá — trạng thái trống",
  "nham-mat-cuoi": "Bini nhắm mắt cười",
  "may-anh": "Bini cầm máy ảnh",
};

/** Ảnh dự phòng khi file SVG không tải được. */
function MascotSVG({ size, className }: { size: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 114 159" className={className} aria-label={MO_TA_TU_THE.mascot}>
      <circle cx="57" cy="80" r="45" fill="#1E3045" />
      <ellipse cx="57" cy="85" rx="30" ry="26" fill="#F6F2DD" />
      <circle cx="45" cy="76" r="6" fill="#1C2C46" />
      <circle cx="69" cy="76" r="6" fill="#1C2C46" />
    </svg>
  );
}

// Nội dung SVG tách lớp (`binh-thuong-layered.svg`) — fetch một lần rồi giữ trong
// bộ nhớ. Các mã màu nằm TRONG file SVG (public), không phải trong .tsx, nên không
// vi phạm test chặn hex.
let biniLayeredCache: string | null = null;
async function layBiniLayered(): Promise<string> {
  if (!biniLayeredCache) {
    const res = await fetch("/mascot/binh-thuong-layered.svg");
    biniLayeredCache = await res.text();
  }
  return biniLayeredCache;
}

export function Mascot({
  size = 120,
  tuThe = "mascot",
  className,
}: {
  size?: number;
  tuThe?: TuTheMascot;
  className?: string;
}) {
  const [loi, setLoi] = React.useState(false);
  const [noiDungBini, setNoiDungBini] = React.useState<string | null>(null);

  // Pose trung tính + cỡ lớn ⇒ inline SVG tách lớp để CSS chạm được mắt (`bini-mat`)
  // và mầm (`bini-mam`) — chớp mắt + nhú mầm. Pose khác / Bini nhỏ giữ `<img>`.
  const inlineLon = tuThe === "hello" && size >= 120;
  React.useEffect(() => {
    if (!inlineLon) return;
    let song = true;
    layBiniLayered()
      .then((s) => { if (song) setNoiDungBini(s); })
      .catch(() => { /* rơi êm về <img> */ });
    return () => { song = false; };
  }, [inlineLon]);

  // Mascot có "hồn" (WOW-B): className của caller nằm trên wrapper NGOÀI CÙNG
  // (đúng gốc render trước WOW-B → -mt-16/mb-2/mx-auto giữ nguyên vị trí). Mỗi
  // animation ở một element riêng để không xung đột `animation`:
  //   ngoài  = className caller (định vị + có thể có animate-*)
  //   giữa   = .gbmascot (entrance một nhịp + wiggle khi hover/chạm)
  //   trong  = .gbidle (thở/lắc nhẹ mọi pose), bỏ khi caller đã có animate-*
  // Idle ở wrapper trong nên KHÔNG phá transform-box của .bini-mat/.bini-mam.
  const coAnimation = className?.includes("animate-");
  const inner =
    loi ? (
      <MascotSVG size={size} />
    ) : inlineLon && noiDungBini ? (
      // SVG inline qua class `bini-inline` (globals.css). Chỉ chứa nội dung file
      // SVG đã verify, không có input người dùng. KHÔNG mang className caller.
      <div
        className="bini-inline"
        style={{ width: size, height: Math.round((size * 159) / 114) }}
        aria-label={MO_TA_TU_THE[tuThe]}
        dangerouslySetInnerHTML={{ __html: noiDungBini }}
      />
    ) : (
      // SVG Bini hạt mầm — asset phẳng (không tách lớp `<g>`), animation áp lên
      // CẢ con (transform/opacity, xem globals.css). KHÔNG mang className caller.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={`/mascot/${FILE_TU_THE[tuThe]}`}
        width={size}
        height={size}
        alt={MO_TA_TU_THE[tuThe]}
        className="object-contain"
        onError={() => setLoi(true)}
      />
    );

  return (
    // `inline-block` để wrapper ngoài nhận margin dọc (-mt-16/mb-2) y như gốc <img>.
    <span className={`inline-block ${className ?? ""}`}>
      <span className="gbmascot">
        <span className={`inline-block ${coAnimation ? "" : "gbidle"}`}>{inner}</span>
      </span>
    </span>
  );
}

/** Màn chào MỘT slide — Bini hero + thương hiệu + 3 điểm value + CTA vào thẳng
 *  đăng nhập. Animation stagger một lượt khi mở (transform/opacity, reduced-motion).
 *  Không phải form, không xin quyền — chỉ dẫn người dùng tới màn đăng nhập.
 */
export function OnboardingScreen({ onNext }: { onNext: () => void }) {
  // Ba điểm value gọn — trên CÙNG màn chào, không tách slide.
  const GIA_TRI: { icon: LucideIcon; text: string }[] = [
    { icon: IconChupAnh, text: "Chụp → biết bỏ đâu" },
    { icon: IconMamXanh, text: "Điểm xanh đổi quà" },
    { icon: IconXeThuGom, text: "Thu gom theo lịch" },
  ];
  // Stagger mỗi khối hiện so le một lần khi mở (transform+opacity, có
  // prefers-reduced-motion ở globals.css).
  const delay = (ms: number) => ({ animationDelay: `${ms}ms` });

  return (
    <div className="relative flex min-h-full flex-col items-center overflow-hidden px-6 pb-8 pt-[48px] text-center"
      style={{ background: "linear-gradient(180deg,var(--color-leaf-soft),var(--color-cream))" }}
    >
      {/* bong bóng nền */}
      <div className="absolute top-[12%] left-1/2 h-[300px] w-[300px] -translate-x-1/2 rounded-full"
        style={{ background: "var(--color-blob-leaf)", filter: "blur(2px)" }} />

      {/* growth-rings phía sau Bini — rất nhạt, chỉ trang trí, không che chữ */}
      <HoaTiet loai="rings" className="inset-0 h-full w-full" />

      {/* Bini hero — hiện lên có sức nặng rồi trôi nhẹ; vài chấm "tia loé" một nhịp */}
      <div className="animate-gbappear relative z-10" style={delay(0)}>
        <span className="animate-gbappear absolute -left-5 top-4 h-2 w-2 rounded-full bg-leaf-mint" style={delay(160)} />
        <span className="animate-gbappear absolute -right-6 top-10 h-1.5 w-1.5 rounded-full bg-leaf" style={delay(240)} />
        <span className="animate-gbappear absolute -left-7 bottom-8 h-1.5 w-1.5 rounded-full bg-amber" style={delay(320)} />
        <Mascot size={170} tuThe="hello"
          className="animate-gbfloat relative z-10 drop-shadow-[0_22px_28px_rgba(24,20,15,.20)]" />
      </div>

      {/* thương hiệu */}
      <div className="relative z-10 mt-4">
        <h1 className="animate-gbappear font-[family-name:var(--font-display)] text-[34px] font-bold leading-none tracking-tight text-ink"
          style={delay(120)}>
          GreenBin <span className="text-leaf">AI</span>
        </h1>
        <p className="animate-gbappear mt-2.5 max-w-[300px] text-[15px] font-semibold leading-relaxed text-ink-soft"
          style={delay(200)}>
          Phân loại rác bằng AI, ngay tại nguồn.
        </p>
      </div>

      {/* 3 điểm value — hàng ngang 3 chip gọn */}
      <div className="relative z-10 mt-5 flex w-full max-w-[320px] gap-2">
        {GIA_TRI.map((g, i) => (
          <div key={g.text}
            className="animate-gbappear flex flex-1 flex-col items-center gap-1 rounded-xl border border-line bg-surface/80 px-2 py-2 text-center"
            style={delay(280 + i * 60)}>
            <span className="flex h-9 w-9 flex-none items-center justify-center rounded-lg bg-leaf-soft text-leaf-dark">
              <g.icon className="h-5 w-5" strokeWidth={1.9} />
            </span>
            <span className="text-xs font-bold leading-tight text-ink">{g.text}</span>
          </div>
        ))}
      </div>

      {/* CTA */}
      <div className="relative z-10 mt-5 w-full max-w-[320px]">
        <Button block size="lg" onClick={onNext} className="animate-gbappear text-[17px]" style={delay(480)}>
          Bắt đầu
        </Button>
        <button onClick={onNext}
          className="animate-gbappear mt-2.5 w-full cursor-pointer py-3 text-[14px] font-bold text-ink-soft"
          style={delay(540)}>
          Tôi đã có tài khoản
        </button>
      </div>
    </div>
  );
}

const VAI_TRO = {
  resident: { bg: "var(--color-leaf-soft)", fg: "var(--color-leaf)", border: "var(--color-leaf-soft)" },
  cleaner: { bg: "var(--color-recycle-soft)", fg: "var(--color-recycle)", border: "var(--color-recycle-soft)" },
  manager: { bg: "var(--color-bulky-soft)", fg: "var(--color-bulky)", border: "var(--color-bulky-soft)" },
} as const;

/** Form đăng ký cư dân — G1d.
 *
 *  Chọn toà trước rồi mới chọn căn, giống màn hồ sơ: danh sách căn lấy theo toà
 *  chứ không dồn mọi căn của mọi toà vào một ô. Bỏ trống nơi ở cũng đăng ký
 *  được — app đã chịu được tài khoản chưa gắn căn hộ.
 *
 *  Đăng ký xong KHÔNG cần điều hướng: `dangKy` set luôn phiên, `app/page.tsx`
 *  thấy có `user` là tự vẽ màn hình chính.
 */
function FormDangKy() {
  const { dangKy } = useSession();
  const [sdt, setSdt] = React.useState("");
  const [matKhau, setMatKhau] = React.useState("");
  const [ten, setTen] = React.useState("");
  const [toaId, setToaId] = React.useState<number | null>(null);
  const [canHoId, setCanHoId] = React.useState<number | null>(null);
  const [dsToa, setDsToa] = React.useState<{ id: number; code: string; name: string }[]>([]);
  const [dsCanHo, setDsCanHo] = React.useState<{ id: number; code: string; building_id: number }[]>([]);
  const [dangGui, setDangGui] = React.useState(false);
  const [daCham, setDaCham] = React.useState({ sdt: false, matKhau: false, ten: false });
  // Lỗi: từng trường (dưới input) và chung (dưới nút). Server trả mã → map.
  const [loi, setLoi] = React.useState<{ sdt?: string; matKhau?: string; ten?: string; noiO?: string; chung?: string }>({});

  React.useEffect(() => {
    api.buildings().then((d) => setDsToa(d.items)).catch(() => setDsToa([]));
  }, []);

  // Đổi toà thì tải lại danh sách căn và bỏ lựa chọn cũ — giữ lại một căn thuộc
  // toà khác là gửi lên server một cặp toà/căn mâu thuẫn.
  React.useEffect(() => {
    setCanHoId(null);
    if (toaId === null) {
      setDsCanHo([]);
      return;
    }
    api.units(toaId).then((d) => setDsCanHo(d.items)).catch(() => setDsCanHo([]));
  }, [toaId]);

  const sdtHopLe = /^0\d{9}$/.test(sdt.replace(/\s/g, ""));
  const tenHopLe = ten.trim().length >= 2;
  const matKhauHopLe = matKhau.length >= 8;

  // Lỗi client inline — chỉ hiện sau khi người dùng chạm trường đó.
  const loiSdtClient = daCham.sdt && sdt.trim() && !sdtHopLe ? "Số điện thoại chưa đúng (10 chữ số, bắt đầu 0)." : "";
  const loiTenClient = daCham.ten && ten.trim() && !tenHopLe ? "Tên hiển thị ít nhất 2 ký tự." : "";
  const loiMatKhauClient = daCham.matKhau && matKhau && !matKhauHopLe ? "Mật khẩu ít nhất 8 ký tự." : "";

  async function tao() {
    setLoi({});
    setDangGui(true);
    try {
      await dangKy({ phone: sdt, password: matKhau, full_name: ten, unit_id: canHoId, building_id: toaId });
    } catch (err) {
      // Map mã lỗi server sang đúng trường — không chỉ một câu chung cuối form.
      if (err instanceof ApiError) {
        if (err.code === "REG-409") setLoi({ sdt: "Số điện thoại này đã có tài khoản. Bạn đăng nhập nhé." });
        else if (err.code === "RATE-429") setLoi({ chung: err.message });
        else if (err.code === "REG-404" || err.code === "REG-400")
          setLoi({ noiO: err.message });
        else setLoi({ chung: err.message });
      } else {
        setLoi({ chung: "Không tạo được tài khoản, bạn thử lại nhé." });
      }
    } finally {
      setDangGui(false);
    }
  }

  const o =
    "w-full rounded-2xl border-[1.5px] border-line-2 bg-surface px-4 py-4 text-[15px] font-semibold outline-none focus:border-leaf";
  const chuaDu = !sdtHopLe || !matKhauHopLe || !tenHopLe;
  const tenToa = dsToa.find((t) => t.id === toaId)?.name ?? "";
  const toaKhongCoPhong = toaId !== null && dsCanHo.length === 0;

  return (
    <>
      <input
        value={sdt}
        onChange={(e) => setSdt(e.target.value)}
        onBlur={() => setDaCham((d) => ({ ...d, sdt: true }))}
        type="tel"
        inputMode="numeric"
        autoComplete="tel"
        placeholder="Số điện thoại"
        aria-invalid={!!(loi.sdt || loiSdtClient)}
        className={`mb-1 ${o}`}
      />
      {(loiSdtClient || loi.sdt) && <p className="m-0 mb-2.5 text-[12px] font-bold text-hazard-dark">{loi.sdt || loiSdtClient}</p>}

      <input
        value={ten}
        onChange={(e) => setTen(e.target.value)}
        onBlur={() => setDaCham((d) => ({ ...d, ten: true }))}
        autoComplete="name"
        maxLength={120}
        placeholder="Tên của bạn"
        aria-invalid={!!(loi.ten || loiTenClient)}
        className={`mb-1 ${o}`}
      />
      {(loiTenClient || loi.ten) && <p className="m-0 mb-2.5 text-[12px] font-bold text-hazard-dark">{loi.ten || loiTenClient}</p>}

      <input
        value={matKhau}
        onChange={(e) => setMatKhau(e.target.value)}
        onBlur={() => setDaCham((d) => ({ ...d, matKhau: true }))}
        type="password"
        autoComplete="new-password"
        placeholder="Mật khẩu (ít nhất 8 ký tự)"
        aria-invalid={!!(loi.matKhau || loiMatKhauClient)}
        className={`mb-1 ${o}`}
      />
      {(loiMatKhauClient || loi.matKhau) && (
        <p className="m-0 mb-2.5 text-[12px] font-bold text-hazard-dark">{loi.matKhau || loiMatKhauClient}</p>
      )}

      <div className="mb-2 mt-1 flex items-center gap-2">
        <span className="text-[12px] font-extrabold uppercase tracking-wide text-muted">Nơi ở (tuỳ chọn)</span>
        <span className="h-px flex-1 bg-line-2" />
      </div>

      <select
        value={toaId ?? ""}
        onChange={(e) => setToaId(e.target.value ? Number(e.target.value) : null)}
        className={`mb-1 ${o}`}
      >
        <option value="">Toà — để trống nếu chưa biết</option>
        {dsToa.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
      <select
        value={canHoId ?? ""}
        onChange={(e) => setCanHoId(e.target.value ? Number(e.target.value) : null)}
        disabled={dsCanHo.length === 0}
        className={`mb-1 ${o}`}
      >
        <option value="">{toaId === null ? "Căn hộ — chọn toà trước" : "Căn hộ — có thể bỏ trống"}</option>
        {dsCanHo.map((c) => (
          <option key={c.id} value={c.id}>
            {c.code}
          </option>
        ))}
      </select>

      {toaKhongCoPhong ? (
        <p className="m-0 mb-2 text-[12px] font-semibold text-leaf-dark">
          Tòa này chưa có danh sách phòng. Bạn vẫn có thể tiếp tục với toà đã chọn.
        </p>
      ) : canHoId !== null ? (
        <p className="m-0 mb-2 text-[12px] font-semibold text-muted">Đã chọn phòng {dsCanHo.find((c) => c.id === canHoId)?.code} thuộc {tenToa}.</p>
      ) : (
        <p className="m-0 mb-2 text-[12px] font-semibold text-muted">
          Bạn có thể bổ sung nơi ở sau. Chọn toà giúp xem đúng lịch thu gom.
        </p>
      )}
      {loi.noiO && <p className="m-0 mb-2 text-[12px] font-bold text-hazard-dark">{loi.noiO}</p>}

      {loi.chung && <div className="mb-3 text-[13px] font-bold text-hazard-dark">{loi.chung}</div>}
      <Button block size="lg" disabled={dangGui || chuaDu} onClick={tao}>
        {dangGui ? "Đang tạo…" : "Tạo tài khoản"}
      </Button>
    </>
  );
}

export function LoginScreen() {
  const { dangNhap, dangNhapSdt, error } = useSession();
  // Số điện thoại là cách chính; email giữ lại vì ba tài khoản demo dùng email
  // và người đã có tài khoản từ trước vẫn phải vào được.
  const [cheDo, setCheDo] = React.useState<"dangnhap" | "dangky">("dangnhap");
  const [cach, setCach] = React.useState<"sdt" | "email">("sdt");
  const [sdt, setSdt] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [matKhau, setMatKhau] = React.useState("");
  const [dangGui, setDangGui] = React.useState(false);
  const [demo, setDemo] = React.useState<Awaited<ReturnType<typeof api.demoAccounts>> | null>(null);

  React.useEffect(() => {
    api.demoAccounts().then(setDemo).catch(() => setDemo(null));
  }, []);

  /** Đường email. BA NÚT "VÀO THẲNG" GỌI ĐÚNG HÀM NÀY — đừng đổi chữ ký. */
  async function vao(mail: string, pass: string) {
    setDangGui(true);
    try {
      await dangNhap(mail, pass);
    } catch {
      /* câu lỗi đã nằm trong context */
    } finally {
      setDangGui(false);
    }
  }

  async function vaoBangSdt() {
    setDangGui(true);
    try {
      await dangNhapSdt(sdt, matKhau);
    } catch {
      /* câu lỗi đã nằm trong context */
    } finally {
      setDangGui(false);
    }
  }

  const oNhap =
    "w-full rounded-2xl border-[1.5px] border-line-2 bg-surface px-4 py-4 text-[15px] font-semibold outline-none focus:border-leaf-dark";
  const nutCach = (dang: boolean) =>
    `flex-1 cursor-pointer rounded-xl py-3 text-[13px] font-bold ${dang ? "bg-surface shadow-sm" : "text-muted"}`;
  const dinhDanhTrong = cach === "sdt" ? !sdt.trim() : !email.trim();

  return (
    <div className="relative flex min-h-full flex-col overflow-hidden bg-cream px-6 pb-8 pt-[70px]">
      {/* Lớp sóng nền — z-0, không che tương tác. Mobile: giãn theo bề rộng cột
          (≤560px). Desktop ≥lg: neo góc bằng bề rộng cố định để không phình ở 1920px. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/pattern/song-tren-phai.svg"
        alt=""
        aria-hidden="true"
        className="pointer-events-none absolute right-0 top-0 z-0 h-auto w-full lg:w-[min(60vw,560px)]"
      />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/pattern/song-duoi-trai.svg"
        alt=""
        aria-hidden="true"
        className="pointer-events-none absolute bottom-0 left-0 z-0 h-auto w-full lg:w-[min(60vw,560px)]"
      />

      {/* Nội dung — z-10, desktop không trải rộng quá 480px */}
      <div className="relative z-10 mx-auto flex w-full max-w-[480px] flex-col">
        {/* Đầu: logo + "GreenBin AI" + Bini nhắm mắt cười */}
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo/chinh.svg" alt="GreenBin" className="h-8 w-auto" />
            <span className="font-[family-name:var(--font-display)] text-[20px] font-bold tracking-tight text-ink">
              GreenBin <span className="text-leaf">AI</span>
            </span>
          </div>
          <Mascot size={56} tuThe="nham-mat-cuoi" />
        </div>
        <h1 className="mb-1.5 flex items-center gap-2.5 font-[family-name:var(--font-display)] text-[32px] font-bold leading-none tracking-tight text-ink">
          Chào bạn
          <IconChao className="h-7 w-7 text-leaf" />
        </h1>
        <p className="mb-6 text-[15px] font-semibold leading-snug text-ink-faint">
          Cùng phân loại rác, đúng nơi &amp; xanh hơn mỗi ngày.
        </p>

        {/* Form — thẻ nổi kem-soft, bo 24px, giữ nguyên cơ chế cheDo */}
        <div
          className="animate-gbappear rounded-[var(--gb-r-lg)] border-[1.5px] border-line-2 bg-cream-soft p-4 shadow-[var(--shadow-md)]"
          style={{ borderWidth: "1.5px" }}
        >
          {cheDo === "dangky" ? (
            <FormDangKy />
          ) : (
            <>
              <div className="mb-2.5 flex gap-1 rounded-2xl bg-surface/70 p-1">
                <button onClick={() => setCach("sdt")} className={nutCach(cach === "sdt")}>
                  Số điện thoại
                </button>
                <button onClick={() => setCach("email")} className={nutCach(cach === "email")}>
                  Email
                </button>
              </div>

              {cach === "sdt" ? (
                <input
                  value={sdt}
                  onChange={(e) => setSdt(e.target.value)}
                  type="tel"
                  inputMode="numeric"
                  autoComplete="tel"
                  placeholder="Số điện thoại"
                  className={`mb-2.5 ${oNhap}`}
                />
              ) : (
                <input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  type="email"
                  autoComplete="email"
                  placeholder="Email"
                  className={`mb-2.5 ${oNhap}`}
                />
              )}
              <input
                value={matKhau}
                onChange={(e) => setMatKhau(e.target.value)}
                type="password"
                autoComplete="current-password"
                placeholder="Mật khẩu"
                className={`mb-3.5 ${oNhap}`}
              />
              {error && <div className="mb-3 text-[13px] font-bold text-hazard-dark">{error}</div>}
              <Button
                block
                size="lg"
                className="bg-leaf-dark text-cream hover:bg-leaf"
                disabled={dangGui || dinhDanhTrong}
                onClick={() => (cach === "sdt" ? vaoBangSdt() : vao(email, matKhau))}
              >
                {dangGui ? "Đang vào…" : "Đăng nhập"}
              </Button>
            </>
          )}
          <button
            onClick={() => setCheDo(cheDo === "dangky" ? "dangnhap" : "dangky")}
            className="mt-3 w-full cursor-pointer py-2 text-[14px] font-bold text-leaf-dark"
          >
            {cheDo === "dangky" ? "Đã có tài khoản? Đăng nhập" : "Chưa có tài khoản? Đăng ký bằng số điện thoại"}
          </button>
        </div>

        {/* Divider demo */}
        <div className="my-5 flex items-center gap-3">
          <span className="h-px flex-1 bg-line-2" />
          <span className="text-xs font-bold tracking-wider text-label-faint">TRẢI NGHIỆM NHANH (DEMO)</span>
          <span className="h-px flex-1 bg-line-2" />
        </div>

        {/* 3 thẻ demo 1-chạm — thay icon người bằng ảnh role-*.svg */}
        {demo?.accounts.map((tk) => {
          const mau = VAI_TRO[tk.role as keyof typeof VAI_TRO] ?? VAI_TRO.resident;
          const hinh =
            tk.role === "resident"
              ? "/illus/role-cu-dan.svg"
              : tk.role === "cleaner"
                ? "/illus/role-ve-sinh.svg"
                : "/illus/role-quan-li.svg";
          return (
            <button
              key={tk.email}
              onClick={() => vao(tk.email, demo.password)}
              disabled={dangGui}
              className="mb-2.5 flex w-full cursor-pointer items-center gap-3 rounded-2xl border-[1.5px] bg-surface p-3.5 text-left"
              style={{ borderColor: mau.border }}
            >
              <span
                aria-hidden="true"
                className="flex h-11 w-11 flex-none items-center justify-center rounded-xl"
                style={{ background: mau.bg }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={hinh} alt="" className="h-11 w-11 object-contain" />
              </span>
              <span className="flex-1">
                <span className="block text-[15px] font-bold">
                  Vào với vai trò {tk.role === "resident" ? "Cư dân" : tk.role === "cleaner" ? "Đội vệ sinh" : "Ban quản lý"}
                </span>
                <span className="block text-xs font-semibold text-muted">{tk.description}</span>
              </span>
              <IconTiepTuc className="h-[18px] w-[18px]" style={{ color: mau.fg }} />
            </button>
          );
        })}

      {/* Lối vào bản mô phỏng thiết bị. Là trang tĩnh trong `public/` nên đi
          thẳng bằng thẻ <a>, không qua bộ định tuyến của ứng dụng — bản xuất
          tĩnh chỉ có ba đường thật, thêm route mới là 404.
          ⚠️ Đường dẫn PHẢI có dấu `/` ở cuối và KHÔNG có đuôi `.html`, vì
          `next.config.ts` đặt `trailingSlash: true`. Đo trên bản chạy thật:
          `/demo-thiet-bi/` → 200 · `/demo-thiet-bi` → 308 · `/demo-thiet-bi.html`
          → 404. Máy chủ phát triển thì ngược lại (chỉ mở được đuôi `.html`) —
          hai môi trường vênh nhau, và bản chạy thật mới là bản phải đúng. */}
      <a
        href="/demo-thiet-bi/"
        className="mb-4 mt-1 flex w-full cursor-pointer items-center gap-3 rounded-2xl border-[1.5px] border-dashed border-line-2 bg-surface p-3.5 text-left no-underline"
      >
        <span className="flex h-[42px] w-[42px] flex-none items-center justify-center rounded-xl bg-leaf-soft">
          <IconManHinhRong className="h-[22px] w-[22px] text-leaf-dark" />
        </span>
        <span className="flex-1">
          <span className="block text-[15px] font-bold text-ink">Xem mô phỏng thiết bị</span>
          <span className="block text-xs font-semibold text-muted">
            Thùng thông minh chạy thử — không cần đăng nhập
          </span>
        </span>
        <IconTiepTuc className="h-[18px] w-[18px] text-muted" />
      </a>

      <p className="m-0 text-center text-[11px] font-semibold leading-relaxed text-muted-slate">
        {demo?.notice ??
          "Hệ thống demo dùng dữ liệu mô phỏng và dữ liệu công khai. Ảnh tải lên được tự động xoá thông tin vị trí và làm mờ khuôn mặt trước khi xử lý."}
      </p>
      </div>
    </div>
  );
}
