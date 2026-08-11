/** Một cửa duy nhất để lấy ảnh, che khác biệt giữa app cài về và web.
 *
 * Trong app Android đóng gói bằng Capacitor thì mở camera thật của hệ thống
 * (đúng quy trình xin quyền của Android); trên web thì vẫn dùng
 * `<input type="file" capture>` như trước. Màn hình gọi `chupAnh()` /
 * `chonAnh()` và không cần biết mình đang chạy ở đâu.
 */

import { Capacitor } from "@capacitor/core";

/** Đang chạy trong app cài về (Android/iOS) chứ không phải tab trình duyệt. */
export function laAppNative(): boolean {
  return Capacitor.isNativePlatform();
}

export type NguonAnh = "camera" | "thu-vien";

/**
 * Mở camera chụp một tấm. Trả về `null` khi người dùng bấm huỷ.
 *
 * Ném lỗi khi bị từ chối quyền — chỗ gọi bắt lấy để hiện câu tiếng Việt thay vì
 * để màn hình đứng im không hiểu chuyện gì.
 */
export function chupAnh(): Promise<File | null> {
  return layAnh("camera");
}

/** Chọn một ảnh có sẵn trong máy. */
export function chonAnh(): Promise<File | null> {
  return layAnh("thu-vien");
}

async function layAnh(nguon: NguonAnh): Promise<File | null> {
  if (laAppNative()) return layAnhNative(nguon);
  return layAnhWeb(nguon);
}

// --- App cài về ----------------------------------------------------------

async function layAnhNative(nguon: NguonAnh): Promise<File | null> {
  // Nhập động: gói camera chỉ có ích trong app native, không kéo vào bundle web.
  const { Camera, CameraResultType, CameraSource } = await import("@capacitor/camera");

  const anh = await Camera.getPhoto({
    quality: 82,
    // Backend vẫn nén về 512px, nên gửi ảnh vừa phải là đủ — vừa nhanh vừa đỡ
    // tốn 3G của đội vệ sinh dưới hầm.
    width: 1280,
    allowEditing: false,
    correctOrientation: true,
    resultType: CameraResultType.Uri,
    source: nguon === "camera" ? CameraSource.Camera : CameraSource.Photos,
  });

  if (!anh.webPath) return null;

  const blob = await (await fetch(anh.webPath)).blob();
  const duoi = anh.format || "jpeg";
  return new File([blob], `rac-${Date.now()}.${duoi}`, { type: blob.type || `image/${duoi}` });
}

// --- Web -----------------------------------------------------------------

function layAnhWeb(nguon: NguonAnh): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    // `capture` bảo trình duyệt di động mở thẳng camera sau; máy tính bỏ qua.
    if (nguon === "camera") input.setAttribute("capture", "environment");
    input.style.display = "none";

    const xong = () => {
      resolve(input.files?.[0] ?? null);
      input.remove();
    };
    input.addEventListener("change", xong, { once: true });
    // Người dùng bấm Huỷ: `cancel` có ở các trình duyệt hiện đại; trình duyệt cũ
    // không bắn gì cả và promise treo vô hại cho tới khi rời màn hình.
    input.addEventListener("cancel", xong, { once: true });

    document.body.appendChild(input);
    // Bấm ngay trong cùng nhịp xử lý sự kiện — Safari chặn nếu await trước đó.
    input.click();
  });
}
