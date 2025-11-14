# ===============================================================
# Expérience 2 – Analyse des logs CARLA/Unreal (Streamlit)
# ---------------------------------------------------------------
# Ce script analyse les données brutes générées lors de
# l’expérience 2 (« crossing decision experiment »).
#
# Objectifs :
#  - Calcul de l’EOCI (Estimated Opportunity to Cross Interval),
#    défini comme la distance de sécurité / vitesse.
#  - Reconstruction de la courbe Crossing(t) du participant.
#  - Fusion des données piéton / véhicule (peds.csv + cars.csv).
#  - Détection automatique des transitions Crossing 0→1 et 1→0.
#  - Génération de courbes Crossing vs Distance.
#  - Tableaux d’agrégation (par vitesse, météo, position).
#
# Entrées attendues :
#  • Dossier contenant :
#        - exp2*.xlsx  (plan du participant)
#        - un dossier par trial (1, 2, 3, …)
#              -> peds.csv
#              -> cars.csv
#
# Sorties :
#  • Interface Streamlit (tableaux + graphes interactifs).
#
# Remarque :
#  - L’expérience 2 ne comporte pas d'appui unique,
#    mais une pression continue reflétant l'intention de traverser.
# ===============================================================

import re
from pathlib import Path
from typing import List, Dict

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ===============================================================
# Paramètres par défaut
# ===============================================================

# Dossier Logs Unreal : contient le fichier Excel + les sous-dossiers numérotés
DEFAULT_LOGS = r"C:\Users\carlaue5.3\CarlaUE5\Unreal\CarlaUnreal\Logs"


# ===============================================================
# Fonctions utilitaires chargées de la lecture/normalisation
# ===============================================================

def _num_from_any(series: pd.Series) -> pd.Series:
    """
    Convertit n'importe quel champ texte en nombre :
    - "60" → 60.0
    - "60 km/h" → 60.0
    - "60,0" → 60.0
    Renvoie NaN si aucune partie chiffrée n'est trouvée.
    """
    s = series.astype(str).str.extract(r'([-+]?\d+[.,]?\d*)', expand=False)
    s = s.str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce')


def read_csv_semicolon_then_comma(p: Path) -> pd.DataFrame:
    """
    Lecture robuste des CSV :
    - Essaye d'abord avec séparateur ';'
    - Sinon ','
    """
    try:
        return pd.read_csv(p, sep=';')
    except Exception:
        return pd.read_csv(p)


def read_cars(p: Path) -> pd.DataFrame:
    """
    Lecture et normalisation des colonnes du fichier cars.csv.

    Colonnes attendues :
      - Time
      - X_cars
      - X_vel (sinon créée en NaN)

    Retourne un DataFrame propre contenant :
        ['Time', 'X_cars', 'X_vel']
    """
    df = read_csv_semicolon_then_comma(p)

    # Mapping automatique des noms de colonnes
    ren: Dict[str, str] = {}
    for c in df.columns:
        l = c.strip().lower()
        if l == 'time':
            ren[c] = 'Time'
        elif 'x_pos' in l or l == 'x':
            ren[c] = 'X_cars'
        elif 'x_vel' in l:
            ren[c] = 'X_vel'

    df = df.rename(columns=ren)

    # Vérification minimale
    for need in ['Time', 'X_cars']:
        if need not in df.columns:
            raise ValueError("{}: colonne manquante '{}'".format(p.name, need))

    # Si la vitesse n’est pas présente, on la remplit par NaN
    if 'X_vel' not in df.columns:
        df['X_vel'] = np.nan

    return df[['Time', 'X_cars', 'X_vel']]


def read_peds(p: Path) -> pd.DataFrame:
    """
    Lecture du fichier peds.csv et normalisation des colonnes :
      - Time
      - Crossing (peut contenir 0, 1 ou valeurs continues intermédiaires)
    """
    df = read_csv_semicolon_then_comma(p)

    ren: Dict[str, str] = {}
    for c in df.columns:
        l = c.strip().lower()
        if l == 'time':
            ren[c] = 'Time'
        elif 'cross' in l:
            ren[c] = 'Crossing'

    df = df.rename(columns=ren)

    if 'Time' not in df.columns or 'Crossing' not in df.columns:
        raise ValueError("{}: colonnes attendues 'Time' et 'Crossing'".format(p.name))

    return df[['Time', 'Crossing']]


