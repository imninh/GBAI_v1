"use client";

/** Màn Chụp & quét — Tích hợp Quét QR thật & Mở phiên bỏ rác Realtime BOTOL™ (P63/P64).
 *
 *  1. **"Quét mã thùng rác"** — mở khung quét QR kiểu iPhone: lớp phủ tối khoét
 *     ô bo góc ở giữa, bốn dấu góc, vạch sáng chạy lên xuống. Mã QR được đọc ngay
 *     trên luồng `getUserMedia` bằng **jsQR** — thư viện JS thuần.
 *
 *  2. **"Mở phiên bỏ rác"** — gọi `POST /phien/bat-dau` với `maThung` vừa quét.
 *     Màn hình chuyển sang giao diện theo dõi trực tiếp phiên bỏ rác:
 *     - Tự động lắng nghe `so_vat` và `diem_nhan_thuc` nhảy số realtime khi rác được bỏ vào thùng 3D.
 *     - Nút "Hoàn tất & Chốt phiên" gọi `POST /phien/{ma_phien}/dong` để tính điểm và chốt giao dịch.
 *
 *  3. **"Chụp để phân loại"** — chuyển sang màn Trang chủ và mở camera qua `onChup`.
 */

import * as React from "react";

import { Button, Card } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";

import jsQR from "jsqr";

type TrangThai = "chon" | "quet" | "ket-qua" | "dang-bo" | "da-chot";

interface PhienThungInfo {
  ma_phien: string;
  trang_thai: string;
  so_vat: number;
  diem_nhan_thuc: number;
  bat_dau: string;
  ket_thuc: string | null;
}

/** Quét một khung video rồi tự lên lịch khung tiếp theo; đọc được mã thì dừng. */
function quetKhung(
  demRef: { current: number },
  video: HTMLVideoElement | null,
  canvas: HTMLCanvasElement | null,
  nhanMa: (ma: string) => void,
): number | null {
  if (!video || !canvas) return null;
  if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || video.videoWidth === 0) {
    return window.requestAnimationFrame(() => quetKhung(demRef, video, canvas, nhanMa));
  }
  demRef.current += 1;
  if (demRef.current % 3 !== 0) {
    return window.requestAnimationFrame(() => quetKhung(demRef, video, canvas, nhanMa));
  }
  const w = video.videoWidth;
  const h = video.videoHeight;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(video, 0, 0, w, h);
  let code: ReturnType<typeof jsQR> = null;
  try {
    const imageData = ctx.getImageData(0, 0, w, h);
    code = jsQR(imageData.data, w, h, { inversionAttempts: "dontInvert" });
  } catch {
    // Khung đang đổi kích thước giữa chừng — bỏ qua lượt này.
  }
  if (code && code.data) {
    nhanMa(code.data.trim());
    return null;
  }
  return window.requestAnimationFrame(() => quetKhung(demRef, video, canvas, nhanMa));
}

/** Icon khung quét QR */
function IconQuet({ className }: { className?: string }) {
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M4 8V6a2 2 0 0 1 2-2h2" />
      <path d="M16 4h2a2 2 0 0 1 2 2v2" />
      <path d="M20 16v2a2 2 0 0 1-2 2h-2" />
      <path d="M8 20H6a2 2 0 0 1-2-2v-2" />
      <path d="M7 12h10" />
    </svg>
  );
}

/** Icon máy ảnh */
function IconMayAnh({ className }: { className?: string }) {
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  );
}

