"use client";

/** Quyền riêng tư · Lịch thu gom · Yêu cầu của tôi · Tôi. */

import * as React from "react";
import NumberFlow from "@number-flow/react";

import { CaiAppCard } from "@/components/pwa/cai-app";
import { DiemNhanThucScreen } from "@/components/resident/diem_nhan_thuc";
import { Button, Card, EmptyState, Skeleton } from "@/components/ui/primitives";
import { ScreenHeader } from "@/components/ui/shell";
import { api } from "@/lib/api";
import { AnhCoToken } from "@/lib/anh-co-token";
import { dungLuong, kg, ngayVn, TRANG_THAI_YEU_CAU } from "@/lib/format";
import { CAP_DO, tinhCap, tinhStreak } from "@/lib/gamification";
import { useSession } from "@/lib/session";
import { Flame, Recycle } from "lucide-react";
import {
  IconChoDuyet,
  IconChupAnh,
  IconDuyet,
  IconGapLoi,
  IconKhoa,
  IconLichThuGom,
  IconMamXanh,
  IconMonDo,
  IconNguoiDung,
  IconQuayLai,
  IconTiepTuc,
  IconToaNha,
  IconTuChoi,
  IconTuXoa,
  IconXeThuGom,
} from "@/lib/icons";
import type { PickupRequest, PrivacyReport, User } from "@/lib/types";

