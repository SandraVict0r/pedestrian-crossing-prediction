from __future__ import annotations
"""
Streamlit port of: plot_safety_distance_participant_variables.py

Objectif :
- Étudier la relation entre une variable participant (âge, sexe, taille, permis, scale)
  et la distance de sécurité (Crossing Limit).
- Pour chaque combinaison météo × vitesse :
      → on affiche un nuage de points (valeur participant vs safety_distance)
- La figure produit 3 sous-graphiques (Clear, Rain, Night).

- En complément : une table de corrélation automatique comprenant
      → Pearson (linéaire)
      → Spearman (monotone)
      pour chaque condition météo × vitesse, + global.

- Mise en évidence (couleurs) des p-values < 0.01.

Ce script est un **pont** entre :
    - la table participant (profil)
    - la table crossing (comportement)
"""

from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from scipy.stats import pearsonr, spearmanr

# Import flexible pour deployment Streamlit
try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None

# Groupes de vitesse utilisés dans l’expérience VR (km/h)
VELOCITY_GROUPS: Dict[str, Tuple[float, float]] = {
    "low": (20.0, 30.0),
    "medium": (40.0, 50.0),
    "high": (60.0, 70.0),
}

# Couleurs associées
VELOCITY_COLOR = {"low": "#1f77b4", "medium": "#2ca02c", "high": "#d62728"}
WEATHERS = ["clear", "rain", "night"]


def velocity_category(velocity_id: float) -> str:
    """
    Classe une vitesse exacte (20/30/40/50/60/70) dans un groupe low/medium/high.
    """
    if velocity_id in VELOCITY_GROUPS["low"]:
        return "low"
    if velocity_id in VELOCITY_GROUPS["medium"]:
        return "medium"
    return "high"


def _map_value(raw, selected_column: str):
    """
    Convertit la valeur du participant en une représentation numérique exploitable sur l’axe X.
    
    - driver_license : bool → {0, 1}
    - sex : Woman/Man → {0, 1}
    - les autres colonnes (age, height, scale) → valeur numérique brute
    """
    if selected_column == "driver_license":
        return 1 if bool(raw) else 0
    if selected_column == "sex":
        return 1 if str(raw) == "Man" else 0
    return raw


@st.cache_data(show_spinner=False)
def fetch_data(selected_column: str):
    """
    Récupère et agrège les données pour la variable sélectionnée.

    SQL :
    - jointure crossing × participant
    - aggregation AVG(safety_distance) par :
          participant_id × weather_id × velocity_id × selected_column

    Sortie :
    - data_by_weather_velocity : dict imbriqué [weather][velocity] → liste de tuples (pid, safety_distance, X)
    - all_safety_distances : toutes les distances agrégées (global)
    - all_values : toutes les valeurs X (global)

    Utilisé pour :
    - construire la figure
    - calculer les corrélations
    """

    if get_db_connection is None:
        raise RuntimeError("db_utils.get_db_connection introuvable/import impossible.")

    conn, cursor = get_db_connection()
    try:
        query = f"""
            SELECT 
                c.participant_id,
                c.weather_id,
                c.velocity_id,
                AVG(c.safety_distance) AS safety_distance,
                p.{selected_column}
            FROM crossing c
            JOIN participant p ON c.participant_id = p.participant_id
            GROUP BY c.participant_id, c.weather_id, c.velocity_id, p.{selected_column};
        """
        cursor.execute(query)
        rows = cursor.fetchall()
    finally:
        try: cursor.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass

    data_by_weather_velocity: Dict[str, Dict[float, List[Tuple[Any, float, float]]]] = {}
    all_safety_distances: List[float] = []
    all_values: List[float] = []

    # Construction de la structure exploitable
    for participant_id, weather_id, velocity_id, safety_distance, selected_value in rows:

        if safety_distance is None or selected_value is None:
            continue

        # Conversion en valeur numérique
        xval = _map_value(selected_value, selected_column)

        # Si conversion impossible → ignorer
        try:
            xval = float(xval)
        except Exception:
            continue

        all_safety_distances.append(float(safety_distance))
        all_values.append(xval)

        data_by_weather_velocity \
            .setdefault(str(weather_id), {}) \
            .setdefault(float(velocity_id), []) \
            .append((participant_id, float(safety_distance), xval))

    return data_by_weather_velocity, all_safety_distances, all_values


