from __future__ import annotations

import pytest

from cold_storage.recovery import restore_runner
from cold_storage.recovery.backup_bundle import RecoveryError


def test_restore_receipt_rejects_url_and_secret_fields() -> None:
    fields = {key: "value" for key in restore_runner.RESTORE_RECEIPT_FIELDS}
    fields["verification_result"] = "PASS"
    fields["target_environment_id"] = "postgresql://user:password@example.invalid/db"
    with pytest.raises(RecoveryError, match="RESTORE_RECEIPT_INVALID"):
        restore_runner._validate_receipt(fields)


def test_restore_receipt_requires_closed_schema() -> None:
    fields = {key: "value" for key in restore_runner.RESTORE_RECEIPT_FIELDS}
    fields["verification_result"] = "PASS"
    fields["unexpected"] = "value"
    with pytest.raises(RecoveryError, match="RESTORE_RECEIPT_INVALID"):
        restore_runner._validate_receipt(fields)
