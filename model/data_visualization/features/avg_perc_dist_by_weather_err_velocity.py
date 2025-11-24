from __future__ import annotations
"""
Streamlit port of: plot_avg_perceived_distance_by_weather_error_velocity.py

Objectif :
- Reproduire la figure Python d'origine en version Streamlit.
- Calculer les moyennes perçues (distance & temps) par condition météo.
- Afficher les barres d’erreur provenant des groupes de vitesse (low / medium / high).
- Afficher deux sous-graphiques empilés :
    (1) Temps réel vs temps perçu
    (2) Distance réelle vs distance perçue

Principe :
- On regroupe les données par météo pour calculer les moyennes.
- On regroupe par (météo × groupe de vitesse) pour les écarts-type (barres d’erreur).
- Les décalages horizontaux permettent de séparer visuellement les erreurs selon les vitesses.
- Reproduction fidèle de la logique utilisée dans la version Dash/Matplotlib.

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

# Import flexible du connecteur MySQL (utile pour Streamlit Cloud)
try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None

# Définition des groupes de vitesse (km/h) utilisés pour catégoriser les essais
VELOCITY_GROUPS: Dict[str, Tuple[float, float]] = {
    "low": (20.0, 30.0),
    "medium": (40.0, 50.0),
    "high": (60.0, 70.0),
}

# Couleurs associées à la météo (comme dans la version originale)
WEATHER_COLOR = {
    "clear": "#00BFFF",  # bleu clair
    "rain": "#4682B4",   # bleu acier
    "night": "#191970",  # bleu nuit
}

# Décalage horizontal appliqué aux barres d'erreur pour éviter la superposition
VELOCITY_OFFSETS = {"low": -0.1, "medium": 0.0, "high": 0.1}


def categorize_velocity(v: float) -> str:
    """
    Classe une vitesse (km/h) dans un groupe (low / medium / high).
    Retourne 'unknown' si la vitesse ne correspond pas aux intervalles.
    """
    for g, (a, b) in VELOCITY_GROUPS.items():
        if v in (a, b):
            return g
    return "unknown"


@st.cache_data(show_spinner=False)
def load_perception_df() -> pd.DataFrame:
    """
    Charge la table MySQL `perception` et prépare les colonnes nécessaires :

    - conversion de la vitesse de km/h → m/s
    - calcul du temps réel (distance / vitesse)
    - calcul du temps perçu (distance perçue / vitesse)
    - création de la colonne de groupes de vitesse (velocity_group)
    - tri des lignes pour reproduire l'ordre de l'expérience VR

    Le cache Streamlit évite un rechargement systématique de la base.
    """

    if get_db_connection is None:
        raise RuntimeError("db_utils.get_db_connection introuvable/import impossible.")

    # Connexion MySQL
    conn, cursor = get_db_connection()
    try:
        cursor.execute("SELECT * FROM perception;")
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    finally:
        # Fermeture sécurisée
        try: cursor.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass

    df = pd.DataFrame(rows, columns=cols).dropna()
    if df.empty:
        return df

    # Conversion vitesse → m/s
    df["velocity_id"] = pd.to_numeric(df["velocity_id"], errors="coerce")
    df["velocity_ms"] = df["velocity_id"] * (5.0 / 18.0)

    # Suppression des vitesses nulles/invalides
    df = df[df["velocity_ms"].replace(0, np.nan).notna()].copy()

    # Calcul des temps réel/perçu
    df["real_time"] = df["distance_id"] / df["velocity_ms"]
    df["perceived_time"] = df["perceived_distance"] / df["velocity_ms"]

    # Création du groupe de vitesse
    df["velocity_group"] = df["velocity_id"].apply(categorize_velocity)

    # Tri pour cohérence avec la version Dash/Python originale
    df = df.sort_values(by=["velocity_id", "weather_id", "distance_id"])

    return df


def build_figure(df: pd.DataFrame) -> go.Figure:
    """
    Construit la figure Plotly à deux panneaux :

    Panneau 1 : Temps réel vs temps perçu, regroupé par météo  
    Panneau 2 : Distance réelle vs distance perçue, regroupé par météo  

    Chaque météo dispose :
    - d'une courbe moyenne
    - de barres d'erreur par groupe de vitesse (low/medium/high)

    Les barres d'erreur sont légèrement décalées horizontalement
    → permet de visualiser simultanément l'influence de la vitesse.
    """

    # -------------------------
    #  MOYENNES par météo
    # -------------------------
    mean_dist = (
        df.groupby(["distance_id", "weather_id"])["perceived_distance"]
        .mean()
        .reset_index(name="mean_perceived_distance")
    )

    mean_time = (
        df.groupby(["real_time", "weather_id"])["perceived_time"]
        .mean()
        .reset_index(name="mean_perceived_time")
    )

    # -------------------------
    #  ÉCARTS-TYPE par météo × vitesse
    # -------------------------
    std_dist = (
        df.groupby(["distance_id", "velocity_group", "weather_id"])
        ["perceived_distance"].std().reset_index(name="std_perceived_distance")
    )

    std_time = (
        df.groupby(["real_time", "velocity_group", "weather_id"])
        ["perceived_time"].std().reset_index(name="std_perceived_time")
    )

    # Figure avec 2 sous-graphiques (temps / distance)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.12)

    # Boucle sur les conditions météo
    for weather in mean_dist["weather_id"].dropna().unique():

        # -------------------------
        #   DISTANCE (rangée 2)
        # -------------------------
        d_mean = mean_dist[mean_dist["weather_id"] == weather]
        fig.add_trace(
            go.Scatter(
                x=d_mean["distance_id"],
                y=d_mean["mean_perceived_distance"],
                mode="markers+lines",
                name=f"{weather.capitalize()} Weather",
                marker=dict(color=WEATHER_COLOR.get(weather, "#444"), size=8),
                line=dict(color=WEATHER_COLOR.get(weather, "#444"), width=2),
                legendgroup=weather,
            ),
            row=2, col=1,
        )

        # -------------------------
        #   TEMPS (rangée 1)
        # -------------------------
        t_mean = mean_time[mean_time["weather_id"] == weather]
        fig.add_trace(
            go.Scatter(
                x=t_mean["real_time"],
                y=t_mean["mean_perceived_time"],
                mode="markers+lines",
                name=f"{weather.capitalize()} Weather",
                marker=dict(color=WEATHER_COLOR.get(weather, "#444"), size=8),
                line=dict(color=WEATHER_COLOR.get(weather, "#444"), width=2),
                legendgroup=weather,
                showlegend=False,  # on n'affiche qu'une légende par météo
            ),
            row=1, col=1,
        )

        # -------------------------
        #   BARRES D’ERREUR (météo × vitesse)
        # -------------------------
        for vcat in ["low", "medium", "high"]:

            # --- Distance ---
            d_std = std_dist[(std_dist["weather_id"] == weather) & (std_dist["velocity_group"] == vcat)]
            if not d_std.empty:
                fig.add_trace(
                    go.Scatter(
                        x=d_std["distance_id"] + VELOCITY_OFFSETS.get(vcat, 0.0),
                        y=d_mean[d_mean["distance_id"].isin(d_std["distance_id"])]["mean_perceived_distance"],
                        mode="markers",
                        marker=dict(color=WEATHER_COLOR.get(weather, "#444"), size=8, opacity=0),
                        error_y=dict(type="data", array=d_std["std_perceived_distance"], visible=True),
                        name=f"{vcat.capitalize()} Error",
                        legendgroup=weather,
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

            # --- Temps ---
            t_std = std_time[(std_time["weather_id"] == weather) & (std_time["velocity_group"] == vcat)]
            if not t_std.empty:
                fig.add_trace(
                    go.Scatter(
                        x=t_std["real_time"] + (VELOCITY_OFFSETS.get(vcat, 0.0) / 10.0),
                        y=t_mean[t_mean["real_time"].isin(t_std["real_time"])]["mean_perceived_time"],
                        mode="markers",
                        marker=dict(color=WEATHER_COLOR.get(weather, "#444"), size=8, opacity=0),
                        error_y=dict(type="data", array=t_std["std_perceived_time"], visible=True),
                        name=f"{vcat.capitalize()} Error",
                        legendgroup=weather,
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

    # -------------------------
    #   Lignes de référence y=x
    # -------------------------
    if not df.empty:
        # Distance
        dmin, dmax = float(df["distance_id"].min()), float(df["distance_id"].max())
        fig.add_trace(
            go.Scatter(x=[dmin, dmax], y=[dmin, dmax],
                       mode="lines", line=dict(color="grey", dash="dash"),
                       showlegend=False),
            row=2, col=1,
        )

        # Temps
        tmin, tmax = float(df["real_time"].min()), float(df["real_time"].max())
        fig.add_trace(
            go.Scatter(x=[tmin, tmax], y=[tmin, tmax],
                       mode="lines", line=dict(color="grey", dash="dash"),
                       showlegend=False),
            row=1, col=1,
        )

    # -------------------------
    #   Mise en forme générale
    # -------------------------
    fig.update_layout(
        height=1000,
        xaxis=dict(title="Real Time (s)"),
        yaxis=dict(title="Perceived Time (s)"),
        xaxis2=dict(title="Real Distance (m)"),
        yaxis2=dict(title="Perceived Distance (m)"),
        template="plotly_white",
        margin=dict(t=60, b=40, l=40, r=20),
    )

    # Style des axes
    fig.update_xaxes(title_font=dict(size=18, family="Arial, sans-serif", color="black"),
                     tickfont=dict(size=16, color="black"),
                     showline=True, linewidth=2, linecolor="black")
    fig.update_yaxes(title_font=dict(size=18, family="Arial, sans-serif", color="black"),
                     tickfont=dict(size=16, color="black"),
                     showline=True, linewidth=2, linecolor="black")

    return fig


def render(base_path: Path) -> None:
    """
    Fonction d’intégration Streamlit :
    - charge les données
    - construit la figure
    - l’affiche dans l'interface
    """

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
