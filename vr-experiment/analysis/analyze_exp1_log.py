# =====================================================================
# Analyse Expérience 1 — Script Streamlit
# Analyse du temps perçu vs temps réel pour les trials de l'expérience 1
# Lecture des CSV Unreal/CARLA + Excel Python + calculs + visualisations
# =====================================================================

import re, math
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ===========================
# Réglages par défaut
# ===========================
# Dossier où Unreal Engine écrit Logs/<N>/peds.csv, cars.csv, gaze.csv
DEFAULT_LOGS = r"C:\Users\carlaue5.3\CarlaUE5\Unreal\CarlaUnreal\Logs"

# ===========================
# Utils lecture & calculs
# ===========================

def _num_from_any(series: pd.Series) -> pd.Series:
    """
    Convertit une colonne en valeurs numériques robustes :
      - extrait un nombre depuis : '60', '60 km/h', '60,0', etc.
      - remplace les virgules par des points
      - convertit en float, NaN si impossible.
    """
    s = series.astype(str).str.extract(r'([-+]?\d+[.,]?\d*)', expand=False)
    s = s.str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce')


def read_cars_csv(p: Path) -> pd.DataFrame:
    """
    Lecture robuste du fichier cars.csv d’un trial.
    - Essaye d'abord le séparateur ';', sinon ','.
    - Normalise les noms de colonnes en Time, Time_estimated, X_pos, X_est.
    - Ajoute X_est = 0.0 si absent (sécurité).
    """
    try:
        df = pd.read_csv(p, sep=';')
    except Exception:
        df = pd.read_csv(p)

    # normalisation des noms
    ren = {}
    for c in df.columns:
        l = c.strip().lower()
        if l == 'time': ren[c] = 'Time'
        elif 'time_est' in l: ren[c] = 'Time_estimated'
        elif 'x_pos' in l or l == 'x': ren[c] = 'X_pos'
        elif 'x_est' in l: ren[c] = 'X_est'

    df = df.rename(columns=ren)

    # colonnes indispensables
    for k in ['Time', 'Time_estimated', 'X_pos']:
        if k not in df.columns:
            raise ValueError(f"{p.name}: colonne manquante '{k}'")

    # X_est optionnelle → mise à zéro
    if 'X_est' not in df.columns:
        df['X_est'] = 0.0

    return df


def disappearance_time(time, x, ignore_first_seconds: float, hold: int, eps: float=1e-6) -> float:
    """
    Détection automatique du temps où la voiture "disparaît".
    - On cherche la première transition nonzéro -> zéro qui reste zéro au moins `hold` frames.
    - On ignore les x_pos=0 au tout début (ligne d'initialisation Unreal).
    - Fallback : prend le temps du minimum absolu de X_pos.
    """
    t = np.asarray(time, dtype=float)
    x = np.asarray(x, dtype=float)

    # Début réel du mouvement (ignorer artificiellement les valeurs initiales)
    tmin = float(np.nanmin(t))
    mask = t >= (tmin + ignore_first_seconds - 1e-6)
    if mask.sum() < 2:
        mask = np.ones_like(t, dtype=bool)

    t2, x2 = t[mask], x[mask]

    # états non-zéro et zéro
    nz = np.abs(x2) > eps
    z  = ~nz

    # transitions nonzéro -> zéro
    trans = np.where(nz[:-1] & z[1:])[0]

    # validation du "zéro soutenu pendant hold frames"
    for i in trans:
        i1 = i + 1
        i2 = min(i1 + hold, len(x2))
        if np.all(~(np.abs(x2[i1:i2]) > eps)):
            return float(t2[i1])

    # fallback : minimum absolu
    j = int(np.argmin(np.abs(x2)))
    return float(t2[j])


def first_press_time(df: pd.DataFrame, press_source: str):
    """
    Détection du premier appui participant :
    Deux sources possibles :
      - Time_estimated != 0 (snap du participant)
      - X_est != 0        (données envoyées par Python)
    """
    if press_source == "Time_estimated":
        s = df.loc[df['Time_estimated'] != 0, 'Time']
    else:
        s = df.loc[df['X_est'] != 0, 'Time']

    return None if s.empty else float(s.iloc[0])


