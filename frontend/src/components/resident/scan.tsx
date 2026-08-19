"use client";

/** Màn Chụp & quét — hai lối vào rõ ràng (gói P64).
 *
 *  1. **"Quét mã thùng rác"** — mở khung quét QR kiểu iPhone: lớp phủ tối khoét
 *     ô bo góc ở giữa, bốn dấu góc, vạch sáng chạy lên xuống. Mã QR được đọc ngay
 *     trên luồng `getUserMedia` bằng **jsQR** — thư viện JS thuần (không phải
 *     plugin Capacitor). Plugin native chỉ chạy trong APK, còn người dùng iPhone
 *     đi qua bản web nên sẽ mất tính năng; thư viện JS chạy được cả hai mà không
 *     cần build lại APK.
 *
 *  2. **"Chụp để phân loại"** — đường cũ, giữ nguyên từng bước: chuyển sang màn
 *     Trang chủ và mở thẳng camera qua cơ chế `lanChup` sẵn có của AskScreen.
 *
 *  Quét xong **CHƯA mở phiên**: endpoint mở phiên thuộc gói khác và chưa tồn tại.
 *  Màn này chỉ dừng ở việc hiện mã thùng đọc được + nút "Bắt đầu bỏ rác" đang
 *  khoá — xem TODO ở nhánh "ket-qua" bên dưới.
 */

import * as React from "react";

import { Button, Card } from "@/components/ui/primitives";

import jsQR from "jsqr";

type TrangThai = "chon" | "quet" | "ket-qua";

/** Quét một khung video rồi tự lên lịch khung tiếp theo; đọc được mã thì dừng.
 *
 *  jsQR đắt nên chỉ chạy mỗi khung thứ 3 — các khung còn lại chỉ vẽ lên canvas.
 *  Trả về `number | null` là id của lần lên lịch kế (null nghĩa là đã dừng).
 */
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

/** Icon khung quét QR — vẽ tay theo khuôn icon tự vẽ của shell.tsx/ask.tsx. */
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

/** Icon máy ảnh — cùng hình với nút Chụp trên màn Trang chủ. */
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
      <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z" />
      <circle cx="12" cy="13" r="3.5" />
    </svg>
  );
}

