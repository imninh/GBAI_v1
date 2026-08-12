"""Khoá cửa cho ba lỗi THẬT đang sống trên bản deploy ở app cư dân (gói P27).

Ba lỗi đều lọt qua `lint` + `typecheck` + toàn bộ test Python vì không cổng nào
nhìn vào frontend. Test này quét **dưới dạng văn bản** (đúng khuôn
``test_di_tru_trang_thai.py``), không chạm mạng, không chạm trình duyệt:

1. ảnh "đã gửi cho AI" không được dùng ``<img src={mediaUrl(...)}>`` — endpoint
   đòi Bearer token mà thẻ ``<img>`` không gửi được (đo thật ra 401);
2. màn cư dân không còn từ vựng trạng thái cũ;
3. mọi trạng thái trong điều kiện nút "Huỷ yêu cầu" đều là trạng thái có thật;
4. AndroidManifest khai quyền vị trí (và không khai quyền nền);
5. không còn ``enableHighAccuracy: true`` mà thiếu ``maximumAge``;
6. nhánh lỗi của ``getCurrentPosition`` phải nhận tham số lỗi.
"""

from __future__ import annotations

import re
from pathlib import Path

GOC_DU_AN = Path(__file__).resolve().parents[1]

TU_VUNG_CU = ["pending", "scheduled", "approved", "rejected", "done", "cancelled"]


def _cac_file_frontend(duoi: tuple[str, ...]) -> list[Path]:
    """Mọi file đuôi cho trước dưới ``frontend/src``."""
    goc = GOC_DU_AN / "frontend" / "src"
    cac_file: list[Path] = []
    if goc.is_dir():
        for duoi_teo in duoi:
            cac_file.extend(sorted(goc.rglob(f"*.{duoi_teo}")))
    return cac_file


def test_khong_con_img_src_mediaurl() -> None:
    """Không file frontend nào còn dùng ``<img src={mediaUrl(...)}>``.

    ``GET /api/v1/media/{id}`` đòi header ``Authorization: Bearer …``
    (``src/api/routers/media.py:36``), mà thẻ ``<img>`` không bao giờ gửi header
    đó — đo thật trên bản deploy ngày 11/08: ``/api/v1/media/1`` không token →
    HTTP 401. Mọi ảnh từ endpoint có xác thực phải đi qua ``AnhCoToken``
    (tải bằng ``fetch`` kèm token, đổi ra ``blob:``).
    """
    vi_pham: list[str] = []
    for tep in _cac_file_frontend(("tsx",)):
        noi_dung = tep.read_text(encoding="utf-8")
        if "<img src={mediaUrl" in noi_dung:
            vi_pham.append(str(tep.relative_to(GOC_DU_AN)))
    assert vi_pham == [], (
        "Còn chỗ dùng <img src={mediaUrl(...)}> — sẽ nhận 401 và hiện ảnh vỡ:\n" + "\n".join(vi_pham)
    )


def test_man_cu_dan_khong_con_tu_vung_trang_thai_cu() -> None:
    """Màn cư dân không còn chuỗi trạng thái cũ dưới dạng văn bản.

    Chỉ quét ``personal.tsx`` — ``done``/``cancelled`` vẫn là từ vựng HỢP LỆ của
    máy trạng thái TUYẾN (``PickupRoute.status``), nên KHÔNG cấm hai chuỗi đó ở
    phạm vi toàn repo. Trong đúng file màn cư dân này thì không còn chỗ nào dùng.
    """
    tep = GOC_DU_AN / "frontend" / "src" / "components" / "resident" / "personal.tsx"
    noi_dung = tep.read_text(encoding="utf-8")
    con_sot = [tu for tu in TU_VUNG_CU if f'"{tu}"' in noi_dung]
    assert con_sot == [], f"personal.tsx còn từ vựng trạng thái cũ: {con_sot}"


def _trang_thai_trong_dieu_kien_huy(noi_dung: str) -> list[str]:
    """Các trạng thái trong câu điều kiện nút "Huỷ yêu cầu" (personal.tsx)."""
    trung_khop = re.search(r"\[([^\]]*)\]\s*\.includes\(yc\.status\)", noi_dung)
    assert trung_khop is not None, "Không tìm thấy điều kiện nút 'Huỷ yêu cầu' trong personal.tsx"
    return [m.strip('" ') for m in trung_khop.group(1).split(",") if m.strip()]


def _cac_khoa_nhan_trang_thai() -> list[str]:
    """9 khoá của ``NHAN_TRANG_THAI_YEU_CAU`` (frontend/src/lib/pickup-states.ts)."""
    noi_dung = (GOC_DU_AN / "frontend" / "src" / "lib" / "pickup-states.ts").read_text(encoding="utf-8")
    return [m for m in re.findall(r'^  ([a-z_]+): "', noi_dung, re.MULTILINE)]