def create_graph(data_by_weather_velocity, all_safety_distances, all_values, selected_column: str) -> go.Figure:
    """
    Produit la figure avec 3 sous-graphes :
        Clear | Rain | Night
        
    Chaque point = un participant × (weather × velocity).
    Axe X = variable (age/sex/height/driver_license/scale)
    Axe Y = crossing limit (distance de sécurité moyenne)

    Les couleurs différencient les groupes de vitesse.
    """

    fig = make_subplots(rows=1, cols=3, subplot_titles=["Clear", "Rain", "Night"])
    legend_added = {"low": False, "medium": False, "high": False}

    for col_idx, weather in enumerate(WEATHERS, start=1):
        if weather not in data_by_weather_velocity:
            continue

        for velocity_id, participant_data in data_by_weather_velocity[weather].items():
            vcat = velocity_category(float(velocity_id))
            color = VELOCITY_COLOR.get(vcat, "#444")

            # Afficher la légende seulement une fois par groupe de vitesse
            show_legend = not legend_added[vcat]
            if show_legend:
                legend_added[vcat] = True

            # Ajout des points
            for pid, sdist, xval in participant_data:
                fig.add_trace(
                    go.Scatter(
                        x=[xval],
                        y=[sdist],
                        mode="markers",
                        marker=dict(color=color, size=6),
                        name=f"{vcat.capitalize()} Speed",
                        legendgroup=vcat,
                        showlegend=show_legend,
                        text=f"Participant {pid}",
                    ),
                    row=1, col=col_idx,
                )

    # Construction des étiquettes X
    x_title = selected_column.capitalize()
    if selected_column == "sex":
        x_title = "Sex (Woman=0, Man=1)"
    elif selected_column == "driver_license":
        x_title = "Driver License (No=0, Yes=1)"

    # Définition des bornes dynamiques X & Y
    x_min = float(min(all_values)) if all_values else 0.0
    x_max = float(max(all_values)) if all_values else 1.0
    y_min = float(min(all_safety_distances)) if all_safety_distances else 0.0
    y_max = float(max(all_safety_distances)) if all_safety_distances else 1.0

    # Granularité de l’axe X selon la variable
    dtick_x = 10 if selected_column == "height" else (5 if selected_column == "age" else 1)

    # Layout final
    fig.update_layout(
        template="plotly_white",
        showlegend=True,
        xaxis_title=x_title,
        yaxis_title="Crossing Limit (m)",
        height=520,
        margin=dict(t=60, b=40, l=40, r=20),
    )
    fig.update_xaxes(range=[x_min - 1, x_max + 1], tickmode="linear", dtick=dtick_x)
    fig.update_yaxes(range=[y_min - 1, y_max + 1], tickmode="linear", dtick=20)

    return fig


def calculate_correlations(data_by_weather_velocity, all_values: List[float], all_safety: List[float], selected_column: str) -> pd.DataFrame:
    """
    Calcule les p-values des corrélations Pearson & Spearman :

    - Pour chaque météo × groupe de vitesse
    - En global sur toutes conditions

    Cas particulier :
    - Si selected_column == "height" → filtrage [160, 180] cm pour éviter les extrêmes
    """

    rows = []

    # Fonction imbriquée qui calcule les p-values Pearson/Spearman
    def corr_pair(x: List[float], y: List[float]):
        if len(x) < 3:
            return np.nan, np.nan
        try:
            p_corr, p_p = pearsonr(x, y)
        except Exception:
            p_p = np.nan
        try:
            s_corr, s_p = spearmanr(x, y)
        except Exception:
            s_p = np.nan
        return p_p, s_p

    # --- Corrélations par météo × vitesse ---
    for weather, vdict in data_by_weather_velocity.items():
        # Buckets par groupe de vitesse (Low/Medium/High)
        buckets = {"Low": [], "Medium": [], "High": []}

        for velocity_id, pdata in vdict.items():
            vcat = velocity_category(float(velocity_id))
            key = vcat.capitalize()
            buckets[key].extend(pdata)

        # Calcul pour chaque bucket
        for key, pdata in buckets.items():
            if not pdata:
                continue

            xs = [v for (_pid, _sd, v) in pdata]
            ys = [sd for (_pid, sd, _v) in pdata]

            # Filtrage spécifique height
            if selected_column == "height":
                filt = [(160.0 <= x <= 180.0) for x in xs]
                xs = [x for x, keep in zip(xs, filt) if keep]
                ys = [y for y, keep in zip(ys, filt) if keep]

            p_p, s_p = corr_pair(xs, ys)

            rows.append({
                "Weather": weather.capitalize(),
                "Velocity": key,
                "Pearson": p_p,
                "Spearman": s_p,
            })

    # --- Corrélations globales ---
    xs_g, ys_g = list(all_values), list(all_safety)

    if selected_column == "height":
        filt = [(160.0 <= x <= 180.0) for x in xs_g]
        xs_g = [x for x, keep in zip(xs_g, filt) if keep]
        ys_g = [y for y, keep in zip(ys_g, filt) if keep]

    p_p, s_p = corr_pair(xs_g, ys_g)

    rows.append({
        "Weather": "Global",
        "Velocity": "Global",
        "Pearson": p_p,
        "Spearman": s_p,
    })

    # Retour sous forme de DataFrame
    return pd.DataFrame(rows, columns=["Weather", "Velocity", "Pearson", "Spearman"])


