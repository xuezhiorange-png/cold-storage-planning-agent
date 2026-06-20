from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True)
class AuditEvent:
    actor: str
    action: str
    entity_type: str
    entity_id: str
    before_snapshot: dict[str, object]
    after_snapshot: dict[str, object]
    metadata: dict[str, object]
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
