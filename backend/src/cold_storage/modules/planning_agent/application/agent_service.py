from dataclasses import dataclass

from cold_storage.modules.planning_agent.domain.gateways import ModelGateway


@dataclass(frozen=True)
class AgentResponse:
    message: str
    structured_output: dict[str, object]
    tool_calls: list[str]


class PlanningAgentService:
    def __init__(self, model_gateway: ModelGateway) -> None:
        self.model_gateway = model_gateway

    def handle_message(self, message: str) -> AgentResponse:
        model_response = self.model_gateway.complete(message)
        allowed = {
            "project_name",
            "location",
            "product_types",
            "daily_inbound_mass_kg",
            "working_time_h_per_day",
            "storage_days",
            "utilization_factor",
        }
        structured = {
            key: value for key, value in model_response.structured_output.items() if key in allowed
        }
        return AgentResponse(
            message=(
                "已提取可确认的规划参数，并生成参数变更建议。"
                "工程数值将由确定性计算器完成，结果需专业人员复核。"
            ),
            structured_output=structured,
            tool_calls=["propose_project_input_changes"],
        )
