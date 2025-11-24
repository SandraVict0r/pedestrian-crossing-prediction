from __future__ import annotations
"""
Streamlit port of: plot_bar_perception_delta.py
- Barres (moyenne ± écart-type) du delta = perceived_distance - distance_id
- 2 graphes :
    (1) Groupé par météo (Clear/Rain/Night)
    (2) Groupé par groupe de vitesse (low/medium/high)

Dépendances :
    pip install streamlit plotly pandas numpy mysql-connector-python
"""

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None

# Couleurs
WEATHER_COLOR = {
    "clear": "#00BFFF",  # bleu clair
    "rain": "#4682B4",   # bleu acier
    "night": "#191970",  # bleu nuit
}
VELOCITY_COLOR = {"low": "#1f77b4", "medium": "#2ca02c", "high": "#d62728"}

# Groupes de vitesse (km/h)
VELOCITY_GROUPS: Dict[str, Tuple[float, float]] = {
    "low": (20.0, 30.0),
    "medium": (40.0, 50.0),
    "high": (60.0, 70.0),
}


def categorize_velocity(v: float) -> str:
    for g, (a, b) in VELOCITY_GROUPS.items():
        if v in (a, b):
            return g
    return "unknown"


@st.cache_data(show_spinner=False)
def load_delta_df() -> pd.DataFrame:
    if get_db_connection is None:
        raise RuntimeError("db_utils.get_db_connection introuvable/import impossible.")

    conn, cursor = get_db_connection()
    try:
        cursor.execute(
            """
            SELECT participant_id, velocity_id, distance_id, weather_id,
                   perceived_distance - distance_id AS delta
            FROM Perception;
            """
        )
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
    df["velocity_group"] = df["velocity_id"].apply(categorize_velocity)
    return df


def build_figures(df: pd.DataFrame):
    # Graphique par météo
    fig_weather = go.Figure()
    for weather in df["weather_id"].dropna().unique():
        g = (
            df[df["weather_id"] == weather]
            .groupby("distance_id")["delta"].agg(["mean", "std"]).reset_index()
        )
        fig_weather.add_trace(
            go.Bar(
                x=g["distance_id"],
                y=g["mean"],
                name=f"{str(weather).capitalize()} Weather",
                marker=dict(color=WEATHER_COLOR.get(str(weather), "#7f7f7f")),
                error_y=dict(type="data", array=g["std"], visible=True),
            )
        )

    fig_weather.update_layout(
        barmode="group",
        xaxis=dict(title="Distance of disappearing"),
        yaxis=dict(title="Delta (Perceived - Real)"),
        title="Mean by Weather",
        margin=dict(t=60, b=40, l=40, r=20),
        height=460,
        template="plotly_white",
    )

    # Graphique par groupe de vitesse
    fig_velocity = go.Figure()
    for vcat in df["velocity_group"].dropna().unique():
        g = (
            df[df["velocity_group"] == vcat]
            .groupby("distance_id")["delta"].agg(["mean", "std"]).reset_index()
        )
        fig_velocity.add_trace(
            go.Bar(
                x=g["distance_id"],
                y=g["mean"],
                name=f"{str(vcat).capitalize()} Speed",
                marker=dict(color=VELOCITY_COLOR.get(str(vcat), "#7f7f7f")),
                error_y=dict(type="data", array=g["std"], visible=True),
            )
        )

    fig_velocity.update_layout(
        barmode="group",
        xaxis=dict(title="Distance of disappearing"),
        yaxis=dict(title="Delta (Perceived - Real)"),
        title="Mean by Velocity",
        margin=dict(t=60, b=40, l=40, r=20),
        height=460,
        template="plotly_white",
    )

    return fig_weather, fig_velocity


def render(base_path: Path) -> None:
    st.subheader("Avg Delta Perception By Weather and Velocity")

    try:
        df = load_delta_df()
    except Exception as e:
        st.error(f"Erreur de chargement MySQL : {e}")
        return

    if df.empty:
        st.info("Aucune donnée trouvée dans la table Perception.")
        return

    fig_w, fig_v = build_figures(df)
    st.plotly_chart(fig_w, use_container_width=True)
    st.plotly_chart(fig_v, use_container_width=True)
