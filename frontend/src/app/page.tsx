"use client";

/** Vỏ ứng dụng: chọn "bộ mặt" theo vai trò.
 *
 * Cư dân và đội vệ sinh dùng khung điện thoại; ban quản lý dùng console
 * desktop. Cả hai chung một bảng màu, một bộ chữ — phải nhìn ra là cùng một
 * sản phẩm, nhưng mật độ thông tin và bối cảnh sử dụng khác hẳn nhau.
 */

import * as React from "react";

import { CleanerHistoryScreen, CleanerMeScreen, RouteTodayScreen, VerifyLabelScreen } from "@/components/cleaner/screens";
import { ManagerConsole } from "@/components/manager/console";
import { AskScreen, BUOC_MAC_DINH, ProcessingScreen, buocTuKetQua } from "@/components/resident/ask";
import { NearbyBinsScreen } from "@/components/resident/nearby-bins";
import { LoginScreen, OnboardingScreen } from "@/components/resident/onboarding";
import {
  MeScreen,
  PrivacyScreen,
  RequestDetailScreen,
  RequestsScreen,
  ScheduleScreen,
} from "@/components/resident/personal";
import { PickupWizard } from "@/components/resident/pickup-wizard";
import { HazardResultScreen, ResultScreen, UnsureScreen } from "@/components/resident/result";
import { Button, ErrorState, Skeleton } from "@/components/ui/primitives";
import { PhoneFrame, TabBar, type TabItem } from "@/components/ui/shell";
import { api, ApiError } from "@/lib/api";
import { IconManHinhRong } from "@/lib/icons";
import { laAppNative } from "@/lib/platform";
import { SessionProvider, useSession } from "@/lib/session";
import type { Classification } from "@/lib/types";

export default function Page() {
  return (
    <SessionProvider>
      <main className="min-h-dvh w-full">
        <AppShell />
      </main>
    </SessionProvider>
  );
}

function AppShell() {
  const { user, loading } = useSession();
  const [daBatDau, setDaBatDau] = React.useState(false);

  if (loading) return <Skeleton className="h-dvh w-full" />;

  if (!user) {
    return (
      <PhoneFrame>
        {daBatDau ? <LoginScreen /> : <OnboardingScreen onNext={() => setDaBatDau(true)} />}
      </PhoneFrame>
    );
  }

  if (user.role === "manager") return laAppNative() ? <ManagerTrenAppScreen /> : <ManagerConsole />;
  if (user.role === "cleaner") return <CleanerApp />;
  return <ResidentApp />;
}

/** Ban quản lý mở app cài trên điện thoại.
 *
 * Console đơn vị thu gom là bảng nhiều cột, mật độ thông tin cao, thiết kế cho màn
 * hình rộng (`FRONTEND_SPEC.md` mục 2.1). Nhồi nó vào màn 6 inch thì vừa khó
 * dùng vừa dễ bấm nhầm nút duyệt — nên nói thẳng và chỉ sang web.
 */
function ManagerTrenAppScreen() {
  const { user, dangXuat } = useSession();
  // Địa chỉ web của frontend, không phải của API — đặt lúc build cùng lượt với
  // NEXT_PUBLIC_API_URL. Chưa đặt thì thà bỏ trống còn hơn chỉ sai chỗ.
  const linkWeb = (process.env.NEXT_PUBLIC_WEB_URL ?? "").replace(/\/+$/, "");

  return (
    <PhoneFrame>
      <div className="flex min-h-full flex-col items-center justify-center bg-cream px-7 pb-10 pt-14 text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-[20px] bg-[#ece7f6] text-bulky-dark">
          <IconManHinhRong className="h-7 w-7" strokeWidth={1.8} />
        </div>
        <h1 className="mb-2.5 font-[family-name:var(--font-display)] text-[26px] font-bold leading-tight">
          Console đơn vị thu gom dùng trên máy tính
        </h1>
        <p className="mb-1.5 text-[15px] font-semibold leading-snug text-[#5a6b5f]">
          Chào {user!.full_name}. Hàng đợi duyệt và trang vận hành có nhiều cột số liệu, xem trên màn
          hình rộng mới đủ chỗ.
        </p>
        <p className="mb-6 text-[13px] font-semibold leading-snug text-muted">
          Mở địa chỉ web của hệ thống trên máy tính và đăng nhập bằng đúng tài khoản này.
        </p>

        {linkWeb && (
          <div className="mb-6 w-full break-all rounded-2xl border-[1.5px] border-line-2 bg-white px-4 py-3.5 font-mono text-[13px] font-semibold">
            {linkWeb}
          </div>
        )}

        <Button block variant="danger" onClick={dangXuat}>
          Đăng xuất
        </Button>
        <p className="mt-4 text-[11px] font-semibold leading-relaxed text-[#9aa39a]">
          App trên điện thoại dành cho cư dân và đội vệ sinh.
        </p>
      </div>
    </PhoneFrame>
  );
}

