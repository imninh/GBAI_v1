"use client";

/** Vỏ ứng dụng: chọn "bộ mặt" theo vai trò.
 *
 * Cư dân và đội vệ sinh dùng khung điện thoại; ban quản lý dùng console
 * desktop. Cả hai chung một bảng màu, một bộ chữ — phải nhìn ra là cùng một
 * sản phẩm, nhưng mật độ thông tin và bối cảnh sử dụng khác hẳn nhau.
 */

import * as React from "react";

import { CleanerHistoryScreen, CleanerMeScreen, RouteTodayScreen } from "@/components/cleaner/screens";
import { ManagerConsole } from "@/components/manager/console";
import { AskScreen, BUOC_MAC_DINH, ProcessingScreen, buocTuKetQua } from "@/components/resident/ask";
import { NearbyBinsScreen } from "@/components/resident/nearby-bins";
import { ChatbotModal } from "@/components/resident/ChatbotModal";
import { LoginScreen, OnboardingScreen, Mascot } from "@/components/resident/onboarding";
import {
  DiemXanhScreen,
  MeScreen,
  PrivacyScreen,
  RequestDetailScreen,
  RequestsScreen,
  ScheduleScreen,
} from "@/components/resident/personal";
import { PickupWizard } from "@/components/resident/pickup-wizard";
import { HazardResultScreen, ResultScreen, UnsureScreen } from "@/components/resident/result";
import { ScanScreen } from "@/components/resident/scan";
import { Button, ErrorState, Skeleton } from "@/components/ui/primitives";
import { PhoneFrame, TabBar, type TabItem } from "@/components/ui/shell";
import { api, ApiError } from "@/lib/api";
import { ghiHoatDong } from "@/lib/gamification";
import { IconManHinhRong, IconXeThuGom } from "@/lib/icons";
import { laAppNative } from "@/lib/platform";
import { SessionProvider, useSession } from "@/lib/session";
import type { Classification } from "@/lib/types";

