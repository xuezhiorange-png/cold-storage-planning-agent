from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


def new_id() -> str:
    return str(uuid4())


@dataclass
class ProjectVersion:
    project_id: str
    version_number: int
    change_summary: str
    status: str = "draft"
    input_snapshot: dict[str, object] = field(default_factory=dict)
    created_by: str = "system"
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_locked(self) -> bool:
        return self.status == "approved"


@dataclass
class Project:
    code: str
    name: str
    location: str
    product_category: str
    status: str = "draft"
    current_version_number: int = 0
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    versions: list[ProjectVersion] = field(default_factory=list)


@dataclass
class SaveInputsResult:
    success: bool
    error_code: str | None = None
    version: ProjectVersion | None = None