export function ScanScreen({ onChup }: { onChup: () => void }) {
  const [trangThai, setTrangThai] = React.useState<TrangThai>("chon");
  const [maThung, setMaThung] = React.useState("");
  const [loiCamera, setLoiCamera] = React.useState("");
  const [dangChoCamera, setDangChoCamera] = React.useState(false);
  const [nhapTay, setNhapTay] = React.useState("");
  const [lanThu, setLanThu] = React.useState(0);

  // Trạng thái phiên bỏ rác
  const [phienHienTai, setPhienHienTai] = React.useState<PhienThungInfo | null>(null);
  const [dangMoPhien, setDangMoPhien] = React.useState(false);
  const [dangDongPhien, setDangDongPhien] = React.useState(false);
  const [loiPhien, setLoiPhien] = React.useState("");

  const videoRef = React.useRef<HTMLVideoElement | null>(null);
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const rafRef = React.useRef<number | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);
  const demRef = React.useRef(0);
  const pollTimerRef = React.useRef<NodeJS.Timeout | null>(null);

  const dungCamera = React.useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  // Gỡ camera khi tháo màn hình
  React.useEffect(() => dungCamera, [dungCamera]);

  // Dừng poll timer khi tháo màn hình
  React.useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, []);

  const nhanMa = React.useCallback(
    (ma: string) => {
      dungCamera();
      // Chuẩn hoá mã thùng (nếu quét URL như greenbin://bin/BIN-01 thì lấy BIN-01)
      let cleanCode = ma.trim();
      if (cleanCode.includes("/")) {
        cleanCode = cleanCode.split("/").pop() || cleanCode;
      }
      setMaThung(cleanCode);
      setTrangThai("ket-qua");
    },
    [dungCamera],
  );

  // Mở camera khi vào khung quét
  React.useEffect(() => {
    if (trangThai !== "quet") return;
    let song = true;
    setDangChoCamera(true);
    setLoiCamera("");
    (async () => {
      let stream: MediaStream | null = null;
      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error("KHONG_CO_CAMERA");
        }
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
          audio: false,
        });
        if (!song) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        const video = videoRef.current;
        if (!video) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        video.srcObject = stream;
        await video.play();
        streamRef.current = stream;
        demRef.current = 0;
        rafRef.current = window.requestAnimationFrame(() =>
          quetKhung(demRef, video, canvasRef.current, nhanMa),
        );
      } catch {
        stream?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        if (song) {
          setLoiCamera(
            "Không mở được camera. Kiểm tra quyền truy cập camera trong trình duyệt, hoặc nhập mã thùng bằng tay bên dưới.",
          );
        }
      } finally {
        if (song) setDangChoCamera(false);
      }
    })();
    return () => {
      song = false;
    };
  }, [trangThai, lanThu, nhanMa]);

  // Vòng lặp poll cập nhật số vật và điểm nhận thức khi phiên đang mở
  React.useEffect(() => {
    if (trangThai !== "dang-bo" || !phienHienTai?.ma_phien) {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      return;
    }

    const maPhien = phienHienTai.ma_phien;
    const fetchLatest = async () => {
      try {
        const res = await api.xemPhien(maPhien);
        if (res) {
          setPhienHienTai(res);
          if (res.trang_thai === "da_dong" || res.trang_thai === "het_han") {
            setTrangThai("da-chot");
          }
        }
      } catch {
        // Im lặng khi mạng chập chờn
      }
    };

    pollTimerRef.current = setInterval(fetchLatest, 1200);
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [trangThai, phienHienTai?.ma_phien]);

  const batDauPhienBoRac = async () => {
    const code = maThung.trim() || "BIN-01";
    setDangMoPhien(true);
    setLoiPhien("");
    try {
      const res = await api.batDauPhien(code);
      setPhienHienTai(res);
      setTrangThai("dang-bo");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setLoiPhien(err.message);
      } else {
        setLoiPhien("Không mở được phiên bỏ rác. Vui lòng thử lại!");
      }
    } finally {
      setDangMoPhien(false);
    }
  };

  const chotPhienBoRac = async () => {
    if (!phienHienTai?.ma_phien) return;
    setDangDongPhien(true);
    try {
      const res = await api.dongPhien(phienHienTai.ma_phien);
      setPhienHienTai(res);
      setTrangThai("da-chot");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setLoiPhien(err.message);
      }
    } finally {
      setDangDongPhien(false);
    }
  };

  const xacNhanTay = () => {
    const ma = nhapTay.trim();
    if (!ma) return;
    setMaThung(ma);
    setTrangThai("ket-qua");
  };

  const moLaiCamera = () => {
    setLoiCamera("");
    setNhapTay("");
    setLanThu((n) => n + 1);
  };

  // 1. Màn hình chọn lối vào
  if (trangThai === "chon") {
    return (
      <div className="min-h-full bg-cream px-[18px] pb-10 pt-11">
        <div className="mb-1 text-[13px] font-bold text-bulky">Chụp & quét</div>
        <h1 className="m-0 mb-1 font-[family-name:var(--font-display)] text-[26px] font-bold">
          Bạn cần làm gì?
        </h1>
        <p className="m-0 mb-5 text-[13px] font-semibold text-muted">
          Quét mã thùng để mở phiên bỏ rác, hoặc chụp món rác để biết bỏ vào đâu.
        </p>

        <button
          type="button"
          onClick={() => setTrangThai("quet")}
          className="mb-3 flex w-full cursor-pointer items-center gap-4 rounded-[22px] border border-line bg-white p-4 text-left shadow-[0_2px_10px_rgba(20,40,25,.05)] transition-all hover:border-leaf"
        >
          <span className="flex h-[52px] w-[52px] flex-none items-center justify-center rounded-[16px] bg-bulky-soft text-bulky-dark">
            <IconQuet />
          </span>
          <span className="flex-1">
            <span className="block text-[15px] font-extrabold">Quét mã thùng rác</span>
            <span className="mt-0.5 block text-[12.5px] font-semibold text-ink-soft">
              Đưa camera vào màn hình QR trên thùng BOTOL™
            </span>
          </span>
          <span className="text-[18px] font-bold text-muted">›</span>
        </button>

        <button
          type="button"
          onClick={onChup}
          className="mb-3 flex w-full cursor-pointer items-center gap-4 rounded-[22px] border border-line bg-white p-4 text-left shadow-[0_2px_10px_rgba(20,40,25,.05)] transition-all hover:border-leaf"
        >
          <span className="flex h-[52px] w-[52px] flex-none items-center justify-center rounded-[16px] bg-leaf-soft text-leaf-dark">
            <IconMayAnh />
          </span>
          <span className="flex-1">
            <span className="block text-[15px] font-extrabold">Chụp để phân loại</span>
            <span className="mt-0.5 block text-[12.5px] font-semibold text-ink-soft">
              AI nhận diện món rác ngay trong 3 giây
            </span>
          </span>
          <span className="text-[18px] font-bold text-muted">›</span>
        </button>

        <p className="mt-5 text-center text-[11px] font-semibold leading-relaxed text-muted">
          Điện thoại dùng để xác thực — thùng tự chụp và phân loại khi bạn mở phiên bỏ rác.
        </p>
      </div>
    );
  }

  // 2. Màn hình quét QR qua Camera
  if (trangThai === "quet") {
    return (
      <div className="fixed inset-0 z-40 flex flex-col bg-black">
        <div className="flex items-center justify-between px-5 pb-3 pt-[calc(env(safe-area-inset-top)+14px)]">
          <span className="text-[15px] font-bold text-white">Quét mã thùng rác</span>
          <button
            type="button"
            onClick={() => {
              dungCamera();
              setTrangThai("chon");
            }}
            aria-label="Đóng khung quét"
            className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full bg-white/15 text-white"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="relative flex min-h-0 flex-1 flex-col">
          <video
            ref={videoRef}
            muted
            playsInline
            autoPlay
            className="absolute inset-0 h-full w-full object-cover"
          />

          <div className="pointer-events-none absolute inset-0">
            <div className="absolute left-1/2 top-[10%] h-[62%] w-[76%] max-w-[340px] -translate-x-1/2 rounded-[26px] shadow-[0_0_0_9999px_rgba(0,0,0,.62)]" />
          </div>

          <div className="pointer-events-none absolute left-1/2 top-[10%] h-[62%] w-[76%] max-w-[340px] -translate-x-1/2">
            <span className="absolute left-0 top-0 h-9 w-9 rounded-tl-[22px] border-l-4 border-t-4 border-white" />
            <span className="absolute right-0 top-0 h-9 w-9 rounded-tr-[22px] border-r-4 border-t-4 border-white" />
            <span className="absolute bottom-0 left-0 h-9 w-9 rounded-bl-[22px] border-b-4 border-l-4 border-white" />
            <span className="absolute bottom-0 right-0 h-9 w-9 rounded-br-[22px] border-b-4 border-r-4 border-white" />
            <span className="animate-gbscan absolute left-[16px] right-[16px] h-[2.5px] rounded-full bg-gradient-to-r from-transparent via-[#7fd7a4] to-transparent shadow-[0_0_16px_3px_rgba(127,215,164,.75)]" />
          </div>

          <p className="pointer-events-none absolute bottom-[16%] left-0 w-full px-8 text-center text-[15px] font-bold text-white">
            Đưa mã QR trên thùng BOTOL™ vào khung
          </p>

          {dangChoCamera && (
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="animate-gbspin h-8 w-8 rounded-full border-[3px] border-white/20 border-t-white" />
            </div>
          )}

          {loiCamera && (
            <div className="absolute inset-x-4 bottom-[2%] rounded-2xl bg-white p-4 shadow-[0_16px_40px_-16px_rgba(0,0,0,.5)]">
              <p className="mb-2.5 text-[13px] font-bold text-hazard-dark">{loiCamera}</p>
              <div className="flex gap-2">
                <input
                  value={nhapTay}
                  onChange={(e) => setNhapTay(e.target.value)}
                  placeholder="Mã thùng (VD: BIN-01)"
                  className="min-w-0 flex-1 rounded-xl border border-line-3 px-3 py-2.5 text-[14px] font-semibold outline-none focus:border-leaf"
                />
                <Button onClick={xacNhanTay} disabled={!nhapTay.trim()}>
                  Xác nhận
                </Button>
              </div>
              <button
                type="button"
                onClick={moLaiCamera}
                className="mt-2 cursor-pointer text-[12px] font-bold text-recycle"
              >
                Mở lại camera
              </button>
            </div>
          )}

          <canvas ref={canvasRef} className="hidden" />
        </div>
      </div>
    );
  }

  // 3. Màn hình xác nhận mã thùng & Bấm Bắt đầu bỏ rác
  if (trangThai === "ket-qua") {
    return (
      <div className="min-h-full bg-cream px-[18px] pb-10 pt-11">
        <div className="mb-1 text-[13px] font-bold text-bulky">Quét thành công</div>
        <h1 className="m-0 mb-1 font-[family-name:var(--font-display)] text-[26px] font-bold">
          Xác thực thùng rác
        </h1>
        <p className="m-0 mb-5 text-[13px] font-semibold text-muted">
          Đã nhận diện thiết bị BOTOL™. Bấm bên dưới để mở phiên và bắt đầu tích điểm.
        </p>

        <Card className="mb-4 border-2 border-leaf-soft bg-white p-5 text-center shadow-[0_4px_16px_rgba(20,40,25,.06)]">
          <div className="text-[12px] font-bold uppercase tracking-wider text-muted">Mã thiết bị</div>
          <div className="mt-1 font-[family-name:var(--font-display)] text-[34px] font-extrabold text-bulky-dark">
            {maThung || "BIN-01"}
          </div>
          <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-leaf-soft px-3 py-1 text-[12px] font-bold text-leaf-dark">
            <span className="h-2 w-2 rounded-full bg-leaf animate-pulse" /> Sẵn sàng nhận rác
          </div>
        </Card>

        {loiPhien && (
          <div className="mb-4 rounded-xl bg-hazard-soft p-3 text-[13px] font-bold text-hazard-dark">
            {loiPhien}
          </div>
        )}

        <Button
          block
          size="lg"
          onClick={batDauPhienBoRac}
          disabled={dangMoPhien}
          className="bg-leaf text-white font-extrabold shadow-lg shadow-leaf/25"
        >
          {dangMoPhien ? "Đang mở phiên..." : "🚀 Bắt đầu bỏ rác & Tích điểm"}
        </Button>

        <div className="mt-4 flex gap-2.5">
          <Button
            variant="outline"
            className="flex-1"
            onClick={() => {
              setNhapTay("");
              setTrangThai("quet");
            }}
          >
            Quét lại
          </Button>
          <Button variant="outline" className="flex-1" onClick={() => setTrangThai("chon")}>
            Về lối chọn
          </Button>
        </div>
      </div>
    );
  }

  // 4. MÀN HÌNH PHIÊN BỎ RÁC TRỰC TIẾP (LIVE DISPOSAL SESSION)
  if (trangThai === "dang-bo") {
    const soVat = phienHienTai?.so_vat || 0;
    const diemNhanThuc = phienHienTai?.diem_nhan_thuc || 0;

    return (
      <div className="min-h-full bg-cream px-[18px] pb-10 pt-11">
        <div className="flex items-center justify-between mb-1">
          <div className="text-[13px] font-bold text-leaf-dark flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-leaf animate-ping" />
            PHIÊN BỎ RÁC ĐANG MỞ
          </div>
          <span className="text-[11px] font-mono font-bold text-muted">
            {maThung || "BIN-01"}
          </span>
        </div>

        <h1 className="m-0 mb-1 font-[family-name:var(--font-display)] text-[24px] font-bold">
          Hãy bỏ rác vào thùng
        </h1>
        <p className="m-0 mb-4 text-[12.5px] font-semibold text-muted">
          Đưa từng chai, lon hoặc giấy vào lỗ nhận của máy BOTOL™.
        </p>

        {/* Thẻ thống kê nhảy số Realtime */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          <Card className="p-4 bg-white border-2 border-leaf-soft flex flex-col items-center text-center shadow-sm">
            <span className="text-[28px]">📦</span>
            <div className="mt-1 text-[28px] font-black text-leaf-dark font-mono">
              {soVat}
            </div>
            <span className="text-[11.5px] font-bold text-muted">Vật đã phân loại</span>
          </Card>

          <Card className="p-4 bg-white border-2 border-bulky-soft flex flex-col items-center text-center shadow-sm">
            <span className="text-[28px]">✨</span>
            <div className="mt-1 text-[28px] font-black text-bulky-dark font-mono">
              +{diemNhanThuc}
            </div>
            <span className="text-[11.5px] font-bold text-muted">Điểm nhận thức</span>
          </Card>
        </div>

        <div className="mb-5 rounded-2xl bg-white p-4 border border-line shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-leaf-soft text-leaf-dark text-[18px]">
              🤖
            </div>
            <div className="flex-1 text-left">
              <div className="text-[13px] font-bold text-ink">AI ESP32-CAM sẵn sàng</div>
              <div className="text-[11.5px] text-muted">Tự động nhận diện và tính điểm khi rác rơi</div>
            </div>
          </div>
        </div>

        <Button
          block
          size="lg"
          onClick={chotPhienBoRac}
          disabled={dangDongPhien}
          className="bg-leaf text-white font-extrabold shadow-lg shadow-leaf/25"
        >
          {dangDongPhien ? "Đang chốt phiên..." : "✅ Hoàn tất & Chốt điểm"}
        </Button>

        <p className="mt-3 text-center text-[11px] font-semibold text-muted">
          Điểm nhận thức khuyến khích thói quen phân loại rác đúng cách.
        </p>
      </div>
    );
  }

  // 5. Màn hình Chúc mừng sau khi chốt phiên
  return (
    <div className="min-h-full bg-cream px-[18px] pb-10 pt-11 text-center">
      <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full bg-leaf-soft text-[32px]">
        🎉
      </div>
      <h1 className="m-0 mb-1 font-[family-name:var(--font-display)] text-[26px] font-bold text-ink">
        Tuyệt vời!
      </h1>
      <p className="m-0 mb-5 text-[13px] font-semibold text-muted">
        Bạn vừa hoàn thành một lượt phân loại rác bảo vệ môi trường.
      </p>

      <Card className="mb-5 bg-white p-5 border-2 border-leaf-soft shadow-md text-left">
        <div className="flex justify-between items-center pb-3 border-b border-line">
          <span className="text-[13px] font-semibold text-muted">Thiết bị:</span>
          <span className="text-[14px] font-bold text-ink">{maThung || "BIN-01"}</span>
        </div>
        <div className="flex justify-between items-center py-3 border-b border-line">
          <span className="text-[13px] font-semibold text-muted">Số món đã phân loại:</span>
          <span className="text-[16px] font-black text-leaf font-mono">
            {phienHienTai?.so_vat || 0} vật
          </span>
        </div>
        <div className="flex justify-between items-center pt-3">
          <span className="text-[13px] font-semibold text-muted">Điểm nhận thức:</span>
          <span className="text-[16px] font-black text-bulky-dark font-mono">
            +{phienHienTai?.diem_nhan_thuc || 0} điểm
          </span>
        </div>
      </Card>

      <Button
        block
        size="lg"
        onClick={() => {
          setPhienHienTai(null);
          setTrangThai("chon");
        }}
        className="bg-leaf text-white font-bold"
      >
        Về trang chủ
      </Button>

      <button
        type="button"
        onClick={() => {
          setPhienHienTai(null);
          setTrangThai("quet");
        }}
        className="mt-3 w-full py-2.5 text-[13px] font-bold text-recycle cursor-pointer"
      >
        Bỏ thêm rác tại thùng khác
      </button>
    </div>
  );
}
