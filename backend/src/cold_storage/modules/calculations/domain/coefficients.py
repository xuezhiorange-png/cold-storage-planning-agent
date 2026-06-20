from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class CalculationCoefficient:
    code: str
    name: str
    value: float
    unit: str
    category: str
    source_type: str
    source_reference: str
    version: str
    validity_status: str
    approval_status: str
    requires_review: bool
    applicable_product: str | None = None
    applicable_room_type: str | None = None
    effective_date: date | None = None
    expires_at: date | None = None
    notes: str = ""

    def to_reference(self) -> dict[str, Any]:
        data = asdict(self)
        data["effective_date"] = self.effective_date.isoformat() if self.effective_date else None
        data["expires_at"] = self.expires_at.isoformat() if self.expires_at else None
        return data

    @property
    def is_approved(self) -> bool:
        return self.approval_status == "approved" and self.validity_status == "approved"
