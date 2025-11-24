from __future__ import annotations
"""
Streamlit port of: plot_participant_perceived_distance_by_velocity_weather.py

Objectif :
- Visualiser, pour un participant donné, comment :
      (1) la distance perçue varie selon la distance réelle
      (2) le temps perçu varie selon le temps réel
- Deux sous-graphiques côte à côte :
      gauche : Distance réelle vs Distance perçue
      droite : Temps réel vs Temps perçu
- Le codage :
      • Couleur = vitesse (20-30 bleu, 40-50 vert, 60-70 rouge)
      • Forme = météo (clear/rain/night → cercle/carré/losange)

Idée :
→ Permet d’évaluer le biais individuel de perception, séparément pour chaque (velocity × weather).

Dépendances :
    pip install streamlit plotly pandas numpy mysql-connector-python
"""

from pathlib import Path
from typing import Dict

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

# Couleurs en fonction de la vitesse
COLOR_MAP: Dict[float, str] = {
    20.0: "#1f77b4", 30.0: "#1f77b4",   # bleu (low)
    40.0: "#2ca02c", 50.0: "#2ca02c",   # vert (medium)
    60.0: "#d62728", 70.0: "#d62728",   # rouge (high)
}

# Formes selon la météo
SYMBOL_MAP = {"clear": "circle", "rain": "square", "night": "diamond"}


@st.cache_data(show_spinner=False)
def load_perception_df() -> pd.DataFrame:
    """
    Charge la table MySQL 'perception' et prépare les colonnes nécessaires.

    Ajouts :
    - `velocity_ms` : conversion km/h → m/s
    - `real_time`   : distance réelle / vitesse
    - `perceived_time` : distance perçue / vitesse
    - Tri par vitesse → météo → distance (cohérence avec version Dash)

    Le cache empêche Streamlit de recharger la base à chaque interaction.
    """

    if get_db_connection is None:
        raise RuntimeError("db_utils.get_db_connection introuvable/import impossible.")

    conn, cursor = get_db_connection()
    try:
        cursor.execute("SELECT * FROM perception;")
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    finally:
        # Fermeture propre
        try: cursor.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass

    df = pd.DataFrame(rows, columns=cols).dropna()
    if df.empty:
        return df

    # Tri comme la version Matplotlib/Dash originale
    df = df.sort_values(by=["velocity_id", "weather_id", "distance_id"])

    # Conversion & colonnes dérivées
    df["velocity_id"] = pd.to_numeric(df["velocity_id"], errors="coerce")
    df["velocity_ms"] = df["velocity_id"] * (5.0 / 18.0)

    # Éviter division par zéro
    df = df[df["velocity_ms"].replace(0, np.nan).notna()].copy()

    df["real_time"] = df["distance_id"] / df["velocity_ms"]
    df["perceived_time"] = df["perceived_distance"] / df["velocity_ms"]

    return df


def build_figure(df_part: pd.DataFrame, selected_participant) -> go.Figure:
    """
    Construit les deux sous-graphiques :

    - subplot 1 (col 1) : distance réelle → distance perçue
    - subplot 2 (col 2) : temps réel → temps perçu

    Chaque (velocity × weather) devient une courbe :
        • couleur = vitesse
        • symbole = météo
        • markers + line pour suivre les points par ordre croissant
    """

    fig = make_subplots(rows=1, cols=2, shared_xaxes=False, vertical_spacing=0.1)

    # Boucles sur toutes les combinaisons utilisées par ce participant
    for velocity in df_part["velocity_id"].unique():
        for weather in df_part["weather_id"].unique():

            # Sous-ensemble V×W
            g = df_part[(df_part["velocity_id"] == velocity) &
                        (df_part["weather_id"] == weather)]
            if g.empty:
                continue

            color = COLOR_MAP.get(float(velocity), "#444")
            symbol = SYMBOL_MAP.get(str(weather), "circle")

            # --- Graphique Distance ---
            fig.add_trace(
                go.Scatter(
                    x=g["distance_id"],
                    y=g["perceived_distance"],
                    mode="markers+lines",
                    name=f"{velocity:.0f} km/h - {weather}",
                    marker=dict(symbol=symbol, color=color, size=8),
                    line=dict(color=color, width=2),
                    legendgroup=f"{velocity}-{weather}",
                ),
                row=1, col=1,
            )

            # --- Graphique Temps ---
            fig.add_trace(
                go.Scatter(
                    x=g["real_time"],
                    y=g["perceived_time"],
                    mode="markers+lines",
                    name=f"{velocity:.0f} km/h - {weather}",
                    marker=dict(symbol=symbol, color=color, size=8),
                    line=dict(color=color, width=2),
                    legendgroup=f"{velocity}-{weather}",
                    showlegend=False,   # éviter doublon dans légende
                ),
                row=1, col=2,
            )

    # Lignes de référence y=x (perception parfaite)
    if not df_part.empty:
        # Plot 1 : distance
        x1_min, x1_max = float(df_part["distance_id"].min()), float(df_part["distance_id"].max())
        fig.add_trace(
            go.Scatter(
                x=[x1_min, x1_max], y=[x1_min, x1_max],
                mode="lines", line=dict(color="grey", dash="dash"),
                showlegend=False
            ),
            row=1, col=1,
        )

        # Plot 2 : temps
        x2_min, x2_max = float(df_part["real_time"].min()), float(df_part["real_time"].max())
        fig.add_trace(
            go.Scatter(
                x=[x2_min, x2_max], y=[x2_min, x2_max],
                mode="lines", line=dict(color="grey", dash="dash"),
                showlegend=False
            ),
            row=1, col=2,
        )

    # Mise en forme globale
    fig.update_layout(
        title=f"Participant {selected_participant}",
        height=700,
        xaxis=dict(title="Real Distance (m)"),
        yaxis=dict(title="Perceived Distance (m)"),
        xaxis2=dict(title="Real Time (s)"),
        yaxis2=dict(title="Perceived Time (s)"),
        template="plotly_white",
        margin=dict(t=60, b=40, l=40, r=20),
    )

    return fig


def render(base_path: Path) -> None:
    """
    Fonction Streamlit :
    - charge toutes les données de perception
    - sélectionne un participant
    - affiche les 2 sous-graphiques
    """
    st.subheader("Perceived Distance by Velocity × Weather – par participant")

    # Chargement des données MySQL
    try:
        df = load_perception_df()
    except Exception as e:
        st.error(f"Erreur de chargement MySQL : {e}")
        return

    if df.empty:
        st.info("Aucune donnée trouvée dans la table Perception.")
        return

    # Liste des participants
    participants = sorted(df["participant_id"].unique())
    pid = st.selectbox("Participant", participants, index=0)

    # Sous-ensemble uniquement pour ce participant
    df_part = df[df["participant_id"] == pid]

    # Construction & affichage de la figure
    fig = build_figure(df_part, pid)
    st.plotly_chart(fig, use_container_width=True)
