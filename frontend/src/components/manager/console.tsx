"use client";

/** Console đơn vị thu gom — desktop.
 *
 * Người dùng ở đây ít kinh nghiệm công nghệ, nên cột trái chỉ có ba dòng, đúng
 * ba câu hỏi của một ngày làm việc: *hôm nay đi đâu* · *chờ tôi duyệt* · *báo
 * cáo*. Hai màn còn lại (Tổng quan, Agent run) hiện ngay bên dưới đường kẻ,
 * không phải bấm mở thêm nữa. Mục nào vai trò hiện tại không có quyền thì
 * **hiện mờ kèm tooltip giải thích**, không ẩn hẳn.
 */

import * as React from "react";
import dynamic from "next/dynamic";
import Link from "next/link";

import { AgentRunScreen, OpsScreen, OverviewScreen, QualityScreen } from "@/components/manager/insights";
import { KipVaSuCo } from "@/components/manager/kip_va_su_co";
import { LiveVehiclesScreen } from "@/components/manager/live-vehicles";
import { PickupQueue, RouteApproval, VerifyQueue } from "@/components/manager/queues";
import { TatCaYeuCau } from "@/components/manager/tat-ca-yeu-cau";
import { XepTuyen } from "@/components/manager/xep-tuyen";
import { BinDetail } from "@/components/bins/bin-detail";
import { BrowserFrame } from "@/components/ui/shell";
import { BellButton, NotificationSheet } from "@/components/ui/notifications";
import { ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { Bin, NhanVien } from "@/lib/bins";
import { IconKhoa } from "@/lib/icons";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

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

type Nav = "homnay" | "duyet" | "tat_ca" | "xep_tuyen" | "kip_suco" | "baocao" | "overview" | "runs" | "xe";
type TabDuyet = "pickup" | "verify" | "route";
type TabBaoCao = "ops" | "quality";

type Muc = { key: string; label: string; permission: string; href?: string };

const MUC_CHINH: Muc[] = [
  // WS-1a: "Hôm nay đi đâu" là tab nội bộ (không nhảy khỏi dashboard). Route
  // `/dieu-phoi` vẫn tồn tại làm deep-link phụ, nhưng lối chính là tab này.
  { key: "homnay", label: "Hôm nay đi đâu", permission: "view_bins" },
  { key: "duyet", label: "Chờ tôi duyệt", permission: "review_pickup" },
  { key: "tat_ca", label: "Tất cả yêu cầu", permission: "view_all_pickups" },
  { key: "xep_tuyen", label: "Xếp tuyến", permission: "review_route" },
  { key: "kip_suco", label: "Kíp thu gom & sự cố", permission: "review_route" },
  { key: "baocao", label: "Báo cáo", permission: "view_ops" },
];

const MUC_PHU: Muc[] = [
  { key: "overview", label: "Tổng quan", permission: "view_ops" },
  { key: "xe", label: "Xe đang chạy", permission: "review_route" },
  { key: "runs", label: "Agent run", permission: "view_runs" },
];

const TAB_DUYET: Muc[] = [
  { key: "pickup", label: "Thu gom", permission: "review_pickup" },
  { key: "verify", label: "Nhãn nghi ngờ", permission: "verify_label" },
  { key: "route", label: "Tuyến gộp", permission: "review_route" },
];

const TAB_BAO_CAO: Muc[] = [
  { key: "ops", label: "Vận hành", permission: "view_ops" },
  { key: "quality", label: "Chất lượng AI", permission: "view_eval" },
];

// Leaflet chạm thẳng vào `window` nên phải dynamic `ssr:false` (build `output: export`).
const BinMap = dynamic(() => import("@/components/bins/bin-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

export function ManagerConsole() {
  const { user, dangXuat, duocPhep, lyDoCam } = useSession();
  const duRong = useDuRong();
  // GOI_3 / M2 — vào là thấy tình hình tổng (bản đồ thùng + việc chờ), không phải
  // hàng đợi duyệt. Badge "Cần duyệt" vẫn hiện ở mục "Chờ tôi duyệt".
  const [nav, setNav] = React.useState<Nav>("homnay");
  const [tabDuyet, setTabDuyet] = React.useState<TabDuyet>("pickup");
  const [tabBaoCao, setTabBaoCao] = React.useState<TabBaoCao>("ops");
  const [dem, setDem] = React.useState({ pickup: 0, labels: 0, routes: 0 });
  const [moThongBao, setMoThongBao] = React.useState(false);

  React.useEffect(() => {
    const lay = () =>
      api
        .overview()
        .then((d) => setDem({ pickup: d.queues.pickup, labels: d.queues.labels, routes: d.queues.routes }))
        .catch(() => setDem({ pickup: 0, labels: 0, routes: 0 }));
    lay();
    const id = setInterval(lay, 30000);
    return () => clearInterval(id);
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
      <div className="flex h-14 flex-none items-center gap-3.5 border-b border-line-3 bg-surface px-5">
        <span className="font-[family-name:var(--font-display)] text-base font-bold tracking-tight">
          GreenBin<span className="text-leaf"> AI</span>
        </span>
        <span className="rounded-lg border border-line-3 bg-console-bg px-3 py-1.5 text-[13px] font-bold">
          Toà: {user?.building || "Tất cả"}
        </span>
        <span className="flex-1" />
        <span className="flex items-center gap-2.5">
          <BellButton onOpen={() => setMoThongBao(true)} />
          <span className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full bg-bulky-soft">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/avatar/quan-ly.svg" alt="Avatar ban quản lý" className="h-8 w-8 object-contain" />
        </span>
          <span>
            <span className="block text-[13px] font-bold leading-tight">{user?.full_name}</span>
            <span className="text-xs font-semibold text-muted">Đơn vị thu gom</span>
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
          {MUC_PHU.map((m) => (
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
          {nav === "homnay" && <HomNayPanel />}
          {nav === "duyet" && (
            <div key={nav} className="animate-gbscreen min-h-full">
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
              </>
            </div>
          )}

          {nav === "baocao" && (
            <div key={nav} className="animate-gbscreen min-h-full">
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
            </div>
          )}

          {nav === "xep_tuyen" && (
            <XepTuyen
              onDuyetTuyen={() => {
                setNav("duyet");
                setTabDuyet("route");
              }}
            />
          )}
          {nav === "kip_suco" && <KipVaSuCo />}
          {nav === "tat_ca" && <TatCaYeuCau />}
          {nav === "xe" && <LiveVehiclesScreen />}
          {nav === "overview" && <OverviewScreen
            onGoto={(nav) => {
              if (nav === "homnay") {
                setNav("homnay");
              } else if (nav === "kip_suco") {
                setNav("kip_suco");
              } else if (nav === "duyet:route") {
                setNav("duyet");
                setTabDuyet("route");
              } else {
                // "pickup" hoặc "duyet:pickup" — mặc định hàng đợi thu gom.
                setNav("duyet");
                setTabDuyet("pickup");
              }
            }}
          />}
{nav === "runs" && <AgentRunScreen />}
        </div>
      </div>

      {moThongBao && (
        <NotificationSheet
          onClose={() => setMoThongBao(false)}
          onNavigate={(target) => {
            setMoThongBao(false);
            if (target === "manager:queues") {
              setNav("duyet");
              setTabDuyet("pickup");
            } else if (target === "manager:kip_suco") {
              setNav("kip_suco");
            } else if (target === "manager:duyet_route") {
              setNav("duyet");
              setTabDuyet("route");
            }
          }}
        />
      )}
    </BrowserFrame>
  );
}

/** WS-1a: "Hôm nay đi đâu" — tab nội bộ hiện bản đồ theo dõi thùng ngay trong
 *  dashboard, không nhảy khỏi shell. Bản đồ là nhân vật chính; cạnh phải là
 *  danh sách thùng cần gom theo thứ tự ưu tiên. */
function HomNayPanel() {
  const [bins, setBins] = React.useState<Bin[] | null>(null);
  const [dangChon, setDangChon] = React.useState<Bin | null>(null);
  const [loi, setLoi] = React.useState("");

  // GOI_3 / M3 — quyền giao thùng + danh sách nhân viên để mở BinDetail.
  const { duocPhep, lyDoCam } = useSession();
  const [nhanVien, setNhanVien] = React.useState<NhanVien[] | null>(null);
  const [coQuyenGiao, setCoQuyenGiao] = React.useState(false);
  const [lyDoCamGiao, setLyDoCamGiao] = React.useState("");

  const tai = React.useCallback(() => {
    setLoi("");
    api
      .bins()
      .then((d) => setBins(d.items))
      .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được danh sách thùng."));
  }, []);
  React.useEffect(tai, [tai]);

  // GOI_5 / P5 — khi chọn thùng (từ map hoặc danh sách), cuộn dòng tương ứng
  // trong danh sách vào giữa để map ↔ list đồng bộ.
  React.useEffect(() => {
    if (!dangChon) return;
    const el = document.getElementById(`bin-row-${dangChon.code}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [dangChon]);

  // Kiểm quyền giao thùng MỘT LẦN khi mở màn (mirror dieu-phoi/page.tsx).
  React.useEffect(() => {
    const duoc = duocPhep("assign_bin");
    setCoQuyenGiao(duoc);
    setLyDoCamGiao(lyDoCam("assign_bin"));
    if (!duoc) {
      setNhanVien(null);
      return;
    }
    api
      .nhanVien()
      .then((d) => setNhanVien(d.items))
      .catch(() => setNhanVien(null));
  }, [duocPhep, lyDoCam]);

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (!bins) return <Skeleton className="h-96 w-full" />;

  const canGom = [...bins]
    .filter((b) => b.status === "can_gom" || b.status === "mat_ket_noi")
    .sort((a, b) => b.fill_percent - a.fill_percent);

  return (
    <div key="homnay" className="animate-gbscreen min-h-full">
      <div className="mb-1 flex items-center gap-2.5">
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Hôm nay đi đâu</div>
        <span className="rounded-lg border border-line-3 bg-console-bg px-2.5 py-1 text-xs font-bold text-muted">
          {canGom.length} thùng cần gom
        </span>
      </div>
      <p className="mb-4 text-sm font-semibold text-muted">Bản đồ thùng trong toà — bấm thùng để xem chi tiết.</p>

      <div className="lg:grid lg:grid-cols-[1.5fr_1fr] lg:items-start lg:gap-4">
        <div className="relative mb-4 h-[420px] overflow-hidden rounded-2xl border border-line lg:sticky lg:top-4 lg:mb-0 lg:h-[calc(100vh-9rem)]">
          <BinMap bins={bins} selected={dangChon} onSelect={setDangChon} />
          {dangChon && (
            <BinDetail
              bin={dangChon}
              nhanVien={nhanVien}
              coQuyenGiao={coQuyenGiao}
              lyDoCam={lyDoCamGiao}
              onGanXong={tai}
              onClose={() => setDangChon(null)}
            />
          )}
        </div>

        <div className="space-y-2.5">
          <div className="mb-1 text-xs font-extrabold text-muted">THÙNG CẦN GOM</div>
          {canGom.length === 0 ? (
            <div className="rounded-2xl bg-surface px-4 py-6 text-center text-sm font-bold text-muted">
              Hôm nay không có thùng nào cần gom.
            </div>
          ) : (
            canGom.map((b) => (
              <button
                key={b.code}
                id={`bin-row-${b.code}`}
                type="button"
                onClick={() => setDangChon(b)}
                className={`block w-full cursor-pointer rounded-2xl border bg-surface px-3.5 py-3 text-left transition-all ${
                  dangChon?.code === b.code ? "border-leaf shadow-[var(--shadow-sm)]" : "border-line-3 hover:border-line-2"
                }`}
              >
                <div className="mb-0.5 flex items-center justify-between gap-2">
                  <span className="text-[13px] font-extrabold">{b.code}</span>
                  <span
                    className={`flex-none rounded-lg px-2 py-0.5 text-xs font-extrabold ${
                      b.status === "can_gom" ? "bg-amber-line text-amber-darker" : "bg-muted-bg text-muted"
                    }`}
                  >
                    {b.status === "can_gom" ? `${Math.round(b.fill_percent)}%` : "số liệu cũ"}
                  </span>
                </div>
                <div className="text-[13px] font-semibold text-ink-soft">{b.name}</div>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
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
            className={cn(
              "flex items-center gap-1.5 rounded-2xl px-3.5 py-2 text-xs font-bold transition-all duration-200 ease-[var(--ease-spring)] select-none",
              allowed ? "cursor-pointer active:scale-95" : "cursor-not-allowed text-muted/40",
              dangChon
                ? "bg-ink text-white shadow-[var(--shadow-xs)]"
                : allowed
                ? "bg-transparent text-ink-soft hover:bg-black/5"
                : ""
            )}
          >
            <span>{m.label}</span>
            {!allowed && <IconKhoa className="h-3.5 w-3.5 opacity-60" />}
            {allowed && dem[m.key] ? (
              <span className="rounded-lg bg-hazard px-1.5 py-0.5 text-[10px] font-extrabold text-white shadow-xs">
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
  const btnClass = cn(
    "mb-1 flex w-full items-center rounded-2xl px-3 py-2.5 text-left text-xs font-bold transition-all duration-200 ease-[var(--ease-spring)] select-none",
    allowed ? "cursor-pointer active:scale-[0.98]" : "cursor-not-allowed text-muted/40",
    dangChon
      ? "bg-ink text-white shadow-[var(--shadow-xs)]"
      : allowed
      ? "bg-transparent text-ink-soft hover:bg-black/5 hover:translate-x-0.5"
      : ""
  );

  if (muc.href) {
    return (
      <Link
        href={muc.href}
        aria-disabled={!allowed}
        title={allowed ? undefined : reason}
        onClick={(e) => {
          if (!allowed) e.preventDefault();
        }}
        className={btnClass}
      >
        <span>{muc.label}</span>
        <span className="flex-1" />
        {!allowed && <IconKhoa className="h-3.5 w-3.5 opacity-60" />}
      </Link>
    );
  }

  return (
    <button
      onClick={() => allowed && setNav(muc.key)}
      disabled={!allowed}
      title={allowed ? undefined : reason}
      className={btnClass}
    >
      <span>{muc.label}</span>
      <span className="flex-1" />
      {!allowed && <IconKhoa className="h-3.5 w-3.5 opacity-60" />}
      {allowed && badge ? (
        <span className="rounded-lg bg-hazard px-2 py-0.5 text-xs font-extrabold text-white shadow-xs">{badge}</span>
      ) : null}
    </button>
  );
}
