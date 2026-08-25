"use client";

import * as React from "react";

import { api, ApiError, getToken, setToken } from "./api";
import type { Permissions, User } from "./types";

interface SessionValue {
  user: User | null;
  permissions: Permissions;
  loading: boolean;
  error: string;
  dangNhap: (email: string, password: string) => Promise<User>;
  dangNhapSdt: (phone: string, password: string) => Promise<User>;
  /** Đăng ký rồi vào thẳng. Không nhận `role` — vai trò do server quyết. */
  dangKy: (payload: {
    phone: string;
    password: string;
    full_name: string;
    unit_id?: number | null;
  }) => Promise<User>;
  dangXuat: () => void;
  /** Thay hồ sơ + quyền của phiên bằng dữ liệu server vừa trả, không đụng token. */
  capNhatPhien: (data: { user: User; permissions: Permissions }) => void;
  /** Vai trò hiện tại có quyền này không. Không có quyền thì UI hiện mờ kèm
   *  tooltip giải thích, **không ẩn hẳn** — để ranh giới phân quyền nhìn thấy được. */
  duocPhep: (permission: string) => boolean;
  lyDoCam: (permission: string) => string;
}

const SessionContext = React.createContext<SessionValue | null>(null);

// --- Phiên lưu máy (offline-first) -----------------------------------------
//
// Boot gọi `/auth/me` để biết còn đăng nhập không — mà endpoint đó cần token,
// KHÔNG cache được ở SW (ranh giới riêng tư của sw.js). Offline thì lời gọi ấy
// fail và app từng tưởng "chưa đăng nhập" → rơi về onboarding, dù lịch toà vẫn
// nằm trong cache. Vậy nên lưu bản hồ sơ TỐI THIỂU vào localStorage khi online:
// có token + có bản lưu ⇒ boot offline vẫn vào thẳng app, lời gọi /auth/me chỉ
// còn vai trò làm mới nền. Chỉ dữ liệu dựng màn (tên/vai/căn hộ/toà) — không
// ảnh, không thêm thông tin nhạy cảm hơn token vốn đã nằm trong localStorage.
const KHOA_PHIEN_LUU = "greenbin_phien_luu";

type PhienLuu = { user: User; permissions: Permissions };

/** Bản ghi hỏng bị bỏ im lặng — localStorage là dữ liệu người dùng sửa được. */
function docPhienLuu(): PhienLuu | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KHOA_PHIEN_LUU);
    if (!raw) return null;
    const du = JSON.parse(raw) as Partial<PhienLuu>;
    if (!du || typeof du !== "object") return null;
    const u = du.user as User | undefined;
    if (!u || typeof u.id !== "number" || typeof u.role !== "string") return null;
    if (!du.permissions || typeof du.permissions !== "object") return null;
    return { user: u, permissions: du.permissions };
  } catch {
    return null;
  }
}

function ghiPhienLuu(phien: PhienLuu): void {
  try {
    window.localStorage.setItem(KHOA_PHIEN_LUU, JSON.stringify(phien));
  } catch {
    // Hết chỗ / chế độ riêng tư — bỏ qua, mất offline boot chứ không mất phiên.
  }
}

function xoaPhienLuu(): void {
  try {
    window.localStorage.removeItem(KHOA_PHIEN_LUU);
  } catch {
    /* bỏ qua */
  }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null);
  const [permissions, setPermissions] = React.useState<Permissions>({});
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let huy = false;

    // Boot offline-first: token còn trong máy + đã từng lưu hồ sơ ⇒ coi là đang
    // đăng nhập NGAY, dựng màn từ bản lưu. KHÔNG chờ mạng, KHÔNG ép gọi mới.
    const daLuu = docPhienLuu();
    if (getToken() && daLuu) {
      setUser(daLuu.user);
      setPermissions(daLuu.permissions);
      setLoading(false);
    }

    // Làm mới nền: online thì cập nhật bản mới nhất; offline fail thì GIỮ nguyên
    // bản đã phục hồi ở trên — tuyệt đối không reset về onboarding.
    api
      .me()
      .then((data) => {
        if (huy) return;
        setUser(data.user);
        setPermissions(data.permissions);
        ghiPhienLuu({ user: data.user, permissions: data.permissions });
      })
      .catch(() => {
        /* offline + có bản lưu: giữ phiên đã phục hồi. Chưa từng lưu: chưa
           đăng nhập là trạng thái bình thường, không phải lỗi. */
      })
      .finally(() => !huy && setLoading(false));
    return () => {
      huy = true;
    };
  }, []);

  /** Nhận một phiên mới. Ba đường vào — đăng nhập email, đăng nhập SĐT, đăng ký
   *  — đều trả về cùng khuôn `{token, user, permissions}`, nên gom vào một chỗ. */
  const nhanPhien = React.useCallback(
    (data: { token: string; user: User; permissions: Permissions }) => {
      setToken(data.token);
      setUser(data.user);
      setPermissions(data.permissions);
      ghiPhienLuu({ user: data.user, permissions: data.permissions });
      return data.user;
    },
    [],
  );

  // Đường email. BA NÚT "VÀO THẲNG" ĐI ĐÚNG ĐƯỜNG NÀY — giữ nguyên chữ ký.
  const dangNhap = React.useCallback(
    async (email: string, password: string) => {
      setError("");
      try {
        return nhanPhien(await api.login(email, password));
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Không đăng nhập được.";
        setError(message);
        throw err;
      }
    },
    [nhanPhien],
  );

  const dangNhapSdt = React.useCallback(
    async (phone: string, password: string) => {
      setError("");
      try {
        return nhanPhien(await api.loginPhone(phone, password));
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Không đăng nhập được.";
        setError(message);
        throw err;
      }
    },
    [nhanPhien],
  );

  /** Đăng ký rồi vào luôn — server trả token ngay trong phản hồi đăng ký. */
  const dangKy = React.useCallback(
    async (payload: { phone: string; password: string; full_name: string; unit_id?: number | null }) => {
      setError("");
      try {
        return nhanPhien(await api.register(payload));
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Không tạo được tài khoản.";
        setError(message);
        throw err;
      }
    },
    [nhanPhien],
  );

  const dangXuat = React.useCallback(() => {
    setToken(null);
    setUser(null);
    setPermissions({});
    xoaPhienLuu();
  }, []);

  /** Thay hồ sơ và ma trận quyền của phiên đang chạy bằng dữ liệu server vừa trả.
   *
   *  Dùng sau khi sửa hồ sơ: đổi căn hộ là đổi toạ độ nơi ở, mà toạ độ đó đang
   *  được màn "Điểm gửi" dùng làm mốc sắp xếp. Bắt người dùng tải lại trang mới
   *  thấy thay đổi là hỏng. KHÔNG đụng tới token — token không đổi khi sửa hồ sơ.
   */
  const capNhatPhien = React.useCallback((data: { user: User; permissions: Permissions }) => {
    setUser(data.user);
    setPermissions(data.permissions);
    ghiPhienLuu({ user: data.user, permissions: data.permissions });
  }, []);

  const value: SessionValue = {
    user,
    permissions,
    loading,
    error,
    dangNhap,
    dangNhapSdt,
    dangKy,
    dangXuat,
    capNhatPhien,
    duocPhep: (permission) => permissions[permission]?.allowed ?? false,
    lyDoCam: (permission) => permissions[permission]?.reason ?? "Vai trò của bạn không có quyền này",
  };

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const context = React.useContext(SessionContext);
  if (!context) throw new Error("useSession phải nằm trong SessionProvider");
  return context;
}