def load_inputs_exp2(excel_path: Path) -> pd.DataFrame:
    """
    Lecture du plan expérimental exp2_*.xlsx :
    colonnes typiques :
      - trial
      - velocity_kmh
      - position
      - weather

    Conversion en numérique + index = numéro de trial.
    """
    df = pd.read_excel(excel_path)

    colmap: Dict[str, str] = {}
    for c in df.columns:
        l = c.strip().lower()
        if 'trial' in l:
            colmap[c] = 'trial'
        elif 'velocity' in l:
            colmap[c] = 'velocity_kmh'
        elif 'position' in l:
            colmap[c] = 'position'
        elif 'weather' in l:
            colmap[c] = 'weather'

    df = df.rename(columns=colmap)

    # Si pas de colonne trial, on en génère une
    if 'trial' not in df.columns:
        df['trial'] = np.arange(1, len(df) + 1)

    keep = ['trial', 'velocity_kmh', 'position', 'weather']
    for k in keep:
        if k not in df.columns:
            df[k] = np.nan

    df = df[keep]

    df['velocity_kmh'] = _num_from_any(df['velocity_kmh'])
    df['position'] = pd.to_numeric(df['position'], errors='coerce')

    return df.set_index('trial').sort_index()


# ===============================================================
# Logique principale de l’expérience 2
# ===============================================================

def make_crossing_binary(peds: pd.DataFrame) -> pd.Series:
    """
    Nettoie le signal Crossing fourni par UE5 :
      - La première transition Crossing==1 transforme
        toutes les valeurs précédentes en 1 (termes de continuité).
      - Toutes les autres valeurs sont arrondies (si entre 0 et 1).
      - Le signal final est binaire {0,1}.
    """
    p = peds.copy()

    # Détecter première occurrence de 1
    idx1 = p.index[p['Crossing'] == 1]
    if len(idx1) > 0:
        first_one = idx1[0]
        p.loc[:first_one - 1, 'Crossing'] = 1

    # Round explicite (et clip dans [0,1])
    def _round_keep01(x):
        if x in (0, 1):
            return x
        return float(round(x))

    p['Crossing'] = p['Crossing'].apply(_round_keep01).clip(0, 1)
    return p['Crossing']


def compute_trial_exp2(cars_csv: Path, peds_csv: Path, pos_index: int, pos_map: List[float]) -> Dict[str, object]:
    """
    Calcule les séries fusionnées Time/X_cars/Crossing et la distance de sécurité.

    Étapes :
      1. Lecture peds.csv + cars.csv
      2. Jointure interne par Time
      3. Filtrage des échantillons où la voiture est visible (X_cars != 0)
      4. Construction du gap = (X_cars - X_pieton) / 100
      5. Détection de la transition crossing 1 → 0 (fin de l’intention)
      6. Distance de sécurité = |gap| à la première transition 1→0
    """
    cars = read_cars(cars_csv)
    peds = read_peds(peds_csv)

    # Fusion sur la colonne Time
    df = peds.merge(cars, on='Time', how='inner').dropna()

    # On ne garde que la période où la voiture existe (X ≠ 0)
    df = df[df['X_cars'] != 0].reset_index(drop=True)
    if df.empty:
        return dict(ok=False)

    # Transforme Crossing en signal binaire propre
    df['Crossing'] = make_crossing_binary(df)

    # Position réelle du piéton en cm dans la map CARLA
    ped_x = float(pos_map[int(pos_index)])

    # Écart voiture-piéton en mètres
    df['gap_m'] = (df['X_cars'] - ped_x) / 100.0

    # Détection de la première transition 1 → 0
    start_idx, stop_idx = None, None
    for i in range(len(df) - 1):
        c0, c1 = df.loc[i, 'Crossing'], df.loc[i + 1, 'Crossing']

        # La première montée 0→1 marque un "début potentiel"
        if start_idx is None and (c0 == 0 and c1 == 1):
            start_idx = i
            continue

        # Puis la première descente 1→0 définit la fin
        if start_idx is not None and (c0 == 1 and c1 == 0):
            stop_idx = i
            break

    # Distance de sécurité = valeur absolue du gap au moment de la descente
    safety_distance_m = np.nan
    if stop_idx is not None:
        safety_distance_m = float(abs(df.loc[stop_idx + 1, 'gap_m']))

    return dict(
        ok=True,
        safety_distance_m=safety_distance_m,
        series_time=df['Time'].to_numpy(),
        series_gap=df['gap_m'].to_numpy(),
        series_cross=df['Crossing'].to_numpy(),
    )


