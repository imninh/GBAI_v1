"""Test P82 — quét toàn bộ app, đảm bảo không đường dẫn tĩnh nào bị che.

Mỗi route có đường dẫn chứa ``{`` (tham số) được bỏ qua — chỉ kiểm các
route đường dẫn chữ (``/nhan-vien-kha-dung``, ``/tao-lich-tuan``, …).

Cách làm: tạo ``scope`` HTTP cho mỗi đường dẫn tĩnh, duyệt ``app.routes``
từ đầu, tìm route **đầu tiên** khớp (``route.matches(scope)`` trả khác
``Match.NONE``). Nếu route khớp đầu tiên **không phải chính nó** thì
đường dẫn đang bị che bởi một route tham số đăng ký trước.
"""

from __future__ import annotations

from starlette.routing import Match

from src.main import app


def _static_routes() -> list[tuple[str, str]]:
    """Trả về danh sách ``(method, path)`` cho các route đường dẫn tĩnh."""
    ket_qua: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or methods is None:
            continue
        if "{" in path:
            continue
        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            ket_qua.append((method, path))
    return ket_qua


def test_khong_co_duong_dan_bi_che():
    """Mọi đường dẫn tĩnh phải được route đúng khớp, không bị che bởi /{param}."""
    vi_pham: list[str] = []
    for method, path in _static_routes():
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "root_path": "",
        }
        for route in app.routes:
            match, _ = route.matches(scope)
            if match is Match.NONE:
                continue
            # Route này khớp — kiểm xem có phải route gốc không
            route_path = getattr(route, "path", None)
            if route_path != path:
                vi_pham.append(f"{method} {path} bị route {route_path} cướp")
            break

    assert not vi_pham, (
        "Các đường dẫn bị che:\n" + "\n".join(f"  - {v}" for v in vi_pham)
    )
