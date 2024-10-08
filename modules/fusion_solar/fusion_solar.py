import os

from fusion_solar_py.client import FusionSolarClient, BatteryStatus
from starlette.responses import Response

from main import Configurator

# noinspection SpellCheckingInspection
translation = {
    "neteco.pvms.devTypeLangKey.string": "pv",
    "neteco.pvms.KPI.kpiView.electricalLoad": "load",
    "neteco.pvms.devTypeLangKey.energy_store": "battery_abs",
}


def init(configurator: Configurator):
    configurator.register("FusionSolar", "Metrics endpoint for Huawei FusionSolar.")

    client = FusionSolarClient(
        os.getenv("FUSION_SOLAR_USER"),
        os.getenv("FUSION_SOLAR_PASSWORD"),
    )

    plant_id = os.getenv("FUSION_SOLAR_PLANT_ID")
    battery_id = os.getenv("FUSION_SOLAR_BATTERY_ID")

    def safe_float(value: str) -> float:
        try:
            return float(value)
        except ValueError:
            return 0.0

    def get_battery_basic_stats() -> BatteryStatus:
        battery_stats = client.get_battery_status(battery_id)
        return BatteryStatus(
            state_of_charge=safe_float(battery_stats[8]["realValue"]),
            rated_capacity=safe_float(battery_stats[2]["realValue"]),
            operating_status=battery_stats[0]["value"],
            backup_time=battery_stats[3]["value"],
            bus_voltage=safe_float(battery_stats[7]["realValue"]),
            total_charged_today_kwh=safe_float(battery_stats[4]["realValue"]),
            total_discharged_today_kwh=safe_float(battery_stats[5]["realValue"]),
            current_charge_discharge_kw=safe_float(battery_stats[6]["realValue"]),
        )

    @configurator.get("/fusion_solar/metrics")
    def get_fusion():
        metrics = []
        values = {}

        # Extract values from plant flow
        data: dict = client.get_plant_flow(plant_id)
        for node in data["data"]["flow"]["nodes"]:
            label = node["description"]["label"]
            value = node["description"]["value"]
            if value:
                if label in translation:
                    label = translation[label]
                else:
                    label = label.replace(".", "_")
                value = float(value.replace("kW", "").strip()) * 1000
                values[label] = value

        # Battery
        data: BatteryStatus = get_battery_basic_stats()
        metrics.append(f"battery_state_of_charge {data.state_of_charge / 100}")
        metrics.append(f"battery_bus_voltage {data.bus_voltage}")

        # The home always consumes
        values["home"] = -values["load"]

        # Battery flow can be negative, so lets also provide the more accurate battery charge value
        # We also invert the battery to make it consistent with the rest
        values["battery"] = -data.current_charge_discharge_kw * 1000

        # Grid is not available in the API, so we calculate it
        values["grid"] = -(values["home"] + values["pv"] + values["battery"])

        del values["load"]
        del values["battery_abs"]

        for key, value in values.items():
            metrics.append(f'flow_watt{{handler="{key}"}} {value}')

        return Response("\n".join(metrics), media_type="text/plain")