def test_moi_trang_thai_trong_dieu_kien_huy_deu_co_that() -> None:
    """Mọi trạng thái trong điều kiện nút "Huỷ" phải là trạng thái có thật.

    Lỗi gốc sinh ra vì danh sách CẤM dùng từ vựng cũ (``["scheduled", "done",
    "cancelled"]``) — ba khoá đó không tồn tại nên nút luôn hiện. Test này rút
    danh sách trong câu điều kiện ra rồi đối chiếu với ``NHAN_TRANG_THAI_YEU_CAU``
    — trạng thái không có thật là lỗi, không phải dự phòng.
    """
    tep = GOC_DU_AN / "frontend" / "src" / "components" / "resident" / "personal.tsx"
    danh_sach = _trang_thai_trong_dieu_kien_huy(tep.read_text(encoding="utf-8"))
    assert danh_sach, "Điều kiện nút 'Huỷ yêu cầu' phải có ít nhất một trạng thái"
    khoa_hop_le = set(_cac_khoa_nhan_trang_thai())
    sai = [t for t in danh_sach if t not in khoa_hop_le]
    assert sai == [], f"Trạng thái không tồn tại trong NHAN_TRANG_THAI_YEU_CAU: {sai}"


def test_manifest_android_co_quyen_vi_tri() -> None:
    """AndroidManifest phải khai quyền vị trí, và KHÔNG khai quyền nền.

    WebView của Capacitor không cấp quyền mà app không khai — thiếu
    ``ACCESS_FINE_LOCATION``/``ACCESS_COARSE_LOCATION`` là định vị chết hẳn trong
    bản APK. ``ACCESS_BACKGROUND_LOCATION`` bị cấm vì app không chạy nền và quyền
    đó kéo theo một vòng duyệt riêng của Google Play.
    """
    noi_dung = (GOC_DU_AN / "frontend" / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(
        encoding="utf-8"
    )
    assert 'android.permission.ACCESS_FINE_LOCATION' in noi_dung, "Thiếu ACCESS_FINE_LOCATION"
    assert 'android.permission.ACCESS_COARSE_LOCATION' in noi_dung, "Thiếu ACCESS_COARSE_LOCATION"
    assert 'android.permission.ACCESS_BACKGROUND_LOCATION' not in noi_dung, "Có ACCESS_BACKGROUND_LOCATION — cấm"


def _doan_goi_get_current_position(noi_dung: str) -> str:
    """Thân lời gọi ``getCurrentPosition(...)``, đếm ngoặc để lấy TRỌN khối.

    Lời gọi chứa các lệnh gọi con lồng nhau (``setViTriGps({ ... })`` kết thúc
    bằng ``);``), nên tìm ``);`` đầu tiên là cắt cụt giữa chừng — phải đếm độ
    sâu ngoặc từ ``(`` của ``getCurrentPosition``.
    """
    bat = noi_dung.find("getCurrentPosition(")
    if bat == -1:
        return ""
    bat += len("getCurrentPosition")
    do_sau = 0
    for i in range(bat, len(noi_dung)):
        ky_tu = noi_dung[i]
        if ky_tu == "(":
            do_sau += 1
        elif ky_tu == ")":
            do_sau -= 1
            if do_sau == 0:
                return noi_dung[bat : i + 1]
    return ""


def test_khong_dung_enable_high_accuracy() -> None:
    """`enableHighAccuracy: true` phải đi cùng `maximumAge`.

    Trên laptop không có GPS, ``enableHighAccuracy: true`` ép trình duyệt đợi
    định vị vệ tinh rồi hết giờ → TIMEOUT dù người dùng đã Cho phép. Định vị
    Wi-Fi/di động sai vài trăm mét là đủ để xếp thứ tự điểm gửi.

    Chỉ quét THÂN lời gọi ``getCurrentPosition``, không quét comment — chú thích
    giải thích tại sao cấm cũng nhắc đúng chuỗi bị cấm.
    """
    tep = GOC_DU_AN / "frontend" / "src" / "components" / "resident" / "nearby-bins.tsx"
    doan = _doan_goi_get_current_position(tep.read_text(encoding="utf-8"))
    assert doan, "Không tìm thấy lời gọi getCurrentPosition trong nearby-bins.tsx"
    # Lọc comment: chú thích giải thích tại sao cấm cũng nhắc đúng chuỗi bị cấm.
    khong_comment = "\n".join(dong for dong in doan.splitlines() if not dong.strip().startswith("//"))
    assert "enableHighAccuracy: true" not in khong_comment, "Còn enableHighAccuracy: true — laptop sẽ TIMEOUT"
    assert "maximumAge" in khong_comment, "Thiếu maximumAge — mỗi lần bấm lại đo lại từ đầu"


def test_nhanh_loi_vi_tri_nhan_tham_so() -> None:
    """Nhánh lỗi của ``getCurrentPosition`` phải nhận tham số lỗi.

    Ba nguyên nhân hoàn toàn khác nhau (từ chối quyền · không có nguồn định vị ·
    quá hạn) cần ba câu báo khác nhau. Nhánh ``() =>`` vứt tham số sẽ gộp chúng
    thành một câu mơ hồ, không ai chẩn được.
    """
    tep = GOC_DU_AN / "frontend" / "src" / "components" / "resident" / "nearby-bins.tsx"
    doan = _doan_goi_get_current_position(tep.read_text(encoding="utf-8"))
    assert doan, "Không tìm thấy lời gọi getCurrentPosition trong nearby-bins.tsx"
    assert re.search(r"\(\s*err\s*\)\s*=>", doan), "Nhánh lỗi phải nhận tham số (err)"
    assert not re.search(r"},\s*\(\s*\)\s*=>", doan), "Nhánh lỗi vẫn còn dạng () => vứt tham số"
