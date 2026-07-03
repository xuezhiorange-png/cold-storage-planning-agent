"""One-shot CLI entry point for the audit outbox dispatcher.

Runs a single dispatch cycle: claim → materialize → publish, then exits.
Follows the project convention of standalone scripts (like bootstrap/demo.py).

Usage:
    python -m cold_storage.bootstrap.dispatch_outbox --worker-id w1 --batch-size 10
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch pending audit outbox events (one-shot).")
    parser.add_argument(
        "--worker-id",
        default="cli-worker",
        help="Unique worker identifier (default: cli-worker)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Max events to claim per cycle (default: 10)",
    )
    parser.add_argument(
        "--lease-seconds",
        type=float,
        default=300.0,
        help="Claim lease duration in seconds (default: 300)",
    )
    args = parser.parse_args()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from cold_storage.config import settings
    from cold_storage.modules.orchestration.application.outbox_dispatcher import (
        AuditOutboxDispatcherApplicationService,
    )
    from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
        claim_events_pg,
        claim_events_sqlite,
        mark_retryable_failure,
        mark_terminal_failure,
        materialize_event,
    )

    database_url = settings.DATABASE_URL
    if not database_url:
        print(json.dumps({"error": "DATABASE_URL not configured"}))
        return 1

    engine = create_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)
    is_pg = "postgresql" in database_url.lower()

    service = AuditOutboxDispatcherApplicationService(
        engine=engine,
        claim_fn_pg=claim_events_pg if is_pg else None,
        claim_fn_sqlite=claim_events_sqlite if not is_pg else None,
        materialize_fn=materialize_event,
        mark_retryable_fn=mark_retryable_failure,
        mark_terminal_fn=mark_terminal_failure,
        session_factory=factory,
        is_pg=is_pg,
    )

    summary = service.run_cycle(
        worker_id=args.worker_id,
        batch_size=args.batch_size,
        lease_seconds=args.lease_seconds,
        now=now,
    )

    result = {
        "claimed": summary.claimed,
        "published": summary.published,
        "retried": summary.retried,
        "failed": summary.failed,
        "skipped": summary.skipped,
        "lost_claims": summary.lost_claims,
        "unhandled_failures": summary.unhandled_failures,
    }
    print(json.dumps(result, indent=2))

    if summary.failed > 0 or summary.unhandled_failures > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
