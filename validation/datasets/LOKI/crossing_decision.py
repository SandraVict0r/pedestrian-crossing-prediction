# -*- coding: utf-8 -*-
"""
Export LOKI -> CSV (par piéton) + prédictions modèle (avec / sans ajustement)

Objectif
- Parcourir les dossiers `scenario_***` du dataset LOKI
- Pour chaque frame :
  - lire label3d_****.txt (piétons 3D + intention “Crossing the road”)
  - lire odom_****.txt (pose véhicule) -> calculer vitesse (km/h)
  - associer une météo (via _weather_annotations.csv)
- Construire un DataFrame (scenario_id, frame_id, ped_id, weather, velocity, distance, height, true_label)
- Faire tourner un modèle Python externe (CNRS_behavior_model.py) :
  - mode "adj" (safety bias ON)
  - mode "no-adj" (safety bias OFF)
- Exporter 2 CSV par piéton (adj / no-adj)

Notes
- FRAMERATE_HZ = 5 Hz (LOKI) pour reconstruire la vitesse depuis l’odom.
- La météo est lue uniquement depuis un mapping CSV local (pas d’heuristique).
"""

import os, re, json, math, importlib.util, logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np
from tqdm import tqdm

# ===================== CONFIG =====================
# Dossier racine du dataset LOKI (contient scenario_000, scenario_001, ...)
BASE_DIR = Path(r"E:\crossing-model\main_experiment\model_validation\datasets\loki_data")

# Chemin vers le script modèle : doit contenir une fonction pedestrian_behavior_model(...)
MODEL_PATH = Path(r"E:\crossing-model\main_experiment\model_datas\CNRS_behavior_model.py")

# Dossiers de sortie : un pour les prédictions "ajustées", un pour "non ajustées"
OUT_DIR_ADJ   = Path(r"E:\crossing-model\main_experiment\model_validation\datasets\loki_data\model_resul_adj_LOKI_half_velocity_20kmh_rule")
OUT_DIR_NOADJ = Path(r"E:\crossing-model\main_experiment\model_validation\datasets\loki_data\model_result_no_adj_LOKI_half_velocity_20kmh_rule")
OUT_DIR_ADJ.mkdir(parents=True, exist_ok=True)
OUT_DIR_NOADJ.mkdir(parents=True, exist_ok=True)

# Framerate LOKI (sert à convertir Δframes en Δt)
FRAMERATE_HZ = 5.0  # 5 FPS d'après LOKI

# Limite optionnelle : None = traiter tous les scénarios
MAX_SCENARIOS = None

# ===================== LOG =====================
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("loki_csv_export")

# ===================== HELPERS : listing / paths =====================
# Regex des scénarios (nom dossier)
RE_SCEN  = re.compile(r"^scenario_(\d{3})$")

# Regex frame id (capture 4 digits dans label3d_**** / odom_**** / image_**** etc.)
RE_FRAME = re.compile(r".*_(\d{4})\.(png|json|txt|ply)$", re.IGNORECASE)

def _row_is_valid(weather: str, velocity, distance, height, true_label) -> bool:
    """
    Validation basique : on n’exporte/predit que si toutes les variables nécessaires
    sont présentes et numériques (pas None / NaN).

    NB: weather a un défaut 'clear' si non annoté.
    """
    if weather is None or str(weather).strip() == "":
        return False
    if velocity is None or pd.isna(velocity):
        return False
    if distance is None or pd.isna(distance):
        return False
    if height is None or pd.isna(height):
        return False
    if true_label is None or pd.isna(true_label):
        return False
    return True

def list_scenarios(base_dir: Path) -> List[int]:
    """Retourne la liste triée des scenario_id détectés dans BASE_DIR."""
    sids = []
    for d in base_dir.iterdir():
        if d.is_dir():
            m = RE_SCEN.match(d.name)
            if m:
                sids.append(int(m.group(1)))
    return sorted(sids)

def list_frames(sdir: Path) -> List[int]:
    """
    Liste les frames d’un scénario.
    Ici on s’appuie sur les images (image_****.png) comme “référence” des frames disponibles.
    """
    fids = []
    for name in os.listdir(sdir):
        if name.lower().startswith("image_") and name.lower().endswith(".png"):
            m = RE_FRAME.match(name)
            if m:
                fids.append(int(m.group(1)))
    return sorted(fids)

def scenario_dir(base_dir: Path, sid: int) -> Path:
    """Construit le chemin du dossier scenario_XXX."""
    return base_dir / f"scenario_{sid:03d}"

def paths_for_frame(sdir: Path, fid: int) -> Dict[str, Path]:
    """
    Convention LOKI attendue dans chaque scénario :
    - label3d_****.txt : annotations 3D + intention piéton
    - odom_****.txt    : pose véhicule
    """
    f = f"{fid:04d}"
    return {
        "label3d": sdir / f"label3d_{f}.txt",
        "odom":    sdir / f"odom_{f}.txt",
    }

