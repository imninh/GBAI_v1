"use client";

/** Console đơn vị thu gom — desktop.
 *
 * Người dùng ở đây ít kinh nghiệm công nghệ, nên cột trái chỉ có ba dòng, đúng
 * ba câu hỏi của một ngày làm việc: *hôm nay đi đâu* · *chờ tôi duyệt* · *báo
 * cáo*. Mọi màn hình còn lại nằm dưới "Xem thêm" — vẫn mở được, nhưng không
 * chen vào tầm mắt. Mục nào vai trò hiện tại không có quyền thì **hiện mờ kèm
 * tooltip giải thích**, không ẩn hẳn.
 */

import * as React from "react";
import Link from "next/link";

import { AgentRunScreen, OpsScreen, OverviewScreen, QualityScreen } from "@/components/manager/insights";
import { PickupQueue, RouteApproval, VerifyQueue, WeightConfirmQueue } from "@/components/manager/queues";
import { BrowserFrame } from "@/components/ui/shell";
import { api } from "@/lib/api";
import { IconKhoa } from "@/lib/icons";
import { useSession } from "@/lib/session";

/** Màn có đủ rộng cho console không.
 *
 *  Trả `null` cho tới khi đo được — dự án build tĩnh nên lần dựng đầu tiên
 *  không có `window`. Mặc định `false` sẽ khiến MỌI người dùng máy tính thấy
 *  nhoáng màn "mở trên máy tính" rồi mới biến mất.
 */
function useDuRong(): boolean | null {
  const [duRong, setDuRong] = React.useState<boolean | null>(null);
  React.useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const doLai = () => setDuRong(mq.matches);
    doLai();
    mq.addEventListener("change", doLai);
    return () => mq.removeEventListener("change", doLai);
  }, []);
  return duRong;
}

type Nav = "duyet" | "baocao" | "overview" | "runs";
type TabDuyet = "pickup" | "verify" | "route" | "weight";
type TabBaoCao = "ops" | "quality";

type Muc = { key: string; label: string; permission: string; href?: string };

const MUC_CHINH: Muc[] = [
  { key: "homnay", label: "Hôm nay đi đâu", permission: "view_bins", href: "/dieu-phoi" },
  { key: "duyet", label: "Chờ tôi duyệt", permission: "review_pickup" },
  { key: "baocao", label: "Báo cáo", permission: "view_ops" },
];

const MUC_PHU: Muc[] = [
  { key: "overview", label: "Tổng quan", permission: "view_ops" },
  { key: "runs", label: "Agent run", permission: "view_runs" },
];

const TAB_DUYET: Muc[] = [
  { key: "pickup", label: "Thu gom", permission: "review_pickup" },
  { key: "verify", label: "Nhãn nghi ngờ", permission: "verify_label" },
  { key: "route", label: "Tuyến gộp", permission: "review_route" },
  // Màn đối soát cân đã viết xong từ trước nhưng chưa có đường nào bấm tới.
  { key: "weight", label: "Đối soát cân", permission: "review_pickup" },
];

const TAB_BAO_CAO: Muc[] = [
  { key: "ops", label: "Vận hành", permission: "view_ops" },
  { key: "quality", label: "Chất lượng AI", permission: "view_eval" },
];