# ===============================================================
# Analyse d'un dossier Logs complet (dossier racine)
# ===============================================================

@st.cache_data(show_spinner=False)
def analyze_folder(logs_dir: str, pos1_value: float):
    """
    Cherche automatiquement :
      - exp2*.xlsx pour le plan du participant
      - les sous-dossiers numérotés (1,2,3…)
      - peds.csv + cars.csv pour chaque trial

    Calcule pour chaque essai :
      • la distance de sécurité
      • les séries fusionnées (Gap, Crossing, Time)
    """
    root = Path(logs_dir)

    # Recherche du fichier Excel pour Exp2
    excel = None
    for f in root.iterdir():
        if f.suffix.lower() == '.xlsx' and 'exp2' in f.name.lower():
            excel = f
            break
    if excel is None:
        raise FileNotFoundError("Excel 'exp2*.xlsx' introuvable dans ce dossier.")

    inputs = load_inputs_exp2(excel)

    # Mapping des positions X du piéton (spécifiques à ta map UE5)
    pos_map: List[float] = [14343.0, pos1_value, 13317.0]

    rows: List[Dict[str, object]] = []
    trials = [d for d in root.iterdir() if d.is_dir() and re.fullmatch(r'\d+', d.name)]
    trials.sort(key=lambda p: int(p.name))

    for d in trials:
        tri = int(d.name)

        # Recherche cars.csv (nom flexible)
        cars_csv = d / 'cars.csv'
        if not cars_csv.exists():
            alts = [p for p in d.iterdir()
                    if p.is_file() and p.suffix.lower() == '.csv' and 'car' in p.name.lower()]
            if alts:
                cars_csv = alts[0]

        # Recherche peds.csv (nom flexible)
        peds_csv = d / 'peds.csv'
        if not peds_csv.exists():
            alts = [p for p in d.iterdir()
                    if p.is_file() and p.suffix.lower() == '.csv' and 'ped' in p.name.lower()]
            if alts:
                peds_csv = alts[0]

        if not cars_csv.exists() or not peds_csv.exists():
            continue

        # Charge les paramètres du plan expérimental
        if tri in inputs.index:
            v_kmh = float(inputs.loc[tri, 'velocity_kmh'])
            pos = int(inputs.loc[tri, 'position']) if not pd.isna(inputs.loc[tri, 'position']) else 0
            wthr = inputs.loc[tri, 'weather']
        else:
            v_kmh, pos, wthr = np.nan, 0, None

        # Calcul du résultat pour ce trial
        res = compute_trial_exp2(cars_csv, peds_csv, pos, pos_map)
        if not res.get('ok', False):
            continue

        rows.append({
            'trial': tri,
            'velocity_kmh': v_kmh,
            'position': pos,
            'weather': wthr,
            'safety_distance_m': res['safety_distance_m'],
            'series_time': res['series_time'],
            'series_gap': res['series_gap'],
            'series_cross': res['series_cross'],
        })

    df = pd.DataFrame(rows).sort_values('trial').reset_index(drop=True)
    return inputs, df


# ===============================================================
# Fonction pour empiler les séries en vue des tracés longues courbes
# ===============================================================

