"""Demo weight set seed — unverified, for demonstration only."""

from __future__ import annotations

from decimal import Decimal

from cold_storage.modules.schemes.domain.models import SchemeWeightSet, WeightCriterion

DEMO_WEIGHT_SET_ID = "demo-weight-set-001"


def demo_weight_set() -> SchemeWeightSet:
    """Return a demo weight set marked as unverified."""
    return SchemeWeightSet(
        id=DEMO_WEIGHT_SET_ID,
        code="demo-v1",
        name="V1 演示权重集（待复核）",
        revision=1,
        status="unverified",
        source_type="demo",
        criteria=[
            WeightCriterion(
                criterion_code="total_area_m2",
                weight=Decimal("0.10"),
                direction="lower_is_better",
                description="总建筑面积",
            ),
            WeightCriterion(
                criterion_code="total_position_count",
                weight=Decimal("0.10"),
                direction="higher_is_better",
                description="总板位数",
            ),
            WeightCriterion(
                criterion_code="room_module_count",
                weight=Decimal("0.05"),
                direction="lower_is_better",
                description="房间模块数",
            ),
            WeightCriterion(
                criterion_code="door_count",
                weight=Decimal("0.05"),
                direction="lower_is_better",
                description="门数量",
            ),
            WeightCriterion(
                criterion_code="partition_length_proxy_m",
                weight=Decimal("0.05"),
                direction="lower_is_better",
                description="隔墙代理长度",
            ),
            WeightCriterion(
                criterion_code="investment_cny",
                weight=Decimal("0.30"),
                direction="lower_is_better",
                description="总投资",
            ),
            WeightCriterion(
                criterion_code="installed_power_kw_e",
                weight=Decimal("0.35"),
                direction="lower_is_better",
                description="电气装机功率",
            ),
        ],
        requires_review=True,
    )
