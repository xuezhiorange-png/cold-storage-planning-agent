from cold_storage.modules.planning_agent.application.agent_service import LegacyPlanningAgentService
from cold_storage.modules.planning_agent.infrastructure.fake_gateways import FakeAgentModelGateway
from cold_storage.modules.projects.application.service import ProjectService


def _approve_version(service: ProjectService, project_id: str, version_number: int) -> None:
    """Helper: walk a version through the state machine to approved status."""
    service.submit_version(project_id, version_number)
    service.review_version(project_id, version_number)
    service.approve_version(project_id, version_number)


def test_approved_project_version_cannot_be_modified() -> None:
    service = ProjectService()
    project = service.create_project(
        name="蓝莓加工中心演示项目",
        location="山东",
        product_category="blueberry",
    )
    version = service.create_version(project.id, "初始版本")
    _approve_version(service, project.id, version.version_number)

    result = service.save_inputs(
        project.id,
        version.version_number,
        {"daily_inbound_mass_kg": 25_000},
        actor="tester",
    )

    assert result.success is False
    assert result.error_code == "PROJECT_VERSION_LOCKED"
    assert service.audit_events[-1].action == "reject_modify_approved_version"


def test_agent_extracts_requirements_without_calculating_values() -> None:
    agent = LegacyPlanningAgentService(model_gateway=FakeAgentModelGateway())

    response = agent.handle_message("新建蓝莓项目，日入库25吨，每天工作16小时")

    # New gateway returns decision_type and tool_requests instead of raw param extraction
    assert response.structured_output["decision_type"] == "propose_tools"
    assert "cooling_capacity_kw" not in response.structured_output
    assert "planning.calculate_throughput_inventory_area" in response.tool_calls
    assert "施工图" not in response.message
