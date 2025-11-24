from __future__ import annotations
"""
Streamlit port of: plot_participant_avg_crossing_vs_distance.py
- Sélection d'un participant
- Courbes seuil (0/1) par météo (Clear/Rain/Night) avec décalage vertical
- Marqueur moyenne ± écart-type sur l'axe X (safety distance)

Dépendances :
    pip install streamlit plotly pandas numpy mysql-connector-python
"""

from pathlib import Path
from typing import Dict, Tuple, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None

# Groupes de vitesse en km/h (paires possibles)
VELOCITY_GROUPS: Dict[str, Tuple[float, float]] = {
    "low": (20.0, 30.0),
    "medium": (40.0, 50.0),
    "high": (60.0, 70.0),
}
COLOR_MAP = {"low": "#1f77b4", "medium": "#2ca02c", "high": "#d62728"}
Y_OFFSET = {"low": 0.0, "medium": 0.01, "high": 0.02}
WEATHERS: List[str] = ["clear", "rain", "night"]


def get_velocity_category(velocity_id: float) -> str:
    for cat, pair in VELOCITY_GROUPS.items():
        if velocity_id in pair:
            return cat
    return "unknown"


def calculate_crossing_value(distance: float, safety_distance: float) -> int:
    return 0 if distance >= -float(safety_distance) else 1


@st.cache_data(show_spinner=False)
def load_crossing_avg() -> pd.DataFrame:
    """Charge et agrège la table Crossing par (participant, weather, velocity)."""
    if get_db_connection is None:
        raise RuntimeError("db_utils.get_db_connection introuvable/import impossible.")

    conn, cursor = get_db_connection()
    try:
        cursor.execute(
            "SELECT participant_id, weather_id, position_id, velocity_id, safety_distance FROM Crossing;"
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

    # Agrégation par participant/weather/velocity
    avg = (
        df.groupby(["participant_id", "weather_id", "velocity_id"])  # type: ignore[pd-unique]
        ["safety_distance"].agg(["mean", "std"]).reset_index()
    )
    return avg


def build_figure(avg_df: pd.DataFrame, participant_id) -> go.Figure:
    data = avg_df[avg_df["participant_id"] == participant_id]
    fig = make_subplots(rows=1, cols=3, subplot_titles=["Clear", "Rain", "Night"], shared_yaxes=True)

    for weather_id, weather_data in data.groupby("weather_id"):
        if weather_id not in WEATHERS:
            # Ignore catégories inconnues
            continue
        col_index = {"clear": 1, "rain": 2, "night": 3}[str(weather_id)]

        for velocity_id, vdf in weather_data.groupby("velocity_id"):
            vcat = get_velocity_category(float(velocity_id))
            m = float(vdf["mean"].values[0])
            std_val = vdf["std"].values[0]
            s = float(std_val) if pd.notna(std_val) else 0.0

            xs = list(range(-150, 6))
            ys = [calculate_crossing_value(d, m) for d in xs]
            yofs = Y_OFFSET.get(vcat, 0.0)
            ys = [y + yofs for y in ys]
            color = COLOR_MAP.get(vcat, "#000000")

            # Courbe
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    name=f"{vcat.capitalize()} Speed",
                    line=dict(color=color, width=1),
                    legendgroup=vcat,
                    showlegend=(weather_id == "clear"),
                ),
                row=1,
                col=col_index,
            )

            # Marqueur moyenne ± std
            fig.add_trace(
                go.Scatter(
                    x=[-m],
                    y=[0.5 + yofs],
                    mode="markers",
                    marker=dict(size=5, color=color, symbol="x"),
                    name=f"{vcat.capitalize()} Mean",
                    legendgroup=vcat,
                    error_x=dict(type="data", symmetric=True, array=[s], visible=True),
                    showlegend=False,
                ),
                row=1,
                col=col_index,
            )

    fig.update_layout(
        template="plotly_white",
        showlegend=True,
        xaxis_title="Distance (m) from Pedestrian to Car",
        yaxis_title="Crossing Value (0 = Not Crossing, 1 = Crossing)",
        height=500,
        margin=dict(t=60, b=40, l=40, r=20),
    )
    return fig


def render(base_path: Path) -> None:
    st.subheader("Crossing Value vs Distance (V,W) – par participant")

    # Chargement agrégé
    try:
        avg = load_crossing_avg()
    except Exception as e:
        st.error(f"Erreur de chargement MySQL : {e}")
        return

    if avg.empty:
        st.info("Aucune donnée trouvée dans la table Crossing.")
        return

    # Sélecteur de participant
    participants = sorted(avg["participant_id"].unique())
    default_idx = 0 if participants else None
    pid = st.selectbox("Participant", participants, index=default_idx)

    if pid is None:
        st.info("Aucun participant à afficher.")
        return

    fig = build_figure(avg, pid)
    st.plotly_chart(fig, use_container_width=True)
