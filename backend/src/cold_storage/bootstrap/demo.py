from cold_storage.modules.calculations.domain.inputs import ThroughputInput
from cold_storage.modules.calculations.domain.service import CalculationService


def main() -> None:
    result = CalculationService().run_throughput(
        ThroughputInput(
            daily_inbound_mass_kg=25_000,
            working_time_h_per_day=16,
            utilization_factor=0.85,
        )
    )
    print("蓝莓加工中心演示项目")
    print(result.result)
    print("requires_review:", result.requires_review)


if __name__ == "__main__":
    main()
