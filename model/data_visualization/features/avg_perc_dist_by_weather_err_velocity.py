from __future__ import annotations
"""
Streamlit port of: plot_avg_perceived_distance_by_weather_error_velocity.py
- Agrège Perception par météo (moyennes) et affiche des barres d'erreur par **groupe de vitesse**
- Deux subplots empilés : (1) Temps réel/perçu, (2) Distance réelle/perçue

Dépendances :
    pip install streamlit plotly pandas numpy mysql-connector-python
"""

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None

# Groupes de vitesse
VELOCITY_GROUPS: Dict[str, Tuple[float, float]] = {
    "low": (20.0, 30.0),
    "medium": (40.0, 50.0),
    "high": (60.0, 70.0),
}

WEATHER_COLOR = {
    "clear": "#00BFFF",  # bleu clair
    "rain": "#4682B4",   # bleu acier
    "night": "#191970",  # bleu nuit
}
# Décalage horizontal pour séparer visuellement les barres d'erreur par vitesse
VELOCITY_OFFSETS = {"low": -0.1, "medium": 0.0, "high": 0.1}


def categorize_velocity(v: float) -> str:
    for g, (a, b) in VELOCITY_GROUPS.items():
        if v in (a, b):
            return g
    return "unknown"


@st.cache_data(show_spinner=False)
def load_perception_df() -> pd.DataFrame:
    if get_db_connection is None:
        raise RuntimeError("db_utils.get_db_connection introuvable/import impossible.")

    conn, cursor = get_db_connection()
    try:
        cursor.execute("SELECT * FROM Perception;")
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    df = pd.DataFrame(rows, columns=cols).dropna()
    if df.empty:
        return df

    df["velocity_id"] = pd.to_numeric(df["velocity_id"], errors="coerce")
    df["velocity_ms"] = df["velocity_id"] * (5.0 / 18.0)
    df = df[df["velocity_ms"].replace(0, np.nan).notna()].copy()
    df["real_time"] = df["distance_id"] / df["velocity_ms"]
    df["perceived_time"] = df["perceived_distance"] / df["velocity_ms"]
    df["velocity_group"] = df["velocity_id"].apply(categorize_velocity)
    df = df.sort_values(by=["velocity_id", "weather_id", "distance_id"])  # cohérent Dash
    return df


