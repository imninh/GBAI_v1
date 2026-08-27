"""Backfill ``users.building_id`` từ ``unit_id`` — local-first, idempotent.

Gói worker 27/08/2026 — phần 4.3. Mục tiêu duy nhất: với những user ĐÃ có
``unit_id`` mà ``building_id`` còn trống, gán ``building_id = units.building_id``
cho khớp. Chỉ 7 user trong Supabase nằm trong nhóm này; 606 user chưa có nguồn
mapping (không có ``unit_id``) TUYỆT ĐỐI không được động tới.

An toàn:
  * Mặc định CHỈ đọc (``--dry-run``). Muốn ghi phải thêm ``--apply``.
  * ``--apply`` gọi :func:`chan_khong_ghi_csdl_xa` — từ chối ghi CSDL xa trừ khi
    operator đặt ``CHO_PHEP_GHI_DB_XA=1`` (sau backup). Worker KHÔNG tự chạy trên
    Supabase; PM thực thi remote sau backup và duyệt.
  * Không tạo căn hộ giả, không đổi schema, không đụng ``users.address``.

Bốn nhóm kết quả (in ra, không lặng lẽ ghi đè):
  * updated  — gán được building_id từ unit.
  * skipped  — building_id đã khớp với unit, không đổi.
  * orphan   — unit_id trỏ tới căn hộ không tồn tại, bỏ qua.
  * conflict — building_id đã có nhưng khác với unit.building_id, không ghi đè.

SQL thêm foreign key vật lý (cho PM chạy thủ công sau khi backup + dry-run sạch):

    ALTER TABLE users
      ADD CONSTRAINT fk_users_building_id
      FOREIGN KEY (building_id) REFERENCES buildings (id);
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Unit, User
from src.db.session import chan_khong_ghi_csdl_xa, session_scope


def backfill(session: Session, *, dry_run: bool = True) -> dict[str, list[int]]:
    """Quét user có ``unit_id`` và đồng bộ ``building_id``.

    Thuần function — test gọi trực tiếp với một session test DB. Không commit ở
    đây; caller (``session_scope``) quản lý transaction.
    """
    users = session.scalars(select(User).where(User.unit_id.is_not(None))).all()
    ket_qua: dict[str, list[int]] = {"updated": [], "skipped": [], "orphan": [], "conflict": []}

    for u in users:
        unit = session.get(Unit, u.unit_id)
        if unit is None:
            ket_qua["orphan"].append(u.id)
            continue
        if u.building_id == unit.building_id:
            ket_qua["skipped"].append(u.id)
            continue
        if u.building_id is not None and u.building_id != unit.building_id:
            # Đã có toà khác với toà của căn hộ — mâu thuẫn, không ghi đè âm thầm.
            ket_qua["conflict"].append(u.id)
            continue
        if not dry_run:
            u.building_id = unit.building_id
        ket_qua["updated"].append(u.id)

    if not dry_run:
        session.flush()
    return ket_qua


def _in_dry_run() -> dict[str, list[int]]:
    with session_scope() as session:
        return backfill(session, dry_run=True)


def _in_apply() -> dict[str, list[int]]:
    # Chốt chặn CSDL xa — chỉ operator với CHO_PHEP_GHI_DB_XA=1 mới qua được.
    chan_khong_ghi_csdl_xa()
    with session_scope() as session:
        return backfill(session, dry_run=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill users.building_id từ unit_id (mặc định dry-run).")
    parser.add_argument("--apply", action="store_true", help="Ghi thật vào CSDL (vẫn bị chặn trên CSDL xa).")
    parser.add_argument("--json", action="store_true", help="In kết quả dạng JSON.")
    args = parser.parse_args(argv)

    if args.apply:
        ket_qua = _in_apply()
        che_do = "APPLY"
    else:
        ket_qua = _in_dry_run()
        che_do = "DRY-RUN"

    if args.json:
        import json

        print(json.dumps({"mode": che_do, **ket_qua}, ensure_ascii=False))
    else:
        print(f"[{che_do}] Backfill users.building_id <- unit_id")
        print(f"  updated : {len(ket_qua['updated'])}  {ket_qua['updated']}")
        print(f"  skipped : {len(ket_qua['skipped'])}  {ket_qua['skipped']}")
        print(f"  orphan  : {len(ket_qua['orphan'])}  {ket_qua['orphan']}")
        print(f"  conflict: {len(ket_qua['conflict'])}  {ket_qua['conflict']}")
        if not args.apply:
            print("  (dry-run: chưa ghi. Thêm --apply để ghi trên CSDL cục bộ.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