export function PrivacyScreen({ mediaId, onBack }: { mediaId: number; onBack: () => void }) {
  const [bao, setBao] = React.useState<PrivacyReport | null>(null);
  const [daXoa, setDaXoa] = React.useState(false);

  React.useEffect(() => {
    api.privacy(mediaId).then(setBao).catch(() => setBao(null));
  }, [mediaId]);

  return (
    <div className="min-h-full bg-cream pb-10 pt-11">
      <ScreenHeader title="Ảnh của bạn được xử lý thế nào" onBack={onBack} />
      <div className="px-4">
        <h1 className="mb-3.5 mt-1.5 font-[family-name:var(--font-display)] text-2xl font-bold leading-tight">
          Mình lo quyền riêng tư
          <br />
          trước khi ảnh tới model
        </h1>

        {!bao ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <>
            <div className="mb-4 flex gap-2.5">
              <div className="flex-1">
                <div className="mb-1.5 text-[11px] font-bold text-muted">Ảnh gốc (chỉ ban quản lý mở được)</div>
                <div className="flex aspect-[3/4] items-center justify-center rounded-2xl bg-[repeating-linear-gradient(135deg,var(--color-skeleton-warm),var(--color-skeleton-warm)_8px,var(--color-skeleton-warm-deep)_8px,var(--color-skeleton-warm-deep)_16px)] font-mono text-[10px] font-semibold text-ink-faint">
                  {bao.has_original ? "đã khoá" : "không lưu"}
                </div>
              </div>
              <div className="flex-1">
                <div className="mb-1.5 text-[11px] font-bold text-leaf">Đã gửi cho AI</div>
                <div className="relative aspect-[3/4] overflow-hidden rounded-2xl bg-[repeating-linear-gradient(135deg,var(--color-skeleton),var(--color-skeleton)_8px,var(--color-skeleton-deep)_8px,var(--color-skeleton-deep)_16px)]">
                  {!daXoa && (
                    <AnhCoToken mediaId={bao.media_id} alt="Ảnh đã xử lý" className="h-full w-full object-cover" />
                  )}
                </div>
              </div>
            </div>

            <Card className="overflow-hidden p-0">
              <div className="flex border-b border-line px-4 py-3 text-xs font-extrabold text-muted">
                <span className="flex-[1.4]">Thông tin</span>
                <span className="flex-1">Ảnh gốc</span>
                <span className="flex-1 text-right">Đã gửi đi</span>
              </div>
              {bao.removed_fields.map((truong) => (
                <div key={truong.field} className="flex items-center border-b border-line-4 px-4 py-2.5 text-[13px] font-semibold">
                  <span className="flex-[1.4] text-ink-soft">{truong.label_vi}</span>
                  <span className="flex-1 truncate text-muted-2">{truong.value_before}</span>
                  <span className="flex flex-1 items-center justify-end gap-1.5 font-extrabold text-hazard-dark">
                    <IconTuChoi className="h-3.5 w-3.5" />
                    đã xoá
                  </span>
                </div>
              ))}
              <div className="flex items-center border-b border-line-4 px-4 py-2.5 text-[13px] font-semibold">
                <span className="flex-[1.4] text-ink-soft">Khuôn mặt</span>
                <span className="flex-1 text-muted-2">{bao.faces_blurred} khuôn mặt</span>
                <span className="flex flex-1 items-center justify-end gap-1.5 font-extrabold text-leaf-dark">
                  {bao.faces_blurred > 0 ? (
                    <>
                      <IconDuyet className="h-3.5 w-3.5" />
                      đã làm mờ
                    </>
                  ) : (
                    "không có"
                  )}
                </span>
              </div>
              <div className="flex items-center px-4 py-2.5 text-[13px] font-semibold">
                <span className="flex-[1.4] text-ink-soft">Kích thước</span>
                <span className="flex-1 text-muted-2">
                  {bao.original_size.width}×{bao.original_size.height} ({dungLuong(bao.original_size.bytes)})
                </span>
                <span className="flex-1 text-right font-extrabold text-leaf-dark">
                  {bao.processed_size.width}×{bao.processed_size.height} ({dungLuong(bao.processed_size.bytes)})
                </span>
              </div>
            </Card>

            <div className="mx-0.5 my-3.5 flex items-center gap-2 text-xs font-bold text-muted">
              <IconTuXoa className="h-4 w-4 flex-none" />
              Ảnh này sẽ tự động xoá {bao.expires_at ? `sau ${ngayVn(bao.expires_at)}` : "theo hạn lưu trữ"}.
            </div>
            <Button
              block
              variant="danger"
              disabled={daXoa}
              onClick={() => api.deleteMedia(bao.media_id).then(() => setDaXoa(true))}
            >
              {daXoa ? "Đã xoá khỏi hệ thống" : "Xoá ngay"}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

export function ScheduleScreen({
  buildingId,
  buildingName,
  onBack,
}: {
  buildingId: number | null;
  buildingName: string;
  onBack: () => void;
}) {
  const [lich, setLich] = React.useState<Awaited<ReturnType<typeof api.schedule>> | null>(null);
  const [loi, setLoi] = React.useState("");

  React.useEffect(() => {
    if (!buildingId) return;
    api
      .schedule(buildingId)
      .then(setLich)
      .catch((e) => setLoi(e.message));
  }, [buildingId]);

  const thu = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

  return (
    <div className="min-h-full bg-cream px-[18px] pb-[108px] pt-[54px]">
      <div className="mb-2 flex items-center gap-3">
        <button
          onClick={onBack}
          aria-label="Quay lại"
          className="flex h-[38px] w-[38px] cursor-pointer items-center justify-center rounded-full bg-surface shadow-[0_2px_8px_rgba(20,40,25,.08)]"
        >
          <IconQuayLai className="h-5 w-5" />
        </button>
        <div>
          <h1 className="m-0 font-[family-name:var(--font-display)] text-[28px] font-bold">Lịch thu gom</h1>
        </div>
      </div>
      <p className="m-0 mb-4 text-[13px] font-semibold text-muted">{buildingName} · xem được cả khi không có mạng</p>

      {!buildingId ? (
        <EmptyState icon={IconToaNha} title="Tài khoản chưa gắn với toà nào" hint="Liên hệ ban quản lý để gắn căn hộ." />
      ) : loi ? (
        <EmptyState icon={IconLichThuGom} title="Chưa tải được lịch" hint={loi} />
      ) : !lich ? (
        <Skeleton className="h-52 w-full" />
      ) : (
        <>
          <Card className="gb-hscroll mb-4 p-3">
            <div className="grid min-w-[340px] gap-1.5" style={{ gridTemplateColumns: "auto repeat(7, 1fr)" }}>
              <span />
              {thu.map((t) => (
                <span key={t} className="text-center text-[11px] font-extrabold text-muted">
                  {t}
                </span>
              ))}
              {lich.items.map((row) => (
                <React.Fragment key={row.category_code}>
                  <span className="flex items-center gap-1.5 whitespace-nowrap text-xs font-bold" style={{ color: row.bin_color }}>
                    <span className="h-2.5 w-2.5 rounded-md" style={{ background: row.bin_color }} />
                    {row.category_name}
                  </span>
                  {[0, 1, 2, 3, 4, 5, 6].map((d) => (
                    <span
                      key={d}
                      className="h-[26px] rounded-md"
                      style={{ background: row.weekdays.includes(d) ? row.bin_color : "var(--color-schedule-off)" }}
                      title={row.weekdays.includes(d) ? `${row.window} · ${row.location}` : "không thu gom"}
                    />
                  ))}
                </React.Fragment>
              ))}
            </div>
          </Card>

          <div className="mx-0.5 mb-2 mt-4 text-[13px] font-bold text-muted">Điểm tập kết trong toà</div>
          <Card className="p-4">
            {lich.items.map((row) => (
              <div key={row.category_code} className="flex justify-between border-b border-line-4 py-2 text-sm font-bold last:border-0">
                <span>{row.location}</span>
                <span className="font-semibold text-muted">
                  {row.category_name} · {row.window}
                </span>
              </div>
            ))}
          </Card>
        </>
      )}
    </div>
  );
}

export function RequestsScreen({ onOpen, onCreate }: { onOpen: (id: number) => void; onCreate: () => void }) {
  const [items, setItems] = React.useState<PickupRequest[] | null>(null);

  React.useEffect(() => {
    api.pickups().then((d) => setItems(d.items)).catch(() => setItems([]));
  }, []);

  return (
    <div className="relative min-h-full bg-cream px-[18px] pb-[108px] pt-[54px]">
      <h1 className="m-0 mb-1 font-[family-name:var(--font-display)] text-[28px] font-bold">Yêu cầu của tôi</h1>
      <p className="m-0 mb-4 text-[13px] font-semibold text-muted">Thu gom đồ cồng kềnh & rác tái chế khối lượng lớn</p>
      {items === null ? (
        <Skeleton className="h-24 w-full" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={IconMonDo}
          title="Chưa có yêu cầu nào"
          hint="Chụp món rác đầu tiên để bắt đầu nhé."
          minhHoa={
            // eslint-disable-next-line @next/next/no-img-element
            <img src="/illus/cay-chau.svg" alt="" aria-hidden="true" className="h-20 w-20 object-contain" />
          }
        />
      ) : (
        items.map((yc, i) => {
          const tt = TRANG_THAI_YEU_CAU[yc.status] ?? {
            label: yc.status,
            icon: IconChoDuyet,
            className: "bg-muted-bg text-muted",
          };
          return (
            <Card key={yc.id} onClick={() => onOpen(yc.id)} className="mb-3 cursor-pointer overflow-hidden p-0 animate-gbreveal" style={{ animationDelay: `${Math.min(i, 7) * 0.06}s`, animationFillMode: "both" }}>
              {/* Viền trái màu trạng thái — nhìn nhanh biết yêu cầu đang ở đâu */}
              <div className="flex">
                <div className={`w-1.5 flex-none ${tt.className}`} />
                <div className="flex-1 p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-extrabold text-bulky">#PR-{String(yc.id).padStart(4, "0")}</span>
                    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-extrabold ${tt.className}`}>
                      <tt.icon className="h-3.5 w-3.5" />
                      {tt.label}
                    </span>
                  </div>
                  <div className="mb-1 text-[15px] font-bold">{yc.items.map((i) => i.name).join(", ")}</div>
                  <div className="text-[13px] font-semibold text-muted">
                    {kg(yc.weight_max_kg)} · mong muốn {ngayVn(yc.preferred_date)}
                    {yc.route ? ` · đi cùng ${Math.max(0, yc.route.stop_count - 1)} hộ khác` : ""}
                  </div>
                  <TrackYeuCau status={yc.status} />
                </div>
              </div>
            </Card>
          );
        })
      )}

      <button
        type="button"
        onClick={onCreate}
        aria-label="Tạo yêu cầu thu gom mới"
        title="Tạo yêu cầu thu gom mới"
        className="fixed bottom-[calc(84px+env(safe-area-inset-bottom)+12px)] right-[max(14px,calc((100vw_-_560px)/2_+_14px))] z-40 flex h-14 w-14 cursor-pointer items-center justify-center rounded-full bg-leaf text-white shadow-[0_8px_20px_-4px_rgba(47,174,102,.55)] transition-transform active:scale-95"
      >
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
      </button>
    </div>
  );
}

/** Track 4 bước: Đặt → Xác nhận → Đang tới → Xong. Vẽ từ trạng thái THẬT của
 *  yêu cầu; bước chưa tới thì mờ đi — màu không phải kênh duy nhất. */
function TrackYeuCau({ status }: { status: string }) {
  const buoc = TRACK_YEU_CAU[status] ?? 0;
  const NHAN = ["Đặt", "Xác nhận", "Đang tới", "Xong"];
  return (
    <div className="mt-3">
      <div className="flex items-center">
        {NHAN.map((ten, i) => {
          const xong = i < buoc;
          const dangChay = i === buoc;
          return (
            <React.Fragment key={ten}>
              {i > 0 && (
                <div className={`mx-1 h-[3px] flex-1 rounded-full ${i <= buoc ? "bg-leaf" : "bg-line-2"}`} />
              )}
              <span
                className={`flex h-[20px] w-[20px] flex-none items-center justify-center rounded-full text-[10px] font-extrabold ${
                  xong
                    ? "bg-leaf text-white"
                    : dangChay
                      ? "animate-gbpulse border-2 border-leaf bg-surface text-leaf-dark"
                      : "border-2 border-line-2 bg-surface text-muted"
                }`}
              >
                {xong ? "✓" : i + 1}
              </span>
            </React.Fragment>
          );
        })}
      </div>
      <div className="mt-1.5 flex justify-between">
        {NHAN.map((ten, i) => (
          <span
            key={ten}
            className={`text-[10px] font-bold ${i === buoc ? "text-leaf-dark" : i < buoc ? "text-ink-soft" : "text-muted"}`}
          >
            {ten}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Số bước đã hoàn thành của track, theo trạng thái yêu cầu. */
const TRACK_YEU_CAU: Record<string, number> = {
  cho_duyet: 1,
  cho_nhan: 1,
  da_nhan: 2,
  dang_van_chuyen: 3,
  da_giao_don_vi: 3,
  tranh_chap: 2,
  hoan_tat: 4,
  tu_choi: 1,
  da_huy: 1,
};

export function RequestDetailScreen({ id, onBack }: { id: number; onBack: () => void }) {
  const [yc, setYc] = React.useState<PickupRequest | null>(null);
  const [loi, setLoi] = React.useState("");

  const tai = React.useCallback(() => {
    api.pickup(id).then(setYc).catch((e) => setLoi(e.message));
  }, [id]);
  React.useEffect(tai, [tai]);

  if (loi) return <EmptyState icon={IconGapLoi} title="Không mở được yêu cầu" hint={loi} />;
  if (!yc) return <Skeleton className="m-4 h-64" />;

  const tt = TRANG_THAI_YEU_CAU[yc.status] ?? {
    label: yc.status,
    icon: IconChoDuyet,
    className: "bg-muted-bg text-muted",
  };

  return (
    <div className="min-h-full bg-cream pb-10 pt-11">
      <ScreenHeader title={`#PR-${String(yc.id).padStart(4, "0")}`} onBack={onBack} />
      <div className="px-[18px]">
        <div className="mb-3.5 flex items-center justify-between">
          <h1 className="m-0 font-[family-name:var(--font-display)] text-[22px] font-bold">
            {yc.items.map((i) => i.name).join(", ")}
          </h1>
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-extrabold ${tt.className}`}>
            <tt.icon className="h-3.5 w-3.5" />
            {tt.label}
          </span>
        </div>

        <Card className="p-4">
          {(yc.timeline ?? []).map((moc, i) => (
            <div key={i} className="flex items-start gap-3 pb-4 last:pb-0">
              <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-leaf text-white">
                <IconDuyet className="h-3.5 w-3.5" strokeWidth={3} />
              </span>
              <div className="flex-1">
                <div className="text-xs font-extrabold text-muted">{new Date(moc.at).toLocaleString("vi-VN")}</div>
                <div className="text-sm font-bold leading-snug">{moc.label_vi}</div>
              </div>
            </div>
          ))}
          {yc.status === "cho_duyet" && (
            <div className="flex items-start gap-3">
              <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-amber-line text-amber">
                <IconChoDuyet className="h-3.5 w-3.5" />
              </span>
              <div className="text-sm font-bold text-amber">Chờ ban quản lý duyệt</div>
            </div>
          )}
        </Card>

        {yc.route && (
          <div className="mt-3 flex gap-2.5 rounded-2xl bg-leaf-soft p-4 text-[13px] font-bold leading-relaxed text-leaf-dark">
            <IconXeThuGom className="h-4 w-4 flex-none" />
            Yêu cầu của bạn đi cùng chuyến với {Math.max(0, yc.route.stop_count - 1)} hộ khác trong toà — giảm{" "}
            {yc.route.saved_trips} chuyến xe.
          </div>
        )}

        {yc.reject_reason && (
          <div className="mt-3 rounded-2xl border border-hazard-light bg-hazard-soft p-4 text-[13px] font-bold text-hazard-dark">
            Bị từ chối: {yc.reject_reason}
            {yc.review_note ? ` — ${yc.review_note}` : ""}
          </div>
        )}

        {["cho_duyet", "cho_nhan"].includes(yc.status) && (
          <Button
            block
            variant="danger"
            className="mt-3.5"
            onClick={() => api.cancelPickup(yc.id).then(tai).catch((e) => setLoi(e.message))}
          >
            Huỷ yêu cầu
          </Button>
        )}
      </div>
    </div>
  );
}

/** Lịch sử theo vật liệu — R-04.
 *
 *  Thanh ngang so TƯƠNG ĐỐI số món giữa các vật liệu, không phải phần trăm của
 *  cái gì cả. Cố tình KHÔNG có kg theo từng loại: cân nặng chỉ ước lượng ở mức
 *  cả yêu cầu, chia ra từng món là bịa một con số dữ liệu không đỡ nổi. Tổng kg
 *  hiện dạng khoảng, đúng như server trả.
 */
function LichSuVatLieu() {
  const [ls, setLs] = React.useState<Awaited<ReturnType<typeof api.meHistory>> | null>(null);
  const [loi, setLoi] = React.useState("");

  React.useEffect(() => {
    api
      .meHistory()
      .then(setLs)
      .catch((e) => setLoi(e instanceof Error ? e.message : "Chưa tải được lịch sử."));
  }, []);

  if (loi) {
    return (
      <Card className="mb-3.5 p-4 text-[13px] font-semibold text-muted">Chưa tải được lịch sử: {loi}</Card>
    );
  }
  if (!ls) return <Skeleton className="mb-3.5 h-40 w-full" />;

  const soLon = Math.max(1, ...ls.theo_vat_lieu.map((d) => d.so_mon));
  const so = (n: number) => n.toLocaleString("vi-VN", { maximumFractionDigits: 1 });

  return (
    <Card className="mb-3.5 p-4">
      <div className="mb-3 text-sm font-extrabold">Lịch sử theo vật liệu</div>

      <div className="mb-3 flex gap-2">
        <div className="flex-1 rounded-xl bg-muted-bg p-3">
          <div className="text-[11px] font-bold text-muted">Yêu cầu đã gửi</div>
          <div className="text-lg font-extrabold">{ls.tong.so_yeu_cau}</div>
          <div className="text-[11px] font-semibold text-muted">đã thu {ls.tong.so_yeu_cau_da_thu}</div>
        </div>
        <div className="flex-1 rounded-xl bg-muted-bg p-3">
          <div className="text-[11px] font-bold text-muted">Khối lượng ước lượng</div>
          <div className="text-lg font-extrabold leading-tight">
            {so(ls.tong.khoi_luong_min_kg)} – {so(ls.tong.khoi_luong_max_kg)}
            <span className="text-[13px]"> kg</span>
          </div>
          <div className="text-[11px] font-semibold text-muted">là khoảng, không phải cân thật</div>
        </div>
      </div>

      {ls.theo_vat_lieu.length === 0 ? (
        <div className="rounded-xl bg-muted-bg p-3 text-[13px] font-semibold text-muted">
          Chưa có gì để tổng hợp. Hỏi phân loại hoặc đăng ký thu gom là bắt đầu có lịch sử.
        </div>
      ) : (
        ls.theo_vat_lieu.map((d, i) => (
          <div key={d.category_code} className="border-b border-line-4 py-2.5 last:border-0 animate-gbreveal" style={{ animationDelay: `${Math.min(i, 7) * 0.06}s`, animationFillMode: "both" }}>
            <div className="mb-1.5 flex items-baseline justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5 text-[13px] font-bold">
                <span className="h-2.5 w-2.5 flex-none rounded-md" style={{ background: d.bin_color }} />
                <span className="truncate">{d.category_name}</span>
              </span>
              <span className="flex-none text-[12px] font-semibold text-muted">
                <b className="text-ink">{d.so_mon}</b> món · <b className="text-ink">{d.so_lan_hoi}</b> lần hỏi
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted-bg">
              <div
                className="h-full rounded-full"
                style={{ width: `${Math.round((d.so_mon / soLon) * 100)}%`, background: d.bin_color }}
              />
            </div>
          </div>
        ))
      )}

      <p className="m-0 mt-3 text-[11px] font-semibold leading-relaxed text-muted">{ls.ghi_chu}</p>
    </Card>
  );
}

/** Ô sửa hồ sơ. Chọn toà trước rồi mới chọn căn — danh sách căn hộ lấy theo toà
 *  chứ không dồn mọi căn của mọi toà vào một ô chọn dài dằng dặc. */
function SuaHoSo({ user, onXong, onHuy }: { user: User; onXong: () => void; onHuy: () => void }) {
  const { capNhatPhien } = useSession();
  const [ten, setTen] = React.useState(user.full_name);
  const [toaId, setToaId] = React.useState<number | null>(user.building_id);
  const [canHoId, setCanHoId] = React.useState<number | null>(null);
  const [dsToa, setDsToa] = React.useState<{ id: number; code: string; name: string }[]>([]);
  const [dsCanHo, setDsCanHo] = React.useState<{ id: number; code: string; building_id: number }[]>([]);
  const [dangLuu, setDangLuu] = React.useState(false);
  const [chacBo, setChacBo] = React.useState(false);
  const [chacToa, setChacToa] = React.useState(false);
  const [loi, setLoi] = React.useState("");

  React.useEffect(() => {
    api.buildings().then((d) => setDsToa(d.items)).catch(() => setDsToa([]));
  }, []);

  // Đổi toà thì phải tải lại danh sách căn và BỎ lựa chọn cũ — giữ lại một căn
  // thuộc toà khác là gửi lên server một cặp toà/căn mâu thuẫn.
  React.useEffect(() => {
    setCanHoId(null);
    if (toaId === null) {
      setDsCanHo([]);
      return;
    }
    api.units(toaId).then((d) => setDsCanHo(d.items)).catch(() => setDsCanHo([]));
  }, [toaId]);

  /** Gom payload sửa hồ sơ — tách rõ ba nghĩa, không dùng `null` mơ hồ:
   *  - toaId có giá trị → gắn/chuyển toà (building_id).
   *  - toaId rỗng mà trước đó có toà → bỏ cả toà (xoa_toa, kéo theo bỏ căn).
   *  - canHoId có giá trị → gắn/chuyển căn (unit_id). */
  function payloadLuu(): Record<string, unknown> {
    const p: Record<string, unknown> = { full_name: ten };
    if (toaId !== null) p.building_id = toaId;
    else if (user.building_id !== null) p.xoa_toa = true;
    if (canHoId !== null) p.unit_id = canHoId;
    return p;
  }

  async function gui(payload: { full_name?: string; unit_id?: number; xoa_can_ho?: boolean; building_id?: number | null; xoa_toa?: boolean }) {
    setDangLuu(true);
    setLoi("");
    try {
      capNhatPhien(await api.updateMe(payload));
      onXong();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không lưu được thay đổi.");
    } finally {
      setDangLuu(false);
    }
  }

  const o = "w-full rounded-xl border border-line-3 bg-surface px-3 py-2 text-sm font-semibold outline-none focus:border-ink";

  return (
    <Card className="mb-5 p-4">
      <label className="mb-1 block text-xs font-bold text-muted">Tên hiển thị</label>
      <input value={ten} onChange={(e) => setTen(e.target.value)} maxLength={120} className={`${o} mb-3`} />

      <label className="mb-1 block text-xs font-bold text-muted">Toà</label>
      <select
        value={toaId ?? ""}
        onChange={(e) => setToaId(e.target.value ? Number(e.target.value) : null)}
        className={`${o} mb-3`}
      >
        <option value="">— chưa chọn —</option>
        {dsToa.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>

      <label className="mb-1 block text-xs font-bold text-muted">Căn hộ</label>
      <select
        value={canHoId ?? ""}
        onChange={(e) => setCanHoId(e.target.value ? Number(e.target.value) : null)}
        disabled={dsCanHo.length === 0}
        className={`${o} mb-1`}
      >
        <option value="">{toaId === null ? "— chọn toà trước —" : "— giữ nguyên —"}</option>
        {dsCanHo.map((c) => (
          <option key={c.id} value={c.id}>
            {c.code}
          </option>
        ))}
      </select>
      <p className="m-0 mb-3 text-[11px] font-semibold text-muted">
        Đổi căn hộ là đổi luôn lịch thu gom và thứ tự danh sách điểm gửi.
      </p>

      {loi && <div className="mb-3 text-[12px] font-bold text-hazard-dark">{loi}</div>}

      <div className="mb-2 flex gap-2">
        <Button
          block
          disabled={dangLuu || !ten.trim()}
          onClick={() => gui(payloadLuu())}
        >
          {dangLuu ? "Đang lưu…" : "Lưu thay đổi"}
        </Button>
        <Button variant="ghost" disabled={dangLuu} onClick={onHuy}>
          Huỷ
        </Button>
      </div>

      {user.building_id !== null && (
        <div className="flex flex-col gap-2">
          <button
            disabled={dangLuu}
            onClick={() => (chacBo ? gui({ xoa_can_ho: true, full_name: ten }) : setChacBo(true))}
            className="w-full cursor-pointer rounded-xl border border-line-3 bg-surface px-3 py-2 text-[13px] font-bold text-hazard-dark"
          >
            {chacBo ? "Chắc chắn bỏ căn hộ? Bấm lần nữa" : "Bỏ gắn căn hộ"}
          </button>
          <button
            disabled={dangLuu}
            onClick={() => (chacToa ? gui({ xoa_toa: true, full_name: ten }) : setChacToa(true))}
            className="w-full cursor-pointer rounded-xl border border-line-3 bg-surface px-3 py-2 text-[13px] font-bold text-hazard-dark"
          >
            {chacToa ? "Chắc chắn bỏ toà? Bấm lần nữa" : "Bỏ gắn toà"}
          </button>
        </div>
      )}
    </Card>
  );
}

/** Màn Điểm xanh — tổng điểm, streak, cấp độ, huy hiệu.
 *
 * Mọi con số đều từ dữ liệu THẬT: điểm từ `user.green_points`, streak đếm
 * hoạt động phân loại thật trên máy, cấp tính từ điểm. Không vẽ số ảo.
 */
export function DiemXanhScreen({ user, onBack }: { user: User; onBack: () => void }) {
  const diem = user.green_points;
  const cap = tinhCap(diem);
  const [streak, setStreak] = React.useState(0);
  const [coYeuCauThuGom, setCoYeuCauThuGom] = React.useState(false);

  React.useEffect(() => {
    setStreak(tinhStreak());
  }, []);

  React.useEffect(() => {
    let huy = false;
    api.pickups()
      .then((d) => { if (!huy) setCoYeuCauThuGom(d.items.length > 0); })
      .catch(() => { if (!huy) setCoYeuCauThuGom(false); })
      .finally(() => { /* rơi êm */ });
    return () => { huy = true; };
  }, []);

  const HUY_HIEU = [
    { icon: Recycle, ten: "Tách đúng nhóm", moTa: "Phân loại đúng món đầu tiên", daMo: diem > 0 },
    { icon: IconChupAnh, ten: "Lần chụp đầu", moTa: "Chụp ảnh món rác", daMo: diem > 0 },
    { icon: Flame, ten: "Streak 7 ngày", moTa: "Phân loại 7 ngày liên tiếp", daMo: streak >= 7 },
    { icon: IconXeThuGom, ten: "Chuyến gộp", moTa: "Đặt lịch thu gom", daMo: coYeuCauThuGom },
  ];

  return (
    <div className="min-h-full bg-[linear-gradient(180deg,var(--color-nen-ho-so)_0%,var(--color-cream)_42%)] px-5 pb-[108px] pt-[54px] lg:mx-auto lg:max-w-[1080px] lg:px-8">
      <div className="mb-2 flex items-center gap-3">
        <button
          onClick={onBack}
          aria-label="Quay lại"
          className="flex h-[38px] w-[38px] cursor-pointer items-center justify-center rounded-full bg-surface shadow-[0_2px_8px_rgba(20,40,25,.08)]"
        >
          <IconQuayLai className="h-5 w-5" />
        </button>
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Điểm xanh của bạn</div>
      </div>

      {/* thẻ hero: cấp + điểm + thanh tiến độ */}
      <div className="relative mt-3 overflow-hidden rounded-2xl border border-line bg-surface p-4 pb-5 text-center shadow-[0_2px_10px_rgba(20,40,25,.05)]">
        <div className="absolute left-4 top-4 rounded-full bg-leaf-soft px-3 py-1.5 text-[11px] font-extrabold tracking-wide text-leaf-dark">
          CẤP · {cap.ten.toUpperCase()} {cap.icon}
        </div>
        <div className="mb-1 mt-10 flex h-[150px] items-end justify-center">
          {/* Cây cấp độ — minh hoạ SVG đơn giản theo mức, đổi theo cấp */}
          <CayCapDo level={CAP_DO.findIndex((c) => c.ten === cap.ten)} />
        </div>
        <div className="font-[family-name:var(--font-display)] text-[40px] font-bold leading-none text-leaf-dark tabular-nums">
          <NumberFlow value={diem} locales="vi-VN" />
        </div>
        <div className="mt-1 text-[13px] font-semibold text-ink-soft">
          điểm xanh · {cap.conThieu > 0 ? `còn ${cap.conThieu} điểm để lên Cây kế tiếp` : "đã đạt cấp cao nhất"}
        </div>
        <div className="mx-5 mt-3 h-2.5 overflow-hidden rounded-full bg-leaf-soft">
          <div className="animate-gbfill h-full rounded-full bg-gradient-to-r from-leaf to-leaf-mint" style={{ width: `${cap.phanTram}%` }} />
        </div>
      </div>

      {/* streak */}
      <div className="mt-3.5 flex items-center gap-3.5 rounded-2xl bg-amber-soft px-4 py-4">
        <span className="flex h-10 w-10 flex-none items-center justify-center rounded-xl bg-amber-soft text-amber">
          <Flame className="h-6 w-6" strokeWidth={1.9} />
        </span>
        <div className="flex-1">
          <div className="font-[family-name:var(--font-display)] text-[19px] font-bold leading-tight text-amber">
            {streak > 0 ? `${streak} ngày liên tiếp` : "Bắt đầu hôm nay"}
          </div>
          <div className="mt-0.5 text-[12.5px] font-semibold text-ink-soft">
            {streak > 0 ? "Quay lại mai để giữ chuỗi nhé!" : "Phân loại một món là bắt đầu chuỗi của bạn"}
          </div>
        </div>
      </div>

      {/* huy hiệu */}
      <div className="mt-5 text-[15px] font-bold">Huy hiệu</div>
      <div className="mt-3 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        {HUY_HIEU.map((h, i) => (
          <div
            key={h.ten}
            className={`rounded-lg border p-3 text-center animate-gbreveal ${
              h.daMo ? "border-line bg-surface shadow-[0_2px_10px_rgba(20,40,25,.05)]" : "border-dashed border-line bg-cream opacity-60"
            }`}
            style={{ animationDelay: `${Math.min(i, 7) * 0.06}s`, animationFillMode: "both" }}
          >
            <div className={`flex items-center justify-center ${h.daMo ? "" : "grayscale"}`}>
              <h.icon className="h-7 w-7" strokeWidth={1.8} />
            </div>
            <div className="mt-1 text-[12px] font-bold">{h.ten}</div>
            <div className="mt-0.5 text-[10.5px] font-semibold text-muted">{h.moTa}</div>
          </div>
        ))}
      </div>

      <p className="mt-4 text-center text-[11px] font-semibold leading-relaxed text-muted">
        Điểm xanh cộng khi yêu cầu thu gom của bạn hoàn tất. Streak đếm số ngày bạn phân loại trên máy này.
      </p>
    </div>
  );
}

/** Cây cấp độ dạng SVG đơn giản — mọc theo 4 mức (Mầm → Rừng). Giữ nét bo tròn,
 *  không phải ảnh tải thêm, đổi màu theo cấp. */
function CayCapDo({ level }: { level: number }) {
  const L = Math.max(0, Math.min(3, level));
  const cao = 34 + L * 26;
  const la = L + 1;
  return (
    <svg width="120" height="140" viewBox="0 0 120 140" fill="none" aria-hidden="true">
      {/* chậu */}
      <path d="M34 118h52l-5 12H39z" fill="#c67139" />
      <rect x="30" y="110" width="60" height="8" rx="4" fill="#a85f30" />
      <rect x="40" y="118" width="40" height="6" rx="3" fill="#4a3524" />
      {/* thân */}
      <rect x="57" y={140 - 24 - cao} width="6" height={cao} rx="3" fill="#728157" />
      {/* lá */}
      {Array.from({ length: la }).map((_, i) => (
        <ellipse
          key={i}
          cx={i % 2 === 0 ? 78 : 42}
          cy={140 - 30 - cao * (0.35 + i * 0.25)}
          rx="16"
          ry="9"
          fill="#2fae66"
          transform={`rotate(${i % 2 === 0 ? 18 : -18} ${i % 2 === 0 ? 78 : 42} ${140 - 30 - cao * (0.35 + i * 0.25)})`}
        />
      ))}
      {L === 3 && <circle cx="60" cy={140 - 40 - cao} r="9" fill="#ffb88c" />}
    </svg>
  );
}

export function MeScreen({ user, onPrivacy, onLogout, onDiemXanh }: { user: User; onPrivacy: () => void; onLogout: () => void; onDiemXanh: () => void }) {
  const [dangSua, setDangSua] = React.useState(false);
  const [xemDiemNhanThuc, setXemDiemNhanThuc] = React.useState(false);

  if (xemDiemNhanThuc) {
    return <DiemNhanThucScreen onBack={() => setXemDiemNhanThuc(false)} />;
  }

  return (
    <div className="min-h-full bg-cream px-[18px] pb-[108px] pt-[54px] lg:mx-auto lg:max-w-[1080px] lg:px-8">
      <div className="mb-5 flex items-center gap-3.5">
        <div className="flex h-[60px] w-[60px] items-center justify-center overflow-hidden rounded-2xl bg-leaf-soft">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/avatar/cu-dan.svg" alt="Avatar cư dân" className="h-[60px] w-[60px] object-contain" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="font-[family-name:var(--font-display)] text-xl font-bold">{user.full_name}</div>
          <div className="text-[13px] font-semibold text-muted">
            {user.unit ? `Căn ${user.unit} · ` : ""}
            {user.building || "Chưa gắn toà"}
          </div>
        </div>
        {!dangSua && (
          <button
            onClick={() => setDangSua(true)}
            className="flex-none cursor-pointer rounded-full border border-line-3 bg-surface px-3.5 py-1.5 text-[13px] font-bold"
          >
            Sửa
          </button>
        )}
      </div>

      {dangSua && (
        <SuaHoSo
          key={`${user.full_name}|${user.building_id}`}
          user={user}
          onXong={() => setDangSua(false)}
          onHuy={() => setDangSua(false)}
        />
      )}

      <div className="lg:grid lg:grid-cols-2 lg:gap-5 lg:items-start">
        <div className="lg:col-span-2"><LichSuVatLieu /></div>

      <Card className="mb-3.5 overflow-hidden p-0">
        <button onClick={onPrivacy} className="flex w-full cursor-pointer items-center gap-3 border-b border-line-4 px-4 py-4 text-left">
          <IconKhoa className="h-[18px] w-[18px] text-muted" />
          <span className="flex-1 text-sm font-bold">Ảnh của tôi được xử lý thế nào</span>
          <IconTiepTuc className="h-[18px] w-[18px] text-line-faint" />
        </button>
        <button
          onClick={onDiemXanh}
          className="flex w-full cursor-pointer items-center gap-3 px-4 py-4 text-left"
        >
          <IconMamXanh className="h-[18px] w-[18px] text-leaf" />
          <span className="flex-1 text-sm font-bold">Điểm xanh</span>
          <span className="text-sm font-extrabold text-leaf-dark">{user.green_points}</span>
          <IconTiepTuc className="h-[18px] w-[18px] text-line-faint" />
        </button>
        <button
          onClick={() => setXemDiemNhanThuc(true)}
          className="flex w-full cursor-pointer items-center gap-3 px-4 py-4 text-left"
        >
          <IconNguoiDung className="h-[18px] w-[18px] text-amber" />
          <span className="flex-1 text-sm font-bold">Điểm nhận thức</span>
          <IconTiepTuc className="h-[18px] w-[18px] text-line-faint" />
        </button>
      </Card>

      <div className="lg:space-y-3.5">
      <CaiAppCard />

      <div className="mb-3.5 rounded-2xl bg-muted-bg p-4">
        <div className="mb-2 text-xs font-bold text-muted">QUYỀN CỦA CƯ DÂN</div>
        <div className="flex flex-col gap-1 text-[13px] font-semibold leading-relaxed text-ink-faint">
          <span className="flex items-start gap-1.5">
            <IconDuyet className="mt-0.5 h-3.5 w-3.5 flex-none text-leaf" />
            Hỏi phân loại · đăng ký thu gom
          </span>
          <span className="flex items-start gap-1.5">
            <IconDuyet className="mt-0.5 h-3.5 w-3.5 flex-none text-leaf" />
            Xem yêu cầu của chính mình
          </span>
          <span className="flex items-start gap-1.5 text-ink-disabled">
            <IconTuChoi className="mt-0.5 h-3.5 w-3.5 flex-none" />
            Duyệt yêu cầu · xem ảnh cư dân khác · trang vận hành
          </span>
        </div>
      </div>
      </div>
      </div>

      <Button block variant="danger" onClick={onLogout}>
        Đăng xuất
      </Button>
    </div>
  );
}