def sanitize_filename(s: str) -> str:
    """Nettoie un identifiant (ped_id) pour en faire un nom de fichier sûr."""
    return re.sub(r"[^A-Za-z0-9_\-\.]+", "_", str(s))

# ===================== METEO : mapping local uniquement =====================
# On lit UNIQUEMENT le CSV "_weather_annotations.csv" (même dossier que ce script).
# Attendu : colonnes ["scenario_id","weather"] avec valeurs: rain / clear / night / other.
# Si un scénario n’est pas présent dans le CSV -> "clear" par défaut.

try:
    SCRIPT_DIR = Path(__file__).resolve().parent
except NameError:
    # Cas notebook / exécution interactive
    SCRIPT_DIR = Path.cwd()

WEATHER_CSV_NAME = "_weather_annotations.csv"
WEATHER_MAPPING_PATH = SCRIPT_DIR / WEATHER_CSV_NAME

# Cache en mémoire (évite de relire le CSV à chaque scénario)
_WEATHER_MAP: Dict[int, str] = {}

def _load_weather_mapping() -> Dict[int, str]:
    """Charge le mapping météo depuis le CSV local (une seule fois) et le met en cache."""
    global _WEATHER_MAP
    if _WEATHER_MAP:
        return _WEATHER_MAP

    m: Dict[int, str] = {}
    if WEATHER_MAPPING_PATH.exists():
        try:
            df = pd.read_csv(WEATHER_MAPPING_PATH)
            for _, r in df.iterrows():
                try:
                    sid = int(r["scenario_id"])
                    w = str(r["weather"]).strip().lower()
                    if w:
                        m[sid] = w
                except Exception:
                    continue
            log.info(f"Météo: mapping chargé ({len(m)} scénarios) depuis {WEATHER_MAPPING_PATH}")
        except Exception as e:
            log.warning(f"Météo: lecture impossible de {WEATHER_MAPPING_PATH}: {e}")
    else:
        log.warning(f"Météo: mapping CSV introuvable à {WEATHER_MAPPING_PATH} — défaut 'clear' si manquant.")

    _WEATHER_MAP = m
    return _WEATHER_MAP

def find_weather_no_heuristic(sdir: Path) -> str:
    """
    Retourne la météo du scénario en mode "mapping only".
    - Recherche scenario_id dans _weather_annotations.csv
    - Si absent -> "clear"
    """
    m = _load_weather_mapping()
    sid = None
    m_sc = RE_SCEN.match(sdir.name)
    if m_sc:
        sid = int(m_sc.group(1))

    if sid is not None and sid in m:
        return m[sid]
    return "clear"

# ===================== PARSE LABEL3D =====================
def read_csv_any(path: Path) -> Optional[pd.DataFrame]:
    """Lecture CSV robuste (engine python) ; retourne None si lecture impossible."""
    try:
        return pd.read_csv(path, engine="python")
    except Exception:
        return None

