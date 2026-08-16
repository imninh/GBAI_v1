#!/usr/bin/env python3
"""Chuẩn hoá log thô của OpenCode sang khuôn chung để nộp cho ban tổ chức.

Đường đi của một dòng log:

    OpenCode  ──plugin .opencode/plugins/ai-log.js──►  .ai-log/opencode-raw.jsonl
                                                              │
                                        script này (chạy ở pre-push)
                                                              ▼
                                                    .ai-log/session.jsonl
                                                              │
                                                    scripts/submit_log.py
                                                              ▼
                                                      máy chủ của BTC

Vì sao tách làm hai chặng thay vì để plugin ghi thẳng khuôn cuối: plugin chạy
trong tiến trình của OpenCode, nên nó phải rẻ và không được phép hỏng. Mọi việc
cần gọi git (tên repo, nhánh, commit, email) đều dồn về đây — chạy một lần lúc
push thay vì chạy lại sau mỗi lần gõ phím.

Cách chạy:
    python scripts/log_opencode.py            # in ra đã nạp bao nhiêu dòng
    python scripts/log_opencode.py --auto     # im lặng, dùng trong git hook
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7))

# Bản thô đã cắt sẵn theo giới hạn của plugin; ở đây chỉ chặn thêm một lần nữa
# phòng khi ai đó sửa plugin mà quên.
MAX_PROMPT = 1000
MAX_RESPONSE = 500

# Sự kiện chỉ có nghĩa lúc gỡ lỗi, không nộp lên máy chủ.
SKIPPED_EVENTS = frozenset({"plugin.loaded"})


def lam_sach(gia_tri: object) -> object:
    """Gỡ ký tự NUL khỏi chuỗi. Kiểu khác trả về nguyên vẹn.

    Vì sao chỉ NUL mà không phải mọi ký tự điều khiển: đo ngày 11/08 trên máy chủ
    của BTC, bản ghi chứa ``\\r`` hay mã màu ANSI đều được nhận (202); chỉ ``\\x00``
    làm nó trả **500**. Cột text của PostgreSQL không lưu được NUL, và endpoint
    ném lỗi thay vì từ chối lịch sự — nên **một** bản ghi dính là cả hàng đợi kẹt
    vô thời hạn, lô nào cũng chứa nó, lô nào cũng 500.

    Nguồn NUL thường gặp: output PowerShell bị bắt ở dạng UTF-16LE rồi lưu như
    text, nên cứ một byte chữ lại một byte NUL — ``"W\\x00i\\x00n\\x00d\\x00..."``.
    Gỡ NUL đi thì chuỗi đọc lại đúng thành ``"Windows PowerShell..."``.
    """
    if isinstance(gia_tri, str) and "\x00" in gia_tri:
        return gia_tri.replace("\x00", "")
    return gia_tri


def git(args: list[str], cwd: Path) -> str:
    """Chạy một lệnh git, trả về chuỗi rỗng nếu lệnh hỏng."""
    try:
        out = subprocess.check_output(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return ""
    return out.strip()


def repo_name(origin: str) -> str:
    """Rút tên repo từ URL remote."""
    name = origin.rstrip("/").split("/")[-1]
    return name[:-4] if name.endswith(".git") else name


def read_new_lines(raw_file: Path, offset_file: Path) -> tuple[list[str], int]:
    """Đọc phần chưa xử lý của file thô, trả về (các dòng, vị trí mới).

    Vị trí đọc dở lưu ở `offset_file` để chạy lại nhiều lần không nộp trùng.
    Nếu file thô ngắn hơn vị trí đã lưu (bị xoá hoặc xoay vòng) thì đọc lại từ
    đầu — thà trùng còn hơn mất.
    """
    if not raw_file.exists():
        return [], 0

    offset = 0
    if offset_file.exists():
        try:
            offset = int(offset_file.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            offset = 0

    size = raw_file.stat().st_size
    if offset > size:
        offset = 0

    with open(raw_file, "rb") as f:
        f.seek(offset)
        chunk = f.read()
        new_offset = f.tell()

    text = chunk.decode("utf-8", errors="replace")
    return [line for line in text.splitlines() if line.strip()], new_offset


def bo_ban_ghi_trung(raws: list[dict]) -> list[dict]:
    """Loại các bản ghi trùng do OpenCode bắn hook hai lần.

    Đo 05/08: `chat.message` và `tool.execute.after` được gọi hai lần cho cùng
    một sự việc, cách nhau khoảng 1 ms và cùng `call_id`. Plugin nay đã chặn tại
    nguồn, nhưng hàm này vẫn giữ lại làm lưới đỡ — vừa dọn được những dòng đã
    trót ghi trước khi plugin được sửa, vừa đỡ nếu OpenCode đổi hành vi.

    Chỉ coi là trùng khi hai bản ghi giống nhau VÀ cách nhau dưới 3 giây, để một
    prompt gõ lại thật sự sau đó vẫn được giữ.
    """
    ket_qua: list[dict] = []
    da_gap: dict[str, datetime] = {}

    for raw in raws:
        event = raw.get("event", "")
        khoa = "|".join(
            [
                event,
                str(raw.get("session_id", "")),
                str(raw.get("call_id", "")),
                str(raw.get("message_id", "")),
                str(raw.get("tool_name", "")),
                str(raw.get("prompt", ""))[:200],
            ]
        )
        try:
            moc = datetime.fromisoformat(str(raw.get("ts", "")).replace("Z", "+00:00"))
        except ValueError:
            ket_qua.append(raw)
            continue

        truoc = da_gap.get(khoa)
        if truoc is not None and abs((moc - truoc).total_seconds()) < 3:
            continue
        da_gap[khoa] = moc
        ket_qua.append(raw)

    return ket_qua


def to_entry(raw: dict, meta: dict) -> dict | None:
    """Đổi một bản ghi thô thành một bản ghi đúng khuôn của `log_hook.py`."""
    event = raw.get("event", "")
    if event in SKIPPED_EVENTS:
        return None

    entry = {
        "ts": raw.get("ts") or datetime.now(VN_TZ).isoformat(),
        "tool": "opencode",
        "event": event,
        "session_id": raw.get("session_id", ""),
        "model": raw.get("model", ""),
        "repo": meta["repo"],
        "branch": meta["branch"],
        "commit": meta["commit"],
        "student": meta["student"],
    }

    if event == "chat.message":
        entry["prompt"] = str(lam_sach(raw.get("prompt", "")))[:MAX_PROMPT]
        entry["agent"] = raw.get("agent", "")
    elif event == "tool.execute.after":
        entry["tool_name"] = raw.get("tool_name", "")
        entry["tool_input"] = lam_sach(raw.get("tool_input", ""))
        # Gỡ NUL TRƯỚC khi cắt: chuỗi UTF-16LE lọt vào có một nửa là byte rỗng,
        # cắt trước thì 500 ký tự chỉ còn 250 ký tự thật.
        entry["tool_response"] = str(lam_sach(raw.get("tool_response", "")))[:MAX_RESPONSE]
    elif event == "message.completed":
        # Số liệu chi phí / độ trễ: vừa là thứ BTC yêu cầu theo dõi, vừa dùng
        # được cho trang Vận hành của chính sản phẩm.
        entry["provider"] = raw.get("provider", "")
        entry["cost"] = raw.get("cost", 0)
        entry["tokens"] = raw.get("tokens")
        entry["latency_ms"] = raw.get("latency_ms")

    return entry


def fill_missing_models(entries: list[dict]) -> None:
    """Điền tên model cho các prompt.

    Hook `chat.message` của OpenCode không mang tên model (đo ngày 05/08: cả
    `provider` lẫn `model` đều rỗng), nên lấy tên model từ câu trả lời kế tiếp
    của cùng phiên. Không tìm thấy thì để trống, không đoán.
    """
    latest_by_session: dict[str, str] = {}
    for entry in reversed(entries):
        session = entry.get("session_id", "")
        if not session:
            continue
        if entry["event"] == "message.completed" and entry.get("model"):
            latest_by_session[session] = entry["model"]
        elif entry["event"] == "chat.message" and not entry.get("model"):
            entry["model"] = latest_by_session.get(session, "")


def main() -> None:
    quiet = "--auto" in sys.argv[1:]

    def say(message: str) -> None:
        if not quiet:
            print(message)

    root = Path.cwd()
    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    raw_file = log_dir / "opencode-raw.jsonl"
    offset_file = log_dir / ".opencode-raw.offset"
    session_file = log_dir / "session.jsonl"

    lines, new_offset = read_new_lines(raw_file, offset_file)
    if not lines:
        say("[ai-log] OpenCode: không có dòng mới.")
        return

    origin = git(["remote", "get-url", "origin"], root)
    if not origin:
        # Cùng quy ước với `log_hook.py`: không có remote thì bản ghi không gắn
        # được vào nhóm nào, giữ lại chỉ làm nghẽn hàng đợi.
        say("[ai-log] OpenCode: thư mục này không có remote origin — bỏ qua.")
        return

    meta = {
        "repo": repo_name(origin),
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], root),
        "commit": git(["rev-parse", "--short", "HEAD"], root),
        "student": git(["config", "user.email"], root),
    }

    raws: list[dict] = []
    for line in lines:
        try:
            raws.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    so_truoc = len(raws)
    raws = bo_ban_ghi_trung(raws)
    if len(raws) < so_truoc:
        say(f"[ai-log] OpenCode: bỏ {so_truoc - len(raws)} bản ghi trùng.")

    entries: list[dict] = []
    for raw in raws:
        entry = to_entry(raw, meta)
        if entry is not None:
            entries.append(entry)

    fill_missing_models(entries)

    if entries:
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(session_file, "a", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    offset_file.write_text(str(new_offset), encoding="utf-8")

    prompts = sum(1 for e in entries if e["event"] == "chat.message")
    say(f"[ai-log] OpenCode: nạp {len(entries)} bản ghi ({prompts} prompt) → {session_file}")


if __name__ == "__main__":
    main()