def stack_samples_from_trials(dff: pd.DataFrame) -> pd.DataFrame:
    """
    Construit un seul tableau "long" regroupant l’ensemble des séries
    de chaque essai filtré.
    
    Colonnes finales :
      - gap_m
      - crossing
      - velocity_kmh
      - weather
      - position
      - trial
    """
    rows = []
    for _, row in dff.iterrows():
        gap = np.asarray(row['series_gap'], dtype=float)
        cr = np.asarray(row['series_cross'], dtype=float)

        if gap.size == 0 or cr.size == 0:
            continue

        n = min(gap.size, cr.size)

        df_s = pd.DataFrame({
            'gap_m': gap[:n],
            'crossing': cr[:n],
            'velocity_kmh': row['velocity_kmh'],
            'weather': str(row['weather']),
            'position': row['position'],
            'trial': row['trial'],
        })

        df_s = df_s[np.isfinite(df_s['gap_m']) & np.isfinite(df_s['crossing'])]
        rows.append(df_s)

    if not rows:
        return pd.DataFrame(columns=['gap_m', 'crossing', 'velocity_kmh',
                                     'weather', 'position', 'trial'])
    return pd.concat(rows, ignore_index=True)


# ===============================================================
# Interface Streamlit : page principale
# ===============================================================

st.set_page_config(page_title="Expérience 2 – EOCI & Crossing/Distance", layout="wide")
st.title("Expérience 2 — EOCI (temps avant impact) & courbes Crossing vs Distance")


# ===============================================================
# Barre latérale : paramètres utilisateur
# ===============================================================
with st.sidebar:
    st.header("Paramètres")
    logs_dir = st.text_input("Dossier Logs (exp2.xlsx + dossiers 1..N)", DEFAULT_LOGS)

    st.caption("Position 1 : certains participants ont 2665, d’autres 3665.")
    pos1_value = st.selectbox("X du piéton pour Position 1", options=[2665.0, 3665.0], index=0)

    run = st.button("Analyser", use_container_width=True)


