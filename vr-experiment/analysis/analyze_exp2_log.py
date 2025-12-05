# ===============================================================
# Expérience 2 – Analyse des logs CARLA/Unreal (Streamlit)
# ----------------------------------------------------------------
# Analyse du "Crossing Decision Experiment".
#
# Dans cette expérience, le participant indique en continu s’il
# estime pouvoir traverser devant la voiture (trigger gauche).
#
# Le script reconstruit :
#   - le signal Crossing (normalisé en {0,1})
#   - la distance véhicule–piéton (gap)
#   - la distance de sécurité : |gap| au moment de la transition 1→0
#
# L’Expérience 2 ne contient aucune estimation de type TTC ou EOCI.
# Elle mesure un comportement binaire et dynamique, et non une
# estimation temporelle.
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
# Paramètre global : chemin du dossier Logs produit par Unreal
# ===============================================================

DEFAULT_LOGS = r"C:\Users\carlaue5.3\CarlaUE5\Unreal\CarlaUnreal\Logs"


# ===============================================================
# Utilitaires de parsing et normalisation
# ===============================================================

def _num_from_any(series: pd.Series) -> pd.Series:
    """
    Convertit des chaînes arbitraires en valeurs numériques.
    Accepte notamment : "60", "60 km/h", "60,0".
    Renvoie NaN si aucune composante numérique n'est trouvée.
    """
    s = series.astype(str).str.extract(r'([-+]?\d+[.,]?\d*)', expand=False)
    s = s.str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce')


def read_csv_semicolon_then_comma(p: Path) -> pd.DataFrame:
    """
    Charger un CSV en tolérant les différences de séparateur.
    Tentative 1 : ';'
    Tentative 2 : ','
    """
    try:
        return pd.read_csv(p, sep=';')
    except Exception:
        return pd.read_csv(p)


def read_cars(p: Path) -> pd.DataFrame:
    """
    Lecture robuste de cars.csv.
    Ce fichier contient la trajectoire de la voiture :
      - Time      : timestamp Unreal Engine
      - X_cars    : position longitudinale du véhicule
      - X_vel     : vitesse (optionnelle selon version)
    """
    df = read_csv_semicolon_then_comma(p)

    # Normalisation des colonnes
    ren = {}
    for c in df.columns:
        l = c.strip().lower()
        if l == 'time':
            ren[c] = 'Time'
        elif 'x_pos' in l or l == 'x':
            ren[c] = 'X_cars'
        elif 'x_vel' in l:
            ren[c] = 'X_vel'

    df = df.rename(columns=ren)

    # Colonnes minimales
    for need in ['Time', 'X_cars']:
        if need not in df.columns:
            raise ValueError(f"{p.name}: colonne manquante {need}")

    # X_vel peut être absent selon le blueprint → NaN
    if 'X_vel' not in df.columns:
        df['X_vel'] = np.nan

    return df[['Time', 'X_cars', 'X_vel']]


def read_peds(p: Path) -> pd.DataFrame:
    """
    Lecture de peds.csv contenant le signal Crossing.
      - Time
      - Crossing : valeurs {0,1} ou valeurs intermédiaires en flottant
    """
    df = read_csv_semicolon_then_comma(p)

    ren = {}
    for c in df.columns:
        l = c.strip().lower()
        if l == 'time':
            ren[c] = 'Time'
        elif 'cross' in l:
            ren[c] = 'Crossing'

    df = df.rename(columns=ren)

    if 'Time' not in df.columns or 'Crossing' not in df.columns:
        raise ValueError(f"{p.name}: colonnes 'Time' et 'Crossing' manquantes")

    return df[['Time', 'Crossing']]


def load_inputs_exp2(excel_path: Path) -> pd.DataFrame:
    """
    Lecture du plan d'expérience exp2_<participant>.xlsx.
    Le fichier doit contenir :
      - trial
      - velocity_kmh
      - position
      - weather
    Retour : DataFrame indexé par le numéro de trial.
    """
    df = pd.read_excel(excel_path)

    colmap = {}
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

    # Génération automatique du numéro de trial si absent
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
# Traitement d'un trial : reconstruction Crossing/Gap
# ===============================================================

