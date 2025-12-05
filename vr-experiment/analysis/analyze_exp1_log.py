# =====================================================================
# Analyse Expérience 1 — Script Streamlit
# Auteur : (Projet Thèse – CARLA/UE5)
#
# Objectif :
#   - Automatiser l’analyse des trials de l’Expérience 1 (TTC estimation)
#   - Lire les données exportées par Unreal/CARLA (peds.csv, cars.csv)
#   - Lire les consignes du trial (Excel généré côté Python)
#   - Reconstituer le TTC réel et perçu
#   - Calculer les erreurs (err_s), les métriques globales
#   - Produire visualisations interactives (Plotly + Streamlit)
#
# Ce script est conçu pour un usage exploratoire et pédagogique
# immédiatement après les sessions VR.
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
# Chemin Windows par défaut. Le script reste compatible Linux/MacOS
# dès lors que l’utilisateur spécifie un dossier manuel.
DEFAULT_LOGS = r"C:\Users\carlaue5.3\CarlaUE5\Unreal\CarlaUnreal\Logs"


# =====================================================================
# 1. Fonctions utilitaires — parsing robuste et lecture CSV
# =====================================================================

def _num_from_any(series: pd.Series) -> pd.Series:
    """
    Convertit une colonne en valeurs numériques robustes.
    Cette fonction est indispensable car les fichiers Excel peuvent
    contenir des entrées comme "60 km/h", "60,0", "  60 ", etc.

    - Extraction regex d'un motif numérique
    - Conversion des virgules -> points
    - Transforme en float, NaN si impossible

    Choix d’implémentation :
        → Le parsing tolérant permet d'éviter des crashs lors de fautes
          de frappe ou variations de format.
    """
    s = series.astype(str).str.extract(r'([-+]?\d+[.,]?\d*)', expand=False)
    s = s.str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce')


def read_cars_csv(p: Path) -> pd.DataFrame:
    """
    Lecture robuste du fichier cars.csv.
    Unreal/CARLA peuvent écrire avec séparateur ';' ou ',' selon machine.
    Cette fonction utilise automatiquement le bon parseur.

    Elle normalise également les noms de colonnes pour simplifier l'analyse.

    Spécificité :
        - X_est est optionnel (selon configuration expérimentale)
          → création d'une colonne X_est=0.0 si absente
          Cela simplifie la logique aval.
    """
    # Tentative : séparateur ';' (format UE/CARLA France)
    try:
        df = pd.read_csv(p, sep=';')
    except Exception:
        df = pd.read_csv(p)  # fallback : ','

    # Normalisation des noms de colonnes
    ren = {}
    for c in df.columns:
        l = c.strip().lower()

        if l == 'time': ren[c] = 'Time'
        elif 'time_est' in l: ren[c] = 'Time_estimated'
        elif 'x_pos' in l or l == 'x': ren[c] = 'X_pos'
        elif 'x_est' in l: ren[c] = 'X_est'

    df = df.rename(columns=ren)

    # Vérification des colonnes obligatoires
    for k in ['Time', 'Time_estimated', 'X_pos']:
        if k not in df.columns:
            raise ValueError(f"{p.name}: colonne manquante '{k}'")

    # Compatibilité ascendante : X_est facultatif
    if 'X_est' not in df.columns:
        df['X_est'] = 0.0

    return df


