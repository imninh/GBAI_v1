"""So sánh nhiều cấu hình model T1 trên cùng một bộ ảnh — chọn model bằng số đo.

Gói P34 — **chỉ đo, không sửa sản phẩm**. Script này là trình bao bọc quanh hạ
tầng đã có: ``eval/run_eval.py`` (quét ảnh, tính chỉ số, lưu kết quả) và đúng
đường sản phẩm ``classify_waste`` + ``preprocess_image``. Model đổi bằng biến
môi trường ``VISION_PROVIDER_T1`` / ``VISION_MODEL_T1`` rồi
``reset_settings_cache()`` chứ không sửa một dòng code.

⚠️ **BẪY ĐÃ DÍNH MỘT LẦN** (đo 08/08/2026 trên Groq): model có nhãn ``reasoning``
tiêu hết trần đầu ra vào khối ``<think>`` rồi mới tới JSON → ``VISION-500`` mọi
ảnh. Với những model như vậy phải khai ``max_output_tokens`` trong cấu hình
(→ env ``VISION_MAX_OUTPUT_TOKENS``) ít nhất 4000.

⚠️ **Cache T0 LUÔN TẮT khi đo** (``dung_cache=False`` ở mọi lần gọi): eval đo năng
lực của model, không đo năng lực bộ nhớ pHash. Bật cache, các cấu hình chạy trên
cùng những tấm ảnh sẽ ăn kết quả lẫn nhau và in ra y hệt nhau.

Một cấu hình hỏng (hết quota, model 404, JSON vỡ) **không được giết cả lượt đo**:
bắt lỗi, ghi ``LỖI`` vào bảng, chạy tiếp cấu hình sau.

Chạy::

    python eval/so_sanh_model.py --liet-ke              # chỉ đếm ảnh + liệt kê cấu hình
    python eval/so_sanh_model.py                        # in dự toán rồi dừng
    python eval/so_sanh_model.py --dong-y --limit 5     # chạy thật
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from eval.metrics import BO_CONG_KHAI, BO_TU_CHUP, KetQuaAnh, TongHop, tong_hop  # noqa: E402
from eval.run_eval import (  # noqa: E402
    THU_MUC_ANH,
    THU_MUC_KET_QUA,
    _in_du_toan,
    _luu_ket_qua,
    _quet_anh,
)
from src.config import get_settings, reset_settings_cache  # noqa: E402
from src.db.models import WasteCategory  # noqa: E402
from src.db.session import session_scope  # noqa: E402
from src.services.classifier import classify_waste  # noqa: E402
from src.services.image import preprocess_image  # noqa: E402
from src.services.safety import RefusalReason  # noqa: E402

BO_HOP_LE = (BO_CONG_KHAI, BO_TU_CHUP)

#: Trần token đầu vào theo PHÚT của Groq free tier — cột ảnh/phút của bảng đo độ
#: phân giải dựa vào con số này. Ghi lại ở đây để hai script dùng chung một nguồn.
TRAN_TOKEN_GROQ_MOI_PHUT = 8000

#: Danh sách cấu hình cần đo. Hai dòng đầu là trạng thái hiện tại (mỗi model là
#: mô hình đang chạy ở T1/T2). Muốn thử model khác thì thêm dòng ở đây — tên model
#: PHẢI tra từ trang model của chính nhà cung cấp tại thời điểm chạy: danh sách
#: model đổi liên tục, và một tên sai chỉ lộ ra thành lỗi 404 sau khi đã tiêu
#: quota cho các cấu hình trước. KHÔNG được đoán tên.
CAC_CAU_HINH: list[dict[str, object]] = [
    {"ten": "hien-tai-t1", "provider": "nvidia", "model": "meta/llama-3.2-90b-vision-instruct"},
    {"ten": "groq-qwen", "provider": "groq", "model": "qwen/qwen3.6-27b", "max_output_tokens": 4000},
    # --- Cập nhật 13/08/2026: tên lấy từ /v1/models SỐNG của tài khoản (docs trễ hơn
    #     thực tế). ĐÃ BỎ: llama-4-maverick (Groq khai tử 09/03/2026 → 404),
    #     pixtral-12b & pixtral-large (Mistral gỡ hẳn, không còn trong list model sống).
    #     Ministral 3b/8b + Medium 3.5 là dòng vision hiện hành — dùng --limit 1 xác
    #     nhận chúng nhận ảnh (không "từ chối hết" như pixtral-12b). ---
    {"ten": "groq-llama4-scout", "provider": "groq", "model": "meta-llama/llama-4-scout-17b-16e-instruct"},
    {"ten": "mistral-medium-3.5", "provider": "mistral", "model": "mistral-medium-latest"},
    {"ten": "ministral-8b", "provider": "mistral", "model": "ministral-8b-latest"},
    {"ten": "ministral-3b", "provider": "mistral", "model": "ministral-3b-latest"},
]


def _tong_token(outcome) -> tuple[int, int]:
    """Gộp (token_vào, token_ra) qua các node của một lần phân loại.

    ``ClassifyOutcome`` KHÔNG có ``tokens_in``/``tokens_out`` ở cấp outcome — token nằm
    trên từng ``NodeMetric`` trong ``outcome.nodes`` (T1, T2, advise…). Trước đây
    ``chay_mot_anh`` đọc thẳng ``outcome.tokens_in`` → ``AttributeError`` mọi lần chạy
    ``--dong-y`` model thật (bug có sẵn từ P34, chỉ lộ khi chạy thật).
    """
    token_vao = sum(node.tokens_in for node in outcome.nodes)
    token_ra = sum(node.tokens_out for node in outcome.nodes)
    return token_vao, token_ra


def chay_mot_anh(
    session,
    duong_dan: Path,
    nhan_dung: str,
    bo: str,
    media_dir: str,
    dung_cache: bool,
    *,
    ham_nen=preprocess_image,
) -> tuple[KetQuaAnh, int, int]:
    """Chạy đúng đường sản phẩm cho một ảnh, trả về ``(kết quả, token vào, token ra)``.

    Bản gần giống ``run_eval._chay_mot_anh`` — cùng gọi ``preprocess_image`` rồi
    ``classify_waste``, chỉ thêm hai số token mà bản gốc không lưu (cần cho bảng
    đo độ phân giải). ``ham_nen`` mặc định là ``preprocess_image`` của sản phẩm;
    ``do_do_phan_giai.py`` truyền vào chính nó để khẳng định cả hai script nén
    ảnh bằng ĐÚNG cùng một hàm.
    """
    kq = KetQuaAnh(duong_dan=str(duong_dan.relative_to(ROOT)), bo=bo, nhan_dung=nhan_dung)
    bat_dau = time.perf_counter()
    try:
        processed = ham_nen(duong_dan.read_bytes(), media_dir=media_dir, keep_original=False)
        image_bytes = Path(processed.stored_path).read_bytes()
        outcome = classify_waste(
            session,
            image_bytes=image_bytes,
            image_phash=processed.phash if dung_cache else "",
        )
    except (OSError, ValueError) as exc:
        kq.loi = f"{type(exc).__name__}: {exc}"
        kq.latency_ms = int((time.perf_counter() - bat_dau) * 1000)
        return kq, 0, 0

    kq.nhan_du_doan = outcome.category_code
    kq.tu_choi = outcome.refused
    kq.ly_do_tu_choi = outcome.refusal_reason
    if outcome.refusal_reason == RefusalReason.MODEL_LOI:
        kq.loi = f"model_loi: {outcome.refusal_headline_vi}"
    kq.tier = outcome.tier
    kq.model = outcome.model
    kq.latency_ms = outcome.latency_ms
    kq.cost_usd = outcome.cost_usd
    kq.price_known = outcome.price_known
    token_vao, token_ra = _tong_token(outcome)
    return kq, token_vao, token_ra


def _ap_dung_cau_hinh(cau_hinh: dict) -> None:
    """Đưa một cấu hình model vào settings bằng biến môi trường, không sửa code."""
    os.environ["VISION_PROVIDER_T1"] = str(cau_hinh["provider"])
    os.environ["VISION_MODEL_T1"] = str(cau_hinh["model"])
    os.environ.pop("VISION_MAX_OUTPUT_TOKENS", None)
    if cau_hinh.get("max_output_tokens"):
        os.environ["VISION_MAX_OUTPUT_TOKENS"] = str(cau_hinh["max_output_tokens"])
    reset_settings_cache()


def chay_mot_cau_hinh(
    session,
    cau_hinh: dict,
    cac_bo: list[str],
    nhan_list: list[str],
    ma_nguy_hai: set[str],
    *,
    limit: int,
    nghi_giay: float,
    luu_file: bool = False,
) -> dict:
    """Chạy một cấu hình model qua cùng bộ ảnh, trả về một dòng của bảng so sánh.

    Raises:
        Exception: khi cả lượt cấu hình này hỏng — người gọi (``chay_luot_do``)
            bắt lỗi và ghi ``LỖI`` vào bảng rồi chạy tiếp cấu hình sau.
    """
    _ap_dung_cau_hinh(cau_hinh)

    anh_theo_bo: dict[str, list[tuple[Path, str]]] = {}
    for bo in cac_bo:
        anh, canh_bao = _quet_anh(bo, set(nhan_list), limit)
        anh_theo_bo[bo] = anh
        for dong in canh_bao:
            print(f"⚠ {dong}")

    ket_qua: list[KetQuaAnh] = []
    token_vao, token_ra = 0, 0
    with tempfile.TemporaryDirectory(prefix="greenbin-eval-") as media_dir:
        for bo in cac_bo:
            for i, (duong_dan, nhan) in enumerate(anh_theo_bo[bo], start=1):
                # Cache T0 LUÔN TẮT khi đo — xem docstring đầu file.
                kq, tv, tr = chay_mot_anh(session, duong_dan, nhan, bo, media_dir, dung_cache=False)
                ket_qua.append(kq)
                token_vao += tv
                token_ra += tr
                dau = "✗" if kq.loi else ("·" if kq.tu_choi else ("✓" if kq.dung else "✗"))
                print(f"  [{bo} {i}/{len(anh_theo_bo[bo])}] {dau} {duong_dan.name}")
                if nghi_giay > 0:
                    time.sleep(nghi_giay)

    tong: dict[str, TongHop] = {}
    for bo in cac_bo:
        cua_bo = [kq for kq in ket_qua if kq.bo == bo]
        if cua_bo:
            tong[bo] = tong_hop(cua_bo, nhan_list, ma_nguy_hai, bo=bo)
    tong_tat_ca = tong_hop(ket_qua, nhan_list, ma_nguy_hai, bo="tất cả") if ket_qua else None

    file_ket_qua = ""
    if luu_file:
        duong_dan = _luu_ket_qua(ket_qua, tong, nhan_list, _cau_hinh_cho_file(cau_hinh, limit, nghi_giay))
        ten_moi = THU_MUC_KET_QUA / f"{cau_hinh['ten']}-{duong_dan.stem}.json"
        duong_dan.rename(ten_moi)
        file_ket_qua = str(ten_moi.relative_to(ROOT))

    return {
        "ten": str(cau_hinh["ten"]),
        "provider": str(cau_hinh["provider"]),
        "model": str(cau_hinh["model"]),
        "tong": tong_tat_ca,
        "token_vao": token_vao,
        "token_ra": token_ra,
        "so_loi": sum(1 for kq in ket_qua if kq.loi),
        "ty_le_leo_t2": _ty_le_leo_t2(ket_qua),
        "p95_ms": _p95_ms(ket_qua),
        "file": file_ket_qua,
        "loi": "",
    }


def _cau_hinh_cho_file(cau_hinh: dict, limit: int, nghi_giay: float) -> dict:
    """Khối ``cau_hinh`` ghi vào file kết quả — để ``so_sanh_lan_chay.py`` đọc lại."""
    from src.services.vision import get_tier_model, get_tier_provider

    settings = get_settings()
    return {
        "tang": {tang: {"provider": get_tier_provider(tang), "model": get_tier_model(tang)} for tang in ("t1", "t2", "text")},
        "local_model_enabled": settings.local_model_enabled,
        "dung_cache_phash": False,
        "nghi_giay": nghi_giay,
        "limit": limit,
        "ten_cau_hinh": str(cau_hinh["ten"]),
    }


def chay_luot_do(
    session,
    cac_cau_hinh: list[dict],
    cac_bo: list[str],
    nhan_list: list[str],
    ma_nguy_hai: set[str],
    *,
    limit: int,
    nghi_giay: float,
    luu_file: bool = False,
) -> list[dict]:
    """Chạy từng cấu hình; một cấu hình hỏng không giết cả lượt — ghi ``LỖI`` rồi tiếp."""
    cac_dong: list[dict] = []
    for cau_hinh in cac_cau_hinh:
        print(f"\n--- Cấu hình: {cau_hinh.get('ten')} · {cau_hinh.get('provider')}/{cau_hinh.get('model')} ---")
        try:
            cac_dong.append(
                chay_mot_cau_hinh(
                    session,
                    cau_hinh,
                    cac_bo,
                    nhan_list,
                    ma_nguy_hai,
                    limit=limit,
                    nghi_giay=nghi_giay,
                    luu_file=luu_file,
                )
            )
        except Exception as exc:
            # Một cấu hình hỏng (hết quota, model 404, JSON vỡ) không được giết
            # cả lượt đo — ghi LỖI vào bảng rồi chạy tiếp cấu hình sau.
            cac_dong.append(
                {
                    "ten": str(cau_hinh.get("ten", "?")),
                    "provider": str(cau_hinh.get("provider", "?")),
                    "model": str(cau_hinh.get("model", "?")),
                    "tong": None,
                    "token_vao": 0,
                    "token_ra": 0,
                    "so_loi": 0,
                    "ty_le_leo_t2": 0.0,
                    "p95_ms": 0,
                    "file": "",
                    "loi": f"LỖI: {type(exc).__name__}: {exc}",
                }
            )
    return cac_dong


def _pt(x: float) -> str:
    return f"{x * 100:.1f}%"


def _ty_le_leo_t2(cac_ket_qua: list[KetQuaAnh]) -> float:
    """Tỉ lệ ảnh leo T2 — đếm trên ``tier`` CUỐI CÙNG của từng ảnh.

    ``kq.tier`` được ``chay_mot_anh`` ghi là tier sau cùng: ca leo T2 rồi T2
    chốt → ``t2_full``; ca T1 chốt luôn → ``t1_mini``. Đây là cột quyết định
    "model T1 nào ít leo T2" — model tự tin đúng thì nhanh và rẻ. Ảnh lỗi
    (``tier=""``) nằm ở mẫu số nhưng không tính là leo.
    """
    if not cac_ket_qua:
        return 0.0
    so_leo = sum(1 for kq in cac_ket_qua if kq.tier == "t2_full")
    return so_leo / len(cac_ket_qua)


def _p95_ms(cac_ket_qua: list[KetQuaAnh]) -> int:
    """p95 độ trễ (ms) của các ảnh — lộ đuôi treo mà p50 giấu đi.

    Ca T1 treo tới hết timeout rồi mới leo T2 sẽ có latency_ms rất lớn; p95 ≈ 60000
    (hoặc ≈ ``vision_timeout_seconds`` sau P43a) tố cáo cấu hình hay timeout. Ảnh lỗi
    vẫn có ``latency_ms`` (được ghi trước khi return) nên vẫn vào mẫu.
    """
    do_tre = sorted(kq.latency_ms for kq in cac_ket_qua)
    if not do_tre:
        return 0
    # Chỉ số p95 theo kiểu "nearest-rank": phần tử ở vị trí ceil(0.95*n) - 1.
    import math

    vi_tri = math.ceil(0.95 * len(do_tre)) - 1
    return do_tre[vi_tri]


def in_bang(cac_dong: list[dict]) -> None:
    """Bảng so sánh: cấu hình · provider/model · acc · F1 · p50 · % leo T2 · token · $ · lỗi."""
    print("\n" + "=" * 130)
    print("SO SÁNH CẤU HÌNH MODEL")
    print("=" * 130)
    print(
        f"{'cấu hình':<16} {'provider/model':<44} {'acc':>7} {'F1':>6} {'p50 ms':>8} "
        f"{'p95 ms':>8} {'% leo T2':>9} {'token vào/ra':>22} {'$ ước tính':>12} {'lỗi':>5}"
    )
    print("-" * 130)
    for dong in cac_dong:
        ten = dong["ten"]
        mo_ta = f"{dong['provider']}/{dong['model']}"
        if dong.get("loi"):
            print(f"{ten:<16} {mo_ta:<44} LỖI — {dong['loi']}")
            continue
        tong = dong["tong"]
        acc = _pt(tong.accuracy_khi_tra_loi) if tong and tong.so_tra_loi else "—"
        f1 = f"{tong.macro_f1:.3f}" if tong else "—"
        p50 = f"{tong.latency_p50_ms}" if tong else "—"
        p95 = f"{dong.get('p95_ms', 0)}"
        ty_le = dong.get("ty_le_leo_t2")
        leo = f"{_pt(ty_le)}" if ty_le is not None else "—"
        chi_phi = (
            f"${tong.tong_chi_phi_usd:.4f}" + ("" if tong.du_gia else " (thiếu giá)")
            if tong
            else "—"
        )
        print(
            f"{ten:<16} {mo_ta:<44} {acc:>7} {f1:>6} {p50:>8} {p95:>8} {leo:>9} "
            f"{dong['token_vao']}/{dong['token_ra']:>9} {chi_phi:>12} {dong['so_loi']:>5}"
        )
    _in_ket_luan(cac_dong)
    print("=" * 130)


def _in_ket_luan(cac_dong: list[dict]) -> None:
    """Gợi ý cấu hình dùng được — accuracy cao nhất trong nhóm p50 < 3000 ms.

    Đây là GỢI Ý cho người đọc, không phải quyết định: nó không đổi gì, chỉ
    giúp đọc bảng nhanh. Ưu tiên accuracy, hoà thì chọn cái % leo T2 thấp hơn.
    """
    ung_vien: list[tuple[float, str, float]] = []
    for dong in cac_dong:
        if dong.get("loi") or dong.get("tong") is None:
            continue
        tong = dong["tong"]
        if tong.latency_p50_ms < 3000 and tong.so_tra_loi:
            ung_vien.append((tong.accuracy_khi_tra_loi, dong["ten"], float(dong.get("ty_le_leo_t2", 0.0) or 0.0)))
    if not ung_vien:
        print("\nKhông có cấu hình nào đạt p50 < 3000 ms và có ảnh trả lời — xem bảng để quyết định.")
        return
    ung_vien.sort(key=lambda dong: (-dong[0], dong[2]))
    acc_tot, ten_tot, leo_tot = ung_vien[0]
    print(
        f"\nGợi ý: '{ten_tot}' — accuracy cao nhất ({_pt(acc_tot)}) trong nhóm p50 < 3000 ms, "
        f"% leo T2 = {_pt(leo_tot)}. Kiểm số liệu thô rồi quyết định."
    )


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="So sánh nhiều cấu hình model T1 trên cùng bộ ảnh")
    parser.add_argument("--limit", type=int, default=50, help="số ảnh tối đa mỗi nhóm mỗi bộ (mặc định 50)")
    parser.add_argument("--bo", choices=BO_HOP_LE, help="chỉ chạy một bộ; mặc định chạy cả hai")
    parser.add_argument("--dong-y", action="store_true", help="đồng ý tiêu quota/chi phí và chạy thật")
    parser.add_argument("--liet-ke", action="store_true", help="chỉ đếm ảnh + liệt kê cấu hình, không gọi model")
    parser.add_argument(
        "--nghi-giay",
        type=float,
        default=0.0,
        help="nghỉ bao nhiêu giây giữa hai ảnh; bắt buộc khi provider giới hạn theo PHÚT (Groq: 25)",
    )
    args = parser.parse_args(argv)

    cac_bo = [args.bo] if args.bo else list(BO_HOP_LE)

    with session_scope() as session:
        rows = session.scalars(select(WasteCategory).order_by(WasteCategory.sort_order)).all()
        nhan_list = [c.code for c in rows]
        ma_nguy_hai = {c.code for c in rows if c.is_hazardous}

        print(f"\nDanh sách cấu hình ({len(CAC_CAU_HINH)}):")
        for cf in CAC_CAU_HINH:
            max_tok = f" · max_output_tokens={cf.get('max_output_tokens')}" if cf.get("max_output_tokens") else ""
            print(f"  · {cf['ten']:<14} {cf['provider']}/{cf['model']}{max_tok}")

        anh_theo_bo: dict[str, list[tuple[Path, str]]] = {}
        for bo in cac_bo:
            anh, canh_bao = _quet_anh(bo, set(nhan_list), args.limit)
            anh_theo_bo[bo] = anh
            for dong in canh_bao:
                print(f"⚠ {dong}")

        tong_anh = sum(len(v) for v in anh_theo_bo.values())
        print(f"\nBộ ảnh tại {THU_MUC_ANH.relative_to(ROOT)}:")
        for bo in cac_bo:
            nhom = {nhan for _, nhan in anh_theo_bo[bo]}
            print(f"  {bo:10s} {len(anh_theo_bo[bo]):4d} ảnh · {len(nhom)}/{len(nhan_list)} nhóm có ảnh")
        if tong_anh == 0:
            print("⚠ Chưa có ảnh nào trong data/eval — không đo được gì.")
            return 1

        if args.liet_ke:
            return 0
        if not args.dong_y:
            for cf in CAC_CAU_HINH:
                _ap_dung_cau_hinh(cf)
                print(f"\n→ Dự toán cho cấu hình: {cf['ten']} ({cf['provider']}/{cf['model']})")
                _in_du_toan({bo: len(v) for bo, v in anh_theo_bo.items()})
            print("\nThêm --dong-y để chạy thật.")
            return 0

        cac_dong = chay_luot_do(
            session,
            CAC_CAU_HINH,
            cac_bo,
            nhan_list,
            ma_nguy_hai,
            limit=args.limit,
            nghi_giay=args.nghi_giay,
            luu_file=True,
        )
        in_bang(cac_dong)
        for dong in cac_dong:
            if dong.get("file"):
                print(f"  Kết quả thô của {dong['ten']}: {dong['file']}")
        print("\nSo tiếp nhiều lần chạy: python eval/so_sanh_lan_chay.py <tên file> ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
