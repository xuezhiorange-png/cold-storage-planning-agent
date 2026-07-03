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
    from cold_storage.modules.orchestration.application.outbox_errors import (
        OutboxClaimLostError,
        OutboxMaterializationMismatchError,
        OutboxPayloadIntegrityError,
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

    claimed = 0
    published = 0
    retried = 0
    failed = 0
    skipped = 0
    lost_claims = 0

    is_pg = "postgresql" in database_url.lower()

    session = factory()
    try:
        if is_pg:
            events = claim_events_pg(
                session,
                worker_id=args.worker_id,
                batch_size=args.batch_size,
                lease_seconds=args.lease_seconds,
                now=now,
            )
        else:
            events = claim_events_sqlite(
                session,
                worker_id=args.worker_id,
                batch_size=args.batch_size,
                lease_seconds=args.lease_seconds,
                now=now,
            )
        claimed = len(events)
        session.commit()
    except Exception as exc:
        session.rollback()
        print(json.dumps({"error": f"Claim failed: {exc}"}))
        return 1
    finally:
        session.close()

    # Materialize each claimed event in its own short transaction
    for event in events:
        materialized = False
        sess = factory()
        try:
            try:
                materialize_event(
                    sess,
                    claimed=event,
                    worker_id=args.worker_id,
                    claim_token=event.claim_token,
                    now=datetime.now(UTC),
                )
                sess.commit()
                published += 1
                materialized = True
            except OutboxClaimLostError:
                lost_claims += 1
            except (
                OutboxMaterializationMismatchError,
                OutboxPayloadIntegrityError,
            ) as exc:
                try:
                    mark_terminal_failure(
                        sess,
                        event_id=event.outbox_row_id,
                        worker_id=args.worker_id,
                        claim_token=event.claim_token,
                        error=exc,
                        now=datetime.now(UTC),
                    )
                    sess.commit()
                    failed += 1
                except Exception:
                    sess.rollback()
                    failed += 1
            except Exception as exc:
                try:
                    mark_retryable_failure(
                        sess,
                        event_id=event.outbox_row_id,
                        worker_id=args.worker_id,
                        claim_token=event.claim_token,
                        error=exc,
                        now=datetime.now(UTC),
                    )
                    sess.commit()
                    retried += 1
                except Exception:
                    sess.rollback()
                    retried += 1
        finally:
            if not materialized:
                sess.close()

    summary = {
        "claimed": claimed,
        "published": published,
        "retried": retried,
        "failed": failed,
        "skipped": skipped,
        "lost_claims": lost_claims,
    }
    print(json.dumps(summary, indent=2))

    # Exit 0 if no unhandled failures
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
