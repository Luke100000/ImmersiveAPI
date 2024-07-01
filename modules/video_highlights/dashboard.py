import base64
from dataclasses import dataclass
from io import BytesIO

import dash_bootstrap_components as dbc
from PIL import Image
from dash import Dash, html, dcc, Input, Output, State, DiskcacheManager
from dash_bootstrap_templates import load_figure_template
from plotly import express as px

from modules.video_highlights.labels import (
    negative_labels as default_negative_labels,
    positive_labels as default_positive_labels,
)
from modules.video_highlights.processor import predict

dbc_css = "https://cdn.jsdelivr.net/gh/AnnMarieW/dash-bootstrap-templates/dbc.min.css"
load_figure_template("darkly")

# Diskcache for non-production apps when developing locally
import diskcache

cache = diskcache.Cache("./cache/video_highlights")
background_callback_manager = DiskcacheManager(cache)


@dataclass
class Highlight:
    time: float
    similarity: float
    image: Image.Image


def pillow_image_to_base64(img):
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def format_time(seconds):
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes:02}:{seconds:02}"


def to_labels(label):
    return [l.strip() for l in str(label).split(",")]


def generate(
    url,
    positive_labels,
    negative_labels,
    set_progress,
    resolution: float,
    enhance: bool,
):
    similarity, times, frames = predict(
        url,
        to_labels(positive_labels) if positive_labels else default_positive_labels,
        to_labels(negative_labels) if negative_labels else default_negative_labels,
        resolution=resolution,
        enhance=enhance,
        report_progress=set_progress,
    )
    highlights = [
        Highlight(
            time,
            similarity[int(time * resolution)],
            frame,
        )
        for time, frame in zip(times, frames)
    ]
    return highlights, similarity


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
                html.H3("Video Highlight Extractor"),
                html.P(
                    "Extracts prompted key moments from video material. By default, aesthetically pleasing images are extracted."
                ),
                dbc.Input(id="url-input", placeholder="Enter video URL", type="text"),
                html.Div(
                    children=[
                        dbc.Input(
                            id="positive-labels-input",
                            placeholder="Enter labels (optional)",
                            type="text",
                        ),
                        dbc.Input(
                            id="negative-labels-input",
                            placeholder="Enter negative labels (optional)",
                            type="text",
                        ),
                    ],
                    style={"display": "flex", "align-items": "center"},
                ),
                html.Span(
                    "Resolution: ", style={"margin-left": "12px", "margon-right": "8px"}
                ),
                dbc.Select(
                    id="resolution-dropdown",
                    options=[
                        {"label": "Low", "value": 0.5},
                        {"label": "Default", "value": 2},
                        {"label": "High", "value": 4},
                    ],
                    value=2,
                    style={"display": "inline-block", "width": "200px"},
                ),
                html.Span(
                    "Enhance: ", style={"margin-left": "12px", "margon-right": "8px"}
                ),
                dbc.Select(
                    id="enhance-dropdown",
                    options=[
                        {"label": "Yes", "value": True},
                        {"label": "No (faster, less accuracy)", "value": False},
                    ],
                    value=2,
                    style={"display": "inline-block", "width": "200px"},
                ),
                html.Br(),
                html.Div(
                    children=[
                        dbc.Button("Generate", id="generate-button", color="primary"),
                        html.P(
                            "",
                            id="progress-component",
                            style={
                                "margin-left": "12px",
                                "padding-top": "0px",
                                "margin-bottom": "0px",
                            },
                        ),
                    ],
                    style={"display": "flex", "align-items": "center"},
                ),
                html.Br(),
                dcc.Loading(
                    id="loading-1",
                    type="default",
                    children=[
                        html.Div(
                            id="image-list",
                            style={"display": "flex", "align-items": "center"},
                        ),
                        html.Div(id="heatstrip-container"),
                    ],
                ),
            ],
            style={"padding": "96px"},
        )

    app.layout = serve_layout

    @app.callback(
        Output("image-list", "children"),
        Output("heatstrip-container", "children"),
        Input("generate-button", "n_clicks"),
        State("url-input", "value"),
        State("positive-labels-input", "value"),
        State("negative-labels-input", "value"),
        State("resolution-dropdown", "value"),
        State("enhance-dropdown", "value"),
        prevent_initial_call=True,
        background=True,
        manager=background_callback_manager,
        progress=[
            Output("progress-component", "children"),
        ],
        running=[
            (Output("generate-button", "disabled"), True, False),
        ],
    )
    def generate_callback(
        set_progress, _, url, positive_labels, negative_labels, resolution, enhance
    ):
        if url is None:
            set_progress("Please enter a URL")
            return [], []

        try:
            highlights, heatstrip = generate(
                url,
                positive_labels,
                negative_labels,
                lambda x: set_progress([x]),
                resolution=float(resolution),
                enhance=enhance == "True",
            )
        except Exception as e:
            set_progress(e)
            return [], []

        set_progress("Done")

        image_elements = [
            html.Div(
                [
                    html.Img(
                        src=f"data:image/png;base64,{pillow_image_to_base64(highlight.image)}",
                        style={
                            "display": "block",
                            "width": "100%",
                            "height": "100%",
                            "object-fit": "cover",
                        },
                    ),
                    dcc.Markdown(
                        f"Timestamp: {format_time(highlight.time)}  \nSimilarity: {highlight.similarity:.0%}  \n[View]({url}&t={int(highlight.time)})",
                        style={"margin": "10px"},
                    ),
                ],
                style={
                    "display": "inline-block",
                    "margin": "10px",
                    "position": "relative",
                },
            )
            for highlight in highlights
        ]

        figure = px.imshow(
            heatstrip.reshape(1, -1),
            labels=dict(x="Seconds"),
            x=list(range(len(heatstrip))),
            y=[0],
            color_continuous_scale="hot",
            template="darkly",
            aspect="auto",
        )
        figure.update_layout(
            title=None,
            yaxis=dict(title=None, showticklabels=False),
            xaxis=dict(ticksuffix="s"),
            height=300,
            margin=dict(l=20, r=20, t=20, b=20),
        )
        heatstrip_element = dcc.Graph(figure=figure)

        return image_elements, heatstrip_element

    return app


if __name__ == "__main__":
    get_app().run(debug=True)
