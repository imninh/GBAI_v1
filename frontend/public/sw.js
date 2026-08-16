/* Service worker của GreenBin AI — viết tay, không thêm phụ thuộc.
 *
 * `next-pwa` chưa theo kịp App Router nên không đáng rước rủi ro cho ~70 dòng.
 *
 * Bốn chính sách, theo đúng thứ tự kiểm tra trong `fetch`:
 *
 *   1. Điều hướng (trang HTML) → **network-first**, chỉ lui về cache khi mất
 *      mạng. Xem ghi chú bên dưới, đây là chỗ từng có lỗi thật.
 *   2. Tài nguyên tĩnh có hash trong tên → cache-first.
 *   3. Ba endpoint tra cứu công khai → stale-while-revalidate, để **màn Lịch
 *      thu gom xem được khi không có mạng** (FRONTEND_SPEC mục 2.5).
 *   4. Mọi thứ còn lại → network-only, không đụng vào cache.
 *
 * ⚠️ Vì sao trang HTML KHÔNG được cache-first (lỗi đã gặp thật 02/08):
 * `index.html` là file duy nhất trong bản export **không có hash trong tên**.
 * Cache-first nó đồng nghĩa người dùng bị ghim vĩnh viễn vào bản đầu tiên họ
 * từng mở — đẩy bao nhiêu bản lên Vercel họ cũng không thấy, vì file quyết định
 * nạp chunk nào lại chính là file không bao giờ được làm mới. Lỗi càng khó thấy
 * vì `activate` xoá cache theo điều kiện `!t.startsWith(PHIEN_BAN)`, mà
 * `PHIEN_BAN` là hằng số cứng nên điều kiện đó không bao giờ đúng.
 *
 * Ranh giới không được vượt: **không bao giờ cache ảnh cư dân hay endpoint có
 * token.** Quyền riêng tư đứng trước tiện lợi — một tấm ảnh rác nằm lại trong
 * cache của máy là đúng thứ mà cả mục 5 của CLAUDE.md đang tìm cách tránh.
 */

// Tăng số này khi đổi CHIẾN LƯỢC cache (không cần tăng mỗi lần deploy: từ khi
// trang HTML chạy network-first thì bản mới tự tới, không phụ thuộc số này).
const PHIEN_BAN = "greenbin-v2";
const CACHE_VO = `${PHIEN_BAN}-vo`;
const CACHE_TRA_CUU = `${PHIEN_BAN}-tra-cuu`;

// Nạp sẵn lúc cài để lần mở đầu tiên khi mất mạng vẫn có gì đó hiện ra.
const NAP_SAN = ["/", "/tai-app/", "/manifest.webmanifest", "/icons/icon-192.png"];

/** Endpoint tra cứu được phép cache: công khai, không token, không dữ liệu cá nhân. */
function laTraCuuCongKhai(pathname) {
  return (
    pathname.endsWith("/api/v1/categories") ||
    pathname.endsWith("/api/v1/meta/enums") ||
    /\/api\/v1\/buildings\/\d+\/schedule$/.test(pathname)
  );
}

/** Tài nguyên tĩnh của bản export — an toàn để cache-first vì tên file có hash. */
function laVoUngDung(url, request) {
  if (url.origin !== self.location.origin) return false;
  if (url.pathname.startsWith("/api/")) return false;
  return request.destination !== "" || url.pathname === "/" || url.pathname.endsWith("/");
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_VO)
      .then((cache) => cache.addAll(NAP_SAN))
      .catch(() => undefined) // thiếu một file không được làm hỏng cả lần cài
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((ten) => Promise.all(ten.filter((t) => !t.startsWith(PHIEN_BAN)).map((t) => caches.delete(t))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  // Chỉ đụng vào GET. POST/PATCH/DELETE luôn phải đi thẳng ra mạng.
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Trang HTML: mạng trước. Phải đứng TRƯỚC `laVoUngDung` vì hàm đó cũng nhận
  // "/" — xem ghi chú đầu file về việc index.html không có hash trong tên.
  if (request.mode === "navigate") {
    event.respondWith(mangTruocCacheSau(request));
    return;
  }

  if (laTraCuuCongKhai(url.pathname)) {
    event.respondWith(cuTruocMoiSau(request));
    return;
  }

  if (laVoUngDung(url, request)) {
    event.respondWith(cacheTruoc(request));
  }
  // Còn lại: không gọi respondWith → trình duyệt tự đi mạng như bình thường.
});

/** Network-first: luôn lấy bản mới nhất, mất mạng mới lui về cache.
 *
 * Dành riêng cho trang HTML. Đắt hơn cache-first một chuyến mạng, nhưng đó là
 * cái giá để bản deploy mới tới được tay người dùng — và khi mất mạng thì vẫn
 * lui về được bản đã lưu, nên lời hứa "xem lịch thu gom offline" không mất.
 */
async function mangTruocCacheSau(request) {
  try {
    const phanHoi = await fetch(request);
    if (phanHoi.ok) {
      const cache = await caches.open(CACHE_VO);
      cache.put(request, phanHoi.clone());
    }
    return phanHoi;
  } catch (loi) {
    const daCo = (await caches.match(request)) || (await caches.match("/"));
    if (daCo) return daCo;
    throw loi;
  }
}

/** Cache-first: trả bản đã lưu ngay, chỉ ra mạng khi chưa có. */
async function cacheTruoc(request) {
  const daCo = await caches.match(request);
  if (daCo) return daCo;
  try {
    const phanHoi = await fetch(request);
    if (phanHoi.ok) {
      const cache = await caches.open(CACHE_VO);
      cache.put(request, phanHoi.clone());
    }
    return phanHoi;
  } catch (loi) {
    // Điều hướng khi mất mạng: trả trang gốc đã cache để app tự dựng lại.
    if (request.mode === "navigate") {
      const goc = await caches.match("/");
      if (goc) return goc;
    }
    throw loi;
  }
}

/** Stale-while-revalidate: trả bản cũ ngay, đồng thời làm mới ngầm. */
async function cuTruocMoiSau(request) {
  const cache = await caches.open(CACHE_TRA_CUU);
  const daCo = await cache.match(request);

  const dangLayMoi = fetch(request)
    .then((phanHoi) => {
      if (phanHoi.ok) cache.put(request, phanHoi.clone());
      return phanHoi;
    })
    .catch(() => undefined);

  if (daCo) return daCo;

  const moi = await dangLayMoi;
  if (moi) return moi;

  // Chưa từng cache mà cũng không có mạng: trả đúng khuôn lỗi của backend để
  // giao diện hiện ErrorState quen thuộc thay vì một lỗi fetch trần trụi.
  return new Response(
    JSON.stringify({
      error: { code: "NET-503", message_vi: "Không có mạng và chưa có bản lưu offline cho mục này." },
    }),
    { status: 503, headers: { "Content-Type": "application/json" } },
  );
}
