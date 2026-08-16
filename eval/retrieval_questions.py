"""Bộ câu hỏi có đáp án để đo chất lượng truy hồi của RAG (PLO 3).

Câu hỏi viết theo **cách cư dân thật sự gõ**, không chép lại chữ trong văn bản
quy định — nếu chép lại thì BM25 luôn thắng và phép đo mất hết ý nghĩa. Đó cũng
chính là chỗ embedding phải chứng minh mình có ích.

``dung``: các mục được coi là **đúng** cho câu hỏi đó. Nhiều câu có nhiều đáp án
hợp lệ — hỏi về pin thì cả mục "Rác nguy hại" của nội quy toà lẫn mục "Pin và ắc
quy" của danh mục nguy hại đều trả lời được.

Bộ này còn nhỏ (18 câu). ``CLAUDE.md`` mục 7 đặt mục tiêu ~60 câu; muốn con số
đủ chắc để đưa lên slide thì phải viết tiếp cho đủ.
"""

from __future__ import annotations

# (câu hỏi, mã toà, các mục được tính là đúng)
CAU_HOI_TRUY_HOI: list[tuple[str, str, set[str]]] = [
    # --- Rác nguy hại: nhóm quan trọng nhất, sai ở đây là sai nguy hiểm ---
    ("pin cũ bỏ ở đâu", "S1", {"Pin và ắc quy", "Mục 4.4 — Rác nguy hại"}),
    ("pin tiểu AA đã hết", "S1", {"Pin và ắc quy", "Mục 4.4 — Rác nguy hại"}),
    ("cục sạc dự phòng hỏng vứt thế nào", "S1", {"Pin và ắc quy", "Mục 4.4 — Rác nguy hại"}),
    ("bóng đèn hỏng vứt thế nào", "S1", {"Bóng đèn huỳnh quang", "Mục 4.4 — Rác nguy hại"}),
    ("thuốc quá hạn sử dụng đổ đi đâu", "S1", {"Thuốc hết hạn", "Mục 4.4 — Rác nguy hại"}),
    ("kim tiêm dùng rồi bỏ đâu", "S1", {"Vật sắc nhọn y tế", "Mục 4.4 — Rác nguy hại"}),
    # --- Đồ cồng kềnh ---
    ("đồ đạc to quá thì làm sao", "S1", {"Mục 4.5 — Đồ cồng kềnh"}),
    ("bỏ tủ quần áo cũ", "S1", {"Mục 4.5 — Đồ cồng kềnh"}),
    ("vứt đệm giường hỏng", "S1", {"Mục 4.5 — Đồ cồng kềnh"}),
    # --- Tái chế ---
    ("hộp sữa giấy có tái chế được không", "S1", {"Mục 4.2 — Rác tái chế"}),
    ("chai nhựa bỏ thùng nào", "S1", {"Mục 4.2 — Rác tái chế"}),
    ("vỏ lon bia để đâu", "S1", {"Mục 4.2 — Rác tái chế"}),
    # --- Rác thực phẩm ---
    ("cơm thừa canh cặn đổ đâu", "S1", {"Mục 4.3 — Rác thực phẩm"}),
    ("rác nhà bếp có phải để ráo nước không", "S1", {"Mục 4.3 — Rác thực phẩm"}),
    # --- Nguyên tắc chung và nền pháp lý ---
    ("nhà mình phải chia rác ra mấy loại", "S1", {"Mục 4.1 — Nguyên tắc chung"}),
    ("không phân loại rác có bị phạt tiền không", "S1", {"Diễn giải — chế tài với hành vi không phân loại"}),
    # --- Toà S2: kiểm luôn việc lọc theo toà ---
    ("phòng rác tầng nhà mình đặt được mấy thùng", "S2", {"Mục 3.2 — Điểm tập kết"}),
    ("toà mình khác toà S1 chỗ nào", "S2", {"Mục 3.1 — Nhóm rác và thùng chứa"}),
]
