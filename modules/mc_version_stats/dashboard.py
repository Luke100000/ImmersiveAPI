import re
from collections import defaultdict

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.express
from cachetools import cached, TTLCache
from dash import Dash, html, dcc, Output, Input
from dash_bootstrap_templates import load_figure_template
from packaging.version import parse, Version
from plotly.subplots import make_subplots

from modules.mc_version_stats.data import get_cached_mods
from modules.mc_version_stats.mod import Mod

dbc_css = "https://cdn.jsdelivr.net/gh/AnnMarieW/dash-bootstrap-templates/dbc.min.css"
load_figure_template("darkly")


def is_version(input_string):
    return bool(re.match(r"^[0-9.]+$", input_string))


def safe_parse(v):
    # noinspection PyBroadException
    try:
        return parse(v)
    except Exception:
        return Version("0.0.0")


def sort_df(df: pd.DataFrame):
    df["ParsedVersion"] = df["Version"].apply(safe_parse)
    df = df.sort_values("ParsedVersion", ascending=True)
    df = df.drop(columns=["ParsedVersion"])
    return df


@cached(
    cache=TTLCache(maxsize=8, ttl=3600),
    key=lambda mods, span, version_list, sampling: hash(
        (len(mods), span, sampling, *version_list)
    ),
)
def get_heatmap(mods: list, span: int, version_list: list, sampling: int):
    heatmap = np.zeros(dtype=int, shape=(len(version_list), span // sampling + 1))
    version_to_index = {version: i for i, version in enumerate(version_list)}
    for mod in mods:
        cached_versions = set()
        for version in mod.versions:
            if (
                version.game_version not in cached_versions
                and version.game_version in version_to_index
                and version.age < span
            ):
                cached_versions.add(version.game_version)
                index = version_to_index[version.game_version]
                heatmap[index, version.age // sampling] += 1
    return heatmap


def aggregate_others(df, threshold):
    threshold = df["Downloads"].max() * float(threshold)
    agg = df.loc[df["Extrapolated Downloads"] < threshold].sum().to_frame().T
    agg["Version"] = "Other"
    df = pd.concat(
        [
            agg,
            df.loc[df["Extrapolated Downloads"] >= threshold],
        ]
    )
    return sort_df(df)


def filter_must_haves(mod: Mod):
    categories = set(mod.categories)
    categories = categories.difference({"optimization", "library", "utility"})
    return len(categories) > 0


def get_app(route: str = None):
    app = Dash(
        __name__,
        requests_pathname_prefix=route,
        external_stylesheets=[dbc.themes.DARKLY, dbc.icons.FONT_AWESOME, dbc_css],
        suppress_callback_exceptions=True,
    )

    def serve_layout():
        return html.Div(
            [
                # header
                html.H3("Minecraft Modding Version Stats Dashboard", id="header"),
                html.Div(
                    [
                        dbc.Select(
                            id="timeSpan-dropdown",
                            options=[
                                {"label": "Week", "value": 7},
                                {"label": "Month", "value": 30},
                                {"label": "Quarter", "value": 90},
                                {"label": "Year", "value": 365},
                                {"label": "All Time", "value": 365 * 10},
                            ],
                            value=90,
                            style={"display": "inline-block", "width": "200px"},
                        ),
                        dbc.Select(
                            id="threshold-dropdown",
                            options=[
                                {"label": "1%", "value": 0.01},
                                {"label": "0.1%", "value": 0.001},
                                {"label": "0.01%", "value": 0.0001},
                            ],
                            value=0.05,
                            style={"display": "inline-block", "width": "200px"},
                        ),
                        dbc.Select(
                            id="index-dropdown",
                            options=[
                                {"label": "Patch Version", "value": "patch"},
                                {"label": "Minor Version", "value": "major"},
                            ],
                            value="patch",
                            style={"display": "inline-block", "width": "200px"},
                        ),
                        dbc.Select(
                            id="filter-dropdown",
                            options=[
                                {"label": "Count all Mods", "value": "all"},
                                {"label": "Ignore Libraries", "value": "no_libraries"},
                                {
                                    "label": "Ignore Must-Have Mods",
                                    "value": "no_basics",
                                },
                            ],
                            value="no_libraries",
                            style={"display": "inline-block", "width": "200px"},
                        ),
                    ],
                    style={"display": "flex", "align-items": "center"},
                ),
                dcc.Graph(id="download-graph"),
                dcc.Graph(id="update-heatmap"),
                html.Div(
                    [
                        dcc.Graph(id="releases-graph", style={"width": "50%"}),
                        dcc.Graph(id="updates-graph", style={"width": "50%"}),
                    ],
                    style={
                        "display": "flex",
                        "flex-direction": "row",
                        "width": "95%",
                    },
                ),
                html.Div(
                    [
                        dcc.Graph(id="mod-loader-graph", style={"width": "50%"}),
                        dcc.Graph(id="website-graph", style={"width": "50%"}),
                    ],
                    style={
                        "display": "flex",
                        "flex-direction": "row",
                        "width": "95%",
                    },
                ),
                dcc.Graph(id="category-graph"),
                dcc.Markdown(
                    f"""
                    ---------------------------------------
                    *Updates continuously from Modrinth and CurseForge*
                    
                    {len(get_cached_mods())} mods scanned, {sum([len(mod.versions) for mod in get_cached_mods()])} versions scanned.
                    
                    * Estimated Downloads: Estimated fraction of downloads on versions released before the time span
                    * Extrapolated Downloads: Ongoing downloads on the newest version, extrapolated to the full time span
                    """
                ),
            ],
            style={"padding": "64px"},
        )

    app.layout = serve_layout

    @app.callback(
        Output("download-graph", "figure"),
        Output("update-heatmap", "figure"),
        Output("releases-graph", "figure"),
        Output("updates-graph", "figure"),
        Output("mod-loader-graph", "figure"),
        Output("website-graph", "figure"),
        Output("category-graph", "figure"),
        Input("timeSpan-dropdown", "value"),
        Input("threshold-dropdown", "value"),
        Input("index-dropdown", "value"),
        Input("filter-dropdown", "value"),
    )
    def update_output(span: int, threshold: float, index_name: str, filter_name: str):
        span = int(span)
        mods = get_cached_mods()

        if filter_name == "no_libraries":
            mods = [mod for mod in mods if "library" not in mod.categories]
        elif filter_name == "no_basics":
            mods = [mod for mod in mods if filter_must_haves(mod)]

        mod_loaders = set()
        websites = set()

        buckets_downloads_estimated = defaultdict(int)
        buckets_downloads_extrapolated = defaultdict(int)
        buckets_downloads_confirmed = defaultdict(int)
        buckets_releases = defaultdict(int)
        buckets_updates = defaultdict(int)

        buckets_mod_loader = defaultdict(lambda: defaultdict(int))
        buckets_website = defaultdict(lambda: defaultdict(int))

        categories = defaultdict(lambda: defaultdict(int))
        for mod in mods:
            for category in mod.categories:
                categories[mod.website][category] += 1

            unique_versions = len(mod.unique_versions)

            duplicates = set()
            for version in mod.versions:
                if is_version(version.game_version):
                    index = (
                        version.game_version
                        if index_name == "patch"
                        else ".".join(version.game_version.split(".")[:2])
                    )
                    buckets_downloads_estimated[index] += (
                        version.get_discounted_downloads(
                            int(span), extrapolate=False, interpolate=True
                        )
                        / unique_versions
                    )
                    buckets_downloads_extrapolated[index] += (
                        version.get_discounted_downloads(
                            int(span), extrapolate=True, interpolate=True
                        )
                        / unique_versions
                    )
                    buckets_downloads_confirmed[index] += (
                        version.get_discounted_downloads(
                            int(span), extrapolate=False, interpolate=False
                        )
                        / unique_versions
                    )

                    if version.age < span:
                        buckets_releases[index] += 1

                        if index not in duplicates:
                            duplicates.add(index)
                            buckets_updates[index] += 1

                            buckets_website[index][mod.website] += 1
                            websites.add(mod.website)

                        if version.mod_loader not in duplicates:
                            duplicates.add(version.mod_loader)
                            buckets_mod_loader[index][version.mod_loader] += 1
                            mod_loaders.add(version.mod_loader)

        data = [
            {
                "Version": k,
                "Downloads": buckets_downloads_confirmed[k],
                "Estimated Downloads": buckets_downloads_estimated[k],
                "Extrapolated Downloads": buckets_downloads_extrapolated[k],
                "Releases": buckets_releases[k],
                "Updates": buckets_updates[k],
            }
            for k in buckets_downloads_estimated.keys()
        ]
        df = pd.DataFrame(data)

        df_websites = sort_df(
            pd.DataFrame(
                [
                    {
                        "Version": k,
                        "Website": website,
                        "Count": count,
                    }
                    for k in buckets_website.keys()
                    for website, count in buckets_website[k].items()
                ]
            )
        )

        df_mod_loaders = sort_df(
            pd.DataFrame(
                [
                    {
                        "Version": k,
                        "Mod Loader": mod_loader,
                        "Count": count,
                    }
                    for k in buckets_mod_loader.keys()
                    for mod_loader, count in buckets_mod_loader[k].items()
                ]
            )
        )

        df_categories = pd.DataFrame(
            [
                {
                    "Website": website,
                    "Category": category,
                    "Count": count,
                }
                for website in websites
                for category, count in categories[website].items()
            ]
        )

        df = aggregate_others(df, threshold)

        f_downloads = make_subplots(rows=1, cols=1)
        f_downloads.update_layout(barmode="stack")
        f_downloads.add_bar(
            x=df["Version"],
            y=df["Downloads"],
            name="Confirmed",
        )
        f_downloads.add_bar(
            x=df["Version"],
            y=df["Estimated Downloads"] - df["Downloads"],
            name="Estimated",
        )
        f_downloads.add_bar(
            x=df["Version"],
            y=df["Extrapolated Downloads"] - df["Estimated Downloads"],
            name="Extrapolated",
        )
        f_downloads.update_layout(barmode="stack")

        # Visualize updates using a heatmap
        heatmap_sub_samping = 1 + span // 256
        version_list = list(df["Version"])
        version_list.remove("Other")
        heatmap = get_heatmap(mods, span, version_list, heatmap_sub_samping)
        f_heatmap = plotly.express.imshow(
            heatmap,
            y=list(version_list),
            x=list(range(0, span + 1, heatmap_sub_samping)),
            title="Mod Updates over age in days",
            aspect="auto",
            color_continuous_scale="hot",
            template="darkly",
        )
        f_heatmap.update_xaxes(autorange="reversed")

        f_releases = plotly.express.bar(
            df,
            x="Version",
            y="Releases",
            title="Version Releases",
            labels={"Version": "Version", "Releases": "Releases"},
            template="darkly",
        )

        f_updates = plotly.express.bar(
            df,
            x="Version",
            y="Updates",
            title="Mod Updates",
            labels={"Version": "Version", "Updates": "Updates"},
            template="darkly",
        )

        f_loader = plotly.express.bar(
            df_mod_loaders,
            x="Version",
            y="Count",
            color="Mod Loader",
            title="Mod Loader",
            template="darkly",
            barmode="stack",
        )

        f_websites = plotly.express.bar(
            df_websites,
            x="Version",
            y="Count",
            color="Website",
            title="Website",
            template="darkly",
            barmode="stack",
        )

        f_tags = plotly.express.pie(
            (
                df_categories.sort_values(by="Count", ascending=False)
                .groupby("Website")
                .head(10)
            ),
            names="Category",
            values="Count",
            title="Categories by Website",
            template="darkly",
            facet_col="Website",
        )
        f_tags.update_traces(textinfo="label+value")

        return (
            f_downloads,
            f_heatmap,
            f_releases,
            f_updates,
            f_loader,
            f_websites,
            f_tags,
        )

    return app


if __name__ == "__main__":
    get_app().run(debug=True)
