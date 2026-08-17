"""Chặn kiểu numpy rò lên cột JSON — sự cố 16/08/2026.

Production trả ``TypeError: Object of type int64 is not JSON serializable`` ở
``finish_run`` vì một con số thống kê numpy lọt vào ``meta`` rồi được ghi xuống
cột JSON. Không tái hiện được ở máy dev vì numpy khác phiên bản (2.x trả `int`,
1.x trả `int64`).

Vá ở biên ghi dữ liệu (:func:`runs._ve_kieu_python`) thay vì đuổi theo từng field
— mỗi phiên bản numpy lại lộ một field khác. Test dùng một lớp giả có ``.item()``
đóng vai numpy scalar, **không import numpy** (máy chạy có thể không có).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from src.services.classifier import NodeMetric
from src.services.image import phash_distance
from src.services.runs import _ve_kieu_python, record_nodes, start_run


class _NumpyGia:
    """Đóng vai numpy scalar: có ``.item()`` trả về giá trị Python."""

    def __init__(self, gia_tri: int) -> None:
        self._gia_tri = gia_tri

    def item(self) -> int:
        return self._gia_tri


@pytest.fixture(autouse=True)
def _khong_numpy(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ngăn ai lén import numpy vào bài test — fix phải chạy được khi không có numpy."""
    import builtins

    that = builtins.__import__

    def chan(ten: str, *args, **kwargs):
        if ten == "numpy" or ten.startswith("numpy."):
            raise AssertionError("Test này không được import numpy")
        return that(ten, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", chan)
    yield


def test_dung_lop_gia_duong_vai_numpy_scalar() -> None:
    """Lớp giả có ``.item()`` → ``_ve_kieu_python`` đổi thành int và JSON dumps chạy."""
    gia = _ve_kieu_python(_NumpyGia(7))
    assert gia == 7
    assert type(gia) is int, "numpy scalar phải về đúng kiểu int"
    assert json.dumps({"diem": gia}) == '{"diem": 7}'


def test_long_nhau_dict_trong_list_trong_dict() -> None:
    """Đệ quy xuyên cả dict → list → dict, lá nào mang numpy cũng bị đổi."""
    lon_xon = {
        "nhan": "local_model",
        "meta": [
            {"nguong": _NumpyGia(82), "chot": True},
            {"danh_sach": {"so_vat": _NumpyGia(3), "nhanh": None}},
        ],
    }
    sach = _ve_kieu_python(lon_xon)

    assert sach["meta"][0]["nguong"] == 82
    assert type(sach["meta"][0]["nguong"]) is int
    assert sach["meta"][1]["danh_sach"]["so_vat"] == 3
    assert sach["meta"][1]["danh_sach"]["nhanh"] is None
    json.dumps(sach)


def test_kieu_goc_giu_nguyen() -> None:
    """bool/int/float/str/None/dict/list không bị xáo động."""
    vao = {"a": 1, "b": 1.5, "c": "chữ", "d": True, "e": None, "f": [1, "hai"]}
    ra = _ve_kieu_python(vao)
    assert ra == vao


def test_gia_tri_la_dich_list_tu_tuong_duoc_gop() -> None:
    """List/tuple đầu vào không đổi kiểu container — chỉ đổi lá."""
    ra = _ve_kieu_python([_NumpyGia(5), ("x", _NumpyGia(9))])
    assert ra == [5, ["x", 9]]


def test_ghi_meta_vao_csdl_chay_trot_lot(db_session: Session) -> None:
    """record_nodes ghi được node mang meta numpy giả — đúng đường đã từng nổ."""
    run = start_run(db_session, kind="classify", trigger="user")
    node = NodeMetric(
        node="local_yolo",
        meta={"nghi_do_dien_tu": False, "cac_lop": [_NumpyGia(1), _NumpyGia(2)]},
    )
    record_nodes(db_session, run, [node])

    from src.db.models import RunNodeMetric

    ghi = db_session.query(RunNodeMetric).one()
    assert ghi.meta["cac_lop"] == [1, 2]
    assert type(ghi.meta["cac_lop"][0]) is int


def test_phash_distance_tra_dung_kieu_int() -> None:
    """phash_distance ép về int tại nguồn — không trả int64 cho dù numpy 1.x."""
    khoang_cach = phash_distance("a" * 16, "b" * 16)
    assert type(khoang_cach) is int, "chữ ký `-> int` phải đúng trên mọi phiên bản numpy"
    assert khoang_cach > 0


def test_phash_distance_ban_trai_ban_phai() -> None:
    """Cùng hai giá trị, so trái/phải phải cho cùng một khoảng cách."""
    assert phash_distance("0" * 16, "f" * 16) == phash_distance("f" * 16, "0" * 16)
