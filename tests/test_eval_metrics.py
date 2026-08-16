"""Kiểm phần tính chỉ số của eval — chạy được mà không cần ảnh, không cần API key.

Trọng tâm là **quy ước đếm**, vì đó mới là chỗ dễ sai và cũng là chỗ quyết định
con số đưa lên slide: từ chối trả lời phải được tính là *an toàn*, không phải là
*sai*.
"""

from __future__ import annotations

from eval.metrics import NHAN_TU_CHOI, KetQuaAnh, chi_so_theo_nhom, ma_tran_nham_lan, tong_hop

NHAN = ["recyclable_plastic", "recyclable_paper", "hazardous"]
NGUY_HAI = {"hazardous"}


def _anh(nhan_dung: str, nhan_du_doan: str = "", **kwargs) -> KetQuaAnh:
    return KetQuaAnh(duong_dan=f"{nhan_dung}.jpg", bo="tu_chup", nhan_dung=nhan_dung, nhan_du_doan=nhan_du_doan, **kwargs)


def test_tu_choi_khong_tinh_la_dung_va_khong_tinh_la_sai_nhom_khac():
    """Ảnh bị từ chối là ``fn`` của nhóm đúng, và không đổ ``fp`` cho nhóm nào."""
    ket_qua = [_anh("hazardous", tu_choi=True, ly_do_tu_choi="nghi_nguy_hai")]
    theo_nhom = {cs.nhan: cs for cs in chi_so_theo_nhom(ket_qua, NHAN)}

    assert theo_nhom["hazardous"].fn == 1
    assert theo_nhom["hazardous"].tp == 0
    assert sum(cs.fp for cs in theo_nhom.values()) == 0


def test_chi_so_an_toan_khong_tinh_anh_bi_tu_choi():
    """Từ chối một ảnh nguy hại là hành vi ĐÚNG — không được vào tử số chỉ số an toàn.

    Đây là quy ước quan trọng nhất của cả module. Đếm sai chỗ này thì con số
    "0% rác nguy hại bị xếp thành rác thường" trên slide là con số bịa.
    """
    ket_qua = [
        _anh("hazardous", "hazardous"),  # đúng
        _anh("hazardous", tu_choi=True, ly_do_tu_choi="nghi_nguy_hai"),  # an toàn
        _anh("hazardous", "recyclable_plastic"),  # ← ca nguy hiểm thật
        _anh("hazardous", tu_choi=True, ly_do_tu_choi="duoi_nguong"),  # an toàn
    ]
    th = tong_hop(ket_qua, NHAN, NGUY_HAI)

    assert th.so_anh_nguy_hai == 4
    assert th.ty_le_nguy_hai_thanh_thuong == 0.25  # đúng 1/4, không phải 3/4
    assert th.recall_nguy_hai == 0.25


def test_hai_loai_accuracy_khac_nhau_khi_co_tu_choi():
    ket_qua = [
        _anh("recyclable_plastic", "recyclable_plastic"),
        _anh("recyclable_paper", "recyclable_plastic"),
        _anh("recyclable_paper", tu_choi=True, ly_do_tu_choi="anh_mo"),
        _anh("recyclable_plastic", tu_choi=True, ly_do_tu_choi="anh_mo"),
    ]
    th = tong_hop(ket_qua, NHAN, NGUY_HAI)

    assert th.ty_le_tra_loi == 0.5
    assert th.accuracy_khi_tra_loi == 0.5  # 1 đúng / 2 ảnh đã trả lời
    assert th.accuracy_toan_bo == 0.25  # 1 đúng / 4 ảnh
    assert th.ly_do_tu_choi == {"anh_mo": 2}


def test_bao_dong_nham_tinh_tren_rieng_anh_khong_nguy_hai():
    ket_qua = [
        _anh("recyclable_plastic", "hazardous"),
        _anh("recyclable_paper", "recyclable_paper"),
        _anh("hazardous", "hazardous"),
    ]
    th = tong_hop(ket_qua, NHAN, NGUY_HAI)

    assert th.ty_le_thuong_thanh_nguy_hai == 0.5  # 1/2 ảnh không nguy hại, không phải 1/3


def test_macro_f1_chi_tinh_tren_nhom_co_anh():
    """Nhóm chưa chụp được ảnh nào không được kéo macro-F1 xuống 0."""
    ket_qua = [_anh("recyclable_plastic", "recyclable_plastic"), _anh("recyclable_paper", "recyclable_paper")]
    th = tong_hop(ket_qua, NHAN, NGUY_HAI)

    assert th.macro_f1 == 1.0  # `hazardous` support 0 nên bị bỏ ra ngoài


def test_anh_loi_khong_lot_vao_bat_ky_chi_so_nao():
    ket_qua = [_anh("recyclable_plastic", "recyclable_plastic"), _anh("hazardous", loi="OSError: hỏng file")]
    th = tong_hop(ket_qua, NHAN, NGUY_HAI)

    assert th.so_anh == 1
    assert th.so_loi == 1
    assert th.so_anh_nguy_hai == 0
    assert th.accuracy_toan_bo == 1.0


def test_ma_tran_co_cot_rieng_cho_tu_choi():
    ket_qua = [
        _anh("hazardous", "recyclable_plastic"),
        _anh("hazardous", tu_choi=True, ly_do_tu_choi="nghi_nguy_hai"),
    ]
    matran = ma_tran_nham_lan(ket_qua, NHAN)

    assert matran["hazardous"]["recyclable_plastic"] == 1
    assert matran["hazardous"][NHAN_TU_CHOI] == 1
    assert matran["hazardous"]["hazardous"] == 0


def test_do_tre_p50_p95():
    ket_qua = [_anh("recyclable_plastic", "recyclable_plastic", latency_ms=ms) for ms in (100, 200, 300, 400, 5000)]
    th = tong_hop(ket_qua, NHAN, NGUY_HAI)

    assert th.latency_p50_ms == 300
    assert th.latency_p95_ms == 5000


def test_thieu_gia_model_thi_bao_thieu():
    """Một ảnh không biết giá là cả lần chạy phải bị đánh dấu thiếu giá."""
    ket_qua = [
        _anh("recyclable_plastic", "recyclable_plastic", cost_usd=0.001),
        _anh("recyclable_paper", "recyclable_paper", price_known=False),
    ]
    th = tong_hop(ket_qua, NHAN, NGUY_HAI)

    assert th.du_gia is False
    assert th.tong_chi_phi_usd == 0.001