export function ManagerConsole() {
  const { user, dangXuat, duocPhep, lyDoCam } = useSession();
  const duRong = useDuRong();
  // Vào là thấy việc, không phải thấy số liệu — "Tổng quan" lui xuống Xem thêm.
  const [nav, setNav] = React.useState<Nav>("duyet");
  const [tabDuyet, setTabDuyet] = React.useState<TabDuyet>("pickup");
  const [tabBaoCao, setTabBaoCao] = React.useState<TabBaoCao>("ops");
  const [moThem, setMoThem] = React.useState(false);
  const [dem, setDem] = React.useState({ pickup: 0, labels: 0, routes: 0 });

  React.useEffect(() => {
    api
      .overview()
      .then((d) => setDem({ pickup: d.queues.pickup, labels: d.queues.labels, routes: d.queues.routes }))
      .catch(() => setDem({ pickup: 0, labels: 0, routes: 0 }));
  }, [nav, tabDuyet]);

  const demTab: Record<string, number> = { pickup: dem.pickup, verify: dem.labels, route: dem.routes };
  const tongCanDuyet = dem.pickup + dem.labels + dem.routes;

  if (duRong === null) return null;
  if (!duRong)
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-3 px-8 text-center">
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">
          Console dùng trên máy tính
        </div>
        <p className="max-w-[42ch] text-[15px] font-semibold leading-snug text-muted">
          Chào {user?.full_name}. Hàng đợi duyệt và trang báo cáo có nhiều cột số liệu, cần màn
          rộng từ 1024 điểm ảnh trở lên mới đủ chỗ.
        </p>
        <p className="text-[13px] font-semibold text-muted">
          App trên điện thoại dành cho cư dân và nhân viên thu gom.
        </p>
        <button onClick={dangXuat} className="mt-2 cursor-pointer text-[13px] font-bold text-hazard-dark">
          Đăng xuất
        </button>
      </div>
    );

  return (
    <BrowserFrame>
      <div className="flex h-14 flex-none items-center gap-3.5 border-b border-line-3 bg-white px-5">
        <span className="font-[family-name:var(--font-display)] text-base font-bold tracking-tight">
          GreenBin<span className="text-leaf"> AI</span>
        </span>
        <span className="rounded-lg border border-line-3 bg-console-bg px-3 py-1.5 text-[13px] font-bold">
          Toà: {user?.building || "Tất cả"}
        </span>
        <span className="flex-1" />
        <span className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-bulky-soft text-[13px] font-extrabold text-bulky">
            {user?.full_name
              ?.split(" ")
              .slice(-2)
              .map((w) => w[0])
              .join("") ?? "ĐV"}
          </span>
          <span>
            <span className="block text-[13px] font-bold leading-tight">{user?.full_name}</span>
            <span className="text-[11px] font-semibold text-muted">Đơn vị thu gom</span>
          </span>
        </span>
        <button onClick={dangXuat} className="cursor-pointer text-[13px] font-bold text-hazard-dark">
          Đăng xuất
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="w-[230px] flex-none overflow-y-auto border-r border-line-3 bg-cream-soft p-3">
          {MUC_CHINH.map((m) => (
            <NavButton
              key={m.key}
              muc={m}
              nav={nav}
              setNav={(n) => setNav(n as Nav)}
              allowed={duocPhep(m.permission)}
              reason={lyDoCam(m.permission)}
              badge={m.key === "duyet" ? tongCanDuyet : undefined}
            />
          ))}

          <div className="mx-2 my-3 h-px bg-line-3" />
          <button
            onClick={() => setMoThem((v) => !v)}
            aria-expanded={moThem}
            className="mb-0.5 flex w-full cursor-pointer items-center rounded-xl px-3 py-2.5 text-left text-[13px] font-bold text-muted"
          >
            Xem thêm
            <span className="flex-1" />
            <span className="text-[10px] leading-none">{moThem ? "▲" : "▼"}</span>
          </button>
          {moThem &&
            MUC_PHU.map((m) => (
              <NavButton
                key={m.key}
                muc={m}
                nav={nav}
                setNav={(n) => setNav(n as Nav)}
                allowed={duocPhep(m.permission)}
                reason={lyDoCam(m.permission)}
              />
            ))}
        </div>

        <div className="gb-scroll flex-1 overflow-y-auto px-8 py-6">
          {nav === "duyet" && (
            <>
              <SubTabs
                muc={TAB_DUYET}
                dang={tabDuyet}
                setDang={(k) => setTabDuyet(k as TabDuyet)}
                duocPhep={duocPhep}
                lyDoCam={lyDoCam}
                dem={demTab}
              />
              {tabDuyet === "pickup" && <PickupQueue />}
              {tabDuyet === "verify" && <VerifyQueue />}
              {tabDuyet === "route" && <RouteApproval />}
              {tabDuyet === "weight" && <WeightConfirmQueue />}
            </>
          )}

          {nav === "baocao" && (
            <>
              <SubTabs
                muc={TAB_BAO_CAO}
                dang={tabBaoCao}
                setDang={(k) => setTabBaoCao(k as TabBaoCao)}
                duocPhep={duocPhep}
                lyDoCam={lyDoCam}
                dem={{}}
              />
              {tabBaoCao === "ops" && <OpsScreen />}
              {tabBaoCao === "quality" && <QualityScreen />}
            </>
          )}

          {/* Tổng quan chỉ có một đích nhảy duy nhất là hàng đợi thu gom. */}
          {nav === "overview" && (
            <OverviewScreen
              onGoto={() => {
                setNav("duyet");
                setTabDuyet("pickup");
              }}
            />
          )}
          {nav === "runs" && <AgentRunScreen />}
        </div>
      </div>
    </BrowserFrame>
  );
}

