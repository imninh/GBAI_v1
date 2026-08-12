"""Đo ảnh nén xuống 256 / 384 / 512 px — cùng một model, cùng một bộ ảnh.

Gói P34 — **chỉ đo, không sửa sản phẩm**. Một ảnh 512px tốn ~1.865 token; Groq
free tier cho 8.000 token/phút → ~4,3 ảnh/phút, và đó là nút thắt thông lượng,
không phải tiền. Hạ độ phân giải cắt đôi cả tiền lẫn trần phút cùng lúc — câu
hỏi của gói này là *mất bao nhiêu độ chính xác để đổi lấy thông lượng đó*.

Độ phân giải được đưa vào bằng biến môi trường ``MEDIA_MAX_EDGE_PX``
(→ ``settings.media_max_edge_px``, chỗ :func:`preprocess_image` đang nén) rồi
``reset_settings_cache()``. **Không sửa ``src/services/image.py``** — ảnh nén
bằng chính hàm của sản phẩm, chỉ khác con số cạnh dài.

⚠️ **Cache T0 LUÔN TẮT ở MỌI lần chạy** (``dung_cache=False``) — đây là chốt chặn
của gói này. Nếu bật cache, lần đo 256px chạy sau lần 512px trên **cùng những
tấm ảnh đó** sẽ ăn kết quả đã cache ở tầng T0 (khi ảnh gốc nhỏ hơn cạnh dài thì
``_resize_to_max_edge`` không nén, pHash trùng) → ba độ phân giải in ra y hệt
nhau: accuracy giống, token ≈ 0, latency thấp bất thường. Trông rất giống kết
luận "hạ xuống 256px không mất gì!" nhưng là kết luận hoàn toàn sai, và nó sẽ
dẫn cả dự án đi sai một vòng gói. Bằng chứng mỗi lần chạy thật sự gọi model:
cột token vào của ba lần phải **khác nhau**.

Chạy::

    python eval/do_do_phan_giai.py --liet-ke              # chỉ đếm ảnh
    python eval/do_do_phan_giai.py                        # in dự toán rồi dừng
    python eval/do_do_phan_giai.py --dong-y --limit 5     # chạy thật
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
from eval.run_eval import THU_MUC_ANH, THU_MUC_KET_QUA, _luu_ket_qua, _quet_anh  # noqa: E402
from eval.so_sanh_model import TRAN_TOKEN_GROQ_MOI_PHUT, chay_mot_anh  # noqa: E402
from src.config import get_settings, reset_settings_cache  # noqa: E402
from src.db.models import WasteCategory  # noqa: E402
from src.db.session import session_scope  # noqa: E402
from src.services.image import preprocess_image  # noqa: E402

BO_HOP_LE = (BO_CONG_KHAI, BO_TU_CHUP)

#: Ba mức cạnh dài cần so — con số ở đây là cột đầu của bảng kết quả.
CAC_DO_PHAN_GIAI = [256, 384, 512]


def chay_mot_do_phan_giai(
    session,
    px: int,
    cac_bo: list[str],
    nhan_list: list[str],
    ma_nguy_hai: set[str],
    *,
    limit: int,
    nghi_giay: float,
    luu_file: bool = False,
) -> dict:
    """Chạy cùng bộ ảnh ở một độ phân giải, trả về một dòng của bảng đo.

    Raises:
        Exception: khi cả lượt độ phân giải này hỏng — ``chay_luot_do`` bắt lỗi.
    """
    # Đổi độ phân giải bằng env, KHÔNG sửa src/services/image.py.
    os.environ["MEDIA_MAX_EDGE_PX"] = str(px)
    reset_settings_cache()

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
                # Cache T0 LUÔN TẮT — nén bằng ĐÚNG `preprocess_image` của sản phẩm.
                kq, tv, tr = chay_mot_anh(
                    session,
                    duong_dan,
                    nhan,
                    bo,
                    media_dir,
                    dung_cache=False,
                    ham_nen=preprocess_image,
                )
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
        duong_dan = _luu_ket_qua(ket_qua, tong, nhan_list, _cau_hinh_cho_file(px, limit, nghi_giay))
        ten_moi = THU_MUC_KET_QUA / f"phan-giai-{px}-{duong_dan.stem}.json"
        duong_dan.rename(ten_moi)
        file_ket_qua = str(ten_moi.relative_to(ROOT))

    return {
        "px": px,
        "tong": tong_tat_ca,
        "token_vao": token_vao,
        "token_ra": token_ra,
        "so_anh": len(ket_qua),
        "so_loi": sum(1 for kq in ket_qua if kq.loi),
        "file": file_ket_qua,
        "loi": "",
    }


def _cau_hinh_cho_file(px: int, limit: int, nghi_giay: float) -> dict:
    """Khối ``cau_hinh`` ghi vào file kết quả — để ``so_sanh_lan_chay.py`` đọc lại."""
    from src.services.vision import get_tier_model, get_tier_provider

    settings = get_settings()
    return {
        "tang": {tang: {"provider": get_tier_provider(tang), "model": get_tier_model(tang)} for tang in ("t1", "t2", "text")},
        "local_model_enabled": settings.local_model_enabled,
        "dung_cache_phash": False,
        "nghi_giay": nghi_giay,
        "limit": limit,
        "media_max_edge_px": px,
    }


def chay_luot_do(
    session,
    cac_px: list[int],
    cac_bo: list[str],
    nhan_list: list[str],
    ma_nguy_hai: set[str],
    *,
    limit: int,
    nghi_giay: float,
    luu_file: bool = False,
) -> list[dict]:
    """Chạy từng độ phân giải; một mức hỏng không giết cả lượt — ghi ``LỖI`` rồi tiếp."""
    cac_dong: list[dict] = []
    for px in cac_px:
        print(f"\n--- Độ phân giải: {px} px ---")
        try:
            cac_dong.append(
                chay_mot_do_phan_giai(
                    session,
                    px,
                    cac_bo,
                    nhan_list,
                    ma_nguy_hai,
                    limit=limit,
                    nghi_giay=nghi_giay,
                    luu_file=luu_file,
                )
            )
        except Exception as exc:
            # Một mức hỏng không giết cả lượt đo — ghi LỖI vào bảng rồi tiếp.
            cac_dong.append(
                {"px": px, "tong": None, "token_vao": 0, "token_ra": 0, "so_anh": 0, "so_loi": 0, "file": "", "loi": f"LỖI: {type(exc).__name__}: {exc}"}
            )
    return cac_dong


def _pt(x: float) -> str:
    return f"{x * 100:.1f}%"


def in_bang(cac_dong: list[dict]) -> None:
    """Bảng độ phân giải: px · acc · F1 · token vào tb/ảnh · p50 · $/1000 ảnh · ảnh/phút.

    Cột cuối (ảnh/phút) trả lời thẳng câu hỏi về nút thắt thông lượng: chia trần
    8.000 token/phút của Groq cho số token vào trung bình mỗi ảnh. Token của ba
    lần chạy PHẢI khác nhau — giống nhau nghĩa là lần sau ăn cache, đo vô nghĩa.
    """
    print("\n" + "=" * 100)
    print("ĐO ĐỘ PHÂN GIẢI ẢNH — cùng model, cùng bộ ảnh")
    print("=" * 100)
    print(f"{'px':>5}  {'accuracy':>9}  {'macro F1':>9}  {'token vào/ảnh':>14}  {'p50 ms':>8}  {'$/1000 ảnh':>11}  {'ảnh/phút (trần 8k tk)':>23}")
    for dong in cac_dong:
        if dong.get("loi"):
            print(f"{dong['px']:>5}  LỖI — {dong['loi']}")
            continue
        tong = dong["tong"]
        so_anh = dong["so_anh"]
        acc = _pt(tong.accuracy_khi_tra_loi) if tong and tong.so_tra_loi else "—"
        f1 = f"{tong.macro_f1:.3f}" if tong else "—"
        tb_token = (dong["token_vao"] / so_anh) if so_anh else 0
        p50 = f"{tong.latency_p50_ms}" if tong else "—"
        gia_1000 = (tong.tong_chi_phi_usd / so_anh * 1000) if (tong and so_anh) else 0.0
        anh_phut = (TRAN_TOKEN_GROQ_MOI_PHUT / tb_token) if tb_token else 0
        print(
            f"{dong['px']:>5}  {acc:>9}  {f1:>9}  {tb_token:>14.1f}  {p50:>8}  {gia_1000:>10.4f}$  {anh_phut:>20.1f}"
        )
    print("=" * 100)
    print("Cột 'token vào/ảnh' phải KHÁC NHAU giữa ba dòng — giống nhau nghĩa là lần sau ăn cache T0, đo vô nghĩa.")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="Đo độ phân giải ảnh: 256 / 384 / 512 px trên cùng bộ ảnh")
    parser.add_argument("--limit", type=int, default=50, help="số ảnh tối đa mỗi nhóm mỗi bộ (mặc định 50)")
    parser.add_argument("--bo", choices=BO_HOP_LE, help="chỉ chạy một bộ; mặc định chạy cả hai")
    parser.add_argument("--dong-y", action="store_true", help="đồng ý tiêu quota/chi phí và chạy thật")
    parser.add_argument("--liet-ke", action="store_true", help="chỉ đếm ảnh, không gọi model")
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
        print(f"Ba độ phân giải: {' · '.join(str(px) for px in CAC_DO_PHAN_GIAI)} px")
        if tong_anh == 0:
            print("⚠ Chưa có ảnh nào trong data/eval — không đo được gì.")
            return 1

        if args.liet_ke:
            return 0
        if not args.dong_y:
            print(f"\nDự toán cho {tong_anh} ảnh × 3 độ phân giải = {tong_anh * 3} lượt gọi model.\n")
            from eval.run_eval import _in_du_toan

            _in_du_toan({bo: len(v) for bo, v in anh_theo_bo.items()})
            print("\nThêm --dong-y để chạy thật.")
            return 0

        cac_dong = chay_luot_do(
            session,
            CAC_DO_PHAN_GIAI,
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
                print(f"  Kết quả thô của {dong['px']}px: {dong['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
