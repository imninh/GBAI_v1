// Cấu hình ESLint dạng "flat config" (ESLint 9).
//
// Vì sao có file này: Cohort 1 mất điểm Code Quality vì frontend không hề được
// lint (`docs/guide/anti-patterns/`). Script `npm run lint` trước đây gọi
// `next lint` — lệnh đó đã bị Next 15 đánh dấu deprecated và bị bỏ ở Next 16,
// nên ở đây gọi thẳng ESLint CLI.
//
// Quy tắc riêng của dự án nằm ở cuối file, mỗi cái kèm lý do. Đừng thêm rule
// mà không ghi lý do — rule không giải thích được là rule sẽ bị tắt ở lần đầu
// tiên nó kêu.

import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  {
    ignores: [
      ".next/**",
      "out/**",
      "node_modules/**",
      "android/**", // khung Capacitor sinh tự động, không phải code của nhóm
      "public/sw.js", // service worker viết tay, chạy ngoài bundler nên không theo module graph
      "public/simulation/**", // static simulation 3D third-party bundles (three.min.js, etc.)
      "next-env.d.ts", // Next sinh lại file này mỗi lần build, sửa vào là mất
    ],
  },

  ...compat.extends("next/core-web-vitals", "next/typescript"),

  {
    rules: {
      // Biến không dùng là lỗi, nhưng cho phép tiền tố `_` để cố ý bỏ qua một
      // tham số — hay gặp ở handler của React.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],

      // `any` làm rỗng toàn bộ giá trị của TypeScript. Để mức cảnh báo chứ chưa
      // phải lỗi, để không chặn CI ngay ngày đầu bật lint.
      "@typescript-eslint/no-explicit-any": "warn",

      // Bắt cùng một lỗi mà ruff bắt ở phía Python (`CLAUDE.md` mục 9: không
      // dùng bare except) — nuốt lỗi im lặng ở hai đầu đều nguy hiểm như nhau.
      "no-empty": ["error", { allowEmptyCatch: false }],
    },
  },
];

export default config;
