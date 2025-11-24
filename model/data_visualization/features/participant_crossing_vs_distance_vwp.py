from __future__ import annotations
"""
Streamlit port of: plot_participant_crossing_vs_distance.py (V,W,P)
- Sélection d'un participant
- Grille 3x3 : météo (clear/rain/night) × position (0/1/2)
- Courbes crossing vs distance par essai, colorées selon la catégorie de vitesse,
  avec un léger décalage vertical par vitesse pour faciliter la lecture.

Dépendances :
    pip install streamlit plotly pandas numpy mysql-connector-python
"""

from pathlib import Path
from typing import Dict, List, Any
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None

WEATHERS: List[str] = ["clear", "rain", "night"]
POSITIONS: List[int] = [0, 1, 2]

COLOR_MAP = {
    "low": "#1f77b4",    # bleu doux
    "medium": "#2ca02c", # vert vif
    "high": "#d62728",   # rouge chaleureux
}
Y_OFFSET = {"low": 0.0, "medium": 0.02, "high": 0.04}


def velocity_category(velocity_id: float) -> str:
    if velocity_id in (20.0, 30.0):
        return "low"
    if velocity_id in (40.0, 50.0):
        return "medium"
    return "high"


@st.cache_data(show_spinner=False)
def load_crossing_series() -> Dict[Any, Dict[str, Dict[int, List[Dict[str, Any]]]]]:
    """Charge les séries crossing/distance groupées par participant → météo → position.
    Retourne un dict imbriqué : data[participant][weather][position] = [ {velocity_id, distance, crossing}, ... ]
    """
    if get_db_connection is None:
        raise RuntimeError("db_utils.get_db_connection introuvable/import impossible.")

    conn, cursor = get_db_connection()
    try:
        cursor.execute(
            "SELECT participant_id, weather_id, position_id, velocity_id, distance_car_ped, crossing_value, crossing_id FROM crossing;"
        )
        rows = cursor.fetchall()
        cols = [c[0] for c in cursor.description]
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    # Build nested structure
    data_by_participant: Dict[Any, Dict[str, Dict[int, List[Dict[str, Any]]]]] = {}

    for row in rows:
        participant_id = row[0]
        weather_id = row[1]
        position_id = int(row[2]) if row[2] is not None else None
        velocity_id = float(row[3]) if row[3] is not None else None
        distance_car_ped = json.loads(row[4]) if row[4] else []
        crossing_value = json.loads(row[5]) if row[5] else []
        crossing_id = row[6]

        if position_id is None or velocity_id is None or weather_id is None:
            continue

        # Aligner signe (comme dans la version Dash) pour position 1
        if position_id == 1:
            try:
                distance_car_ped = [-float(x) for x in distance_car_ped]
            except Exception:
                distance_car_ped = []

        # Assainir longueurs
        n = min(len(distance_car_ped), len(crossing_value))
        if n == 0:
            continue
        dists = [float(distance_car_ped[i]) for i in range(n)]
        cross = [float(crossing_value[i]) for i in range(n)]

        data_by_participant.setdefault(participant_id, {}).setdefault(str(weather_id), {}).setdefault(position_id, []).append(
            {
                "crossing_id": crossing_id,
                "velocity_id": velocity_id,
                "distance": dists,
                "crossing": cross,
            }
        )

    return data_by_participant


def build_figure(participant_data: Dict[str, Dict[int, List[Dict[str, Any]]]]) -> go.Figure:
    # Titre des sous-graphiques
    subtitles: List[str] = []
    for w in WEATHERS:
        for p in POSITIONS:
            subtitles.append(f"Position {p} - {w.capitalize()}")

    fig = make_subplots(
        rows=len(WEATHERS),
        cols=len(POSITIONS),
        shared_yaxes=True,
        subplot_titles=subtitles,
        vertical_spacing=0.08,
    )

    for weather in WEATHERS:
        if weather not in participant_data:
            continue
        row_idx = WEATHERS.index(weather) + 1
        for pos in POSITIONS:
            series_list = participant_data.get(weather, {}).get(pos, [])
            if not series_list:
                continue
            col_idx = pos + 1

            for serie in series_list:
                vcat = velocity_category(float(serie.get("velocity_id", 0)))
                color = COLOR_MAP.get(vcat, "#000000")
                yofs = Y_OFFSET.get(vcat, 0.0)

                xs = serie.get("distance", [])
                ys = serie.get("crossing", [])
                if not xs or not ys:
                    continue
                ys = [float(y) + yofs for y in ys]

                fig.add_trace(
                    go.Scatter(
                        x=xs,
                        y=ys,
                        mode="lines",
                        name=f"{vcat.capitalize()} Speed",
                        line=dict(color=color, width=2),
                        legendgroup=vcat,
                        showlegend=(pos == 0 and weather == "clear"),
                    ),
                    row=row_idx,
                    col=col_idx,
                )

    fig.update_layout(
        template="plotly_white",
        showlegend=True,
        xaxis_title="Distance car-pedestrian",
        yaxis_title="Crossing",
        height=900,
        margin=dict(t=60, b=40, l=40, r=20),
    )
    return fig


def render(base_path: Path) -> None:
    st.subheader("Crossing Value vs Distance (V,W,P) – par participant")

    try:
        data = load_crossing_series()
    except Exception as e:
        st.error(f"Erreur de chargement MySQL : {e}")
        return

    if not data:
        st.info("Aucune donnée trouvée dans la table Crossing.")
        return

    participants = sorted(list(data.keys()))
    pid = st.selectbox("Participant", participants, index=0)

    participant_data = data.get(pid, {})
    fig = build_figure(participant_data)
    st.plotly_chart(fig, use_container_width=True)