# ===============================================================
# Lancement de l’analyse
# ===============================================================
if run:
    try:
        inputs, df = analyze_folder(logs_dir, pos1_value)
    except Exception as e:
        st.error(str(e))
    else:

        # -------------------------------
        # Filtres utilisateur
        # -------------------------------
        st.subheader("Filtres")

        c1, c2, c3 = st.columns(3)

        velC = sorted([v for v in df['velocity_kmh'].dropna().unique().tolist()])
        posC = sorted([int(p) for p in df['position'].dropna().unique().tolist()])
        wthC = sorted([str(w) for w in df['weather'].dropna().astype(str).unique().tolist()])

        sel_vel = c1.multiselect("Vitesses (km/h)", velC, default=velC)
        sel_pos = c2.multiselect("Positions (-pos)", posC, default=posC)
        sel_wth = c3.multiselect("Météo", wthC, default=wthC)

        dff = df.copy()
        dff['weather'] = dff['weather'].astype(str)
        dff = dff[
            dff['velocity_kmh'].isin(sel_vel)
            & dff['position'].isin(sel_pos)
            & dff['weather'].isin(sel_wth)
        ]

        # ===============================================================
        # 1) Calcul de l’EOCI (temps avant impact)
        # ===============================================================

        # Vitesse réelle (m/s)
        dff['speed_mps'] = dff['velocity_kmh'] / 3.6

        # EOCI = distance de sécurité / vitesse
        dff['eoci_s'] = np.where(
            (dff['safety_distance_m'].notna()) & (dff['speed_mps'] > 0),
            dff['safety_distance_m'] / dff['speed_mps'],
            np.nan
        )

        # -------------------------------
        # Agrégats EOCI
        # -------------------------------
        st.header("EOCI (s) — agrégats")

        s = dff.dropna(subset=['eoci_s'])

        if s.empty:
            st.info("Aucun EOCI calculable avec ces filtres (vitesse nulle ou safety distance manquante).")
        else:
            a1, a2 = st.columns(2)

            # Agrégats météo
            with a1:
                st.markdown("### Moyenne par **météo**")
                agg_w = (s.groupby('weather')['eoci_s']
                         .agg(['mean', 'std', 'count'])
                         .reset_index()
                         .rename(columns={'mean': 'mean_s', 'std': 'std_s', 'count': 'n'}))
                st.dataframe(agg_w.round(3), use_container_width=True, height=240)
                fig = px.bar(agg_w, x='weather', y='mean_s', error_y='std_s', text='n',
                             labels={'weather': 'Météo', 'mean_s': 'EOCI (s)'})
                st.plotly_chart(fig, use_container_width=True)

            # Agrégats vitesse
            with a2:
                st.markdown("### Moyenne par **vitesse**")
                agg_v = (s.groupby('velocity_kmh')['eoci_s']
                         .agg(['mean', 'std', 'count'])
                         .reset_index()
                         .rename(columns={'mean': 'mean_s', 'std': 'std_s', 'count': 'n'}))
                st.dataframe(agg_v.round(3), use_container_width=True, height=240)
                fig = px.bar(agg_v, x='velocity_kmh', y='mean_s', error_y='std_s', text='n',
                             labels={'velocity_kmh': 'Vitesse (km/h)', 'mean_s': 'EOCI (s)'})
                st.plotly_chart(fig, use_container_width=True)

            # Heatmap vitesse × météo
            st.markdown("### Heatmap — EOCI moyen : **météo × vitesse**")
            piv = (s.groupby(['weather', 'velocity_kmh'])['eoci_s']
                   .mean()
                   .reset_index()
                   .pivot(index='weather', columns='velocity_kmh', values='eoci_s'))
            fig_h = px.imshow(piv, text_auto=".2f", aspect='auto', color_continuous_scale='Viridis')
            fig_h.update_layout(xaxis_title="Vitesse (km/h)",
                                yaxis_title="Météo",
                                coloraxis_colorbar_title="s")
            st.plotly_chart(fig_h, use_container_width=True)

        # ===============================================================
        # 2) Courbes Crossing vs Distance
        # ===============================================================

        st.header("Courbes Crossing (0/1) vs Distance — par position")

        samples_all = stack_samples_from_trials(dff)

        if samples_all.empty:
            st.info("Aucun échantillon pour tracer les courbes.")
        else:
            pos_presentes = sorted(samples_all['position'].dropna().unique().astype(int).tolist())

            if not pos_presentes:
                st.info("Aucune position trouvée dans les données filtrées.")
            else:
                tabs = st.tabs([f"Position {p}" for p in pos_presentes])

                for tab, p in zip(tabs, pos_presentes):
                    with tab:
                        st.markdown(f"#### Position {p} — couleurs par **météo**")

                        sp = samples_all[samples_all['position'] == p].copy()
                        if sp.empty:
                            st.info("Pas de données pour cette position.")
                            continue

                        sp = sp.sort_values(['trial', 'gap_m'])

                        fig1 = px.line(
                            sp, x='gap_m', y='crossing',
                            color='weather', line_group='trial',
                            hover_data=['trial', 'velocity_kmh', 'weather']
                        )
                        fig1.update_layout(
                            xaxis_title="Distance (m)",
                            yaxis_title="Crossing (0/1)",
                            yaxis=dict(range=[-0.05, 1.05])
                        )
                        st.plotly_chart(fig1, use_container_width=True)

                        st.markdown(f"#### Position {p} — couleurs par **vitesse**")

                        sp['vel_cat'] = sp['velocity_kmh'].round().astype('Int64').astype(str) + " km/h"

                        fig2 = px.line(
                            sp, x='gap_m', y='crossing',
                            color='vel_cat', line_group='trial',
                            hover_data=['trial', 'velocity_kmh', 'weather']
                        )
                        fig2.update_layout(
                            xaxis_title="Distance (m)",
                            yaxis_title="Crossing (0/1)",
                            yaxis=dict(range=[-0.05, 1.05])
                        )
                        st.plotly_chart(fig2, use_container_width=True)

        # ===============================================================
        # 3) Tableau des essais
        # ===============================================================
        st.markdown("### Tableau des essais (EOCI inclus)")

        show = dff[['trial', 'position', 'weather', 'velocity_kmh',
                    'safety_distance_m', 'eoci_s']].round(3)

        st.dataframe(show.sort_values('trial'),
                     use_container_width=True, height=340)

else:
    st.info("Renseigne le dossier et clique **Analyser**.")
