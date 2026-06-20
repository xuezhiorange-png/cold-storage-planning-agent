from cold_storage.modules.planning_agent.application.agent_service import PlanningAgentService
from cold_storage.modules.planning_agent.infrastructure.fake_gateways import FakeModelGateway
from cold_storage.modules.projects.application.service import ProjectService


def test_approved_project_version_cannot_be_modified() -> None:
    service = ProjectService()
    project = service.create_project(
        name="蓝莓加工中心演示项目",
        location="山东",
        product_category="blueberry",
    )
    version = service.create_version(project.id, "初始版本")
    service.approve_version(project.id, version.version_number)

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
    agent = PlanningAgentService(model_gateway=FakeModelGateway())

    response = agent.handle_message("新建蓝莓项目，日入库25吨，每天工作16小时")

    assert response.structured_output["daily_inbound_mass_kg"] == 25_000
    assert response.structured_output["working_time_h_per_day"] == 16
    assert "cooling_capacity_kw" not in response.structured_output
    assert response.tool_calls == ["propose_project_input_changes"]
    assert "施工图" not in response.message
