"""Khoá cửa cho gói P34 — hai script đo model/độ phân giải.

Không test nào gọi model thật, không test nào chạm mạng: mọi đường "gọi model"
đều bị thay bằng hàm giả có bộ đếm, hoặc bị khoá bởi quét văn bản. Ba việc gói
này chốt lại:

- Mặc định chạy khô: chỉ ``--dong-y`` mới gọi model (test 1, 2);
- **Cache T0 luôn tắt** ở mọi lần chạy của cả hai script (test 4 — chốt chặn
  chính: bật cache, ba độ phân giải ăn kết quả lẫn nhau và in ra y hệt nhau);
- Không bịa tên model, không tự viết hàm nén thay cho ``src.services.image``
  (test 5, 6).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import select

from eval import so_sanh_model
from eval.metrics import KetQuaAnh
from src.config import reset_settings_cache
from src.db.models import WasteCategory

GOC_DU_AN = Path(__file__).resolve().parents[1]
TEP_SO_SANH = GOC_DU_AN / "eval" / "so_sanh_model.py"
TEP_DO_DO = GOC_DU_AN / "eval" / "do_do_phan_giai.py"

#: Bốn biến môi trường mà hai script đổi — phải trả về nguyên trạng sau mỗi test.
_BIEN_MAY_TINH = (
    "VISION_PROVIDER_T1",
    "VISION_MODEL_T1",
    "VISION_MAX_OUTPUT_TOKENS",
    "MEDIA_MAX_EDGE_PX",
)


@pytest.fixture
def _giu_moi_truong() -> None:
    """Khôi phục biến môi trường và cache settings sau mỗi test."""
    cu = {k: os.environ.get(k) for k in _BIEN_MAY_TINH}
    yield
    for k, v in cu.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    reset_settings_cache()


@contextmanager
def _mo_phong_session_scope(session):
    """Thay ``session_scope()`` để main() chạy trên CSDL trong bộ nhớ thay vì data/app.db."""
    yield session


def _cac_nhan(db_session) -> tuple[list[str], set[str]]:
    rows = db_session.scalars(select(WasteCategory).order_by(WasteCategory.sort_order)).all()
    nhan_list = [c.code for c in rows]
    ma_nguy_hai = {c.code for c in rows if c.is_hazardous}
    return nhan_list, ma_nguy_hai


def test_liet_ke_khong_goi_model(db_session, monkeypatch, capsys, _giu_moi_truong) -> None:
    """``--liet-ke`` chỉ đếm ảnh + liệt kê cấu hình, không gọi model một lần nào."""
    so_goi: list[str] = []

    def _cam_goi(*a, **k):
        so_goi.append("model")
        raise AssertionError("--liet-ke không được gọi model")

    monkeypatch.setattr(so_sanh_model, "classify_waste", _cam_goi)
    monkeypatch.setattr(so_sanh_model, "session_scope", lambda: _mo_phong_session_scope(db_session))

    ket = so_sanh_model.main(["--liet-ke"])

    assert ket == 0
    assert so_goi == [], "Nhánh --liet-ke phải không gọi model lần nào"
    out = capsys.readouterr().out
    assert "Danh sách cấu hình" in out
    assert "hien-tai-t1" in out


def test_khong_co_dong_y_thi_khong_goi_model(db_session, monkeypatch, capsys, _giu_moi_truong) -> None:
    """Thiếu ``--dong-y`` thì không gọi model, nhưng phải in dự toán."""
    so_goi: list[str] = []

    def _cam_goi(*a, **k):
        so_goi.append("model")
        raise AssertionError("Chưa có --dong-y thì không được gọi model")

    monkeypatch.setattr(so_sanh_model, "classify_waste", _cam_goi)
    monkeypatch.setattr(so_sanh_model, "session_scope", lambda: _mo_phong_session_scope(db_session))

    ket = so_sanh_model.main(["--limit", "5"])

    assert ket == 0
    assert so_goi == [], "Thiếu --dong-y phải dừng ở bước dự toán"
    out = capsys.readouterr().out
    assert "Dự toán" in out, "Phải in dự toán trước khi dừng"


def test_mot_cau_hinh_hong_khong_giet_ca_luot(db_session, monkeypatch, capsys, _giu_moi_truong) -> None:
    """Cấu hình thứ 2 ném lỗi (hết quota/mô phỏng) → cấu hình 1 và 3 vẫn chạy, dòng 2 ghi LỖI."""
    cac_cau_hinh = [
        {"ten": "ok-1", "provider": "nvidia", "model": "m-ok-1"},
        {"ten": "hong-2", "provider": "groq", "model": "m-hong"},
        {"ten": "ok-3", "provider": "nvidia", "model": "m-ok-3"},
    ]

    def _gia_chay_mot_anh(session, duong_dan, nhan_dung, bo, media_dir, dung_cache=False, **kw):
        model = os.environ.get("VISION_MODEL_T1", "")
        if model == "m-hong":
            raise RuntimeError("hết quota giả lập giữa lượt đo")
        kq = KetQuaAnh(duong_dan=str(duong_dan), bo=bo, nhan_dung=nhan_dung, nhan_du_doan=nhan_dung)
        return kq, 100, 50

    monkeypatch.setattr(so_sanh_model, "chay_mot_anh", _gia_chay_mot_anh)
    nhan_list, ma_nguy_hai = _cac_nhan(db_session)

    cac_dong = so_sanh_model.chay_luot_do(
        db_session,
        cac_cau_hinh,
        ["cong_khai"],
        nhan_list,
        ma_nguy_hai,
        limit=1,
        nghi_giay=0,
        luu_file=False,
    )

    assert cac_dong[0]["loi"] == "", "Cấu hình 1 phải chạy xong bình thường"
    assert cac_dong[0]["tong"] is not None
    assert "LỖI" in cac_dong[1]["loi"], "Cấu hình 2 phải ghi LỖI vào bảng"
    assert cac_dong[2]["loi"] == "", "Cấu hình 3 phải vẫn chạy sau khi cấu hình 2 hỏng"

    so_sanh_model.in_bang(cac_dong)
    out = capsys.readouterr().out
    assert "hong-2" in out


def test_moi_lan_chay_deu_tat_cache() -> None:
    """Chốt chặn chính: cả hai script luôn tắt cache T0.

    Bật cache, lần 256px chạy sau lần 512px trên cùng tấm ảnh sẽ ăn kết quả đã
    cache (cùng pHash) → ba độ phân giải in ra y hệt nhau, token ≈ 0, trông như
    "hạ xuống 256px không mất gì" nhưng là kết luận hoàn toàn sai.
    """
    for tep in (TEP_SO_SANH, TEP_DO_DO):
        noi_dung = tep.read_text(encoding="utf-8")
        assert "dung_cache=False" in noi_dung, f"{tep.name} phải tắt cache T0 ở mọi lần chạy"
        assert "dung_cache=True" not in noi_dung, f"{tep.name} không được bật cache T0"
        assert "--dung-cache" not in noi_dung, f"{tep.name} không được để người dùng bật cache"


def test_ba_do_phan_giai_dung_cung_ham_nen() -> None:
    """``do_do_phan_giai.py`` phải nén bằng ĐÚNG hàm của ``src.services.image``.

    Khác hàm là khác kết quả — nếu nó tự định nghĩa một hàm resize riêng thì bảng
    đo độ phân giải không còn so sánh được với lần đo của ``run_eval.py``.
    """
    noi_dung = TEP_DO_DO.read_text(encoding="utf-8")
    assert "from src.services.image import" in noi_dung, "Phải import hàm nén từ src.services.image"
    assert "preprocess_image" in noi_dung
    assert "ham_nen=preprocess_image" in noi_dung, "Phải truyền hàm nén của sản phẩm vào đường đo"
    for dong in noi_dung.splitlines():
        if dong.lstrip().startswith("def ") and ("resize" in dong.lower() or "thumbnail" in dong.lower()):
            raise AssertionError(f"do_do_phan_giai tự định nghĩa hàm nén: {dong.strip()}")


def test_khong_bia_ten_model(_giu_moi_truong) -> None:
    """Không được tự bịa tên model vào ``CAC_CAU_HINH``.

    Hai cấu hình "hiện tại" phải khớp đúng chuỗi model trong ``config.py``
    (``PROVIDER_DEFAULT_MODELS``) — nơi duy nhất trong repo tên model được xác
    nhận là còn sống. Đã điền thêm cấu hình khác thì mọi phần tử phải đủ ba khoá.
    """
    reset_settings_cache()
    from src.config import PROVIDER_DEFAULT_MODELS

    cac = so_sanh_model.CAC_CAU_HINH
    assert len(cac) >= 2, "Phải có ít nhất hai cấu hình hiện tại"

    if len(cac) == 2:
        for cf in cac:
            assert {"ten", "provider", "model"} <= set(cf.keys())
        hien_tai = {c["ten"]: c for c in cac}
        assert "hien-tai-t1" in hien_tai and "hien-tai-t2" in hien_tai
        assert hien_tai["hien-tai-t1"]["model"] == PROVIDER_DEFAULT_MODELS["nvidia"][0], (
            "'hien-tai-t1' phải khớp mặc định nvidia trong config.py"
        )
        assert hien_tai["hien-tai-t2"]["model"] == PROVIDER_DEFAULT_MODELS["groq"][0], (
            "'hien-tai-t2' phải khớp mặc định groq trong config.py"
        )
    else:
        for cf in cac:
            assert {"ten", "provider", "model"} <= set(cf.keys()), f"Thiếu khoá ten/provider/model: {cf}"
