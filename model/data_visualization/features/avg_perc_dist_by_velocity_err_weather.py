from __future__ import annotations
"""
Streamlit port of: plot_avg_perceived_distance_by_velocity_error_weather.py

Objectif :
- Reproduire dans Streamlit la figure Python utilisée dans la thèse.
- Calculer les moyennes perçues (distance & temps) par groupe de vitesse.
- Afficher les barres d’erreurs provenant de différentes conditions météo.
- Afficher deux graphiques empilés :
    (1) Temps réel vs temps perçu
    (2) Distance réelle vs distance perçue

Logique :
- On filtre la météo = "clear" pour calculer les *moyennes* (comme dans la version Dash d’origine).
- Les barres d’erreur utilisent *toutes* les conditions météo, mais restent alignées sur la moyenne "clear".
- Les données proviennent de la table MySQL `perception`.

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

# Import flexible : permet au module d'être importé dans Streamlit Cloud
# même si db_utils n'existe pas encore au moment du build
try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None

# Définition des groupes de vitesse utilisés pour catégoriser l’expérience
# Les valeurs correspondent aux vitesses en km/h présentes dans la base VR
VELOCITY_GROUPS: Dict[str, Tuple[float, float]] = {
    "low": (20.0, 30.0),
    "medium": (40.0, 50.0),
    "high": (60.0, 70.0),
}

# Couleurs par groupe de vitesse (mêmes que dans la version Dash)
COLOR_MAP = {"low": "#1f77b4", "medium": "#2ca02c", "high": "#d62728"}

# Décalage horizontal appliqué aux points des barres d'erreur selon la météo
# pour éviter la superposition parfaite des marqueurs
OFFSETS = {"clear": -0.1, "rain": 0.0, "night": 0.1}


def categorize_velocity(v: float) -> str:
    """
    Associe une vitesse (km/h) à un groupe ('low', 'medium', 'high').

    Remarque :
    - Dans les données VR, velocity_id contient les vitesses exactes : 20/30/40/50/60/70.
    - On retourne "unknown" si la valeur ne correspond pas à un intervalle connu.
    """
    for g, (a, b) in VELOCITY_GROUPS.items():
        if v in (a, b):
            return g
    return "unknown"


@st.cache_data(show_spinner=False)
def load_perception_df() -> pd.DataFrame:
    """
    Charge la table `perception` depuis MySQL et prépare les colonnes nécessaires.

    Transformations effectuées :
    - Conversion velocity_id → m/s
    - Calcul du temps réel et temps perçu
    - Catégorisation de la vitesse (low/medium/high)
    - Tri pour un rendu graphique cohérent avec la version originale

    Le cache est important : évite de recharger la base à chaque interaction Streamlit.
    """

    if get_db_connection is None:
        raise RuntimeError("db_utils.get_db_connection introuvable/import impossible.")

    conn, cursor = get_db_connection()
    try:
        cursor.execute("SELECT * FROM perception;")
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    finally:
        # Toujours fermer proprement la connexion MySQL
        try: cursor.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass

    df = pd.DataFrame(rows, columns=cols).dropna()

    if df.empty:
        return df

    # Conversion de la vitesse → m/s (velocity_id = km/h)
    df["velocity_id"] = pd.to_numeric(df["velocity_id"], errors="coerce")
    df["velocity_ms"] = df["velocity_id"] * (5.0 / 18.0)

    # Suppression des vitesses nulles ou invalides
    df = df[df["velocity_ms"].replace(0, np.nan).notna()].copy()

    # Calcul du temps réel/perçu selon distance / vitesse
    df["real_time"] = df["distance_id"] / df["velocity_ms"]
    df["perceived_time"] = df["perceived_distance"] / df["velocity_ms"]

    # Catégorisation des vitesses
    df["velocity_group"] = df["velocity_id"].apply(categorize_velocity)

    # Tri pour respecter l'ordre des vitesses/météos/distances comme l'original
    df = df.sort_values(by=["velocity_id", "weather_id", "distance_id"])

    return df


def build_figure(df: pd.DataFrame) -> go.Figure:
    """
    Construit la figure Plotly composée de deux sous-graphiques empilés.

    Logique :
    - Les *moyennes* utilisent uniquement la météo "clear" (comme la version Dash).
    - Les barres d'erreurs utilisent *toutes* les conditions météo.
    - On ajoute des offsets horizontaux pour distinguer les erreurs selon "clear/rain/night".
    """

    # Filtrer "clear" pour les moyennes (réplicant l’ancienne figure Python)
    df_clear = df[df["weather_id"] == "clear"].copy()

    # Moyennes distance perçue par distance et groupe de vitesse
    df_mean_distance = (
        df_clear.groupby(["distance_id", "velocity_group"])  # type: ignore
        ["perceived_distance"].mean().reset_index(name="mean_perceived_distance")
    )

    # Écarts-types par météo pour distance perçue
    weather_std_distance = (
        df.groupby(["distance_id", "velocity_group", "weather_id"])  # type: ignore
        ["perceived_distance"].std().reset_index(name="std_perceived_distance")
    )

    # Moyennes temps perçu par temps réel et groupe de vitesse
    df_mean_time = (
        df_clear.groupby(["real_time", "velocity_group"])  # type: ignore
        ["perceived_time"].mean().reset_index(name="mean_perceived_time")
    )

    # Écarts-types par météo pour temps perçu
    weather_std_time = (
        df.groupby(["real_time", "velocity_group", "weather_id"])  # type: ignore
        ["perceived_time"].std().reset_index(name="std_perceived_time")
    )

    # Figure avec deux sous-graphiques empilés
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.12)

    # Pour chaque groupe de vitesse : tracer les moyennes + barres d’erreurs
    for group in df_mean_distance["velocity_group"].dropna().unique():

        # -----------------------------
        # 1) Distance perçue (rangée 2)
        # -----------------------------
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

        # -----------------------------
        # 2) Temps perçu (rangée 1)
        # -----------------------------
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
                showlegend=False,   # éviter double affichage dans la légende
            ),
            row=1, col=1,
        )

        # -----------------------------
        # 3) Barres d’erreurs par météo
        # -----------------------------
        for weather in ["clear", "rain", "night"]:

            # Distance
            std_d = weather_std_distance[
                (weather_std_distance["velocity_group"] == group) &
                (weather_std_distance["weather_id"] == weather)
            ]
            if not std_d.empty:
                fig.add_trace(
                    go.Scatter(
                        x=std_d["distance_id"] + OFFSETS.get(weather, 0.0),
                        y=mean_d[mean_d["distance_id"].isin(std_d["distance_id"])]["mean_perceived_distance"],
                        mode="markers",
                        marker=dict(color=COLOR_MAP.get(str(group), "#444"),
                                    size=8, opacity=0),  # marqueur invisible → seulement barres d’erreur
                        error_y=dict(type="data", array=std_d["std_perceived_distance"], visible=True),
                        legendgroup=str(group),
                        showlegend=False,
                        hoverinfo="x+y+name+text",
                        customdata=[weather.capitalize()] * len(std_d),
                        hovertemplate=(
                            "Weather: %{customdata}<br>"
                            "Distance: %{x}<br>"
                            "Mean Perceived Distance: %{y}<br>"
                            "Error: %{error_y.array}<br>"
                        ),
                    ),
                    row=2, col=1,
                )

            # Temps réel / perçu
            std_t = weather_std_time[
                (weather_std_time["velocity_group"] == group) &
                (weather_std_time["weather_id"] == weather)
            ]
            if not std_t.empty:
                fig.add_trace(
                    go.Scatter(
                        x=std_t["real_time"] + (OFFSETS.get(weather, 0.0) / 10.0),
                        y=mean_t[mean_t["real_time"].isin(std_t["real_time"])]["mean_perceived_time"],
                        mode="markers",
                        marker=dict(color=COLOR_MAP.get(str(group), "#444"),
                                    size=8, opacity=0),
                        error_y=dict(type="data", array=std_t["std_perceived_time"], visible=True),
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

    # -----------------------------
    # Ajout des lignes de baseline y = x
    # -----------------------------
    if not df_clear.empty:
        dmin, dmax = float(df_clear["distance_id"].min()), float(df_clear["distance_id"].max())
        fig.add_trace(
            go.Scatter(x=[dmin, dmax], y=[dmin, dmax],
                       mode="lines", line=dict(color="grey", dash="dash"),
                       showlegend=False),
            row=2, col=1,
        )

        tmin, tmax = float(df_clear["real_time"].min()), float(df_clear["real_time"].max())
        fig.add_trace(
            go.Scatter(x=[tmin, tmax], y=[tmin, tmax],
                       mode="lines", line=dict(color="grey", dash="dash"),
                       showlegend=False),
            row=1, col=1,
        )

    # -----------------------------
    # Mise en forme générale
    # -----------------------------
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
                     tickfont=dict(size=16, color="black"), showline=True,
                     linewidth=2, linecolor="black")
    fig.update_yaxes(title_font=dict(size=18, family="Arial, sans-serif", color="black"),
                     tickfont=dict(size=16, color="black"), showline=True,
                     linewidth=2, linecolor="black")

    return fig


def render(base_path: Path) -> None:
    """
    Fonction appelée depuis app.py pour afficher la visualisation dans Streamlit.

    Paramètres
    ----------
    base_path : Path
        Chemin du dossier racine du module (actuellement inutilisé mais conservé
        pour compatibilité avec d’autres modules).
    """
    st.subheader("Avg Perceived Distance by Velocity (errors by Weather)")

    # Chargement des données MySQL
    try:
        df = load_perception_df()
    except Exception as e:
        st.error(f"Erreur de chargement MySQL : {e}")
        return

    if df.empty:
        st.info("Aucune donnée trouvée dans la table Perception.")
        return

    # Construction et affichage de la figure
    fig = build_figure(df)
    st.plotly_chart(fig, use_container_width=True)