function SubTabs({
  muc,
  dang,
  setDang,
  duocPhep,
  lyDoCam,
  dem,
}: {
  muc: Muc[];
  dang: string;
  setDang: (k: string) => void;
  duocPhep: (p: string) => boolean;
  lyDoCam: (p: string) => string;
  dem: Record<string, number>;
}) {
  return (
    <div className="mb-5 flex gap-1.5 border-b border-line-3 pb-2.5">
      {muc.map((m) => {
        const allowed = duocPhep(m.permission);
        const dangChon = dang === m.key;
        return (
          <button
            key={m.key}
            onClick={() => allowed && setDang(m.key)}
            disabled={!allowed}
            title={allowed ? undefined : lyDoCam(m.permission)}
            className="flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-[13px] font-bold"
            style={{
              background: dangChon ? "#16211a" : "transparent",
              color: !allowed ? "#b8beb6" : dangChon ? "#fff" : "#3a453d",
              cursor: allowed ? "pointer" : "not-allowed",
            }}
          >
            {m.label}
            {!allowed && <IconKhoa className="h-3.5 w-3.5" />}
            {allowed && dem[m.key] ? (
              <span className="rounded-md bg-hazard px-1.5 py-0.5 text-[10px] font-extrabold text-white">
                {dem[m.key]}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

function NavButton({
  muc,
  nav,
  setNav,
  allowed,
  reason,
  badge,
}: {
  muc: { key: string; label: string; href?: string };
  nav: string;
  setNav: (n: string) => void;
  allowed: boolean;
  reason: string;
  badge?: number;
}) {
  const dangChon = nav === muc.key;
  const className = "mb-0.5 flex w-full items-center rounded-xl px-3 py-2.5 text-left text-[13px] font-bold";
  const style = {
    background: dangChon ? "#16211a" : "transparent",
    color: !allowed ? "#b8beb6" : dangChon ? "#fff" : "#3a453d",
    cursor: allowed ? "pointer" : "not-allowed",
  };

  if (muc.href) {
    return (
      <Link
        href={muc.href}
        aria-disabled={!allowed}
        title={allowed ? undefined : reason}
        onClick={(e) => {
          if (!allowed) e.preventDefault();
        }}
        className={className}
        style={style}
      >
        {muc.label}
        <span className="flex-1" />
        {!allowed && <IconKhoa className="h-3.5 w-3.5" />}
      </Link>
    );
  }

  return (
    <button
      onClick={() => allowed && setNav(muc.key)}
      disabled={!allowed}
      title={allowed ? undefined : reason}
      className={className}
      style={style}
    >
      {muc.label}
      <span className="flex-1" />
      {!allowed && <IconKhoa className="h-3.5 w-3.5" />}
      {allowed && badge ? (
        <span className="rounded-md bg-hazard px-2 py-0.5 text-[11px] font-extrabold text-white">{badge}</span>
      ) : null}
    </button>
  );
}
