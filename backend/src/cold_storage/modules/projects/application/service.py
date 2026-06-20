from cold_storage.modules.audit.domain import AuditEvent
from cold_storage.modules.calculations.domain.result import CalculationResult
from cold_storage.modules.projects.domain.models import Project, ProjectVersion, SaveInputsResult


class ProjectService:
    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}
        self.audit_events: list[AuditEvent] = []
        self.calculation_runs: list[dict[str, object]] = []

    def create_project(self, name: str, location: str, product_category: str) -> Project:
        code = f"P{len(self.projects) + 1:04d}"
        project = Project(
            code=code,
            name=name,
            location=location,
            product_category=product_category,
        )
        self.projects[project.id] = project
        self.audit_events.append(
            AuditEvent(
                actor="system",
                action="create_project",
                entity_type="Project",
                entity_id=project.id,
                before_snapshot={},
                after_snapshot={"name": name, "location": location},
                metadata={"project_id": project.id},
            )
        )
        return project

    def list_projects(self) -> list[Project]:
        return list(self.projects.values())

    def get_project(self, project_id: str) -> Project:
        return self.projects[project_id]

    def create_version(
        self, project_id: str, change_summary: str, created_by: str = "system"
    ) -> ProjectVersion:
        project = self.get_project(project_id)
        version = ProjectVersion(
            project_id=project_id,
            version_number=project.current_version_number + 1,
            change_summary=change_summary,
            created_by=created_by,
        )
        project.current_version_number = version.version_number
        project.versions.append(version)
        self.audit_events.append(
            AuditEvent(
                actor=created_by,
                action="create_project_version",
                entity_type="ProjectVersion",
                entity_id=version.id,
                before_snapshot={},
                after_snapshot={"version_number": version.version_number},
                metadata={"project_id": project_id},
            )
        )
        return version

    def get_version(self, project_id: str, version_number: int) -> ProjectVersion:
        project = self.get_project(project_id)
        for version in project.versions:
            if version.version_number == version_number:
                return version
        raise KeyError(version_number)

    def list_versions(self, project_id: str) -> list[ProjectVersion]:
        return self.get_project(project_id).versions

    def approve_version(self, project_id: str, version_number: int) -> ProjectVersion:
        version = self.get_version(project_id, version_number)
        before: dict[str, object] = {"status": version.status}
        version.status = "approved"
        self.audit_events.append(
            AuditEvent(
                actor="system",
                action="approve_project_version",
                entity_type="ProjectVersion",
                entity_id=version.id,
                before_snapshot=before,
                after_snapshot={"status": version.status},
                metadata={"project_id": project_id, "version_number": version_number},
            )
        )
        return version

    def save_inputs(
        self, project_id: str, version_number: int, inputs: dict[str, object], actor: str
    ) -> SaveInputsResult:
        version = self.get_version(project_id, version_number)
        if version.is_locked:
            self.audit_events.append(
                AuditEvent(
                    actor=actor,
                    action="reject_modify_approved_version",
                    entity_type="ProjectVersion",
                    entity_id=version.id,
                    before_snapshot=version.input_snapshot.copy(),
                    after_snapshot=version.input_snapshot.copy(),
                    metadata={"project_id": project_id, "version_number": version_number},
                )
            )
            return SaveInputsResult(success=False, error_code="PROJECT_VERSION_LOCKED")
        before = version.input_snapshot.copy()
        version.input_snapshot = inputs.copy()
        self.audit_events.append(
            AuditEvent(
                actor=actor,
                action="save_design_inputs",
                entity_type="ProjectVersion",
                entity_id=version.id,
                before_snapshot=before,
                after_snapshot=version.input_snapshot.copy(),
                metadata={"project_id": project_id, "version_number": version_number},
            )
        )
        return SaveInputsResult(success=True, version=version)

    def validate_inputs(self, inputs: dict[str, object]) -> dict[str, object]:
        required = [
            "daily_inbound_mass_kg",
            "working_time_h_per_day",
            "utilization_factor",
            "finished_storage_days",
            "packaging_storage_days",
            "reserve_factor",
        ]
        missing = [field for field in required if field not in inputs]
        tentative = [
            field
            for field, value in inputs.items()
            if isinstance(value, dict) and value.get("requires_review")
        ]
        return {"valid": not missing, "missing_fields": missing, "tentative_fields": tentative}

    def record_calculation(
        self,
        project_id: str,
        version_number: int,
        calculation_result: CalculationResult,
        actor: str,
    ) -> dict[str, object]:
        version = self.get_version(project_id, version_number)
        record = {
            "id": f"memory-{len(self.calculation_runs) + 1}",
            "project_id": project_id,
            "project_version_id": version.id,
            "calculator_name": calculation_result.calculator_name,
            "calculator_version": calculation_result.calculator_version,
            "input_snapshot": calculation_result.input,
            "result_snapshot": {
                "success": calculation_result.success,
                "calculator_name": calculation_result.calculator_name,
                "calculator_version": calculation_result.calculator_version,
                "input": calculation_result.input,
                "result": calculation_result.result,
            },
            "formulas": [item.__dict__ for item in calculation_result.formula_references],
            "coefficients": calculation_result.coefficients,
            "assumptions": calculation_result.assumptions,
            "warnings": [item.__dict__ for item in calculation_result.warnings],
            "source_references": calculation_result.source_references,
            "requires_review": calculation_result.requires_review,
        }
        self.calculation_runs.append(record)
        self.audit_events.append(
            AuditEvent(
                actor=actor,
                action="run_project_calculations",
                entity_type="CalculationRun",
                entity_id=str(record["id"]),
                before_snapshot={},
                after_snapshot={
                    "calculator_name": calculation_result.calculator_name,
                    "requires_review": calculation_result.requires_review,
                },
                metadata={"project_id": project_id, "version_number": version_number},
            )
        )
        return record

    def list_calculations(self, project_id: str, version_number: int) -> list[dict[str, object]]:
        version = self.get_version(project_id, version_number)
        return [
            record
            for record in self.calculation_runs
            if record["project_id"] == project_id and record["project_version_id"] == version.id
        ]

    def list_audit_events(self, project_id: str) -> list[dict[str, object]]:
        return [
            {
                "id": event.id,
                "actor": event.actor,
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "before_snapshot": event.before_snapshot,
                "after_snapshot": event.after_snapshot,
                "metadata": event.metadata,
                "created_at": event.created_at.isoformat(),
            }
            for event in self.audit_events
            if event.metadata.get("project_id") == project_id or event.entity_id == project_id
        ]
