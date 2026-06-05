#!/usr/bin/env python3
"""
Interactive scatter plot: commercial aircraft range vs. passenger capacity.
Run:  python app.py          (auto-scrapes if no data file found)
      python app.py --fresh  (force re-scrape)
Then open http://127.0.0.1:8050/
"""

import json
import sys
import subprocess
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dash import Dash, dcc, html, Input, Output

DATA_FILE = Path("aircraft_data.json")


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    if not DATA_FILE.exists():
        print("No data file found — running scraper …")
        subprocess.run([sys.executable, "scrape.py"], check=True)

    raw = json.loads(DATA_FILE.read_text())
    df = pd.DataFrame(raw)
    df = df.dropna(subset=["range_km", "capacity"])
    df["manufacturer"] = df["manufacturer"].fillna("Unknown")
    df["first_flight"] = pd.to_numeric(df["first_flight"], errors="coerce")
    df = df[df["range_km"].between(200, 22_000)]
    df = df[df["capacity"].between(10, 900)]
    df = df[df["first_flight"].between(1940, 2030) | df["first_flight"].isna()]
    df = df.reset_index(drop=True)
    return df


# ── App ───────────────────────────────────────────────────────────────────────

PALETTE = px.colors.qualitative.Plotly + px.colors.qualitative.Dark24 + px.colors.qualitative.Light24


