"use client";

import * as React from "react";

import { Button, Card, EmptyState, ErrorState, Input, Skeleton } from "@/components/ui/primitives";
import { IconLichThuGom } from "@/lib/icons";
import { api } from "@/lib/api";
import type { WasteCategory } from "@/lib/types";

const NGAY = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

type DongLich = { weekdays: number[]; window: string; location: string };

export function LichThuGom() {
  const [buildings, setBuildings] = React.useState<{ id: number; code: string; name: string }[]>([]);
  const [buildingId, setBuildingId] = React.useState<number | null>(null);
  const [categories, setCategories] = React.useState<WasteCategory[]>([]);
  const [rows, setRows] = React.useState<Record<string, DongLich>>({});
  const [dangTai, setDangTai] = React.useState(true);
  const [loi, setLoi] = React.useState("");
  const [dangLuu, setDangLuu] = React.useState(false);
  const [dangTao, setDangTao] = React.useState(false);
  const [thongBao, setThongBao] = React.useState<{ loai: "ok" | "loi"; msg: string } | null>(null);
  const [tuanBatDau, setTuanBatDau] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [ketQuaTao, setKetQuaTao] = React.useState<{ so_chuyen_tao: number; so_chuyen_da_gan_kip: number } | null>(null);

  // Tải toà + nhóm rác một lần.
  React.useEffect(() => {
    let biXoa = false;
    Promise.all([api.buildings(), api.categories()])
      .then(([b, c]) => {
        if (biXoa) return;
        setBuildings(b.items);
        setCategories(c.items);
        if (b.items.length) setBuildingId(b.items[0].id);
      })
      .catch((e) => !biXoa && setLoi(e instanceof Error ? e.message : "Không tải được dữ liệu"))
      .finally(() => !biXoa && setDangTai(false));
    return () => {
      biXoa = true;
    };
  }, []);

  const taiLich = React.useCallback(
    (id: number) => {
      setLoi("");
      setThongBao(null);
      setKetQuaTao(null);
      setDangTai(true);
      api
        .schedule(id)
        .then((d) => {
          const moi: Record<string, DongLich> = {};
          for (const cat of categories) {
            const cu = d.items.find((i) => i.category_code === cat.code);
            moi[cat.code] = {
              weekdays: cu ? [...cu.weekdays] : [],
              window: cu?.window ?? "",
              location: cu?.location ?? "",
            };
          }
          setRows(moi);
        })
        .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được lịch"))
        .finally(() => setDangTai(false));
    },
    [categories],
  );

  React.useEffect(() => {
    if (buildingId != null) taiLich(buildingId);
  }, [buildingId, taiLich]);

  function toggleDay(code: string, day: number) {
    setRows((r) => {
      const cur = r[code] ?? { weekdays: [], window: "", location: "" };
      const has = cur.weekdays.includes(day);
      const weekdays = has
        ? cur.weekdays.filter((d) => d !== day)
        : [...cur.weekdays, day].sort((a, b) => a - b);
      return { ...r, [code]: { ...cur, weekdays } };
    });
  }

  function setTruong(code: string, truong: "window" | "location", value: string) {
    setRows((r) => ({
      ...r,
      [code]: { ...(r[code] ?? { weekdays: [], window: "", location: "" }), [truong]: value },
    }));
  }

  async function luu() {
    if (buildingId == null) return;
    setDangLuu(true);
    setThongBao(null);
    setLoi("");
    try {
      const items = categories.map((c) => {
        const row = rows[c.code] ?? { weekdays: [], window: "", location: "" };
        return { category_code: c.code, weekdays: row.weekdays, window: row.window, location: row.location };
      });
      await api.luuSchedule(buildingId, items);
      setThongBao({ loai: "ok", msg: "Đã lưu lịch thu gom." });
    } catch (e) {
      setThongBao({ loai: "loi", msg: e instanceof Error ? e.message : "Lưu lịch thất bại" });
    } finally {
      setDangLuu(false);
    }
  }

  async function taoTuan() {
    setDangTao(true);
    setThongBao(null);
    try {
      const kq = await api.taoLichTuan(tuanBatDau);
      setKetQuaTao({ so_chuyen_tao: kq.so_chuyen_tao, so_chuyen_da_gan_kip: kq.so_chuyen_da_gan_kip });
      setThongBao({
        loai: "ok",
        msg: `Đã tạo ${kq.so_chuyen_tao} chuyến, gán kíp ${kq.so_chuyen_da_gan_kip}.`,
      });
    } catch (e) {
      setThongBao({ loai: "loi", msg: e instanceof Error ? e.message : "Tạo lịch tuần thất bại" });
    } finally {
      setDangTao(false);
    }
  }

  const coLich = categories.length > 0 && Object.values(rows).some((r) => r.weekdays.length > 0);

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-[22px] font-bold">Lịch thu gom</h1>
          <p className="text-[13px] font-semibold text-muted">Chọn ngày gom cho từng nhóm rác tại mỗi toà.</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-[13px] font-bold text-muted">Toà</label>
          <select
            className="rounded-[var(--gb-r-md)] border border-line-2 bg-surface px-3 py-2 text-sm font-semibold"
            value={buildingId ?? ""}
            onChange={(e) => setBuildingId(Number(e.target.value))}
            disabled={dangTai}
          >
            {buildings.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {thongBao && (
        <div
          className={[
            "mb-3 rounded-[var(--gb-r-md)] border px-4 py-3 text-sm font-bold",
            thongBao.loai === "loi"
              ? "border-hazard/30 bg-hazard-soft text-hazard-dark"
              : "border-leaf-mint/40 bg-leaf-soft text-leaf-dark",
          ].join(" ")}
        >
          {thongBao.msg}
        </div>
      )}

      {dangTai ? (
        <Skeleton className="h-72 w-full" />
      ) : loi ? (
        <ErrorState message={loi} onRetry={() => buildingId != null && taiLich(buildingId)} />
      ) : categories.length === 0 ? (
        <EmptyState icon={IconLichThuGom} title="Chưa có nhóm rác" hint="Thêm nhóm rác trong Danh mục trước khi đặt lịch." />
      ) : (
        <>
          {!coLich && (
            <div className="mb-3 rounded-[var(--gb-r-md)] border border-line-3 bg-cream-soft px-4 py-3 text-[13px] font-semibold text-muted">
              Toà này chưa có lịch — bật ngày gom cho từng nhóm rác bên dưới, rồi nhấn <b>Lưu lịch</b>.
            </div>
          )}
          <Card className="overflow-hidden p-0">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="bg-cream-soft">
                    <th className="sticky left-0 z-10 bg-cream-soft p-3 text-left font-extrabold">Nhóm rác</th>
                    {NGAY.map((n) => (
                      <th key={n} className="p-2 text-center font-extrabold text-muted">
                        {n}
                      </th>
                    ))}
                    <th className="p-3 text-left font-extrabold">Khung giờ</th>
                    <th className="p-3 text-left font-extrabold">Địa điểm</th>
                  </tr>
                </thead>
                <tbody>
                  {categories.map((cat) => {
                    const row = rows[cat.code] ?? { weekdays: [], window: "", location: "" };
                    return (
                      <tr key={cat.code} className="border-t border-line-3">
                        <td className="sticky left-0 z-10 bg-surface p-3">
                          <span className="flex items-center gap-2 font-bold">
                            <span className="h-3 w-3 rounded-full" style={{ background: cat.bin_color || "#999" }} />
                            {cat.name}
                          </span>
                        </td>
                        {NGAY.map((_, day) => {
                          const on = row.weekdays.includes(day);
                          return (
                            <td key={day} className="p-1 text-center">
                              <button
                                type="button"
                                onClick={() => toggleDay(cat.code, day)}
                                aria-pressed={on}
                                className={[
                                  "mx-auto flex h-9 w-9 items-center justify-center rounded-[var(--gb-r-md)] text-sm font-extrabold transition-colors",
                                  on ? "bg-leaf text-white" : "bg-muted-bg text-muted hover:bg-leaf-soft",
                                ].join(" ")}
                              >
                                {on ? "✓" : ""}
                              </button>
                            </td>
                          );
                        })}
                        <td className="p-2">
                          <Input
                            className="w-36"
                            placeholder="18:00-20:00"
                            value={row.window}
                            onChange={(e) => setTruong(cat.code, "window", e.target.value)}
                          />
                        </td>
                        <td className="p-2">
                          <Input
                            className="w-44"
                            placeholder="Sảnh B"
                            value={row.location}
                            onChange={(e) => setTruong(cat.code, "location", e.target.value)}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button variant="leaf" loading={dangLuu} onClick={luu} disabled={buildingId == null || categories.length === 0}>
          Lưu lịch
        </Button>
        <div className="flex items-center gap-2">
          <label className="text-[13px] font-bold text-muted">Tuần bắt đầu</label>
          <Input type="date" className="w-44" value={tuanBatDau} onChange={(e) => setTuanBatDau(e.target.value)} />
        </div>
        <Button variant="outline" loading={dangTao} onClick={taoTuan}>
          Tạo lịch tuần
        </Button>
        {ketQuaTao && (
          <span className="text-[13px] font-semibold text-muted">
            → {ketQuaTao.so_chuyen_tao} chuyến, gán kíp {ketQuaTao.so_chuyen_da_gan_kip}
          </span>
        )}
      </div>
    </div>
  );
}
