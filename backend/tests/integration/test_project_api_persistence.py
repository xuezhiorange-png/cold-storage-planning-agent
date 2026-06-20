from pathlib import Path

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.infrastructure.database import create_database_project_service
from cold_storage.modules.projects.infrastructure.orm import Base


def test_project_api_persists_inputs_calculations_and_audit(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    service = create_database_project_service(database_url)
    Base.metadata.create_all(service.engine)
    client = TestClient(create_app(project_service=service))

    created = client.post(
        "/api/v1/projects",
        json={
            "name": "蓝莓加工中心演示项目",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version = created["current_version_number"]

    save_response = client.put(
        f"/api/v1/projects/{project_id}/versions/{version}/inputs",
        json={
            "inputs": {
                "daily_inbound_mass_kg": 25_000,
                "working_time_h_per_day": 16,
                "utilization_factor": 0.85,
                "finished_storage_days": 2.5,
                "packaging_storage_days": 3,
                "main_packaging_storage_days": 3,
                "auxiliary_packaging_storage_days": 30,
                "reserve_factor": 1.05,
            }
        },
    )
    assert save_response.json() == {"success": True}

    validation = client.post(f"/api/v1/projects/{project_id}/versions/{version}/validate").json()
    assert validation["valid"] is True
    assert validation["missing_fields"] == []

    calculation = client.post(
        f"/api/v1/projects/{project_id}/versions/{version}/calculate",
        json={"calculators": ["throughput"]},
    ).json()
    assert calculation["success"] is True
    assert calculation["calculator_name"] == "throughput"

    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version}/calculations"
    ).json()
    assert len(calculations) == 1
    assert calculations[0]["calculator_name"] == "throughput"
    assert calculations[0]["result_snapshot"]["result"]["average_hourly_throughput_kg_h"] == 1562.5

    audit_events = client.get(f"/api/v1/projects/{project_id}/audit-events").json()
    assert [event["action"] for event in audit_events] == [
        "create_project",
        "create_project_version",
        "save_design_inputs",
        "run_project_calculations",
    ]

    zone_plan = client.post(
        f"/api/v1/projects/{project_id}/versions/{version}/zone-plan",
        json={},
    ).json()
    assert zone_plan["calculator_name"] == "cold_room_zone_plan"
    assert zone_plan["result"]["zones"][7]["zone_name"] == "成品间"
    assert zone_plan["result"]["zones"][7]["temperature_band"] == "1~3℃"
    assert zone_plan["result"]["zones"][7]["design_storage_mass_kg"] == 62_500
    assert zone_plan["result"]["zones"][10]["position_count"] == 90
    assert zone_plan["requires_review"] is True

    investment = client.post(
        f"/api/v1/projects/{project_id}/versions/{version}/investment-estimate",
        json={},
    ).json()
    assert investment["calculator_name"] == "investment_estimate"
    assert investment["result"]["total_investment_cny"] == 6_150_420.50
    assert [item["item_name"] for item in investment["result"]["items"]] == [
        "土建及钢结构",
        "冷库制冷设备",
        "高低压配电",
        "住宿及生活区",
        "监控及开厂物资",
    ]

    planning_run = client.post(
        f"/api/v1/projects/{project_id}/versions/{version}/planning-run",
        json={
            "finished_storage_days": 3,
            "main_packaging_storage_days": 7,
            "auxiliary_packaging_storage_days": 15,
            "primary_precooling_working_hours_per_day": 5,
            "secondary_precooling_pallet_weight_kg": 500,
            "secondary_precooling_hours_per_pallet": 2,
            "secondary_precooling_working_hours_per_day": 10,
            "raw_storage_ratio": 0.5,
            "raw_fruit_pallet_weight_kg": 250,
            "finished_goods_pallet_weight_kg": 500,
            "frozen_fruit_ratio": 0.06,
            "frozen_storage_days": 10,
            "frozen_goods_pallet_weight_kg": 500,
        },
    ).json()
    assert planning_run["success"] is True
    assert planning_run["input_snapshot"]["daily_inbound_mass_kg"] == 25_000
    assert planning_run["input_snapshot"]["finished_storage_days"] == 3
    assert planning_run["input_snapshot"]["main_packaging_storage_days"] == 7
    assert planning_run["input_snapshot"]["auxiliary_packaging_storage_days"] == 15
    assert planning_run["zone_plan"]["result"]["planning_parameters"]["raw_storage_ratio"] == 0.5
    assert planning_run["zone_plan"]["result"]["zones"][2]["raw_position_count"] == 23
    assert planning_run["zone_plan"]["result"]["zones"][2]["position_count"] == 24
    assert planning_run["zone_plan"]["result"]["zones"][3]["raw_position_count"] == 10
    assert planning_run["zone_plan"]["result"]["zones"][3]["position_count"] == 12
    assert planning_run["zone_plan"]["result"]["zones"][4]["design_storage_mass_kg"] == 12_500
    assert planning_run["zone_plan"]["result"]["zones"][7]["position_count"] == 150
    assert planning_run["zone_plan"]["result"]["zones"][9]["design_storage_mass_kg"] == 15_000
    assert planning_run["zone_plan"]["result"]["zones"][10]["position_count"] == 137
    assert planning_run["summary"]["total_power_kw"] == 1360.55
    assert planning_run["power_configuration"]["equipment_rows"][0]["name"] == "制冷压缩机组"
    assert (
        planning_run["power_configuration"]["equipment_rows"][0]["area"]
        == "一级预冷、原果暂存间、分选间"
    )
    assert planning_run["power_configuration"]["equipment_rows"][0]["total_power_kw"] == 297.6
    assert planning_run["power_configuration"]["equipment_rows"][6]["area"] == "一级预冷间"
    axial_fan_row = next(
        row
        for row in planning_run["power_configuration"]["equipment_rows"]
        if row["name"] == "轴流风机"
    )
    assert axial_fan_row["quantity"] == (24 + 12) * 4
    assert axial_fan_row["total_power_kw"] == 79.2
    assert planning_run["power_configuration"]["summary_rows"][0]["name"] == "化霜总功率"
    assert planning_run["power_configuration"]["summary_rows"][1]["name"] == "设备运行功率"
    assert planning_run["power_configuration"]["summary_rows"][2] == {
        "name": "制冷总功率",
        "basis": "化霜同时系数30% + 设备运行同时系数90%",
        "total_power_kw": 1076.15,
    }
    assert planning_run["power_configuration"]["summary_rows"][-1]["total_power_kw"] == 1360.55
    assert planning_run["power_configuration"]["requires_review"] is True

    client.post(f"/api/v1/projects/{project_id}/versions/{version}/approve")
    locked_response = client.put(
        f"/api/v1/projects/{project_id}/versions/{version}/inputs",
        json={"inputs": {"daily_inbound_mass_kg": 30_000}},
    ).json()
    assert locked_response["error"]["code"] == "PROJECT_VERSION_LOCKED"


def test_project_api_reads_versions_from_database_between_app_instances(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    service = create_database_project_service(database_url)
    Base.metadata.create_all(service.engine)
    first_client = TestClient(create_app(project_service=service))

    created = first_client.post(
        "/api/v1/projects",
        json={"name": "持久化项目", "location": "辽宁", "product_category": "blueberry"},
    ).json()

    second_service = create_database_project_service(database_url)
    second_client = TestClient(create_app(project_service=second_service))
    project = second_client.get(f"/api/v1/projects/{created['id']}").json()
    versions = second_client.get(f"/api/v1/projects/{created['id']}/versions").json()

    assert project["name"] == "持久化项目"
    assert versions[0]["version_number"] == 1


def test_demo_overview_api_returns_all_module_samples() -> None:
    client = TestClient(create_app())

    overview = client.get("/api/v1/demo/overview").json()

    assert overview["overall_status"]["module_count"] == 13
    assert overview["modules"][0]["module"] == "项目管理"
    assert overview["modules"][5]["module"] == "投资测算"
    assert overview["modules"][6]["module"] == "用电配置"
    assert overview["modules"][10]["sample"]["word_report"] == "方案书草稿.docx"
