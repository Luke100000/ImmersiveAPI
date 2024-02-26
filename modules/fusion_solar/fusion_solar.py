import os

from fastapi import FastAPI
from starlette.responses import Response

# noinspection SpellCheckingInspection
translation = {
    "neteco.pvms.devTypeLangKey.string": "pv",
    "neteco.pvms.KPI.kpiView.electricalLoad": "load",
    "neteco.pvms.devTypeLangKey.energy_store": "battery_abs",
}


def initFusionSolar(app: FastAPI):
    from fusion_solar_py.client import FusionSolarClient, BatteryStatus

    client = FusionSolarClient(
        os.getenv("FUSION_SOLAR_USER"),
        os.getenv("FUSION_SOLAR_PASSWORD"),
    )

    plant_id = os.getenv("FUSION_SOLAR_PLANT_ID")
    battery_id = os.getenv("FUSION_SOLAR_BATTERY_ID")

    @app.get("/fusion_solar/metrics")
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
        data: BatteryStatus = client.get_battery_basic_stats(battery_id)
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
