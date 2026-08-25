import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Chính sách riêng tư — GreenBin AI",
  description:
    "GreenBin AI thu thập gì và xử lý dữ liệu ra sao: ảnh, vị trí, tài khoản, theo dõi chất lượng AI.",
  openGraph: {
    type: "website",
    locale: "vi_VN",
    siteName: "GreenBin AI",
    title: "Chính sách riêng tư — GreenBin AI",
    description:
      "GreenBin AI thu thập gì và xử lý dữ liệu ra sao: ảnh, vị trí, tài khoản, theo dõi chất lượng AI.",
    images: [
      {
        url: "/og-image.jpg",
        width: 1200,
        height: 630,
        alt: "GreenBin AI — chính sách riêng tư",
      },
    ],
  },
};

export default function RiengTuLayout({ children }: { children: React.ReactNode }) {
  return children;
}
