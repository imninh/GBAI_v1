import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Xuất tĩnh ra `out/`: cùng một bản build vừa cho Vercel phục vụ, vừa cho
  // Capacitor gói vào APK. Chạy được vì `src/` không có server action, route
  // handler hay `next/image` nào.
  output: "export",
  images: { unoptimized: true },
  // Bản export tĩnh không có máy chủ để chuyển hướng /tai-app → /tai-app/,
  // nên phải xuất thành thư mục có index.html.
  trailingSlash: true,
  // CHỈ có tác dụng ở `next dev`. Next 15 chặn request dev đến từ origin lạ;
  // khi thử trên điện thoại thật (qua IP nội bộ hoặc tunnel Cloudflare) thì
  // origin không phải localhost nên bị chặn. Bản build production không đọc
  // mục này.
  allowedDevOrigins: ["192.168.0.108", "*.trycloudflare.com"],
  // Ảnh cư dân luôn đi qua endpoint có kiểm quyền của backend, không đặt ở
  // URL công khai đoán được — nên không dùng next/image remote patterns.
  //
  // KHÔNG khai lại `NEXT_PUBLIC_*` trong khối `env` ở đây. Next tự nội tuyến mọi
  // biến `NEXT_PUBLIC_*`, còn khối `env` được tính lúc nạp file config — tức là
  // trước khi `.env.local` được đọc — nên nó ghi đè bằng giá trị mặc định và
  // mọi thứ đặt trong `.env.local` bị bỏ qua trong im lặng.
  // Giá trị mặc định đặt ngay tại chỗ dùng:
  //   NEXT_PUBLIC_API_URL     → src/lib/api.ts
  //   NEXT_PUBLIC_WEB_URL     → src/app/page.tsx
  //   NEXT_PUBLIC_GITHUB_REPO → src/app/tai-app/page.tsx
};

export default nextConfig;
