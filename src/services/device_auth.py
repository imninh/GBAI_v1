"""Device authentication via the ``X-Device-Key`` header (spec §8).

Keys are configured as ``device_id:key`` pairs so a stolen key cannot be used to
impersonate a different bin:

    IOT_DEVICE_KEYS=GBIN-001:key-one,GBIN-002:key-two
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
import time
from functools import lru_cache

from src.config import get_settings

logger = logging.getLogger(__name__)


class DeviceAuthError(Exception):
    """Raised when a device presents no key or a bad one."""


@lru_cache
def _key_table() -> dict[str, str]:
    settings = get_settings()
    table: dict[str, str] = {}
    for entry in settings.iot_device_keys.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        device_id, _, key = entry.partition(":")
        device_id, key = device_id.strip(), key.strip()
        if device_id and key:
            table[device_id] = key
    return table


def reset_cache() -> None:
    """Test hook: re-read settings after they are patched."""
    _key_table.cache_clear()


def authenticate(device_key: str | None, device_id: str | None = None) -> str:
    """Verify a device key and return the authenticated device id.

    Raises :class:`DeviceAuthError` on any failure. Callers must not distinguish
    "unknown device" from "wrong key" in their response — that difference tells
    an attacker which half they got right.
    """
    if not device_key:
        raise DeviceAuthError("Missing X-Device-Key header")

    table = _key_table()
    if not table:
        raise DeviceAuthError("No device keys configured on the server")

    if device_id:
        expected = table.get(device_id)
        # compare_digest even on the miss path, so the timing of a wrong device
        # id matches the timing of a wrong key.
        if expected is None or not secrets.compare_digest(expected, device_key):
            raise DeviceAuthError("Invalid device credentials")
        return device_id

    # No device id claimed: accept any configured key and report whose it was.
    for known_id, known_key in table.items():
        if secrets.compare_digest(known_key, device_key):
            return known_id

    raise DeviceAuthError("Invalid device credentials")


# --- Chống phát lại: cửa sổ thời gian + chữ ký HMAC --------------------------
#
# Thiết bị gửi kèm hai header:
#   X-Device-Timestamp  mốc thời gian Unix (giây)
#   X-Device-Signature  HMAC-SHA256(khoá_thô, "{device_id}.{timestamp}"), hex
#
# Khoá HMAC là CHUỖI KHOÁ THÔ vừa xác thực thành công — không phải bản băm
# trong CSDL. Nhờ vậy lớp này phủ được CẢ thùng dùng khoá chung (BIẾN môi
# trường) lẫn thùng có ``device_key_hash`` riêng: với thùng khoá riêng, server
# không giữ khoá thô trong CSDL, nhưng thiết bị vừa gửi khoá thô đó trong
# header ``X-Device-Key`` và nó đã mở được thùng ⇒ đủ để tính lại chữ ký.

_da_thay: dict[tuple[str, int, str], float] = {}
_khoa_bo_nho = threading.Lock()


def reset_replay_store() -> None:
    """Test hook / dọn dẹp: xoá sạch bộ nhớ chống phát lại."""
    with _khoa_bo_nho:
        _da_thay.clear()


def _ghi_dau_vet(device_id: str, ts: int, chu_ky: str, cua_so: int) -> bool:
    """Ghi dấu một bộ ba đã thấy; trả ``False`` nếu nó đã từng thấy trong cửa sổ.

    Dọn mục quá hạn ngay mỗi lần ghi — bộ nhớ không bao giờ lớn hơn số request
    hợp lệ trong một cửa sổ của tiến trình hiện tại.
    """
    bay = time.time()
    with _khoa_bo_nho:
        for k in [k for k, t in _da_thay.items() if bay - t > cua_so]:
            del _da_thay[k]
        khoa = (device_id, ts, chu_ky)
        if khoa in _da_thay:
            return False
        _da_thay[khoa] = bay
    return True


def kiem_chong_phat_lai(
    device_id: str,
    khoa_tho: str,
    timestamp_header: str | None,
    chu_ky_header: str | None,
) -> bool:
    """Xác minh bộ ba chống phát lại; ``False`` nghĩa là phải chặn 401.

    Chấp nhận khi ĐỦ BA điều kiện:

    1. Chữ ký khớp — so bằng ``hmac.compare_digest``, không dùng ``==``;
    2. Timestamp lệch máy chủ không quá cửa sổ ``iot_cua_so_thoi_gian_s`` giây
       (cả lệch về quá khứ lẫn tương lai);
    3. Cặp ``(device_id, timestamp, chữ_ký)`` chưa từng thấy trong cửa sổ.

    Mọi lý do từ chối đều chỉ ghi LOG máy chủ và trả ``False`` — phía HTTP trả
    chung MỘT thông báo 401, không tiết lộ sai ở đâu.

    ⚠️ Giới hạn đa-worker: bộ nhớ trùng nằm TRONG TIẾN TRÌNH. Chạy nhiều worker
    (uvicorn ``--workers N``) thì mỗi worker một bộ nhớ riêng — phát lại sang
    worker khác vẫn lọt qua. Đây là lựa chọn chủ đích: lớp này không đụng CSDL,
    đổi lại chỉ kín hoàn toàn khi triển khai một tiến trình.
    """
    cua_so = max(1, int(get_settings().iot_cua_so_thoi_gian_s))
    ly_do = ""
    if not timestamp_header or not chu_ky_header:
        ly_do = "thiếu header chống phát lại"
    else:
        try:
            ts = int(str(timestamp_header).strip())
        except ValueError:
            ly_do = "timestamp không parse được"
        else:
            lech = abs(time.time() - ts)
            if lech > cua_so:
                ly_do = f"lệch thời gian {lech:.0f}s vượt cửa sổ {cua_so}s"
            else:
                ky_dung = hmac.new(
                    khoa_tho.encode("utf-8"),
                    f"{device_id}.{ts}".encode(),
                    hashlib.sha256,
                ).hexdigest()
                if not hmac.compare_digest(ky_dung, str(chu_ky_header).strip().lower()):
                    ly_do = "chữ ký sai"
                elif not _ghi_dau_vet(device_id, ts, ky_dung, cua_so):
                    ly_do = "phát lại"
    if ly_do:
        logger.warning("Chống phát lại chặn device %s: %s.", device_id or "?", ly_do)
        return False
    return True
