"use client";

/** Onboarding + đăng nhập.
 *
 * Linh vật "Mun" là ba file PNG ở `assets/`, được `scripts/build_assets.py` cắt
 * và xuất thành WebP ba bề rộng trong `public/mascot/`. Bản SVG vẽ tay vẫn giữ
 * nguyên làm ảnh dự phòng: nếu file ảnh lỗi hoặc chưa build thì giao diện vẫn
 * có linh vật thay vì một ô trống.
 */

import * as React from "react";

import { Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { IconChao, IconManHinhRong, IconTiepTuc } from "@/lib/icons";
import { useSession } from "@/lib/session";

/** Ba tư thế, map đúng ba tình huống trong luồng cư dân. */
export type TuTheMascot = "mascot" | "hello" | "magnify";

const MO_TA_TU_THE: Record<TuTheMascot, string> = {
  mascot: "Mun — linh vật GreenBin",
  hello: "Mun vẫy tay chào",
  magnify: "Mun đang soi món rác",
};

/** Ảnh dự phòng khi file WebP không tải được. */
function MascotSVG({ size, className }: { size: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" className={className} aria-label={MO_TA_TU_THE.mascot}>
      <circle cx="60" cy="62" r="42" fill="#8a9a92" />
      <ellipse cx="60" cy="72" rx="30" ry="26" fill="#cfdcd4" />
      <path d="M22 34c4-12 14-16 22-10-6 5-9 11-9 18z" fill="#8a9a92" />
      <path d="M98 34c-4-12-14-16-22-10 6 5 9 11 9 18z" fill="#8a9a92" />
      <ellipse cx="45" cy="55" rx="15" ry="12" fill="#3a453d" />
      <ellipse cx="75" cy="55" rx="15" ry="12" fill="#3a453d" />
      <circle cx="47" cy="55" r="6" fill="#fff" />
      <circle cx="73" cy="55" r="6" fill="#fff" />
      <circle cx="48" cy="56" r="3" fill="#16211a" />
      <circle cx="74" cy="56" r="3" fill="#16211a" />
      <ellipse cx="60" cy="70" rx="6" ry="4.5" fill="#16211a" />
      <path d="M52 80q8 7 16 0" stroke="#16211a" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      <path d="M28 96c8 6 20 9 32 9s24-3 32-9" stroke="#8a9a92" strokeWidth="7" fill="none" strokeLinecap="round" />
    </svg>
  );
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
  if (loi) return <MascotSVG size={size} className={className} />;

  // Ba ảnh gốc gần vuông (tỉ lệ 0,99–1,03). Đặt trong khung vuông cố định +
  // object-contain: không méo ảnh, không giật layout khi ảnh tải xong.
  //
  // Cố ý dùng `<img>` chứ không `next/image`: bản build là `output: "export"`
  // nên `images.unoptimized: true`, tức next/image không tối ưu được gì thêm.
  // Ba bề rộng WebP ở đây do `scripts/build_assets.py` dựng sẵn (2,3 MB →
  // 22–80 KB) và `srcSet` bên dưới đã làm đúng việc mà rule này muốn.
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/mascot/${tuThe}-512.webp`}
      srcSet={`/mascot/${tuThe}-240.webp 240w, /mascot/${tuThe}-360.webp 360w, /mascot/${tuThe}-512.webp 512w`}
      sizes={`${size}px`}
      width={size}
      height={size}
      alt={MO_TA_TU_THE[tuThe]}
      className={`object-contain ${className ?? ""}`}
      onError={() => setLoi(true)}
    />
  );
}

/** Bốn beat onboarding — kể chuyện, mỗi màn MỘT ý như prototype redesign.
 *  Mỗi beat: tint nền + blob khác nhau, Mun một tư thế, chữ khổng lồ, CTA duy nhất.
 *  Không phải form, không xin quyền — chỉ dẫn dắt người dùng tới màn đăng nhập.
 */
const ONBOARDING_BEATS = [
  {
    over: "Cùng Mun bắt đầu",
    h1: "Bỏ rác\ndúng thùng",
    body: "Chai dầu, hộp sữa, pin cũ… ai cũng từng phân vân bỏ vào đâu.",
    cta: "Tiếp tục",
    tuThe: "mascot" as const,
    tint: "linear-gradient(180deg,#e6f4ea,#f4f1ea)",
    blob: "#d6efe0",
    kick: "#1f8a4f",
  },
  {
    over: "Đơn giản thôi",
    h1: "Chụp một\ntấm là xong",
    body: "AI nhận ra món rác ngay, mách bạn bỏ thùng nào và để ở đâu.",
    cta: "Tiếp tục",
    tuThe: "magnify" as const,
    tint: "linear-gradient(180deg,#e2eefb,#f4f1ea)",
    blob: "#cfe0f7",
    kick: "#2f7fe0",
  },
  {
    over: "Chào bạn nhé",
    h1: "Mình là\nMun 🦝",
    body: "Gấu mèo đồng hành của bạn — mình sẽ khen khi bạn phân loại đúng.",
    cta: "Tiếp tục",
    tuThe: "hello" as const,
    tint: "linear-gradient(180deg,#efe9f9,#f4f1ea)",
    blob: "#e0d6f4",
    kick: "#7c5cdf",
  },
  {
    over: "Sẵn sàng chưa?",
    h1: "Mỗi món\nđúng chỗ",
    body: "là một lần bạn cứu hành tinh — và cây xanh của bạn lớn thêm.",
    cta: "Bắt đầu",
    tuThe: "mascot" as const,
    tint: "linear-gradient(180deg,#e6f4ea,#f4f1ea)",
    blob: "#d6efe0",
    kick: "#1f8a4f",
  },
];

export function OnboardingScreen({ onNext }: { onNext: () => void }) {
  const [beat, setBeat] = React.useState(0);
  const b = ONBOARDING_BEATS[beat];

  const tiep = () => (beat >= ONBOARDING_BEATS.length - 1 ? onNext() : setBeat((i) => i + 1));

  return (
    <div
      key={beat}
      className="animate-gbfade relative flex min-h-full flex-col overflow-hidden px-[26px] pb-7 pt-[60px]"
      style={{ background: b.tint }}
    >
      {/* chấm tiến trình + bỏ qua */}
      <div className="relative z-10 flex items-center justify-between">
        <div className="flex gap-1.5">
          {ONBOARDING_BEATS.map((_, i) => (
            <span
              key={i}
              className="h-[6px] rounded-full transition-all"
              style={{
                width: i === beat ? "20px" : "6px",
                background: i <= beat ? b.kick : "rgba(22,33,26,.18)",
              }}
            />
          ))}
        </div>
        <button onClick={onNext} className="cursor-pointer bg-transparent text-[14px] font-bold text-ink-soft">
          Bỏ qua
        </button>
      </div>

      {/* cảnh minh hoạ: blob + Mun + lá bay */}
      <div className="relative z-0 mt-8 flex flex-1 items-center justify-center">
        <div className="absolute h-[290px] w-[290px] rounded-full" style={{ background: b.blob, filter: "blur(2px)" }} />
        <span className="animate-gbfloat absolute left-[8%] top-[6%] text-[22px]">🍃</span>
        <span className="animate-gbfloat absolute bottom-[12%] right-[6%] text-[17px] [animation-delay:.6s]">✦</span>
        <Mascot size={264} tuThe={b.tuThe} className="animate-gbfloat relative z-10 drop-shadow-[0_20px_26px_rgba(24,20,15,.22)]" />
      </div>

      {/* nội dung + CTA */}
      <div className="relative z-10">
        <div className="mb-2.5 text-[11px] font-extrabold uppercase tracking-[.1em]" style={{ color: b.kick }}>
          {b.over}
        </div>
        <h1 className="mb-3 whitespace-pre-line font-[family-name:var(--font-display)] text-[46px] font-bold leading-[.98] tracking-tight text-ink">
          {b.h1}
        </h1>
        <p className="mb-6 max-w-[300px] text-[15.5px] font-medium leading-relaxed text-ink-soft">{b.body}</p>
        <Button block size="lg" onClick={tiep} className="text-[17px]">
          {b.cta}
        </Button>
        <button onClick={onNext} className="mt-1.5 w-full cursor-pointer py-3 text-[14px] font-bold text-ink">
          Tôi đã có tài khoản
        </button>
      </div>
    </div>
  );
}

const VAI_TRO = {
  resident: { bg: "#e6f4ea", fg: "#2fae66", border: "#e6f4ea" },
  cleaner: { bg: "#e2eefb", fg: "#2f7fe0", border: "#e2eefb" },
  manager: { bg: "#ece7f6", fg: "#7c5cdf", border: "#ece7f6" },
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
  const { dangKy, error } = useSession();
  const [sdt, setSdt] = React.useState("");
  const [matKhau, setMatKhau] = React.useState("");
  const [ten, setTen] = React.useState("");
  const [toaId, setToaId] = React.useState<number | null>(null);
  const [canHoId, setCanHoId] = React.useState<number | null>(null);
  const [dsToa, setDsToa] = React.useState<{ id: number; code: string; name: string }[]>([]);
  const [dsCanHo, setDsCanHo] = React.useState<{ id: number; code: string; building_id: number }[]>([]);
  const [dangGui, setDangGui] = React.useState(false);

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

  async function tao() {
    setDangGui(true);
    try {
      await dangKy({ phone: sdt, password: matKhau, full_name: ten, unit_id: canHoId });
    } catch {
      /* câu lỗi đã nằm trong context */
    } finally {
      setDangGui(false);
    }
  }

  const o =
    "w-full rounded-2xl border-[1.5px] border-line-2 bg-white px-4 py-4 text-[15px] font-semibold outline-none focus:border-leaf";
  const chuaDu = !sdt.trim() || matKhau.length < 8 || ten.trim().length < 2;

  return (
    <>
      <input
        value={sdt}
        onChange={(e) => setSdt(e.target.value)}
        type="tel"
        inputMode="numeric"
        autoComplete="tel"
        placeholder="Số điện thoại"
        className={`mb-2.5 ${o}`}
      />
      <input
        value={ten}
        onChange={(e) => setTen(e.target.value)}
        autoComplete="name"
        maxLength={120}
        placeholder="Tên của bạn"
        className={`mb-2.5 ${o}`}
      />
      <input
        value={matKhau}
        onChange={(e) => setMatKhau(e.target.value)}
        type="password"
        autoComplete="new-password"
        placeholder="Mật khẩu (ít nhất 8 ký tự)"
        className={`mb-2.5 ${o}`}
      />

      <select
        value={toaId ?? ""}
        onChange={(e) => setToaId(e.target.value ? Number(e.target.value) : null)}
        className={`mb-2.5 ${o}`}
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
      <p className="m-0 mb-3.5 text-[11px] font-semibold text-muted">
        Gắn căn hộ để xem đúng lịch thu gom của toà và sắp điểm gửi theo khoảng cách. Bỏ trống cũng dùng
        được, sửa sau ở mục Tôi.
      </p>

      {error && <div className="mb-3 text-[13px] font-bold text-hazard-dark">{error}</div>}
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
    "w-full rounded-2xl border-[1.5px] border-line-2 bg-white px-4 py-4 text-[15px] font-semibold outline-none focus:border-leaf";
  const nutCach = (dang: boolean) =>
    `flex-1 cursor-pointer rounded-xl py-2 text-[13px] font-bold ${dang ? "bg-white shadow-sm" : "text-muted"}`;
  const dinhDanhTrong = cach === "sdt" ? !sdt.trim() : !email.trim();

  return (
    <div className="flex min-h-full flex-col bg-cream px-6 pb-8 pt-[70px]">
      <div className="mb-[18px] flex h-[60px] w-[60px] items-center justify-center rounded-[20px] bg-leaf shadow-[0_10px_22px_-8px_rgba(47,174,102,.6)]">
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M7 19a2 2 0 0 1-2-2l-1-9h16l-1 9a2 2 0 0 1-2 2z" />
          <path d="M3 8h18" />
          <path d="M9 8V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3" />
        </svg>
      </div>
      <h1 className="mb-1.5 flex items-center gap-2.5 font-[family-name:var(--font-display)] text-[34px] font-bold leading-none tracking-tight">
        Chào bạn
        <IconChao className="h-7 w-7 text-leaf" />
      </h1>
      <p className="mb-6 text-[15px] font-semibold leading-snug text-[#5a6b5f]">Chụp ảnh — biết ngay bỏ vào thùng nào.</p>

      {cheDo === "dangky" ? (
        <FormDangKy />
      ) : (
        <>
          <div className="mb-2.5 flex gap-1 rounded-2xl bg-[#eef1ec] p-1">
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

      <div className="my-5 flex items-center gap-3">
        <span className="h-px flex-1 bg-line-2" />
        <span className="text-xs font-bold text-[#a0a89f]">TÀI KHOẢN DEMO</span>
        <span className="h-px flex-1 bg-line-2" />
      </div>

      {demo?.accounts.map((tk) => {
        const mau = VAI_TRO[tk.role as keyof typeof VAI_TRO] ?? VAI_TRO.resident;
        return (
          <button
            key={tk.email}
            onClick={() => vao(tk.email, demo.password)}
            disabled={dangGui}
            className="mb-2.5 flex w-full cursor-pointer items-center gap-3 rounded-2xl border-[1.5px] bg-white p-3.5 text-left"
            style={{ borderColor: mau.border }}
          >
            <span className="flex h-[42px] w-[42px] flex-none items-center justify-center rounded-xl" style={{ background: mau.bg }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={mau.fg} strokeWidth="2" strokeLinecap="round">
                <circle cx="12" cy="8" r="4" />
                <path d="M4 21c0-4 3.6-7 8-7s8 3 8 7" />
              </svg>
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
        className="mb-4 mt-1 flex w-full cursor-pointer items-center gap-3 rounded-2xl border-[1.5px] border-dashed border-line-2 bg-white p-3.5 text-left no-underline"
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

      <p className="m-0 text-center text-[11px] font-semibold leading-relaxed text-[#9aa39a]">
        {demo?.notice ??
          "Hệ thống demo dùng dữ liệu mô phỏng và dữ liệu công khai. Ảnh tải lên được tự động xoá thông tin vị trí và làm mờ khuôn mặt trước khi xử lý."}
      </p>
    </div>
  );
}
