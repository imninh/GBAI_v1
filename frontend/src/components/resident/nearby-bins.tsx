"use client";

/** Tìm điểm gửi rác — yêu cầu R-01 của Gate01.
 *
 *  Cư dân cần biết gần mình có điểm gửi nào còn nhận loại rác họ đang cầm. Màn
 *  này là màn hình cư dân (không phải màn điều phối): lọc theo vật liệu, xem trên
 *  bản đồ, và tình trạng thùng viết cho người đi đổ — nhận thẳng `tinh_trang_vi`
 *  từ backend, không tự dịch ở client.
 */

import dynamic from "next/dynamic";
import * as React from "react";

import { Card, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import {
  dinhDangKhoangCach,
  khoangCachKm,
  type Bin,
  type BinStatus,
  type DiemGui,
  type TinhTrangDiemGui,
} from "@/lib/bins";
import { docDiaChi, themDiaChi, xoaDiaChi, type DiaChiLuu } from "@/lib/dia-chi";
import { IconXeThuGom } from "@/lib/icons";
import { useSession } from "@/lib/session";
import type { WasteCategory } from "@/lib/types";

// Leaflet chạm thẳng vào `window` nên không dựng được lúc build tĩnh — phải qua
// `next/dynamic` với `ssr:false` (dự án build bằng `output: "export"`).
const BinMap = dynamic(() => import("@/components/bins/bin-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

// Màu theo tình trạng cho cư dân. `tinh_trang_vi` lấy thẳng từ server để luật
// "số cũ không được nói là còn chỗ" nằm ở backend, có test bao, không lặp ở đây.
const MAU_TINH_TRANG: Record<TinhTrangDiemGui, string> = {
  con_cho: "bg-leaf-soft text-leaf-dark",
  sap_day: "bg-amber-line text-amber-darker",
  chua_ro: "bg-muted-bg text-muted",
};

const THU_TU_XEP: Record<TinhTrangDiemGui, number> = {
  con_cho: 0,
  sap_day: 1,
  chua_ro: 2,
};

// BinMap là bản đồ của đội vận hành nên nó đọc `Bin` — đừng sửa nó. Ở đây dựng
// một `Bin` tối thiểu từ `DiemGui`: các trường BinMap không đọc (`id`, mức pin,
// lần báo cuối…) để giá trị vô hại; `chua_ro` ánh xạ sang `mat_ket_noi` để marker
// hiện "?" thay vì một con số cũ gây hiểu nhầm cho cư dân.
const TRANG_THAI_MARKER: Record<TinhTrangDiemGui, BinStatus> = {
  con_cho: "binh_thuong",
  sap_day: "can_gom",
  chua_ro: "mat_ket_noi",
};

function diemGuiThanhBin(d: DiemGui): Bin {
  return {
    id: 0,
    code: d.code,
    name: d.name,
    building_id: null,
    address: d.address,
    category_codes: d.category_codes,
    lat: d.lat,
    lng: d.lng,
    fill_percent: d.fill_percent ?? 0,
    battery_percent: 0,
    // Điểm gửi của cư dân không mang dữ liệu vận hành: `GET /bins/diem-gui` cố
    // tình không trả ai đang được giao thùng.
    assigned_cleaner_id: null,
    last_seen_at: null,
    status: TRANG_THAI_MARKER[d.tinh_trang],
  };
}

export function NearbyBinsScreen() {
  const { user } = useSession();
  const [binList, setBinList] = React.useState<DiemGui[] | null>(null);
  const [nhomList, setNhomList] = React.useState<WasteCategory[]>([]);
  const [loi, setLoi] = React.useState("");
  const [mauLoc, setMauLoc] = React.useState<string | null>(null);
  const [dangChon, setDangChon] = React.useState<DiemGui | null>(null);
  // "nha" · "gps" · hoặc id một mốc đã lưu. Xem chú thích ở `mocLuu` bên dưới.
  const [moc, setMoc] = React.useState<string>("nha");
  const [viTriGps, setViTriGps] = React.useState<{ lat: number; lng: number } | null>(null);
  const [dangXinViTri, setDangXinViTri] = React.useState(false);
  const [loiViTri, setLoiViTri] = React.useState("");
  const [diaChi, setDiaChi] = React.useState<DiaChiLuu[]>([]);
  const [dangThem, setDangThem] = React.useState(false);
  const [tenMoi, setTenMoi] = React.useState("");
  const [diemMoi, setDiemMoi] = React.useState<{ lat: number; lng: number } | null>(null);
  const [duongDi, setDuongDi] = React.useState<[number, number][] | null>(null);
  // Giữ id của watchPosition để dừng theo dõi khi rời màn.
  const watchIdRef = React.useRef<number | null>(null);

  // localStorage chỉ có ở trình duyệt. Đọc nó ngay trong `useState` sẽ cho kết
  // quả khác nhau giữa lần dựng trên server và lần dựng ở client → React báo
  // lệch hydrate. Vì vậy phải đọc trong `useEffect`, sau khi đã gắn vào DOM.
  React.useEffect(() => {
    setDiaChi(docDiaChi());
  }, []);

  // Ngừng theo dõi vị trí khi rời màn — watchPosition chạy nền, bỏ quên là rò.
  React.useEffect(() => {
    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
    };
  }, []);

  const coNha = user?.building_lat != null && user?.building_lng != null;
  // `moc` nhận ba loại giá trị: "nha", "gps", hoặc id một mốc đã lưu. Mọi id do
  // `themDiaChi` sinh ra đều bắt đầu bằng "dc-" nên không đụng hai chuỗi kia.
  const mocLuu = diaChi.find((d) => d.id === moc) ?? null;
  // `mocToaDo` phải là tham chiếu ổn định (useMemo): effect đường đi thật phụ
  // thuộc nó, mà dựng object mới mỗi render thì effect chạy lại vô hạn lần.
  const mocToaDo = React.useMemo(
    () =>
      mocLuu
        ? { lat: mocLuu.lat, lng: mocLuu.lng }
        : moc === "gps"
          ? viTriGps
          : coNha
            ? { lat: user!.building_lat as number, lng: user!.building_lng as number }
            : null,
    [mocLuu, moc, viTriGps, coNha, user],
  );

  // Có mốc + thùng đang chọn thì hỏi đường đi thật; đổi lựa chọn thì bỏ đường cũ.
  React.useEffect(() => {
    if (!mocToaDo || !dangChon || dangChon.lat == null || dangChon.lng == null) {
      setDuongDi(null);
      return;
    }
    let huy = false;
    api
      .duongDiToiDiem([mocToaDo, { lat: dangChon.lat, lng: dangChon.lng }])
      .then((r) => { if (!huy) setDuongDi(r.duong_di); })
      .catch(() => { if (!huy) setDuongDi(null); });
    return () => { huy = true; };
  }, [mocToaDo, dangChon]);

  /** Đóng bảng thêm mốc và dọn bản nháp — mở lại là tờ giấy trắng. */
  function dongThem() {
    setDangThem(false);
    setTenMoi("");
    setDiemMoi(null);
  }

  function luuMoc() {
    if (!tenMoi.trim() || !diemMoi) return;
    const ds = themDiaChi(tenMoi, diemMoi.lat, diemMoi.lng);
    setDiaChi(ds);
    // Chuyển ngay sang mốc vừa lưu — người ta thêm nó là để dùng luôn.
    const vuaThem = ds[ds.length - 1];
    if (vuaThem) setMoc(vuaThem.id);
    dongThem();
  }

  function xoaMoc(id: string) {
    setDiaChi(xoaDiaChi(id));
    // Đang lấy chính mốc bị xoá làm gốc thì lui về nơi ở — đừng để màn hình treo
    // ở một mốc không còn tồn tại.
    if (moc === id) setMoc("nha");
  }

  /** Xin quyền vị trí — chỉ chạy khi người dùng tự chạm, không bao giờ tự động.
   *  Dùng watchPosition để chấm bám theo khi người dùng di chuyển. */
  function xinViTri() {
    if (viTriGps) {
      setMoc("gps");
      return;
    }
    if (!("geolocation" in navigator)) {
      setLoiViTri("Trình duyệt này không hỗ trợ định vị. Đang tính theo nơi ở đã đăng ký.");
      return;
    }
    if (typeof window !== "undefined" && !window.isSecureContext) {
      setLoiViTri(
        "Trình duyệt chặn định vị vì trang đang mở qua kết nối không bảo mật (http). " +
          "Mở bằng địa chỉ https rồi thử lại. Đang tính theo nơi ở đã đăng ký.",
      );
      return;
    }
    // Đã theo dõi rồi thì chỉ cần đưa mốc về GPS, không mở watcher thứ hai.
    if (watchIdRef.current !== null) {
      setMoc("gps");
      return;
    }
    setDangXinViTri(true);
    setLoiViTri("");
    watchIdRef.current = navigator.geolocation.watchPosition(
      (v) => {
        setViTriGps({ lat: v.coords.latitude, lng: v.coords.longitude });
        setMoc("gps");
        setDangXinViTri(false);
      },
      (err) => {
        setDangXinViTri(false);
        // Lỗi khi CHƯA có lần đọc nào mới lui về nơi ở; lỗi chập chờn giữa chừng
        // (đã có toạ độ) thì giữ nguyên chấm cũ, đừng giật người dùng khỏi GPS.
        if (!viTriGps) {
          if (watchIdRef.current !== null) {
            navigator.geolocation.clearWatch(watchIdRef.current);
            watchIdRef.current = null;
          }
          setMoc("nha");
          const viSao =
            err.code === err.PERMISSION_DENIED
              ? "Bạn đã từ chối quyền vị trí, hoặc trình duyệt đang chặn sẵn."
              : err.code === err.POSITION_UNAVAILABLE
                ? "Máy không xác định được vị trí lúc này."
                : "Quá lâu không lấy được vị trí.";
          setLoiViTri(
            coNha
              ? `${viSao} Đang tính khoảng cách theo nơi ở đã đăng ký.`
              : `${viSao} Tài khoản cũng chưa gắn căn hộ nên chưa tính được khoảng cách.`,
          );
        }
      },
      // `enableHighAccuracy: true` bắt máy đợi định vị vệ tinh; laptop không có
      // GPS nên nó chỉ dẫn tới TIMEOUT sau 10 giây dù người dùng đã Cho phép.
      // Định vị theo Wi-Fi/di động sai vài trăm mét là thừa đủ để XẾP THỨ TỰ
      // điểm gửi. `maximumAge` cho phép dùng lại bản đọc còn mới, khỏi đo lại.
      { enableHighAccuracy: false, timeout: 20000, maximumAge: 60000 },
    );
  }

  const tai = React.useCallback(() => {
    setLoi("");
    Promise.all([api.diemGui(), api.categories()])
      .then(([b, c]) => {
        setBinList(b.items);
        setNhomList(c.items);
      })
      .catch((e) => setLoi(e instanceof Error ? e.message : "Không tải được danh sách điểm gửi."));
  }, []);
  React.useEffect(tai, [tai]);

  if (loi) {
    return (
      <div className="min-h-full bg-cream px-[18px] pb-[108px] pt-[54px]">
        <ErrorState message={loi} onRetry={tai} />
      </div>
    );
  }
  if (!binList) {
    return (
      <div className="min-h-full bg-cream px-[18px] pb-[108px] pt-[54px]">
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }

  const tenNhom = new Map(nhomList.map((c) => [c.code, c.name]));
  // Chip chỉ dựng từ nhóm rác mà ít nhất một điểm gửi đang nhận — không bịa nhóm.
  const cacMaCoThung = Array.from(new Set(binList.flatMap((b) => b.category_codes)));
  const chipNhom = cacMaCoThung
    .map((ma) => ({ ma, ten: tenNhom.get(ma) ?? ma }))
    .sort((a, b) => a.ten.localeCompare(b.ten, "vi"));

  const loc = mauLoc ? binList.filter((b) => b.category_codes.includes(mauLoc)) : binList;
  // Khoảng cách tới điểm gửi, `null` khi chưa có mốc hoặc điểm chưa có toạ độ.
  const khoangCach = (d: DiemGui): number | null =>
    mocToaDo && d.lat !== null && d.lng !== null
      ? khoangCachKm(mocToaDo, { lat: d.lat, lng: d.lng })
      : null;

  // Có mốc thì gần nhất lên đầu — đó là câu hỏi người dùng đang hỏi. Chưa có mốc
  // thì giữ thứ tự cũ: còn chỗ trước, rồi theo tên.
  const sapXep = [...loc].sort((a, b) => {
    const ka = khoangCach(a);
    const kb = khoangCach(b);
    if (ka !== null && kb !== null && ka !== kb) return ka - kb;
    if (ka !== null && kb === null) return -1;
    if (ka === null && kb !== null) return 1;
    return THU_TU_XEP[a.tinh_trang] - THU_TU_XEP[b.tinh_trang] || a.name.localeCompare(b.name, "vi");
  });
  const cacBinTrenMap = sapXep.map(diemGuiThanhBin);

  const chonNhom = (ma: string | null) => {
    setMauLoc(ma);
    setDangChon(null);
  };

  const chip = (ten: string, dang: boolean) =>
    `flex-none cursor-pointer rounded-full px-3.5 py-1.5 text-[13px] font-bold ${
      dang ? "bg-ink text-white" : "border border-line-3 bg-surface text-muted"
    }`;

  return (
    <div className="min-h-full bg-cream px-[18px] pb-[108px] pt-[54px]">
      <h1 className="m-0 mb-1 font-[family-name:var(--font-display)] text-[28px] font-bold">Điểm gửi rác</h1>
      <p className="m-0 mb-3 text-[13px] font-semibold text-muted">
        Chọn loại rác để xem điểm gửi nào còn chỗ.
      </p>

      {/* Mốc tính khoảng cách. KHÔNG xin quyền vị trí lúc mở màn — chỉ xin khi
          người dùng tự chạm vào chip. Xin ngay lúc mở là kiểu bị từ chối nhiều
          nhất, mà trình duyệt đã nhớ "từ chối" thì rất khó lấy lại. */}
      <div className="gb-scroll -mx-[18px] mb-3 flex gap-2 overflow-x-auto px-[18px] pb-1">
        <button
          onClick={() => coNha && setMoc("nha")}
          disabled={!coNha}
          title={coNha ? undefined : "Tài khoản chưa gắn căn hộ nên chưa biết nhà bạn ở đâu"}
          className={chip("nha", moc === "nha" && coNha)}
          style={coNha ? undefined : { opacity: 0.5, cursor: "not-allowed" }}
        >
          Nơi ở của tôi
        </button>
        <button onClick={xinViTri} className={chip("gps", moc === "gps")}>
          {dangXinViTri ? "Đang lấy vị trí…" : "Vị trí hiện tại"}
        </button>
        {diaChi.map((d) => (
          <button key={d.id} onClick={() => setMoc(d.id)} className={chip(d.ten, moc === d.id)}>
            {d.ten}
          </button>
        ))}
        <button
          onClick={() => (dangThem ? dongThem() : setDangThem(true))}
          title="Thêm một chỗ bạn hay đi — chạm lên bản đồ để đánh dấu"
          className={chip("them", dangThem)}
        >
          {dangThem ? "Đóng" : "+"}
        </button>
      </div>
      {loiViTri && <div className="mb-3 text-[12px] font-semibold text-hazard-dark">{loiViTri}</div>}

      {/* Bảng thêm mốc. Không có ô nhập địa chỉ bằng chữ và không gọi dịch vụ
          geocoding nào — toạ độ chỉ đến từ cú chạm lên bản đồ ngay bên dưới. */}
      {dangThem && (
        <div className="mb-4 rounded-2xl border border-line bg-surface p-4">
          <input
            value={tenMoi}
            onChange={(e) => setTenMoi(e.target.value)}
            maxLength={40}
            placeholder="Tên gợi nhớ, ví dụ: Chỗ làm"
            className="mb-2 w-full rounded-xl border border-line-3 px-3 py-2 text-[14px] font-semibold outline-none focus:border-ink"
          />
          <p className="m-0 mb-3 text-[12px] font-semibold text-muted">
            {diemMoi
              ? `Đã đánh dấu ${diemMoi.lat.toFixed(5)}, ${diemMoi.lng.toFixed(5)} — chạm chỗ khác để đổi.`
              : "Chạm lên bản đồ bên dưới để đánh dấu chỗ đó."}
          </p>
          <div className="mb-3 flex gap-2">
            <button
              onClick={luuMoc}
              disabled={!tenMoi.trim() || !diemMoi}
              className="flex-1 rounded-xl bg-ink px-4 py-2 text-[14px] font-bold text-white disabled:opacity-40"
            >
              Lưu mốc này
            </button>
            <button
              onClick={dongThem}
              className="flex-none rounded-xl border border-line-3 bg-surface px-4 py-2 text-[14px] font-bold text-muted"
            >
              Huỷ
            </button>
          </div>
          {diaChi.length > 0 && (
            <div className="border-t border-line pt-3">
              <p className="m-0 mb-2 text-[12px] font-bold text-muted">Mốc đã lưu trên máy này</p>
              {diaChi.map((d) => (
                <div key={d.id} className="flex items-center justify-between gap-2 py-1">
                  <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{d.ten}</span>
                  <button
                    onClick={() => xoaMoc(d.id)}
                    aria-label={`Xoá mốc ${d.ten}`}
                    className="flex-none rounded-lg border border-line-3 px-2 py-1 text-[12px] font-bold text-hazard-dark"
                  >
                    Xoá
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="gb-scroll -mx-[18px] mb-4 flex gap-2 overflow-x-auto px-[18px] pb-1">
        <button onClick={() => chonNhom(null)} className={chip("Tất cả", mauLoc === null)}>
          Tất cả
        </button>
        {chipNhom.map((c) => (
          <button key={c.ma} onClick={() => chonNhom(c.ma)} className={chip(c.ten, mauLoc === c.ma)}>
            {c.ten}
          </button>
        ))}
      </div>

      {/* Đang thêm mốc thì bản đồ cao hơn — người dùng phải chạm trúng một chỗ
          cụ thể, 220px là quá chật để ngắm. */}
      <div className="lg:grid lg:grid-cols-2 lg:gap-5 lg:items-start">
      <div
        className={`mb-4 overflow-hidden rounded-2xl border lg:sticky lg:top-[70px] lg:col-span-1 lg:h-[560px] ${
          dangThem ? "h-[320px] border-ink" : "h-[220px] border-line"
        }`}
      >
        <BinMap
          bins={cacBinTrenMap}
          selected={dangChon ? diemGuiThanhBin(dangChon) : null}
          onSelect={(b) => {
            const tim = sapXep.find((x) => x.code === b.code);
            if (tim) setDangChon(tim);
          }}
          onMapClick={dangThem ? (lat, lng) => setDiemMoi({ lat, lng }) : undefined}
          diemDanhDau={dangThem ? diemMoi : null}
          viTriNguoiDung={viTriGps}
          tuMoc={mocToaDo}
          duongDi={duongDi}
        />
      </div>

      {sapXep.length === 0 ? (
        <EmptyState
          icon={IconXeThuGom}
          title="Không có điểm gửi nào nhận loại này"
          hint="Chọn vật liệu khác, hoặc báo ban quản lý để họ bổ sung điểm gửi."
        />
      ) : (
        sapXep.map((b) => {
          const mon = b.category_codes.map((ma) => tenNhom.get(ma) ?? ma).join(" · ");
          return (
            <Card
              key={b.code}
              className={`mb-3 cursor-pointer p-4 ${dangChon?.code === b.code ? "border-leaf" : ""}`}
              onClick={() => setDangChon(b)}
            >
              <div className="mb-1 flex items-start justify-between gap-2">
                <span className="text-[15px] font-bold">{b.name}</span>
                <span className={`flex-none rounded-full px-3 py-1 text-xs font-extrabold ${MAU_TINH_TRANG[b.tinh_trang]}`}>
                  {b.tinh_trang_vi}
                </span>
              </div>
              <div className="mb-1 flex items-baseline gap-2 text-[13px] font-semibold text-muted">
                <span className="min-w-0 flex-1 truncate">{b.address}</span>
                {khoangCach(b) !== null && (
                  <span className="flex-none font-extrabold text-ink-soft">
                    ~{dinhDangKhoangCach(khoangCach(b))}
                  </span>
                )}
              </div>
              <div className="text-[13px] font-bold text-bulky">{mon}</div>
            </Card>
          );
        })
        )}
      </div>
      </div>
    );
  }
