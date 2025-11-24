from __future__ import annotations
"""
Streamlit port of: plot_safety_distance_participant_variables.py
- Sélection d'une variable (age, sex, height, driver_license, scale)
- Joint Crossing × Participant, moyenne de safety_distance par (participant, weather, velocity, variable)
- Graphe : 3 sous-graphiques (Clear/Rain/Night), couleurs par catégorie de vitesse (low/medium/high)
- Tableau des corrélations (p-values Pearson & Spearman) par météo × catégorie de vitesse + global
  avec surlignage conditionnel (< 0.01)

Dépendances :
    pip install streamlit plotly pandas numpy mysql-connector-python scipy
"""

from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from scipy.stats import pearsonr, spearmanr

try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None

# Catégories de vitesse (km/h)
VELOCITY_GROUPS: Dict[str, Tuple[float, float]] = {
    "low": (20.0, 30.0),
    "medium": (40.0, 50.0),
    "high": (60.0, 70.0),
}
VELOCITY_COLOR = {"low": "#1f77b4", "medium": "#2ca02c", "high": "#d62728"}
WEATHERS = ["clear", "rain", "night"]


def velocity_category(velocity_id: float) -> str:
    if velocity_id in VELOCITY_GROUPS["low"]:
        return "low"
    if velocity_id in VELOCITY_GROUPS["medium"]:
        return "medium"
    return "high"


def _map_value(raw, selected_column: str):
    """Map variable vers numérique pour l'axe X.
    - driver_license: bool → {0,1}
    - sex: 'Man'/'Woman' → {1,0}
    - sinon: valeur telle quelle
    """
    if selected_column == "driver_license":
        return 1 if bool(raw) else 0
    if selected_column == "sex":
        return 1 if str(raw) == "Man" else 0
    return raw


@st.cache_data(show_spinner=False)
def fetch_data(selected_column: str):
    """Récupère et agrège les données pour la variable choisie.
    Retourne:
        data_by_weather_velocity: dict[weather][velocity] -> list[(participant_id, safety_distance, mapped_value)]
        all_safety_distances: List[float]
        all_values: List[float]
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
            FROM Crossing c
            JOIN participant p ON c.participant_id = p.participant_id
            GROUP BY c.participant_id, c.weather_id, c.velocity_id, p.{selected_column};
        """
        cursor.execute(query)
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

    data_by_weather_velocity: Dict[str, Dict[float, List[Tuple[Any, float, float]]]] = {}
    all_safety_distances: List[float] = []
    all_values: List[float] = []

    for participant_id, weather_id, velocity_id, safety_distance, selected_value in rows:
        if safety_distance is None or selected_value is None:
            continue
        xval = _map_value(selected_value, selected_column)
        try:
            xval = float(xval)
        except Exception:
            # ignore lignes non convertibles
            continue

        all_safety_distances.append(float(safety_distance))
        all_values.append(xval)

        data_by_weather_velocity.setdefault(str(weather_id), {}).setdefault(float(velocity_id), []).append(
            (participant_id, float(safety_distance), xval)
        )

    return data_by_weather_velocity, all_safety_distances, all_values


