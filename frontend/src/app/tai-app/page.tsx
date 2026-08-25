"use client";

/** Trang "Tải app" — ba đường cài, chọn theo máy người dùng đang cầm.
 *
 * Nói thẳng cái làm được và cái không: **không build được IPA trên Windows**
 * nên iPhone đi đường PWA. Hứa suông một nút "Tải cho iPhone" rồi để nó dẫn đi
 * đâu đó là kiểu tệ nhất.
 */

import Link from "next/link";
import * as React from "react";

import { dangChayDangApp, useCaiApp } from "@/components/pwa/register-sw";
import { Mascot } from "@/components/resident/onboarding";
import { Button, Card } from "@/components/ui/primitives";

// Đổi bằng biến môi trường lúc build khi repo đã có tên thật.
const REPO = process.env.NEXT_PUBLIC_GITHUB_REPO ?? "";
const LINK_APK = REPO ? `https://github.com/${REPO}/releases/latest` : "";

function Buoc({ so, children }: { so: number; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-leaf-soft text-xs font-bold text-leaf">
        {so}
      </span>
      <span className="flex-1 pt-0.5 text-sm font-semibold leading-snug text-ink-dim">{children}</span>
    </li>
  );
}

export default function TaiAppPage() {
  const [caiDuoc, cai] = useCaiApp();
  const [daCai, setDaCai] = React.useState(false);

  React.useEffect(() => setDaCai(dangChayDangApp()), []);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[560px] flex-col gap-5 px-5 pb-16 pt-12">
      <header className="flex items-center gap-4">
        <Mascot size={72} tuThe="hello" />
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-[30px] font-bold leading-none tracking-tight">
            Cài GreenBin AI
          </h1>
          <p className="mt-1.5 text-sm font-semibold text-ink-faint">
            Cư dân và đội vệ sinh dùng app trên điện thoại. Ban quản lý dùng web trên máy tính.
          </p>
        </div>
      </header>

      {daCai && (
        <Card className="border-leaf-soft bg-leaf-soft/40 p-4 text-sm font-bold text-leaf">
          Bạn đang mở bản đã cài rồi — không cần làm gì thêm.
        </Card>
      )}

      {caiDuoc && !daCai && (
        <Button block size="lg" onClick={cai}>
          Cài app ngay
        </Button>
      )}

      {/* --- Android --- */}
      <Card className="p-5">
        <div className="mb-1 text-xs font-bold uppercase tracking-wide text-muted">Android</div>
        <h2 className="mb-3 font-[family-name:var(--font-display)] text-xl font-bold">Tải file APK về cài</h2>
        {LINK_APK ? (
          <a href={LINK_APK} target="_blank" rel="noreferrer">
            <Button block>Tải APK bản mới nhất</Button>
          </a>
        ) : (
          <div className="mb-3 rounded-xl border-[1.5px] border-dashed border-line-2 px-4 py-3 text-sm font-semibold text-muted">
            Bản APK đầu tiên chưa phát hành.{" "}
            {caiDuoc ? (
              <>
                Trong lúc chờ, bấm <b>Cài app ngay</b> ở đầu trang — Chrome trên Android cài thẳng
                được từ web.
              </>
            ) : (
              <>
                Trong lúc chờ, mở trang này bằng <b>Chrome trên Android</b> rồi chọn <b>Cài ứng dụng</b>{" "}
                trong menu — cùng một giao diện.
              </>
            )}
          </div>
        )}
        <ol className="mt-3.5 flex flex-col gap-2.5">
          <Buoc so={1}>Mở file vừa tải, Android sẽ hỏi có cho cài từ nguồn này không — chọn Cho phép.</Buoc>
          <Buoc so={2}>Mở app, đăng nhập bằng tài khoản của bạn.</Buoc>
          <Buoc so={3}>Lần đầu chụp ảnh, app xin quyền camera — bấm Đồng ý.</Buoc>
        </ol>
        <p className="mt-3.5 text-xs font-semibold leading-relaxed text-muted">
          Đây là bản APK gỡ lỗi dùng cho demo học tập, chưa ký để lên Google Play. Không cài được thì
          dùng đường PWA bên dưới — cùng một giao diện.
        </p>
      </Card>

      {/* --- iPhone --- */}
      <Card className="p-5">
        <div className="mb-1 text-xs font-bold uppercase tracking-wide text-muted">iPhone / iPad</div>
        <h2 className="mb-3 font-[family-name:var(--font-display)] text-xl font-bold">Thêm vào màn hình chính</h2>
        <ol className="flex flex-col gap-2.5">
          <Buoc so={1}>Mở trang này bằng <b>Safari</b> (Chrome trên iPhone không thêm được).</Buoc>
          <Buoc so={2}>Bấm nút Chia sẻ ở thanh dưới.</Buoc>
          <Buoc so={3}>Chọn <b>Thêm vào MH chính</b>, rồi bấm Thêm.</Buoc>
        </ol>
        <p className="mt-3.5 text-xs font-semibold leading-relaxed text-muted">
          Nhóm phát triển trên Windows nên chưa dựng được bản cài cho iPhone. Bản thêm vào màn hình
          chính chạy đủ mọi tính năng, chỉ mở camera qua trình duyệt thay vì camera của hệ thống.
        </p>
      </Card>

      {/* --- Máy tính --- */}
      <Card className="p-5">
        <div className="mb-1 text-xs font-bold uppercase tracking-wide text-muted">Máy tính</div>
        <h2 className="mb-3 font-[family-name:var(--font-display)] text-xl font-bold">Dùng thẳng trên web</h2>
        <p className="text-sm font-semibold leading-snug text-ink-dim">
          Console ban quản lý được thiết kế cho màn hình rộng — mở web là dùng được, không cần cài gì.
        </p>
        <Link href="/" className="mt-3.5 block">
          <Button block variant="outline">
            Mở console trên web
          </Button>
        </Link>
      </Card>

      <p className="text-center text-[11px] font-semibold leading-relaxed text-muted-slate">
        Bản demo chạy trên hạ tầng miễn phí: máy chủ ngủ khi rảnh nên lần mở đầu tiên có thể chậm
        vài chục giây, và ảnh đã tải lên sẽ mất khi máy chủ khởi động lại.
      </p>

      <Link
        href="/rieng-tu/"
        className="mx-auto mt-1 block w-fit text-center text-[12px] font-bold text-leaf underline-offset-4 hover:underline"
      >
        Chính sách riêng tư
      </Link>
    </main>
  );
}