def disappearance_time(time, x, ignore_first_seconds: float, hold: int, eps: float = 1e-6) -> float:
    """
    Détection automatique de la disparition du véhicule.
    Hypothèses basées sur l'architecture Unreal :
        - Unreal écrit parfois un X_pos=0 pendant quelques frames au chargement.
        - Lorsque le véhicule disparaît, X_pos devient 0 pendant plusieurs frames
          consécutives (≥ hold).

    Stratégie :
        1) Ignore les premières secondes (initialisation moteur)
        2) Détecte une transition (non-zero → zero)
        3) Valide que la zone zéro est persistante (hold frames)
        4) Fallback : prend le minimum absolu de X_pos

    Ce mécanisme est robuste aux glitchs VR/UE et garantit une
    détection stable même sur des machines hétérogènes.
    """
    t = np.asarray(time, dtype=float)
    x = np.asarray(x, dtype=float)

    # Ignore la tête du signal (initialisation UE)
    tmin = float(np.nanmin(t))
    mask = t >= (tmin + ignore_first_seconds - 1e-6)
    if mask.sum() < 2:
        # Si trop peu de données, on désactive le filtrage
        mask = np.ones_like(t, dtype=bool)

    t2, x2 = t[mask], x[mask]

    nz = np.abs(x2) > eps   # état normal
    z  = ~nz                # état disparition

    # transitions non-zero → zero
    trans = np.where(nz[:-1] & z[1:])[0]

    # validation des hold frames
    for i in trans:
        i1 = i + 1
        i2 = min(i1 + hold, len(x2))
        if np.all(~(np.abs(x2[i1:i2]) > eps)):
            return float(t2[i1])

    # fallback (cas extrême)
    j = int(np.argmin(np.abs(x2)))
    return float(t2[j])


def first_press_time(df: pd.DataFrame, press_source: str):
    """
    Détection du premier appui participant.
    Deux sources possibles (selon paramètre utilisateur) :

        A) Time_estimated :
              Unreal écrit Time_estimated != 0 lors d'un snap Exp1
        B) X_est :
              Valeur envoyée par Python (rare mais utile en debug)

    Retourne None si aucun appui n'est détecté.
    """
    if press_source == "Time_estimated":
        s = df.loc[df['Time_estimated'] != 0, 'Time']
    else:
        s = df.loc[df['X_est'] != 0, 'Time']

    return None if s.empty else float(s.iloc[0])


def load_exp1_excel(excel_path: Path) -> pd.DataFrame:
    """
    Lecture du fichier Excel exp1.xlsx généré par les scripts Python.
    On standardise les colonnes afin d'éviter les effets de formatting Excel.

    Le fichier contient :
        - vitesse (km/h)
        - distance de disparition (m)
        - position du participant
        - météo
        - numéro de trial

    La fonction tolère :
        - colonnes désordonnées
        - formats non classiques
        - formats texte
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

    # Si "trial" absent → numérotation incrémentale
    if 'trial' not in df.columns:
        df['trial'] = np.arange(1, len(df) + 1)

    keep = ['trial', 'velocity_kmh', 'disappear_m', 'position', 'weather']
    for k in keep:
        if k not in df.columns:
            # colonne inexistante → remplissage par sécurité
            df[k] = np.nan

    df = df[keep]

    # Conversions numériques robustes
    df['velocity_kmh'] = _num_from_any(df['velocity_kmh'])
    df['disappear_m']  = _num_from_any(df['disappear_m']).abs()
    df['position']     = pd.to_numeric(df['position'], errors='coerce')

    return df.set_index('trial').sort_index()


# =====================================================================
# 2. Métriques d'erreur + agrégations
# =====================================================================

def metrics_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcul des principales métriques d’évaluation :
        - biais
        - MAE
        - RMSE
        - écart-type
        - % correct (selon tolérance)

    La métrique est renvoyée sous forme DataFrame → compatible Streamlit.
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
    Agrège les métriques selon une variable donnée :
        - par vitesse
        - par météo
        - par distance

    La structure retournée s'intègre directement dans Streamlit.
    """
    rows = []
    for k, g in df.groupby(key):
        mt = metrics_table(g).iloc[0].to_dict()
        mt[key] = k
        rows.append(mt)

    cols = [key, 'n', 'bias', 'mae', 'rmse', 'std', 'p_correct']
    return pd.DataFrame(rows)[cols].sort_values(key).reset_index(drop=True)


# =====================================================================
# 3. Pipeline principal — analyse complète des Logs
# =====================================================================

