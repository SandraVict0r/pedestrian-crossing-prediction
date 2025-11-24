from __future__ import annotations
"""
Streamlit port of: plot_avg_perceived_distance_by_velocity_error_weather.py
- Agrège la table Perception
- Moyennes par (distance, groupe de vitesse) et (temps, groupe de vitesse) **sur météo = clear** (comme l'original)
- Barres d'erreur par météo (clear/rain/night) avec léger décalage horizontal
- Deux sous-graphiques empilés : (1) Temps réel/perçu, (2) Distance réelle/perçue

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

COLOR_MAP = {"low": "#1f77b4", "medium": "#2ca02c", "high": "#d62728"}
OFFSETS = {"clear": -0.1, "rain": 0.0, "night": 0.1}


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
        cursor.execute("SELECT * FROM perception;")
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
    df = df.sort_values(by=["velocity_id", "weather_id", "distance_id"])  # cohérent avec la version Dash
    return df


def build_figure(df: pd.DataFrame) -> go.Figure:
    # Comme l'original : moyennes calculées sur météo == clear uniquement
    df_clear = df[df["weather_id"] == "clear"].copy()

    # Moyennes par distance et groupe de vitesse
    df_mean_distance = (
        df_clear.groupby(["distance_id", "velocity_group"])  # type: ignore[pd-unique]
        ["perceived_distance"].mean().reset_index(name="mean_perceived_distance")
    )

    # Écarts-type par météo (sur l'ensemble du df tel que fourni par l'original 
    # — NB : dans le script Dash source, c'était aussi basé sur df filtré à clear)
    weather_std_distance = (
        df.groupby(["distance_id", "velocity_group", "weather_id"])  # type: ignore[pd-unique]
        ["perceived_distance"].std().reset_index(name="std_perceived_distance")
    )

    # Moyennes par temps réel et groupe de vitesse
    df_mean_time = (
        df_clear.groupby(["real_time", "velocity_group"])  # type: ignore[pd-unique]
        ["perceived_time"].mean().reset_index(name="mean_perceived_time")
    )

    weather_std_time = (
        df.groupby(["real_time", "velocity_group", "weather_id"])  # type: ignore[pd-unique]
        ["perceived_time"].std().reset_index(name="std_perceived_time")
    )

    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.12)

    # Courbes moyennes + barres d'erreur décalées par météo
    for group in df_mean_distance["velocity_group"].dropna().unique():
        # DISTANCE (rangée 2)
        mean_d = df_mean_distance[df_mean_distance["velocity_group"] == group]
        fig.add_trace(
            go.Scatter(
                x=mean_d["distance_id"],
                y=mean_d["mean_perceived_distance"],
                mode="markers+lines",
                name=f"{str(group).capitalize()} Speed",
                marker=dict(color=COLOR_MAP.get(str(group), "#444"), size=8),
                line=dict(color=COLOR_MAP.get(str(group), "#444"), width=2),
                legendgroup=str(group),
            ),
            row=2, col=1,
        )

        # TEMPS (rangée 1)
        mean_t = df_mean_time[df_mean_time["velocity_group"] == group]
        fig.add_trace(
            go.Scatter(
                x=mean_t["real_time"],
                y=mean_t["mean_perceived_time"],
                mode="markers+lines",
                name=f"{str(group).capitalize()} Speed",
                marker=dict(color=COLOR_MAP.get(str(group), "#444"), size=8),
                line=dict(color=COLOR_MAP.get(str(group), "#444"), width=2),
                legendgroup=str(group),
                showlegend=False,
            ),
            row=1, col=1,
        )

        # Barres d'erreur par météo
        for weather in ["clear", "rain", "night"]:
            std_d = weather_std_distance[(weather_std_distance["velocity_group"] == group) & (weather_std_distance["weather_id"] == weather)]
            if not std_d.empty:
                fig.add_trace(
                    go.Scatter(
                        x=std_d["distance_id"] + OFFSETS.get(weather, 0.0),
                        y=mean_d[mean_d["distance_id"].isin(std_d["distance_id"])]["mean_perceived_distance"],
                        mode="markers",
                        marker=dict(color=COLOR_MAP.get(str(group), "#444"), size=8, opacity=0),
                        error_y=dict(type="data", array=std_d["std_perceived_distance"], visible=True),
                        name=f"{weather.capitalize()} Error",
                        legendgroup=str(group),
                        showlegend=False,
                        hoverinfo="x+y+name+text",
                        customdata=[weather.capitalize()] * len(std_d),
                        hovertemplate=(
                            "Weather: %{customdata}<br>"  # météo
                            "Distance: %{x}<br>"
                            "Mean Perceived Distance: %{y}<br>"
                            "Error: %{error_y.array}<br>"
                        ),
                    ),
                    row=2, col=1,
                )

            std_t = weather_std_time[(weather_std_time["velocity_group"] == group) & (weather_std_time["weather_id"] == weather)]
            if not std_t.empty:
                fig.add_trace(
                    go.Scatter(
                        x=std_t["real_time"] + (OFFSETS.get(weather, 0.0) / 10.0),
                        y=mean_t[mean_t["real_time"].isin(std_t["real_time"])]["mean_perceived_time"],
                        mode="markers",
                        marker=dict(color=COLOR_MAP.get(str(group), "#444"), size=8, opacity=0),
                        error_y=dict(type="data", array=std_t["std_perceived_time"], visible=True),
                        name=f"{weather.capitalize()} Error",
                        legendgroup=str(group),
                        showlegend=False,
                        hoverinfo="x+y+name+text",
                        customdata=[weather.capitalize()] * len(std_t),
                        hovertemplate=(
                            "Weather: %{customdata}<br>"
                            "Real Time: %{x}<br>"
                            "Mean Perceived Time: %{y}<br>"
                            "Error: %{error_y.array}<br>"
                        ),
                    ),
                    row=1, col=1,
                )

    # Lignes y=x
    if not df_clear.empty:
        dmin, dmax = float(df_clear["distance_id"].min()), float(df_clear["distance_id"].max())
        fig.add_trace(
            go.Scatter(x=[dmin, dmax], y=[dmin, dmax], mode="lines", name="Baseline",
                        line=dict(color="grey", dash="dash"), legendgroup="Baseline", showlegend=False),
            row=2, col=1,
        )
        tmin, tmax = float(df_clear["real_time"].min()), float(df_clear["real_time"].max())
        fig.add_trace(
            go.Scatter(x=[tmin, tmax], y=[tmin, tmax], mode="lines", name="Baseline",
                        line=dict(color="grey", dash="dash"), legendgroup="Baseline", showlegend=False),
            row=1, col=1,
        )

    # Mise en forme
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
    st.subheader("Avg Perceived Distance by Velocity (errors by Weather)")

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
