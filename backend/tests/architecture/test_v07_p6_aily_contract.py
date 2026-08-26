"""Architecture tests for V0.7 P6 Feishu Aily integration boundary contract.

Enforces the frozen contract in
``docs/tasks/V0_7-P6-aily-integration-boundary-contract.md`` and static
artifacts under ``docs/contracts/aily/v0.7/**`` without implementing live Aily
or changing application behavior.

Contract authority SHA: ``f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_7-P6-aily-integration-boundary-contract.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-027-aily-integration-boundary.md"
P0_CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_7-P0-trust-loop-contract.md"
AILY_CONTRACTS_DIR = REPO_ROOT / "docs" / "contracts" / "aily" / "v0.7"

FROZEN_MODEL_TOOLS: tuple[str, ...] = (
    "planning_context.get",
    "engineering_inputs.validate",
    "five_stage_execution.propose",
    "report_delivery.propose",
)

WRITE_TOOLS_REQUIRING_CONFIRMATION: frozenset[str] = frozenset(
    {
        "five_stage_execution.propose",
        "report_delivery.propose",
    }
)

REQUIRED_GOVERNANCE_FLAGS: tuple[str, ...] = (
    "TASK=V07_P6_AILY_INTEGRATION_BOUNDARY_CONTRACT_R1",
    "PARENT_ISSUE=PENDING",
    "P6_TRACKING_ISSUE=PENDING",
    "DISPATCH_ISSUE=PENDING",
    "GOVERNANCE_OWNER=V0.7",
    "BASE_MAIN_SHA=f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba",
    "BASE_TREE=23af6e60e4247394b2b12c50440d5fc03a819074",
    "PREVIOUS_RELEASE=v0.6.0",
    "TARGET_BRANCH=cursor/v07-p6-aily-boundary-contract-6c68",
    "TARGET_PR_STATE=DRAFT",
    "CONTRACT_STATUS=DEFINITION_R1_DRAFT_FOR_INDEPENDENT_REVIEW",
    "V07_P6_IMPLEMENTATION_AUTHORIZED=YES",
    "V07_P7_IMPLEMENTATION_AUTHORIZED=NO",
    "READY_AUTHORIZED=NO",
    "MERGE_AUTHORIZED=NO",
    "CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=NO",
    "TAG_PUBLICATION_AUTHORIZED=NO",
    "RELEASE_PUBLICATION_AUTHORIZED=NO",
    "FORMULA_RECUT_AUTHORIZED=NO",
    "COEFFICIENT_PROMOTION_AUTHORIZED=NO",
    "LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO",
    "AILY_LIVE_IMPLEMENTATION=NO",
    "PRODUCTION_DEPLOYMENT_AUTHORIZED=NO",
    "NO_STEP_IMPLIES_THE_NEXT=TRUE",
)

P6_ALLOWLIST_PATHS: tuple[str, ...] = (
    "docs/tasks/V0_7-P6-aily-integration-boundary-contract.md",
    "docs/architecture/ADR-027-aily-integration-boundary.md",
    "docs/contracts/aily/v0.7/**",
    "backend/tests/architecture/test_v07_p6_aily_contract.py",
)

REQUIRED_STATIC_ARTIFACTS: tuple[str, ...] = (
    "README.md",
    "model-visible-tools.v1.json",
    "confirmation-callback.v1.json",
    "forbidden-model-surfaces.v1.json",
    "aily-to-system-connector.v1.json",
    "system-to-aily-openapi.v1.yaml",
)

FORBIDDEN_TOOL_FRAGMENTS: tuple[str, ...] = (
    "mark_reviewed",
    "approve",
    "report.mark_reviewed",
    "report.approve",
)

FORBIDDEN_MODEL_FIELD_FRAGMENTS: tuple[str, ...] = (
    "confirmation_token",
    "actor_principal",
    "confirmed_by",
)

FORBIDDEN_CONTRACT_FRAGMENTS: tuple[str, ...] = (
    "utilization_factor",
    "reserve_factor",
)

_ENGINEERING_VALUE_PATTERNS = (
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
    re.compile(r"\butilization_factor\s*=\s*0\.\d+"),
    re.compile(r"\breserve_factor\s*=\s*0\.\d+"),
    re.compile(r"\b\d{2,}_\d{3}\b"),
)


def _read_contract() -> str:
    assert CONTRACT_PATH.is_file(), f"P6 contract missing: {CONTRACT_PATH}"
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _read_json_artifact(name: str) -> dict:
    path = AILY_CONTRACTS_DIR / name
    assert path.is_file(), f"Missing Aily contract artifact: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_allowlist_paths(contract: str, marker: str) -> set[str]:
    start = contract.index(marker)
    fence_start = contract.rfind("```", 0, start)
    fence_end = contract.index("```", start)
    block = contract[fence_start + 3 : fence_end].strip()
    if block.startswith("text"):
        block = block.split("\n", 1)[1].strip()
    paths: set[str] = set()
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped == marker:
            continue
        paths.add(stripped)
    return paths


def test_v07_p6_contract_file_exists() -> None:
    """P6 contract document must exist at the authorized path."""
    assert CONTRACT_PATH.is_file()


def test_v07_p6_adr_exists() -> None:
    """ADR-027 must exist for the Aily integration boundary."""
    assert ADR_PATH.is_file()
    text = ADR_PATH.read_text(encoding="utf-8")
    assert "AILY_LIVE_IMPLEMENTATION=NO" in text
    assert "ADR-027" in text or "ADR-027:" in text


def test_v07_p6_contract_governance_flags_present() -> None:
    """Governance identity block must match authorized constants exactly."""
    contract = _read_contract()
    for flag in REQUIRED_GOVERNANCE_FLAGS:
        assert flag in contract, f"P6 contract missing governance flag: {flag!r}"


def test_v07_p6_allowlist_paths_are_documented() -> None:
    """P6 exclusive allowlist must list the authorized artifact paths."""
    contract = _read_contract()
    paths = _extract_allowlist_paths(contract, "V07_P6_FILE_ALLOWLIST")
    for path in P6_ALLOWLIST_PATHS:
        assert path in paths, f"P6 allowlist missing {path!r}"


def test_v07_p6_static_contract_artifacts_exist() -> None:
    """All frozen static artifacts under docs/contracts/aily/v0.7 must exist."""
    assert AILY_CONTRACTS_DIR.is_dir()
    for name in REQUIRED_STATIC_ARTIFACTS:
        assert (AILY_CONTRACTS_DIR / name).is_file(), f"Missing artifact: {name!r}"


def test_v07_p6_model_visible_tools_are_exactly_four() -> None:
    """Model-visible tool registry must freeze exactly four tools."""
    artifact = _read_json_artifact("model-visible-tools.v1.json")
    tool_names = [tool["name"] for tool in artifact["tools"]]
    assert artifact["model_visible_tool_count"] == 4
    assert len(tool_names) == 4
    assert tuple(tool_names) == FROZEN_MODEL_TOOLS


def test_v07_p6_write_tools_require_confirmation() -> None:
    """Write propose tools must require confirmation in the static schema."""
    artifact = _read_json_artifact("model-visible-tools.v1.json")
    for tool in artifact["tools"]:
        name = tool["name"]
        if name in WRITE_TOOLS_REQUIRING_CONFIRMATION:
            assert tool["requires_confirmation"] is True, f"{name} must require confirmation"
            assert tool["authorization_level"] == "write", f"{name} must be write-level"
        else:
            assert tool["requires_confirmation"] is False, f"{name} must not require confirmation"
            assert tool["authorization_level"] == "read", f"{name} must be read-level"


def test_v07_p6_forbidden_tools_not_in_model_registry() -> None:
    """Forbidden review/legacy tools must not appear in model-visible registry."""
    artifact = _read_json_artifact("model-visible-tools.v1.json")
    tool_names = {tool["name"] for tool in artifact["tools"]}
    forbidden = _read_json_artifact("forbidden-model-surfaces.v1.json")
    for forbidden_name in forbidden["forbidden_tool_names"]:
        assert forbidden_name not in tool_names, (
            f"Forbidden tool {forbidden_name!r} found in model-visible registry"
        )


def test_v07_p6_confirmation_callback_is_not_model_visible() -> None:
    """Confirmation callbacks must be non-model surfaces."""
    callback = _read_json_artifact("confirmation-callback.v1.json")
    assert callback["model_visible"] is False
    for entry in callback["callbacks"]:
        assert entry["model_visible"] is False
    contract = _read_contract()
    assert "Confirmation callback is not a model tool" in contract or (
        "not a model tool" in contract
    )


def test_v07_p6_confirmation_tokens_forbidden_from_model_context() -> None:
    """confirmation_token must be denied across callback and forbidden surfaces."""
    callback = _read_json_artifact("confirmation-callback.v1.json")
    assert "confirmation_token" in callback["callbacks"][0]["forbidden_fields"]
    assert (
        callback["callbacks"][0]["server_side_token_handling"][
            "confirmation_token_in_model_context"
        ]
        == "FORBIDDEN"
    )

    forbidden = _read_json_artifact("forbidden-model-surfaces.v1.json")
    assert "confirmation_token" in forbidden["forbidden_model_fields"]
    assert "confirmation_tokens" in forbidden["forbidden_model_context_categories"]


def test_v07_p6_actor_must_not_be_model_self_attested() -> None:
    """Actor identity must be transport-derived, not model JSON."""
    contract = _read_contract()
    assert "trusted transport" in contract
    assert "not from model JSON" in contract or "never from model" in contract

    callback = _read_json_artifact("confirmation-callback.v1.json")
    assert "model_json" in callback["transport"]["forbidden_actor_sources"]

    artifact = _read_json_artifact("model-visible-tools.v1.json")
    for tool in artifact["tools"]:
        for field in ("actor", "actor_principal", "confirmed_by", "operator_id"):
            assert field in tool["forbidden_input_fields"], (
                f"{tool['name']} must forbid model actor field {field!r}"
            )


def test_v07_p6_call_directions_are_separated() -> None:
    """Inbound connector and outbound OpenAPI contracts must be distinct."""
    inbound = _read_json_artifact("aily-to-system-connector.v1.json")
    outbound_path = AILY_CONTRACTS_DIR / "system-to-aily-openapi.v1.yaml"
    outbound_text = outbound_path.read_text(encoding="utf-8")

    assert inbound["direction"] == "aily_to_system"
    assert inbound["transport_family"] == "custom_mcp_or_feishu_connector"
    assert "system_to_aily" in outbound_text
    assert "x-direction: system_to_aily" in outbound_text

    contract = _read_contract()
    assert "Aily → this system" in contract or "Aily → this system (inbound)" in contract
    assert "This system → Aily" in contract or "system → Aily" in contract


def test_v07_p6_inbound_connector_maps_four_operations() -> None:
    """Inbound connector must map exactly four model-visible operations."""
    inbound = _read_json_artifact("aily-to-system-connector.v1.json")
    operations = inbound["operations"]
    assert len(operations) == 4
    mapped_tools = tuple(op["tool_name"] for op in operations)
    assert mapped_tools == FROZEN_MODEL_TOOLS
    for op in operations:
        assert op["model_visible"] is True


def test_v07_p6_agent_api_documented_as_v06_compat_only() -> None:
    """Contract must freeze /api/v1/agent/** as non-production, non-extended."""
    contract = _read_contract()
    required_fragments = (
        "/api/v1/agent/**",
        "V0.6 internal compatibility",
        "no further extension",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P6 contract missing fragment: {fragment!r}"

    inbound = _read_json_artifact("aily-to-system-connector.v1.json")
    assert inbound["not_production_boundary"]["surface"] == "/api/v1/agent/**"
    assert inbound["not_production_boundary"]["extend_for_aily"] == "FORBIDDEN"


def test_v07_p6_contract_documents_ownership_split_and_engineering_authority() -> None:
    """Aily dialogue vs system engineering/persistence authority must be explicit."""
    contract = _read_contract()
    required_fragments = (
        "EngineeringInputBundleV1",
        "five-stage execution",
        "confirmation",
        "audit",
        "Reports MUST NOT recalculate formulas",
        "AGENT_TO_ENGINEERING_VALUE=NO",
        "PRODUCTION_RBAC_CLAIM=NO",
        "V07-GAP-008",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P6 contract missing fragment: {fragment!r}"


def test_v07_p6_contract_documents_forbidden_review_tools() -> None:
    """mark_reviewed and approve must be forbidden model tools."""
    contract = _read_contract()
    for fragment in FORBIDDEN_TOOL_FRAGMENTS:
        assert fragment in contract, f"P6 contract must forbid {fragment!r}"

    forbidden = _read_json_artifact("forbidden-model-surfaces.v1.json")
    for fragment in ("mark_reviewed", "approve"):
        assert fragment in forbidden["forbidden_tool_names"]


def test_v07_p6_contract_references_p0_section_seven() -> None:
    """P6 must cite P0 §7 as parent authority when P0 contract is present."""
    contract = _read_contract()
    assert "V0_7-P0-trust-loop-contract.md" in contract
    assert "§7" in contract or "section 7" in contract.lower()

    if P0_CONTRACT_PATH.is_file():
        p0 = P0_CONTRACT_PATH.read_text(encoding="utf-8")
        for tool in FROZEN_MODEL_TOOLS:
            assert tool in p0, f"P0 §7 reference tool missing from P0 contract: {tool!r}"


def test_v07_p6_contract_and_tests_contain_no_engineering_formula_values() -> None:
    """Neither the contract file nor this test module may embed formula numbers."""
    this_file = Path(__file__).read_text(encoding="utf-8")
    contract = _read_contract()

    for label, content in (("contract", contract), ("test module", this_file)):
        if label == "contract":
            for fragment in FORBIDDEN_CONTRACT_FRAGMENTS:
                assert fragment not in content, (
                    f"Forbidden engineering fragment {fragment!r} found in {label}"
                )
        for pattern in _ENGINEERING_VALUE_PATTERNS:
            match = pattern.search(content)
            assert match is None, (
                f"Engineering formula value pattern {pattern.pattern!r} "
                f"found in {label}: {match.group()!r}"
            )


def test_v07_p6_model_tool_schemas_forbid_sensitive_fields() -> None:
    """Static tool schemas must list forbidden actor/token fields."""
    artifact = _read_json_artifact("model-visible-tools.v1.json")
    for tool in artifact["tools"]:
        for field in FORBIDDEN_MODEL_FIELD_FRAGMENTS:
            assert field in tool["forbidden_input_fields"] or field in tool.get(
                "forbidden_output_fields", []
            ), f"{tool['name']} must document forbidden field {field!r}"
