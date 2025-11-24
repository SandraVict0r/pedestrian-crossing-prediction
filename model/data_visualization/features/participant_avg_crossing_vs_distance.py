from __future__ import annotations
"""
Streamlit port of: plot_participant_avg_crossing_vs_distance.py

Objectif :
- Visualiser, pour un participant donné, son comportement de crossing moyen.
- Afficher la “courbe seuil” Crossing = f(distance) pour chaque météo (Clear/Rain/Night).
- Chaque courbe représente :
      crossing_value = 0 si distance >= -mean_safety_distance
      crossing_value = 1 sinon
- Les vitesses sont différenciées par :
      - une couleur
      - un léger décalage vertical (évite que plusieurs courbes se superposent)
- On affiche la moyenne ± écart-type (symbole "x" + barre d’erreur).

Structure finale :
→ 3 sous-graphes horizontaux : Clear | Rain | Night

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

# Import flexible, utile sur Streamlit Cloud
try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None

# Groupes de vitesse possibles (exactement comme dans la base VR)
VELOCITY_GROUPS: Dict[str, Tuple[float, float]] = {
    "low": (20.0, 30.0),
    "medium": (40.0, 50.0),
    "high": (60.0, 70.0),
}

# Couleurs associées aux groupes de vitesses
COLOR_MAP = {"low": "#1f77b4", "medium": "#2ca02c", "high": "#d62728"}

# Décalage vertical appliqué pour séparer visuellement les courbes
Y_OFFSET = {"low": 0.0, "medium": 0.01, "high": 0.02}

# Ordre fixe des 3 conditions météo
WEATHERS: List[str] = ["clear", "rain", "night"]


def get_velocity_category(velocity_id: float) -> str:
    """
    Retourne la catégorie ('low', 'medium', 'high') correspondant à la vitesse.
    La valeur velocity_id contient des vitesses exactes (20/30/40/50/60/70).
    """
    for cat, pair in VELOCITY_GROUPS.items():
        if velocity_id in pair:
            return cat
    return "unknown"


def calculate_crossing_value(distance: float, safety_distance: float) -> int:
    """
    Fonction core de la “courbe seuil”.

    Règle utilisée dans tous les scripts de crossing :
        crossing = 1 si distance < -safety_distance
        crossing = 0 sinon

    → distance est signée dans le modèle VR (négatif = véhicule proche).
    """
    return 0 if distance >= -float(safety_distance) else 1


@st.cache_data(show_spinner=False)
def load_crossing_avg() -> pd.DataFrame:
    """
    Charge la table 'crossing' et calcule la moyenne & écart-type
    de la safety_distance par :
        (participant_id, weather_id, velocity_id)

    Cela permet d’obtenir :
        - un safety_distance moyen pour chaque config
        - un écart-type qui sera affiché en barre d’erreur
    """
    if get_db_connection is None:
        raise RuntimeError("db_utils.get_db_connection introuvable/import impossible.")

    conn, cursor = get_db_connection()
    try:
        cursor.execute(
            "SELECT participant_id, weather_id, position_id, velocity_id, safety_distance FROM crossing;"
        )
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    finally:
        try: cursor.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass

    df = pd.DataFrame(rows, columns=cols).dropna()
    if df.empty:
        return df

    # Agrégation par combinaison [participant, météo, vitesse]
    avg = (
        df.groupby(["participant_id", "weather_id", "velocity_id"])  # type: ignore
        ["safety_distance"]
        .agg(["mean", "std"])
        .reset_index()
    )
    return avg


def build_figure(avg_df: pd.DataFrame, participant_id) -> go.Figure:
    """
    Construit la figure à 3 colonnes (Clear, Rain, Night)
    avec pour chaque météo :
        - une courbe threshold pour chaque vitesse
        - un marqueur indiquant mean ± std de la safety_distance
    """

    # Sous-ensemble : données du participant sélectionné
    data = avg_df[avg_df["participant_id"] == participant_id]

    # 3 sous-graphes côte-à-côte
    fig = make_subplots(
        rows=1,
        cols=3,
        subplot_titles=["Clear", "Rain", "Night"],
        shared_yaxes=True,
    )

    # Boucle météo → colonne du subplot
    for weather_id, weather_data in data.groupby("weather_id"):

        if weather_id not in WEATHERS:
            # Ignore toute météo inattendue
            continue

        col_index = {"clear": 1, "rain": 2, "night": 3}[str(weather_id)]

        # Boucle sur les différentes vitesses
        for velocity_id, vdf in weather_data.groupby("velocity_id"):

            # Catégorie de vitesse
            vcat = get_velocity_category(float(velocity_id))

            # Moyenne & std de la safety_distance
            m = float(vdf["mean"].values[0])
            std_val = vdf["std"].values[0]
            s = float(std_val) if pd.notna(std_val) else 0.0

            # Génération de la courbe crossing(threshold)
            xs = list(range(-150, 6))  # distances simulées
            ys = [calculate_crossing_value(d, m) for d in xs]

            # Décalage vertical pour éviter overlap
            yofs = Y_OFFSET.get(vcat, 0.0)
            ys = [y + yofs for y in ys]

            # Couleur de ce groupe de vitesse
            color = COLOR_MAP.get(vcat, "#000000")

            # ---- Courbe crossing ----
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    name=f"{vcat.capitalize()} Speed",
                    line=dict(color=color, width=1),
                    legendgroup=vcat,
                    showlegend=(weather_id == "clear"),  # éviter répétitions
                ),
                row=1,
                col=col_index,
            )

            # ---- Marqueur Mean ± Std ----
            fig.add_trace(
                go.Scatter(
                    x=[-m],  # -m car sign convention VR
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

    # ---- Mise en forme globale ----
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
    """
    Fonction appelée par app.py pour afficher la visualisation dans Streamlit.
    - charge les données agrégées
    - propose un selectbox de participant
    - affiche la figure
    """

    st.subheader("Crossing Value vs Distance (V,W) – par participant")

    # Chargement base MySQL
    try:
        avg = load_crossing_avg()
    except Exception as e:
        st.error(f"Erreur de chargement MySQL : {e}")
        return

    if avg.empty:
        st.info("Aucune donnée trouvée dans la table Crossing.")
        return

    # Liste dynamique des participants
    participants = sorted(avg["participant_id"].unique())
    default_idx = 0 if participants else None

    # Sélecteur dans la barre latérale
    pid = st.selectbox("Participant", participants, index=default_idx)

    if pid is None:
        st.info("Aucun participant à afficher.")
        return

    # Construction & affichage
    fig = build_figure(avg, pid)
    st.plotly_chart(fig, use_container_width=True)