// --- App cư dân ----------------------------------------------------------

type ManCuDan =
  | "ask"
  | "diem"
  | "processing"
  | "result"
  | "privacy"
  | "pickup"
  | "requests"
  | "requestDetail"
  | "schedule"
  | "me";

const ICON = {
  ask: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 8a2 2 0 0 1 2-2h1l1.2-2h5.6L16 6h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z" transform="translate(1 0)" />
      <circle cx="12" cy="13" r="3.2" />
    </svg>
  ),
  diem: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 21s-6.5-5.6-6.5-10a6.5 6.5 0 1 1 13 0c0 4.4-6.5 10-6.5 10z" />
      <circle cx="12" cy="11" r="2.2" />
    </svg>
  ),
  lich: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="5" width="18" height="16" rx="2.5" />
      <path d="M3 9h18M8 3v4M16 3v4" />
    </svg>
  ),
  yeuCau: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 4h14v16l-7-3-7 3z" />
    </svg>
  ),
  toi: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4 3.6-7 8-7s8 3 8 7" />
    </svg>
  ),
  tuyen: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 12h13l3 4h2v3h-2M3 7h9v9H3z" />
      <circle cx="7" cy="19" r="1.6" />
      <circle cx="17" cy="19" r="1.6" />
    </svg>
  ),
  xacNhan: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 12l2 2 4-4" />
      <circle cx="12" cy="12" r="9" />
    </svg>
  ),
  lichSu: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 8v4l3 2" />
      <circle cx="12" cy="12" r="9" />
    </svg>
  ),
};

