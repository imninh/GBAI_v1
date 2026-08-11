import type { Metadata, Viewport } from "next";
import { Fredoka, Nunito } from "next/font/google";
import "./globals.css";

import { RegisterSW } from "@/components/pwa/register-sw";

// Fredoka chưa có subset tiếng Việt trên Google Fonts — dùng latin-ext để phủ
// phần lớn dấu, còn chữ thân bài dùng Nunito (có subset vietnamese đầy đủ).
const fredoka = Fredoka({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-fredoka",
});

const nunito = Nunito({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "600", "700", "800"],
  variable: "--font-nunito",
});

export const metadata: Metadata = {
  title: "GreenBin AI — Phân loại rác & điều phối thu gom",
  description:
    "Chụp một tấm — biết ngay bỏ thùng nào, để ở đâu, thu gom lúc mấy giờ. Ảnh được xoá thông tin vị trí và làm mờ khuôn mặt trước khi xử lý.",
  manifest: "/manifest.webmanifest",
  applicationName: "GreenBin AI",
  appleWebApp: {
    capable: true,
    title: "GreenBin AI",
    statusBarStyle: "default",
  },
  icons: {
    icon: "/icons/icon-192.png",
    apple: "/icons/apple-touch-icon.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#2fae66",
  // Giao diện thiết kế theo khung điện thoại; cho phóng to để không cản người
  // cần chữ lớn, nhưng chặn phóng theo chiều rộng làm vỡ bố cục.
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={`${fredoka.variable} ${nunito.variable}`}>
      <body>
        <RegisterSW />
        {children}
      </body>
    </html>
  );
}
