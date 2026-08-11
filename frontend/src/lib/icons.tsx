/** Bộ icon dùng chung cho toàn app — **một nguồn duy nhất**.
 *
 * Trước file này, giao diện trộn bốn loại ký hiệu: emoji màu (🚛 📦 🔒), ký hiệu
 * chữ đơn sắc (✓ ✕ ⚠ ✦), và tệ nhất là hai loại cho cùng một ý (✓ lẫn ✅,
 * ✕ lẫn ❌). Emoji còn được mỗi hệ điều hành vẽ một kiểu, nên cùng một màn hình
 * trên Android và trên iPhone nhìn ra hai sản phẩm khác nhau.
 *
 * Nay mọi icon đi qua đây. Tên đặt theo **ý nghĩa trong nghiệp vụ**, không theo
 * hình vẽ — đổi cả bộ icon sau này chỉ phải sửa đúng file này, không phải đi lùng
 * 93 chỗ rải rác trong 13 file.
 */

import {
  AlertTriangle,
  ArrowRight,
  Ban,
  Brush,
  Building2,
  CalendarDays,
  Camera,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Clock,
  CupSoda,
  Download,
  FileText,
  Flag,
  Frown,
  Hand,
  HelpCircle,
  Hourglass,
  Image,
  Leaf,
  Lock,
  Magnet,
  MapPin,
  MessageCircle,
  Monitor,
  Package,
  PartyPopper,
  Pencil,
  PenLine,
  Recycle,
  RefreshCw,
  Search,
  SkipForward,
  Smartphone,
  Sofa,
  Sparkles,
  Sprout,
  ThumbsDown,
  ThumbsUp,
  Timer,
  Trash2,
  TrendingDown,
  TrendingUp,
  Truck,
  Undo2,
  User,
  Wine,
  X,
  Zap,
  type LucideIcon,
  type LucideProps,
} from "lucide-react";
import * as React from "react";

/** Nét vẽ chung — khớp với mấy hình tự vẽ tay còn lại ở `shell.tsx`, `ask.tsx`,
 *  `result.tsx` và `onboarding.tsx` (đều dùng 1,9–2,4). */
const STROKE_WIDTH = 2.2;

/** Cỡ mặc định vừa với chữ trong dòng. Đặt `className="h-8 w-8"` là ghi đè được
 *  vì CSS thắng thuộc tính `width`/`height` của thẻ `<svg>`. */
const DEFAULT_SIZE = 16;

/** Icon là hình trang trí — nội dung phải nằm ở chữ bên cạnh, không nằm ở icon.
 *  Nên `aria-hidden` bật sẵn; chỗ nào icon là thông tin duy nhất thì truyền
 *  `aria-hidden={false}` kèm `aria-label`. */
function defineIcon(Base: LucideIcon, displayName: string): LucideIcon {
  const Wrapped = React.forwardRef<SVGSVGElement, LucideProps>((props, ref) => (
    <Base ref={ref} size={DEFAULT_SIZE} strokeWidth={STROKE_WIDTH} aria-hidden {...props} />
  ));
  Wrapped.displayName = displayName;
  return Wrapped as LucideIcon;
}

// --- Hành động và trạng thái ---------------------------------------------

export const IconDuyet = defineIcon(Check, "IconDuyet");
export const IconXongHet = defineIcon(CheckCircle2, "IconXongHet");
export const IconTuChoi = defineIcon(X, "IconTuChoi");
export const IconCanhBao = defineIcon(AlertTriangle, "IconCanhBao");
export const IconCam = defineIcon(Ban, "IconCam");
export const IconChoDuyet = defineIcon(Hourglass, "IconChoDuyet");
export const IconBoQua = defineIcon(SkipForward, "IconBoQua");
export const IconHoanTac = defineIcon(Undo2, "IconHoanTac");
export const IconLamLai = defineIcon(RefreshCw, "IconLamLai");
export const IconSua = defineIcon(Pencil, "IconSua");
export const IconTang = defineIcon(TrendingUp, "IconTang");
export const IconGiam = defineIcon(TrendingDown, "IconGiam");

/** Dấu hiệu "chỗ này do AI sinh ra" — trước đây là ✦, dùng ở khối AI đề xuất,
 *  AI giải thích và AI ước lượng khối lượng. */
export const IconAi = defineIcon(Sparkles, "IconAi");

/** Ca khó hay bị nhầm, rút từ eval — trước đây là ⚑. */
export const IconCaKho = defineIcon(Flag, "IconCaKho");

// --- Điều hướng -----------------------------------------------------------

export const IconMuiTenPhai = defineIcon(ArrowRight, "IconMuiTenPhai");
export const IconTiepTuc = defineIcon(ChevronRight, "IconTiepTuc");
export const IconQuayLai = defineIcon(ChevronLeft, "IconQuayLai");