def load_exp1_excel(excel_path: Path) -> pd.DataFrame:
    """
    Lecture du fichier Excel contenant :
      - vitesse
      - distance de disparition
      - position (spawn participant)
      - météo
    Renommage automatique + conversion numérique.
    """
    df = pd.read_excel(excel_path)

    colmap = {}
    for c in df.columns:
        l = c.strip().lower()
        if 'velocity' in l: colmap[c] = 'velocity_kmh'
        elif 'distance' in l: colmap[c] = 'disappear_m'
        elif 'position' in l: colmap[c] = 'position'
        elif 'weather'  in l: colmap[c] = 'weather'
        elif 'trial'    in l: colmap[c] = 'trial'

    df = df.rename(columns=colmap)

    # si "trial" absent → numérote automatiquement
    if 'trial' not in df.columns:
        df['trial'] = np.arange(1, len(df) + 1)

    keep = ['trial', 'velocity_kmh', 'disappear_m', 'position', 'weather']
    for k in keep:
        if k not in df.columns:
            df[k] = np.nan

    df = df[keep]

    # conversions numériques
    df['velocity_kmh'] = _num_from_any(df['velocity_kmh'])
    df['disappear_m']  = _num_from_any(df['disappear_m']).abs()
    df['position']     = pd.to_numeric(df['position'], errors='coerce')

    return df.set_index('trial').sort_index()


