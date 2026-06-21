from cold_storage.bootstrap.demo_overview import build_demo_overview


def test_demo_overview_contains_sample_data_for_all_modules() -> None:
    overview = build_demo_overview()

    assert overview["project"]["name"] == "蓝莓加工厂"
    assert overview["project"]["overview_text"] == (
        "蓝莓加工厂覆盖定植面积1250亩，按20吨/千亩对应峰值产量25吨，主要定植品种为蓝莓"
    )
    assert overview["overall_status"]["module_count"] == 13
    assert overview["overall_status"]["requires_review_count"] >= 5
    assert overview["overall_status"]["total_area_m2"] == 1813.57
    assert overview["overall_status"]["total_investment_cny"] == 6_150_420.50
    assert [module["module"] for module in overview["modules"]] == [
        "项目管理",
        "设计参数",
        "参数完整度",
        "确定性计算",
        "冷间区域规划",
        "投资测算",
        "用电配置",
        "方案生成",
        "知识依据",
        "规划Agent",
        "报告输出",
        "版本历史",
        "审计记录",
    ]
    assert overview["modules"][4]["sample"]["zones"][7]["zone_name"] == "成品间"
    assert [item["item_name"] for item in overview["modules"][5]["sample"]["items"]] == [
        "土建及钢结构",
        "冷库制冷设备",
        "高低压配电",
        "住宿及生活区",
        "监控及开厂物资",
    ]
    assert overview["modules"][6]["sample"]["items"][0]["category"] == "制冷系统"
    axial_fan_row = next(
        row
        for row in overview["modules"][6]["sample"]["equipment_rows"]
        if row["name"] == "轴流风机"
    )
    assert axial_fan_row["quantity"] == (24 + 8) * 4
    assert axial_fan_row["total_power_kw"] == 70.4
    assert (
        "planning.calculate_throughput_inventory_area"
        in overview["modules"][9]["sample"]["tool_calls"]
    )
