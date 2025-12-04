"""
annotate_crossing.py
--------------------

Objectif
--------
Ce script annote les fichiers CSV du dataset BPI pour produire, pour chaque
frame valide, un fichier contenant :

    [true_label, predicted_label, weather, ped_height_cm,
     vehicle_speed_kmh, distance_m, adj]

Cette version est volontairement *minimale* comparée à
`annotate_crossing_intention.py` :

- Le **ground-truth** est défini uniquement comme :
        true_label = (LiDAR valide) ET (012_lidar_pc_lat > 0)
  c’est-à-dire : "le piéton est sur la route".

- PAS d’orientation, PAS d’intention.
- On écrit uniquement les frames où :
        LiDAR valide + distance définie + vitesse définie.

Entrées :
---------
- INPUT_DIR : CSV générés après extraction (extracted_csvfiles/).

Sorties :
---------
Deux versions annotées :
- OUTPUT_DIR_FALSE : prédictions du modèle sans ajustement (adj=False)
- OUTPUT_DIR_TRUE  : prédictions ajustées (adj=True)

Chaque sortie = `<fichier>_annot.csv`.

Remarque
--------
Ce script est utile pour tester rapidement le modèle sur BPI sans
inclure l’intention ou l’orientation.
"""

# ======================================================================
# IMPORTS
# ======================================================================
import os, glob, importlib.util, functools, re
import numpy as np
import pandas as pd

# ======================================================================
# CONFIG — Répertoires & paramètres
# ======================================================================

INPUT_DIR        = r"C:\Users\svictor\Documents\BPI_Dataset\extracted_csvfiles"

# Sorties "modèle non ajusté" / "modèle ajusté"
OUTPUT_DIR_FALSE = r"C:\Users\svictor\Documents\BPI_Dataset\extracted_csvfiles_annotated_adj_false"
OUTPUT_DIR_TRUE  = r"C:\Users\svictor\Documents\BPI_Dataset\extracted_csvfiles_annotated_adj_true"

# Trois sessions filmées BPI (nécessaire pour estimer la taille via LiDAR)
SESSIONS = [
    r"raw_data\data_2018-01-28-14-57-55",
    r"raw_data\data_2018-01-28-14-58-46",
    r"raw_data\data_2018-01-28-15-00-12",
]

WEATHER_DEFAULT = "clear"          # pas d’annotation météo dans BPI → valeur fixe
CHINA_DEFAULT_HEIGHT_CM = 169.6    # fallback si estimation LiDAR impossible
MIN_HEIGHT_COUNT        = 5        # nombre minimal de mesures LiDAR valides

# ======================================================================
# TQDM — barre de progression
# ======================================================================
try:
    from tqdm import tqdm
    def tqdm_write(msg):
        try: tqdm.write(msg)
        except Exception: print(msg)
except Exception:
    def tqdm(x, **k): return x
    def tqdm_write(msg): print(msg)

# ======================================================================
# ESTIMATION DE LA TAILLE DU PIÉTON
# ======================================================================
from ped_height import estimate_ped_height_cm_for_df

# ======================================================================
# CHARGEMENT DU MODÈLE DE DÉCISION (CNRS)
# ======================================================================

MODEL_PATH = r"E:\crossing-model\main_experiment\model_datas\CNRS_behavior_model.py"

