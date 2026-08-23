"""Sinh hai tệp âm báo thông báo cho ứng dụng Android.

Vì sao tự sinh thay vì tải về: đồ án được chấm nên mọi tài nguyên phải rõ nguồn
gốc. Âm tổng hợp bằng script thì không vướng giấy phép, tái tạo được y hệt, và
sửa được bằng cách đổi tham số thay vì chỉnh tay trong phần mềm biên tập.

Quy cách nhắm tới (Android bỏ qua hoặc phát méo nếu sai):

* dài **0,8 – 1,5 giây** — dài hơn thì một số máy cắt giữa chừng;
* **WAV PCM 16-bit**, 44,1 kHz, **mono** — an toàn nhất giữa các đời máy;
* đỉnh khoảng **−3 dBFS**, KHÔNG nén kịch trần — âm báo to hơn âm hệ thống thì
  người dùng tắt thông báo;
* **không có khoảng lặng ở đầu** — trễ 200 ms là cảm giác máy đơ;
* **fade 100 ms ở cuối** để không nghe tiếng "tách".

Đặt tệp vào ``frontend/android/app/src/main/res/raw/``. Tên tệp phải là chữ
thường, chỉ chữ cái/số/gạch dưới, không dấu tiếng Việt — Android từ chối build
nếu sai, kèm thông báo lỗi rất khó hiểu.

⚠️ Trên Android 8 trở lên, âm thanh **gắn cứng vào kênh thông báo lúc kênh được
tạo lần đầu**. Đổi tệp âm sau khi người dùng đã cài thì máy **vẫn phát âm cũ**
cho tới khi gỡ ứng dụng hoặc đổi mã kênh. Vì vậy: chốt âm xong rồi mới đóng gói,
và lúc thử nghiệm thì gỡ cài đặt hẳn giữa hai lần thử.

Chạy: ``python scripts/tao_am_bao.py``
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

TAN_SO_LAY_MAU = 44_100
DINH_MUC_TIEU = 0.708  # ≈ −3 dBFS
THU_MUC_RA = Path(__file__).resolve().parents[1] / "frontend" / "android" / "app" / "src" / "main" / "res" / "raw"


def _mot_not(tan_so: float, do_dai: float, bat_dau: float, tong_dai: float, do_lon: float) -> np.ndarray:
    """Một nốt kiểu chuông: sóng cơ bản cộng hai bồi âm, biên độ tắt dần theo hàm mũ.

    Bồi âm bậc 2 và 3 nhỏ dần cho ra chất "chuông/thanh gõ" thay vì tiếng sin
    trần trụi nghe như còi báo. Tắt dần theo hàm mũ là cách rung thật của vật thể
    kim loại hay thuỷ tinh.
    """
    tin_hieu = np.zeros(int(tong_dai * TAN_SO_LAY_MAU), dtype=np.float64)
    so_mau = int(do_dai * TAN_SO_LAY_MAU)
    t = np.arange(so_mau) / TAN_SO_LAY_MAU

    song = np.sin(2 * np.pi * tan_so * t)
    song += 0.35 * np.sin(2 * np.pi * tan_so * 2 * t)
    song += 0.12 * np.sin(2 * np.pi * tan_so * 3 * t)

    # Tắt dần theo hàm mũ; hằng số 0,25 giây cho đuôi ngắn, gọn.
    song *= np.exp(-t / 0.25)

    # Vào tiếng trong 5 ms — bỏ qua bước này là nghe thấy tiếng "cụp" ở đầu nốt.
    so_mau_vao = int(0.005 * TAN_SO_LAY_MAU)
    song[:so_mau_vao] *= np.linspace(0.0, 1.0, so_mau_vao)

    vi_tri = int(bat_dau * TAN_SO_LAY_MAU)
    tin_hieu[vi_tri : vi_tri + so_mau] += song * do_lon
    return tin_hieu


def tao_am(ten_tep: str, tan_so_1: float, tan_so_2: float, tong_dai: float = 1.0) -> Path:
    """Dựng một âm báo hai nốt rồi ghi ra tệp WAV."""
    tin_hieu = _mot_not(tan_so_1, 0.55, 0.00, tong_dai, 1.00)
    tin_hieu += _mot_not(tan_so_2, 0.65, 0.18, tong_dai, 0.85)

    # Fade 100 ms cuối để tránh tiếng "tách" khi tín hiệu bị cắt đột ngột.
    so_mau_ra = int(0.100 * TAN_SO_LAY_MAU)
    tin_hieu[-so_mau_ra:] *= np.linspace(1.0, 0.0, so_mau_ra)

    # Chuẩn hoá về đúng đỉnh mục tiêu — KHÔNG nén kịch trần.
    dinh = float(np.max(np.abs(tin_hieu)))
    if dinh > 0:
        tin_hieu = tin_hieu / dinh * DINH_MUC_TIEU

    mau_16bit = (tin_hieu * 32767).astype(np.int16)

    THU_MUC_RA.mkdir(parents=True, exist_ok=True)
    duong_dan = THU_MUC_RA / ten_tep
    with wave.open(str(duong_dan), "wb") as tep:
        tep.setnchannels(1)
        tep.setsampwidth(2)
        tep.setframerate(TAN_SO_LAY_MAU)
        tep.writeframes(mau_16bit.tobytes())
    return duong_dan


def main() -> None:
    # Thành công: hai nốt ĐI LÊN, quãng bốn đúng (A5 → D6) — nghe mở, tích cực.
    thanh_cong = tao_am("greenbin_thanh_cong.wav", 880.00, 1174.66)

    # Thất bại: hai nốt ĐI XUỐNG, thấp hơn hẳn (D5 → A4). Cố tình KHÔNG dùng
    # tiếng "buzz" gắt: người dùng đang đứng cạnh thùng rác nơi công cộng.
    that_bai = tao_am("greenbin_that_bai.wav", 587.33, 440.00)

    for duong_dan in (thanh_cong, that_bai):
        with wave.open(str(duong_dan), "rb") as tep:
            giay = tep.getnframes() / tep.getframerate()
        print(f"{duong_dan.name:28s} {giay:.2f}s  {duong_dan.stat().st_size:,} byte")


if __name__ == "__main__":
    main()