@st.cache_data(show_spinner=False)
def analyze_logs(logs_dir: str, tolerance_sec: float, ignore_first_seconds: float, hold_zeros: int, press_source: str):
    """
    Fonction principale d'analyse.

    Étapes :
        1. Recherche du fichier Excel exp1.xlsx dans logs_dir
        2. Récupération de tous les dossiers <N> correspondant aux trials
        3. Lecture de chaque cars.csv
        4. Détection robuste :
               - t_disappear
               - t_press
        5. Récupération des paramètres du trial depuis Excel
        6. Calcul du TTC théorique (distance / vitesse)
        7. Calcul du TTC perçu
        8. Calcul de l’erreur err_s et du critère "correct"
        9. Agrégations selon vitesse / météo / distance

    La structure de retour :
        inputs → données de consigne (Excel)
        df     → tableau complet trial par trial
        agg_*  → agrégations pour graphiques
    """
    root = Path(logs_dir)

    # Recherche du fichier Excel (exp1)
    excel = None
    for f in root.iterdir():
        if f.suffix.lower() == '.xlsx' and 'exp1' in f.name.lower():
            excel = f
            break
    if excel is None:
        raise FileNotFoundError("Aucun fichier Excel 'exp1*.xlsx' trouvé dans ce dossier.")

    inputs = load_exp1_excel(excel)

    # Dossiers trials = entiers 1, 2, 3, ...
    trial_dirs = [d for d in root.iterdir() if d.is_dir() and re.fullmatch(r'\d+', d.name)]
    trial_dirs.sort(key=lambda p: int(p.name))

    rows = []
    for d in trial_dirs:
        trial = int(d.name)

        # Lecture robuste du cars.csv
        cars_csv = d / 'cars.csv'
        if not cars_csv.exists():
            # fallback → trouve n'importe quel fichier contenant 'car'
            alts = [p for p in d.iterdir()
                    if p.is_file() and p.suffix.lower() == '.csv' and 'car' in p.name.lower()]
            if alts:
                cars_csv = alts[0]

        if not cars_csv.exists():
            continue  # ignorer les dossiers corrompus

        # Extraction des temps
        try:
            cars = read_cars_csv(cars_csv)
            t_disappear = disappearance_time(
                cars['Time'].values, cars['X_pos'].values,
                ignore_first_seconds, hold_zeros
            )
            t_press = first_press_time(cars, press_source)
        except Exception:
            t_disappear, t_press = np.nan, np.nan

        # paramètres du trial
        if trial in inputs.index:
            v_kmh = float(inputs.loc[trial, 'velocity_kmh'])
            d_m   = float(inputs.loc[trial, 'disappear_m'])
            pos   = inputs.loc[trial, 'position']
            wthr  = inputs.loc[trial, 'weather']
        else:
            v_kmh, d_m, pos, wthr = np.nan, np.nan, np.nan, None

        # Temps théorique
        v_mps = (v_kmh / 3.6) if not math.isnan(v_kmh) else np.nan
        t_true = (d_m / v_mps) if (pd.notna(d_m) and pd.notna(v_mps) and v_mps > 0) else np.nan

        # Temps perçu
        if (t_press is None) or any(math.isnan(x) for x in [t_disappear, t_press]):
            t_perceived = np.nan
            err_s = np.nan
        else:
            t_perceived = float(t_press - t_disappear)
            err_s = float(t_perceived - t_true)

        # Correct ou non
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

    # Agrégations
    df_valid = df.dropna(subset=['err_s'])
    agg_vel = aggregate(df_valid, 'velocity_kmh') if not df_valid.empty else pd.DataFrame()
    agg_wth = aggregate(df_valid, 'weather')      if not df_valid.empty else pd.DataFrame()
    agg_dst = aggregate(df_valid, 'disappear_m')  if not df_valid.empty else pd.DataFrame()

    return inputs, df, agg_vel, agg_wth, agg_dst


# =====================================================================
# 4. Interface utilisateur Streamlit
# =====================================================================

st.set_page_config(page_title="Expérience 1 – Analyse", layout="wide")
st.title("Expérience 1 — Temps perçu vs réel (CARLA/UE)")

