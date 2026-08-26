"use client";

/** Kíp thu gom hai người và sự cố thu gom — màn ban quản lý.
 *
 * Gồm hai phần, chọn bằng tab:
 *  - Kíp thu gom: xem kíp của một chuyến, gán kíp từ danh sách nhân viên khả dụng,
 *    tạo lịch tuần.
 *  - Sự cố: danh sách sự cố, lọc theo trạng thái, xử lý từng cái.
 *
 * Backend cố ý không trả thông tin liên hệ của nhân viên — quyền riêng tư của họ
 * là quyết định đúng, không phải thiếu sót.
 */

import * as React from "react";

import { Button, Card, Chip, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { ngayGioVn } from "@/lib/format";
import {
  IconCanhBao,
  IconDoiVeSinh,
  IconDuyet,
  IconLamLai,
  IconTuChoi,
  IconXongHet,
} from "@/lib/icons";
import type {
  DanhSachKip,
  KetQuaTaoLichTuan,
  NhanVienKhaDung,
  PickupRoute,
  SuCoThuGom,
  TrangThaiSuCoThuGom,
} from "@/lib/types";

const TRANG_THAI_SU_CO: Record<TrangThaiSuCoThuGom, string> = {
  cho_xu_ly: "Chờ xử lý",
  da_xu_ly: "Đã xử lý",
  tu_choi: "Từ chối",
};

/** Nhãn loại sự cố — bộ giá trị cố định của backend (`LOAI_HOP_LE` trong
 *  ``src/services/su_co_thu_gom.py``). Mã lạ (tương lai thêm mới) thì hiện
 *  nguyên mã thay vì biến mất. */
const NHAN_LOAI_SU_CO: Record<string, string> = {
  phan_loai_sai: "Phân loại sai",
  thung_day: "Thùng đầy / quá tải",
  khong_tiep_can: "Không tiếp cận được điểm dừng",
  khac: "Khác",
};

function tinhTuanBatDau(): string {
  const now = new Date();
  const thu = (now.getDay() + 6) % 7; // thứ Hai = 0
  const thuHai = new Date(now);
  thuHai.setDate(now.getDate() - thu);
  return thuHai.toISOString().slice(0, 10);
}

export function KipVaSuCo() {
  const [tab, setTab] = React.useState<"kip" | "su_co">("kip");
  return (
    <section className="mt-8 border-t border-line-3 pt-6">
      <div className="mb-4 flex items-center gap-2.5">
        <div className="font-[family-name:var(--font-display)] text-[22px] font-bold">Kíp thu gom &amp; sự cố</div>
      </div>
      <div className="mb-4 flex gap-1.5 border-b border-line-3 pb-2.5">
        {(
          [
            { key: "kip", label: "Kíp thu gom" },
            { key: "su_co", label: "Sự cố" },
          ] as const
        ).map((m) => (
          <button
            key={m.key}
            onClick={() => setTab(m.key)}
            className={`rounded-2xl px-3.5 py-2 text-xs font-bold transition-all ${
              tab === m.key ? "bg-ink text-white shadow-[var(--shadow-xs)]" : "text-ink-soft hover:bg-black/5"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>
      {tab === "kip" ? <CrewManagement /> : <IncidentBoard />}
    </section>
  );
}

function CrewManagement() {
  const [tuyen, setTuyen] = React.useState<PickupRoute[] | null>(null);
  const [routeId, setRouteId] = React.useState<number | null>(null);
  const [kip, setKip] = React.useState<DanhSachKip | null>(null);
  const [nhanVien, setNhanVien] = React.useState<NhanVienKhaDung[] | null>(null);
  const [chon, setChon] = React.useState<number[]>([]);
  const [truongKip, setTruongKip] = React.useState<number | null>(null);
  const [dangGui, setDangGui] = React.useState(false);
  const [loi, setLoi] = React.useState("");
  const [thongBao, setThongBao] = React.useState("");

  const taiTuyen = React.useCallback(() => {
    api
      .routes()
      .then((d) => {
        setTuyen(d.items);
        if (d.items.length && routeId === null) setRouteId(d.items[0].id);
      })
      .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được danh sách tuyến"));
  }, [routeId]);

  const taiKip = React.useCallback(() => {
    if (routeId === null) return;
    setLoi("");
    setThongBao("");
    Promise.all([api.kipCuaChuyen(routeId), api.nhanVienKhaDung()])
      .then(([k, nv]) => {
        setKip(k);
        setNhanVien(nv.items);
      })
      .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được kíp / nhân viên"));
  }, [routeId]);

  React.useEffect(() => {
    taiTuyen();
  }, [taiTuyen]);
  React.useEffect(() => {
    taiKip();
  }, [taiKip]);

  function toggleChon(id: number) {
    setChon((cu) => {
      const moi = cu.includes(id) ? cu.filter((x) => x !== id) : [...cu, id];
      if (!moi.includes(truongKip ?? -1)) setTruongKip(moi[0] ?? null);
      return moi;
    });
  }

  async function ganKip() {
    if (routeId === null || chon.length === 0 || dangGui) return;
    setDangGui(true);
    setLoi("");
    try {
      await api.ganKip(routeId, { user_ids: chon, truong_kip_id: truongKip ?? chon[0] });
      setThongBao(`Đã gán kíp ${chon.length} người cho chuyến #${routeId}.`);
      await taiKip();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không gán được kíp, thử lại giúp mình nhé.");
    } finally {
      setDangGui(false);
    }
  }

  async function taoLichTuan() {
    setDangGui(true);
    setLoi("");
    setThongBao("");
    try {
      const ketQua = await api.taoLichTuan(tinhTuanBatDau());
      hienLichTuan(ketQua);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không tạo được lịch tuần.");
    } finally {
      setDangGui(false);
    }
  }

  const [ketQuaLich, setKetQuaLich] = React.useState<KetQuaTaoLichTuan | null>(null);
  function hienLichTuan(k: KetQuaTaoLichTuan) {
    setKetQuaLich(k);
  }

  if (loi) return <ErrorState message={loi} onRetry={() => { taiTuyen(); taiKip(); }} />;
  if (tuyen === null) return <Skeleton className="h-96 w-full" />;

  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="chon-tuyen" className="mb-1 block text-[11px] font-extrabold text-muted">
          Chọn chuyến để xem / gán kíp
        </label>
        <select
          id="chon-tuyen"
          value={routeId ?? ""}
          onChange={(e) => {
            setRouteId(Number(e.target.value));
            setKip(null);
            setNhanVien(null);
            setChon([]);
            setTruongKip(null);
          }}
          className="h-12 w-full rounded-2xl border border-line-2 bg-surface px-3.5 text-base font-bold text-ink-soft outline-none focus:border-leaf"
        >
          {tuyen.map((r) => (
            <option key={r.id} value={r.id}>
              #{r.id} · {r.window} · {r.service_date}
            </option>
          ))}
        </select>
      </div>

      <Card className="p-4">
        <div className="mb-2.5 flex items-center gap-1.5 text-[13px] font-bold text-ink-soft">
          <IconDoiVeSinh className="h-4 w-4" />
          Kíp hiện tại
        </div>
        {kip === null ? (
          <Skeleton className="h-16 w-full" />
        ) : kip.items.length === 0 ? (
          <div className="text-[13px] font-semibold text-muted">Chuyến này chưa có kíp. Chọn nhân viên bên dưới để gán.</div>
        ) : (
          <div className="space-y-2">
            {/* Trưởng kíp đứng đầu danh sách (vai_tro chỉ có truong_kip/thanh_vien) */}
            {[...kip.items]
              .sort((a, b) => (a.vai_tro === "truong_kip" ? 0 : 1) - (b.vai_tro === "truong_kip" ? 0 : 1))
              .map((tv, i) => (
              <div
                key={tv.id}
                className={`flex items-center gap-3 rounded-2xl border px-3.5 py-2.5 ${
                  tv.vai_tro === "truong_kip" ? "border-leaf-line bg-leaf-soft" : "border-line bg-surface"
                }`}
              >
                <span className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-recycle-soft text-[12px] font-extrabold text-recycle">
                  {i + 1}
                </span>
                <span className="flex-1 text-[14px] font-bold">{tv.full_name}</span>
                {tv.vai_tro === "truong_kip" ? (
                  <Chip tone="leaf" className="text-[11px]">
                    Trưởng kíp
                  </Chip>
                ) : (
                  <Chip tone="neutral" className="text-[11px]">
                    Thành viên
                  </Chip>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="p-4">
        <div className="mb-2.5 text-[13px] font-bold text-ink-soft">Nhân viên khả dụng</div>
        {nhanVien === null ? (
          <Skeleton className="h-16 w-full" />
        ) : nhanVien.length === 0 ? (
          <div className="text-[13px] font-semibold text-muted">Không có nhân viên nào khả dụng.</div>
        ) : (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {nhanVien.map((nv) => {
              const dangChon = chon.includes(nv.id);
              return (
                <button
                  key={nv.id}
                  onClick={() => toggleChon(nv.id)}
                  className={`flex items-center gap-3 rounded-2xl border px-3.5 py-2.5 text-left transition-all ${
                    dangChon ? "border-leaf bg-leaf-soft" : "border-line bg-surface hover:border-line-2"
                  }`}
                >
                  <span
                    className={`flex h-5 w-5 flex-none items-center justify-center rounded-lg border ${
                      dangChon ? "border-leaf bg-leaf text-white" : "border-line-2"
                    }`}
                  >
                    {dangChon ? <IconDuyet className="h-3.5 w-3.5" /> : null}
                  </span>
                  <span className="flex-1 text-[14px] font-bold">{nv.full_name}</span>
                  <span className="text-[11px] font-semibold text-muted">{nv.role}</span>
                </button>
              );
            })}
          </div>
        )}

        {chon.length > 0 && (
          <div className="mt-3 rounded-2xl bg-console-bg px-3.5 py-3">
            <div className="mb-1.5 text-[11px] font-extrabold text-muted">TRƯỞNG KÍP</div>
            <div className="flex flex-wrap gap-2">
              {chon.map((id) => {
                const nv = nhanVien?.find((x) => x.id === id);
                return (
                  <button
                    key={id}
                    onClick={() => setTruongKip(id)}
                    className={`rounded-lg px-2.5 py-1.5 text-[13px] font-bold ${
                      truongKip === id ? "bg-leaf text-white" : "bg-surface text-ink-soft"
                    }`}
                  >
                    {nv?.full_name ?? `#${id}`}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="mt-3 flex flex-wrap gap-2.5">
          <Button
            variant="leaf"
            size="lg"
            disabled={dangGui || chon.length === 0}
            onClick={ganKip}
          >
            <IconDoiVeSinh className="h-4 w-4" />
            {dangGui ? "Đang gán…" : `Gán kíp (${chon.length})`}
          </Button>
        </div>
      </Card>

      <Card className="p-4">
        <div className="mb-2.5 flex items-center gap-1.5 text-[13px] font-bold text-ink-soft">
          <IconLamLai className="h-4 w-4" />
          Lịch tuần
        </div>
        <div className="mb-3 text-[13px] font-semibold leading-relaxed text-muted">
          Tạo chuyến cho 7 ngày tới từ thứ Hai này, tự gán kíp theo vòng tròn. Bấm một lần đầu tuần
          là đủ.
        </div>
        <Button variant="leaf" size="lg" disabled={dangGui} onClick={taoLichTuan}>
          <IconLamLai className="h-4 w-4" />
          {dangGui ? "Đang tạo…" : "Tạo lịch tuần"}
        </Button>

        {ketQuaLich && (
          <div className="mt-3 rounded-2xl border border-leaf-line bg-leaf-soft px-4 py-3">
            <div className="mb-2 text-[13px] font-extrabold text-leaf-dark">Kết quả tạo lịch tuần</div>
            <div className="divide-y divide-leaf-line/60">
              <DongLichTuan nhan="Số ngày được xét" so={ketQuaLich.so_ngay_xet} />
              <DongLichTuan nhan="Số chuyến được tạo" so={ketQuaLich.so_chuyen_tao} />
              <DongLichTuan nhan="Số chuyến đã gán kíp" so={ketQuaLich.so_chuyen_da_gan_kip} />
              <DongLichTuan nhan="Số chuyến chưa gán kíp" so={ketQuaLich.so_chuyen_chua_gan_kip} />
              <DongLichTuan nhan="Lịch bỏ vì đã có từ trước" so={ketQuaLich.so_lich_bo_vi_da_co} />
              <DongLichTuan nhan="Lịch bỏ vì không yêu cầu" so={ketQuaLich.so_lich_bo_vi_khong_yeu_cau} />
            </div>
            <p className="mt-2 text-[11px] font-semibold text-leaf-dark/80">
              Chạy lại không tạo chuyến trùng — những ngày đã có lịch tuần được giữ nguyên, nên
              &quot;Số chuyến được tạo&quot; có thể về 0 lần hai.
            </p>
          </div>
        )}
      </Card>

      {thongBao && (
        <div className="rounded-2xl bg-leaf-soft px-4 py-3 text-sm font-bold text-leaf-dark">{thongBao}</div>
      )}
    </div>
  );
}

function DongLichTuan({ nhan, so }: { nhan: string; so: number }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-[13px] font-bold">
      <span className="text-leaf-dark/90">{nhan}</span>
      <span className="font-[family-name:var(--font-display)] text-base text-leaf-dark">{so}</span>
    </div>
  );
}

function IncidentBoard() {
  const [trangThai, setTrangThai] = React.useState<TrangThaiSuCoThuGom | "">("");
  const [ds, setDs] = React.useState<SuCoThuGom[] | null>(null);
  const [loi, setLoi] = React.useState("");
  const [dangXuLy, setDangXuLy] = React.useState<number | null>(null);
  const [ghiChu, setGhiChu] = React.useState("");
  const [dangGui, setDangGui] = React.useState(false);

  const tai = React.useCallback(() => {
    setLoi("");
    const params: { trang_thai?: TrangThaiSuCoThuGom } = {};
    if (trangThai) params.trang_thai = trangThai;
    api
      .suCoThuGom(params)
      .then((d) => setDs(d.items))
      .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được danh sách sự cố"));
  }, [trangThai]);

  React.useEffect(() => {
    tai();
  }, [tai]);

  async function xuLy(chapNhan: boolean) {
    if (dangXuLy === null || dangGui) return;
    setDangGui(true);
    setLoi("");
    try {
      await api.xuLySuCo(dangXuLy, { chap_nhan: chapNhan, ghi_chu: ghiChu || undefined });
      setDangXuLy(null);
      setGhiChu("");
      await tai();
    } catch (e) {
      setLoi(e instanceof Error ? e.message : "Không lưu được xử lý, thử lại giúp mình nhé.");
    } finally {
      setDangGui(false);
    }
  }

  const BO_LOC: { key: TrangThaiSuCoThuGom | ""; label: string }[] = [
    { key: "", label: "Tất cả" },
    { key: "cho_xu_ly", label: "Chờ xử lý" },
    { key: "da_xu_ly", label: "Đã xử lý" },
    { key: "tu_choi", label: "Từ chối" },
  ];

  if (loi) return <ErrorState message={loi} onRetry={tai} />;
  if (ds === null) return <Skeleton className="h-96 w-full" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5 border-b border-line-3 pb-2.5">
        {BO_LOC.map((m) => (
          <button
            key={m.key}
            onClick={() => setTrangThai(m.key)}
            className={`rounded-2xl px-3.5 py-2 text-xs font-bold transition-all ${
              trangThai === m.key ? "bg-ink text-white shadow-[var(--shadow-xs)]" : "text-ink-soft hover:bg-black/5"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {ds.length === 0 ? (
        <EmptyState
          icon={IconXongHet}
          title="Chưa có sự cố nào"
          hint="Khi đội thu gom báo sự cố trên đường đi (thùng tràn, xe hỏng, điểm không có người…), danh sách sẽ hiện ở đây để bạn xử lý."
        />
      ) : (
        ds.map((sc) => (
          <Card key={sc.id} className="p-4">
            <div className="mb-2.5 flex items-start justify-between gap-3">
              <div className="flex items-center gap-1.5 text-[13px] font-bold text-ink-soft">
                <IconCanhBao className="h-4 w-4 text-amber" />
                Sự cố #{sc.id}
              </div>
              <Chip
                tone={sc.trang_thai === "cho_xu_ly" ? "amber" : sc.trang_thai === "da_xu_ly" ? "leaf" : "neutral"}
              >
                {TRANG_THAI_SU_CO[sc.trang_thai]}
              </Chip>
            </div>
             <div className="mb-1 text-[14px] font-bold">{NHAN_LOAI_SU_CO[sc.loai] ?? sc.loai}</div>
            {sc.mo_ta && <div className="mb-1.5 text-[13px] font-semibold text-muted">{sc.mo_ta}</div>}
            <div className="text-[11px] font-semibold text-muted">
              Chuyến #{sc.route_id}
              {sc.created_at ? ` · báo lúc ${ngayGioVn(sc.created_at)}` : ""}
            </div>

            {sc.trang_thai === "cho_xu_ly" && dangXuLy !== sc.id && (
              <div className="mt-3 flex gap-2.5">
                <Button variant="leaf" size="lg" className="flex-1" onClick={() => setDangXuLy(sc.id)}>
                  <IconDuyet className="h-4 w-4" />
                  Xử lý
                </Button>
              </div>
            )}

            {dangXuLy === sc.id && (
              <div className="mt-3 space-y-2.5 rounded-2xl bg-console-bg p-3.5">
                <div>
                  <label htmlFor={`ghichu-${sc.id}`} className="mb-1 block text-[11px] font-extrabold text-muted">
                    Ghi chú xử lý (tuỳ chọn)
                  </label>
                  <input
                    id={`ghichu-${sc.id}`}
                    value={ghiChu}
                    onChange={(e) => setGhiChu(e.target.value)}
                    placeholder="vd: đã điều xe thay thế"
                    className="h-12 w-full rounded-2xl border border-line-2 bg-surface px-3.5 text-base font-bold text-ink-soft outline-none focus:border-leaf"
                  />
                </div>
                <div className="flex gap-2.5">
                  <Button
                    variant="leaf"
                    size="lg"
                    className="flex-1"
                    disabled={dangGui}
                    onClick={() => xuLy(true)}
                  >
                    <IconDuyet className="h-4 w-4" />
                    {dangGui ? "Đang lưu…" : "Chấp nhận"}
                  </Button>
                  <Button
                    variant="danger"
                    size="lg"
                    className="flex-1"
                    disabled={dangGui}
                    onClick={() => xuLy(false)}
                  >
                    <IconTuChoi className="h-4 w-4" />
                    Từ chối
                  </Button>
                </div>
                <Button size="sm" variant="ghost" block onClick={() => setDangXuLy(null)}>
                  Đóng
                </Button>
              </div>
            )}
          </Card>
        ))
      )}
    </div>
  );
}
