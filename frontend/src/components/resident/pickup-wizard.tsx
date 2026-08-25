"use client";

/** Wizard đăng ký thu gom đồ cồng kềnh — 3 bước + màn xác nhận.
 *
 * Hai chi tiết không được cắt:
 * - bước 2 đánh dấu khung giờ **đã có chuyến của toà**, kèm câu nói rõ chọn
 *   khung đó tiết kiệm được một chuyến xe (giá trị kinh doanh hiện ra trước
 *   mắt người dùng, không giấu trong báo cáo);
 * - bước 3 nói **ngưỡng bằng con số cụ thể** trước khi bấm gửi, để người dùng
 *   hiểu vì sao mình phải chờ.
 */

import * as React from "react";

import { Button, Card } from "@/components/ui/primitives";
import { AnhCoToken } from "@/lib/anh-co-token";
import { api } from "@/lib/api";
import { kg, ngayVn } from "@/lib/format";
import { IconChoDuyet, IconDuyet, IconQuayLai, IconTuChoi, IconXeThuGom } from "@/lib/icons";
import { useSession } from "@/lib/session";
import type { Classification, PickupRequest, ScheduleHint, WasteCategory } from "@/lib/types";

interface MonRac {
  name: string;
  category_code: string;
  qty: number;
  est_weight_kg: number;
  media_id: number | null;
}

const NGUONG_KG_MAC_DINH = 30;

// Hai nhóm cư dân được chọn khi thêm món. Tên hiển thị LẤY TỪ API (`GET /categories`,
// `api.categories()` đã có sẵn) — tên nằm trong CSDL, có thể được sửa ở màn quản lý.
// Bảng này chỉ là nhãn tối thiểu khi danh mục chưa tải xong hoặc gọi hỏng, để
// wizard vẫn thêm được món mà không chặn cả luồng.
const HAI_NHOM: string[] = ["recyclable", "bulky"];
const NHOM_LOI_THEO_MA: Record<string, string> = {
  recyclable: "Rác tái chế",
  bulky: "Đồ cồng kềnh",
};

function tenNhom(ma: string, danhMuc: WasteCategory[]): string {
  const nhom = danhMuc.find((c) => c.code === ma);
  if (nhom) return nhom.name;
  return NHOM_LOI_THEO_MA[ma] ?? ma;
}

// Giờ tự chọn nằm trong 06:00–22:00. Chọn giờ ngoài lịch của toà → cần BQL duyệt.
const KHUNG_TU_CHON = ["06:00-08:00", "08:00-10:00", "10:00-12:00", "13:00-15:00", "15:00-17:00", "17:00-19:00", "19:00-22:00"];

