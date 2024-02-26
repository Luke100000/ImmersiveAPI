from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh


def get_data() -> pd.DataFrame:
    url = "http://conczin.net:9090/api/v1/query_range"

    params = {
        "query": 'flow_watt{handler!~"battery_abs|load"}',
        "start": (datetime.utcnow() - timedelta(minutes=220)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "end": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "step": "5m",
    }

    response = requests.get(url, params=params)

    data = {}
    for metric in response.json()["data"]["result"]:
        data[metric["metric"]["handler"]] = np.asarray(
            [float(v[1]) for v in metric["values"]]
        )

    min_length = min([len(v) for v in data.values()])

    return pd.DataFrame({k: v[-min_length:] for k, v in data.items()})


def main():
    data = get_data()

    data["home"] = np.absolute(data["home"])
    data["battery"] = -data["battery"]

    st.line_chart(data, width=5)

    st_autorefresh(interval=10000)

    horizon = 60 // 5
    cols = st.columns(len(data.columns))
    for i, metric in enumerate(data.columns):
        value = data[metric].iloc[-horizon:].mean()
        last_value = data[metric].iloc[-horizon * 2 : -horizon].mean()
        cols[i].metric(
            metric.capitalize(),
            f"{value / 1000:.2f} kW",
            delta=f"{(value - last_value) / 1000:.2f} kW",
            delta_color="normal"
        )


if __name__ == "__main__":
    main()
