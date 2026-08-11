"""Hugging Face Space — dịch vụ CLIP zero-shot cho tầng T0.5 của GreenBin AI.

Space này **CHỈ suy luận**: nhận ảnh đã xử lý, trả điểm khớp với các câu mô tả
nhóm rác. KHÔNG lưu ảnh và KHÔNG lưu bất kỳ dữ liệu nào sau mỗi request.

Chạy trên CPU free tier của HF Spaces. Bộ file ONNX (~89 MB) tải từ
``CLIP_ASSETS_URL`` (đính trong GitHub Release, không commit vào repo) một lần
lúc khởi động, không nạp lại mỗi request.

Toàn bộ logic tiền xử lý ảnh và chấm điểm được **sao chép y nguyên** từ
``src/services/vision/local_clip.py`` (hàm ``tien_xu_ly_anh`` và phần lõi của
``_diem_onnx``) để hai bên không bao giờ lệch nhau về mặt toán — chỉ khác chỗ
bản ở máy chủ gọi trực tiếp, bản này nghe HTTP.
"""

from __future__ import annotations

import io
import json
import logging
import os
import tarfile
import tempfile
from pathlib import Path

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image

logger = logging.getLogger(__name__)

ONNX_MODEL_FILE = "clip_vision_int8.onnx"
TEXT_EMBEDDING_FILE = "clip_text_embeddings.json"

# Chế độ giả lập dành cho test/đo tại chỗ: không cần file model 89 MB. Bật bằng
# `SPACE_FAKE_MODEL=1` rồi gọi /health và /phan-loai vẫn trả JSON thật.
_FAKE_MODE = os.environ.get("SPACE_FAKE_MODEL", "").lower() in {"1", "true", "yes"}

THU_MUC_ASSET = Path(os.environ.get("CLIP_ASSETS_DIR", "./clip_assets"))

_session: ort.InferenceSession | None = None
_meta: dict | None = None


# --- Tiền xử lý ảnh --------------------------------------------------------
# Chép y nguyên từ src/services/vision/local_clip.py — đừng "tối ưu" ở đây.


def tien_xu_ly_anh(image: Image.Image, size: int, mean: list[float], std: list[float]):
    """Đưa ảnh về đúng khuôn CLIP nhận, **không dùng torch/transformers**."""
    rong, cao = image.size
    ti_le = size / min(rong, cao)
    image = image.resize((round(rong * ti_le), round(cao * ti_le)), Image.BICUBIC)

    rong, cao = image.size
    trai = (rong - size) // 2
    tren = (cao - size) // 2
    image = image.crop((trai, tren, trai + size, tren + size))

    arr = np.asarray(image, dtype=np.float32) / 255.0
    arr = (arr - np.asarray(mean, dtype=np.float32)) / np.asarray(std, dtype=np.float32)
    return arr.transpose(2, 0, 1)[None].astype(np.float32)


# --- Tải bộ file ONNX một lần ----------------------------------------------


def _tai_asset_neu_thieu() -> None:
    """Tải .tar.gz từ CLIP_ASSETS_URL nếu chưa có file, giải nén đúng hai file."""
    url = os.environ.get("CLIP_ASSETS_URL", "")
    if not url or (THU_MUC_ASSET / ONNX_MODEL_FILE).exists():
        return
    THU_MUC_ASSET.mkdir(parents=True, exist_ok=True)
    logger.info("Tải bộ model T0.5 từ %s …", url)

    import httpx

    try:
        with httpx.Client(timeout=300.0, follow_redirects=True) as client:
            phan_hoi = client.get(url)
            phan_hoi.raise_for_status()
        if not phan_hoi.content.startswith(b"\x1f\x8b"):
            logger.warning("CLIP_ASSETS_URL không trả về file .tar.gz (có vẻ là trang web).")
            return
        with tempfile.TemporaryDirectory() as tam:
            goi = Path(tam) / "clip_assets.tar.gz"
            goi.write_bytes(phan_hoi.content)
            with tarfile.open(goi) as tf:
                for ten in (ONNX_MODEL_FILE, TEXT_EMBEDDING_FILE):
                    thanh_vien = next((m for m in tf.getmembers() if Path(m.name).name == ten), None)
                    if thanh_vien is None or not thanh_vien.isfile():
                        continue
                    nguon = tf.extractfile(thanh_vien)
                    if nguon is not None:
                        (THU_MUC_ASSET / ten).write_bytes(nguon.read())
    except (httpx.HTTPError, OSError, tarfile.TarError) as exc:
        logger.warning("Không tải được bộ model T0.5: %s.", exc)


