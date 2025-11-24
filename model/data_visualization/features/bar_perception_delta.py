from __future__ import annotations
"""
Streamlit port of: plot_bar_perception_delta.py

Objectif :
- Reproduire la figure « delta de perception » utilisée dans l’analyse VR.
- Delta = perceived_distance - distance_id.
- Afficher 2 graphes :
    (1) Barres groupées par météo (Clear / Rain / Night)
    (2) Barres groupées par vitesse (low / medium / high)
- Les barres affichent la moyenne ± écart-type.

Principe :
- On calcule le delta directement via un SELECT SQL.
- On agrège par distance_id pour conserver la structure des essais Exp1.
- On utilise des couleurs cohérentes avec le reste de l’app.

Dépendances :
    pip install streamlit plotly pandas numpy mysql-connector-python
"""

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Import flexible : permet à Streamlit Cloud de ne pas planter au build
try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None

# Palette météo (cohérente avec les autres visualisations)
WEATHER_COLOR = {
    "clear": "#00BFFF",  # bleu clair
    "rain": "#4682B4",   # bleu acier
    "night": "#191970",  # bleu nuit
}

# Palette vitesse (mêmes couleurs que velocity groups ailleurs dans l’app)
VELOCITY_COLOR = {"low": "#1f77b4", "medium": "#2ca02c", "high": "#d62728"}

# Groupes de vitesse (km/h)
VELOCITY_GROUPS: Dict[str, Tuple[float, float]] = {
    "low": (20.0, 30.0),
    "medium": (40.0, 50.0),
    "high": (60.0, 70.0),
}


def categorize_velocity(v: float) -> str:
    """
    Classe une vitesse précise (ex : 20, 30, 40 km/h) dans un groupe low/medium/high.

    - Les intervalles sont définis dans VELOCITY_GROUPS.
    - Si une vitesse ne correspond pas : retourne "unknown".
    """
    for g, (a, b) in VELOCITY_GROUPS.items():
        if v in (a, b):
            return g
    return "unknown"


@st.cache_data(show_spinner=False)
def load_delta_df() -> pd.DataFrame:
    """
    Charge depuis MySQL les colonnes nécessaires pour le calcul du delta.

    Requête SQL :
        SELECT participant_id, velocity_id, distance_id, weather_id,
               perceived_distance - distance_id AS delta
        FROM perception;

    Colonnes finales :
    - participant_id
    - distance_id
    - velocity_group (calculé)
    - weather_id
    - delta (perception - réalité)

    Avantages :
    - pas de post-calcul en Python pour le delta
    - format léger → plus rapide pour Streamlit
    """
    if get_db_connection is None:
        raise RuntimeError("db_utils.get_db_connection introuvable/import impossible.")

    conn, cursor = get_db_connection()
    try:
        # Calcul du delta directement en SQL
        cursor.execute(
            """
            SELECT participant_id, velocity_id, distance_id, weather_id,
                   perceived_distance - distance_id AS delta
            FROM perception;
            """
        )
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    finally:
        # Fermeture sécurisée MySQL
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    # Construction du DataFrame
    df = pd.DataFrame(rows, columns=cols).dropna()
    if df.empty:
        return df

    # Conversion des vitesses + classification
    df["velocity_id"] = pd.to_numeric(df["velocity_id"], errors="coerce")
    df["velocity_ms"] = df["velocity_id"] * (5.0 / 18.0)
    df["velocity_group"] = df["velocity_id"].apply(categorize_velocity)

    return df


def build_figures(df: pd.DataFrame):
    """
    Construit les deux barplots (par météo et par vitesse).

    Méthode :
    - On groupe par distance_id pour conserver la structure de l’expérience.
    - On calcule mean ± std pour chaque distance.
    - Les couleurs et labels sont harmonisés avec le reste de l’application.
    """

    # -------------------------
    # 1) Graphique groupé par météo
    # -------------------------
    fig_weather = go.Figure()

    for weather in df["weather_id"].dropna().unique():

        # Agrégation mean ± std
        g = (
            df[df["weather_id"] == weather]
            .groupby("distance_id")["delta"]
            .agg(["mean", "std"])
            .reset_index()
        )

        # Ajout de la barre
        fig_weather.add_trace(
            go.Bar(
                x=g["distance_id"],
                y=g["mean"],
                name=f"{weather.capitalize()} Weather",
                marker=dict(color=WEATHER_COLOR.get(str(weather), "#7f7f7f")),
                error_y=dict(type="data", array=g["std"], visible=True),
            )
        )

    # Mise en forme
    fig_weather.update_layout(
        barmode="group",
        xaxis=dict(title="Distance of disappearing"),
        yaxis=dict(title="Delta (Perceived - Real)"),
        title="Mean by Weather",
        margin=dict(t=60, b=40, l=40, r=20),
        height=460,
        template="plotly_white",
    )

    # -------------------------
    # 2) Graphique groupé par vitesse
    # -------------------------
    fig_velocity = go.Figure()

    for vcat in df["velocity_group"].dropna().unique():

        g = (
            df[df["velocity_group"] == vcat]
            .groupby("distance_id")["delta"]
            .agg(["mean", "std"])
            .reset_index()
        )

        fig_velocity.add_trace(
            go.Bar(
                x=g["distance_id"],
                y=g["mean"],
                name=f"{vcat.capitalize()} Speed",
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
    """
    Fonction appelée par app.py :
    - charge les données
    - génère les figures
    - les affiche dans Streamlit
    """

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