// --- Nghiệp vụ ------------------------------------------------------------

export const IconXeThuGom = defineIcon(Truck, "IconXeThuGom");
export const IconMonDo = defineIcon(Package, "IconMonDo");
export const IconLichSuChuyen = defineIcon(ClipboardList, "IconLichSuChuyen");
export const IconLichThuGom = defineIcon(CalendarDays, "IconLichThuGom");
export const IconViTri = defineIcon(MapPin, "IconViTri");
export const IconKhungGio = defineIcon(Clock, "IconKhungGio");
export const IconToaNha = defineIcon(Building2, "IconToaNha");
export const IconDoiVeSinh = defineIcon(Brush, "IconDoiVeSinh");
export const IconNguoiDung = defineIcon(User, "IconNguoiDung");
export const IconMamXanh = defineIcon(Sprout, "IconMamXanh");

/** Hạn tự xoá ảnh cư dân — khác `IconKhungGio` ở chỗ đây là đồng hồ đếm ngược. */
export const IconTuXoa = defineIcon(Timer, "IconTuXoa");

// --- Định tuyến model -----------------------------------------------------

/** Tầng T2 soi kỹ — trước đây là 🔍. */
export const IconSoiKy = defineIcon(Search, "IconSoiKy");
/** Các tầng rẻ và nhanh — trước đây là ⚡. */
export const IconNhanh = defineIcon(Zap, "IconNhanh");

// --- Quyền riêng tư và an toàn --------------------------------------------

export const IconKhoa = defineIcon(Lock, "IconKhoa");

// --- Nhập liệu ------------------------------------------------------------

export const IconChupAnh = defineIcon(Camera, "IconChupAnh");
export const IconChonAnh = defineIcon(Image, "IconChonAnh");
export const IconMoTaChu = defineIcon(PenLine, "IconMoTaChu");
export const IconHoiBanQuanLy = defineIcon(MessageCircle, "IconHoiBanQuanLy");
export const IconHuuIch = defineIcon(ThumbsUp, "IconHuuIch");
export const IconSaiRoi = defineIcon(ThumbsDown, "IconSaiRoi");

// --- Cài app --------------------------------------------------------------

export const IconCaiApp = defineIcon(Smartphone, "IconCaiApp");
export const IconTaiVe = defineIcon(Download, "IconTaiVe");
export const IconManHinhRong = defineIcon(Monitor, "IconManHinhRong");

// --- Trạng thái rỗng và cảm xúc -------------------------------------------

export const IconChao = defineIcon(Hand, "IconChao");
export const IconChucMung = defineIcon(PartyPopper, "IconChucMung");
export const IconGapLoi = defineIcon(Frown, "IconGapLoi");
export const IconChuaChac = defineIcon(HelpCircle, "IconChuaChac");

/** "Chưa tìm thấy bản ghi nào" — cùng hình với `IconSoiKy` nhưng khác ý nghĩa,
 *  nên tách tên: đổi hình cho một trong hai sau này không kéo theo cái còn lại. */
export const IconTim = defineIcon(Search, "IconTim");

// --- Nhóm rác -------------------------------------------------------------

/** Ánh xạ mã nhóm rác của backend sang icon.
 *
 * Cột `waste_categories.icon` trong CSDL vẫn giữ emoji cũ (`src/db/seed_data.py`)
 * để không phải seed lại dữ liệu, nhưng **frontend không đọc cột đó nữa** — icon
 * là chuyện của giao diện, không phải của CSDL. Thêm nhóm rác mới thì thêm một
 * dòng ở đây; quên thì rơi về `IconNhomRacMacDinh` chứ không vỡ màn hình.
 */
const ICON_THEO_NHOM: Record<string, LucideIcon> = {
  recyclable: defineIcon(Recycle, "IconRacTaiChe"),
  recyclable_paper: defineIcon(FileText, "IconGiayBia"),
  recyclable_plastic: defineIcon(CupSoda, "IconNhuaTaiChe"),
  recyclable_metal: defineIcon(Magnet, "IconKimLoai"),
  recyclable_glass: defineIcon(Wine, "IconThuyTinh"),
  organic: defineIcon(Leaf, "IconRacThucPham"),
  other: defineIcon(Trash2, "IconRacSinhHoatKhac"),
  hazardous: defineIcon(AlertTriangle, "IconRacNguyHai"),
  bulky: defineIcon(Sofa, "IconDoCongKenh"),
};

export const IconNhomRacMacDinh = defineIcon(Recycle, "IconNhomRacMacDinh");

/** Icon của một nhóm rác, tra theo mã nhóm trả về từ API. */
export function IconNhomRac({ code, ...props }: { code: string } & LucideProps) {
  const Icon = ICON_THEO_NHOM[code] ?? IconNhomRacMacDinh;
  return <Icon {...props} />;
}