def build_app(df: pd.DataFrame) -> Dash:
    manufacturers = sorted(df["manufacturer"].unique())
    color_map = {m: PALETTE[i % len(PALETTE)] for i, m in enumerate(manufacturers)}

    valid_years = df["first_flight"].dropna().astype(int)
    year_min, year_max = int(valid_years.min()), int(valid_years.max())
    year_marks = {y: str(y) for y in range(year_min, year_max + 1, 5)}

    app = Dash(__name__, title="Aircraft Range vs Capacity")
    app.layout = html.Div(
        style={"fontFamily": "'Segoe UI', Arial, sans-serif",
               "maxWidth": "1500px", "margin": "0 auto", "padding": "20px 24px"},
        children=[
            # ── Header ────────────────────────────────────────────────────
            html.H1("Commercial Aircraft — Range vs. Capacity",
                    style={"margin": "0 0 4px", "fontSize": "1.6rem"}),
            html.P(
                "Source: Wikipedia. Hover a point for details. "
                "Click legend entries to toggle manufacturers.",
                style={"margin": "0 0 18px", "color": "#666", "fontSize": "0.9rem"},
            ),

            # ── Filter row ─────────────────────────────────────────────────
            html.Div(
                style={"display": "flex", "gap": "32px", "flexWrap": "wrap",
                       "background": "#f5f7fa", "borderRadius": "10px",
                       "padding": "14px 20px", "marginBottom": "16px",
                       "alignItems": "flex-start"},
                children=[
                    html.Div(
                        style={"flex": "1", "minWidth": "260px"},
                        children=[
                            html.Label("Manufacturer",
                                       style={"fontWeight": "600", "fontSize": "0.85rem",
                                              "display": "block", "marginBottom": "6px"}),
                            dcc.Dropdown(
                                id="mfr-filter",
                                options=[{"label": m, "value": m} for m in manufacturers],
                                value=[],
                                multi=True,
                                placeholder="All manufacturers — click to filter …",
                                style={"fontSize": "0.9rem"},
                            ),
                        ],
                    ),
                    html.Div(
                        style={"flex": "2", "minWidth": "340px"},
                        children=[
                            html.Label("First Flight Year",
                                       style={"fontWeight": "600", "fontSize": "0.85rem",
                                              "display": "block", "marginBottom": "10px"}),
                            dcc.RangeSlider(
                                id="year-slider",
                                min=year_min, max=year_max, step=1,
                                value=[year_min, year_max],
                                marks=year_marks,
                                tooltip={"placement": "bottom", "always_visible": True},
                                allowCross=False,
                            ),
                        ],
                    ),
                ],
            ),

            # ── Chart ──────────────────────────────────────────────────────
            dcc.Graph(id="chart", style={"height": "68vh"}, config={"displayModeBar": True}),

            # ── Status bar ─────────────────────────────────────────────────
            html.Div(id="status",
                     style={"textAlign": "center", "color": "#888",
                            "fontSize": "0.85rem", "marginTop": "6px"}),
        ],
    )

    # ── Callback ───────────────────────────────────────────────────────────

    @app.callback(
        Output("chart", "figure"),
        Output("status", "children"),
        Input("mfr-filter", "value"),
        Input("year-slider", "value"),
    )
    def update(selected_mfrs, year_range):
        filtered = df.copy()

        if selected_mfrs:
            filtered = filtered[filtered["manufacturer"].isin(selected_mfrs)]

        y0, y1 = year_range
        has_year = filtered["first_flight"].notna()
        in_range = filtered["first_flight"].between(y0, y1)
        filtered = filtered[~has_year | in_range]  # keep aircraft with unknown year

        fig = go.Figure()

        for mfr in sorted(filtered["manufacturer"].unique()):
            sub = filtered[filtered["manufacturer"] == mfr]
            for body, symbol, size in [("wide", "diamond", 11), ("narrow", "circle", 9)]:
                s = sub[sub["body_type"] == body] if "body_type" in sub.columns else sub
                if s.empty:
                    continue
                fig.add_trace(go.Scatter(
                    x=s["range_km"],
                    y=s["capacity"],
                    mode="markers+text",
                    name=mfr,
                    legendgroup=mfr,
                    showlegend=(body == "wide"),   # one legend entry per manufacturer
                    marker=dict(
                        symbol=symbol,
                        size=size,
                        color=color_map[mfr],
                        opacity=0.85,
                        line=dict(width=0.8, color="white"),
                    ),
                    text=s["name"],
                    textposition="top center",
                    textfont=dict(size=9, color=color_map[mfr]),
                    customdata=list(zip(
                        s["manufacturer"],
                        s["first_flight"].fillna(0).astype(int).replace(0, None),
                        s.get("body_type", "").fillna("") if "body_type" in s.columns else [""] * len(s),
                    )),
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        "Manufacturer: %{customdata[0]}<br>"
                        "Range: %{x:,.0f} km<br>"
                        "Capacity: %{y} pax<br>"
                        "First flight: %{customdata[1]}<br>"
                        "Body: %{customdata[2]}"
                        "<extra></extra>"
                    ),
                ))

        fig.update_layout(
            xaxis=dict(title="Range (km)", tickformat=",",
                       gridcolor="#eee", showgrid=True, zeroline=False),
            yaxis=dict(title="Typical passenger capacity",
                       gridcolor="#eee", showgrid=True, zeroline=False),
            plot_bgcolor="white",
            paper_bgcolor="white",
            hovermode="closest",
            legend=dict(
                title=dict(text="Manufacturer<br><sup>◆ wide-body · ● narrow-body</sup>",
                           font=dict(size=12)),
                yanchor="top", y=0.99,
                xanchor="left", x=1.01,
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor="#ddd", borderwidth=1,
            ),
            margin=dict(l=60, r=200, t=20, b=60),
            transition=dict(duration=250),
        )

        n = len(filtered)
        n_mfr = filtered["manufacturer"].nunique()
        yr_note = f"first-flown {y0}–{y1}" if (y0 != year_min or y1 != year_max) else "all years"
        return fig, f"Showing {n} aircraft from {n_mfr} manufacturers · {yr_note}"

    return app


def main():
    force = "--fresh" in sys.argv or "--force" in sys.argv
    if force and DATA_FILE.exists():
        DATA_FILE.unlink()

    df = load_data()
    print(f"Loaded {len(df)} aircraft records")

    app = build_app(df)
    print("Starting at http://127.0.0.1:8050/")
    app.run(debug=False, port=8050)


if __name__ == "__main__":
    main()
