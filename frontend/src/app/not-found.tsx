import Link from "next/link";

import { Button } from "@/components/ui/primitives";
import { IconMamXanh } from "@/lib/icons";

/** Trang 404 tiếng Việt, sinh tĩnh bởi App Router + output:export (ra 404.html).
 *  Render NGOÀI PhoneFrame nên tự lo canh giữa toàn màn hình. */
export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-cream px-6 py-16 text-center">
      <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-leaf-soft text-leaf">
        <IconMamXanh className="h-10 w-10" strokeWidth={1.8} />
      </div>
      <h1 className="mt-6 font-[family-name:var(--font-display)] text-[28px] font-bold text-ink">
        Trang này đi lạc mất rồi
      </h1>
      <p className="mt-2.5 max-w-[42ch] text-[15px] font-semibold leading-snug text-ink-faint">
        Có thể đường dẫn đã đổi, hoặc trang chưa từng tồn tại. Về trang chủ để tiếp tục
        phân loại rác thôi nào.
      </p>
      <Link href="/" className="mt-7">
        <Button size="lg">Về trang chủ</Button>
      </Link>
    </main>
  );
}