def parse_label3d_pedestrians(path: Path) -> pd.DataFrame:
    """
    Parse label3d_****.txt et retourne uniquement les lignes 'pedestrian'.

    Sortie (DataFrame):
    - ped_id           : identifiant de track
    - distance_m       : distance euclidienne (pos_x,pos_y,pos_z)
    - real_height_cm   : hauteur estimée à partir dim_z (bornée sinon valeur par défaut)
    - true_label       : 1 si intended_actions == 'Crossing the road', sinon 0
    """
    df = read_csv_any(path)
    if df is None or df.empty:
        return pd.DataFrame(columns=["ped_id","distance_m","real_height_cm","true_label"])

    # Colonnes attendues ; sinon on tente de renommer par position si le fichier a >= 13 colonnes
    needed = ["labels","track_id","pos_x","pos_y","pos_z","dim_z","intended_actions"]
    if not set(needed).issubset(df.columns) and df.shape[1] >= 13:
        df.columns = [
            "labels","track_id","stationary","pos_x","pos_y","pos_z",
            "dim_x","dim_y","dim_z","yaw","vehicle_state",
            "intended_actions","potential_destination"
        ] + [f"col_{i}" for i in range(df.shape[1]-13)]

    # Filtre piétons uniquement
    df = df[df["labels"].astype(str).str.lower() == "pedestrian"].copy()
    if df.empty:
        return pd.DataFrame(columns=["ped_id","distance_m","real_height_cm","true_label"])

    # Conversion numérique
    for c in ["pos_x","pos_y","pos_z","dim_z"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Distance euclidienne à l’origine (véhicule)
    df["distance_m"] = np.sqrt(df["pos_x"]**2 + df["pos_y"]**2 + df["pos_z"]**2)

    # Hauteur en cm (dim_z en m -> *100), bornage [150,200], sinon valeur par défaut 165.25
    df["real_height_cm"] = (
        pd.to_numeric(df["dim_z"], errors="coerce")
          .abs()
          .mul(100)
          .where(lambda s: (s >= 150) & (s <= 200), 165.25)
    )

    # Label GT (intention)
    df["true_label"] = (
        df["intended_actions"].astype(str).str.strip().str.lower() == "crossing the road"
    ).astype(int)

    # Identifiant piéton (track)
    df["ped_id"] = df["track_id"].astype(str)

    return df[["ped_id","distance_m","real_height_cm","true_label"]].reset_index(drop=True)

# ===================== ODOM -> VITESSE =====================
def read_odom_pose(path: Path) -> Optional[Tuple[float, float, float]]:
    """
    Lit odom_*.txt et retourne (x,y,z) si possible.

    Format attendu :
    - 1 ligne
    - valeurs séparées par virgule ou espaces
    - au moins 3 colonnes (pos_x,pos_y,pos_z)
    """
    if not path.exists():
        return None

    # Tentative 1 : lecture CSV brute sans entête
    try:
        df = pd.read_csv(path, engine="python", header=None)
        if df.shape[1] >= 3:
            row = df.iloc[0]
            return (float(row[0]), float(row[1]), float(row[2]))
    except Exception:
        pass

    # Tentative 2 : parsing texte
    try:
        line = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()[0]
        parts = re.split(r"[,\s;]+", line)
        if len(parts) >= 3:
            x, y, z = map(float, parts[:3])
            return (x, y, z)
    except Exception:
        pass

    return None

def speeds_from_odom(sdir: Path, frame_ids: List[int]) -> Dict[int, Optional[float]]:
    """
    Calcule une vitesse véhicule par frame à partir de l’odom :
    v = ||Δpos|| / Δt, avec Δt = (Δframes)/FRAMERATE_HZ
    - diff arrière : vitesse de fid calculée avec fid-1
    - la toute première frame récupère la première vitesse valide si nécessaire
    - conversion m/s -> km/h (*3.6)
    """
    poses: Dict[int, Optional[Tuple[float,float,float]]] = {}
    for fid in frame_ids:
        poses[fid] = read_odom_pose(paths_for_frame(sdir, fid)["odom"])

    vmap: Dict[int, Optional[float]] = {fid: None for fid in frame_ids}

    prev_fid = None
    prev_pose = None
    for fid in frame_ids:
        pose = poses[fid]
        if pose is not None and prev_pose is not None and prev_fid is not None:
            dx = pose[0] - prev_pose[0]
            dy = pose[1] - prev_pose[1]
            dz = pose[2] - prev_pose[2]
            dt = (fid - prev_fid) / float(FRAMERATE_HZ)
            if dt > 0:
                vmap[fid] = (math.sqrt(dx*dx + dy*dy + dz*dz) / dt) * 3.6

        # On met à jour "prev" uniquement si pose valide
        if pose is not None:
            prev_pose = pose
            prev_fid = fid

    # Copie de la première vitesse valide sur la frame 0 si elle est manquante
    valid = [fid for fid in frame_ids if vmap.get(fid) is not None]
    if len(valid) >= 1:
        f1 = valid[0]
        f0 = frame_ids[0]
        if vmap.get(f0) is None:
            vmap[f0] = vmap[f1]

    return vmap

# ===================== MODÈLE (import dynamique) =====================
def load_model(model_path: Path):
    """
    Charge dynamiquement un fichier Python (.py) et récupère la fonction
    pedestrian_behavior_model(...) dedans.
    """
    spec = importlib.util.spec_from_file_location("pedestrian_behavior_model", str(model_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "pedestrian_behavior_model"):
        raise AttributeError("pedestrian_behavior_model(...) introuvable dans le module.")
    return module.pedestrian_behavior_model

# Fonction du modèle (callable)
ped_model = load_model(MODEL_PATH)

# ===================== PIPELINE SCÉNARIO =====================
def process_scenario(sid: int, pos_frames: int = 1, pos_peds: int = 2) -> int:
    """
    Traite un scénario :
    - parse données frame par frame
    - agrège lignes valides
    - prédit par piéton
    - écrit 2 CSV par piéton (adj / noadj)
    Retourne : nombre de CSV écrits.
    """
    sdir = scenario_dir(BASE_DIR, sid)
    frames = list_frames(sdir)
    if not frames:
        log.info(f"scenario_{sid:03d}: aucune frame — skip.")
        return 0

    # Météo du scénario (mapping CSV ; défaut clear)
    weather = find_weather_no_heuristic(sdir)

    # Vitesse véhicule par frame (km/h)
    vmap = speeds_from_odom(sdir, frames)

    rows: List[Dict[str, Any]] = []

    # --- Barre de progression FRAMES (tqdm) ---
    with tqdm(total=len(frames), desc=f"Frames s{sid:03d}", position=pos_frames,
              leave=False, dynamic_ncols=True) as p_frames:

        for fid in frames:
            l3d = paths_for_frame(sdir, fid)["label3d"]

            # On ne traite que si label3d existe
            if l3d.exists():
                dfp = parse_label3d_pedestrians(l3d)

                # Pour chaque piéton détecté dans cette frame :
                if not dfp.empty:
                    for _, r in dfp.iterrows():
                        vel = vmap.get(fid, None)
                        dist = r.get("distance_m", np.nan)
                        hgt  = r.get("real_height_cm", np.nan)
                        gt   = r.get("true_label", np.nan)

                        # Filtre “ligne exploitable”
                        if _row_is_valid(weather, vel, dist, hgt, gt):
                            rows.append({
                                "scenario_id": sid,
                                "frame_id": fid,
                                "pedestrian_id": r["ped_id"],
                                "weather": weather,
                                # Ici tu appliques une règle spécifique : vitesse /2
                                "velocity_kmh": vel / 2,
                                "distance_m": dist,
                                "real_height_cm": hgt,
                                "true_label": gt,
                            })

            p_frames.update(1)

    if not rows:
        log.info(f"scenario_{sid:03d}: aucun piéton 3D — skip.")
        return 0

    # Table globale scénario (toutes les frames/peds)
    df = pd.DataFrame(rows).sort_values(["pedestrian_id", "frame_id"]).reset_index(drop=True)
    if df.empty:
        log.info(f"scenario_{sid:03d}: aucune frame valide — skip.")
        return 0

    n_csv = 0
    ped_ids = list(df["pedestrian_id"].unique())

    # --- Barre de progression PIÉTONS ---
    with tqdm(total=len(ped_ids), desc=f"Piétons s{sid:03d}", position=pos_peds,
              leave=False, dynamic_ncols=True) as p_peds:

        for ped_id in ped_ids:
            dfp = df[df["pedestrian_id"] == ped_id].sort_values("frame_id").reset_index(drop=True)
            if dfp.empty:
                continue

            def predict_for(adj_flag: bool) -> pd.Series:
                """
                Applique le modèle frame par frame pour un piéton donné.
                adj_flag:
                  - True  -> prédiction avec biais/ajustement sécurité
                  - False -> sans ajustement
                """
                preds = []
                for _, row in dfp.iterrows():
                    try:
                        crossing = ped_model(
                            row["weather"],                         # str (défaut 'clear')
                            float(row["real_height_cm"]),
                            float(row["velocity_kmh"]),
                            float(row["distance_m"]),
                            bool(adj_flag)
                        )

                        # Règle métier supplémentaire :
                        # si vitesse < 20 km/h -> crossing = True
                        if float(row["velocity_kmh"]) < 20:
                            crossing = True

                    except Exception as e:
                        log.warning(f"Model error (s{sid:03d}, ped={ped_id}, frame={row['frame_id']}): {e}")
                        crossing = None

                    preds.append(crossing)

                return pd.Series(preds, name="predicted_label")

            # Deux versions : ajustée / non ajustée
            df_adj   = dfp.copy()
            df_noadj = dfp.copy()

            df_adj["predicted_label"]   = predict_for(True)
            df_noadj["predicted_label"] = predict_for(False)

            # Colonnes finales exportées
            final_cols = [
                "scenario_id","frame_id","pedestrian_id",
                "weather","velocity_kmh","distance_m","real_height_cm",
                "true_label","predicted_label"
            ]
            df_adj   = df_adj[final_cols]
            df_noadj = df_noadj[final_cols]

            # Un fichier par piéton, par scénario
            fname = f"scenario_{sid:03d}_ped_{sanitize_filename(ped_id)}.csv"
            df_adj.to_csv(OUT_DIR_ADJ / fname, index=False, encoding="utf-8")
            df_noadj.to_csv(OUT_DIR_NOADJ / fname, index=False, encoding="utf-8")
            n_csv += 2

            p_peds.update(1)

    return n_csv

# ===================== RUN GLOBAL =====================
def run_all():
    """
    Lance le traitement sur tous les scénarios présents dans BASE_DIR.
    MAX_SCENARIOS peut servir à limiter (debug).
    """
    sids = list_scenarios(BASE_DIR)
    if MAX_SCENARIOS is not None:
        sids = [sid for sid in sids if sid < MAX_SCENARIOS]

    # Barre de progression principale : scénarios
    with tqdm(total=len(sids), desc="Scénarios", position=0, dynamic_ncols=True) as p_scen:
        for sid in sids:
            process_scenario(sid, pos_frames=1, pos_peds=2)
            p_scen.update(1)

    log.info("Terminé.")

if __name__ == "__main__":
    run_all()
