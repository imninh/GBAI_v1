"use client";

/** Màn Điều phối thùng thu gom — dành cho đội vệ sinh và ban quản lý.
 *
 *  Thiết kế dựng bằng Lovable rồi mang về; phần bố cục và 6 component trong
 *  `components/bins/` giữ nguyên bản thiết kế. Chỗ khác bản gốc là **nguồn dữ
 *  liệu**: bản thiết kế chạy trên dữ liệu mẫu cắm cứng, còn ở đây gọi thẳng
 *  `GET /bins` và `GET /bins/stats`.
 */

import dynamic from "next/dynamic";
import Link from "next/link";
import * as React from "react";
import { AlertCircle, ArrowLeft, PackagePlus, PartyPopper, RefreshCw, Trash2 } from "lucide-react";

import { ActionPanel } from "@/components/bins/action-panel";
import { BinDetail } from "@/components/bins/bin-detail";
import { BinListSkeleton, BinRow } from "@/components/bins/bin-row";
import { StatCards } from "@/components/bins/stat-cards";
import { Button, Skeleton } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { computeStats, sortForCollection, type Bin, type BinStats, type NhanVien } from "@/lib/bins";

// Leaflet chạm thẳng vào `window` nên không dựng được lúc build tĩnh. `ssr:false`
// đẩy nó xuống trình duyệt — bắt buộc vì dự án build bằng `output: "export"`.
const BinMap = dynamic(() => import("@/components/bins/bin-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

/** Nhịp gọi lại API khi bật theo dõi trực tiếp. 3 giây đủ để thấy số đổi mà
 *  không nện máy chủ free tier của Render. */
const NHIP_LAM_MOI_GIAY = 3;

export default function DieuPhoiPage() {
  const [bins, setBins] = React.useState<Bin[] | null>(null);
  const [stats, setStats] = React.useState<BinStats | undefined>(undefined);
  const [dangTai, setDangTai] = React.useState(true);
  const [dangLamMoi, setDangLamMoi] = React.useState(false);
  const [loi, setLoi] = React.useState<{ message: string; code: string; status: number } | null>(null);

  const [chiCanGom, setChiCanGom] = React.useState(false);
  const [maDangChon, setMaDangChon] = React.useState<string | null>(null);
  const [theoDoi, setTheoDoi] = React.useState(false);
  const [soLanLamMoi, setSoLanLamMoi] = React.useState(0);

  const [nhanVien, setNhanVien] = React.useState<NhanVien[] | null>(null);
  const [coQuyenGiao, setCoQuyenGiao] = React.useState(false);
  const [lyDoCamGiao, setLyDoCamGiao] = React.useState("");

  const tai = React.useCallback(async (lanDau: boolean) => {
    if (lanDau) setDangTai(true);
    else setDangLamMoi(true);
    try {
      // Gọi song song: hai endpoint độc lập nhau, không việc gì phải chờ nối tiếp.
      const [dsThung, soLieu] = await Promise.all([api.bins(), api.binStats()]);
      setBins(dsThung.items);
      setStats(soLieu);
      setLoi(null);
    } catch (exc) {
      if (exc instanceof ApiError) setLoi({ message: exc.message, code: exc.code, status: exc.status });
      else setLoi({ message: "Có lỗi không xác định khi tải danh sách thùng.", code: "UNKNOWN", status: 0 });
    } finally {
      setDangTai(false);
      setDangLamMoi(false);
    }
  }, []);

  React.useEffect(() => {
    void tai(true);
  }, [tai]);

  // Quyền giao thùng và danh sách nhân viên: tải MỘT LẦN lúc mở màn, KHÔNG theo
  // nhịp làm mới 3 giây — hai thứ này gần như không đổi trong một ca làm việc,
  // mà `GET /bins/nhan-vien` lại đếm thùng nên không phải truy vấn rẻ.
  //
  // Kiểm quyền TRƯỚC rồi mới gọi: vai không có `assign_bin` nhận 403, và dùng
  // lỗi 403 làm luồng bình thường thì log đầy lỗi giả.
  React.useEffect(() => {
    let huy = false;
    api
      .me()
      .then(async (phien) => {
        if (huy) return;
        const duoc = phien.permissions.assign_bin?.allowed ?? false;
        setCoQuyenGiao(duoc);
        setLyDoCamGiao(phien.permissions.assign_bin?.reason ?? "");
        if (!duoc) return;
        const ds = await api.nhanVien();
        if (!huy) setNhanVien(ds.items);
      })
      .catch(() => {
        /* Không lấy được quyền thì coi như không có: ô giao thùng hiện mờ, phần
           còn lại của màn hình vẫn dùng bình thường. */
      });
    return () => {
      huy = true;
    };
  }, []);

  // Theo dõi trực tiếp: gọi lại API theo nhịp. Số liệu chỉ đổi khi có thiết bị
  // thật — hoặc `python scripts/device_simulator.py` — đang bơm dữ liệu vào.
  // Màn hình này không bao giờ tự bịa số.
  React.useEffect(() => {
    if (!theoDoi) return;
    const id = setInterval(() => {
      setSoLanLamMoi((n) => n + 1);
      void tai(false);
    }, NHIP_LAM_MOI_GIAY * 1000);
    return () => clearInterval(id);
  }, [theoDoi, tai]);

  const hienThi = React.useMemo(() => {
    if (!bins) return [];
    const loc = chiCanGom ? bins.filter((b) => b.status === "can_gom") : bins;
    return sortForCollection(loc);
  }, [bins, chiCanGom]);

  // Khi đang lọc, bốn thẻ số phải nói về đúng tập đang nhìn thấy.
  const soLieuHienThi = chiCanGom && bins ? computeStats(hienThi) : stats;
  const dangChon = hienThi.find((b) => b.code === maDangChon) ?? null;

  if (loi && loi.status === 401)
    return <ManChan tieuDe="Bạn cần đăng nhập" moTa={loi.message} coGioiThieuDemo />;
  if (loi && loi.status === 403)
    return <ManChan tieuDe="Tài khoản này không có quyền" moTa={loi.message} />;

  return (
    <div className="flex h-dvh flex-col bg-background">
      <header className="flex items-center justify-between gap-3 border-b bg-card px-4 py-3 sm:px-5">
        <div className="flex min-w-0 items-center gap-2.5">
          {/* Trang này mở từ mục "Hôm nay đi đâu" của console. Không có đường
              quay lại thì người dùng kẹt ở đây, phải sửa URL hoặc bấm nút back
              của trình duyệt — với người ít kinh nghiệm công nghệ là ngõ cụt. */}
          <Button asChild variant="outline" size="sm" aria-label="Quay lại màn hình chính">
            <Link href="/">
              <ArrowLeft />
              <span className="hidden sm:inline">Quay lại</span>
            </Link>
          </Button>
          <span className="hidden size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground sm:flex">
            <Trash2 className="size-4" />
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold leading-tight">Điều phối thùng thu gom</h1>
            <p className="truncate text-xs text-muted-foreground">Quận Hoàn Kiếm · ca sáng</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={() => void tai(false)} disabled={dangLamMoi}>
          <RefreshCw className={dangLamMoi ? "animate-spin" : undefined} />
          <span className="hidden sm:inline">Làm mới</span>
        </Button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Trên điện thoại thanh bên nằm TRÊN bản đồ và bị giới hạn chiều cao.
            Đo ở 390px với bố cục cũ: thanh bên ăn 380px, bản đồ còn đúng 10px. */}
        <aside className="flex max-h-[42vh] w-full shrink-0 flex-col gap-4 overflow-y-auto border-b bg-sidebar p-4 lg:max-h-none lg:w-[380px] lg:border-b-0 lg:border-r">
          <StatCards stats={soLieuHienThi} loading={dangTai} />

          <ActionPanel
            running={theoDoi}
            step={soLanLamMoi}
            intervalSeconds={NHIP_LAM_MOI_GIAY}
            onToggle={() => setTheoDoi((v) => !v)}
          />

          <div className="flex items-center justify-between border-t pt-3">
            <h2 className="text-sm font-semibold">Danh sách thùng</h2>
            <button
              type="button"
              role="switch"
              aria-checked={chiCanGom}
              onClick={() => setChiCanGom((v) => !v)}
              className="flex items-center gap-2 text-xs text-muted-foreground"
            >
              Chỉ cần gom
              <span
                className={`relative h-5 w-9 rounded-full transition-colors ${chiCanGom ? "bg-primary" : "bg-muted-bg"}`}
              >
                <span
                  className={`absolute top-0.5 size-4 rounded-full bg-card shadow transition-all ${
                    chiCanGom ? "left-[1.125rem]" : "left-0.5"
                  }`}
                />
              </span>
            </button>
          </div>

          {dangTai ? (
            <BinListSkeleton />
          ) : loi ? (
            <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-center">
              <AlertCircle className="mx-auto size-5 text-destructive" />
              <p className="mt-2 text-sm">{loi.message}</p>
              <p className="mt-1 text-xs text-muted-foreground">Mã lỗi: {loi.code}</p>
              <Button size="sm" className="mt-3" onClick={() => void tai(true)}>
                Thử lại
              </Button>
            </div>
          ) : hienThi.length === 0 ? (
            chiCanGom ? (
              <div className="rounded-xl border border-ok/30 bg-ok-soft p-5 text-center">
                <PartyPopper className="mx-auto size-5 text-ok" />
                <p className="mt-2 text-sm font-medium">Không thùng nào cần gom lúc này</p>
                <p className="mt-1 text-xs text-muted-foreground">Cả tuyến đang ổn. Cứ tiếp tục theo dõi.</p>
              </div>
            ) : (
              <div className="rounded-xl border border-dashed p-5 text-center">
                <PackagePlus className="mx-auto size-5 text-muted-foreground" />
                <p className="mt-2 text-sm">Chưa có thùng nào được đăng ký</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Chạy <code>python scripts/seed.py --reset --demo</code> để nạp 10 thùng mẫu.
                </p>
              </div>
            )
          ) : (
            <div className="space-y-2.5 pb-2">
              {hienThi.map((bin) => (
                <BinRow
                  key={bin.code}
                  bin={bin}
                  active={bin.code === maDangChon}
                  onSelect={(b) => setMaDangChon(b.code)}
                />
              ))}
            </div>
          )}
        </aside>

        <main className="relative min-h-[58vh] min-w-0 flex-1 lg:min-h-0">
          <BinMap bins={hienThi} selected={dangChon} onSelect={(b) => setMaDangChon(b.code)} />
          {dangChon && (
            <BinDetail
              bin={dangChon}
              nhanVien={nhanVien}
              coQuyenGiao={coQuyenGiao}
              lyDoCam={lyDoCamGiao}
              onGanXong={() => void tai(false)}
              onClose={() => setMaDangChon(null)}
            />
          )}
        </main>
      </div>
    </div>
  );
}

/** Màn chặn khi chưa đăng nhập hoặc sai vai trò — không để người dùng nhìn một
 *  bản đồ trống mà không hiểu vì sao. */
function ManChan({
  tieuDe,
  moTa,
  coGioiThieuDemo = false,
}: {
  tieuDe: string;
  moTa: string;
  coGioiThieuDemo?: boolean;
}) {
  return (
    <div className="flex h-screen items-center justify-center bg-background p-6">
      <div className="max-w-sm rounded-2xl border bg-card p-6 text-center">
        <AlertCircle className="mx-auto size-6 text-destructive" />
        <h1 className="mt-3 text-base font-semibold">{tieuDe}</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">{moTa}</p>
        <p className="mt-1.5 text-xs text-muted-foreground">
          Màn này dành cho đội vệ sinh và ban quản lý.
        </p>
        {coGioiThieuDemo && (
          <p className="mt-3 rounded-lg bg-muted/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
            Ở màn đăng nhập có sẵn ba tài khoản demo — bấm vào là vào thẳng.
          </p>
        )}
        <Button asChild size="sm" className="mt-4">
          <Link href="/">Về trang đăng nhập</Link>
        </Button>
      </div>
    </div>
  );
}