def make_crossing_binary(peds: pd.DataFrame) -> pd.Series:
    """
    Normalisation du signal Crossing :
      - UE peut enregistrer des valeurs intermédiaires (0 < x < 1)
      - La première transition vers 1 est rcontinue
      - Le signal final est strictement binaire {0,1}
    """
    p = peds.copy()

    idx1 = p.index[p['Crossing'] == 1]
    if len(idx1) > 0:
        first_one = idx1[0]
        p.loc[:first_one - 1, 'Crossing'] = 1

    def _round_keep01(x):
        if x in (0, 1):
            return x
        return float(round(x))

    p['Crossing'] = p['Crossing'].apply(_round_keep01).clip(0, 1)
    return p['Crossing']


def compute_trial_exp2(cars_csv: Path, peds_csv: Path, pos_index: int, pos_map: List[float]) -> Dict[str, object]:
    """
    Analyse complète d’un essai :
      1. Lecture des fichiers peds.csv et cars.csv
      2. Fusion temporelle (inner join sur Time)
      3. Filtrage des frames où la voiture existe (X_cars != 0)
      4. Calcul du gap véhicule–piéton en mètres
      5. Détection de la transition Crossing 1→0
      6. Distance de sécurité : |gap| à la transition

    La distance de sécurité est le seul indicateur pertinent pour l’Expérience 2.
    Aucune estimation temporelle n'est calculée.
    """
    cars = read_cars(cars_csv)
    peds = read_peds(peds_csv)

    df = peds.merge(cars, on='Time', how='inner').dropna()

    df = df[df['X_cars'] != 0].reset_index(drop=True)
    if df.empty:
        return dict(ok=False)

    df['Crossing'] = make_crossing_binary(df)

    ped_x = float(pos_map[int(pos_index)])
    df['gap_m'] = (df['X_cars'] - ped_x) / 100.0

    start_idx, stop_idx = None, None
    for i in range(len(df) - 1):
        c0, c1 = df.loc[i, 'Crossing'], df.loc[i + 1, 'Crossing']
        if start_idx is None and (c0 == 0 and c1 == 1):
            start_idx = i
            continue
        if start_idx is not None and (c0 == 1 and c1 == 0):
            stop_idx = i
            break

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
# Analyse d'un dossier Logs complet (avec exp2.xlsx)
# ===============================================================

@st.cache_data(show_spinner=False)
def analyze_folder(logs_dir: str, pos1_value: float):
    """
    Analyse de l’ensemble du dossier Logs :
      - Localisation du fichier exp2*.xlsx
      - Découverte des dossiers numérotés
      - Extraction de la distance de sécurité pour chaque trial

    Retour :
      - DataFrame du plan expérimental
      - DataFrame des résultats par trial
    """
    root = Path(logs_dir)

    excel = None
    for f in root.iterdir():
        if f.suffix.lower() == '.xlsx' and 'exp2' in f.name.lower():
            excel = f
            break
    if excel is None:
        raise FileNotFoundError("Excel 'exp2*.xlsx' introuvable dans ce dossier.")

    inputs = load_inputs_exp2(excel)

    pos_map = [14343.0, pos1_value, 13317.0]  # coordonnées spécifiques à la carte Unreal

    rows = []
    trials = [d for d in root.iterdir() if d.is_dir() and re.fullmatch(r'\d+', d.name)]
    trials.sort(key=lambda p: int(p.name))

    for d in trials:
        tri = int(d.name)

        cars_csv = next((p for p in d.iterdir() if p.is_file() and 'car' in p.name.lower()), d / 'cars.csv')
        peds_csv = next((p for p in d.iterdir() if p.is_file() and 'ped' in p.name.lower()), d / 'peds.csv')

        if not cars_csv.exists() or not peds_csv.exists():
            continue

        if tri in inputs.index:
            v_kmh = float(inputs.loc[tri, 'velocity_kmh'])
            pos = int(inputs.loc[tri, 'position']) if not pd.isna(inputs.loc[tri, 'position']) else 0
            wthr = inputs.loc[tri, 'weather']
        else:
            v_kmh, pos, wthr = np.nan, 0, None

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
