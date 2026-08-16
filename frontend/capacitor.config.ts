import type { CapacitorConfig } from "@capacitor/cli";

/** Cấu hình đóng gói app Android.
 *
 * `webDir: "out"` là thư mục Next xuất ra khi `output: "export"` — cùng một bản
 * build mà Vercel phục vụ, không có nhánh code riêng cho app.
 *
 * Trong app, giao diện được phục vụ từ origin `https://localhost`; origin đó
 * phải nằm trong `CORS_ORIGINS` của backend, không thì mọi lệnh gọi API bị chặn.
 */
const config: CapacitorConfig = {
  appId: "vn.greenbin.app",
  appName: "GreenBin AI",
  webDir: "out",
  android: {
    // Bản demo học tập gọi API qua HTTPS; không mở cửa cho HTTP trần.
    allowMixedContent: false,
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 900,
      backgroundColor: "#f4f1ea",
      androidScaleType: "CENTER_CROP",
      showSpinner: false,
    },
  },
};

export default config;