def build_figure(df: pd.DataFrame) -> go.Figure:
    # Moyennes par météo
    mean_dist = (
        df.groupby(["distance_id", "weather_id"])  # type: ignore[pd-unique]
        ["perceived_distance"].mean().reset_index(name="mean_perceived_distance")
    )
    std_dist = (
        df.groupby(["distance_id", "velocity_group", "weather_id"])  # type: ignore[pd-unique]
        ["perceived_distance"].std().reset_index(name="std_perceived_distance")
    )

    mean_time = (
        df.groupby(["real_time", "weather_id"])  # type: ignore[pd-unique]
        ["perceived_time"].mean().reset_index(name="mean_perceived_time")
    )
    std_time = (
        df.groupby(["real_time", "velocity_group", "weather_id"])  # type: ignore[pd-unique]
        ["perceived_time"].std().reset_index(name="std_perceived_time")
    )

    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.12)

    for weather in mean_dist["weather_id"].dropna().unique():
        # DISTANCE (rangée 2)
        d_mean = mean_dist[mean_dist["weather_id"] == weather]
        fig.add_trace(
            go.Scatter(
                x=d_mean["distance_id"],
                y=d_mean["mean_perceived_distance"],
                mode="markers+lines",
                name=f"{str(weather).capitalize()} Weather",
                marker=dict(color=WEATHER_COLOR.get(str(weather), "#444"), size=8),
                line=dict(color=WEATHER_COLOR.get(str(weather), "#444"), width=2),
                legendgroup=str(weather),
            ),
            row=2, col=1,
        )

        # TEMPS (rangée 1)
        t_mean = mean_time[mean_time["weather_id"] == weather]
        fig.add_trace(
            go.Scatter(
                x=t_mean["real_time"],
                y=t_mean["mean_perceived_time"],
                mode="markers+lines",
                name=f"{str(weather).capitalize()} Weather",
                marker=dict(color=WEATHER_COLOR.get(str(weather), "#444"), size=8),
                line=dict(color=WEATHER_COLOR.get(str(weather), "#444"), width=2),
                legendgroup=str(weather),
                showlegend=False,
            ),
            row=1, col=1,
        )

        # Barres d'erreur par groupe de vitesse
        for vcat in ["low", "medium", "high"]:
            d_std = std_dist[(std_dist["weather_id"] == weather) & (std_dist["velocity_group"] == vcat)]
            if not d_std.empty:
                fig.add_trace(
                    go.Scatter(
                        x=d_std["distance_id"] + VELOCITY_OFFSETS.get(vcat, 0.0),
                        y=d_mean[d_mean["distance_id"].isin(d_std["distance_id"])]["mean_perceived_distance"],
                        mode="markers",
                        marker=dict(color=WEATHER_COLOR.get(str(weather), "#444"), size=8, opacity=0),
                        error_y=dict(type="data", array=d_std["std_perceived_distance"], visible=True),
                        name=f"{vcat.capitalize()} Error",
                        legendgroup=str(weather),
                        showlegend=False,
                        hoverinfo="x+y+name+text",
                        customdata=[vcat.capitalize()] * len(d_std),
                        hovertemplate=(
                            "Velocity: %{customdata}<br>"
                            "Distance: %{x}<br>"
                            "Mean Perceived Distance: %{y}<br>"
                            "Error: %{error_y.array}<br>"
                        ),
                    ),
                    row=2, col=1,
                )

            t_std = std_time[(std_time["weather_id"] == weather) & (std_time["velocity_group"] == vcat)]
            if not t_std.empty:
                fig.add_trace(
                    go.Scatter(
                        x=t_std["real_time"] + (VELOCITY_OFFSETS.get(vcat, 0.0) / 10.0),
                        y=t_mean[t_mean["real_time"].isin(t_std["real_time"])]["mean_perceived_time"],
                        mode="markers",
                        marker=dict(color=WEATHER_COLOR.get(str(weather), "#444"), size=8, opacity=0),
                        error_y=dict(type="data", array=t_std["std_perceived_time"], visible=True),
                        name=f"{vcat.capitalize()} Error",
                        legendgroup=str(weather),
                        showlegend=False,
                        hoverinfo="x+y+name+text",
                        customdata=[vcat.capitalize()] * len(t_std),
                        hovertemplate=(
                            "Velocity: %{customdata}<br>"
                            "Real Time: %{x}<br>"
                            "Mean Perceived Time: %{y}<br>"
                            "Error: %{error_y.array}<br>"
                        ),
                    ),
                    row=1, col=1,
                )

    # Lignes de base y=x
    if not df.empty:
        dmin, dmax = float(df["distance_id"].min()), float(df["distance_id"].max())
        fig.add_trace(
            go.Scatter(x=[dmin, dmax], y=[dmin, dmax], mode="lines", name="Baseline",
                        line=dict(color="grey", dash="dash"), legendgroup="Baseline", showlegend=False),
            row=2, col=1,
        )
        tmin, tmax = float(df["real_time"].min()), float(df["real_time"].max())
        fig.add_trace(
            go.Scatter(x=[tmin, tmax], y=[tmin, tmax], mode="lines", name="Baseline",
                        line=dict(color="grey", dash="dash"), legendgroup="Baseline", showlegend=False),
            row=1, col=1,
        )

    fig.update_layout(
        height=1000,
        xaxis=dict(title="Real Time (s)"),
        yaxis=dict(title="Perceived Time (s)"),
        xaxis2=dict(title="Real Distance (m)"),
        yaxis2=dict(title="Perceived Distance (m)"),
        template="plotly_white",
        margin=dict(t=60, b=40, l=40, r=20),
    )

    fig.update_xaxes(title_font=dict(size=18, family="Arial, sans-serif", color="black"),
                     tickfont=dict(size=16, color="black"), showline=True, linewidth=2, linecolor="black")
    fig.update_yaxes(title_font=dict(size=18, family="Arial, sans-serif", color="black"),
                     tickfont=dict(size=16, color="black"), showline=True, linewidth=2, linecolor="black")

    return fig


def render(base_path: Path) -> None:
    st.subheader("Avg Perceived Distance by Weather (errors by Velocity)")

    try:
        df = load_perception_df()
    except Exception as e:
        st.error(f"Erreur de chargement MySQL : {e}")
        return

    if df.empty:
        st.info("Aucune donnée trouvée dans la table Perception.")
        return

    fig = build_figure(df)
    st.plotly_chart(fig, use_container_width=True)
