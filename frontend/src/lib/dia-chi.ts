/** Địa chỉ do cư dân tự đánh dấu — lưu trong máy, không gửi lên server.
 *
 *  Quyết định đã chốt: KHÔNG dùng dịch vụ geocoding. Người dùng gõ một cái tên
 *  gợi nhớ rồi chạm thẳng lên bản đồ để lấy toạ độ. Đổi lại, dữ liệu chỉ nằm ở
 *  máy này: xoá dữ liệu trình duyệt là mất, và máy khác không thấy.
 */

const KHOA = "greenbin_dia_chi";

export type DiaChiLuu = {
  /** Sinh lúc thêm, không bao giờ đổi — dùng làm `key` của React và để xoá. */
  id: string;
  ten: string;
  lat: number;
  lng: number;
};

/** localStorage là dữ liệu người dùng sửa được, nên mọi bản ghi đọc lên đều
 *  phải soi lại từng trường. Bản ghi hỏng bị bỏ im lặng, không làm hỏng cả list. */
function hopLe(x: unknown): x is DiaChiLuu {
  if (typeof x !== "object" || x === null) return false;
  const d = x as Record<string, unknown>;
  return (
    typeof d.id === "string" &&
    typeof d.ten === "string" &&
    typeof d.lat === "number" &&
    typeof d.lng === "number" &&
    Number.isFinite(d.lat) &&
    Number.isFinite(d.lng)
  );
}

/** Đọc danh sách đã lưu. Hỏng dữ liệu thì trả mảng rỗng, KHÔNG ném lỗi — màn
 *  điểm gửi không được chết vì một chuỗi JSON rác trong localStorage. */
export function docDiaChi(): DiaChiLuu[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KHOA);
    if (!raw) return [];
    const data: unknown = JSON.parse(raw);
    return Array.isArray(data) ? data.filter(hopLe) : [];
  } catch {
    return [];
  }
}

function ghi(ds: DiaChiLuu[]): DiaChiLuu[] {
  if (typeof window === "undefined") return ds;
  try {
    window.localStorage.setItem(KHOA, JSON.stringify(ds));
  } catch {
    // Hết dung lượng hoặc chế độ riêng tư chặn ghi. Danh sách trả về vẫn đúng
    // cho phiên này; lần sau mở lại thì mất. Thà vậy còn hơn ném lỗi ra UI.
  }
  return ds;
}

/** Thêm một địa chỉ, trả về danh sách SAU khi thêm. Tên bị cắt khoảng trắng
 *  thừa; tên rỗng bị từ chối và danh sách giữ nguyên. */
export function themDiaChi(ten: string, lat: number, lng: number): DiaChiLuu[] {
  const sach = ten.trim();
  if (!sach) return docDiaChi();
  const moi: DiaChiLuu = {
    id: `dc-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    ten: sach,
    lat,
    lng,
  };
  return ghi([...docDiaChi(), moi]);
}

/** Xoá theo id, trả về danh sách SAU khi xoá. */
export function xoaDiaChi(id: string): DiaChiLuu[] {
  return ghi(docDiaChi().filter((d) => d.id !== id));
}
