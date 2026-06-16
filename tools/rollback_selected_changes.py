#!/usr/bin/env python3
"""
Selective rollback utility for AEF Crop Intelligence.

Usage examples:
    python tools/rollback_selected_changes.py --list
    python tools/rollback_selected_changes.py --files src/models/simulation_engine.py pages/main/report.py
    python tools/rollback_selected_changes.py --all

The script restores selected files from backups/pre_refactor_snapshot by default.
It never deletes files unless --delete-new-files is explicitly provided.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_backup(root: Path) -> Path:
    return root / "backups" / "pre_refactor_snapshot"


def iter_backup_files(backup: Path):
    for path in backup.rglob("*"):
        if path.is_file():
            yield path.relative_to(backup)


def restore_file(root: Path, backup: Path, rel: Path) -> str:
    src = backup / rel
    dst = root / rel
    if not src.exists():
        return f"SKIP missing in backup: {rel}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f"RESTORED {rel}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore selected AEF files from the pre-refactor backup.")
    parser.add_argument("--backup", type=Path, default=None, help="Backup folder. Defaults to backups/pre_refactor_snapshot.")
    parser.add_argument("--files", nargs="*", default=None, help="Relative files to restore.")
    parser.add_argument("--all", action="store_true", help="Restore every file present in the backup.")
    parser.add_argument("--list", action="store_true", help="List files available in the backup.")
    parser.add_argument("--delete-new-files", action="store_true", help="Delete files not present in backup. Use only after review.")
    args = parser.parse_args()

    root = project_root()
    backup = args.backup or default_backup(root)
    if not backup.exists():
        raise SystemExit(f"Backup not found: {backup}")

    files = sorted(iter_backup_files(backup))
    if args.list:
        for rel in files:
            print(rel.as_posix())
        return 0

    if args.all:
        targets = files
    elif args.files:
        targets = [Path(f) for f in args.files]
    else:
        raise SystemExit("Choose --list, --all, or --files.")

    for rel in targets:
        print(restore_file(root, backup, rel))

    if args.delete_new_files:
        backup_set = {p.as_posix() for p in files}
        for path in root.rglob("*"):
            if not path.is_file() or "backups" in path.parts or ".git" in path.parts:
                continue
            rel = path.relative_to(root).as_posix()
            if rel not in backup_set and not rel.startswith("tools/rollback_selected_changes.py"):
                path.unlink()
                print(f"DELETED new file {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
