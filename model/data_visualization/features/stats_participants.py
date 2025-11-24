from __future__ import annotations
"""
Streamlit port of: plot_stats_participants.py
- Histogrammes pour Age, Height, Scale, Driver License, Sex
- Ajoute moyennes et écarts-types (sous forme d'un "bar" vertical avec error_x) comme dans la version Dash

Dépendances :
    pip install streamlit plotly pandas mysql-connector-python
"""

from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

try:
    from db_utils import get_db_connection
except Exception:
    get_db_connection = None


@st.cache_data(show_spinner=False)
def load_participants_df() -> pd.DataFrame:
    if get_db_connection is None:
        raise RuntimeError("db_utils.get_db_connection introuvable/import impossible.")
    conn, cursor = get_db_connection()
    try:
        cursor.execute("SELECT participant_id, age, sex, height, driver_license, scale FROM participant;")
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

    df = pd.DataFrame(rows, columns=cols)
    df["sex_normalized"] = df["sex"].map({"Man": 0, "Woman": 1})
    return df


def _add_stats(fig, col_data: pd.Series, row: int, col: int):
    if pd.api.types.is_numeric_dtype(col_data):
        mean_val = float(col_data.mean())
        std_val = float(col_data.std()) if pd.notna(col_data.std()) else 0.0
        max_freq = int(col_data.value_counts().max()) if not col_data.empty else 0
        fig.add_trace(
            go.Bar(
                x=[mean_val],
                y=[max_freq],
                error_x=dict(type="data", symmetric=True, array=[std_val]),
                name="Std Dev",
                marker=dict(color="rgba(255,0,0,0.3)"),
                hovertemplate=f"Mean: {mean_val:.2f}<br>Std Dev: {std_val:.2f}<extra></extra>",
                showlegend=False,
            ),
            row=row,
            col=col,
        )


def build_figure(df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=2, cols=3)

    # Age
    fig.add_trace(
        go.Histogram(
            x=df["age"],
            name="Age",
            nbinsx=df["age"].nunique(),
            xbins=dict(start=df["age"].min() - 0.5, end=df["age"].max() + 0.5, size=1),
        ),
        row=1,
        col=1,
    )
    fig.update_xaxes(range=[19, 65], row=1, col=1)
    _add_stats(fig, df["age"], row=1, col=1)

    # Height
    fig.add_trace(
        go.Histogram(
            x=df["height"], 
            name="Height (cm)", 
            nbinsx=max(10, len(df)//2),
        ), 
        row=1, 
        col=2,
        )
    fig.update_xaxes(range=[159, 193], row=1, col=2)
    _add_stats(fig, df["height"], row=1, col=2)

    # Scale (1..7)
    fig.add_trace(go.Histogram(x=df["scale"], name="Scale", nbinsx=7), row=1, col=3)
    fig.update_xaxes(range=[1, 8], tickvals=[1, 2, 3, 4, 5, 6, 7], row=1, col=3)
    _add_stats(fig, df["scale"], row=1, col=3)

    # Driver license (0/1)
    fig.add_trace(go.Histogram(x=df["driver_license"], name="Driver's License"), row=2, col=1)
    fig.update_xaxes(tickmode="array", tickvals=[0, 1], ticktext=["No", "Yes"], row=2, col=1)

    # Sex (0/1)
    fig.add_trace(go.Histogram(x=df["sex_normalized"], name="Gender"), row=2, col=2)
    fig.update_xaxes(tickmode="array", tickvals=[0, 1], ticktext=["Man", "Woman"], row=2, col=2)

    # Mise en forme
    fig.update_layout(
        showlegend=False,
        hovermode="x unified",
        title_font=dict(size=11),
        font=dict(family="Arial, sans-serif", size=9),
        bargap=0,
    )

    # Titres axes
    fig.update_xaxes(title_text="Age (years)", row=1, col=1)
    fig.update_yaxes(title_text="Number of Participants", row=1, col=1)

    fig.update_xaxes(title_text="Height (cm)", row=1, col=2)
    fig.update_yaxes(title_text="Number of Participants", row=1, col=2)

    fig.update_xaxes(title_text="Close to Reality (1: not close at all - 7: Very Close)", row=1, col=3)
    fig.update_yaxes(title_text="Number of Participants", row=1, col=3)

    fig.update_xaxes(title_text="Driver's License", row=2, col=1)
    fig.update_yaxes(title_text="Number of Participants", row=2, col=1)

    fig.update_xaxes(title_text="Gender", row=2, col=2)
    fig.update_yaxes(title_text="Number of Participants", row=2, col=2)

    return fig


def render(base_path: Path) -> None:
    st.subheader("Participant Statistics")

    try:
        df = load_participants_df()
    except Exception as e:
        st.error(f"Erreur de chargement MySQL : {e}")
        return

    if df.empty:
        st.info("Aucune donnée trouvée dans la table Participant.")
        return

    fig = build_figure(df)
    st.plotly_chart(fig, use_container_width=True)
