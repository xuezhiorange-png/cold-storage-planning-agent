"""Durable architecture locks for the V2.2 MCP Tool 7 integration."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import anyio
from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

from cold_storage.modules.aily.api.mcp_sse import (
    _MCP_TOOL_ORDER,
    _PREVIEW_TOOL_ORDER,
    build_zone_plan_mcp_server,
)
from cold_storage.modules.aily.application.mcp_site_layout import (
    PREVIEW_SITE_LAYOUT_INPUT_FIELDS,
    PREVIEW_SITE_LAYOUT_TOOL_NAME,
)
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parent
BASE_MAIN_SHA = "cd0a2cc16a9b49296a25b398d4a17dbd4f63b67b"
P4_APPLICATION = "backend/src/cold_storage/modules/aily/application/site_layout_preview.py"
P4_MCP_APPLICATION = "backend/src/cold_storage/modules/aily/application/mcp_site_layout.py"
MCP_API = "backend/src/cold_storage/modules/aily/api/mcp_sse.py"
P4_UNIT = "backend/tests/unit/test_v22_p4_site_layout_mcp.py"
P4_ARCHITECTURE = "backend/tests/architecture/test_v22_p4_mcp_tool7_doubao_feishu_integration.py"
P4_DOC = "docs/tasks/V2_2-P4-mcp-tool7-doubao-feishu-integration.md"
P4_ALLOWED_PATHS = {
    P4_APPLICATION,
    P4_MCP_APPLICATION,
    MCP_API,
    P4_UNIT,
    P4_ARCHITECTURE,
    P4_DOC,
    "backend/tests/unit/test_v11_aily_mcp_protocol.py",
    "backend/tests/unit/test_v12_aily_mcp_protocol.py",
    "backend/tests/integration/test_v11_aily_mcp_sse_http.py",
    "backend/tests/integration/test_v21_p2_aily_factory_power_mcp_http.py",
    "docs/tasks/V2_2-version-plan.md",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/audit/current-state.md",
    # Append-only corrections keep completed P2 scope guards on immutable history.
    "backend/tests/architecture/test_v22_p2a_site_geometry_foundation.py",
    "backend/tests/architecture/test_v22_p2b1_truck_maneuver_template_contract.py",
}


def _source(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _historical_target() -> str | None:
    history = _git(
        "log",
        "--reverse",
        "--diff-filter=A",
        "--format=%H",
        "HEAD",
        "--",
        P4_ARCHITECTURE,
    )
    return history.splitlines()[0] if history else None


def _historical_changed_paths() -> set[str]:
    target = _historical_target()
    if target is None:
        paths = set(_git("diff", "--name-only", BASE_MAIN_SHA, "HEAD").splitlines())
        paths.update(_git("ls-files", "--others", "--exclude-standard").splitlines())
        return {path for path in paths if path}
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", target, "HEAD"],
        cwd=REPO_ROOT,
        check=True,
    )
    return set(_git("diff", "--name-only", BASE_MAIN_SHA, target).splitlines())


def test_p4_scope_is_immutable_from_p4_base_to_p4_target() -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"],
        cwd=REPO_ROOT,
        check=True,
    )
    changed = _historical_changed_paths()
    assert changed <= P4_ALLOWED_PATHS
    assert not any(path.startswith("backend/alembic/") for path in changed)
    assert not any(path.startswith("frontend/") for path in changed)
    assert not any(path.startswith("deployment/") for path in changed)
    assert not any(path.startswith(".github/workflows/") for path in changed)


async def _list_tools() -> list[object]:
    server = build_zone_plan_mcp_server()
    client_to_server_send, client_to_server_recv = anyio.create_memory_object_stream[
        SessionMessage | Exception
    ](64)
    server_to_client_send, server_to_client_recv = anyio.create_memory_object_stream[
        SessionMessage
    ](64)
    result_box: list[list[object]] = []

    async def run_server() -> None:
        await server.run(
            client_to_server_recv,
            server_to_client_send,
            server.create_initialization_options(),
        )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(run_server)
        async with ClientSession(server_to_client_recv, client_to_server_send) as session:
            await session.initialize()
            result = await session.list_tools()
            result_box.append(list(result.tools))
        task_group.cancel_scope.cancel()
    return result_box[0]


def test_mcp_surface_appends_exactly_one_tool_at_position_seven() -> None:
    assert _PREVIEW_TOOL_ORDER == (
        "preview_zone_plan",
        "preview_cooling_load",
        "preview_equipment",
        "preview_installed_power",
        "preview_investment",
        "preview_factory_power",
    )
    assert (*_PREVIEW_TOOL_ORDER, PREVIEW_SITE_LAYOUT_TOOL_NAME) == _MCP_TOOL_ORDER
    assert len(_MCP_TOOL_ORDER) == 7
    tools = anyio.run(_list_tools)
    names = [tool.name for tool in tools]  # type: ignore[attr-defined]
    assert names == list(_MCP_TOOL_ORDER)
    first_schema = tools[0].inputSchema  # type: ignore[attr-defined]
    assert all(tool.inputSchema == first_schema for tool in tools[:6])  # type: ignore[attr-defined]
    assert tuple(first_schema["required"]) == tuple(OPERATOR_V09_FIVE_KEY_FIELDS)
    assert first_schema["additionalProperties"] is False
    site_schema = tools[6].inputSchema  # type: ignore[attr-defined]
    assert tuple(site_schema["required"]) == tuple(PREVIEW_SITE_LAYOUT_INPUT_FIELDS)
    assert set(site_schema["properties"]) == set(PREVIEW_SITE_LAYOUT_INPUT_FIELDS)
    assert site_schema["additionalProperties"] is False


def test_p4_application_has_no_direct_engineering_calculation_imports() -> None:
    for path in (P4_APPLICATION, P4_MCP_APPLICATION):
        tree = ast.parse(_source(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    not alias.name.startswith("cold_storage.modules.calculations")
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("cold_storage.modules.calculations")

    source = _source(P4_APPLICATION)
    for forbidden in (
        "calculate_cooling_load",
        "calculate_installed_power",
        "calculate_factory_power",
        "calculate_investment",
        "COP",
        "simultaneity",
    ):
        assert forbidden not in source
    for required in (
        "execute_zone_preview_authority",
        "build_p1_project_handoff",
        "select_validated_placement",
        "validate_truck_maneuver_project_binding",
        "project_validated_layout_to_svg",
    ):
        assert required in source
    assert "from cold_storage.modules.layout.application.placement import" not in source
    assert "from cold_storage.modules.layout.application.access_routing import" not in source
    assert "truck_maneuver" in source
    assert '"site_constraints": copy.deepcopy(dict(site))' in source
    assert '"truck_access": p1f_input' in source
    assert "bound_truck" in source


def test_p4_api_keeps_existing_transport_auth_and_appends_only_tool_seven() -> None:
    source = _source(MCP_API)
    assert 'MCP_SSE_PATH = f"{MCP_MOUNT_PATH}/sse"' in source
    assert "verify_connector_key" in source
    assert "validate_input=False" in source
    assert "_PREVIEW_TOOL_ORDER" in source
    assert "_MCP_TOOL_ORDER" in source
    assert "PREVIEW_SITE_LAYOUT_TOOL_NAME" in source
    assert "invoke_preview_site_layout_tool" in source


def test_p4_contract_records_seventh_tool_and_no_p4_downstream_authority() -> None:
    source = _source(P4_DOC)
    for required in (
        "MCP_TOOL_COUNT=7",
        "MCP_TOOL_7_NAME=preview_site_layout",
        "MCP_TOOL_7_POSITION=7",
        "EXISTING_SIX_TOOL_ORDER_PRESERVED=YES",
        "P4_AUTHORIZED=YES",
        "P5_AUTHORIZED=NO",
        "MCP_TOOL_7_IMPLEMENTED=YES",
        "SITE_LAYOUT_RESULT_IDENTITY=site_validated_layout@1.0.0",
        "SVG_PROJECTION_IDENTITY=validated-layout-svg-projection@1.0.0",
        "MCP_INPUT_AUTHORITY=FIVE_BUSINESS_KEYS_PLUS_SITE_CONSTRAINTS_TRUCK_ACCESS_AND_TRUCK_MANEUVER",
        "P2_VALIDATED_CANDIDATE_SELECTOR_USED=YES",
        "P4_CANDIDATE_SELECTION_IMPLEMENTED=NO",
        "P4_PRODUCTION_FULL_PASS=YES",
        "P4_COMPLETE=YES",
        "P4_BLOCKER=NONE",
        "TOOL7_REAL_FULL_CHAIN_TEST=PASS",
        "NO_CHAT_PARSING=YES",
        "NO_ENGINEERING_FORMULAS_IN_P4=YES",
    ):
        assert required in source