# Barre latérale
with st.sidebar:
    st.header("Paramètres")

    logs_dir = st.text_input("Dossier Logs (contient exp1.xlsx + 1 dossier par trial)", DEFAULT_LOGS)

    colA, colB = st.columns(2)
    tolerance = colA.number_input("Tolérance (s)", value=0.25, min_value=0.0, step=0.05)
    ignore_first = colB.number_input("Ignorer tête (s)", value=1.0, min_value=0.0, step=0.1)

    colC, colD = st.columns(2)
    hold_zeros = int(colC.number_input("Zéros consécutifs (hold)", value=3, min_value=1, step=1))
    press_source = colD.selectbox("Source appui", ["Time_estimated", "X_est"])

    st.caption("• Temps perçu = t(appui) − t(disparition véhicule)\n"
               "• Temps réel = distance / vitesse_m/s")

    ready = st.button("Analyser", use_container_width=True)

# Si l'utilisateur lance l'analyse
if ready:
    try:
        inputs, df, agg_vel, agg_wth, agg_dst = analyze_logs(
            logs_dir, tolerance, ignore_first, hold_zeros, press_source
        )
    except Exception as e:
        st.error(str(e))
    else:

        # Métriques globales
        kpi = metrics_table(df.dropna(subset=['err_s']))

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Essais valides", int(kpi['n'].iloc[0]) if not kpi.empty else 0)
        c2.metric("Biais (s)", f"{kpi['bias'].iloc[0]:.3f}" if not kpi.empty else "–")
        c3.metric("MAE (s)", f"{kpi['mae'].iloc[0]:.3f}" if not kpi.empty else "–")
        c4.metric("RMSE (s)", f"{kpi['rmse'].iloc[0]:.3f}" if not kpi.empty else "–")
        c5.metric("% Correct", f"{100*kpi['p_correct'].iloc[0]:.1f}%" if not kpi.empty else "–")

        # Filtres utilisateur
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

        # ======================================
        # Graphique : Perçu vs Réel
        # ======================================
        st.markdown("### Perçu vs Réel")

        valid_pairs = dff.dropna(subset=['t_true','t_perceived'])
        if not valid_pairs.empty:
            fig = px.scatter(
                valid_pairs, x='t_true', y='t_perceived',
                color='weather',
                hover_data=['trial','velocity_kmh','disappear_m']
            )

            lo = float(min(valid_pairs[['t_true','t_perceived']].min().min(), 0))
            hi = float(valid_pairs[['t_true','t_perceived']].max().max())

            # Ajout de la diagonale y=x
            fig.add_trace(go.Scatter(x=[lo,hi], y=[lo,hi], mode='lines', name='y=x'))

            fig.update_layout(
                legend_title="Météo",
                xaxis_title="Temps réel (s)",
                yaxis_title="Temps perçu (s)"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucune donnée valide pour ce filtre.")

        # ======================================
        # Histogramme des erreurs
        # ======================================
        colL, colR = st.columns(2)
        with colL:
            st.markdown("### Histogramme des erreurs (s)")
            e = dff['err_s'].dropna()
            if not e.empty:
                fig = px.histogram(
                    e, x='err_s',
                    nbins=min(40, max(10, int(np.sqrt(len(e))*3)))
                )
                fig.add_vline(x=0, line_dash='dash')
                fig.update_layout(
                    xaxis_title="Erreur (s)  (>0 = en retard, <0 = en avance)",
                    yaxis_title="Fréquence"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Pas d'erreurs à afficher.")

        # ======================================
        # Boxplots
        # ======================================
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

        # ======================================
        # Tableau final
        # ======================================
        st.markdown("### Tableau des essais")

        st.dataframe(
            dff[['trial','velocity_kmh','disappear_m','weather',
                 't_true','t_perceived','err_s','correct']]
            .round({'t_true':3, 't_perceived':3, 'err_s':3})
            .sort_values('trial'),
            use_container_width=True, height=360
        )