def _style_corr(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """
    Style avancé du tableau de corrélations :
    - Surlignage vert si Pearson < 0.01 ET Spearman < 0.01
    - Surlignage bleu si Pearson < 0.01
    - Surlignage jaune si Spearman < 0.01
    - Formatage scientifique {X.Ye-Z}
    """

    def color_row(r):
        p = r.get("Pearson", np.nan)
        s = r.get("Spearman", np.nan)
        if pd.notna(p) and pd.notna(s) and p < 0.01 and s < 0.01:
            return ["background-color: green; color: white;"] * len(r)
        return [""] * len(r)

    def color_cells(colname: str, color: str, text: str):
        """Coloration colonne Pearson ou Spearman conditionnée sur p-value."""
        def f(col):
            styles = [""] * len(col)
            for i, val in enumerate(col):
                try:
                    if float(val) < 0.01:
                        styles[i] = f"background-color: {color}; color: {text};"
                except Exception:
                    pass
            return styles
        return f

    styler = (
        df.style
        .apply(lambda r: color_row(r), axis=1)
        .apply(color_cells("Pearson", "blue", "white"), subset=["Pearson"])
        .apply(color_cells("Spearman", "yellow", "black"), subset=["Spearman"])
        .format({"Pearson": "{:.3e}", "Spearman": "{:.3e}"})
    )

    return styler


def render(base_path: Path) -> None:
    """
    Fonction Streamlit :
    - Sélection de la variable participant
    - Construction de la figure 3×3 (météos)
    - Calcul & affichage des corrélations
    """

    st.subheader("Pedestrian–Car Gap (Crossing Limit) vs Participant Characteristics")

    # Menu de sélection de la variable participant
    selected_column = st.selectbox(
        "Variable",
        options=[
            ("Age", "age"),
            ("Sex", "sex"),
            ("Height (cm)", "height"),
            ("Driver License", "driver_license"),
            ("Scale", "scale"),
        ],
        index=2,
        format_func=lambda x: x[0],
    )[1]

    try:
        data_by_wv, all_safety, all_vals = fetch_data(selected_column)
    except Exception as e:
        st.error(f"Erreur de chargement MySQL : {e}")
        return

    if not all_safety or not all_vals:
        st.info("Aucune donnée exploitable.")
        return

    # Figure principale
    fig = create_graph(data_by_wv, all_safety, all_vals, selected_column)
    st.plotly_chart(fig, use_container_width=True)

    # Table des corrélations
    corr_df = calculate_correlations(data_by_wv, all_vals, all_safety, selected_column)
    st.markdown("**Correlations (p-values)**")

    try:
        st.dataframe(_style_corr(corr_df), use_container_width=True)
    except Exception:
        # Fallback si l’environnement Streamlit bloque les styles HTML
        st.dataframe(corr_df, use_container_width=True)

    # Explication selon variable
    if selected_column == "height":
        st.info(
            "Pearson et Spearman sont calculés après restriction de la taille à [160, 180] cm (global et par conditions)."
        )
    else:
        st.caption(
            "La table montre les p-values Pearson et Spearman pour la variable sélectionnée."
        )
