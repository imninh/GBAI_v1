import Link from "next/link";

import { Button } from "@/components/ui/primitives";

/** Trang chính sách riêng tư — nội dung tĩnh, dùng token màu, không đăng nhập.
 *  Nội dung lấy nguyên văn từ đặc tả F3-SEO §2.5, không tự bịa thêm. */
export default function ChinhSachRiengTuPage() {
  return (
    <main className="mx-auto min-h-dvh w-full max-w-[640px] bg-cream px-5 pb-16 pt-12">
      <h1 className="font-[family-name:var(--font-display)] text-[30px] font-bold text-ink">
        Chính sách riêng tư
      </h1>
      <p className="mt-1.5 text-sm font-semibold text-ink-faint">Cập nhật: 08/2026</p>

      <p className="mt-5 text-[15px] font-semibold leading-relaxed text-ink-dim">
        GreenBin AI là sản phẩm trong khuôn khổ học tập. Trang này nói rõ ứng dụng thu
        thập gì và xử lý ra sao.
      </p>

      <section className="mt-7">
        <h2 className="font-[family-name:var(--font-display)] text-xl font-bold text-leaf-dark">
          Ảnh bạn chụp
        </h2>
        <p className="mt-2 text-[15px] font-semibold leading-relaxed text-ink-dim">
          Khi bạn chụp một món rác để phân loại, ảnh được gửi lên máy chủ để nhận diện.{" "}
          <strong className="text-ink">Trước khi xử lý</strong>, máy chủ tự động:
        </p>
        <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5 text-[15px] font-semibold leading-relaxed text-ink-dim">
          <li>
            <strong className="text-ink">xoá toàn bộ thông tin ẩn trong ảnh</strong> (EXIF) — trong đó có toạ độ
            GPS và thời điểm chụp;
          </li>
          <li>
            <strong className="text-ink">làm mờ khuôn mặt</strong> nếu phát hiện có người trong khung hình.
          </li>
        </ul>
        <p className="mt-2 text-[15px] font-semibold leading-relaxed text-ink-dim">
          Ảnh sau khi xử lý được lưu để cải thiện chất lượng nhận diện. Ảnh gốc không được giữ lại.
        </p>
      </section>

      <section className="mt-7">
        <h2 className="font-[family-name:var(--font-display)] text-xl font-bold text-leaf-dark">Vị trí</h2>
        <p className="mt-2 text-[15px] font-semibold leading-relaxed text-ink-dim">
          Ứng dụng dùng vị trí <strong className="text-ink">chỉ khi bạn đặt lịch thu gom hoặc xem bản đồ điểm gửi</strong>{" "}
          — để tính điểm gần bạn và sắp tuyến cho đội thu gom. Ứng dụng không theo dõi vị trí ở chế độ nền.
        </p>
      </section>

      <section className="mt-7">
        <h2 className="font-[family-name:var(--font-display)] text-xl font-bold text-leaf-dark">
          Thông tin tài khoản
        </h2>
        <p className="mt-2 text-[15px] font-semibold leading-relaxed text-ink-dim">
          Khi đăng ký, ứng dụng lưu số điện thoại và mật khẩu (đã mã hoá) để đăng nhập, và
          địa chỉ bạn tự nhập để phục vụ thu gom. Ứng dụng <strong className="text-ink">không</strong> thu thập
          danh bạ, không đọc tin nhắn, không gắn quảng cáo.
        </p>
      </section>

      <section className="mt-7">
        <h2 className="font-[family-name:var(--font-display)] text-xl font-bold text-leaf-dark">
          Theo dõi chất lượng AI
        </h2>
        <p className="mt-2 text-[15px] font-semibold leading-relaxed text-ink-dim">
          Để cải thiện độ chính xác, hệ thống ghi lại quá trình xử lý của AI. Trước khi ghi,{" "}
          <strong className="text-ink">số điện thoại, email, toạ độ và họ tên đều được che</strong>.
        </p>
      </section>

      <section className="mt-7">
        <h2 className="font-[family-name:var(--font-display)] text-xl font-bold text-leaf-dark">Chia sẻ</h2>
        <p className="mt-2 text-[15px] font-semibold leading-relaxed text-ink-dim">
          Dữ liệu chỉ dùng trong phạm vi vận hành GreenBin (phân loại, thu gom, điều phối).
          Ứng dụng không bán dữ liệu cho bên thứ ba.
        </p>
      </section>

      <section className="mt-7">
        <h2 className="font-[family-name:var(--font-display)] text-xl font-bold text-leaf-dark">Liên hệ</h2>
        <p className="mt-2 text-[15px] font-semibold leading-relaxed text-ink-dim">
          Mọi thắc mắc về dữ liệu, liên hệ ban quản lý toà nhà của bạn.
        </p>
      </section>

      <Link href="/" className="mt-9 inline-block">
        <Button variant="outline">Về trang chủ</Button>
      </Link>
    </main>
  );
}
