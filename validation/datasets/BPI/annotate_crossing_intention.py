"""
annotate_crossing_intention.py
------------------------------

Objectif
--------
Ce script annote dynamiquement les frames du dataset BPI afin de produire,
pour chaque CSV de trajectoire, un fichier contenant :

    [true_label, predicted_label, weather, ped_height_cm,
     vehicle_speed_kmh, distance_m, adj]

Il applique :
- une estimation automatique de la taille du piéton (via LiDAR),
- une heuristique "orientation → vers la route" basée sur les angles,
- une définition du ground-truth frame-wise,
- l'appel au modèle CNRS (avec/without ajustement : adj=True/False),
- l’enregistrement de deux versions annotées : ajustée et non-ajustée.

Hypothèses fortes du script
---------------------------
- 111_img_orientation est en DEGRÉS (0..360).
- Un piéton "regarde vers la route" si son angle est dans ORI_TOWARD_DEG_WINDOWS.
- Un piéton est "sur la route" si 012_lidar_pc_lat > 0.
- La distance envoyée au modèle = 014_lidar_pv_lon (mètres, brut).
- On n’écrit QUE les frames pour lesquelles :
    LiDAR valide + distance finie + vitesse finie + orientation vers la route.

Entrées :
---------
- INPUT_DIR : CSV bruts BPI après extraction.
- ped_height.py : estimation de la taille du piéton
- CNRS_behavior_model.py : modèle de décision piéton

Sorties :
---------
Deux versions annotées :
- OUTPUT_DIR_FALSE : prédictions sans ajustement du modèle (adj=False)
- OUTPUT_DIR_TRUE  : prédictions avec ajustement de biais (adj=True)

Chaque fichier de sortie : `<base>_annot.csv`
"""

# ======================================================================
# IMPORTS
# ======================================================================
import os, glob, importlib.util, functools, re
import numpy as np
import pandas as pd

# ======================================================================
# CONFIG — Répertoires et paramètres du dataset BPI
# ======================================================================

INPUT_DIR        = r"C:\Users\svictor\Documents\BPI_Dataset\extracted_csvfiles"

# Sorties avec modèle ajusté / non ajusté
OUTPUT_DIR_FALSE = r"C:\Users\svictor\Documents\BPI_Dataset\extracted_csvfiles_annotated_adj_false_intention"
OUTPUT_DIR_TRUE  = r"C:\Users\svictor\Documents\BPI_Dataset\extracted_csvfiles_annotated_adj_true_intention"

# Trois sessions filmées dans BPI (structure interne du dataset)
SESSIONS = [
    r"raw_data\data_2018-01-28-14-57-55",
    r"raw_data\data_2018-01-28-14-58-46",
    r"raw_data\data_2018-01-28-15-00-12",
]

WEATHER_DEFAULT = "clear"          # BPI n’a pas d’annotation météo → clear par défaut
CHINA_DEFAULT_HEIGHT_CM = 169.6    # Taille fallback si estimation impossible
MIN_HEIGHT_COUNT        = 5        # Nombre minimal de mesures LiDAR valides

# Orientation → fenêtre considérée comme "piéton regarde la route"
ORI_TOWARD_DEG_WINDOWS = [(135.0, 225.0)]
REQUIRE_IMG_VALID      = False     # Si True → exige 112_img_valid == 1

# ======================================================================
# TQDM — pour afficher la progression proprement
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
# CHARGEMENT DU MODÈLE CNRS (décision piéton)
# ======================================================================

MODEL_PATH = r"E:\crossing-model\main_experiment\model_datas\CNRS_behavior_model.py"

