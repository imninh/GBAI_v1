"use client";

/** Màn Điểm nhận thức & Nhiệm vụ.
 *
 *  ⚠️ ĐIỂM NHẬN THỨC KHÔNG PHẢI ĐIỂM XANH.
 *  - Điểm nhận thức: đếm số vật đã phân loại + làm nhiệm vụ → xếp hạng, huy hiệu.
 *  - Điểm xanh (green_points): cân thật khi thu gom → đổi được quà.
 *  Hai loại điểm KHÔNG BAO GIỜ gộp. Giao diện phải nói rõ điều này bằng chữ
 *  người dùng đọc được (không giấu trong tooltip).
 *
 *  Dữ liệu:
 *  - Tổng điểm & lịch sử: api.diemNhanThuc() → TongQuanDiemNhanThuc
 *  - Nhiệm vụ ngày/tuần: api.nhiemVuNhanThuc() → DanhSachNhiemVu
 *  - Kiểm nhiệm vụ: api.kiemNhiemVu() → KetQuaKiemNhiemVu
 */

import * as React from "react";
import NumberFlow from "@number-flow/react";

import { Button, Card, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { ScreenHeader } from "@/components/ui/shell";
import { Mascot } from "@/components/resident/onboarding";
import { api, ApiError } from "@/lib/api";
import { IconDuyet, IconMamXanh, IconCanhBao } from "@/lib/icons";
import { ngayVn, soVn } from "@/lib/format";
import type { NhiemVuDiemNhanThuc, NhiemVuVuaHoanThanh, TongQuanDiemNhanThuc } from "@/lib/types";

interface DiemNhanThucProps {
  onBack: () => void;
}

export function DiemNhanThucScreen({ onBack }: DiemNhanThucProps) {
  const [tongQuan, setTongQuan] = React.useState<TongQuanDiemNhanThuc | null>(null);
  const [nhiemVu, setNhiemVu] = React.useState<{ ngay: string; items: NhiemVuDiemNhanThuc[] } | null>(null);
  const [loi, setLoi] = React.useState<string | null>(null);
  const [dangTai, setDangTai] = React.useState(true);
  const [kiemDangChay, setKiemDangChay] = React.useState(false);
  const [vuaNhan, setVuaNhan] = React.useState<NhiemVuVuaHoanThanh[] | null>(null);

  const taiDuLieu = React.useCallback(async () => {
    setDangTai(true);
    setLoi(null);
    try {
      const [tq, nv] = await Promise.all([api.diemNhanThuc(), api.nhiemVuNhanThuc()]);
      setTongQuan(tq);
      setNhiemVu(nv);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Chưa tải được điểm nhận thức.";
      setLoi(msg);
    } finally {
      setDangTai(false);
    }
  }, []);

  React.useEffect(() => {
    taiDuLieu();
  }, [taiDuLieu]);

  async function xuLyKiemNhiemVu() {
    setKiemDangChay(true);
    try {
      const kq = await api.kiemNhiemVu();
      setVuaNhan(kq.da_hoan_thanh);
      if (kq.da_hoan_thanh.length > 0) {
        // Hiện thông báo vừa nhận điểm
        setTimeout(() => setVuaNhan(null), 4000);
      }
      // Làm mới lại danh sách nhiệm vụ
      const nv = await api.nhiemVuNhanThuc();
      setNhiemVu(nv);
      // Cập nhật tổng điểm
      const tq = await api.diemNhanThuc();
      setTongQuan(tq);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Kiểm nhiệm vụ không thành công.";
      setLoi(msg);
    } finally {
      setKiemDangChay(false);
    }
  }

  // Trạng thái loading
  if (dangTai) {
    return (
      <div className="min-h-full bg-cream px-[18px] pb-[108px] pt-[54px]">
        <ScreenHeader title="Điểm nhận thức" onBack={onBack} />
        <div className="space-y-3.5">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );
  }

  // Trạng thái lỗi
  if (loi) {
    return (
      <div className="min-h-full bg-cream px-[18px] pb-[108px] pt-[54px]">
        <ScreenHeader title="Điểm nhận thức" onBack={onBack} />
        <ErrorState message={loi} onRetry={taiDuLieu} />
      </div>
    );
  }

  if (!tongQuan || !nhiemVu) {
    return (
      <div className="min-h-full bg-cream px-[18px] pb-[108px] pt-[54px]">
        <ScreenHeader title="Điểm nhận thức" onBack={onBack} />
        <ErrorState message="Không có dữ liệu điểm nhận thức." onRetry={taiDuLieu} />
      </div>
    );
  }

  // Tách nhiệm vụ theo chu kỳ
  const nhiemVuNgay = nhiemVu.items.filter((nv) => nv.chu_ky === "ngay");
  const nhiemVuTuan = nhiemVu.items.filter((nv) => nv.chu_ky === "tuan");

  // Trạng thái rỗng (chưa có điểm nào)
  const coLichSu = tongQuan.gan_day.length > 0;

  // `hom_nay` là NGÀY (YYYY-MM-DD), không phải số điểm — ép Number() lên nó là
  // ra "NaN điểm" như bản trước. Điểm trong ngày phải cộng từ sổ cái: lọc các
  // dòng có ngày trùng `hom_nay` rồi cộng lại; sổ cái rỗng thì tự nhiên là 0.
  const diemHomNay = tongQuan.gan_day
    .filter((d) => d.ngay === tongQuan.hom_nay)
    .reduce((tong, d) => tong + d.diem, 0);

  return (
    <div className="min-h-full bg-cream px-[18px] pb-[108px] pt-[54px] lg:mx-auto lg:max-w-[960px] lg:px-8">
      <ScreenHeader title="Điểm nhận thức" onBack={onBack} />

      {/* Cảnh báo phân biệt hai loại điểm */}
      <div className="mb-3.5 rounded-xl border border-amber-line bg-amber-soft px-4 py-3 text-sm font-bold leading-relaxed text-amber">
        <div className="flex items-start gap-2">
          <IconCanhBao className="mt-0.5 h-4 w-4 flex-none" />
          <div>
            <div className="font-extrabold">Điểm nhận thức ≠ Điểm xanh</div>
            <div className="mt-0.5">Điểm này chỉ để xếp hạng, nhận huy hiệu — <span className="font-extrabold">KHÔNG đổi được quà</span>. Điểm xanh (cân thật khi thu gom) mới đổi được quà.</div>
          </div>
        </div>
      </div>

      {/* Thẻ tổng điểm */}
      <Card className="mb-3.5 p-4">
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <span className="text-sm font-extrabold">Tổng điểm nhận thức</span>
          <span className="flex-none text-lg font-extrabold tabular-nums text-leaf-dark">
            <NumberFlow value={tongQuan.tong_diem_nhan_thuc} locales="vi-VN" />
          </span>
        </div>
        <div className="text-[12px] font-semibold text-muted">Hôm nay: <span className="font-extrabold text-ink">{soVn(diemHomNay)}</span> điểm</div>

        {/* Lịch sử gần đây */}
        {coLichSu && (
          <div className="mt-3 space-y-2">
            <div className="text-xs font-bold text-muted">Gần đây</div>
            {tongQuan.gan_day.slice(0, 5).map((item, i) => (
              <div key={i} className="flex items-center justify-between gap-2 rounded-xl border border-line-3 bg-surface px-3 py-2 text-sm">
                <span className="font-semibold text-ink-soft">{item.ghi_chu}</span>
                <span className="flex-none font-extrabold text-leaf-dark">+{soVn(item.diem)}</span>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Nhiệm vụ hôm nay */}
      <Card className="mb-3.5 p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-extrabold">Nhiệm vụ hôm nay</span>
          {nhiemVuNgay.length > 0 && (
            <span className="text-[11px] font-bold text-muted">{ngayVn(nhiemVu.ngay)}</span>
          )}
        </div>

        {nhiemVuNgay.length === 0 ? (
          <EmptyState
            icon={IconMamXanh}
            title="Hôm nay chưa có nhiệm vụ"
            hint="Nhiệm vụ ngày sẽ hiện ở đây khi có. Hãy phân loại rác để bắt đầu."
            minhHoa={<Mascot size={64} tuThe="nup-la" />}
          />
        ) : (
          <div className="space-y-2.5">
            {nhiemVuNgay.map((nv) => (
              <NhiemVuCard key={nv.ma} nhiemVu={nv} />
            ))}
          </div>
        )}
      </Card>

      {/* Nhiệm vụ tuần này */}
      <Card className="mb-3.5 p-4">
        <div className="mb-3 text-sm font-extrabold">Nhiệm vụ tuần này</div>

        {nhiemVuTuan.length === 0 ? (
          <EmptyState
            icon={IconMamXanh}
            title="Tuần này chưa có nhiệm vụ"
            hint="Nhiệm vụ tuần xuất hiện khi bắt đầu tuần mới. Tiếp tục phân loại nhé."
          />
        ) : (
          <div className="space-y-2.5">
            {nhiemVuTuan.map((nv) => (
              <NhiemVuCard key={nv.ma} nhiemVu={nv} />
            ))}
          </div>
        )}
      </Card>

      {/* Nút kiểm nhiệm vụ */}
      <Button
        block
        variant="leaf"
        disabled={kiemDangChay}
        onClick={xuLyKiemNhiemVu}
        className="mb-3.5"
      >
        {kiemDangChay ? "Đang kiểm tra…" : "Kiểm tra nhiệm vụ đã hoàn thành"}
      </Button>

      {/* Toast vừa nhận điểm */}
      {vuaNhan && vuaNhan.length > 0 && (
        <div className="fixed bottom-[calc(84px+env(safe-area-inset-bottom)+12px)] left-[18px] right-[18px] z-50 animate-gbslideup">
          {vuaNhan.map((nv, i) => (
            <Card key={i} className="mb-2 border-2 border-leaf bg-leaf-soft shadow-[var(--shadow-lg)]">
              <div className="p-4 flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-leaf text-white">
                  <IconDuyet className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <div className="font-bold text-leaf-dark">{nv.ten}</div>
                  <div className="text-sm font-semibold text-ink-soft">Vừa nhận <span className="font-extrabold">+{soVn(nv.diem)}</span> điểm nhận thức</div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Footer ghi chú */}
      <p className="text-center text-[11px] font-semibold leading-relaxed text-muted">
        Con số đếm là <span className="font-extrabold">số vật đã phân loại</span> (một túi nhiều vỏ chai = 1 vật), không phải số rác đã bỏ.
      </p>
    </div>
    );
  }

/** Card hiển thị một nhiệm vụ */
function NhiemVuCard({ nhiemVu }: { nhiemVu: NhiemVuDiemNhanThuc }) {
  const phanTram = nhiemVu.dieu_kien_nguong > 0 ? Math.min(100, Math.round((nhiemVu.tien_do / nhiemVu.dieu_kien_nguong) * 100)) : 0;
  const daXong = nhiemVu.da_nhan || phanTram >= 100;

  return (
    <div className="rounded-xl border p-3 transition-colors" style={{ borderColor: daXong ? "var(--leaf)" : "var(--line-3)", backgroundColor: daXong ? "var(--leaf-soft)" : "white" }}>
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="font-bold text-ink">{nhiemVu.ten}</span>
            {daXong && (
              <span className="inline-flex items-center gap-1 rounded-full bg-leaf px-2 py-0.5 text-[10px] font-extrabold text-white">
                <IconDuyet className="h-3 w-3" />
                Đã nhận
              </span>
            )}
            {nhiemVu.chu_ky === "tuan" && !daXong && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-soft px-2 py-0.5 text-[10px] font-extrabold text-amber">
                Tuần
              </span>
            )}
          </div>
          <div className="mt-1 text-[12px] font-semibold text-muted line-clamp-2">{nhiemVu.mo_ta}</div>
        </div>
        <div className="flex-none text-right">
          <div className="font-extrabold text-leaf-dark">+{soVn(nhiemVu.diem)}</div>
          <div className="text-[11px] font-semibold text-muted">điểm</div>
        </div>
      </div>

      {/* Thanh tiến độ */}
      <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-line-2">
        <div
          className="h-full rounded-full transition-all duration-500 ease-[var(--ease-spring)]"
          style={{
            width: `${phanTram}%`,
            backgroundColor: daXong ? "var(--leaf)" : "var(--amber)",
          }}
        />
      </div>

      <div className="flex items-center justify-between text-[11px] font-bold">
        <span className="text-muted">{nhiemVu.tien_do} / {nhiemVu.dieu_kien_nguong}</span>
        <span className={daXong ? "text-leaf-dark" : "text-amber"}>
          {phanTram}%
        </span>
      </div>
    </div>
  );
}