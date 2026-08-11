"""Gói P18 — câu `criteria` phải luôn đúng với thứ vừa chạy, không bao giờ hai câu.

`criteria` là lời giải thích của agent cho người duyệt tuyến. Bật cờ đường đi
thật (G3) lên mà để cả "đường chim bay" lẫn "đường đi thật" đứng cạnh nhau là
một câu nói dối trên màn hình giám khảo sẽ nhìn. Test này chốt: đúng MỘT câu nói
về khoảng cách ở mọi trạng thái cờ. Không test nào chạm mạng — bản `ma_tran_km`
thật được thay bằng ma trận giả, hoặc để cờ tắt cho nó trả `None`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest

from src.config import reset_settings_cache
from src.db.models import Bin, utcnow
from src.services import duong_di_that, route_planner


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    """Cấu hình đọc qua ``lru_cache`` nên phải xoá cache quanh mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


def _thung_day(code: str, lat: float, lng: float) -> Bin:
    """Thùng vừa báo về, đầy, có toạ độ — đủ điều kiện vào bộ xếp tuyến."""
    return Bin(
        code=code,
        name=f"Thùng {code}",
        lat=lat,
        lng=lng,
        capacity_liters=240.0,
        fill_percent=92.0,
        battery_percent=90.0,
        last_seen_at=utcnow(),
        is_active=True,
    )


def _tao_tuyen(db_session, monkeypatch: pytest.MonkeyPatch, *, dung_ma_tran: bool, ma: str = "CR") -> list[str]:
    """Dựng một tuyến 3 thùng rồi trả về danh sách `criteria`.

    ``dung_ma_tran=False`` để cờ tắt hẳn (không gọi mạng, ``ma_tran_km`` trả
    ``None``); ``dung_ma_tran=True`` thay ``ma_tran_km`` bằng bản trả ma trận giả
    hợp lệ để đường đi thật được dùng mà không đụng mạng. ``ma`` là tiền tố mã
    thùng — dùng khác nhau mỗi lần gọi vì session test dùng chung giữa các lần.
    """
    monkeypatch.setenv("ROUTE_REAL_DISTANCE", "true" if dung_ma_tran else "false")
    reset_settings_cache()
    if dung_ma_tran:

        def _ma_tran_gia(toa_do: list[tuple[float, float]]) -> list[list[float]]:
            n = len(toa_do)
            return [[0.0 if i == j else 1.0 for j in range(n)] for i in range(n)]

        monkeypatch.setattr(duong_di_that, "ma_tran_km", _ma_tran_gia)

    db_session.add_all(
        [
            _thung_day(f"{ma}-01", 21.0285, 105.8542),
            _thung_day(f"{ma}-02", 21.0330, 105.8500),
            _thung_day(f"{ma}-03", 21.0200, 105.8600),
        ]
    )
    db_session.flush()

    tuyen = route_planner.propose_route(db_session, service_date=date.today(), window="sang")
    return list(tuyen.reasoning["criteria"])


def test_criteria_noi_chim_bay_khi_cho_tat(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    criteria = _tao_tuyen(db_session, monkeypatch, dung_ma_tran=False)

    cau_ve_khoang_cach = [c for c in criteria if "khoảng cách" in c]
    assert len(cau_ve_khoang_cach) == 1, f"Phải đúng một câu về khoảng cách, có: {cau_ve_khoang_cach}"
    assert "đường chim bay" in cau_ve_khoang_cach[0]


def test_criteria_noi_duong_that_khi_dung_ma_tran(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    criteria = _tao_tuyen(db_session, monkeypatch, dung_ma_tran=True)

    cau_ve_khoang_cach = [c for c in criteria if "khoảng cách" in c]
    assert len(cau_ve_khoang_cach) == 1, f"Phải đúng một câu về khoảng cách, có: {cau_ve_khoang_cach}"
    assert "OSRM" in cau_ve_khoang_cach[0]


def test_khong_bao_gio_co_hai_cau_ve_khoang_cach(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chốt chặn chính của gói: đúng một câu về khoảng cách ở CẢ hai trạng thái cờ."""
    for dung_ma_tran, ma in ((False, "CRA"), (True, "CRB")):
        criteria = _tao_tuyen(db_session, monkeypatch, dung_ma_tran=dung_ma_tran, ma=ma)
        so_cau = sum(1 for c in criteria if "khoảng cách" in c)
        assert so_cau == 1, (
            f"Cờ {'bật' if dung_ma_tran else 'tắt'}: phải đúng một câu về khoảng cách, có {so_cau}"
        )


def test_criteria_khac_khong_bi_dung_toi(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bốn dòng còn lại (ngày, cụm toà, tải trọng, thùng + yêu cầu) giữ nguyên."""
    criteria = _tao_tuyen(db_session, monkeypatch, dung_ma_tran=False)

    assert len(criteria) == 5, criteria
    assert criteria[0].startswith("Cùng ngày")
    assert criteria[1].startswith("Cùng cụm toà")
    assert criteria[2].startswith("Tổng")
    assert "thùng đang đầy" in criteria[3]
    assert "gộp chung một chuyến" in criteria[3]
    assert criteria[4] == (
        "Thứ tự ghé tối ưu bằng nearest-neighbour + 2-opt trên khoảng cách đường chim bay"
    )
