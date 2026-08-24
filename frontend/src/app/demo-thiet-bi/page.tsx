"use client";

import Link from "next/link";
import * as React from "react";

export default function DemoThietBiPage() {
  const [iframeSrc, setIframeSrc] = React.useState<string>("/demo-thiet-bi.html");
  const [isPort5173Online, setIsPort5173Online] = React.useState<boolean | null>(null);
  const [reloadKey, setReloadKey] = React.useState(0);
  const iframeRef = React.useRef<HTMLIFrameElement>(null);

  // Khởi tạo nguồn phù hợp theo môi trường (localhost hay production)
  React.useEffect(() => {
    const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
    if (isLocal) {
      fetch("http://localhost:5173/demo_visual", { mode: "no-cors" })
        .then(() => {
          setIsPort5173Online(true);
          setIframeSrc("http://localhost:5173/demo_visual");
        })
        .catch(() => {
          setIsPort5173Online(false);
          setIframeSrc("/demo-thiet-bi.html");
        });
    } else {
      setIsPort5173Online(false);
      setIframeSrc("/demo-thiet-bi.html");
    }
  }, [reloadKey]);

  const handleReload = () => {
    setReloadKey((prev) => prev + 1);
    if (iframeRef.current) {
      iframeRef.current.src = iframeSrc;
    }
  };

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[#090d16] text-[#f8fafc]">
      {/* Thanh điều hướng phía trên */}
      <header className="z-20 flex h-14 flex-none items-center justify-between border-b border-[#1e293b] bg-[#0c1527]/95 px-4 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-1.5 rounded-lg border border-[#334155] bg-[#1e293b]/70 px-3 py-1.5 text-xs font-semibold text-[#94a3b8] transition-colors hover:border-[#10b981] hover:text-[#f8fafc]"
          >
            <span>←</span>
            <span>Về App Cư Dân</span>
          </Link>

          <div className="hidden h-5 w-[1px] bg-[#334155] sm:block" />

          <div className="flex items-center gap-2">
            <span className="flex h-2.5 w-2.5 rounded-full bg-[#10b981] shadow-[0_0_8px_#10b981]" />
            <h1 className="text-sm font-bold tracking-wide text-white">
              BOTOL™ <span className="font-normal text-[#94a3b8]">Mô phỏng 3D Thùng Thông Minh</span>
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Nguồn hiển thị */}
          <div className="hidden items-center gap-1.5 rounded-lg border border-[#334155]/60 bg-[#0f172a] px-2.5 py-1 text-xs sm:flex">
            <span className="text-[#64748b]">Nguồn:</span>
            <button
              type="button"
              onClick={() => setIframeSrc("http://localhost:5173/demo_visual")}
              className={`rounded px-1.5 py-0.5 font-medium transition-colors ${
                iframeSrc.includes("5173")
                  ? "bg-[#10b981]/20 font-bold text-[#10b981]"
                  : "text-[#94a3b8] hover:text-white"
              }`}
            >
              Port 5173 {isPort5173Online === true && "●"}
            </button>
            <span className="text-[#334155]">|</span>
            <button
              type="button"
              onClick={() => setIframeSrc("/simulation/demo_visual.html")}
              className={`rounded px-1.5 py-0.5 font-medium transition-colors ${
                iframeSrc.includes("/simulation/")
                  ? "bg-[#10b981]/20 font-bold text-[#10b981]"
                  : "text-[#94a3b8] hover:text-white"
              }`}
            >
              Static
            </button>
          </div>

          <button
            type="button"
            onClick={handleReload}
            title="Tải lại mô phỏng"
            className="flex items-center gap-1 rounded-lg border border-[#334155] bg-[#1e293b]/70 px-2.5 py-1.5 text-xs font-semibold text-[#94a3b8] transition-colors hover:border-[#10b981] hover:text-white"
          >
            <span>↺</span>
            <span className="hidden sm:inline">Làm mới</span>
          </button>

          <a
            href="http://localhost:5173/demo_visual"
            target="_blank"
            rel="noopener noreferrer"
            title="Mở tab riêng ở port 5173"
            className="flex items-center gap-1 rounded-lg border border-[#10b981]/40 bg-[#10b981]/15 px-3 py-1.5 text-xs font-bold text-[#10b981] transition-colors hover:bg-[#10b981] hover:text-[#00170d]"
          >
            <span>Mở tab mới</span>
            <span>↗</span>
          </a>
        </div>
      </header>

      {/* Frame nhúng mô phỏng 3D */}
      <main className="relative flex-1 bg-[#090d16]">
        <iframe
          key={reloadKey}
          ref={iframeRef}
          src={iframeSrc}
          title="BOTOL 3D Smart Recycler Simulation"
          className="h-full w-full border-0"
          allow="camera; microphone; geolocation"
        />
      </main>
    </div>
  );
}
