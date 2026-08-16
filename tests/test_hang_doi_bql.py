"""Khoá cửa cho gói P28 — hàng đợi nhãn phân tầng và nối `duong_di` vào màn duyệt.

Quét **thân đúng một hàm** trong `frontend/src/components/manager/queues.tsx`
bằng khuôn đã viết ở `test_di_tru_trang_thai.py`: tìm điểm mở, đếm độ sâu ngoặc
tới điểm đóng. Lý do KHÔNG quét cả file: `queues.tsx` chứa bốn hàng đợi với
nhiều đoạn mã gần giống nhau, quét cả file sẽ khoá nhầm một hàm khác.

Không test nào chạm mạng — chỉ đọc file văn bản, không chạy code frontend.
"""

from __future__ import annotations

from pathlib import Path

GOC_DU_AN = Path(__file__).resolve().parents[1]

TEP_QUEUES = GOC_DU_AN / "frontend" / "src" / "components" / "manager" / "queues.tsx"
TEP_TYPES = GOC_DU_AN / "frontend" / "src" / "lib" / "types.ts"


def _than_khoi(noi_dung: str, ten: str) -> str:
    """Thân khối bắt đầu sau token `ten`, tính độ sâu ngoặc tới ngoặc đóng cân bằng.

    Trả về chuỗi rỗng khi không tìm thấy — file khác khỏi bị quét. Cách cắt này
    lặp lại khuôn `_than_tb_trang_thai` của gói P24: tìm điểm mở rồi đếm `{`/`}`.
    """
    bat_dau = noi_dung.find(ten)
    if bat_dau == -1:
        return ""
    mo = noi_dung.find("{", bat_dau)
    if mo == -1:
        return ""
    # Đếm từ chính ngoặc mở (`mo`) chứ không phải từ sau nó: ngoặc mở của khối
    # phải được đếm thì ngoặc đóng cân bằng mới là ngoặc ngoài cùng. Đúng khuôn
    # `_than_tb_trang_thai` của gói P24 (mo chỉ VÀO `{` rồi range từ mo).
    do_sau = 0
    for i in range(mo, len(noi_dung)):
        ky_tu = noi_dung[i]
        if ky_tu == "{":
            do_sau += 1
        elif ky_tu == "}":
            do_sau -= 1
            if do_sau == 0:
                return noi_dung[mo + 1 : i]
    return ""


def _noi_dung_queues() -> str:
    return TEP_QUEUES.read_text(encoding="utf-8")


def _than_verify_queue() -> str:
    return _than_khoi(_noi_dung_queues(), "function VerifyQueue")


def _than_weight_confirm_queue() -> str:
    return _than_khoi(_noi_dung_queues(), "function WeightConfirmQueue")


def test_route_map_duoc_truyen_duong_di() -> None:
    """Chỗ gọi `RouteMap` phải truyền `duong_di` xuống bản đồ.

    Gói P26 đã dựng xong cả hai đầu — backend trả `duong_di` trong payload và
    `route-map.tsx` nhận prop — nhưng chỗ gọi bị bỏ quên nên màn duyệt vẫn vẽ
    nét đứt, toàn bộ công của P26 không ai nhìn thấy. Test này chặn việc đó
    tái diễn: đúng một chỗ gọi `<RouteMap` và chính dòng đó phải có `duong_di`.
    """
    noi_dung = _noi_dung_queues()
    cac_dong = [dong for dong in noi_dung.splitlines() if "<RouteMap" in dong]
    assert len(cac_dong) == 1, f"Phải đúng một chỗ gọi <RouteMap, gặp {len(cac_dong)}"
    assert "duong_di" in cac_dong[0], "Dòng gọi <RouteMap phải truyền duong_di"


def test_pickuproute_khai_khoa_duong_di() -> None:
    """`PickupRoute` trong `types.ts` phải khai trường `duong_di`.

    Khai đúng ngay cạnh `diff?` — cùng khối interface, cùng hợp đồng với backend.
    """
    noi_dung = TEP_TYPES.read_text(encoding="utf-8")
    than = _than_khoi(noi_dung, "PickupRoute")
    assert than, "Không tìm thấy khối PickupRoute trong types.ts"
    assert "duong_di" in than, "PickupRoute phải khai trường duong_di"


def test_khong_duyet_hang_loat_ca_nguy_hai() -> None:
    """Bộ lọc khối duyệt hàng loạt phải loại ca nguy hại và ca bị từ chối.

    Đây là ràng buộc an toàn: nhóm nguy hại dùng ngưỡng cao hơn hẳn, và ca đã
    bị từ chối trả lời thì không có nhãn AI nào để chấp nhận. Nếu bộ lọc mất
    một trong hai điều kiện, test này đỏ — quét thân đúng `VerifyQueue`, không
    quét cả file vì `refused`/`is_hazardous` còn xuất hiện ở các hàng đợi khác.
    """
    than = _than_verify_queue()
    assert than, "Không tìm thấy thân hàm VerifyQueue"
    assert "is_hazardous" in than, "Bộ lọc duyệt nhanh phải loại ca nguy hại"
    assert "refused" in than, "Bộ lọc duyệt nhanh phải loại ca bị từ chối"


def test_khong_dung_promise_all_khi_duyet_hang_loat() -> None:
    """Duyệt hàng loạt phải chạy TUẦN TỰ — `Promise.all` là 50 request song song
    vào một máy chủ 512 MB, tự bắn vào chân và mất luôn khả năng báo ca nào hỏng.
    """
    than = _than_verify_queue()
    assert "Promise.all" not in than, "Không được dùng Promise.all khi duyệt hàng loạt"


def test_o_nhap_can_khong_con_goi_la_khoi_luong_that() -> None:
    """Nhãn ô nhập cân không còn mời người ngồi bàn giấy đoán số.

    Nhãn cũ "Khối lượng thật (kg)" khiến ban quản lý tưởng số cân là việc của
    mình, trong khi người cầm cân là đội thu gom ngoài hiện trường. Nay phải
    nói rõ số đến từ đội thu gom và cảnh báo không ước lượng thay họ.
    """
    than = _than_weight_confirm_queue()
    assert than, "Không tìm thấy thân hàm WeightConfirmQueue"
    assert "Số cân đội thu gom báo (kg)" in than, "Nhãn ô nhập phải nói số cân đội thu gom báo"
    assert "Khối lượng thật (kg)" not in than, "Nhãn cũ phải được bỏ đi"
    assert "đừng ước lượng thay họ" in than, "Phải có câu cảnh báo không ước lượng thay đội thu gom"