def metrics_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule les métriques d’erreur :
      - biais
      - MAE
      - RMSE
      - écart-type
      - % correct (selon tolérance)
    """
    s = df['err_s'].dropna().values
    if s.size == 0:
        return pd.DataFrame([dict(n=0, bias=np.nan, mae=np.nan, rmse=np.nan,
                                  std=np.nan, p_correct=np.nan)])

    out = dict(
        n=int(s.size),
        bias=float(np.mean(s)),
        mae=float(np.mean(np.abs(s))),
        rmse=float(np.sqrt(np.mean(s**2))),
        std=float(np.std(s, ddof=1)) if s.size > 1 else 0.0,
        p_correct=float(np.mean(df['correct'])) if 'correct' in df else np.nan
    )

    return pd.DataFrame([out])


def aggregate(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """
    Agrège les métriques par :
      - vitesse
      - météo
      - distance
    """
    rows = []
    for k, g in df.groupby(key):
        mt = metrics_table(g).iloc[0].to_dict()
        mt[key] = k
        rows.append(mt)

    cols = [key, 'n', 'bias', 'mae', 'rmse', 'std', 'p_correct']
    return pd.DataFrame(rows)[cols].sort_values(by=key).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def analyze_logs(logs_dir: str, tolerance_sec: float, ignore_first_seconds: float, hold_zeros: int, press_source: str):
    """
    Fonction principale :
    - cherche Excel exp1 dans Logs
    - charge chaque dossier <N>
    - lit cars.csv → détecte t_disappear et t_press
    - calcule t_true = distance / vitesse
    - calcule erreur err_s
    - retourne :
        inputs (excel), df complet, agrégations
    """
    root = Path(logs_dir)

    # recherche du fichier Excel consigne exp1
    excel = None
    for f in root.iterdir():
        if f.suffix.lower() == '.xlsx' and 'exp1' in f.name.lower():
            excel = f
            break
    if excel is None:
        raise FileNotFoundError("Aucun fichier Excel 'exp1*.xlsx' trouvé dans ce dossier.")

    inputs = load_exp1_excel(excel)

    # dossiers de trials : "1", "2", "3", ...
    trial_dirs = [d for d in root.iterdir() if d.is_dir() and re.fullmatch(r'\d+', d.name)]
    trial_dirs.sort(key=lambda p: int(p.name))

    rows = []
    for d in trial_dirs:
        trial = int(d.name)

        # détection robuste de cars.csv
        cars_csv = d / 'cars.csv'
        if not cars_csv.exists():
            alts = [p for p in d.iterdir()
                    if p.is_file() and p.suffix.lower()=='.csv' and 'car' in p.name.lower()]
            if alts:
                cars_csv = alts[0]

        if not cars_csv.exists():
            continue

        # extraction des temps
        try:
            cars = read_cars_csv(cars_csv)
            t_disappear = disappearance_time(
                cars['Time'].values, cars['X_pos'].values,
                ignore_first_seconds, hold_zeros
            )
            t_press = first_press_time(cars, press_source)
        except Exception:
            t_disappear, t_press = np.nan, np.nan

        # paramètres du trial (depuis Excel)
        if trial in inputs.index:
            v_kmh = float(inputs.loc[trial, 'velocity_kmh'])
            d_m   = float(inputs.loc[trial, 'disappear_m'])
            pos   = inputs.loc[trial, 'position']
            wthr  = inputs.loc[trial, 'weather']
        else:
            v_kmh, d_m, pos, wthr = np.nan, np.nan, np.nan, None

        # calcul temps théorique = distance / vitesse
        v_mps  = (v_kmh / 3.6) if (not math.isnan(v_kmh)) else np.nan
        t_true = (d_m / v_mps) if (pd.notna(d_m) and pd.notna(v_mps) and v_mps > 0) else np.nan

        # temps perçu par le participant
        if (t_press is None) or any(math.isnan(x) for x in [t_disappear, t_press]):
            t_perceived = np.nan
            err_s = np.nan
        else:
            # définition : (appui participant) − (disparition voiture)
            t_perceived = float(t_press - t_disappear)
            err_s = float(t_perceived - t_true)

        # correct = erreur <= tolérance
        correct = (abs(err_s) <= tolerance_sec) if not math.isnan(err_s) else False

        rows.append(dict(
            trial=trial,
            velocity_kmh=v_kmh,
            disappear_m=d_m,
            position=pos,
            weather=wthr,
            t_disappear=t_disappear,
            t_press=(np.nan if t_press is None else t_press),
            t_true=t_true,
            t_perceived=t_perceived,
            err_s=err_s,
            correct=bool(correct)
        ))

    df = pd.DataFrame(rows).sort_values('trial').reset_index(drop=True)

    # agrégations
    df_valid = df.dropna(subset=['err_s'])
    agg_vel = aggregate(df_valid, 'velocity_kmh') if not df_valid.empty else pd.DataFrame()
    agg_wth = aggregate(df_valid, 'weather')      if not df_valid.empty else pd.DataFrame()
    agg_dst = aggregate(df_valid, 'disappear_m')  if not df_valid.empty else pd.DataFrame()

    return inputs, df, agg_vel, agg_wth, agg_dst


# ===========================
# Interface graphique Streamlit
# ===========================

st.set_page_config(page_title="Expérience 1 – Analyse", layout="wide")
st.title("Expérience 1 — Temps perçu vs réel (CARLA/UE)")

# barre latérale paramètres
with st.sidebar:
    st.header("Paramètres")

    logs_dir = st.text_input("Dossier Logs (contient exp1.xlsx + 1 dossier par trial)", DEFAULT_LOGS)

    colA, colB = st.columns(2)
    tolerance = colA.number_input("Tolérance (s)", value=0.25, min_value=0.0, step=0.05)
    ignore_first = colB.number_input("Ignorer tête (s)", value=1.0, min_value=0.0, step=0.1)

    colC, colD = st.columns(2)
    hold_zeros = int(colC.number_input("Zéros consécutifs (hold)", value=3, min_value=1, step=1))
    press_source = colD.selectbox("Source appui", ["Time_estimated", "X_est"])

    st.caption("• Temps perçu = t(appui) − t(disparition X_pos)\n• Temps réel = distance / (vitesse/3.6)")

    ready = st.button("Analyser", use_container_width=True)

# lancement traitement
if ready:
    try:
        inputs, df, agg_vel, agg_wth, agg_dst = analyze_logs(
            logs_dir, tolerance, ignore_first, hold_zeros, press_source
        )
    except Exception as e:
        st.error(str(e))
    else:
        # ===========================
        # KPIs globaux
        # ===========================
        kpi = metrics_table(df.dropna(subset=['err_s']))

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Essais valides", int(kpi['n'].iloc[0]) if not kpi.empty else 0)
        c2.metric("Biais (s)", f"{kpi['bias'].iloc[0]:.3f}" if not kpi.empty else "–")
        c3.metric("MAE (s)", f"{kpi['mae'].iloc[0]:.3f}" if not kpi.empty else "–")
        c4.metric("RMSE (s)", f"{kpi['rmse'].iloc[0]:.3f}" if not kpi.empty else "–")
        c5.metric("% Correct", f"{100*kpi['p_correct'].iloc[0]:.1f}%" if not kpi.empty else "–")

        # ===========================
        # Filtres utilisateur
        # ===========================
        st.subheader("Filtres")

        fcol1, fcol2, fcol3 = st.columns(3)
        vel_choices = sorted(df['velocity_kmh'].dropna().unique().tolist())
        dst_choices = sorted(df['disappear_m'].dropna().unique().tolist())
        wth_choices = sorted(df['weather'].dropna().astype(str).unique().tolist())

        sel_vel = fcol1.multiselect("Vitesses (km/h)", vel_choices, default=vel_choices)
        sel_dst = fcol2.multiselect("Distances (m)",  dst_choices, default=dst_choices)
        sel_wth = fcol3.multiselect("Météo",          wth_choices, default=wth_choices)

        dff = df.copy()
        dff['weather'] = dff['weather'].astype(str)
        dff = dff[
            dff['velocity_kmh'].isin(sel_vel) &
            dff['disappear_m'].isin(sel_dst) &
            dff['weather'].isin(sel_wth)
        ]

        # ===========================
        # Graphes
        # ===========================
        st.markdown("### Perçu vs Réel")

        # graphe perçu vs réel
        valid_pairs = dff.dropna(subset=['t_true','t_perceived'])
        if not valid_pairs.empty:
            fig = px.scatter(valid_pairs, x='t_true', y='t_perceived',
                             color='weather',
                             hover_data=['trial','velocity_kmh','disappear_m'])

            lo = float(min(valid_pairs[['t_true','t_perceived']].min().min(), 0))
            hi = float(valid_pairs[['t_true','t_perceived']].max().max())
            fig.add_trace(go.Scatter(x=[lo,hi], y=[lo,hi], mode='lines', name='y=x'))
            fig.update_layout(legend_title="Météo",
                              xaxis_title="Temps réel (s)",
                              yaxis_title="Temps perçu (s)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucune donnée valide pour ce filtre.")

        # histogramme erreurs
        colL, colR = st.columns(2)
        with colL:
            st.markdown("### Histogramme des erreurs (s)")
            e = dff['err_s'].dropna()
            if not e.empty:
                fig = px.histogram(e, x='err_s',
                                   nbins=min(40, max(10, int(np.sqrt(len(e))*3))))
                fig.add_vline(x=0, line_dash='dash')
                fig.update_layout(xaxis_title="Erreur (s)  (>0 = en retard, <0 = en avance)",
                                  yaxis_title="Fréquence")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Pas d'erreurs à afficher.")

        # boxplots
        with colR:
            st.markdown("### Boîtes par vitesse (erreur en s)")
            if not dff.dropna(subset=['err_s']).empty:
                fig = px.box(dff, x='velocity_kmh', y='err_s', points='all')
                fig.add_hline(y=0, line_dash='dash')
                fig.update_layout(xaxis_title="Vitesse (km/h)", yaxis_title="Erreur (s)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Pas de données pour les boîtes.")

        colB1, colB2 = st.columns(2)
        with colB1:
            st.markdown("### Boîtes par météo")
            if not dff.dropna(subset=['err_s']).empty:
                fig = px.box(dff, x='weather', y='err_s', points='all')
                fig.add_hline(y=0, line_dash='dash')
                fig.update_layout(xaxis_title="Météo", yaxis_title="Erreur (s)")
                st.plotly_chart(fig, use_container_width=True)

        with colB2:
            st.markdown("### Boîtes par distance")
            if not dff.dropna(subset=['err_s']).empty:
                fig = px.box(dff, x='disappear_m', y='err_s', points='all')
                fig.add_hline(y=0, line_dash='dash')
                fig.update_layout(xaxis_title="Distance (m)", yaxis_title="Erreur (s)")
                st.plotly_chart(fig, use_container_width=True)

        # ===========================
        # Tableau des trials
        # ===========================
        st.markdown("### Tableau des essais")

        st.dataframe(
            dff[['trial','velocity_kmh','disappear_m','weather',
                 't_true','t_perceived','err_s','correct']]
            .round({'t_true':3, 't_perceived':3, 'err_s':3})
            .sort_values('trial'),
            use_container_width=True, height=360
        )

        # (La partie finale du script — inspecteur graphique d'un trial —
        #  n’est pas incluse dans ton extrait)
