"""Đo chất lượng phân loại rác trên bộ ảnh có đáp án — deliverable #10.

Đây là phép đo cho PLO 7 (*"eval pipeline, failure → cải tiến"*) và cho mục 7
của ``CLAUDE.md``. Script chạy **đúng đường sản phẩm**: tiền xử lý ảnh →
:func:`src.services.classifier.classify_waste` → định tuyến 4 tầng. Không có
đường tắt nào, nên con số đo được là năng lực thật của sản phẩm chứ không phải
năng lực của một model gọi trần.

## Xếp ảnh ở đâu

Thư mục ``data/eval/`` (đã nằm trong ``.gitignore``), **hai bộ tách bạch**::

    data/eval/
      cong_khai/            ← TrashNet, RealWaste, TACO… — ghi nguồn vào NGUON.md
        recyclable_plastic/*.jpg
        hazardous/*.jpg
      tu_chup/              ← ảnh nhóm tự chụp tại phòng rác tầng
        recyclable_paper/*.jpg
        ...

Tên thư mục con **chính là mã nhóm rác** trong bảng ``waste_categories``. Sai
tên thì script báo ngay chứ không âm thầm bỏ qua.

Hai bộ **luôn báo cáo tách rời**. Khoảng cách miền là có thật và rất lớn: một
model đạt 94,18% trên TrashNet chỉ còn 41,04% trên RealWaste (``CLAUDE.md``
mục 6). Gộp hai bộ vào một con số là tự lừa mình.

## Kiểm soát chi phí

``--limit`` mặc định **50 ảnh/bộ**, và script **in dự toán rồi dừng** — phải
thêm ``--dong-y`` mới thực sự gọi model (quy ước ``CLAUDE.md`` mục 9).

Chạy::

    python eval/run_eval.py --liet-ke              # chỉ đếm ảnh, không gọi gì
    python eval/run_eval.py                        # in dự toán rồi dừng
    python eval/run_eval.py --dong-y --limit 20    # chạy thật
    python eval/run_eval.py --dong-y --bo tu_chup  # chỉ bộ tự chụp
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from eval.metrics import BO_CONG_KHAI, BO_TU_CHUP, KetQuaAnh, TongHop, ma_tran_nham_lan, tong_hop  # noqa: E402
from eval.report_writer import in_bao_cao, in_ma_tran  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.db.models import WasteCategory  # noqa: E402
from src.db.session import session_scope  # noqa: E402
from src.services.classifier import classify_waste  # noqa: E402
from src.services.image import preprocess_image  # noqa: E402
from src.services.safety import RefusalReason  # noqa: E402

THU_MUC_ANH = ROOT / "data" / "eval"
THU_MUC_KET_QUA = ROOT / "eval" / "results"
DUOI_ANH = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
BO_HOP_LE = (BO_CONG_KHAI, BO_TU_CHUP)

#: Token đầu vào đo được cho một ảnh 512px, ngày 02/08/2026 (`eval/results/report.md`
#: mục 2). Dùng để **dự toán**, không dùng để báo cáo.
TOKEN_VAO_MOI_ANH = 2400
TOKEN_RA_MOI_ANH = 700


def _quet_anh(bo: str, nhan_hop_le: set[str], limit: int) -> tuple[list[tuple[Path, str]], list[str]]:
    """Quét ``data/eval/<bo>/<mã nhóm>/*`` thành danh sách (đường dẫn, nhãn đúng).

    Returns:
        Cặp ``(danh sách ảnh, danh sách cảnh báo)``. Thư mục con không khớp mã
        nhóm nào **không bị bỏ qua im lặng** — nó thành một dòng cảnh báo.
    """
    goc = THU_MUC_ANH / bo
    if not goc.is_dir():
        return [], []

    anh: list[tuple[Path, str]] = []
    canh_bao: list[str] = []
    for thu_muc in sorted(p for p in goc.iterdir() if p.is_dir()):
        nhan = thu_muc.name
        if nhan not in nhan_hop_le:
            canh_bao.append(f"{bo}/{nhan} — không phải mã nhóm rác nào, đã bỏ qua")
            continue
        tep = sorted(p for p in thu_muc.iterdir() if p.suffix.lower() in DUOI_ANH)
        anh.extend((p, nhan) for p in tep[:limit])
        if len(tep) > limit:
            canh_bao.append(f"{bo}/{nhan} — có {len(tep)} ảnh, chỉ lấy {limit} đầu (xem --limit)")
    return anh, canh_bao


def _chay_mot_anh(session, duong_dan: Path, nhan_dung: str, bo: str, media_dir: str, dung_cache: bool) -> KetQuaAnh:
    """Chạy trọn đường sản phẩm cho một ảnh và ghi lại kết cục."""
    kq = KetQuaAnh(duong_dan=str(duong_dan.relative_to(ROOT)), bo=bo, nhan_dung=nhan_dung)
    bat_dau = time.perf_counter()
    try:
        processed = preprocess_image(duong_dan.read_bytes(), media_dir=media_dir, keep_original=False)
        image_bytes = Path(processed.stored_path).read_bytes()
        outcome = classify_waste(
            session,
            image_bytes=image_bytes,
            image_phash=processed.phash if dung_cache else "",
        )
    except (OSError, ValueError) as exc:
        kq.loi = f"{type(exc).__name__}: {exc}"
        kq.latency_ms = int((time.perf_counter() - bat_dau) * 1000)
        return kq

    kq.nhan_du_doan = outcome.category_code
    kq.tu_choi = outcome.refused
    kq.ly_do_tu_choi = outcome.refusal_reason
    # `model_loi` KHÔNG phải một lần từ chối — nó là hệ thống không chạy được.
    # Gộp hai thứ vào một cột "tỉ lệ trả lời" sẽ khiến một lần chạy hỏng vì hết
    # quota trông y hệt một hệ thống thận trọng, và số đó dễ đi thẳng vào báo cáo.
    if outcome.refusal_reason == RefusalReason.MODEL_LOI:
        kq.loi = f"model_loi: {outcome.refusal_headline_vi}"
    kq.tier = outcome.tier
    kq.model = outcome.model
    kq.latency_ms = outcome.latency_ms
    kq.cost_usd = outcome.cost_usd
    kq.price_known = outcome.price_known
    return kq


def _in_du_toan(so_anh_theo_bo: dict[str, int]) -> None:
    """In dự toán token/chi phí/quota trước khi tiêu một đồng nào."""
    from src.config import MODEL_PRICES_USD_PER_MTOK
    from src.services.vision import get_tier_model, get_tier_provider

    tong_anh = sum(so_anh_theo_bo.values())
    print(f"Dự toán cho {tong_anh} ảnh (mỗi ảnh ~{TOKEN_VAO_MOI_ANH} token vào, ~{TOKEN_RA_MOI_ANH} token ra):\n")

    tong_usd = 0.0
    thieu_gia: list[str] = []
    for tang in ("t1", "t2"):
        model = get_tier_model(tang)
        provider = get_tier_provider(tang)
        gia = MODEL_PRICES_USD_PER_MTOK.get(model)
        if gia is None:
            thieu_gia.append(f"{tang.upper()} {provider}/{model}")
            print(f"  {tang.upper():3s} {provider}/{model} — CHƯA CÓ GIÁ trong bảng")
            continue
        usd = tong_anh * (TOKEN_VAO_MOI_ANH * gia[0] + TOKEN_RA_MOI_ANH * gia[1]) / 1_000_000
        tong_usd += usd
        print(f"  {tang.upper():3s} {provider}/{model} — tối đa ${usd:.4f}")

    print(f"\n  Cận trên (giả định MỌI ảnh đều leo lên T2): ${tong_usd:.4f}")
    if thieu_gia:
        print(
            "\n⚠ Không dự toán được bằng tiền cho: "
            + ", ".join(thieu_gia)
            + "\n  Bổ sung vào MODEL_PRICES_USD_PER_MTOK (src/config.py) thì số này mới đủ."
        )
    print(
        f"\n⚠ Ràng buộc thật thường là QUOTA chứ không phải tiền: free tier Gemini chỉ\n"
        f"  20 request/model/ngày. {tong_anh} ảnh sẽ cạn quota nếu tầng nào đó chạy Gemini.\n"
        f"\nThêm --dong-y để chạy thật."
    )


def _cau_hinh_dang_chay(args: argparse.Namespace) -> dict:
    """Ảnh chụp cấu hình đang chạy, ghi thẳng vào file kết quả.

    Ngày 08/08/2026 hai file kết quả nằm cạnh nhau mà không cách nào biết lần
    nào cấu hình tầng T1 ra sao — phải suy ngược từ tên model xuất hiện nhiều
    nhất, và suy sai, vì lần đó T1 hỏng hết nên mọi bản ghi đều mang tên model
    của T2. Ghi thẳng cấu hình vào file thì hết phải đoán.
    """
    from src.services.vision import get_tier_model, get_tier_provider

    settings = get_settings()
    return {
        "tang": {
            tang: {"provider": get_tier_provider(tang), "model": get_tier_model(tang)} for tang in ("t1", "t2", "text")
        },
        "local_model_enabled": settings.local_model_enabled,
        "dung_cache_phash": bool(args.dung_cache),
        "nghi_giay": float(args.nghi_giay),
        "limit": int(args.limit),
    }


def _luu_ket_qua(
    ket_qua: list[KetQuaAnh],
    tong: dict[str, TongHop],
    nhan_list: list[str],
    cau_hinh: dict,
) -> Path:
    """Ghi kết quả thô ra JSON để lần sau so sánh được hai lần chạy."""
    THU_MUC_KET_QUA.mkdir(parents=True, exist_ok=True)
    dau_thoi_gian = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    duong_dan = THU_MUC_KET_QUA / f"phan_loai-{dau_thoi_gian}.json"
    duong_dan.write_text(
        json.dumps(
            {
                "chay_luc": datetime.now(UTC).isoformat(),
                "nhan": nhan_list,
                "cau_hinh": cau_hinh,
                "tong_hop": {
                    bo: {
                        "so_anh": t.so_anh,
                        "so_tra_loi": t.so_tra_loi,
                        "so_tu_choi": t.so_tu_choi,
                        "so_loi": t.so_loi,
                        "ty_le_tra_loi": round(t.ty_le_tra_loi, 4),
                        "accuracy_khi_tra_loi": round(t.accuracy_khi_tra_loi, 4),
                        "accuracy_toan_bo": round(t.accuracy_toan_bo, 4),
                        "macro_f1": round(t.macro_f1, 4),
                        "recall_nguy_hai": round(t.recall_nguy_hai, 4),
                        "ty_le_nguy_hai_thanh_thuong": round(t.ty_le_nguy_hai_thanh_thuong, 4),
                        "latency_p50_ms": t.latency_p50_ms,
                        "latency_p95_ms": t.latency_p95_ms,
                        "tong_chi_phi_usd": round(t.tong_chi_phi_usd, 6),
                        "du_gia": t.du_gia,
                        "theo_tier": t.theo_tier,
                        "ly_do_tu_choi": t.ly_do_tu_choi,
                    }
                    for bo, t in tong.items()
                },
                "tung_anh": [vars(kq) for kq in ket_qua],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return duong_dan


def main() -> int:
    # PHẢI đứng trước `ArgumentParser`: `--help` in mô tả tiếng Việt rồi thoát
    # ngay trong `parse_args()`, nên đặt sau đó là quá muộn — console Windows mã
    # cp1252 sẽ nổ `UnicodeEncodeError` trước khi dòng chỉnh mã kịp chạy.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Đo chất lượng phân loại rác trên bộ ảnh có đáp án")
    parser.add_argument("--limit", type=int, default=50, help="số ảnh tối đa mỗi nhóm rác mỗi bộ (mặc định 50)")
    parser.add_argument("--bo", choices=BO_HOP_LE, help="chỉ chạy một bộ; mặc định chạy cả hai")
    parser.add_argument("--dong-y", action="store_true", help="đồng ý tiêu quota/chi phí và chạy thật")
    parser.add_argument("--liet-ke", action="store_true", help="chỉ đếm ảnh đang có, không gọi model")
    parser.add_argument("--dung-cache", action="store_true", help="bật cache pHash T0 (mặc định TẮT khi eval)")
    parser.add_argument(
        "--nghi-giay",
        type=float,
        default=0.0,
        help="nghỉ bao nhiêu giây giữa hai ảnh; bắt buộc khi provider giới hạn theo PHÚT (Groq: 25)",
    )
    args = parser.parse_args()

    cac_bo = [args.bo] if args.bo else list(BO_HOP_LE)

    with session_scope() as session:
        rows = session.scalars(select(WasteCategory).order_by(WasteCategory.sort_order)).all()
        nhan_list = [c.code for c in rows]
        ma_nguy_hai = {c.code for c in rows if c.is_hazardous}
        if not nhan_list:
            print("⚠ CSDL chưa có nhóm rác nào — chạy `python scripts/seed.py --reset` trước.")
            return 1

        anh_theo_bo: dict[str, list[tuple[Path, str]]] = {}
        for bo in cac_bo:
            anh, canh_bao = _quet_anh(bo, set(nhan_list), args.limit)
            anh_theo_bo[bo] = anh
            for dong in canh_bao:
                print(f"⚠ {dong}")

        print(f"\nBộ ảnh tại {THU_MUC_ANH.relative_to(ROOT)}:")
        for bo in cac_bo:
            nhom = {nhan for _, nhan in anh_theo_bo[bo]}
            print(f"  {bo:10s} {len(anh_theo_bo[bo]):4d} ảnh · {len(nhom)}/{len(nhan_list)} nhóm có ảnh")

        tong_anh = sum(len(v) for v in anh_theo_bo.values())
        if tong_anh == 0:
            print(
                "\n⚠ Chưa có ảnh nào. Xếp ảnh theo cấu trúc sau rồi chạy lại:\n"
                f"    {THU_MUC_ANH.relative_to(ROOT)}/<cong_khai|tu_chup>/<mã nhóm>/*.jpg\n"
                f"  Mã nhóm hợp lệ: {', '.join(nhan_list)}\n"
                "  Bộ tự chụp là bộ QUAN TRỌNG NHẤT, không phải bộ bổ sung (CLAUDE.md mục 6)."
            )
            return 1

        if args.liet_ke:
            return 0
        if not args.dong_y:
            print()
            _in_du_toan({bo: len(v) for bo, v in anh_theo_bo.items()})
            return 0

        ket_qua: list[KetQuaAnh] = []
        with tempfile.TemporaryDirectory(prefix="greenbin-eval-") as media_dir:
            for bo in cac_bo:
                for i, (duong_dan, nhan) in enumerate(anh_theo_bo[bo], start=1):
                    kq = _chay_mot_anh(session, duong_dan, nhan, bo, media_dir, args.dung_cache)
                    ket_qua.append(kq)
                    dau = "✗" if kq.loi else ("·" if kq.tu_choi else ("✓" if kq.dung else "✗"))
                    ket = kq.loi or kq.nhan_du_doan or kq.ly_do_tu_choi
                    print(f"  [{bo} {i}/{len(anh_theo_bo[bo])}] {dau} {duong_dan.name} → {ket}")
                    # Hạn mức theo PHÚT không lách được bằng cách chạy ít ảnh đi
                    # — phải giãn từng lượt. Đo ngày 08/08/2026: một ảnh 512px
                    # qua `qwen/qwen3.6-27b` tốn ~2.250 token vào + ~990 token ra;
                    # trần 8.000 token/phút của Groq cho khoảng 2,5 ảnh mỗi phút,
                    # nên `--nghi-giay 25`. Chạy sát nhau thì 429 từ ảnh thứ ba,
                    # và cả lần đo thành vô nghĩa.
                    if args.nghi_giay > 0:
                        time.sleep(args.nghi_giay)

        so_loi = sum(1 for kq in ket_qua if kq.loi)
        if so_loi > len(ket_qua) / 5:
            print(
                f"\n⛔ {so_loi}/{len(ket_qua)} ảnh KHÔNG chạy được (hết quota, thiếu key, model hỏng).\n"
                "   Lần chạy này chưa đo được gì — ĐỪNG trích số bên dưới vào báo cáo."
            )

        tong: dict[str, TongHop] = {}
        for bo in cac_bo:
            cua_bo = [kq for kq in ket_qua if kq.bo == bo]
            if cua_bo:
                tong[bo] = tong_hop(cua_bo, nhan_list, ma_nguy_hai, bo=bo)

        in_bao_cao(tong, ma_nguy_hai)
        for bo, t in tong.items():
            if t.so_anh:
                print(f"\n### Ma trận nhầm lẫn — {bo}")
                in_ma_tran(ma_tran_nham_lan([kq for kq in ket_qua if kq.bo == bo], nhan_list), nhan_list)

        duong_dan = _luu_ket_qua(ket_qua, tong, nhan_list, _cau_hinh_dang_chay(args))
        print(f"\nKết quả thô: {duong_dan.relative_to(ROOT)}")
        print(f"Chép các bảng trên vào {(THU_MUC_KET_QUA / 'report.md').relative_to(ROOT)} mục 3.")

        sai = [kq for kq in ket_qua if not kq.loi and not kq.tu_choi and kq.nhan_du_doan and not kq.dung]
        if sai:
            print(f"\nFailure case ({len(sai)} ảnh) — đây là đầu vào cho vòng cải tiến, không phải số để giấu:")
            for kq in sai[:20]:
                nguy_hiem = " ⚠ NGUY HẠI BỊ BỎ LỌT" if kq.nhan_dung in ma_nguy_hai else ""
                print(f"  · {kq.duong_dan} — đúng {kq.nhan_dung}, hệ thống nói {kq.nhan_du_doan}{nguy_hiem}")

        settings = get_settings()
        print(f"\nCấu hình lúc chạy: prompt {settings.prompt_version} · cache T0 {'BẬT' if args.dung_cache else 'TẮT'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
