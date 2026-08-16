---
title: GreenBin AI — CLIP T0.5
sdk: docker
app_file: app.py
pinned: false
---

# GreenBin AI — tầng T0.5 chạy từ xa

Dịch vụ CLIP zero-shot của tầng T0.5, tách ra một Hugging Face Space CPU miễn
phí để backend máy chủ 512 MB không phải gánh model. Backend gọi sang bằng
`CLIP_RUNTIME=remote` + `CLIP_REMOTE_URL`.

## Space này làm gì — và KHÔNG làm gì

- **CHỈ suy luận:** nhận ảnh, trả nhãn và điểm khớp.
- **KHÔNG lưu ảnh.** Không lưu file, không ghi log nội dung ảnh, không giữ gì
  sau mỗi request. Ảnh cư dân là dữ liệu nhạy cảm; chúng đã được backend xử lý
  trước khi gửi sang (xem dưới), và bản thân Space không được giữ lại thứ gì.
- **KHÔNG lưu trạng thái.** Mỗi request độc lập, không session.

## Ảnh gửi sang là ảnh đã được làm sạch

Trước khi tới tầng T0.5 (và từ đó gửi sang Space này), backend đã chạy
`src/services/image.preprocess_image` trên ảnh thô:

1. tước toàn bộ EXIF — kể cả toạ độ GPS;
2. làm mờ khuôn mặt (Haar cascade);
3. nén cạnh dài về 512px.

Nghĩa là Space này **không bao giờ nhìn thấy ảnh gốc**, chỉ thấy pixel đã rửa.
Lớp xử lý đó chạy bắt buộc trước mọi ảnh đi vào pipeline phân loại
(`src/api/routers/classify.py`).

## Bộ file ONNX lấy ở đâu

Space cần hai file do `scripts/export_clip_onnx.py` xuất ra:

- `clip_vision_int8.onnx`
- `clip_text_embeddings.json`

(≈ 89 MB, gói thành `.tar.gz` **đính trong GitHub Release**, KHÔNG commit vào
repo). Đặt biến môi trường `CLIP_ASSETS_URL` trỏ vào link tải file
(`…/releases/download/<tag>/…tar.gz`) — Space tự tải và giải nén lúc khởi động.
Dãy số câu mô tả tính sẵn một lần, giống hệt bản chạy tại chỗ; hai phía khớp
nhau bằng mã băm `prompt_hash` (câu mô tả đổi mà không xuất lại là hai bên tự
ngắt, không chấm sai trong im lặng).

## Giới hạn — nói thẳng

- CPU free tier của HF Spaces **ngủ khi rảnh**: request đầu sau khi ngủ có thể
  chậm vài giây cho tới khi instance thức dậy.
- Backend đặt `CLIP_REMOTE_TIMEOUT_SECONDS` (mặc định 8 giây): Space ngủ hoặc
  chậm quá thì backend **rơi êm lên T1** như tầng T0.5 đang tắt — người dùng
  không bị chặn, chỉ mất tầng tiết kiệm chi phí.
- Miễn phí nghĩa là không cam kết uptime. Muốn chắc thì tự mình chạy, hoặc thuê
  một máy nhỏ.

## Cách chạy tại chỗ (không cần deploy)

```bash
pip install -r hf_space/requirements.txt

# Không có file model 89 MB trên máy? Chế độ giả lập cho test/đo:
$env:SPACE_FAKE_MODEL = "1"
python hf_space/app.py          # nghe cổng 7860 (đổi bằng PORT)

curl http://localhost:7860/health
curl -F "file=@anh.jpg" http://localhost:7860/phan-loai
```

## Deploy

Space này là một dịch vụ HTTP Python tuỳ biến nên cần `sdk: docker` và một
`Dockerfile` (ví dụ `FROM python:3.11-slim` + cài `hf_space/requirements.txt` +
`CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]`). Việc tạo
Space, đăng nhập Hugging Face và đẩy file là bước deploy của chủ gói, không nằm
trong gói H1 này.