spec = importlib.util.spec_from_file_location("pedestrian_behavior_model", MODEL_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Impossible de charger le modèle: {MODEL_PATH}")

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if not hasattr(module, "pedestrian_behavior_model") or not callable(module.pedestrian_behavior_model):
    raise RuntimeError(f"Le module ne fournit pas la fonction 'pedestrian_behavior_model' ({MODEL_PATH})")

# ======================================================================
# FONCTIONS UTILITAIRES
# ======================================================================

def find_col(df: pd.DataFrame, suffix: str) -> str:
    """
    Recherche robuste d’une colonne par suffixe :
    - si match exact → prioritaire
    - sinon, suffixe équivalent (ex : 000_lidar_pv_lon → lidar_pv_lon)
    - s’il y a plusieurs matches, on prend celui avec le plus petit préfixe numérique.
    """
    if suffix in df.columns:
        return suffix

    hits = [c for c in df.columns if str(c).endswith(suffix)]
    if not hits:
        raise KeyError(f"Colonne se terminant par '{suffix}' introuvable.")

    if len(hits) > 1:
        def prefnum(col):
            m = re.match(r"^(\d+)_", str(col))
            return int(m.group(1)) if m else 10**9
        hits.sort(key=prefnum)

    return hits[0]


def pick_time_col(df: pd.DataFrame) -> str:
    """
    Sélection automatique d’une colonne temporelle cohérente.
    On ignore image_rel_time (pas synchronisable avec LiDAR).
    """
    priorities = [
        "001_rel_time", "rel_time",
        "lidar_rel_time", "can_rel_time", "imu_rel_time"
    ]

    for name in priorities:
        cands = [c for c in df.columns if c.endswith(name) and "image_rel_time" not in c]
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1 and name == "rel_time":
            def prefnum(col):
                m = re.match(r"^(\d+)_", str(col))
                return int(m.group(1)) if m else 10**9
            return sorted(cands, key=prefnum)[0]

    # fallback
    rels = [c for c in df.columns if c.endswith("rel_time") and "image_rel_time" not in c]
    if rels:
        def prefnum(col):
            m = re.match(r"^(\d+)_", str(col))
            return int(m.group(1)) if m else 10**9
        return sorted(rels, key=prefnum)[0]

    df["_idx"] = np.arange(len(df))
    return "_idx"


def frame_glob_patterns(root, frame_id):
    """Construit les patterns possibles pour les fichiers LiDAR correspondant à un frame."""
    fid = int(frame_id)
    stems = [f"{fid:06d}", f"{fid:05d}", str(fid)]
    pats = []
    for s in stems:
        pats += [
            os.path.join(root, "sync_pcl1", f"*{s}*.pcd"),
            os.path.join(root, "sync_pcl1", f"*{s}*.ply"),
            os.path.join(root, "sync_pcl1", f"*{s}*.bin"),
            os.path.join(root, "sync_pcl1_mat", f"*{s}*.mat"),
        ]
    return pats


@functools.lru_cache(maxsize=4096)
def exists_any_cached(patterns_tuple):
    """Mémoïsation pour accélérer les recherches de fichiers LiDAR."""
    for p in patterns_tuple:
        if glob.glob(p):
            return True
    return False


def guess_session_for_csv(df, sessions, sample_n=40):
    """
    Devine automatiquement à quelle session raw_data correspond un CSV,
    en vérifiant si ses frames existent dans les différents dossiers LiDAR.
    """
    try:
        fr_col = find_col(df, "lidar_frame")
    except:
        return sessions[0]

    frames = pd.to_numeric(df[fr_col], errors="coerce").dropna().astype(int).tolist()
    if not frames:
        return sessions[0]

    sample = frames[:min(sample_n, len(frames))]
    best = (-1, sessions[0])

    for root in sessions:
        hits = 0
        for f in sample:
            if exists_any_cached(tuple(frame_glob_patterns(root, f))):
                hits += 1
        if hits > best[0]:
            best = (hits, root)

    return best[1]

# ======================================================================
# ANNOTATION PRINCIPALE (SANS INTENTION)
# ======================================================================

def annotate_file(path, output_dir_false, output_dir_true):
    """
    Annote un CSV BPI :
    - estime la taille du piéton,
    - définit le ground-truth "sur la route",
    - applique le modèle CNRS en mode adj=True/False,
    - écrit deux fichiers `_annot.csv`.
    """
    base_name = os.path.basename(path)
    if base_name.lower().startswith("explain"):
        return None  # fichiers internes ignorés

    df = pd.read_csv(path, low_memory=False)
    if df.empty:
        raise ValueError("CSV vide (0 lignes).")

    # ---- Détection des colonnes clés ----
    time_col        = pick_time_col(df)
    lidar_valid_col = find_col(df, "lidar_is_valid")
    pv_lon_col      = find_col(df, "lidar_pv_lon")       # distance au véhicule
    pc_lat_col      = find_col(df, "lidar_pc_lat")       # latéral → sur route ?
    speed_col       = find_col(df, "can_VehicleSpeed")   # vitesse du véhicule

    # Tri temporel
    df = df.sort_values(by=[time_col]).reset_index(drop=True)

    # ---- Estimation de la taille ----
    session_root = guess_session_for_csv(df, SESSIONS)
    h_cm_all, _ = estimate_ped_height_cm_for_df(df, pcl_root=session_root, f_px=None)

    h_raw = pd.to_numeric(h_cm_all, errors="coerce").astype(float)
    mask = np.isfinite(h_raw) & (150 <= h_raw) & (h_raw <= 200)

    ped_h_const = (
        round(float(np.nanmean(h_raw[mask])), 1)
        if mask.sum() >= MIN_HEIGHT_COUNT
        else CHINA_DEFAULT_HEIGHT_CM
    )

    # ---- Extraction des séries utiles ----
    lidar_valid = (pd.to_numeric(df[lidar_valid_col], errors="coerce") == 1)
    distance_m  = pd.to_numeric(df[pv_lon_col], errors="coerce").astype(float)
    speed_kmh   = pd.to_numeric(df[speed_col], errors="coerce").astype(float)
    pc_lat      = pd.to_numeric(df[pc_lat_col], errors="coerce").astype(float)

    # ---- Ground-truth (simplifié) ----
    # Sur la route <=> pc_lat > 0 & LiDAR valide
    true_label_s = ((pc_lat > 0) & lidar_valid).astype(bool)

    # ---- Filtre strict pour écrire ----
    keep = lidar_valid & np.isfinite(distance_m) & np.isfinite(speed_kmh)
    if not keep.any():
        tqdm_write(f"[SKIP] {base_name} : aucune frame exploitable")
        return None

    # ==================================================================
    # PREDICT (adj=False et adj=True)
    # ==================================================================
    for adj_value, out_dir in [(False, output_dir_false), (True, output_dir_true)]:
        os.makedirs(out_dir, exist_ok=True)

        d_vals = distance_m[keep].to_numpy()
        v_vals = speed_kmh[keep].to_numpy()
        t_vals = true_label_s[keep].to_numpy()

        preds = []
        for d_m, v_kmh in zip(d_vals, v_vals):
            try:
                y = module.pedestrian_behavior_model(
                    WEATHER_DEFAULT,
                    float(ped_h_const),
                    float(v_kmh),
                    float(d_m),
                    adj_value
                )
                preds.append(bool(y))
            except Exception:
                preds.append(False)

        # ---- DataFrame sortie ----
        out = pd.DataFrame({
            "true_label":        t_vals.astype(bool),
            "predicted_label":   np.asarray(preds, dtype=bool),
            "weather":           WEATHER_DEFAULT,
            "ped_height_cm":     float(ped_h_const),
            "vehicle_speed_kmh": v_vals,
            "distance_m":        d_vals,
            "adj":               bool(adj_value),
        })

        if out.empty:
            tqdm_write(f"[SKIP] {base_name} ({'adj=True' if adj_value else 'adj=False'}) : aucune ligne")
            continue

        base_noext = os.path.splitext(base_name)[0]
        out_path = os.path.join(out_dir, f"{base_noext}_annot.csv")
        out.to_csv(out_path, index=False, encoding="utf-8")

    return base_name

# ======================================================================
# MAIN
# ======================================================================
if __name__ == "__main__":
    files = [
        p for p in glob.glob(os.path.join(INPUT_DIR, "*.csv"))
        if "explain" not in os.path.basename(p).lower()
    ]

    if not files:
        print(f"Aucun CSV dans {INPUT_DIR}")
        raise SystemExit

    for f in tqdm(files, desc="Annotating + Predicting"):
        try:
            res = annotate_file(f, OUTPUT_DIR_FALSE, OUTPUT_DIR_TRUE)
            if res:
                tqdm_write(f"[OK] {res} -> {os.path.basename(OUTPUT_DIR_FALSE)}, {os.path.basename(OUTPUT_DIR_TRUE)}")
        except Exception as e:
            tqdm_write(f"[WARN] {os.path.basename(f)} : {e}")
