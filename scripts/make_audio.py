import asyncio
import sys
from pathlib import Path

import edge_tts

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

VOICE = "vi-VN-NamMinhNeural"
AUDIO_DIR = Path("D:/P-075/video_output/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

VO_SCRIPTS = [
    (1, "Phân loại rác không thất bại vì chúng ta thiếu thùng rác."),
    (2, "Nó thất bại khi người dùng phải tự đoán, đội vận hành thiếu dữ liệu, và việc thu gom vẫn diễn ra theo những quy trình rời rạc."),
    (3, "GreenBin AI biến một lần bỏ rác thành một luồng dữ liệu và hành động xuyên suốt."),
    (4, "Một hệ sinh thái kết nối thiết bị IoT tại nguồn, AI thị giác ở backend và trung tâm vận hành."),
    (5, "Khi một vật thể được đưa vào, thiết bị không vội chụp. Chuyển động được phát hiện trước, cảm biến khoảng cách xác nhận có vật thể thật, rồi camera mới được kích hoạt."),
    (6, "Ảnh được gửi tới backend, nơi toàn bộ trí tuệ AI được đặt tập trung — thay vì nhét mô hình và API key vào từng chiếc thùng."),
    (7, "Trước khi AI bên ngoài nhìn thấy ảnh, GreenBin loại bỏ metadata, làm mờ khuôn mặt, resize và tạo dấu vân tay ảnh."),
    (8, "Sau đó Vision AI phân loại vật thể thành nhựa, giấy, kim loại hoặc nhóm khác, và kết quả được chuyển thành hành động phân luồng."),
    (9, "Ba cơ cấu servo tạo thành hệ thống chia hai tầng để đưa vật thể tới đúng một trong bốn ngăn."),
    (10, "Ngay sau giao dịch, mức đầy được đo lại. Hệ thống chỉ phát cảnh báo khi trạng thái thực sự thay đổi, thay vì spam dữ liệu liên tục."),
    (11, "Ở phía Ban Quản lý, GreenBin Ops biến dữ liệu IoT thành bản đồ vận hành thời gian thực."),
    (12, "Các điểm cần thu gom được đưa vào thuật toán tối ưu tuyến, giúp đội vận hành tập trung vào nơi thực sự cần đi."),
    (13, "Và AI không được phép giả vờ chắc chắn. Nhãn có độ tin cậy thấp hoặc nghi ngờ nguy hại được chuyển cho con người kiểm tra."),
    (14, "Ba điểm Human-in-the-Loop giữ các quyết định nhạy cảm — từ nhãn nguy hại đến phê duyệt tuyến — trong tay con người."),
    (15, "Vertical slice hiện được bảo vệ bởi 68 backend tests, 61 test logic firmware và 27 kiểm tra end-to-end."),
    (16, "GreenBin AI không dừng lại ở việc nhận diện một món rác. Mỗi kết quả AI phải trở thành một hành động hoặc một bản ghi vận hành."),
    (17, "GreenBin AI. Phân loại tại nguồn. Vận hành bằng dữ liệu.")
]

async def gen_single(sid, text):
    out_file = AUDIO_DIR / f"scene_{sid:02d}.mp3"
    print(f"Generating VO {sid:02d}...", flush=True)
    for attempt in range(3):
        try:
            comm = edge_tts.Communicate(text, VOICE, rate="+3%")
            await asyncio.wait_for(comm.save(str(out_file)), timeout=15.0)
            if out_file.exists() and out_file.stat().st_size > 1000:
                print(f"  [OK] Saved VO {sid:02d} ({out_file.stat().st_size} bytes)", flush=True)
                return
        except Exception as e:
            print(f"  [Retry {attempt+1}] VO {sid:02d}: {e}", flush=True)
            await asyncio.sleep(1.0)

async def main():
    for sid, text in VO_SCRIPTS:
        await gen_single(sid, text)
        await asyncio.sleep(0.3)
    print("ALL VO GENERATION COMPLETE!", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