def _tai_assets() -> bool:
    """Nạp phiên ONNX + dãy số câu mô tả. ``True`` khi sẵn sàng phục vụ."""
    global _session, _meta
    if _session is not None and _meta is not None:
        return True
    if _FAKE_MODE:
        _meta = {
            "prompt_hash": "fake-hash",
            "logit_scale": 1.0,
            "owner_codes": ["fake_a", "fake_b"],
            "text_embeddings": np.eye(2, dtype=np.float32),
            "image_preprocess": {"size": 224, "mean": [0.0, 0.0, 0.0], "std": [1.0, 1.0, 1.0]},
        }
        _session = object()  # type: ignore[assignment]
        return True

    _tai_asset_neu_thieu()
    model_path = THU_MUC_ASSET / ONNX_MODEL_FILE
    meta_path = THU_MUC_ASSET / TEXT_EMBEDDING_FILE
    if not model_path.exists() or not meta_path.exists():
        logger.warning("Chưa có bộ file ONNX — /phan-loai sẽ trả 503.")
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["text_embeddings"] = np.asarray(meta["text_embeddings"], dtype=np.float32)
        _meta = meta
        _session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        logger.info("Đã nạp CLIP int8 cho Space: %s", model_path)
        return True
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Bộ file ONNX hỏng: %s.", exc)
        return False


# --- Chấm điểm -------------------------------------------------------------


def _diem_anh(image: Image.Image) -> dict:
    """Chấm một ảnh, trả đúng khuôn backend `_diem_remote` chờ."""
    if _FAKE_MODE:
        return {
            "nhan": "fake_a",
            "diem": 0.91,
            "moi_nhan": {"fake_a": 0.91, "fake_b": 0.09},
            "prompt_hash": "fake-hash",
        }

    assert _meta is not None and _session is not None
    cau_hinh = _meta["image_preprocess"]
    pixel_values = tien_xu_ly_anh(image, cau_hinh["size"], cau_hinh["mean"], cau_hinh["std"])
    image_emb = _session.run(None, {"pixel_values": pixel_values})[0][0]

    logits = float(_meta["logit_scale"]) * _meta["text_embeddings"] @ image_emb
    exp = np.exp(logits - logits.max())
    probs = exp / exp.sum()

    moi_nhan: dict[str, float] = {}
    for prob, code in zip(probs.tolist(), _meta["owner_codes"], strict=True):
        moi_nhan[code] = max(moi_nhan.get(code, 0.0), float(prob))

    nhan = max(moi_nhan, key=moi_nhan.get)
    return {"nhan": nhan, "diem": moi_nhan[nhan], "moi_nhan": moi_nhan, "prompt_hash": _meta["prompt_hash"]}


# --- HTTP ------------------------------------------------------------------


app = FastAPI(title="GreenBin AI — CLIP T0.5 (chỉ suy luận)", docs_url=None, redoc_url=None)


@app.on_event("startup")
def _khoi_dong() -> None:
    _tai_assets()


@app.get("/health")
def health() -> dict:
    """Đường đánh thức — Space CPU free ngủ khi rảnh, backend gọi cái này trước."""
    return {"ok": True}


@app.post("/phan-loai")
async def phan_loai(file: UploadFile = File(...)) -> dict:
    """Nhận ảnh đã xử lý, trả nhãn + điểm. KHÔNG lưu ảnh."""
    if _session is None or _meta is None:
        raise HTTPException(status_code=503, detail="Model chưa sẵn sàng — thử lại sau.")
    try:
        image = Image.open(io.BytesIO(await file.read())).convert("RGB")
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="Không đọc được ảnh.")
    return _diem_anh(image)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7860")))