export function PickupWizard({
  goiYTuKetQua,
  scheduleHint,
  onBack,
  onDone,
}: {
  goiYTuKetQua?: Classification | null;
  scheduleHint?: ScheduleHint;
  onBack: () => void;
  onDone: (yeuCau: PickupRequest) => void;
}) {
  const [buoc, setBuoc] = React.useState(1);
  const [mon, setMon] = React.useState<MonRac[]>(() =>
    goiYTuKetQua?.category
      ? [
          {
            name: goiYTuKetQua.item_name || goiYTuKetQua.category.name,
            category_code: goiYTuKetQua.category.code,
            qty: 1,
            est_weight_kg: 30,
            media_id: goiYTuKetQua?.media_id ?? null,
          },
        ]
      : [],
  );
  const [ngay, setNgay] = React.useState("");
  const [khungGio, setKhungGio] = React.useState("");
  const [laGioNgoaiLich, setLaGioNgoaiLich] = React.useState(false);
  const [ghiChu, setGhiChu] = React.useState("");
  const [daTick, setDaTick] = React.useState(false);
  const [dangGui, setDangGui] = React.useState(false);
  const [loi, setLoi] = React.useState("");
  const [ketQua, setKetQua] = React.useState<PickupRequest | null>(null);
  const [dangTaiAnh, setDangTaiAnh] = React.useState<number | null>(null);
  // Điểm lấy hàng của riêng yêu cầu này (`CreatePickupRequest.address`). Hộ dân
  // lẻ chưa gắn căn hộ thì bắt buộc; cư dân có căn hộ để trống là lấy tại nơi ở.
  const { user } = useSession();
  const [diaChi, setDiaChi] = React.useState("");
  // Tên nhóm rác lấy từ API để hiện tiếng Việt thay cho mã kỹ thuật (`bulky`…).
  // Gọi hỏng KHÔNG chặn wizard — lui về nhãn tối thiểu ở `tenNhom`.
  const [danhMuc, setDanhMuc] = React.useState<WasteCategory[]>([]);

  React.useEffect(() => {
    let song = true;
    api.categories()
      .then((r) => {
        if (song) setDanhMuc(r.items);
      })
      .catch(() => {
        // Danh mục lỗi: giữ danhMuc rỗng, người dùng vẫn thêm món được.
      });
    return () => {
      song = false;
    };
  }, []);

  const tongKg = mon.reduce((s, m) => s + m.est_weight_kg * m.qty, 0);
  // Món mới bắt đầu với tên trống (thay "Món mới" cứng) — phải có tên mới gửi
  // được, máy chủ từ chối món tên rỗng (`PickupItem.name` min_length=1).
  const thieuTen = mon.some((m) => !m.name.trim());
  const vuotNguong = tongKg * 1.4 > NGUONG_KG_MAC_DINH;
  // `user.unit` rỗng nghĩa là chưa gắn căn hộ (serializer `user_dict` trả chuỗi
  // rỗng khi `unit_id` None) — tín hiệu có sẵn, không gọi thêm API.
  const coCanHo = Boolean(user?.unit);
  const thieuDiaChi = !coCanHo && !diaChi.trim();

  const khungBQL = React.useMemo(() => {
    // Chỉ lấy khung có chuyến thật của toà. Bỏ 2 khung cứng cũ — giờ ngoài lịch
    // do cư dân tự chọn ở phần "Chọn giờ khác" bên dưới.
    const chuyenDaCo = scheduleHint?.khung_gio_da_co_chuyen ?? [];
    return chuyenDaCo.map((c) => ({
      key: `${c.service_date}|${c.window}`,
      ngay: c.service_date,
      window: c.window,
      ghiChu: c.ghi_chu,
    }));
  }, [scheduleHint?.khung_gio_da_co_chuyen]);

  async function gui() {
    setDangGui(true);
    setLoi("");
    try {
      if (ngay && ngay < new Date().toISOString().slice(0, 10)) {
        setLoi("Ngày mong muốn không thể ở quá khứ, chọn lại giúp mình nhé.");
        setDangGui(false);
        return;
      }
      if (thieuDiaChi) {
        setLoi("Vui lòng nhập địa chỉ lấy hàng để đội vệ sinh biết chỗ đến.");
        setDangGui(false);
        return;
      }
      const yeuCau = await api.createPickup({
        items: mon,
        est_weight_kg: tongKg,
        preferred_date: ngay || null,
        preferred_window: khungGio,
        note: ghiChu,
        confirmed_no_hazardous: daTick,
        ngoai_lich: laGioNgoaiLich,
        address: diaChi.trim(),
      });
      setKetQua(yeuCau);
      setBuoc(4);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không gửi được yêu cầu.");
    } finally {
      setDangGui(false);
    }
  }

  async function dinhAnh(i: number, file: File) {
    setDangTaiAnh(i);
    setLoi("");
    try {
      const { media_id } = await api.uploadMedia(file);
      setMon((cu) => cu.map((x, j) => (j === i ? { ...x, media_id } : x)));
    } catch {
      setLoi("Không tải được ảnh, thử lại giúp mình nhé.");
    } finally {
      setDangTaiAnh(null);
    }
  }

  const nhanNut = buoc === 1 ? "Tiếp tục" : buoc === 2 ? "Xem lại" : "Gửi yêu cầu";
  const choPhepTiep = buoc === 1 ? mon.length > 0 && !thieuTen : buoc === 2 ? Boolean(khungGio) : daTick && !thieuDiaChi;

  return (
    <div className="min-h-full bg-cream pb-10 pt-11 lg:mx-auto lg:max-w-[720px]">
      <div className="flex items-center gap-3 px-[18px] pb-3.5 pt-1.5">
        <button
          onClick={() => (buoc === 1 ? onBack() : setBuoc((b) => b - 1))}
          className="flex h-[38px] w-[38px] cursor-pointer items-center justify-center rounded-full bg-surface shadow-[0_2px_8px_rgba(20,40,25,.08)]"
          aria-label="Quay lại bước trước"
        >
          <IconQuayLai className="h-5 w-5" />
        </button>
        <div className="flex flex-1 gap-1.5">
          {[1, 2, 3].map((b) => (
            <span key={b} className="h-[5px] flex-1 rounded-full" style={{ background: buoc >= b ? "var(--color-bulky-stripe)" : "var(--color-surface)" }} />
          ))}
        </div>
      </div>

      <div className="px-[18px]">
        {buoc === 1 && (
          <>
            <div className="mb-1 text-[13px] font-bold text-bulky">Bước 1/3</div>
            <h1 className="m-0 mb-1 font-[family-name:var(--font-display)] text-[26px] font-bold">Món cần thu gom</h1>
            <p className="m-0 mb-4 text-[13px] font-semibold text-muted">
              AI gợi ý tên và nhóm rác — khối lượng do bạn tự nhập, kiểm tra lại giúp mình.
            </p>
            {mon.map((m, i) => (
              <Card key={i} className="mb-2.5 flex gap-3 p-3.5">
                <label className="relative h-16 w-16 flex-none cursor-pointer overflow-hidden rounded-xl">
                  {m.media_id ? (
                    <AnhCoToken mediaId={m.media_id} alt={m.name} className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center bg-[repeating-linear-gradient(135deg,var(--color-bulky-soft),var(--color-bulky-soft)_7px,var(--color-bulky-stripe)_7px,var(--color-bulky-stripe)_14px)] text-[10px] font-bold text-bulky-dark">
                      {dangTaiAnh === i ? "Đang tải…" : "+ Ảnh"}
                    </div>
                  )}
                  <input
                    type="file"
                    accept="image/*"
                    capture="environment"
                    className="absolute inset-0 cursor-pointer opacity-0"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) dinhAnh(i, f);
                      e.target.value = "";
                    }}
                  />
                </label>
                <div className="flex-1">
                  <input
                    value={m.name}
                    onChange={(e) => setMon((cu) => cu.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
                    placeholder="Tên món (VD: tủ gỗ cũ)"
                    className="w-full bg-transparent text-[15px] font-extrabold outline-none"
                  />
                  <div className="my-1.5 flex flex-wrap items-center gap-1.5">
                    {HAI_NHOM.map((ma) => {
                      const dangChon = m.category_code === ma;
                      return (
                        <button
                          key={ma}
                          type="button"
                          onClick={() =>
                            setMon((cu) => cu.map((x, j) => (j === i ? { ...x, category_code: ma } : x)))
                          }
                          aria-pressed={dangChon}
                          className="cursor-pointer rounded-lg px-2 py-0.5 text-[11px] font-extrabold transition-colors"
                          style={{
                            background: dangChon ? "var(--color-bulky-soft)" : "var(--color-line-4)",
                            color: dangChon ? "var(--color-category-selected)" : "var(--color-category-unselected)",
                            border: dangChon ? "1.5px solid var(--color-bulky-stripe)" : "1.5px solid transparent",
                          }}
                        >
                          {tenNhom(ma, danhMuc)}
                        </button>
                      );
                    })}
                    {!HAI_NHOM.includes(m.category_code) && (
                      <span className="rounded-lg bg-bulky-soft px-2 py-0.5 text-[11px] font-extrabold text-bulky-dark">
                        {tenNhom(m.category_code, danhMuc)}
                      </span>
                    )}
                    <input
                      type="number"
                      value={m.est_weight_kg}
                      min={1}
                      onChange={(e) =>
                        setMon((cu) => cu.map((x, j) => (j === i ? { ...x, est_weight_kg: Number(e.target.value) } : x)))
                      }
                      className="w-16 rounded-lg bg-line-4 px-2 py-0.5 text-[11px] font-bold text-amber-muted outline-none"
                    />
                    <span className="text-[11px] font-bold text-amber-muted">kg</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] font-bold text-amber-muted">
                    Khối lượng bạn tự nhập — sửa lại nếu chưa đúng
                  </div>
                </div>
                <button
                  onClick={() => setMon((cu) => cu.filter((_, j) => j !== i))}
                  className="cursor-pointer text-muted"
                  aria-label={`Bỏ món ${m.name}`}
                >
                  <IconTuChoi className="h-4 w-4" />
                </button>
              </Card>
            ))}
            <button
              onClick={() => setMon((cu) => [...cu, { name: "", category_code: "bulky", qty: 1, est_weight_kg: 10, media_id: null }])}
              className="w-full cursor-pointer rounded-2xl border-[1.5px] border-dashed border-line-2 bg-surface p-3.5 text-sm font-bold text-bulky-dark"
            >
              + Thêm món
            </button>
            {thieuTen && (
              <p className="mt-2 text-[12px] font-bold text-hazard-dark">
                Điền tên món để tiếp tục — món phải có tên mới gửi được.
              </p>
            )}
            <div className="mx-0.5 mt-4 flex items-center justify-between text-sm font-bold">
              <span className="text-muted">Tổng ước tính</span>
              <span className="font-[family-name:var(--font-display)] text-lg font-extrabold">{kg(tongKg)}</span>
            </div>
          </>
        )}

        {buoc === 2 && (
          <>
            <div className="mb-1 text-[13px] font-bold text-bulky">Bước 2/3</div>
            <h1 className="m-0 mb-4 font-[family-name:var(--font-display)] text-[26px] font-bold">Chọn thời gian</h1>

            {khungBQL.length > 0 && (
              <>
                <div className="mb-2 text-[13px] font-bold text-muted">Khung theo lịch của toà</div>
                {khungBQL.map((k) => {
                  const dangChon = khungGio === k.window && ngay === k.ngay && !laGioNgoaiLich;
                  return (
                    <button
                      key={k.key}
                      onClick={() => { setKhungGio(k.window); setNgay(k.ngay); setLaGioNgoaiLich(false); }}
                      className="mb-2.5 w-full cursor-pointer rounded-2xl p-4 text-left"
                      style={{ background: dangChon ? "var(--color-leaf-soft)" : "var(--color-surface)", border: dangChon ? "2px solid var(--color-leaf)" : "1.5px solid var(--color-line-2)" }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[15px] font-extrabold">{ngayVn(k.ngay)} · {k.window}</span>
                        {dangChon && (
                          <span className="flex h-[22px] w-[22px] items-center justify-center rounded-full bg-leaf text-white">
                            <IconDuyet className="h-3.5 w-3.5" strokeWidth={3} />
                          </span>
                        )}
                      </div>
                      {k.ghiChu && (
                        <div className="mt-2 flex items-center gap-1.5 text-xs font-bold text-leaf-dark">
                          <IconXeThuGom className="h-4 w-4 flex-none" />
                          {k.ghiChu}
                        </div>
                      )}
                    </button>
                  );
                })}
              </>
            )}

            <div className="mb-2 mt-3 text-[13px] font-bold text-muted">Chọn giờ khác</div>
            <div className="mb-2.5 rounded-2xl border-[1.5px] border-line-2 bg-surface p-4">
              <input
                type="date"
                value={laGioNgoaiLich ? ngay : ""}
                min={new Date().toISOString().slice(0, 10)}
                onChange={(e) => { setNgay(e.target.value); setLaGioNgoaiLich(true); if (!khungGio) setKhungGio(KHUNG_TU_CHON[0]); }}
                className="mb-2.5 w-full rounded-xl border border-line-3 px-3 py-2 text-[14px] font-semibold outline-none focus:border-leaf"
              />
              <div className="flex flex-wrap gap-2">
                {KHUNG_TU_CHON.map((w) => {
                  const chon = laGioNgoaiLich && khungGio === w;
                  return (
                    <button
                      key={w}
                      onClick={() => { setKhungGio(w); setLaGioNgoaiLich(true); if (!ngay) { const d = new Date(); d.setDate(d.getDate() + 1); setNgay(d.toISOString().slice(0, 10)); } }}
                      className="cursor-pointer rounded-full px-3 py-1.5 text-[13px] font-bold"
                      style={{ background: chon ? "var(--color-bulky-chip)" : "var(--color-line-4)", color: chon ? "var(--color-category-selected)" : "var(--color-category-unselected)", border: chon ? "1.5px solid var(--color-bulky-stripe)" : "1.5px solid transparent" }}
                    >
                      {w}
                    </button>
                  );
                })}
              </div>
            </div>
            {laGioNgoaiLich && (
              <div className="mb-2.5 rounded-2xl border-[1.5px] border-amber-line bg-amber-soft p-3.5 text-[13px] font-semibold leading-relaxed text-amber-dark">
                Giờ này nằm ngoài lịch thu gom của toà — ban quản lý sẽ duyệt trước khi nhận yêu cầu.
              </div>
            )}

            <textarea
              value={ghiChu}
              onChange={(e) => setGhiChu(e.target.value)}
              placeholder="Ghi chú thêm (VD: để ở sảnh tầng 1)"
              className="mt-2 min-h-[70px] w-full resize-none rounded-2xl border-[1.5px] border-line-2 p-3 text-sm font-semibold outline-none focus:border-leaf"
            />
          </>
        )}

        {buoc === 3 && (
          <>
            <div className="mb-1 text-[13px] font-bold text-bulky">Bước 3/3</div>
            <h1 className="m-0 mb-4 font-[family-name:var(--font-display)] text-[26px] font-bold">Xác nhận</h1>

            {coCanHo ? (
              <div className="mb-2.5 rounded-2xl border-[1.5px] border-line-2 bg-surface p-4">
                <label htmlFor="dia-chi-lay-hang" className="mb-1 block text-[13px] font-bold text-muted">
                  Lấy hàng ở chỗ khác? nhập địa chỉ
                </label>
                <input
                  id="dia-chi-lay-hang"
                  type="text"
                  value={diaChi}
                  onChange={(e) => setDiaChi(e.target.value)}
                  placeholder="VD: 25 Lý Thường Kiệt, Hoàn Kiếm"
                  className="w-full rounded-xl border border-line-3 bg-surface px-3 py-2 text-[14px] font-semibold outline-none focus:border-leaf"
                />
                <div className="mt-1 text-[11px] font-semibold text-muted">
                  Để trống thì đội vệ sinh lấy tại nơi ở đã đăng ký.
                </div>
              </div>
            ) : (
              <div className="mb-2.5 rounded-2xl border-[1.5px] border-line-2 bg-surface p-4">
                <label htmlFor="dia-chi-lay-hang" className="mb-1 block text-[13px] font-bold text-ink-soft">
                  Địa chỉ lấy hàng <span className="text-hazard-dark">*</span>
                </label>
                <input
                  id="dia-chi-lay-hang"
                  type="text"
                  value={diaChi}
                  onChange={(e) => setDiaChi(e.target.value)}
                  placeholder="Số nhà, tên phố, phường/xã, quận/huyện"
                  className="w-full rounded-xl border border-line-3 bg-surface px-3 py-2 text-[14px] font-semibold outline-none focus:border-leaf"
                />
                <div className="mt-1 text-[11px] font-semibold text-muted">
                  Đội vệ sinh sẽ đến lấy tại địa chỉ này.
                </div>
              </div>
            )}

            <Card className="mb-3 p-4">
              <Dong nhan="Số món" gia={`${mon.length} món`} />
              <Dong nhan="Tổng khối lượng" gia={kg(tongKg)} dam />
              <Dong nhan="Thời gian" gia={`${ngayVn(ngay)} · ${khungGio}`} />
            </Card>

            {vuotNguong && (
              <div className="mb-3 rounded-2xl border-[1.5px] border-amber-line bg-amber-soft p-4">
                <div className="flex gap-2.5">
                  <IconChoDuyet className="mt-0.5 h-[18px] w-[18px] flex-none text-amber" />
                  <div>
                    <div className="mb-1 text-sm font-extrabold text-amber">Cần ban quản lý duyệt</div>
                    <div className="text-[13px] font-semibold leading-relaxed text-amber-dark">
                      Khối lượng ước tính <b>{kg(tongKg)}</b> (sai số ±40% nên cận trên tới{" "}
                      <b>{kg(Math.round(tongKg * 1.4))}</b>) vượt ngưỡng tự động <b>({NGUONG_KG_MAC_DINH} kg)</b>, nên
                      cần BQL duyệt trước khi lên lịch. Bạn sẽ nhận thông báo trong vòng 1 ngày làm việc.
                    </div>
                  </div>
                </div>
              </div>
            )}

            <label className="flex cursor-pointer items-start gap-2.5 rounded-2xl bg-surface p-3.5 text-[13px] font-semibold leading-snug text-ink-soft">
              <input type="checkbox" checked={daTick} onChange={(e) => setDaTick(e.target.checked)} className="mt-0.5 h-5 w-5 accent-leaf" />
              Tôi xác nhận các món trên không chứa rác nguy hại (pin, hoá chất, bóng đèn, thuốc).
            </label>
            {loi && <div className="mt-3 text-[13px] font-bold text-hazard-dark">{loi}</div>}
          </>
        )}

        {buoc === 4 && ketQua && (
          <>
            <div className="py-6 text-center">
              <div className="mx-auto mb-4 flex h-[74px] w-[74px] items-center justify-center rounded-full bg-leaf-soft text-leaf">
                <IconDuyet className="h-9 w-9" strokeWidth={2.6} />
              </div>
              <h1 className="m-0 mb-1 font-[family-name:var(--font-display)] text-[25px] font-bold">Đã gửi yêu cầu!</h1>
              <div className="mb-4 text-[15px] font-extrabold text-bulky">#PR-{String(ketQua.id).padStart(4, "0")}</div>
            </div>
            <Card className="p-4">
              {(ketQua.timeline ?? []).map((moc, i) => (
                <div key={i} className="mb-3.5 flex gap-3 last:mb-0">
                  <span className="flex h-[22px] w-[22px] flex-none items-center justify-center rounded-full bg-leaf text-white">
                    <IconDuyet className="h-3 w-3" strokeWidth={3} />
                  </span>
                  <div className="text-[13px] font-bold">
                    <span className="font-semibold text-muted">{new Date(moc.at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })} · </span>
                    {moc.label_vi}
                  </div>
                </div>
              ))}
              {ketQua.status === "cho_duyet" && (
                <div className="flex gap-3">
                  <span className="flex h-[22px] w-[22px] flex-none items-center justify-center rounded-full bg-amber-line text-amber">
                    <IconChoDuyet className="h-3 w-3" />
                  </span>
                  <div className="text-[13px] font-bold text-amber">Chờ ban quản lý duyệt</div>
                </div>
              )}
            </Card>
            <Button block size="lg" className="mt-4" onClick={() => onDone(ketQua)}>
              Xem yêu cầu của tôi
            </Button>
          </>
        )}
      </div>

      {buoc < 4 && (
        <div className="px-[18px] pt-4">
          <Button
            block
            size="lg"
            disabled={!choPhepTiep || dangGui}
            onClick={() => (buoc === 3 ? gui() : setBuoc((b) => b + 1))}
          >
            {dangGui ? "Đang gửi…" : nhanNut}
          </Button>
        </div>
      )}
    </div>
  );
}

function Dong({ nhan, gia, dam }: { nhan: string; gia: string; dam?: boolean }) {
  return (
    <div className="flex justify-between py-1 text-sm font-bold">
      <span className="text-muted">{nhan}</span>
      <span className={dam ? "font-extrabold" : ""}>{gia}</span>
    </div>
  );
}
