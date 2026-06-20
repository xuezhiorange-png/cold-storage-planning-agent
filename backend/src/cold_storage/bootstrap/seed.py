from cold_storage.modules.calculations.domain.coefficients import CalculationCoefficient


def demo_coefficients() -> list[CalculationCoefficient]:
    return [
        CalculationCoefficient(
            code="blueberry_effective_volume_loading_kg_m3",
            name="蓝莓有效容积储量演示值",
            value=280,
            unit="kg/m3",
            category="storage",
            source_type="demo",
            source_reference="V1演示数据，未作为正式标准",
            version="demo-1",
            validity_status="unverified",
            approval_status="unverified",
            requires_review=True,
        )
    ]


if __name__ == "__main__":
    for coefficient in demo_coefficients():
        print(f"seed coefficient: {coefficient.code} {coefficient.validity_status}")
