"""Khoá xác thực của thiết bị gắn trên thùng thu gom.

Mỗi thùng có một khoá riêng, lưu dưới dạng **băm** — chuỗi thô chỉ hiện đúng một
lần lúc cấp. Thùng chưa được cấp khoá riêng thì vẫn dùng khoá chung
``BIN_DEVICE_KEY``, để đội thùng đang chạy ngoài hiện trường không chết giữa
chừng khi triển khai.

Băm bằng SHA-256 chứ không dùng ``hash_password`` (PBKDF2 200.000 vòng): PBKDF2
chậm có chủ đích để chống dò **mật khẩu do người chọn** — thứ ít entropy. Khoá ở
đây là 32 byte ngẫu nhiên do máy sinh, dò kiểu đó là vô vọng, nên cái chậm chỉ
còn là chi phí — mà endpoint ingest bị gọi liên tục bởi mọi thùng.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from src.db.models import Bin


def sinh_khoa() -> str:
    """Sinh một khoá thiết bị mới, dạng chuỗi an toàn cho URL và header."""
    return secrets.token_urlsafe(32)


def bam_khoa(khoa: str) -> str:
    """Băm khoá thành 64 ký tự hex. Cùng đầu vào luôn cho cùng đầu ra."""
    return hashlib.sha256(khoa.encode("utf-8")).hexdigest()


def kiem_khoa(thung: Bin, khoa_nhan: str, khoa_chung: str) -> bool:
    """Khoá gửi lên có mở được thùng này không.

    Thứ tự xét là bắt buộc:

    1. Khoá rỗng → **chặn**, không xét gì thêm. Fail closed.
    2. Thùng **đã có** khoá riêng → chỉ khoá riêng của nó mới mở được. Khoá chung
       KHÔNG còn mở được thùng đã cấp khoá — nếu không thì việc cấp khoá riêng
       chẳng thu hẹp được gì.
    3. Thùng **chưa có** khoá riêng → so với khoá chung, đúng như trước gói này.

    So bằng ``hmac.compare_digest`` ở cả hai nhánh: so chuỗi thường mất thời gian
    khác nhau theo số ký tự đúng, đủ để đoán dần khoá.
    """
    if not khoa_nhan:
        return False
    if thung.device_key_hash:
        return hmac.compare_digest(bam_khoa(khoa_nhan), thung.device_key_hash)
    if not khoa_chung:
        return False
    return hmac.compare_digest(khoa_nhan, khoa_chung)


def cap_khoa_moi(thung: Bin) -> str:
    """Cấp khoá mới cho một thùng, ghi bản băm vào thùng, **trả về chuỗi thô**.

    Chuỗi thô này là lần duy nhất khoá tồn tại ở dạng đọc được — chỗ gọi phải in
    ra hoặc đưa cho người lắp thiết bị ngay. Cấp lại lần nữa là **thu hồi** khoá
    cũ: bản băm cũ bị ghi đè, thiết bị nào còn giữ khoá cũ sẽ bị chặn từ request
    kế tiếp.
    """
    khoa = sinh_khoa()
    thung.device_key_hash = bam_khoa(khoa)
    return khoa


def thu_hoi_khoa(thung: Bin) -> None:
    """Thu hồi khoá của một thùng — dùng khi khoá bị lộ.

    Sau khi gọi, thùng **không nhận reading từ bất kỳ khoá nào** cho tới lúc
    được cấp khoá mới bằng ``cap_khoa_moi``.

    Cách làm: cấp một khoá mới rồi **vứt chuỗi thô đi**. Bản băm còn lại trong
    CSDL là băm của một chuỗi 32 byte ngẫu nhiên mà không ai trên đời biết —
    tương đương một cánh cửa không có chìa.

    ⚠️ **Đừng đặt ``device_key_hash = ""``.** Đọc ``kiem_khoa``: ô băm rỗng nghĩa
    là "thùng chưa được cấp khoá riêng" và nó **rơi ngược về khoá chung**. Thùng
    vừa bị lộ khoá lại quay về cơ chế lỏng hơn — thu hồi kiểu đó là hạ cấp bảo
    mật chứ không phải nâng.
    """
    khoa_moi = sinh_khoa()
    thung.device_key_hash = bam_khoa(khoa_moi)