spec = importlib.util.spec_from_file_location("pedestrian_behavior_model", MODEL_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Impossible de charger le modèle: {MODEL_PATH}")

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if not hasattr(module, "pedestrian_behavior_model") or not callable(module.pedestrian_behavior_model):
    raise RuntimeError(f"Le module ne fournit pas 'pedestrian_behavior_model' ({MODEL_PATH})")

# ======================================================================
# FONCTIONS UTILITAIRES
# ======================================================================

def find_col(df: pd.DataFrame, suffix: str) -> str:
    """
    Recherche robuste d'une colonne :
    - match exact privilégié
    - sinon match par suffixe (utile avec préfixes '000_')
    - si plusieurs matches → choisir celui au plus petit préfixe numérique
    """
    if suffix in df.columns:
        return suffix

    hits = [c for c in df.columns if str(c).endswith(suffix)]
    if not hits:
        raise KeyError(f"Colonne se terminant par '{suffix}' introuvable.")

    if len(hits) > 1:
        def prefnum(x):
            m = re.match(r"^(\d+)_", str(x))
            return int(m.group(1)) if m else 10**9
        hits.sort(key=prefnum)

    return hits[0]


def pick_time_col(df: pd.DataFrame) -> str:
    """
    Détecte automatiquement la meilleure colonne temporelle.
    Évite les colonnes image_rel_time (incohérentes entre capteurs).
    """
    priorities = ["001_rel_time", "rel_time", "lidar_rel_time", "can_rel_time", "imu_rel_time"]

    for name in priorities:
        cands = [c for c in df.columns if c.endswith(name) and "image_rel_time" not in c]
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1 and name == "rel_time":
            def prefnum(x):
                m = re.match(r"^(\d+)_", str(x))
                return int(m.group(1)) if m else 10**9
            return sorted(cands, key=prefnum)[0]

    rels = [c for c in df.columns if c.endswith("rel_time") and "image_rel_time" not in c]
    if rels:
        def prefnum(x):
            m = re.match(r"^(\d+)_", str(x))
            return int(m.group(1)) if m else 10**9
        return sorted(rels, key=prefnum)[0]

    # fallback : index artificiel
    df["_idx"] = np.arange(len(df))
    return "_idx"


def frame_glob_patterns(root, frame_id):
    """Retourne les patterns possibles pour retrouver un fichier LiDAR correspondant à un frame_id."""
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
    """Mémoïsation : évite de refaire des dizaines de tests glob.glob()."""
    for p in patterns_tuple:
        if glob.glob(p):
            return True
    return False


def guess_session_for_csv(df, sessions, sample_n=40):
    """
    Devine à quelle session un CSV appartient en recherchant ses frames dans les fichiers LiDAR.
    Permet à ped_height.py d'utiliser le bon dossier raw_data.
    """
    try:
        fr_col = find_col(df, "lidar_frame")
    except:
        return sessions[0]

    frames = pd.to_numeric(df[fr_col], errors="coerce").dropna().astype(int).values.tolist()
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


def normalize_degrees(series):
    """Normalise une colonne d'angles en DEGRÉS dans [0, 360)."""
    deg = pd.to_numeric(series, errors="coerce").astype(float)
    deg = np.mod(deg, 360.0)
    deg[deg < 0] += 360.0
    return deg


def in_windows_deg(angle_deg, windows):
    """Retourne True si l'angle est dans au moins une fenêtre (a,b)."""
    out = pd.Series(False, index=angle_deg.index)
    for a, b in windows:
        a = float(a); b = float(b)
        if a <= b:
            out |= (angle_deg >= a) & (angle_deg <= b)
        else:
            out |= (angle_deg >= a) | (angle_deg <= b)
    return out

# ======================================================================
# ANNOTATION PRINCIPALE
# ======================================================================

def annotate_file(path, output_dir_false, output_dir_true):
    """
    Lit un CSV brut du dataset BPI, estime la taille du piéton, identifie les frames pertinentes
    et génère deux fichiers annotés : prédiction non ajustée et ajustée du modèle.
    """
    base_name = os.path.basename(path)
    if base_name.lower().startswith("explain"):
        return None  # fichiers internes ignorés

    df = pd.read_csv(path, low_memory=False)
    if df.shape[0] == 0:
        raise ValueError("CSV vide (0 lignes)")

    # ---- Détection des colonnes essentielles ----
    time_col        = pick_time_col(df)
    lidar_valid_col = find_col(df, "lidar_is_valid")
    pv_lon_col      = find_col(df, "lidar_pv_lon")       # distance (m)
    pc_lat_col      = find_col(df, "lidar_pc_lat")       # sur route
    speed_col       = find_col(df, "can_VehicleSpeed")   # vitesse (km/h)
    ori_col         = find_col(df, "img_orientation")    # orientation (°)

    # img_valid peut ne pas exister
    img_valid_col = None
    try:
        img_valid_col = find_col(df, "img_valid")
    except Exception:
        pass

    # Tri temporel
    df = df.sort_values(by=[time_col]).reset_index(drop=True)

    # ---- Estimation de la taille ----
    session_root = guess_session_for_csv(df, SESSIONS)
    h_cm_all, _ = estimate_ped_height_cm_for_df(df, pcl_root=session_root, f_px=None)

    h_raw = pd.to_numeric(h_cm_all, errors="coerce").astype(float)
    mask_150_200 = np.isfinite(h_raw) & (150 <= h_raw) & (h_raw <= 200)

    ped_h_const = (
        round(float(np.nanmean(h_raw[mask_150_200])), 1)
        if mask_150_200.sum() >= MIN_HEIGHT_COUNT
        else CHINA_DEFAULT_HEIGHT_CM
    )

    # ---- Extraction des séries ----
    lidar_valid = (pd.to_numeric(df[lidar_valid_col], errors="coerce") == 1)
    distance_m  = pd.to_numeric(df[pv_lon_col], errors="coerce").astype(float)
    speed_kmh   = pd.to_numeric(df[speed_col], errors="coerce").astype(float)
    pc_lat      = pd.to_numeric(df[pc_lat_col], errors="coerce").astype(float)

    # Orientation en degrés
    ori_deg = normalize_degrees(df[ori_col])
    ori_ok  = in_windows_deg(ori_deg, ORI_TOWARD_DEG_WINDOWS)

    # Option : exiger img_valid == 1
    if REQUIRE_IMG_VALID and img_valid_col is not None:
        img_ok = (pd.to_numeric(df[img_valid_col], errors="coerce") == 1)
        ori_ok = ori_ok & img_ok

    # ---- Définition du ground-truth frame-wise ----
    # GT = sur route (pc_lat > 0) ET LiDAR valide ET orientation vers la route
    onroad_bool  = (pc_lat > 0)
    true_label_s = (onroad_bool & lidar_valid & ori_ok).astype(bool)

    # ---- Filtre strict pour écrire ----
    keep = lidar_valid & np.isfinite(distance_m) & np.isfinite(speed_kmh) & ori_ok
    if not bool(keep.any()):
        tqdm_write(f"[SKIP] {base_name} : aucune frame exploitable")
        return None

    # ==================================================================
    # PREDICTION (adj=False et adj=True)
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
                    adj_value   # <--- ajustement biais activé/désactivé
                )
                preds.append(bool(y))
            except Exception:
                preds.append(False)  # fallback robuste

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

        # Écriture
        base = os.path.splitext(base_name)[0]
        out_path = os.path.join(out_dir, f"{base}_annot.csv")
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
                tqdm_write(
                    f"[OK] {res} -> "
                    f"{os.path.basename(OUTPUT_DIR_FALSE)}, "
                    f"{os.path.basename(OUTPUT_DIR_TRUE)}"
                )
        except Exception as e:
            tqdm_write(f"[WARN] {os.path.basename(f)} : {e}")
