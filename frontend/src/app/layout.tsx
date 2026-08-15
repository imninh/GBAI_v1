import type { Metadata, Viewport } from "next";
import { Baloo_2, Nunito } from "next/font/google";
import "./globals.css";

import { RegisterSW } from "@/components/pwa/register-sw";

// Baloo 2 có subset tiếng Việt đầy đủ trên Google Fonts — thay Fredoka (chỉ có
// latin-ext nên một số tổ hợp dấu tiếng Việt hiển thị sai). Cùng tính cách
// tròn trịa, vui vẻ, đúng thương hiệu. Chữ thân bài vẫn dùng Nunito.
const baloo = Baloo_2({
  subsets: ["latin", "vietnamese"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-baloo",
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
    <html lang="vi" className={`${baloo.variable} ${nunito.variable}`}>
      <body>
        <RegisterSW />
        {children}
      </body>
    </html>
  );
}
