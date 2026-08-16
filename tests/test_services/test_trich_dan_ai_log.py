"""Test script trích dẫn AI log (deliverable #4) — không đọc .ai-log/ thật.

Dựng file .jsonl giả bằng ``tmp_path`` vì `.ai-log/` không có trong repo của
người khác; test đọc dữ liệu thật là test không lặp lại được. Chốt chặn chính
nằm ở test cuối: nhét đủ cả bốn loại bí mật rồi khẳng định không cái nào sót
trong đầu ra.
"""

from __future__ import annotations

from pathlib import Path

from scripts.trich_dan_ai_log import che_bi_mat, chon_trace, doc_trace, dung_bao_cao


def test_che_duoc_khoa_dang_sk() -> None:
    ket_qua = che_bi_mat("dung khoa sk-abc1234567890 de goi API")

    assert "sk-abc1234567890" not in ket_qua
    assert "dung khoa" in ket_qua, "Ngữ cảnh xung quanh phải còn nguyên"


def test_che_duoc_khoa_dang_gan_bang() -> None:
    ket_qua = che_bi_mat("GEMINI_API_KEY=abcxyz123456")

    assert "GEMINI_API_KEY" in ket_qua, "Tên biến phải còn nguyên để đọc còn hiểu"
    assert "abcxyz123456" not in ket_qua


def test_che_duoc_chuoi_ket_noi_postgres() -> None:
    ket_qua = che_bi_mat("postgresql://user:mat-khau@host:5432/db")

    assert "user:mat-khau@host" not in ket_qua
    assert "postgresql://«đã che»" in ket_qua, "Phần sau // phải bị che, tiền tố còn lại cho dễ đọc"


def test_che_duoc_duong_dan_ca_nhan() -> None:
    ket_qua = che_bi_mat("log o C:\\Users\\Ninh\\Desktop\\du-an\\file.py")

    assert "C:\\Users\\Ninh" not in ket_qua
    assert "C:\\Users\\<user>" in ket_qua, "Tên người dùng bị che, phần còn lại giữ nguyên"


def test_giu_lai_tai_khoan_demo() -> None:
    ket_qua = che_bi_mat("login bang resident@demo.vn, sdt 0901000001")

    assert "resident@demo.vn" in ket_qua, "Email demo đã công bố trong README không được che"
    assert "0901000001" in ket_qua, "Số điện thoại demo đã công bố không được che"

    ket_qua_khac = che_bi_mat("lien he tranninh41225@gmail.com")
    assert "tranninh41225@gmail.com" not in ket_qua_khac, "Email cá nhân phải bị che"


def test_dong_json_hong_thi_bo_qua_khong_chet(tmp_path: Path) -> None:
    tep = tmp_path / "a.jsonl"
    tep.write_text(
        '{"ts": "2026-08-01T10:00:00+07:00", "tool": "opencode", "event": "chat.message", "prompt": "chao"}\n'
        "dong nay khong phai json\n"
        '{"ts": "2026-08-01T11:00:00+07:00", "tool": "opencode", "event": "chat.message", "prompt": "xin chao"}\n',
        encoding="utf-8",
    )

    cac_dong = doc_trace(tep)

    assert len(cac_dong) == 2, "Dòng hỏng phải bị bỏ qua, không làm chết cả file"


def test_chon_trace_trai_deu_theo_ngay() -> None:
    cac_dong = []
    for ngay in ("2026-08-01", "2026-08-02", "2026-08-03"):
        for gio in range(3):
            cac_dong.append(
                {
                    "ts": f"{ngay}T{8 + gio}:00:00+07:00",
                    "tool": "opencode",
                    "event": "chat.message",
                    "prompt": f"{ngay} {gio}",
                }
            )

    ket_qua = chon_trace(cac_dong, 3)

    cac_ngay = sorted({dong["ts"][:10] for dong in ket_qua})
    assert cac_ngay == ["2026-08-01", "2026-08-02", "2026-08-03"], (
        "Xin 3 trace trên 3 ngày thì mỗi ngày phải có một cái"
    )


def test_bao_cao_co_khoi_giai_thich_o_dau() -> None:
    bao_cao = dung_bao_cao(
        [{"ts": "2026-08-01T10:00:00+07:00", "tool": "opencode", "event": "chat.message", "prompt": "chao"}],
        tong_dong=10,
    )

    assert "bản trích dẫn" in bao_cao.lower(), "Báo cáo phải nói rõ đây là bản trích dẫn"
    assert "log thô" in bao_cao.lower(), "Báo cáo phải nói rõ log thô không được đẩy lên repo"


def test_khong_con_bi_mat_nao_sot_lai() -> None:
    """Chốt chặn chính: nhét đủ cả bốn loại bí mật, chạy hết đường ống, không cái nào sót."""
    cac_bi_mat = [
        "sk-abcdef1234567890",
        "GEMINI_API_KEY=abcxyz123456",
        "postgresql://user:mat-khau@host:5432/db",
        "C:\\Users\\Ninh\\Desktop\\du-an\\file.py",
        "tranninh41225@gmail.com",
        "0912345678",
    ]
    trace = {
        "ts": "2026-08-01T10:00:00+07:00",
        "tool": "opencode",
        "event": "tool.execute.after",
        "tool_name": "write",
        "prompt": " ".join(cac_bi_mat),
        "tool_input": {"file_path": cac_bi_mat[3], "content": cac_bi_mat[0]},
        "tool_response": "xong",
        "session_id": "phien-1",
    }

    bao_cao = dung_bao_cao([trace], tong_dong=1)

    for bi_mat in cac_bi_mat:
        assert bi_mat not in bao_cao, f"Bí mật sót lại trong đầu ra: {bi_mat}"
