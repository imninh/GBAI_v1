import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Điều phối thùng thu gom — GreenBin AI",
  description:
    "Bản đồ thùng rác: mức đầy, mức pin, trạng thái kết nối. Đầu ca biết ngay hôm nay đi gom thùng nào trước.",
  openGraph: {
    type: "website",
    locale: "vi_VN",
    siteName: "GreenBin AI",
    title: "Điều phối thùng thu gom — GreenBin AI",
    description:
      "Bản đồ thùng rác: mức đầy, mức pin, trạng thái kết nối. Đầu ca biết ngay hôm nay đi gom thùng nào trước.",
    images: [
      {
        url: "/og-image.jpg",
        width: 1200,
        height: 630,
        alt: "GreenBin AI — điều phối thu gom",
      },
    ],
  },
};

export default function DieuPhoiLayout({ children }: { children: React.ReactNode }) {
  return children;
}