export default function Page() {
  return (
    <SessionProvider>
      <main className="min-h-dvh w-full" suppressHydrationWarning>
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
  | "scan"
  | "processing"
  | "result"
  | "privacy"
  | "pickup"
  | "requests"
  | "requestDetail"
  | "schedule"
  | "diemxanh"
  | "me";

const ICON = {
  home: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />
    </svg>
  ),
  scan: (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z" />
      <circle cx="12" cy="13" r="3.5" />
    </svg>
  ),
  diem: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 21s-6.5-5.6-6.5-10a6.5 6.5 0 1 1 13 0c0 4.4-6.5 10-6.5 10z" />
      <circle cx="12" cy="11" r="2.2" />
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
  // Nút Chụp nổi giữa ở tab bar: đếm số lần người dùng chạm để AskScreen tự mở
  // camera. Đang ở tab khác vẫn bấm được — lần chạm tiếp theo mở thẳng camera.
  const [lanChup, setLanChup] = React.useState(0);
  // Overlay chúc mừng sau khi phân loại ĐÚNG món thường (không refused, không
  // nguy hại). Không cộng điểm giả — chỉ ăn mừng việc phân loại đúng.
  const [chucMung, setChucMung] = React.useState(false);
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
      // Streak đếm hoạt động phân loại THÀNH CÔNG thật (lưu ngày hôm nay).
      if (!kq.refused) ghiHoatDong();
      setTimeout(() => {
        if (huyRef.current) return;
        setMan("result");
        // Chỉ ăn mừng khi kết quả là món THƯỜNG và không bị từ chối.
        if (!kq.refused && !kq.category?.is_hazardous) setChucMung(true);
      }, 500);
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
    { key: "ask", label: "Trang chủ", icon: ICON.home },
    { key: "diem", label: "Điểm gửi", icon: ICON.diem },
    { key: "scan", label: "Chụp", icon: ICON.scan, raised: true },
    { key: "requests", label: "Yêu cầu", icon: ICON.yeuCau },
    { key: "me", label: "Tôi", icon: ICON.toi },
  ];
  // Lịch thu gom không còn là tab riêng: vào từ thẻ lịch trên Trang chủ hoặc nút
  // trong tab Yêu cầu. Khi ở màn con (schedule, kết quả…) thì ẩn tab bar.
  const hienTabBar = ["ask", "diem", "scan", "requests", "me"].includes(man);
  const nenMan =
    man === "processing"
      ? "#0c0f0c"
      : man === "result" && ketQua?.refused
        ? "#eef1f5"
        : man === "result" && ketQua?.category?.is_hazardous
          ? "#fbeadf"
          : "#f4f1ea";

  return (
    <>
      <PhoneFrame
        bg={nenMan}
        statusDark={man === "processing"}
        tabBar={
          hienTabBar ? (
            <TabBar
              items={tabs}
              active={man}
              onChange={(k) => {
                // Nút Chụp nổi giờ mở màn Chụp & quét (scan.tsx) — hai lối vào:
                // quét mã thùng và chụp phân loại. Đường chụp cũ vẫn nguyên vẹn:
                // nút "Chụp để phân loại" trong đó quay về Trang chủ và nhờ
                // AskScreen mở camera qua `lanChup` như trước.
                setMan(k as ManCuDan);
              }}
            />
        ) : undefined
      }
    >
      {loi && man === "ask" && (
        <div className="px-4 pt-14">
          <ErrorState message={loi.message} code={loi.code} onRetry={() => setLoi(null)} />
        </div>
      )}

      {man === "ask" && (
        <>
          <AskScreen
            unit={user!.unit}
            lanChup={lanChup}
            onXemLich={() => setMan("schedule")}
            onAskText={(q) => chay(() => api.classifyText(q, user!.building_id), false)}
            onPickImage={(f) => chay(() => api.classifyImage(f, user!.building_id), true)}
          />
          {/* Lối vào nhanh wizard ở màn chính (phát hiện A-02): wizard nằm sâu
              trong tab Yêu cầu nên người mới tưởng app chỉ có chụp ảnh. Đây chỉ
              là chỗ đặt lối vào — không thay đường cũ, không đổi luồng wizard. */}
          <button
            type="button"
            onClick={() => {
              setNguonPickup("requests");
              setMan("pickup");
            }}
            aria-label="Đặt lịch thu gom đồ cồng kềnh"
            className="fixed bottom-[calc(84px+env(safe-area-inset-bottom)+12px)] left-[max(14px,calc((100vw_-_560px)/2_+_14px))] z-40 flex cursor-pointer items-center gap-2 rounded-full border-[1.5px] border-[#d9cef0] bg-white py-2 pl-2.5 pr-4 shadow-[0_12px_28px_-14px_rgba(106,77,196,.75)]"
          >
            <span className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-bulky-soft text-bulky-dark">
              <IconXeThuGom className="h-4 w-4" />
            </span>
            <span className="text-[13px] font-extrabold text-bulky-dark">
              Đặt lịch thu gom đồ cồng kềnh
            </span>
          </button>
        </>
      )}

      {man === "scan" && (
        <ScanScreen
          onChup={() => {
            setMan("ask");
            setLanChup((n) => n + 1);
          }}
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

      {man === "schedule" && (
        <ScheduleScreen buildingId={user!.building_id} buildingName={user!.building} onBack={() => setMan("ask")} />
      )}

      {man === "diem" && <NearbyBinsScreen />}

      {man === "diemxanh" && <DiemXanhScreen user={user!} onBack={() => setMan("me")} />}

      {man === "me" && (
        <MeScreen
          user={user!}
          onPrivacy={() => (ketQua?.media_id ? setMan("privacy") : setMan("ask"))}
          onLogout={dangXuat}
          onDiemXanh={() => setMan("diemxanh")}
        />
      )}

      {/* Trợ lý AI Chatbot nổi */}
      <ChatbotModal
        buildingId={user?.building_id}
        userLat={user?.building_lat}
        userLng={user?.building_lng}
      />
    </PhoneFrame>

    {/* Overlay chúc mừng sau phân loại đúng — Mun nhảy, người dùng bấm để đóng.
        Nằm ngoài PhoneFrame để phủ toàn màn hình thiết bị. */}
    {chucMung && (
      <div
        onClick={() => setChucMung(false)}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-8 backdrop-blur-[3px]"
        role="dialog"
        aria-modal="true"
        aria-label="Phân loại thành công"
      >
        <div className="animate-gbpop relative w-full max-w-[300px] rounded-[30px] bg-white p-7 pb-6 text-center shadow-[0_30px_60px_-22px_rgba(0,0,0,.35)]">
          <Mascot size={120} tuThe="hello" className="mx-auto -mt-16 mb-2 animate-gbwave" />
          <div className="font-[family-name:var(--font-display)] text-[26px] font-bold text-leaf-dark">Tuyệt vời!</div>
          <div className="mt-1.5 text-[14px] font-semibold text-ink-soft">Bạn vừa phân loại đúng một món rác</div>
          <Button block className="mt-5" onClick={() => setChucMung(false)}>
            Tiếp tục
          </Button>
        </div>
      </div>
      )}
    </>
  );
}

// --- App đội vệ sinh -----------------------------------------------------

function CleanerApp() {
  const { user, dangXuat } = useSession();
  const [man, setMan] = React.useState("route");

  const tabs: TabItem[] = [
    { key: "route", label: "Tuyến", icon: ICON.tuyen },
    { key: "history", label: "Lịch sử", icon: ICON.lichSu },
    { key: "me", label: "Tôi", icon: ICON.toi },
  ];

  return (
    <PhoneFrame
      bg="#eef2f6"
      tabBar={<TabBar items={tabs} active={man} onChange={setMan} accent="#2f7fe0" />}
    >
      {man === "route" && <RouteTodayScreen onXemLichSu={() => setMan("history")} />}
      {man === "history" && <CleanerHistoryScreen />}
      {man === "me" && <CleanerMeScreen user={user!} onLogout={dangXuat} />}
    </PhoneFrame>
  );
}
