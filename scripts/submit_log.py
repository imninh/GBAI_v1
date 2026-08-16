#!/usr/bin/env python3
"""
Submit .ai-log/session.jsonl to grading server.
Called by git pre-push hook or manually.

After a successful submit, the live log is rotated:
  - Moved into .ai-log/archive/YYYY-MM-DD.jsonl (appended, never overwritten)
  - The live session.jsonl is recreated empty by the next hook write

If the POST fails, the pending file is restored so nothing is lost.
"""
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def _nap_env() -> None:
    """Load .env from the repo root, with or without python-dotenv installed.

    The git pre-push hook runs this through `scripts/_pyrun.sh`, which picks
    whatever `python3`/`python` Git Bash resolves first. On Windows that is
    often the Microsoft Store stub — a different interpreter from the dev one,
    with none of the project's packages. `python-dotenv` is missing there, so
    the old `except ImportError: pass` silently skipped .env and every push
    printed "AI_LOG_SERVER not set" while logs piled up locally.

    The fallback parser only needs to understand what a .env actually holds:
    `KEY=value` lines, `#` comments, and optional surrounding quotes. Values
    already present in the environment win — never override a real setting.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        return

    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_nap_env()

SERVER_URL = os.environ.get("AI_LOG_SERVER", "")
API_KEY = os.environ.get("AI_LOG_API_KEY", "")
LOG_DIR = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
LOG_FILE = LOG_DIR / "session.jsonl"
ARCHIVE_DIR = LOG_DIR / "archive"

# Match server-side MAX_BATCH_ENTRIES so we never get a 422.
# If the local file has more than this, we submit the oldest BATCH_LIMIT
# and leave the rest for the next push.
BATCH_LIMIT = 100


def _lam_sach(entry: dict) -> dict:
    """Strip NUL from every string field.

    A single NUL (U+0000) makes the grading server answer **500**, not 4xx —
    PostgreSQL text columns cannot hold it. Measured 2026-08-11: records with
    \\r or ANSI colour codes are accepted (202); only \\x00 breaks it. Since
    every retry resends the same head of the queue, one poisoned record jams
    the whole backlog forever.

    Usual source: PowerShell output captured as UTF-16LE, so every other byte
    is NUL ("W\\x00i\\x00n\\x00d\\x00..."). Dropping the NULs restores the text.
    """
    return {
        k: (v.replace("\x00", "") if isinstance(v, str) and "\x00" in v else v)
        for k, v in entry.items()
    }


def _archive_lines(lines: list[str]) -> None:
    """Append the lines we actually submitted to today's archive.

    Only the submitted batch — never the whole pending file. Archiving the
    leftover too meant every deferred entry got written again on the next run:
    measured 2026-08-11, one day's archive held 8.749 lines of which 7.475 were
    duplicates (7,3 MB for 1,0 MB of real data).
    """
    if not lines:
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    archive_file = ARCHIVE_DIR / f"{today}.jsonl"
    with open(archive_file, "a", encoding="utf-8") as dst:
        dst.writelines(lines)


def _archive(pending: Path) -> None:
    """Append pending file to today's archive. Never overwrites existing data."""
    if not pending.exists() or pending.stat().st_size == 0:
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    archive_file = ARCHIVE_DIR / f"{today}.jsonl"
    with open(pending, "rb") as src, open(archive_file, "ab") as dst:
        shutil.copyfileobj(src, dst)


def _restore_pending(pending: Path) -> None:
    """Failure path: put pending back at LOG_FILE so the next push retries.
    If hook wrote new entries to LOG_FILE in the meantime, prepend pending."""
    if not pending.exists():
        return
    if LOG_FILE.exists():
        # Concat: pending (older) + LOG_FILE (newer) → LOG_FILE
        tmp = LOG_FILE.with_suffix(".merge.jsonl")
        with open(tmp, "wb") as out:
            with open(pending, "rb") as a:
                shutil.copyfileobj(a, out)
            with open(LOG_FILE, "rb") as b:
                shutil.copyfileobj(b, out)
        os.replace(tmp, LOG_FILE)
        pending.unlink()
    else:
        pending.rename(LOG_FILE)


def main():
    if not SERVER_URL:
        print("[ai-log] AI_LOG_SERVER not set — skipping submission.", file=sys.stderr)
        sys.exit(0)

    if not LOG_FILE.exists() or LOG_FILE.stat().st_size == 0:
        print("[ai-log] No logs to submit.", file=sys.stderr)
        sys.exit(0)

    # Atomic rename closes the race window: hook writes that arrive after this
    # land in a fresh LOG_FILE, not in the batch we're about to POST.
    pending = LOG_FILE.with_name(f"session.pending.{int(time.time())}.jsonl")
    try:
        LOG_FILE.rename(pending)
    except FileNotFoundError:
        print("[ai-log] No logs to submit.", file=sys.stderr)
        sys.exit(0)

    entries = []
    leftover_lines = []
    bad_lines = []
    with open(pending, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if len(entries) >= BATCH_LIMIT:
                leftover_lines.append(line)
                continue
            try:
                entries.append(_lam_sach(json.loads(stripped)))
            except json.JSONDecodeError:
                bad_lines.append(line)  # keep it: archived, never sent

    if not entries:
        # Nothing to send; archive whatever was there (probably junk) and bail.
        _archive(pending)
        pending.unlink()
        print("[ai-log] No valid entries to submit.", file=sys.stderr)
        sys.exit(0)

    # Archive exactly what we send, so the archive and the server agree.
    submitted_lines = [json.dumps(e, ensure_ascii=False) + "\n" for e in entries]

    payload = json.dumps({"entries": entries}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(
        SERVER_URL,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"[ai-log] Submitted {len(entries)} entries → {resp.status}", file=sys.stderr)
    except urllib.error.URLError as e:
        # Failure: restore the whole pending (including leftover) for next push.
        _restore_pending(pending)
        print(f"[ai-log] Submit failed: {e} — logs kept locally.", file=sys.stderr)
        sys.exit(0)  # Don't block push on server error
    except BaseException:
        # Ctrl+C lands here. `KeyboardInterrupt` is NOT a `URLError`, so without
        # this the pending file is orphaned and `session.jsonl` disappears —
        # happened for real on 2026-08-11. Put the logs back, then re-raise.
        _restore_pending(pending)
        print("[ai-log] Interrupted — logs restored, nothing lost.", file=sys.stderr)
        raise

    # Success: archive exactly the batch we submitted (plus any unparseable
    # lines, so nothing silently disappears) and leave the rest for next time.
    _archive_lines(submitted_lines + bad_lines)
    pending.unlink()

    if leftover_lines:
        # More than BATCH_LIMIT entries existed; put the rest back so the
        # next push picks them up.
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.writelines(leftover_lines)
        print(
            f"[ai-log] {len(leftover_lines)} entries deferred to next push.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
