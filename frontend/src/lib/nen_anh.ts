/** Nén ảnh ngay trên máy người dùng trước khi gửi lên máy chủ.
 *
 *  Ảnh máy ảnh điện thoại đời mới là 3–6 MB / 4000×3000. Gửi thẳng file đó đi
 *  tốn 3–10 giây qua 4G, rồi máy chủ lại tốn thêm 4,1 giây để giải mã, làm mờ
 *  mặt và thu nhỏ. Nén trước ở đây cắt cả hai khâu cùng lúc.
 *
 *  KHÔNG nén xuống 512px: máy chủ còn giữ một bản "ảnh gốc" cho ban quản lý mở
 *  khi có tranh chấp. 1600px vẫn là bằng chứng đọc được; 512px thì không.
 */
export const CANH_DAI_TOI_DA = 1600;
export const CHAT_LUONG = 0.85;

/** Đọc ảnh vào `HTMLImageElement` qua object URL; thu hồi URL trong mọi nhánh. */
function taiAnhVaoImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("không giải mã được ảnh"));
    };
    image.src = url;
  });
}

function veRaCanvas(image: HTMLImageElement, tiLe: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(image.naturalWidth * tiLe));
  canvas.height = Math.max(1, Math.round(image.naturalHeight * tiLe));
  const ctx = canvas.getContext("2d");
  if (ctx) ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
  return canvas;
}

/** Trình duyệt cũ không có `canvas.toBlob` → hàm ném lỗi, rơi vào nhánh catch ngoài. */
function toBlob(canvas: HTMLCanvasElement): Promise<Blob | null> {
  return new Promise((resolve) => {
    canvas.toBlob(resolve, "image/jpeg", CHAT_LUONG);
  });
}

export async function nenAnh(file: File): Promise<File> {
  if (typeof document === "undefined") return file;
  try {
    const image = await taiAnhVaoImage(file);
    const rong = image.naturalWidth;
    const cao = image.naturalHeight;
    // Ảnh đã nhỏ ở CẢ HAI chiều → trả nguyên, không mã hoá lại. Mã hoá lại một
    // ảnh nhỏ chỉ làm nó xấu đi mà không nhỏ hơn.
    if (rong <= CANH_DAI_TOI_DA && cao <= CANH_DAI_TOI_DA) return file;

    // CANH_DAI_TOI_DA là cạnh DÀI tối đa → phải chia cho cạnh DÀI (`Math.max`).
    // Chia nhầm cho cạnh ngắn (`Math.min`) thì cạnh dài sau thu nhỏ còn
    // 1600 × (dài/ngắn) — ảnh to hơn ý định ~78% số điểm ảnh, đúng thứ gói này
    // sinh ra để cắt.
    const tiLe = CANH_DAI_TOI_DA / Math.max(rong, cao);
    const blob = await toBlob(veRaCanvas(image, tiLe));
    if (!blob) return file;

    // Truyền thẳng Blob vào FormData thì trình duyệt gửi `filename="blob"`
    // không đuôi — phải bọc trong File có tên đuôi .jpg.
    return new File([blob], "anh.jpg", { type: "image/jpeg" });
  } catch {
    // Trình duyệt cũ không có toBlob · ảnh HEIC không giải mã được · canvas bị
    // chặn vì lý do bảo mật… Tất cả đều rơi êm về "gửi như cũ" — chậm còn hơn
    // không gửi được.
    return file;
  }
}
