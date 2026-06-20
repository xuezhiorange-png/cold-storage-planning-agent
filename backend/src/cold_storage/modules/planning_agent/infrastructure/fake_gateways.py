import re

from cold_storage.modules.planning_agent.domain.gateways import ModelResponse


class FakeModelGateway:
    def complete(self, prompt: str) -> ModelResponse:
        output: dict[str, object] = {}
        if "蓝莓" in prompt:
            output["product_types"] = ["blueberry"]
        ton_match = re.search(r"(\d+(?:\.\d+)?)\s*吨", prompt)
        if ton_match:
            daily_mass_kg = float(ton_match.group(1)) * 1000
            output["daily_inbound_mass_kg"] = (
                int(daily_mass_kg) if daily_mass_kg == int(daily_mass_kg) else daily_mass_kg
            )
        hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|h)", prompt)
        if hour_match:
            working_hours = float(hour_match.group(1))
            output["working_time_h_per_day"] = (
                int(working_hours) if working_hours == int(working_hours) else working_hours
            )
        return ModelResponse(text="fake extraction", structured_output=output)


class FakeEmbeddingGateway:
    def embed(self, text: str) -> list[float]:
        base = sum(ord(char) for char in text) or 1
        return [float((base + index) % 97) / 97 for index in range(8)]
