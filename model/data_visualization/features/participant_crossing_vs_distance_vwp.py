from __future__ import annotations
"""
Streamlit port of: plot_participant_crossing_vs_distance.py (V,W,P)

Objectif :
- Afficher pour un participant donné toutes les séries crossing(distance)
  pour chaque combinaison :
        → météo (Clear / Rain / Night)
        → position (0 / 1 / 2)
- Cela produit une grille 3×3 : (3 météo) × (3 positions).

Détails :
- Chaque essai est une courbe crossing vs distance.
- Les courbes sont colorées selon la vitesse (low/medium/high).
- Un léger décalage vertical est ajouté selon la vitesse pour éviter la superposition.
- Les données viennent directement de la table `crossing`, avec distance et crossing
  stockés en JSON.

C'est la visualisation la plus détaillée : chaque essai individuels est affiché.
"""

from pathlib import Path
from typing import Dict, List, Any
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Import flexible pour Streamlit Cloud
try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None

# Ordre fixe pour les 3 conditions météo et les 3 positions
WEATHERS: List[str] = ["clear", "rain", "night"]
POSITIONS: List[int] = [0, 1, 2]

# Couleurs par groupe de vitesse
COLOR_MAP = {
    "low": "#1f77b4",    # bleu doux
    "medium": "#2ca02c", # vert vif
    "high": "#d62728",   # rouge vif
}

# Décalage vertical pour séparer les courbes selon la vitesse
Y_OFFSET = {"low": 0.0, "medium": 0.02, "high": 0.04}


def velocity_category(velocity_id: float) -> str:
    """
    Associe une vitesse (20/30 → low, 40/50 → medium, 60/70 → high)
    selon les vitesses utilisées dans l'expérience VR.
    """
    if velocity_id in (20.0, 30.0):
        return "low"
    if velocity_id in (40.0, 50.0):
        return "medium"
    return "high"


@st.cache_data(show_spinner=False)
def load_crossing_series() -> Dict[Any, Dict[str, Dict[int, List[Dict[str, Any]]]]]:
    """
    Charge les séries brutes crossing(distance) depuis la base.

    Requête :
        SELECT participant_id, weather_id, position_id, velocity_id,
               distance_car_ped, crossing_value
        FROM crossing;

    Remarque :
    - distance_car_ped et crossing_value sont des JSON (listes synchronisées).
    - position_id = 1 implique inversion du signe de distance (hérité du script Dash).
    - Les listes sont alignées pour éviter les problèmes de longueur incohérente.

    Retour :
    Un dictionnaire imbriqué :
        data[participant][weather][position] = [
            {
                "velocity_id": ...,
                "distance": [...],
                "crossing": [...],
                "crossing_id": ...
            },
            ...
        ]
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
        try: cursor.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass

    # Structure imbriquée participant → weather → position → essais
    data_by_participant: Dict[Any, Dict[str, Dict[int, List[Dict[str, Any]]]]] = {}

    # Parcours ligne par ligne
    for row in rows:
        participant_id = row[0]
        weather_id = row[1]
        position_id = int(row[2]) if row[2] is not None else None
        velocity_id = float(row[3]) if row[3] is not None else None

        # distance et crossing sous forme JSON (listes)
        distance_car_ped = json.loads(row[4]) if row[4] else []
        crossing_value = json.loads(row[5]) if row[5] else []
        crossing_id = row[6]

        # Vérification des valeurs essentielles
        if position_id is None or velocity_id is None or weather_id is None:
            continue

        # Alignement de signe spécifique à position 1 (héritage du script original)
        if position_id == 1:
            try:
                distance_car_ped = [-float(x) for x in distance_car_ped]
            except Exception:
                distance_car_ped = []

        # Assainissement : garder uniquement la longueur minimale des deux listes
        n = min(len(distance_car_ped), len(crossing_value))
        if n == 0:
            continue

        dists = [float(distance_car_ped[i]) for i in range(n)]
        cross = [float(crossing_value[i]) for i in range(n)]

        # Insérer au bon endroit (structure imbriquée)
        data_by_participant \
            .setdefault(participant_id, {}) \
            .setdefault(str(weather_id), {}) \
            .setdefault(position_id, []) \
            .append(
                {
                    "crossing_id": crossing_id,
                    "velocity_id": velocity_id,
                    "distance": dists,
                    "crossing": cross,
                }
            )

    return data_by_participant


def build_figure(participant_data: Dict[str, Dict[int, List[Dict[str, Any]]]]) -> go.Figure:
    """
    Construit la grille 3×3 de sous-graphes :
        lignes = météo
        colonnes = positions

    Chaque cellule affiche toutes les courbes crossing(distance)
    correspondant à cette combinaison (un essai = une courbe).
    """

    # Sous-titres de la grille
    subtitles: List[str] = []
    for w in WEATHERS:
        for p in POSITIONS:
            subtitles.append(f"Position {p} - {w.capitalize()}")

    # Figure composée en grille
    fig = make_subplots(
        rows=len(WEATHERS),
        cols=len(POSITIONS),
        shared_yaxes=True,
        subplot_titles=subtitles,
        vertical_spacing=0.08,
    )

    # Parcours par météo puis par position
    for weather in WEATHERS:
        if weather not in participant_data:
            continue
        row_idx = WEATHERS.index(weather) + 1

        for pos in POSITIONS:
            series_list = participant_data.get(weather, {}).get(pos, [])
            if not series_list:
                continue
            col_idx = pos + 1

            # On affiche toutes les courbes des essais
            for serie in series_list:
                vcat = velocity_category(float(serie.get("velocity_id", 0)))
                color = COLOR_MAP.get(vcat, "#000000")
                yofs = Y_OFFSET.get(vcat, 0.0)

                xs = serie.get("distance", [])
                ys = serie.get("crossing", [])
                if not xs or not ys:
                    continue

                # Décalage vertical pour séparer visuellement selon vitesse
                ys = [float(y) + yofs for y in ys]

                fig.add_trace(
                    go.Scatter(
                        x=xs,
                        y=ys,
                        mode="lines",
                        name=f"{vcat.capitalize()} Speed",
                        line=dict(color=color, width=2),
                        legendgroup=vcat,
                        # On n’affiche la légende qu’une seule fois : clear / position 0
                        showlegend=(pos == 0 and weather == "clear"),
                    ),
                    row=row_idx,
                    col=col_idx,
                )

    # Mise en forme finale
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
    """
    Fonction Streamlit :
    - charge toutes les séries crossing(distance)
    - propose un selectbox pour choisir un participant
    - affiche la grille 3×3
    """
    st.subheader("Crossing Value vs Distance (V,W,P) – par participant")

    try:
        data = load_crossing_series()
    except Exception as e:
        st.error(f"Erreur de chargement MySQL : {e}")
        return

    if not data:
        st.info("Aucune donnée trouvée dans la table Crossing.")
        return

    # Liste des participants disponibles
    participants = sorted(list(data.keys()))
    pid = st.selectbox("Participant", participants, index=0)

    # Sous-données pour ce participant
    participant_data = data.get(pid, {})

    # Affichage de la figure
    fig = build_figure(participant_data)
    st.plotly_chart(fig, use_container_width=True)
