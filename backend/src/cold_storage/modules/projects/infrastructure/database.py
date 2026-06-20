from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from cold_storage.modules.audit.domain import AuditEvent
from cold_storage.modules.calculations.domain.result import CalculationResult
from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.domain.models import Project, ProjectVersion, SaveInputsResult
from cold_storage.modules.projects.infrastructure.orm import (
    AuditEventRecord,
    CalculationRunRecord,
    ProjectRecord,
    ProjectVersionRecord,
)


class DatabaseProjectService(ProjectService):
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def create_project(self, name: str, location: str, product_category: str) -> Project:
        with self.session_factory() as session:
            count = len(session.scalars(select(ProjectRecord)).all())
            project = Project(
                code=f"P{count + 1:04d}",
                name=name,
                location=location,
                product_category=product_category,
            )
            session.add(self._project_record(project))
            self._add_audit(
                session,
                AuditEvent(
                    actor="system",
                    action="create_project",
                    entity_type="Project",
                    entity_id=project.id,
                    before_snapshot={},
                    after_snapshot={"name": name, "location": location},
                    metadata={},
                ),
            )
            session.commit()
            return project

    def list_projects(self) -> list[Project]:
        with self.session_factory() as session:
            records = session.scalars(
                select(ProjectRecord).order_by(ProjectRecord.created_at)
            ).all()
            return [self._project_from_record(record, include_versions=False) for record in records]

    def get_project(self, project_id: str) -> Project:
        with self.session_factory() as session:
            record = self._get_project_record(session, project_id)
            return self._project_from_record(record, include_versions=True)

    def create_version(
        self, project_id: str, change_summary: str, created_by: str = "system"
    ) -> ProjectVersion:
        with self.session_factory() as session:
            project = self._get_project_record(session, project_id)
            version = ProjectVersion(
                project_id=project_id,
                version_number=project.current_version_number + 1,
                change_summary=change_summary,
                created_by=created_by,
            )
            project.current_version_number = version.version_number
            session.add(self._version_record(version))
            self._add_audit(
                session,
                AuditEvent(
                    actor=created_by,
                    action="create_project_version",
                    entity_type="ProjectVersion",
                    entity_id=version.id,
                    before_snapshot={},
                    after_snapshot={"version_number": version.version_number},
                    metadata={"project_id": project_id},
                ),
            )
            session.commit()
            return version

    def get_version(self, project_id: str, version_number: int) -> ProjectVersion:
        with self.session_factory() as session:
            record = self._get_version_record(session, project_id, version_number)
            return self._version_from_record(record)

    def list_versions(self, project_id: str) -> list[ProjectVersion]:
        with self.session_factory() as session:
            records = session.scalars(
                select(ProjectVersionRecord)
                .where(ProjectVersionRecord.project_id == project_id)
                .order_by(ProjectVersionRecord.version_number)
            ).all()
            return [self._version_from_record(record) for record in records]

    def approve_version(self, project_id: str, version_number: int) -> ProjectVersion:
        with self.session_factory() as session:
            record = self._get_version_record(session, project_id, version_number)
            before: dict[str, object] = {"status": record.status}
            record.status = "approved"
            self._add_audit(
                session,
                AuditEvent(
                    actor="system",
                    action="approve_project_version",
                    entity_type="ProjectVersion",
                    entity_id=record.id,
                    before_snapshot=before,
                    after_snapshot={"status": record.status},
                    metadata={"project_id": project_id, "version_number": version_number},
                ),
            )
            session.commit()
            return self._version_from_record(record)

    def save_inputs(
        self, project_id: str, version_number: int, inputs: dict[str, object], actor: str
    ) -> SaveInputsResult:
        with self.session_factory() as session:
            record = self._get_version_record(session, project_id, version_number)
            if record.status == "approved":
                self._add_audit(
                    session,
                    AuditEvent(
                        actor=actor,
                        action="reject_modify_approved_version",
                        entity_type="ProjectVersion",
                        entity_id=record.id,
                        before_snapshot=dict(record.input_snapshot),
                        after_snapshot=dict(record.input_snapshot),
                        metadata={"project_id": project_id, "version_number": version_number},
                    ),
                )
                session.commit()
                return SaveInputsResult(success=False, error_code="PROJECT_VERSION_LOCKED")
            before = dict(record.input_snapshot)
            record.input_snapshot = inputs.copy()
            self._add_audit(
                session,
                AuditEvent(
                    actor=actor,
                    action="save_design_inputs",
                    entity_type="ProjectVersion",
                    entity_id=record.id,
                    before_snapshot=before,
                    after_snapshot=dict(record.input_snapshot),
                    metadata={"project_id": project_id, "version_number": version_number},
                ),
            )
            session.commit()
            return SaveInputsResult(success=True, version=self._version_from_record(record))

    def record_calculation(
        self,
        project_id: str,
        version_number: int,
        calculation_result: CalculationResult,
        actor: str,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            version = self._get_version_record(session, project_id, version_number)
            result_snapshot = asdict(calculation_result)
            record = CalculationRunRecord(
                id=str(uuid4()),
                project_id=project_id,
                project_version_id=version.id,
                calculator_name=calculation_result.calculator_name,
                calculator_version=calculation_result.calculator_version,
                input_snapshot=calculation_result.input,
                result_snapshot=result_snapshot,
                formulas=[asdict(item) for item in calculation_result.formula_references],
                coefficients=calculation_result.coefficients,
                assumptions=calculation_result.assumptions,
                warnings=[asdict(item) for item in calculation_result.warnings],
                source_references=calculation_result.source_references,
                requires_review=calculation_result.requires_review,
                created_at=datetime.now(UTC),
            )
            session.add(record)
            self._add_audit(
                session,
                AuditEvent(
                    actor=actor,
                    action="run_project_calculations",
                    entity_type="CalculationRun",
                    entity_id=record.id,
                    before_snapshot={},
                    after_snapshot={
                        "calculator_name": record.calculator_name,
                        "requires_review": record.requires_review,
                    },
                    metadata={"project_id": project_id, "version_number": version_number},
                ),
            )
            session.commit()
            return self._calculation_to_dict(record)

    def list_calculations(self, project_id: str, version_number: int) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            version = self._get_version_record(session, project_id, version_number)
            records = session.scalars(
                select(CalculationRunRecord)
                .where(CalculationRunRecord.project_version_id == version.id)
                .order_by(CalculationRunRecord.created_at)
            ).all()
            return [self._calculation_to_dict(record) for record in records]

    def list_audit_events(self, project_id: str) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            records = session.scalars(
                select(AuditEventRecord).order_by(AuditEventRecord.created_at)
            ).all()
            return [
                self._audit_to_dict(record)
                for record in records
                if record.entity_id == project_id
                or record.event_metadata.get("project_id") == project_id
            ]

    def _get_project_record(self, session: Session, project_id: str) -> ProjectRecord:
        record = session.get(ProjectRecord, project_id)
        if record is None:
            raise KeyError(project_id)
        return record

    def _get_version_record(
        self, session: Session, project_id: str, version_number: int
    ) -> ProjectVersionRecord:
        record = session.scalar(
            select(ProjectVersionRecord).where(
                ProjectVersionRecord.project_id == project_id,
                ProjectVersionRecord.version_number == version_number,
            )
        )
        if record is None:
            raise KeyError(version_number)
        return record

    def _add_audit(self, session: Session, event: AuditEvent) -> None:
        session.add(
            AuditEventRecord(
                id=event.id,
                actor=event.actor,
                action=event.action,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                before_snapshot=event.before_snapshot,
                after_snapshot=event.after_snapshot,
                event_metadata=event.metadata,
                created_at=event.created_at,
            )
        )

    def _project_record(self, project: Project) -> ProjectRecord:
        return ProjectRecord(
            id=project.id,
            code=project.code,
            name=project.name,
            location=project.location,
            product_category=project.product_category,
            status=project.status,
            current_version_number=project.current_version_number,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    def _version_record(self, version: ProjectVersion) -> ProjectVersionRecord:
        return ProjectVersionRecord(
            id=version.id,
            project_id=version.project_id,
            version_number=version.version_number,
            change_summary=version.change_summary,
            status=version.status,
            input_snapshot=version.input_snapshot,
            created_at=version.created_at,
            created_by=version.created_by,
        )

    def _project_from_record(self, record: ProjectRecord, include_versions: bool) -> Project:
        versions = (
            [self._version_from_record(version) for version in record.versions]
            if include_versions
            else []
        )
        return Project(
            id=record.id,
            code=record.code,
            name=record.name,
            location=record.location,
            product_category=record.product_category,
            status=record.status,
            current_version_number=record.current_version_number,
            created_at=record.created_at,
            updated_at=record.updated_at,
            versions=versions,
        )

    def _version_from_record(self, record: ProjectVersionRecord) -> ProjectVersion:
        return ProjectVersion(
            id=record.id,
            project_id=record.project_id,
            version_number=record.version_number,
            change_summary=record.change_summary,
            status=record.status,
            input_snapshot=dict(record.input_snapshot),
            created_at=record.created_at,
            created_by=record.created_by,
        )

    def _calculation_to_dict(self, record: CalculationRunRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "project_id": record.project_id,
            "project_version_id": record.project_version_id,
            "calculator_name": record.calculator_name,
            "calculator_version": record.calculator_version,
            "input_snapshot": record.input_snapshot,
            "result_snapshot": record.result_snapshot,
            "formulas": record.formulas,
            "coefficients": record.coefficients,
            "assumptions": record.assumptions,
            "warnings": record.warnings,
            "source_references": record.source_references,
            "requires_review": record.requires_review,
            "created_at": record.created_at.isoformat(),
        }

    def _audit_to_dict(self, record: AuditEventRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "actor": record.actor,
            "action": record.action,
            "entity_type": record.entity_type,
            "entity_id": record.entity_id,
            "before_snapshot": record.before_snapshot,
            "after_snapshot": record.after_snapshot,
            "metadata": record.event_metadata,
            "created_at": record.created_at.isoformat(),
        }


def create_database_project_service(database_url: str) -> DatabaseProjectService:
    engine = create_engine(database_url, future=True)
    return DatabaseProjectService(engine)
