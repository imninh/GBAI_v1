import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Điều phối thùng thu gom — GreenBin AI",
  description:
    "Bản đồ thùng rác: mức đầy, mức pin, trạng thái kết nối. Đầu ca biết ngay hôm nay đi gom thùng nào trước.",
};

export default function DieuPhoiLayout({ children }: { children: React.ReactNode }) {
  return children;
}
