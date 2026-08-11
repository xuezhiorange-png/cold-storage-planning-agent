"""Canonical operator CLI for the Slice 6 data recovery foundation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from cold_storage.recovery.backup_bundle import RecoveryError, create_backup
from cold_storage.recovery.restore_runner import restore_isolated, verify_restore


def _add_target_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target-environment-id")
    parser.add_argument("--target-database-environment-id")
    parser.add_argument("--target-artifact-environment-id")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cold_storage.recovery.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup")
    backup.add_argument("--execute-backup", action="store_true")
    backup.add_argument("--backup-root", required=True, type=Path)
    backup.add_argument("--retention-days", type=int, default=30)
    backup.add_argument("--source-environment-id")
    backup.add_argument("--source-database-environment-id")
    backup.add_argument("--source-artifact-environment-id")
    backup.add_argument("--source-artifact-root", type=Path)

    restore = subparsers.add_parser("restore-isolated")
    restore.add_argument("--execute-restore", action="store_true")
    restore.add_argument("--backup-bundle", required=True, type=Path)
    restore.add_argument("--output-dir", required=True, type=Path)
    _add_target_options(restore)

    verify = subparsers.add_parser("verify-restore")
    verify.add_argument("--backup-bundle", required=True, type=Path)
    verify.add_argument("--receipt", required=True, type=Path)
    _add_target_options(verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "backup":
            bundle = create_backup(
                backup_root=args.backup_root,
                execute_backup=args.execute_backup,
                retention_days=args.retention_days,
                source_environment_id=args.source_environment_id,
                source_database_environment_id=args.source_database_environment_id,
                source_artifact_environment_id=args.source_artifact_environment_id,
                source_artifact_root=args.source_artifact_root,
            )
            print("BACKUP_RESULT=PASS")
            print(f"BACKUP_BUNDLE={bundle}")
            return 0
        if args.command == "restore-isolated":
            receipt = restore_isolated(
                bundle_root=args.backup_bundle,
                output_dir=args.output_dir,
                execute_restore=args.execute_restore,
                target_environment_id=args.target_environment_id,
                target_database_environment_id=args.target_database_environment_id,
                target_artifact_environment_id=args.target_artifact_environment_id,
            )
            print("RESTORE_RESULT=PASS")
            print(f"RESTORE_RECEIPT={receipt}")
            return 0
        receipt = verify_restore(
            bundle_root=args.backup_bundle,
            receipt_path=args.receipt,
            target_environment_id=args.target_environment_id,
            target_database_environment_id=args.target_database_environment_id,
            target_artifact_environment_id=args.target_artifact_environment_id,
        )
        print("VERIFY_RESTORE_RESULT=PASS")
        print(f"RESTORE_RECEIPT={receipt}")
        return 0
    except RecoveryError as exc:
        print(f"ERROR_CODE={exc.code}")
        if exc.detail:
            print(f"ERROR_DETAIL={exc.detail}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