function ResidentApp() {
  const { user, dangXuat } = useSession();
  const [man, setMan] = React.useState<ManCuDan>("ask");
  const [ketQua, setKetQua] = React.useState<Classification | null>(null);
  const [buocXuLy, setBuocXuLy] = React.useState(0);
  const [cacBuoc, setCacBuoc] = React.useState(BUOC_MAC_DINH);
  const [loi, setLoi] = React.useState<{ message: string; code: string } | null>(null);
  const [yeuCauId, setYeuCauId] = React.useState<number | null>(null);
  // Nguồn mở PickupWizard: "result" (sau khi phân loại) hay "requests" (nút + ở tab Yêu cầu).
  // Khác nguồn thì nút Quay lại phải về đúng chỗ, không về nhầm màn phân loại.
  const [nguonPickup, setNguonPickup] = React.useState<"result" | "requests">("result");
  const huyRef = React.useRef(false);

  async function chay(goi: () => Promise<Classification>, coAnh: boolean) {
    huyRef.current = false;
    setLoi(null);
    setBuocXuLy(0);
    setCacBuoc(BUOC_MAC_DINH);
    setMan("processing");

    // Tiến trình chạy song song với request thật: mỗi bước tích dần để người
    // dùng thấy quyền riêng tư được xử lý trước khi ảnh tới model.
    const nhip = setInterval(() => setBuocXuLy((b) => Math.min(b + 1, coAnh ? 3 : 4)), 620);
    try {
      const kq = await goi();
      if (huyRef.current) return;
      if (kq.media_id) {
        try {
          const privacy = await api.privacy(kq.media_id);
          setCacBuoc(buocTuKetQua(kq, privacy));
        } catch {
          setCacBuoc(buocTuKetQua(kq));
        }
      }
      setBuocXuLy(5);
      setKetQua(kq);
      setTimeout(() => !huyRef.current && setMan("result"), 500);
    } catch (e) {
      if (huyRef.current) return;
      setLoi({
        message: e instanceof ApiError ? e.message : "Có lỗi khi phân loại.",
        code: e instanceof ApiError ? e.code : "APP-500",
      });
      setMan("ask");
    } finally {
      clearInterval(nhip);
    }
  }

  const tabs: TabItem[] = [
    { key: "ask", label: "Hỏi", icon: ICON.ask },
    { key: "diem", label: "Điểm gửi", icon: ICON.diem },
    { key: "schedule", label: "Lịch", icon: ICON.lich },
    { key: "requests", label: "Yêu cầu", icon: ICON.yeuCau },
    { key: "me", label: "Tôi", icon: ICON.toi },
  ];
  const hienTabBar = ["ask", "diem", "schedule", "requests", "me"].includes(man);

  const nenMan =
    man === "processing"
      ? "#0c0f0c"
      : man === "result" && ketQua?.refused
        ? "#eef1f5"
        : man === "result" && ketQua?.category?.is_hazardous
          ? "#fbeadf"
          : "#f4f1ea";

  return (
    <PhoneFrame
      bg={nenMan}
      statusDark={man === "processing"}
      tabBar={hienTabBar ? <TabBar items={tabs} active={man} onChange={(k) => setMan(k as ManCuDan)} /> : undefined}
    >
      {loi && man === "ask" && (
        <div className="px-4 pt-14">
          <ErrorState message={loi.message} code={loi.code} onRetry={() => setLoi(null)} />
        </div>
      )}

      {man === "ask" && (
        <AskScreen
          unit={user!.unit}
          onAskText={(q) => chay(() => api.classifyText(q, user!.building_id), false)}
          onPickImage={(f) => chay(() => api.classifyImage(f, user!.building_id), true)}
        />
      )}

      {man === "processing" && (
        <ProcessingScreen
          buoc={buocXuLy}
          cacBuoc={cacBuoc}
          onCancel={() => {
            huyRef.current = true;
            setMan("ask");
          }}
        />
      )}

      {man === "result" && ketQua && (
        ketQua.refused ? (
          <UnsureScreen
            ketQua={ketQua}
            onBack={() => setMan("ask")}
            onRetake={() => setMan("ask")}
            onAskManager={() => api.feedback(ketQua.classification_id, false).catch(() => undefined)}
          />
        ) : ketQua.category?.is_hazardous ? (
          <HazardResultScreen ketQua={ketQua} onBack={() => setMan("ask")} onPickup={() => { setNguonPickup("result"); setMan("pickup"); }} />
        ) : (
          <ResultScreen
            ketQua={ketQua}
            onBack={() => setMan("ask")}
            onPrivacy={() => setMan("privacy")}
            onPickup={() => { setNguonPickup("result"); setMan("pickup"); }}
            onFeedback={(ok) => api.feedback(ketQua.classification_id, ok).catch(() => undefined)}
          />
        )
      )}

      {man === "privacy" && ketQua?.media_id && (
        <PrivacyScreen mediaId={ketQua.media_id} onBack={() => setMan(ketQua ? "result" : "ask")} />
      )}

      {man === "pickup" && (
        <PickupWizard
          goiYTuKetQua={nguonPickup === "result" ? ketQua : null}
          scheduleHint={nguonPickup === "result" ? ketQua?.schedule_hint : undefined}
          onBack={() => setMan(nguonPickup === "result" ? (ketQua ? "result" : "ask") : "requests")}
          onDone={() => setMan("requests")}
        />
      )}

      {man === "requests" && (
        <RequestsScreen
          onOpen={(id) => {
            setYeuCauId(id);
            setMan("requestDetail");
          }}
          onCreate={() => {
            setNguonPickup("requests");
            setMan("pickup");
          }}
        />
      )}

      {man === "requestDetail" && yeuCauId && (
        <RequestDetailScreen id={yeuCauId} onBack={() => setMan("requests")} />
      )}

      {man === "schedule" && <ScheduleScreen buildingId={user!.building_id} buildingName={user!.building} />}

      {man === "diem" && <NearbyBinsScreen />}

      {man === "me" && (
        <MeScreen
          user={user!}
          onPrivacy={() => (ketQua?.media_id ? setMan("privacy") : setMan("ask"))}
          onLogout={dangXuat}
        />
      )}
    </PhoneFrame>
  );
}

// --- App đội vệ sinh -----------------------------------------------------

function CleanerApp() {
  const { user, dangXuat } = useSession();
  const [man, setMan] = React.useState("route");

  const tabs: TabItem[] = [
    { key: "route", label: "Tuyến", icon: ICON.tuyen },
    { key: "verify", label: "Xác nhận", icon: ICON.xacNhan },
    { key: "history", label: "Lịch sử", icon: ICON.lichSu },
    { key: "me", label: "Tôi", icon: ICON.toi },
  ];

  return (
    <PhoneFrame
      bg="#eef2f6"
      tabBar={<TabBar items={tabs} active={man} onChange={setMan} accent="#2f7fe0" />}
    >
      {man === "route" && <RouteTodayScreen onXemLichSu={() => setMan("history")} />}
      {man === "verify" && <VerifyLabelScreen />}
      {man === "history" && <CleanerHistoryScreen />}
      {man === "me" && <CleanerMeScreen user={user!} onLogout={dangXuat} />}
    </PhoneFrame>
  );
}