def create_graph(data_by_weather_velocity, all_safety_distances, all_values, selected_column: str) -> go.Figure:
    fig = make_subplots(rows=1, cols=3, subplot_titles=["Clear", "Rain", "Night"])
    legend_added = {"low": False, "medium": False, "high": False}

    for col_idx, weather in enumerate(WEATHERS, start=1):
        if weather not in data_by_weather_velocity:
            continue
        for velocity_id, participant_data in data_by_weather_velocity[weather].items():
            vcat = velocity_category(float(velocity_id))
            color = VELOCITY_COLOR.get(vcat, "#444")
            show_legend = not legend_added[vcat]
            if show_legend:
                legend_added[vcat] = True

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

    # Axes + titres
    x_title = selected_column.capitalize()
    if selected_column == "sex":
        x_title = "Sex (Woman=0, Man=1)"
    elif selected_column == "driver_license":
        x_title = "Driver License (No=0, Yes=1)"

    # Ranges & dtick
    if not all_values:
        x_min, x_max = 0.0, 1.0
    else:
        x_min, x_max = float(min(all_values)), float(max(all_values))
    if not all_safety_distances:
        y_min, y_max = 0.0, 1.0
    else:
        y_min, y_max = float(min(all_safety_distances)), float(max(all_safety_distances))

    dtick_x = 10 if selected_column == "height" else (5 if selected_column == "age" else 1)

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
    rows = []

    def corr_pair(x: List[float], y: List[float]):
        if len(x) < 3:
            return np.nan, np.nan  # insuffisant
        try:
            p_corr, p_p = pearsonr(x, y)
        except Exception:
            p_p = np.nan
        try:
            s_corr, s_p = spearmanr(x, y)
        except Exception:
            s_p = np.nan
        return p_p, s_p

    # Par météo × catégorie de vitesse
    for weather, vdict in data_by_weather_velocity.items():
        buckets = {"Low": [], "Medium": [], "High": []}
        for velocity_id, pdata in vdict.items():
            vcat = velocity_category(float(velocity_id))
            key = vcat.capitalize()
            buckets.setdefault(key, []).extend(pdata)
        for key, pdata in buckets.items():
            if not pdata:
                continue
            xs = [v for (_pid, _sd, v) in pdata]
            ys = [sd for (_pid, sd, _v) in pdata]
            # Filtre taille pour height
            if selected_column == "height":
                filt = [(160.0 <= x <= 180.0) for x in xs]
                xs = [x for x, keep in zip(xs, filt) if keep]
                ys = [y for y, keep in zip(ys, filt) if keep]
            p_p, s_p = corr_pair(xs, ys)
            rows.append({"Weather": weather.capitalize(), "Velocity": key, "Pearson": p_p, "Spearman": s_p})

    # Global
    xs_g, ys_g = list(all_values), list(all_safety)
    if selected_column == "height":
        filt = [(160.0 <= x <= 180.0) for x in xs_g]
        xs_g = [x for x, keep in zip(xs_g, filt) if keep]
        ys_g = [y for y, keep in zip(ys_g, filt) if keep]
    p_p, s_p = corr_pair(xs_g, ys_g)
    rows.append({"Weather": "Global", "Velocity": "Global", "Pearson": p_p, "Spearman": s_p})

    df = pd.DataFrame(rows, columns=["Weather", "Velocity", "Pearson", "Spearman"])  # ordre stable
    return df


def _style_corr(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    def color_row(r):
        p = r.get("Pearson", np.nan)
        s = r.get("Spearman", np.nan)
        if pd.notna(p) and pd.notna(s) and p < 0.01 and s < 0.01:
            return ["background-color: green; color: white;"] * len(r)
        return [""] * len(r)

    def color_cells(colname: str, color: str, text: str):
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
    st.subheader("Pedestrian–Car Gap (Crossing Limit) vs Participant Characteristics")

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

    fig = create_graph(data_by_wv, all_safety, all_vals, selected_column)
    st.plotly_chart(fig, use_container_width=True)

    # Corrélations
    corr_df = calculate_correlations(data_by_wv, all_vals, all_safety, selected_column)
    st.markdown("**Correlations (p-values)**")
    try:
        st.dataframe(_style_corr(corr_df), use_container_width=True)
    except Exception:
        # fallback sans style si l'environnement bloque les styles
        st.dataframe(corr_df, use_container_width=True)

    # Texte explicatif
    if selected_column == "height":
        st.info(
            "Pearson et Spearman sont calculés après restriction de la taille à [160, 180] cm (global et par conditions)."
        )
    else:
        st.caption(
            "La table montre les p-values Pearson et Spearman pour la variable sélectionnée. Utilisez les filtres/tri du tableau pour explorer."
        )
