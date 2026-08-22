"""Chỉ số đánh giá phân loại rác — phần tính toán thuần, không I/O, không gọi API.

Tách khỏi :mod:`eval.run_eval` để **test được mà không cần ảnh và không cần API
key**. Mọi hàm ở đây nhận vào một danh sách :class:`KetQuaAnh` và trả ra số.

## Ba trạng thái, không phải hai

Hệ thống có **ba** kết cục cho một tấm ảnh, không phải hai:

``đúng`` · ``sai`` · ``từ chối trả lời``

Từ chối **không phải là một dự đoán sai**. Đó là hành vi được thiết kế có chủ ý
(`CLAUDE.md` mục 5) và với nhóm nguy hại thì nó là hành vi *đúng*. Vì vậy mọi
chỉ số ở đây đều tách bạch ba trạng thái, và báo cáo phải ghi kèm **tỉ lệ trả
lời** — một hệ thống từ chối 90% số ảnh có thể đạt accuracy 100% mà vô dụng.

## Chỉ số an toàn là chỉ số quan trọng nhất

``ty_le_nguy_hai_thanh_thuong`` — trong các ảnh **thật sự** là rác nguy hại, bao
nhiêu phần trăm bị hệ thống chốt thành một nhóm **không** nguy hại. Mục tiêu 0%
(`CLAUDE.md` mục 7). Ảnh bị từ chối **không** tính vào tử số: từ chối là an toàn.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

BO_CONG_KHAI = "cong_khai"
BO_TU_CHUP = "tu_chup"

#: Cột dành riêng cho ảnh bị từ chối trong ma trận nhầm lẫn.
NHAN_TU_CHOI = "(từ chối)"


@dataclass
class KetQuaAnh:
    """Kết cục của **một** tấm ảnh sau khi đi trọn định tuyến 4 tầng."""

    duong_dan: str
    bo: str
    nhan_dung: str
    nhan_du_doan: str = ""
    tu_choi: bool = False
    ly_do_tu_choi: str = ""
    tier: str = ""
    model: str = ""
    latency_ms: int = 0
    cost_usd: float = 0.0
    price_known: bool = True
    loi: str = ""

    @property
    def dung(self) -> bool:
        """Đúng khi **có** trả lời và nhãn trùng đáp án. Từ chối không tính là đúng."""
        return not self.tu_choi and self.nhan_du_doan == self.nhan_dung


@dataclass
class ChiSoNhom:
    """Precision / recall / F1 của **một** nhóm rác."""

    nhan: str
    support: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        mau = self.tp + self.fp
        return self.tp / mau if mau else 0.0

    @property
    def recall(self) -> float:
        mau = self.tp + self.fn
        return self.tp / mau if mau else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class TongHop:
    """Toàn bộ số liệu của một lần chạy eval trên một bộ ảnh."""

    bo: str = "tất cả"
    so_anh: int = 0
    so_tra_loi: int = 0
    so_tu_choi: int = 0
    so_loi: int = 0
    so_dung: int = 0

    macro_f1: float = 0.0
    recall_nguy_hai: float = 0.0
    ty_le_nguy_hai_thanh_thuong: float = 0.0
    so_anh_nguy_hai: int = 0
    ty_le_thuong_thanh_nguy_hai: float = 0.0

    latency_p50_ms: int = 0
    latency_p95_ms: int = 0
    tong_chi_phi_usd: float = 0.0
    du_gia: bool = True

    theo_nhom: list[ChiSoNhom] = field(default_factory=list)
    theo_tier: dict[str, int] = field(default_factory=dict)
    ly_do_tu_choi: dict[str, int] = field(default_factory=dict)

    @property
    def ty_le_tra_loi(self) -> float:
        """Tỉ lệ ảnh hệ thống dám trả lời. Đọc accuracy mà bỏ qua số này là đọc sai."""
        return self.so_tra_loi / self.so_anh if self.so_anh else 0.0

    @property
    def accuracy_khi_tra_loi(self) -> float:
        """Accuracy tính trên **riêng** các ảnh đã trả lời."""
        return self.so_dung / self.so_tra_loi if self.so_tra_loi else 0.0

    @property
    def accuracy_toan_bo(self) -> float:
        """Accuracy tính trên **mọi** ảnh — từ chối bị tính như không đúng."""
        return self.so_dung / self.so_anh if self.so_anh else 0.0


def _phan_vi(gia_tri: list[int], phan_tram: float) -> int:
    """Phân vị theo lối "nearest-rank", đủ dùng và không cần numpy.

    Dùng ``ceil`` chứ không phải ``round``: ``round`` của Python làm tròn về số
    chẵn, nên p50 của 5 mẫu ra hạng 2 thay vì hạng 3 — tức báo độ trễ *thấp hơn*
    thực tế, đúng chiều sai mà một báo cáo hiệu năng không được phép mắc.
    """
    if not gia_tri:
        return 0
    sap_xep = sorted(gia_tri)
    vi_tri = max(1, min(len(sap_xep), math.ceil(phan_tram / 100 * len(sap_xep))))
    return sap_xep[vi_tri - 1]


def chi_so_theo_nhom(ket_qua: list[KetQuaAnh], nhan_list: list[str]) -> list[ChiSoNhom]:
    """Tính precision/recall/F1 cho từng nhóm rác.

    Ảnh bị **từ chối** tính là ``fn`` của nhóm đúng và **không** tính ``fp`` cho
    nhóm nào — vì hệ thống không hề khẳng định nhãn nào cả. Cách quy ước này làm
    recall tụt khi hệ thống nhát, đúng như bản chất, mà không đổ oan cho precision.
    """
    bang = {nhan: ChiSoNhom(nhan=nhan) for nhan in nhan_list}
    for kq in ket_qua:
        if kq.loi:
            continue
        if kq.nhan_dung in bang:
            bang[kq.nhan_dung].support += 1
        if kq.tu_choi or not kq.nhan_du_doan:
            if kq.nhan_dung in bang:
                bang[kq.nhan_dung].fn += 1
            continue
        if kq.nhan_du_doan == kq.nhan_dung:
            if kq.nhan_dung in bang:
                bang[kq.nhan_dung].tp += 1
            continue
        if kq.nhan_du_doan in bang:
            bang[kq.nhan_du_doan].fp += 1
        if kq.nhan_dung in bang:
            bang[kq.nhan_dung].fn += 1
    return [bang[nhan] for nhan in nhan_list]


def ma_tran_nham_lan(ket_qua: list[KetQuaAnh], nhan_list: list[str]) -> dict[str, dict[str, int]]:
    """Ma trận nhầm lẫn, có thêm cột :data:`NHAN_TU_CHOI` cho ảnh bị từ chối.

    Hàng là nhãn đúng, cột là nhãn hệ thống trả ra. Cột từ chối tách riêng để
    nhìn ra ngay hệ thống đang *sai* hay đang *nhát*.
    """
    cot = [*nhan_list, NHAN_TU_CHOI]
    matran = {hang: dict.fromkeys(cot, 0) for hang in nhan_list}
    for kq in ket_qua:
        if kq.loi or kq.nhan_dung not in matran:
            continue
        du_doan = NHAN_TU_CHOI if (kq.tu_choi or not kq.nhan_du_doan) else kq.nhan_du_doan
        if du_doan in matran[kq.nhan_dung]:
            matran[kq.nhan_dung][du_doan] += 1
    return matran


def tong_hop(ket_qua: list[KetQuaAnh], nhan_list: list[str], ma_nguy_hai: set[str], bo: str = "tất cả") -> TongHop:
    """Gộp toàn bộ chỉ số của một bộ ảnh.

    Args:
        ket_qua: kết cục từng ảnh.
        nhan_list: danh sách mã nhóm rác hợp lệ, đọc từ CSDL.
        ma_nguy_hai: các mã thuộc nhóm nguy hại — quyết định chỉ số an toàn.
        bo: tên bộ ảnh, chỉ để in ra.
    """
    hop_le = [kq for kq in ket_qua if not kq.loi]
    tra_loi = [kq for kq in hop_le if not kq.tu_choi and kq.nhan_du_doan]

    th = TongHop(
        bo=bo,
        so_anh=len(hop_le),
        so_tra_loi=len(tra_loi),
        so_tu_choi=len(hop_le) - len(tra_loi),
        so_loi=len(ket_qua) - len(hop_le),
        so_dung=sum(1 for kq in hop_le if kq.dung),
        theo_nhom=chi_so_theo_nhom(hop_le, nhan_list),
    )

    co_mat = [cs for cs in th.theo_nhom if cs.support > 0]
    th.macro_f1 = sum(cs.f1 for cs in co_mat) / len(co_mat) if co_mat else 0.0

    # --- Chỉ số an toàn: đây là con số in to trên slide ---
    that_su_nguy_hai = [kq for kq in hop_le if kq.nhan_dung in ma_nguy_hai]
    th.so_anh_nguy_hai = len(that_su_nguy_hai)
    if that_su_nguy_hai:
        th.recall_nguy_hai = sum(1 for kq in that_su_nguy_hai if kq.nhan_du_doan in ma_nguy_hai) / len(
            that_su_nguy_hai
        )
        # Từ chối KHÔNG tính vào tử số — từ chối là hành vi an toàn.
        bo_lot = sum(
            1 for kq in that_su_nguy_hai if not kq.tu_choi and kq.nhan_du_doan and kq.nhan_du_doan not in ma_nguy_hai
        )
        th.ty_le_nguy_hai_thanh_thuong = bo_lot / len(that_su_nguy_hai)

    # Chiều ngược lại không nguy hiểm nhưng tốn công đội vệ sinh — vẫn phải báo.
    thuc_su_thuong = [kq for kq in hop_le if kq.nhan_dung not in ma_nguy_hai]
    if thuc_su_thuong:
        bao_dong_nham = sum(1 for kq in thuc_su_thuong if not kq.tu_choi and kq.nhan_du_doan in ma_nguy_hai)
        th.ty_le_thuong_thanh_nguy_hai = bao_dong_nham / len(thuc_su_thuong)

    do_tre = [kq.latency_ms for kq in hop_le]
    th.latency_p50_ms = _phan_vi(do_tre, 50)
    th.latency_p95_ms = _phan_vi(do_tre, 95)
    th.tong_chi_phi_usd = sum(kq.cost_usd for kq in hop_le)
    th.du_gia = all(kq.price_known for kq in hop_le)

    for kq in hop_le:
        if kq.tier:
            th.theo_tier[kq.tier] = th.theo_tier.get(kq.tier, 0) + 1
        if kq.tu_choi and kq.ly_do_tu_choi:
            th.ly_do_tu_choi[kq.ly_do_tu_choi] = th.ly_do_tu_choi.get(kq.ly_do_tu_choi, 0) + 1

    return th


# --- Chỉ số bám nguồn cho câu trả lời chatbot (P86) ------------------------
#
# Hai chỉ số TÁCH RIÊNG thay cho cách đo bám nguồn cũ đã chấm ngược và bị xoá
# hẳn: số hiệu điều luật và nội dung là hai thứ khác nhau, gộp chung một chỉ số
# thì một lỗi trượt làm cả hai cùng sai nghĩa.
#
# * ``khong_bia_dieu_luat`` — mọi cụm "Điều XX" trong câu trả lời phải có thật
#   trong kho tri thức của sản phẩm (biến ``KNOWLEDGE_DOCS`` trong
#   ``src/db/seed_data.py``, nguồn nạp bảng knowledge_chunks mà
#   ``rag.retrieve()`` truy hồi). KHÔNG so với ``ground_truth_context`` của từng
#   ca như chỉ số cũ — chỗ đó khiến chatbot trích ĐÚNG điều luật vẫn bị chấm
#   trượt vì context chỉ chứa nội dung, không chứa số hiệu.
# * ``bam_noi_dung_nguon`` — phần trăm từ có nghĩa của đoạn nguồn được truy hồi
#   xuất hiện lại trong câu trả lời. Phép so khớp tất định: chạy lại ra đúng
#   cùng một số, không dùng model để chấm model.

#: Từ dừng tiếng Việt — hư từ, không mang nghĩa so khớp nội dung. Khai thành
#: hằng số một chỗ để phép đo chạy lại ra cùng kết quả, không rải chuỗi trong hàm.
TU_DUNG_TIENG_VIET: frozenset[str] = frozenset(
    {
        "và", "của", "là", "các", "có", "cho", "được", "trong", "với", "theo",
        "khi", "này", "đó", "từ", "đến", "phải", "không",
    }
)

#: Ngưỡng ĐẠT của tỉ lệ bám nội dung nguồn. ĐÂY LÀ NGƯỠNG ĐẶT TẠM, CHƯA HIỆU
#: CHỈNH TRÊN DỮ LIỆU — chốt trước khi đo để chạy lại ra đúng một con số; sau khi
#: có số đo thực tế phải xem xét hiệu chỉnh và ghi rõ việc đó vào báo cáo.
NGUONG_BAM_NOI_DUNG = 0.30

#: Cụm số hiệu điều luật: "Điều 79" → bắt nguyên cụm; "Điều 26.1" → bắt phần
#: "Điều 26". Cả hai phía (kho tri thức và câu trả lời) đi qua cùng một biểu
#: thức nên cách chuẩn hoá là đối xứng.
_MAU_SO_HIEU_DIEU = re.compile(r"Điều\s+\d+")


def trich_so_hieu_dieu(van_ban: str) -> list[str]:
    """Danh sách cụm số hiệu điều luật ("Điều XX") xuất hiện trong văn bản."""
    return _MAU_SO_HIEU_DIEU.findall(van_ban)


def kiem_tra_khong_bia_dieu_luat(
    ca_tra_loi: str,
    cac_so_hieu_co_that: set[str],
) -> tuple[bool, list[str]] | None:
    """Chỉ số ``khong_bia_dieu_luat``: điều luật được trích ra có thật hay không.

    Args:
        ca_tra_loi: toàn văn câu trả lời của chatbot.
        cac_so_hieu_co_that: tập số hiệu điều luật có thật trong kho tri thức,
            gom một lần từ ``src/db/seed_data.py::KNOWLEDGE_DOCS``.

    Returns:
        ``None`` — câu trả lời không nhắc điều luật nào → không thể vi phạm,
        **không tính** vào tử số của chỉ số này.
        ``(True, [])`` — mọi số hiệu được trích đều có thật.
        ``(False, bia)`` — có ít nhất một số hiệu không có thật; ``bia`` liệt kê
        đúng các số hiệu bịa để in ra ngoài, không được nuốt vào trong.
    """
    trich_dan = trich_so_hieu_dieu(ca_tra_loi)
    if not trich_dan:
        return None
    tap_co_that = {d.lower() for d in cac_so_hieu_co_that}
    bia = sorted({d for d in trich_dan if d.lower() not in tap_co_that})
    return not bia, bia


def _tu_y_nghia(van_ban: str) -> set[str]:
    """Tách từ đã thường hoá, bỏ dấu câu và từ dừng."""
    return {tu for tu in re.findall(r"\w+", van_ban.lower(), re.UNICODE) if tu not in TU_DUNG_TIENG_VIET}


def ti_le_bam_noi_dung_nguon(doan_nguon: str, cau_tra_loi: str) -> float:
    """Chỉ số ``bam_noi_dung_nguon``: câu trả lời có bám nội dung đoạn nguồn không.

    Đếm bao nhiêu **phần trăm** các từ có nghĩa trong đoạn nguồn xuất hiện trong
    câu trả lời. So NỘI DUNG, không so số hiệu: một câu trả lời diễn đạt lại
    bằng từ của mình vẫn được ghi nhận là bám nguồn. Đạt khi tỉ lệ
    ``>= :data:`NGUONG_BAM_NOI_DUNG```.
    """
    tu_nguon = _tu_y_nghia(doan_nguon)
    if not tu_nguon:
        return 0.0
    tu_tra_loi = _tu_y_nghia(cau_tra_loi)
    return sum(1 for tu in tu_nguon if tu in tu_tra_loi) / len(tu_nguon)