export function ScanScreen({ onChup }: { onChup: () => void }) {
  const [trangThai, setTrangThai] = React.useState<TrangThai>("chon");
  const [maThung, setMaThung] = React.useState("");
  const [loiCamera, setLoiCamera] = React.useState("");
  const [dangChoCamera, setDangChoCamera] = React.useState(false);
  const [nhapTay, setNhapTay] = React.useState("");
  // Tăng lên để mở lại camera khi bấm "Mở lại camera" sau lỗi quyền.
  const [lanThu, setLanThu] = React.useState(0);

  const videoRef = React.useRef<HTMLVideoElement | null>(null);
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const rafRef = React.useRef<number | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);
  const demRef = React.useRef(0);

  const dungCamera = React.useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  // Gỡ camera khi tháo màn hình (đổi tab giữa chừng) — không để đèn camera sáng.
  React.useEffect(() => dungCamera, [dungCamera]);

  const nhanMa = React.useCallback(
    (ma: string) => {
      dungCamera();
      setMaThung(ma);
      setTrangThai("ket-qua");
    },
    [dungCamera],
  );

  // Mở camera khi vào khung quét. Lỗi quyền camera → hiện thông báo + ô nhập tay.
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
        // Hủy stream đã mở nếu play thất bại — không để đèn camera sáng sau lỗi.
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
  }, [trangThai, lanThu]); // eslint-disable-line react-hooks/exhaustive-deps

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
          className="mb-3 flex w-full cursor-pointer items-center gap-4 rounded-[22px] border border-line bg-white p-4 text-left shadow-[0_2px_10px_rgba(20,40,25,.05)]"
        >
          <span className="flex h-[52px] w-[52px] flex-none items-center justify-center rounded-[16px] bg-bulky-soft text-bulky-dark">
            <IconQuet />
          </span>
          <span className="flex-1">
            <span className="block text-[15px] font-extrabold">Quét mã thùng rác</span>
            <span className="mt-0.5 block text-[12.5px] font-semibold text-ink-soft">
              Đưa camera vào mã QR dán trên thùng
            </span>
          </span>
          <span className="text-[18px] font-bold text-muted">›</span>
        </button>

        <button
          type="button"
          onClick={onChup}
          className="mb-3 flex w-full cursor-pointer items-center gap-4 rounded-[22px] border border-line bg-white p-4 text-left shadow-[0_2px_10px_rgba(20,40,25,.05)]"
        >
          <span className="flex h-[52px] w-[52px] flex-none items-center justify-center rounded-[16px] bg-leaf-soft text-leaf-dark">
            <IconMayAnh />
          </span>
          <span className="flex-1">
            <span className="block text-[15px] font-extrabold">Chụp để phân loại</span>
            <span className="mt-0.5 block text-[12.5px] font-semibold text-ink-soft">
              Mun nhận ra món rác ngay trong 3 giây
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
          {/* video nền — trải toàn màn, cần muted+playsInline để iOS chạy không cần cử chỉ */}
          <video
            ref={videoRef}
            muted
            playsInline
            autoPlay
            className="absolute inset-0 h-full w-full object-cover"
          />

          {/* lớp phủ tối — khoét ô bo góc ở giữa bằng bóng đổ xa */}
          <div className="pointer-events-none absolute inset-0">
            <div className="absolute left-1/2 top-[10%] h-[62%] w-[76%] max-w-[340px] -translate-x-1/2 rounded-[26px] shadow-[0_0_0_9999px_rgba(0,0,0,.62)]" />
          </div>

          {/* bốn dấu góc + vạch sáng chạy lên xuống (animate-gbscan có sẵn) */}
          <div className="pointer-events-none absolute left-1/2 top-[10%] h-[62%] w-[76%] max-w-[340px] -translate-x-1/2">
            <span className="absolute left-0 top-0 h-9 w-9 rounded-tl-[22px] border-l-4 border-t-4 border-white" />
            <span className="absolute right-0 top-0 h-9 w-9 rounded-tr-[22px] border-r-4 border-t-4 border-white" />
            <span className="absolute bottom-0 left-0 h-9 w-9 rounded-bl-[22px] border-b-4 border-l-4 border-white" />
            <span className="absolute bottom-0 right-0 h-9 w-9 rounded-br-[22px] border-b-4 border-r-4 border-white" />
            <span className="animate-gbscan absolute left-[16px] right-[16px] h-[2.5px] rounded-full bg-gradient-to-r from-transparent via-[#7fd7a4] to-transparent shadow-[0_0_16px_3px_rgba(127,215,164,.75)]" />
          </div>

          <p className="pointer-events-none absolute bottom-[16%] left-0 w-full px-8 text-center text-[15px] font-bold text-white">
            Đưa mã QR trên thùng vào khung
          </p>

          {dangChoCamera && (
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="animate-gbspin h-8 w-8 rounded-full border-[3px] border-white/20 border-t-white" />
            </div>
          )}

          {/* Camera hỏng hoặc bị từ chối quyền → nhập mã thùng bằng tay, đừng để kẹt */}
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

          {/* canvas chỉ để đọc khung quét, không hiển thị */}
          <canvas ref={canvasRef} className="hidden" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-cream px-[18px] pb-10 pt-11">
      <div className="mb-1 text-[13px] font-bold text-bulky">Quét thành công</div>
      <h1 className="m-0 mb-1 font-[family-name:var(--font-display)] text-[26px] font-bold">
        Bắt đầu bỏ rác
      </h1>
      <p className="m-0 mb-5 text-[13px] font-semibold text-muted">
        Đã nhận mã thùng. Mở phiên bỏ rác sẽ có ở bản cập nhật sau.
      </p>

      <Card className="mb-4 p-4">
        <div className="text-[12px] font-bold text-muted">Mã thùng</div>
        <div className="mt-0.5 font-[family-name:var(--font-display)] text-[30px] font-extrabold text-bulky">
          {maThung}
        </div>
      </Card>

      {/* TODO(P64): nối endpoint mở phiên bỏ rác tại đây. Endpoint thuộc gói khác và
          chưa tồn tại — khi có, gọi API với mã thùng vừa đọc (maThung) rồi chuyển
          sang màn phiên bỏ rác. Gói này KHÔNG gọi thử API chưa có. */}
      <Button block size="lg" disabled>
        Bắt đầu bỏ rác
      </Button>
      <p className="mt-2 text-center text-[12px] font-bold text-muted">
        Đang hoàn thiện — sẽ mở được ở bản sau
      </p>

      <div className="mt-5 flex gap-2.5">
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
