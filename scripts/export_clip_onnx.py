"""Xuất tầng T0.5 (CLIP) sang ONNX int8 để chạy được trên máy chủ 512 MB.

Chạy **một lần** trên máy có ``torch`` — máy dev hoặc Google Colab bản miễn phí —
rồi cất hai file sinh ra vào GitHub Release. Sau đó máy chủ không cần ``torch``
nữa: chỉ ``onnxruntime`` đọc file ``.onnx``.

Vì sao làm được: CLIP có **hai nửa tách rời** — nửa ảnh và nửa chữ. Phân loại
zero-shot chỉ là so dãy số của ảnh với dãy số của từng câu mô tả. Mà các câu mô
tả (``clip_prompts`` trong danh mục rác) **không đổi giữa các lần chụp**, nên
tính sẵn một lần rồi cất là đủ — đúng cách ``rag.embed_chunks`` đang làm với kho
quy định. Bỏ được nửa chữ thì lúc phục vụ chỉ còn nửa ảnh:

| | Trước | Sau |
|---|---|---|
| Phụ thuộc | torch 1,19 GB | onnxruntime |
| Trọng số phải nạp | cả hai nửa, fp32 | chỉ nửa ảnh, int8 |

Cách chạy::

    pip install -r requirements-local-model.txt
    python scripts/export_clip_onnx.py --anh data/media/<một-ảnh>.jpg

``--anh`` là tuỳ chọn nhưng **nên có**: nó bật phần đối chiếu bản int8 với bản
gốc trên ảnh thật, in ra độ lệch đo được thay vì để bạn tin vào lời hứa.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db.seed_data import WASTE_CATEGORIES  # noqa: E402
from src.services.vision.local_clip import (  # noqa: E402
    ONNX_MODEL_FILE,
    TEXT_EMBEDDING_FILE,
    tien_xu_ly_anh,
)

# Kích thước ảnh vào của CLIP ViT-B/32. Lưu vào file kèm theo chứ không để
# runtime đoán — sai một bước tiền xử lý là lệch toàn bộ điểm số mà không có
# lỗi nào được ném ra.
_IMAGE_SIZE = 224
_CLIP_MEAN = [0.48145466, 0.4578275, 0.40821073]
_CLIP_STD = [0.26862954, 0.26130258, 0.27577711]


def _danh_sach_prompt() -> tuple[list[str], list[str]]:
    """``(prompts, mã nhóm của từng prompt)`` — đúng thứ tự runtime dựng.

    Phải khớp với :func:`src.services.vision.local_clip._prompts_for` và thứ tự
    ``sort_order`` mà ``load_category_options`` dùng, nếu không thì mã băm ở
    runtime sẽ không khớp và tầng T0.5 tự tắt.
    """
    prompts: list[str] = []
    owner: list[str] = []
    for row in sorted(WASTE_CATEGORIES, key=lambda r: r["sort_order"]):
        hint = str(row.get("clip_prompts") or "")
        cau = [p.strip() for p in hint.split("|") if p.strip()] or [f"a photo of {row['name']}"]
        prompts.extend(cau)
        owner.extend([row["code"]] * len(cau))
    return prompts, owner


def _bam_prompt(prompts: list[str]) -> str:
    return hashlib.sha256("\n".join(prompts).encode("utf-8")).hexdigest()


def _mb(path: Path) -> float:
    return path.stat().st_size / 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description="Xuất CLIP T0.5 sang ONNX int8")
    parser.add_argument("--ra", default="assets/clip", help="Thư mục chứa file sinh ra")
    parser.add_argument("--model", default="", help="Tên model CLIP (mặc định lấy từ .env)")
    parser.add_argument("--anh", default="", help="Ảnh thật để đối chiếu bản int8 với bản gốc")
    parser.add_argument("--giu-ban-fp32", action="store_true", help="Giữ lại file .onnx fp32 trung gian")
    args = parser.parse_args()

    try:
        import numpy as np
        import onnxruntime as ort
        import torch
        from onnxruntime.quantization import QuantType, quantize_dynamic
        from PIL import Image
        from transformers import CLIPModel, CLIPProcessor
    except ImportError as exc:
        print(f"Thiếu thư viện: {exc}\nCài bằng: pip install -r requirements-local-model.txt")
        return 1

    from src.config import get_settings

    ten_model = args.model or get_settings().clip_model_name
    thu_muc = Path(args.ra)
    thu_muc.mkdir(parents=True, exist_ok=True)

    print(f"Nạp {ten_model} …")
    model = CLIPModel.from_pretrained(ten_model)
    processor = CLIPProcessor.from_pretrained(ten_model)
    model.eval()

    # --- 1. Tính sẵn dãy số của các câu mô tả ----------------------------
    prompts, owner = _danh_sach_prompt()
    print(f"Mã hoá {len(prompts)} câu mô tả của {len(set(owner))} nhóm rác …")
    with torch.no_grad():
        dau_vao = processor(text=prompts, return_tensors="pt", padding=True, truncation=True)
        text_emb = model.get_text_features(**dau_vao)
        text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)
        # `logit_scale` là hằng số nhân trước softmax. Quên lưu nó thì code vẫn
        # chạy, không lỗi, chỉ có mọi confidence lệch thang — và ngưỡng 0,82
        # mất ý nghĩa trong im lặng.
        logit_scale = float(model.logit_scale.exp())

    meta = {
        "model_name": ten_model,
        "prompt_hash": _bam_prompt(prompts),
        "logit_scale": logit_scale,
        "prompts": prompts,
        "owner_codes": owner,
        "text_embeddings": text_emb.tolist(),
        "image_preprocess": {
            "size": _IMAGE_SIZE,
            "mean": _CLIP_MEAN,
            "std": _CLIP_STD,
        },
    }
    duong_dan_text = thu_muc / TEXT_EMBEDDING_FILE
    duong_dan_text.write_text(json.dumps(meta), encoding="utf-8")
    print(f"  → {duong_dan_text} ({_mb(duong_dan_text):.2f} MB)")

    # --- 2. Xuất nửa ảnh sang ONNX ---------------------------------------
    class NuaAnh(torch.nn.Module):
        """Chỉ nhánh ảnh, đã chuẩn hoá độ dài — runtime khỏi phải làm lại."""

        def __init__(self, clip: CLIPModel) -> None:
            super().__init__()
            self.clip = clip

        def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
            emb = self.clip.get_image_features(pixel_values=pixel_values)
            return emb / emb.norm(dim=-1, keepdim=True)

    fp32 = thu_muc / "clip_vision_fp32.onnx"
    mau = torch.randn(1, 3, _IMAGE_SIZE, _IMAGE_SIZE)
    print("Xuất nửa ảnh sang ONNX …")
    torch.onnx.export(
        NuaAnh(model),
        mau,
        str(fp32),
        input_names=["pixel_values"],
        output_names=["image_embeds"],
        dynamic_axes={"pixel_values": {0: "batch"}, "image_embeds": {0: "batch"}},
        opset_version=14,
    )
    print(f"  → {fp32} ({_mb(fp32):.1f} MB)")

    # --- 3. Nén xuống int8 ------------------------------------------------
    int8 = thu_muc / ONNX_MODEL_FILE
    print("Nén xuống int8 …")
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    print(f"  → {int8} ({_mb(int8):.1f} MB)")

    # --- 4. Đối chiếu: bản nén lệch bao nhiêu so với bản gốc? ------------
    phien = ort.InferenceSession(str(int8), providers=["CPUExecutionProvider"])

    if args.anh:
        anh = Image.open(args.anh).convert("RGB")
        # Đường của runtime: PIL → tiền xử lý tự viết → onnx int8.
        vao_onnx = tien_xu_ly_anh(anh, _IMAGE_SIZE, _CLIP_MEAN, _CLIP_STD)
        emb_onnx = phien.run(None, {"pixel_values": vao_onnx})[0][0]
        # Đường gốc: CLIPProcessor → torch fp32.
        with torch.no_grad():
            vao_torch = processor(images=anh, return_tensors="pt")
            emb_torch = model.get_image_features(**vao_torch)
            emb_torch = (emb_torch / emb_torch.norm(dim=-1, keepdim=True))[0].numpy()

        cosine = float(np.dot(emb_onnx, emb_torch))
        t = np.asarray(meta["text_embeddings"], dtype=np.float32)
        diem_onnx = _diem_nhom(np.array(emb_onnx), t, owner, logit_scale)
        diem_torch = _diem_nhom(emb_torch, t, owner, logit_scale)
        top_onnx = max(diem_onnx, key=lambda c: diem_onnx[c])
        top_torch = max(diem_torch, key=lambda c: diem_torch[c])

        print("\n--- Đối chiếu trên ảnh thật ---")
        print(f"  Độ tương đồng cosine giữa hai dãy số: {cosine:.4f}  (1,0 là trùng khít)")
        print(f"  Bản gốc  : {top_torch} · {diem_torch[top_torch]:.4f}")
        print(f"  Bản int8 : {top_onnx} · {diem_onnx[top_onnx]:.4f}")
        if top_onnx != top_torch:
            print("  ⚠ HAI BẢN CHỌN KHÁC NHÓM — không dùng bản nén này, xem lại bước xuất.")
        lech = abs(diem_onnx[top_onnx] - diem_torch[top_torch])
        print(f"  Lệch confidence: {lech:.4f}")
        print(
            "  → Ngưỡng CLIP_ACCEPT_CONFIDENCE phải chuẩn lại trên bộ ảnh thật, "
            "đừng bê nguyên 0,82 sang."
        )
    else:
        print("\n(Bỏ qua phần đối chiếu — chạy lại với --anh <đường dẫn> để có số đo thật.)")

    if not args.giu_ban_fp32:
        fp32.unlink(missing_ok=True)

    print(f"\nXong. Đẩy thư mục '{thu_muc}' lên GitHub Release rồi đặt CLIP_ASSETS_URL trên Render.")
    return 0


def _diem_nhom(image_emb, text_emb, owner: list[str], logit_scale: float) -> dict[str, float]:
    """Lặp lại đúng phép tính của runtime để hai bên so được với nhau."""
    import numpy as np

    logits = logit_scale * text_emb @ image_emb
    exp = np.exp(logits - logits.max())
    probs = exp / exp.sum()
    ket_qua: dict[str, float] = {}
    for prob, code in zip(probs.tolist(), owner, strict=True):
        ket_qua[code] = max(ket_qua.get(code, 0.0), float(prob))
    return ket_qua


if __name__ == "__main__":
    raise SystemExit(main())
