"""Report assembler — deterministic content assembly from persisted results.

No LLM calls, no recalculation, no ORM access.  Only reads from
application service / repository ports.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cold_storage.modules.reports.domain.canonical import content_hash
from cold_storage.modules.reports.domain.enums import (
    ReportType,
    SourceType,
)
from cold_storage.modules.reports.domain.quality import evaluate_quality

SCHEMA_VERSION_MAP: dict[ReportType, str] = {
    ReportType.COLD_STORAGE_CONCEPT_DESIGN: "cold_storage_concept_design@1.0.0",
}

# Required sections for quality evaluation — per cold_storage_concept_design@1.0.0
# Only data-driven sections that might be absent if the provider has no data.
# citations, provenance, quality_summary are always present (assembler always creates them).
REQUIRED_SECTIONS: tuple[str, ...] = (
    "report_metadata",
    "project_summary",
    "cooling_load",
    "equipment_selection",
    "electrical_and_energy",
    "scheme_comparison",
)

# Required engineering result paths — missing these is a BLOCKER
REQUIRED_ENGINEERING_RESULTS: list[str] = [
    "cooling_load.total_design_refrigeration_load",
    "equipment_selection.total_compressor_capacity",
    "electrical_and_energy.total_installed_power",
    "scheme_comparison.schemes",
    "scheme_comparison.recommended_scheme",
]


class ReportAssembler:
    """Assembles deterministic report content from persisted data sources.

    The assembler only maps values — it never computes engineering results.
    All numeric values must come from the data sources passed in.
    """

    def __init__(self, data_provider: ReportDataProvider) -> None:
        self._provider = data_provider

    def assemble(
        self,
        *,
        report_id: str,
        project_id: str,
        project_version_id: str,
        report_type: ReportType,
        revision_number: int,
        generated_by: str,
    ) -> AssembledReport:
        """Assemble a complete report content dict from persisted data."""
        schema_version = SCHEMA_VERSION_MAP[report_type]

        # Gather data from provider (all persisted, no recalculation)
        project_data = self._provider.get_project(project_id)
        project_version_data = self._provider.get_project_version(
            project_version_id, project_id=project_id
        )
        calculation_data = self._provider.get_calculation_results(project_id, project_version_id)
        scheme_data = self._provider.get_scheme_results(project_id, project_version_id)
        agent_session_data = self._provider.get_agent_sessions(project_id, project_version_id)
        knowledge_data = self._provider.get_knowledge_documents()

        # Build content sections
        content: dict[str, Any] = {}
        source_refs: list[dict[str, Any]] = []

        # 1. report_metadata
        content["report_metadata"] = {
            "schema_version": schema_version,
            "report_id": report_id,
            "project_id": project_id,
            "project_version_id": project_version_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "generated_by": generated_by,
            "revision_number": revision_number,
        }

        # 2. project_summary
        if project_data:
            content["project_summary"] = {
                "project_name": project_data.get("name", ""),
                "project_location": project_data.get("location", ""),
                "description": project_data.get("description", ""),
            }
            source_refs.append(
                _make_source_ref(
                    section_key="project_summary",
                    source_type=SourceType.PROJECT,
                    source_id=project_id,
                    data=project_data,
                )
            )

        # 3-8: Assemble sections from calculation results
        for calc in calculation_data:
            section = calc.get("section_key", "")
            if section:
                content[section] = calc.get("data", {})
                source_refs.append(
                    _make_source_ref(
                        section_key=section,
                        source_type=SourceType.CALCULATION_RESULT,
                        source_id=calc.get("result_id", ""),
                        data=calc,
                    )
                )

        # 9. scheme_comparison
        if scheme_data:
            content["scheme_comparison"] = scheme_data
            source_refs.append(
                _make_source_ref(
                    section_key="scheme_comparison",
                    source_type=SourceType.SCHEME_RESULT,
                    source_id=scheme_data.get("run_id", ""),
                    data={
                        **scheme_data,
                        "result_id": scheme_data.get("run_id", ""),
                        "tool_name": "scheme_evaluator",
                        "tool_version": scheme_data.get("generator_version", ""),
                    },
                )
            )

        # 10. provenance source refs — project_version, knowledge, agent_session
        # Only add sources that are actually present (non-None, non-empty).
        if project_version_data:
            source_refs.append(
                _make_source_ref(
                    section_key="report_metadata",
                    source_type=SourceType.PROJECT_VERSION,
                    source_id=project_version_id,
                    data=project_version_data,
                )
            )

        # Collect knowledge revision IDs actually used by agent tool calls
        used_knowledge_ids: set[str] = set()
        if agent_session_data:
            for session in agent_session_data:
                for tc in session.get("tool_calls", []):
                    if tc.get("tool_name") == "knowledge_retrieval":
                        # Tool call result may reference knowledge revision IDs
                        for ref_id in tc.get("knowledge_revision_ids", []):
                            used_knowledge_ids.add(ref_id)

        if knowledge_data and used_knowledge_ids:
            for doc in knowledge_data:
                for rev in doc.get("approved_revisions", []):
                    if rev["id"] in used_knowledge_ids:
                        source_refs.append(
                            _make_source_ref(
                                section_key="knowledge_references",
                                source_type=SourceType.KNOWLEDGE_REVISION,
                                source_id=rev["id"],
                                data={
                                    "knowledge_status": "approved",
                                    "persisted_content_hash": rev.get("content_sha256", ""),
                                },
                            )
                        )

        if agent_session_data:
            for session in agent_session_data:
                source_refs.append(
                    _make_source_ref(
                        section_key="report_metadata",
                        source_type=SourceType.AGENT_SESSION,
                        source_id=session.get("session_id", ""),
                        data=session,
                    )
                )
                for turn in session.get("turns", []):
                    if turn.get("status") == "completed":
                        source_refs.append(
                            _make_source_ref(
                                section_key="report_metadata",
                                source_type=SourceType.AGENT_TURN,
                                source_id=turn.get("id", ""),
                                data=turn,
                            )
                        )
                for tc in session.get("tool_calls", []):
                    from cold_storage.modules.reports.domain.source_contract import (
                        SOURCE_SUCCESS_STATUSES,
                    )

                    if tc.get("tool_call_status") in SOURCE_SUCCESS_STATUSES:
                        source_refs.append(
                            _make_source_ref(
                                section_key="report_metadata",
                                source_type=SourceType.AGENT_TOOL_CALL,
                                source_id=tc.get("id", ""),
                                data=tc,
                            )
                        )

        # 11. risks_and_missing_information
        content.setdefault(
            "risks_and_missing_information", {"risks": [], "missing_information": []}
        )

        # Evaluate quality
        findings = evaluate_quality(
            content,
            source_refs,
            required_sections=REQUIRED_SECTIONS,
            required_calc_fields=REQUIRED_ENGINEERING_RESULTS,
        )
        from cold_storage.modules.reports.domain.enums import ReportStatus
        from cold_storage.modules.reports.domain.quality import has_blockers

        quality_status = (
            ReportStatus.GENERATED if not has_blockers(findings) else ReportStatus.DRAFT
        )

        # Build quality_summary
        blocker_count = sum(1 for f in findings if f["severity"] == "blocker")
        warning_count = sum(1 for f in findings if f["severity"] == "warning")
        info_count = sum(1 for f in findings if f["severity"] == "info")
        content["quality_summary"] = {
            "total_findings": len(findings),
            "blocker_count": blocker_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "findings": findings,
        }

        # Citations
        content["citations"] = [
            {
                "section_key": ref["section_key"],
                "field_path": ref["field_path"],
                "source_type": ref["source_type"],
                "source_id": ref["source_id"],
                "tool_name": ref.get("tool_name", ""),
                "tool_version": ref.get("tool_version", ""),
                "result_id": ref.get("result_id", ""),
                "content_hash": ref.get("content_hash", ""),
            }
            for ref in source_refs
        ]

        # Canonical hash — exclude time-dependent and sequence-dependent fields
        # so the hash depends only on schema_version, project data, calculation
        # results, and source hashes.
        canonical = content.copy()
        canonical.pop("provenance", None)
        if "report_metadata" in canonical:
            canonical_meta = dict(canonical["report_metadata"])
            canonical_meta.pop("generated_at", None)
            canonical_meta.pop("revision_number", None)
            canonical_meta.pop("report_id", None)
            canonical_meta.pop("generated_by", None)
            canonical["report_metadata"] = canonical_meta
        can_hash = content_hash(canonical)

        content["provenance"] = {
            "content_hash": can_hash,
            "canonical_hash": can_hash,
            "selection_rules": {
                "calculation_results": "latest_by_section",
                "scheme_results": "latest_by_project_version",
                "knowledge": "approved_only",
            },
            "assembly_timestamp": datetime.now(UTC).isoformat(),
        }

        return AssembledReport(
            content=content,
            canonical_content=canonical,  # canonical excludes time/sequence fields
            content_hash=can_hash,
            source_refs=source_refs,
            quality_status=quality_status,
            findings=findings,
            schema_version=schema_version,
        )


def _make_source_ref(
    *,
    section_key: str,
    source_type: SourceType,
    source_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Build a source reference dict from persisted data.

    Only includes metadata that genuinely came from the persisted record.
    Does NOT fabricate or hardcode verification fields (tool_call_status,
    knowledge_status, source_exists, hash_mismatch).  These must be
    provided by the data provider based on actual persisted state.
    """

    ref: dict[str, Any] = {
        "section_key": section_key,
        "field_path": section_key,
        "source_type": source_type.value,
        "source_id": source_id,
        "source_revision": data.get("version", ""),
        "tool_name": data.get("tool_name", ""),
        "tool_version": data.get("tool_version", ""),
        "result_id": data.get("result_id", ""),
        "content_hash": data.get("persisted_content_hash", ""),
    }
    # Only pass through verification metadata that is genuinely present
    # in the data (i.e., came from a persisted record, not fabricated).
    for key in ("tool_call_status", "knowledge_status", "source_exists", "hash_mismatch"):
        if key in data:
            ref[key] = data[key]
    return ref


class AssembledReport:
    """Result of report assembly."""

    def __init__(
        self,
        content: dict[str, Any],
        canonical_content: dict[str, Any],
        content_hash: str,
        source_refs: list[dict[str, Any]],
        quality_status: Any,
        findings: list[dict[str, Any]],
        schema_version: str,
    ) -> None:
        self.content = content
        self.canonical_content = canonical_content
        self.content_hash = content_hash
        self.source_refs = source_refs
        self.quality_status = quality_status
        self.findings = findings
        self.schema_version = schema_version


class ReportDataProvider:
    """Port: provides persisted data for report assembly.

    Implementations should read from repositories, NOT from ORM directly.
    """

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return None

    def get_project_version(
        self, version_id: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        return None

    def get_calculation_results(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        return []

    def get_scheme_results(self, project_id: str, version_id: str) -> dict[str, Any] | None:
        return None

    def get_agent_sessions(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        return []

    def get_knowledge_documents(self) -> list[dict[str, Any]]:
        return []
