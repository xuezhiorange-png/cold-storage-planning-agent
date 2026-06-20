from dataclasses import dataclass


@dataclass(frozen=True)
class DesignScheme:
    scheme_name: str
    scheme_type: str
    room_schedule: list[dict[str, object]]
    score_breakdown: dict[str, float]
    assumptions: list[str]
    warnings: list[str]


class SchemeService:
    def generate(self, total_capacity_kg: float, max_room_capacity_kg: float) -> list[DesignScheme]:
        patterns = [
            ("少量大冷间方案", "large_rooms", 2),
            ("多个小冷间方案", "small_rooms", 5),
            ("平衡方案", "balanced", 3),
        ]
        schemes: list[DesignScheme] = []
        for name, scheme_type, count in patterns:
            room_capacity = min(max_room_capacity_kg, total_capacity_kg / count)
            score = {
                "capacity_satisfaction": min(room_capacity * count / total_capacity_kg, 1),
                "peak_resilience": 0.7 if scheme_type == "large_rooms" else 0.85,
                "operation_flexibility": 0.65 if scheme_type == "large_rooms" else 0.9,
                "area_utilization": 0.88 if scheme_type == "large_rooms" else 0.78,
            }
            schemes.append(
                DesignScheme(
                    scheme_name=name,
                    scheme_type=scheme_type,
                    room_schedule=[
                        {"room_name": f"{name}-{index + 1}", "design_capacity_kg": room_capacity}
                        for index in range(count)
                    ],
                    score_breakdown=score,
                    assumptions=["评分权重为V1演示配置，requires_review=true"],
                    warnings=["方案为概念规划比较，不代表施工图"],
                )
            )
        return schemes
