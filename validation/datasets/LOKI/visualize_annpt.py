# -*- coding: utf-8 -*-
"""
LOKI Viewer (OpenCV) — overlay 2D/3D + météo + vitesses + (option) prédiction modèle

But :
- Afficher les images LOKI frame par frame (image_****.png)
- Dessiner des overlays :
  - Boîtes 2D piétons + informations 3D (distance, hauteur, GT crossing)
  - Boîtes 2D véhicules + (option) distance au piéton le plus proche + vitesse véhicule
  - En-tête : scenario/frame, météo, vitesse ego, compte objets
  - (optionnel) afficher prédictions du modèle (adj / noadj) via la touche 'm'

Entrées attendues dans chaque scenario_*** :
- image_****.png
- label2d_****.json   (boîtes 2D : piétons / véhicules / crosswalks / traffic lights)
- label3d_****.txt    (objets 3D : positions + dim_z + intended_actions + vehicle_state, etc.)
- odom_****.txt       (pose véhicule : x,y,z,roll,pitch,yaw)

Contrôles (viewer) :
- j / espace : frame +1
- k          : frame -1
- J          : frame +10
- K          : frame -10
- n          : scénario +1
- p          : scénario -1
- m          : toggle affichage prédictions modèle
- h          : aide
- q / ESC    : quitter
"""

import os, re, json, math, importlib.util, logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np

# ====== CONFIG ======
# Dataset LOKI : contient les dossiers scenario_000, scenario_001, ...
BASE_DIR = Path(r"E:\crossing-model\main_experiment\model_validation\datasets\loki_data")

# Script modèle Python externe (doit contenir pedestrian_behavior_model(...))
MODEL_PATH = Path(r"E:\crossing-model\main_experiment\model_datas\CNRS_behavior_model.py")

# Paramètres généraux
FRAMERATE_HZ = 5.0          # cadence LOKI (sert au calcul des vitesses via odom)
RUN_MODEL_DEFAULT = False   # par défaut, ne pas afficher la prédiction modèle (toggle 'm')

# Position de départ dans le viewer
START_SCENARIO = 0
START_FRAME = 0

# UI overlay : tailles/épaisseurs
HEADER_FONT_SIZE = 24
BOX_FONT_SIZE    = 20
BOX_THICKNESS    = 3

# Options overlay véhicules
VEH_COLOR = (255, 128, 0)    # couleur “véhicule”
DRAW_LINK_LINE = True        # ligne véhicule ↔ piéton le plus proche (si possible)

# Hypothèse sur le repère des positions 3D dans label3d :
# - 'ego'   : positions exprimées dans le repère ego-vehicle (à convertir via odom)
# - 'world' : positions déjà en coordonnées monde
LOKI_POS_FRAME = "ego"  # 'ego' | 'world'

# Vitesse véhicule (pistes) : réglages “robustesse”
SPEED_USE_Z = False
SPEED_SMOOTH_ALPHA = 0.3
SPEED_MAX_MPS = 60.0
SPEED_ZERO_IF_STATE = {"Parked", "Stopped"}
SPEED_MIN_TIME_S    = 0.6
SPEED_MIN_MOVE_M    = 0.5

# ====== LOG ======
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("loki_viewer")

# ====== LIBS GRAPHIQUES ======
# PIL pour dessiner les overlays, OpenCV pour l’UI interactive
from PIL import Image, ImageDraw, ImageFont
import cv2

# -------------------------------------------------------------------------
# Helpers texte Pillow : compatibilité entre versions (bbox vs textsize)
# -------------------------------------------------------------------------
def _measure_text(draw, text, font, *, multiline=False, spacing=0):
    """Mesure robuste de la taille d’un texte (monoligne ou multilignes)."""
    try:
        if multiline and hasattr(draw, "multiline_textbbox"):
            l, t, r, b = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
            return (r - l, b - t)
        if (not multiline) and hasattr(draw, "textbbox"):
            l, t, r, b = draw.textbbox((0, 0), text, font=font)
            return (r - l, b - t)
    except Exception:
        pass
    # fallbacks
    if multiline and hasattr(draw, "multiline_textsize"):
        return draw.multiline_textsize(text, font=font, spacing=spacing)
    if (not multiline) and hasattr(draw, "textsize"):
        return draw.textsize(text, font=font)

    # approximation (si Pillow minimal)
    try:
        w = int(font.getlength(text)) if hasattr(font, "getlength") else int(len(text) * font.size * 0.6)
        if hasattr(font, "getmetrics"):
            a, d = font.getmetrics()
            h = a + d
        else:
            h = int(font.size * 1.2)
        if multiline:
            lines = text.splitlines() or [text]
            maxw, totalh = 0, 0
            for line in lines:
                lw = int(font.getlength(line)) if hasattr(font, "getlength") else int(len(line) * font.size * 0.6)
                maxw = max(maxw, lw); totalh += h
            totalh += spacing * (len(lines) - 1)
            return (maxw, totalh)
        return (w, h)
    except Exception:
        return (0, 0)

def load_font(size=16):
    """Charge une police lisible (Windows: Arial, fallback DejaVu, sinon default)."""
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()

def draw_box_with_text(img: Image.Image, box: dict, lines: List[str], color=(0,255,0)):
    """
    Dessine une bbox (left, top, width, height) + un bloc texte au-dessus (clampé dans l’image).
    - bbox : contour coloré
    - texte : fond noir semi-transparent + texte blanc
    """
    draw = ImageDraw.Draw(img, "RGBA")

    L = float(box.get("left", 0)); T = float(box.get("top", 0))
    W = float(box.get("width", 0)); H = float(box.get("height", 0))

    draw.rectangle([L, T, L+W, T+H], outline=color+(255,), width=BOX_THICKNESS)

    font = load_font(BOX_FONT_SIZE)
    padding = 4
    text = "\n".join(lines)
    tw, th = _measure_text(draw, text, font, multiline=True, spacing=2)

    # on place le texte au-dessus de la boîte (sinon clamp à y=0)
    x0, y0 = L, max(0, T - th - 2*padding)
    x1, y1 = x0 + tw + 2*padding, y0 + th + 2*padding

    # clamp aux bords image
    Wimg, Himg = img.size
    x0 = max(0, min(x0, Wimg - 1)); y0 = max(0, min(y0, Himg - 1))
    x1 = max(0, min(x1, Wimg - 1)); y1 = max(0, min(y1, Himg - 1))

    draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0, 160))
    draw.multiline_text((x0+padding, y0+padding), text, fill=(255,255,255,255), font=font, spacing=2)

# =============================================================================
# IO / PARSE
# =============================================================================

def _normalize_label3d_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise les colonnes d’un label3d (robuste aux variantes) afin d’obtenir
    au minimum :
      labels, track_id, pos_x, pos_y, pos_z, dim_z, intended_actions, vehicle_state

    Stratégie :
    - si pas d’en-têtes “connus” et table large (>=13 colonnes) :
      -> réaffecter un schéma standard (comme dans tes autres scripts)
    - sinon :
      -> mapping souple (pos_x peut s’appeler x / center_x, etc.)
    """
    if df is None or df.empty:
        return df

    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    lower_map = {c.lower(): c for c in df.columns}

    def pick(*keys):
        for k in keys:
            k = k.lower()
            if k in lower_map:
                return lower_map[k]
        return None

    # fallback schema si pas de colonnes “labels” et table large
    if (pick('labels') is None) and df.shape[1] >= 13:
        df2 = df.copy()
        df2.columns = [
            "labels","track_id","stationary","pos_x","pos_y","pos_z",
            "dim_x","dim_y","dim_z","yaw","vehicle_state",
            "intended_actions","potential_destination"
        ] + [f"col_{i}" for i in range(df.shape[1]-13)]
        return df2

    # soft rename (tolère variantes de noms)
    rename = {}
    c = pick('labels','label','class','type','object_class')
    if c: rename[c] = 'labels'
    c = pick('track_id','trackid','id','object_id','obj_id','track id')
    if c: rename[c] = 'track_id'
    cx = pick('pos_x','position_x','x','center_x','cx')
    cy = pick('pos_y','position_y','y','center_y','cy')
    cz = pick('pos_z','position_z','z','center_z','cz','height')
    if cx: rename[cx] = 'pos_x'
    if cy: rename[cy] = 'pos_y'
    if cz: rename[cz] = 'pos_z'
    dz = pick('dim_z','size_z','length_z','height','h','extent_z')
    if dz: rename[dz] = 'dim_z'
    ia = pick('intended_actions','intention','action','intent')
    if ia: rename[ia] = 'intended_actions'
    vs = pick('vehicle_state','state','motion_state')
    if vs: rename[vs] = 'vehicle_state'

    if rename:
        df = df.rename(columns=rename)

    # log “une fois” pour debug : utile si format change d’un lot à l’autre
    try:
        if not getattr(_normalize_label3d_columns, "_logged_once", False):
            log.info("Colonnes label3d après normalisation: %s", list(df.columns)[:20])
            _normalize_label3d_columns._logged_once = True
    except Exception:
        pass

    return df

# Regex noms dossier / frames
RE_SCEN  = re.compile(r"^scenario_(\d{3})$")
RE_FRAME = re.compile(r".*_(\d{4})\.(png|json|txt|ply)$", re.IGNORECASE)

def list_scenarios(base_dir: Path) -> List[int]:
    """Liste triée des scenario_id (int)."""
    sids = []
    for d in base_dir.iterdir():
        if d.is_dir():
            m = RE_SCEN.match(d.name)
            if m:
                sids.append(int(m.group(1)))
    return sorted(sids)

def list_frames(sdir: Path) -> List[int]:
    """Liste triée des frame_id à partir des images image_****.png."""
    fids = []
    for name in os.listdir(sdir):
        if name.lower().startswith("image_") and name.lower().endswith(".png"):
            m = RE_FRAME.match(name)
            if m:
                fids.append(int(m.group(1)))
    return sorted(fids)

def scenario_dir(base_dir: Path, sid: int) -> Path:
    """Chemin dossier scenario_XXX."""
    return base_dir / f"scenario_{sid:03d}"

def paths_for_frame(sdir: Path, fid: int) -> Dict[str, Path]:
    """Chemins attendus pour une frame (image/label2d/label3d/odom)."""
    f = f"{fid:04d}"
    return {
        "image":   sdir / f"image_{f}.png",
        "label2d": sdir / f"label2d_{f}.json",
        "label3d": sdir / f"label3d_{f}.txt",
        "odom":    sdir / f"odom_{f}.txt",
    }

def read_json(path: Path) -> Optional[dict]:
    """Lecture JSON robuste (None si erreur)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def read_csv(path: Path) -> Optional[pd.DataFrame]:
    """
    Lecture “tolérante” des label3d :
    - tentative csv simple
    - si peu de colonnes : inférence séparateur (sep=None) + skip lignes invalides
    """
    try:
        df = pd.read_csv(path, engine="python")
        if df.shape[1] < 6:
            df = pd.read_csv(path, sep=None, engine="python", on_bad_lines="skip")
        return df
    except Exception:
        return None

# =============================================================================
# Météo : heuristique “fichiers meta”
# =============================================================================
def find_weather_no_heuristic(sdir: Path) -> Optional[str]:
    """
    Retrouve une météo pour le scénario.
    - Cherche d’abord dans quelques fichiers attendus (scenario_meta.json, meta.json, etc.)
    - Puis scan des .json du dossier
    - Défaut : "clear"

    NB : contrairement à ton script d’annotation Streamlit, ici c’est une heuristique “dataset-first”.
    """
    candidates = [sdir / "scenario_meta.json", sdir / "meta.json", sdir / "weather.json", sdir / "weather.txt"]
    for p in candidates:
        if not p.exists():
            continue
        if p.suffix.lower() == ".txt":
            try:
                t = p.read_text(encoding="utf-8").strip()
                return t.strip().capitalize() if t else None
            except Exception:
                continue
        else:
            d = read_json(p)
            if isinstance(d, dict):
                for k, v in d.items():
                    if str(k).lower() == "weather" and v:
                        return str(v).strip().capitalize()

    # scan secours de tous les json
    for name in os.listdir(sdir):
        p = sdir / name
        if p.suffix.lower() == ".json":
            d = read_json(p)
            if isinstance(d, dict):
                for k, v in d.items():
                    if str(k).lower() == "weather" and v:
                        return str(v).strip().capitalize()

    return "clear"

# =============================================================================
# Parse 2D : boîtes + structures (piétons / véhicules / crosswalks / feux)
# =============================================================================
def parse_label2d_pedestrians(path: Path) -> Dict[str, dict]:
    """Extrait les boîtes 2D des piétons depuis label2d JSON.
    Retour : {ped_id: {left, top, width, height}}
    """
    data = read_json(path)
    if not isinstance(data, dict):
        return {}
    ped = data.get("Pedestrian") or data.get("pedestrian") or {}
    out = {}
    if isinstance(ped, dict):
        for pid, obj in ped.items():
            if not isinstance(obj, dict):
                continue
            box = obj.get("box") or {}
            out[str(pid)] = {
                "left": float(box.get("left", 0)),
                "top": float(box.get("top", 0)),
                "width": float(box.get("width", 0)),
                "height": float(box.get("height", 0)),
            }
    return out

def parse_label2d_vehicles(path: Path) -> Dict[str, dict]:
    """Extrait boîtes véhicules depuis label2d, avec tolérance sur les clés.
    Retour : {veh_id: {box:{...}, type:str}}
    """
    data = read_json(path)
    if not isinstance(data, dict):
        return {}
    out: Dict[str, dict] = {}

    # 1) Section générique Vehicle
    veh_sec = data.get("Vehicle") or data.get("vehicle")
    if isinstance(veh_sec, dict):
        for vid, obj in veh_sec.items():
            if not isinstance(obj, dict):
                continue
            box = obj.get("box") or {}
            if {"left","top","width","height"}.issubset(box.keys()):
                out[str(vid)] = {
                    "box": {
                        "left": float(box["left"]), "top": float(box["top"]),
                        "width": float(box["width"]), "height": float(box["height"])
                    },
                    "type": str(obj.get("type") or obj.get("class") or "vehicle")
                }

    # 2) Catégories dédiées (Car/Bus/Truck/etc.)
    for key in ["Car","car","Bus","bus","Truck","truck","Bicycle","bicycle","Motorcycle","motorcycle","Motorbike","motorbike"]:
        sec = data.get(key)
        if isinstance(sec, dict):
            for vid, obj in sec.items():
                if not isinstance(obj, dict):
                    continue
                box = obj.get("box") or {}
                if {"left","top","width","height"}.issubset(box.keys()):
                    out[str(vid)] = {
                        "box": {
                            "left": float(box["left"]), "top": float(box["top"]),
                            "width": float(box["width"]), "height": float(box["height"])
                        },
                        "type": key.lower()
                    }
    return out

def parse_label2d_crosswalks(path: Path) -> List[dict]:
    """Extrait les passages piétons (polygones ou boîtes) si présents dans label2d."""
    data = read_json(path)
    if not isinstance(data, dict):
        return []
    candidates = []
    for key in ["Crosswalk", "crosswalk", "Zebra", "zebra", "PedCrossing", "ped_crossing", "cross_walk"]:
        if key in data and isinstance(data[key], dict):
            candidates.append(data[key])

    out: List[dict] = []
    for section in candidates:
        for _id, obj in section.items():
            if not isinstance(obj, dict):
                continue

            # 1) polygon
            poly = None
            if isinstance(obj.get("polygon"), list):
                poly = obj["polygon"]
            elif isinstance(obj.get("shape"), dict) and isinstance(obj["shape"].get("points"), list):
                poly = obj["shape"]["points"]

            if poly and len(poly) >= 3:
                pts = []
                for p in poly:
                    if isinstance(p, (list, tuple)) and len(p) >= 2:
                        pts.append((float(p[0]), float(p[1])))
                    elif isinstance(p, dict) and {"x","y"}.issubset(p.keys()):
                        pts.append((float(p["x"]), float(p["y"])))
                if len(pts) >= 3:
                    out.append({"polygon": pts})
                    continue

            # 2) fallback box
            box = obj.get("box") or {}
            if {"left","top","width","height"}.issubset(box.keys()):
                out.append({"box": {
                    "left": float(box["left"]),
                    "top": float(box["top"]),
                    "width": float(box["width"]),
                    "height": float(box["height"]),
                }})
    return out

def parse_label2d_traffic_lights(path: Path) -> List[dict]:
    """Extrait les feux tricolores 2D et normalise leur état (red/green/amber/off/unknown)."""
    data = read_json(path)
    if not isinstance(data, dict):
        return []
    sections = []
    for key in ["TrafficLight", "traffic_light", "traffic_lights", "Signal", "signal", "Light", "light"]:
        if key in data and isinstance(data[key], dict):
            sections.append(data[key])

    def norm(s): return str(s).strip().lower()
    out: List[dict] = []

    for section in sections:
        for _id, obj in section.items():
            if not isinstance(obj, dict):
                continue
            box = obj.get("box") or {}
            if not {"left","top","width","height"}.issubset(box.keys()):
                continue

            state_raw = obj.get("state") or obj.get("status") or obj.get("color") or obj.get("light_state") or ""
            s = norm(state_raw)

            # normalisation des variantes (FR/EN)
            if s in ("orange", "amber", "yellow"):
                s = "amber"
            elif s in ("red", "rouge"):
                s = "red"
            elif s in ("green", "vert"):
                s = "green"
            elif s in ("off", "out", "none"):
                s = "off"
            elif s == "":
                s = "unknown"

            out.append({
                "box": {"left": float(box["left"]), "top": float(box["top"]), "width": float(box["width"]), "height": float(box["height"])},
                "state": s
            })
    return out

# =============================================================================
# Parse 3D : piétons et véhicules (positions + distance + hauteur + GT)
# =============================================================================
def parse_label3d_pedestrians(path: Path) -> pd.DataFrame:
    """Retourne un DataFrame piétons 3D : pos + distance + height + true_label."""
    df = read_csv(path)
    if df is None or df.empty:
        return pd.DataFrame(columns=["ped_id","distance_m","real_height_cm","true_label","pos_x","pos_y","pos_z"])

    df = _normalize_label3d_columns(df)

    if "labels" not in df.columns:
        return pd.DataFrame(columns=["ped_id","distance_m","real_height_cm","true_label","pos_x","pos_y","pos_z"])

    lab = df["labels"].astype(str).str.lower().str.strip()
    df = df[lab == "pedestrian"].copy()
    if df.empty:
        return pd.DataFrame(columns=["ped_id","distance_m","real_height_cm","true_label","pos_x","pos_y","pos_z"])

    # Positions 3D requises
    for c in ["pos_x","pos_y","pos_z"]:
        if c not in df.columns:
            return pd.DataFrame(columns=["ped_id","distance_m","real_height_cm","true_label","pos_x","pos_y","pos_z"])
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Hauteur (dim_z en m -> cm), bornage, défaut 165.25 cm
    dimz = pd.to_numeric(df.get("dim_z", np.nan), errors="coerce")
    taille_cm = dimz.abs() * 100.0
    mask = taille_cm.between(150, 200, inclusive="both")
    real_h = taille_cm.where(mask, 165.25)

    # Distance 3D à l’origine (ego)
    dist = np.sqrt(df["pos_x"]**2 + df["pos_y"]**2 + df["pos_z"]**2)

    # True label : basé sur intended_actions (heuristique “contains cross”)
    ia = df.get("intended_actions")
    if ia is not None:
        ia = ia.astype(str).str.lower().str.strip()
        true_label = ia.str.contains("cross", regex=False).astype(int)
    else:
        true_label = 0

    # ID piéton = track_id si présent
    ped_id = df.get("track_id")
    ped_id = (np.arange(len(df)).astype(str) if ped_id is None else ped_id.astype(str))

    out = pd.DataFrame({
        "ped_id": ped_id,
        "distance_m": dist,
        "real_height_cm": real_h,
        "true_label": true_label,
        "pos_x": df["pos_x"],
        "pos_y": df["pos_y"],
        "pos_z": df["pos_z"],
    })
    return out.reset_index(drop=True)

def parse_label3d_vehicles(path: Path) -> pd.DataFrame:
    """Retourne un DataFrame véhicules 3D : pos + type."""
    df = read_csv(path)
    if df is None or df.empty:
        return pd.DataFrame(columns=["veh_id","type","pos_x","pos_y","pos_z"])

    df = _normalize_label3d_columns(df)

    if "labels" not in df.columns:
        return pd.DataFrame(columns=["veh_id","type","pos_x","pos_y","pos_z"])

    lab = df["labels"].astype(str).str.lower().str.strip()
    mask = lab.isin(["vehicle","car","bus","truck","bicycle","motorcycle","motorbike","motorcyclist","van","suv"])
    df = df[mask].copy()
    if df.empty:
        return pd.DataFrame(columns=["veh_id","type","pos_x","pos_y","pos_z"])

    for c in ["pos_x","pos_y","pos_z"]:
        if c not in df.columns:
            return pd.DataFrame(columns=["veh_id","type","pos_x","pos_y","pos_z"])
        df[c] = pd.to_numeric(df[c], errors="coerce")

    veh_id = df.get("track_id")
    veh_id = (np.arange(len(df)).astype(str) if veh_id is None else veh_id.astype(str))

    out = pd.DataFrame({
        "veh_id": veh_id,
        "type": df.get("labels").astype(str),
        "pos_x": df["pos_x"],
        "pos_y": df["pos_y"],
        "pos_z": df["pos_z"],
    })
    return out.reset_index(drop=True)

# =============================================================================
# Odom -> vitesse ego (km/h)
# =============================================================================
def read_odom_pose(path: Path) -> Optional[Tuple[float, float, float]]:
    """Lit odom_*.txt et renvoie (x,y,z) ou None si impossible."""
    if not path.exists():
        return None

    try:
        df = pd.read_csv(path, engine="python", header=None)
        if df.shape[1] >= 3:
            row = df.iloc[0]
            return (float(row[0]), float(row[1]), float(row[2]))
    except Exception:
        pass

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
    """Calcule une vitesse ego (km/h) par frame à partir de la trajectoire odom."""
    poses: Dict[int, Optional[Tuple[float,float,float]]] = {}
    for fid in frame_ids:
        p = paths_for_frame(sdir, fid)["odom"]
        poses[fid] = read_odom_pose(p) if p.exists() else None

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
        if pose is not None:
            prev_pose = pose
            prev_fid = fid

    # backfill vitesse frame 0 si manquante
    if frame_ids:
        first_fid = frame_ids[0]
        if vmap.get(first_fid) is None:
            for fid in frame_ids[1:]:
                if vmap.get(fid) is not None:
                    vmap[first_fid] = vmap[fid]
                    break

    return vmap

# =============================================================================
# Modèle (optionnel) : import dynamique
# =============================================================================
def load_model(model_path: Path):
    """Charge la fonction pedestrian_behavior_model(...) depuis MODEL_PATH."""
    spec = importlib.util.spec_from_file_location("pedestrian_behavior_model", str(model_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "pedestrian_behavior_model"):
        raise AttributeError("pedestrian_behavior_model(...) introuvable dans le module.")
    return module.pedestrian_behavior_model

# =============================================================================
# Helpers overlay supplémentaires (polygones, matching feu↔passage, etc.)
# =============================================================================
def draw_polygon_with_text(img: Image.Image, polygon: List[Tuple[float,float]], lines: List[str],
                           fill_rgba=(0, 200, 255, 60), outline=(0,200,255), text_bg=(0,0,0,160)):
    """Dessine un polygone (ex: passage piéton) + un label texte."""
    draw = ImageDraw.Draw(img, "RGBA")
    draw.polygon(polygon, fill=fill_rgba, outline=outline+(255,))

    cx = sum(p[0] for p in polygon) / len(polygon)
    cy = sum(p[1] for p in polygon) / len(polygon)

    font = load_font(BOX_FONT_SIZE)
    text = "\n".join(lines)
    tw, th = _measure_text(draw, text, font, multiline=True, spacing=2)

    padding = 4
    x0, y0 = cx - tw/2 - padding, cy - th - 10 - 2*padding
    x1, y1 = x0 + tw + 2*padding, y0 + th + 2*padding

    Wimg, Himg = img.size
    x0 = max(0, min(x0, Wimg-1)); y0 = max(0, min(y0, Himg-1))
    x1 = max(0, min(x1, Wimg-1)); y1 = max(0, min(y1, Himg-1))

    draw.rectangle([x0,y0,x1,y1], fill=text_bg)
    draw.multiline_text((x0+padding, y0+padding), text, fill=(255,255,255,255), font=font, spacing=2)

def _box_center(box: dict) -> Tuple[float,float]:
    """Centre (x,y) d’une bbox."""
    return (float(box["left"]) + float(box["width"]) * 0.5,
            float(box["top"])  + float(box["height"]) * 0.5)

def _tl_color_rgba(state: str) -> Tuple[int,int,int,int]:
    """Couleur RGBA pour l’état du feu."""
    s = (state or "unknown").lower()
    if s == "red":   return (255,   0,   0, 180)
    if s == "green": return (  0, 200,   0, 180)
    if s == "amber": return (255, 165,   0, 180)
    if s == "off":   return (180, 180, 180, 180)
    return (120,120,120,180)

def match_crosswalk_to_light(crosswalk: dict, lights: List[dict]) -> Optional[dict]:
    """Associe un passage piéton au feu le plus proche (distance 2D entre centres)."""
    if not lights:
        return None
    if "polygon" in crosswalk:
        pts = crosswalk["polygon"]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
    else:
        cx, cy = _box_center(crosswalk["box"])

    best = None
    bestd2 = float("inf")
    for L in lights:
        lx, ly = _box_center(L["box"])
        d2 = (lx-cx)*(lx-cx) + (ly-cy)*(ly-cy)
        if d2 < bestd2:
            bestd2 = d2; best = L
    return best

# =============================================================================
# Overlay : vitesses véhicules (par piste) + conversion ego->monde si nécessaire
# =============================================================================
def precompute_vehicle_speeds(sdir: Path, frame_ids: List[int]) -> Dict[int, Dict[str, Optional[float]]]:
    """
    Calcule une vitesse “par véhicule” (track) :
    - vitesse = distance totale XY / temps total de la piste
    - même vitesse assignée à toutes les frames de la piste
    Retour : {frame_id: {veh_id: speed_kmh}}
    """
    tracks, maj_state = _build_vehicle_tracks(sdir, frame_ids)
    out: Dict[int, Dict[str, Optional[float]] ] = {fid: {} for fid in frame_ids}

    for vid, seq in tracks.items():
        if len(seq) < 2:
            continue
        t0 = seq[0][0]; t1 = seq[-1][0]
        dt_s = (t1 - t0) / float(FRAMERATE_HZ)

        # règles robustes (durée min, déplacement min, clamp outliers, etc.)
        if dt_s < SPEED_MIN_TIME_S:
            speed_kmh = 0.0
        else:
            total_m = 0.0
            for i in range(1, len(seq)):
                dx = seq[i][1] - seq[i-1][1]
                dy = seq[i][2] - seq[i-1][2]
                total_m += math.hypot(dx, dy)

            if total_m < SPEED_MIN_MOVE_M:
                speed_kmh = 0.0
            else:
                v_ms = min(total_m / max(1e-9, dt_s), SPEED_MAX_MPS)
                if maj_state.get(vid, "") in SPEED_ZERO_IF_STATE:
                    v_ms = 0.0
                speed_kmh = v_ms * 3.6

        for fid, _, _ in seq:
            out.setdefault(fid, {})[vid] = speed_kmh

    return out

def read_odom_pose_with_yaw(path: Path) -> Optional[Tuple[float, float, float, float]]:
    """Lit (x,y,z,yaw) depuis odom si possible, sinon yaw=0.0."""
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, engine="python", header=None)
        if df.shape[1] >= 6:
            row = df.iloc[0]
            return (float(row[0]), float(row[1]), float(row[2]), float(row[5]))
        if df.shape[1] >= 3:
            row = df.iloc[0]
            return (float(row[0]), float(row[1]), float(row[2]), 0.0)
    except Exception:
        pass
    try:
        line = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()[0]
        tmp = line.replace(',', ' ').replace(';', ' ')
        parts = tmp.split()
        if len(parts) >= 6:
            x, y, z, roll, pitch, yaw = map(float, parts[:6])
            return (x, y, z, yaw)
        if len(parts) >= 3:
            x, y, z = map(float, parts[:3])
            return (x, y, z, 0.0)
    except Exception:
        pass
    return None

def _rot2d(yaw: float) -> Tuple[float,float,float,float]:
    """Matrice de rotation 2D (yaw)."""
    c, s = math.cos(yaw), math.sin(yaw)
    return c, -s, s, c

def ego_to_world(x_e: float, y_e: float, yaw: float, tx: float, ty: float) -> Tuple[float, float]:
    """Transforme un point ego (x_e,y_e) en monde via yaw + translation (tx,ty)."""
    c, m, s, c2 = _rot2d(yaw)
    x_w = c * x_e + m * y_e + tx
    y_w = s * x_e + c2 * y_e + ty
    return x_w, y_w

def _build_odom_map(sdir: Path, frame_ids: List[int]) -> Dict[int, Optional[Tuple[float,float,float,float]]]:
    """Cache odom (x,y,z,yaw) pour toutes les frames."""
    od = {}
    for fid in frame_ids:
        p = paths_for_frame(sdir, fid)["odom"]
        od[fid] = read_odom_pose_with_yaw(p) if p.exists() else None
    return od

def _build_vehicle_tracks(sdir: Path, frame_ids: List[int]) -> Tuple[Dict[str, List[Tuple[int,float,float]]], Dict[str, str]]:
    """
    Construit les pistes véhicules en XY monde :
    - si LOKI_POS_FRAME == 'ego' : conversion ego->monde via odom (yaw + translation)
    - récupère aussi un état “majoritaire” vehicle_state par track (optionnel)
    """
    odmap = _build_odom_map(sdir, frame_ids) if LOKI_POS_FRAME.lower() == 'ego' else {}
    tracks: Dict[str, List[Tuple[int,float,float]]] = {}
    states: Dict[str, List[str]] = {}

    for fid in frame_ids:
        p3d = paths_for_frame(sdir, fid)["label3d"]
        if not p3d.exists():
            continue

        dfv = parse_label3d_vehicles(p3d)
        if dfv.empty:
            continue

        # lecture brute pour récupérer vehicle_state par track_id (si présent)
        raw = read_csv(p3d)
        vs_map: Dict[str, str] = {}
        if raw is not None and not raw.empty:
            raw = _normalize_label3d_columns(raw)
            if "track_id" in raw.columns and "vehicle_state" in raw.columns:
                for _, r in raw.iterrows():
                    try:
                        vs_map[str(r["track_id"])] = str(r["vehicle_state"]) if not pd.isna(r["vehicle_state"]) else ""
                    except Exception:
                        pass

        od = odmap.get(fid) if odmap else None

        for _, row in dfv.iterrows():
            vid = row["veh_id"]
            x, y = float(row["pos_x"]), float(row["pos_y"])

            # conversion repère ego -> monde si nécessaire
            if LOKI_POS_FRAME.lower() == 'ego':
                if od is None:
                    continue
                tx, ty, tz, yaw = od
                x, y = ego_to_world(x, y, yaw, tx, ty)

            tracks.setdefault(vid, []).append((fid, x, y))

            st = vs_map.get(vid, "")
            if st:
                states.setdefault(vid, []).append(st)

    for vid in tracks:
        tracks[vid].sort(key=lambda t: t[0])

    # état majoritaire
    maj_state: Dict[str, str] = {}
    for vid, arr in states.items():
        if not arr:
            continue
        vals, counts = np.unique(arr, return_counts=True)
        maj_state[vid] = str(vals[int(np.argmax(counts))])

    return tracks, maj_state

# =============================================================================
# Render overlay : produit une image PIL annotée pour une frame donnée
# =============================================================================
def render_overlay(base_dir: Path, scenario_id: int, frame_id: int,
                   weather_cache: Dict[int, Optional[str]],
                   speed_map_cache: Dict[int, Dict[int, Optional[float]]],
                   show_model: bool, model_fn=None) -> Optional[Image.Image]:
    """
    Construit l’image overlay :
    - charge image
    - récupère météo (cache par scénario)
    - récupère vitesses ego (cache par scénario) et vitesses véhicules (cache interne)
    - parse label2d (boîtes) + label3d (infos métriques)
    - dessine header + boîtes + textes
    - option : prédictions modèle (adj / noadj) pour chaque piéton
    """
    sdir = scenario_dir(base_dir, scenario_id)
    pths = paths_for_frame(sdir, frame_id)

    if not pths["image"].exists():
        log.warning(f"Image manquante: {pths['image']}")
        return None

    # Météo (cache par scenario)
    if scenario_id not in weather_cache:
        weather_cache[scenario_id] = find_weather_no_heuristic(sdir)
    weather = weather_cache[scenario_id]

    # Vitesse ego (cache par scenario : calcul sur toutes les frames du scénario)
    if scenario_id not in speed_map_cache:
        fids = list_frames(sdir)
        speed_map_cache[scenario_id] = speeds_from_odom(sdir, fids)
    v_kmh = speed_map_cache[scenario_id].get(frame_id, None)

    # Cache interne vitesses véhicules
    if not hasattr(render_overlay, "veh_speed_cache"):
        render_overlay.veh_speed_cache = {}
    veh_speed_cache = render_overlay.veh_speed_cache

    if scenario_id not in veh_speed_cache:
        fids = list_frames(sdir)
        veh_speed_cache[scenario_id] = precompute_vehicle_speeds(sdir, fids)
    veh_speed_map = veh_speed_cache[scenario_id].get(frame_id, {})

    # Parse 2D (boîtes)
    boxes_ped = parse_label2d_pedestrians(pths["label2d"]) if pths["label2d"].exists() else {}
    boxes_veh = parse_label2d_vehicles(pths["label2d"]) if pths["label2d"].exists() else {}

    # Parse 3D (infos métriques)
    df3d_ped  = parse_label3d_pedestrians(pths["label3d"]) if pths["label3d"].exists() else pd.DataFrame()
    df3d_veh  = parse_label3d_vehicles(pths["label3d"]) if pths["label3d"].exists() else pd.DataFrame()

    ped_idx = df3d_ped.set_index("ped_id") if not df3d_ped.empty else None
    veh_idx = df3d_veh.set_index("veh_id") if not df3d_veh.empty else None

    # Image de base
    img = Image.open(pths["image"]).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    font = load_font(HEADER_FONT_SIZE)

    # Header info en haut à gauche
    header_lines = [
        f"scenario_{scenario_id:03d}  frame_{frame_id:04d}",
        f"Weather: {weather}" if weather else "Weather: Not found",
        f"Ego speed: {v_kmh:.1f} km/h" if v_kmh is not None else "Ego speed: N/A",
        f"Peds: {len(boxes_ped)}  Veh: {len(boxes_veh)}"
    ]
    header_text = "   ".join(header_lines)
    tw, th = _measure_text(draw, header_text, font)
    draw.rectangle([0,0, tw+16, th+12], fill=(0,0,0,160))
    draw.text((8,6), header_text, fill=(255,255,255,255), font=font)

    # Prépare positions 3D des piétons pour calculer distance véhicule->piéton le plus proche
    ped_positions = []
    if ped_idx is not None:
        for pid, r in ped_idx.iterrows():
            try:
                ped_positions.append((pid, (float(r["pos_x"]), float(r["pos_y"]), float(r["pos_z"])) ))
            except Exception:
                continue

    # ------------------------------
    # Véhicules : overlay boîtes + vitesse + dmin->ped + (option) ligne
    # ------------------------------
    for vid, obj in boxes_veh.items():
        vbox = obj["box"]
        vtype = obj.get("type", "veh")

        speed_txt = "N/A"
        if vid in veh_speed_map:
            speed_txt = f"{veh_speed_map[vid]:.1f} km/h"

        # distance 3D au piéton le plus proche (si infos 3D véhicules disponibles)
        dmin_txt = "N/A"
        nearest_pid = None
        if veh_idx is not None and vid in veh_idx.index and ped_positions:
            vx, vy, vz = float(veh_idx.loc[vid, "pos_x"]), float(veh_idx.loc[vid, "pos_y"]), float(veh_idx.loc[vid, "pos_z"])
            dmin = float("inf")
            for pid, (px,py,pz) in ped_positions:
                d = math.sqrt((vx-px)**2 + (vy-py)**2 + (vz-pz)**2)
                if d < dmin:
                    dmin = d
                    nearest_pid = pid
            if dmin < float("inf"):
                dmin_txt = f"{dmin:.1f} m"

        lines = [f"VEH {vtype}", f"speed: {speed_txt}", f"d→ped: {dmin_txt}"]
        draw_box_with_text(img, vbox, lines, color=(255,128,0))

        # Ligne 2D véhicule↔piéton (si on retrouve la boîte 2D du piéton le plus proche)
        if DRAW_LINK_LINE and nearest_pid is not None:
            try:
                vx2d = (vbox["left"] + vbox["width"]*0.5, vbox["top"] + vbox["height"]*0.5)
                pbox = boxes_ped.get(str(nearest_pid)) or boxes_ped.get(nearest_pid)
                if pbox:
                    px2d = (pbox["left"] + pbox["width"]*0.5, pbox["top"] + pbox["height"]*0.5)
                    draw.line([vx2d, px2d], fill=(255,255,0,200), width=2)
            except Exception:
                pass

    # ------------------------------
    # Piétons : overlay boîtes + dist/height/GT + (option) prédictions modèle
    # ------------------------------
    for ped_id, box in boxes_ped.items():
        dist = height_cm = true_label = None
        if ped_idx is not None and ped_id in ped_idx.index:
            r = ped_idx.loc[ped_id]
            dist = float(r["distance_m"]) if pd.notna(r["distance_m"]) else None
            height_cm = float(r["real_height_cm"]) if pd.notna(r["real_height_cm"]) else None
            true_label = int(r["true_label"]) if pd.notna(r["true_label"]) else None

        lines = [
            f"ID: {str(ped_id)[:8]}",
            f"dist: {dist:.2f} m" if dist is not None else "dist: N/A",
            f"height: {height_cm:.0f} cm" if height_cm is not None else "height: N/A",
            f"GT crossing: {true_label}" if true_label is not None else "GT crossing: N/A",
        ]

        # Option : afficher prédiction modèle (adj=True / adj=False)
        if show_model and (model_fn is not None):
            try:
                pred_adj   = model_fn(weather if weather else None,
                                      height_cm if height_cm is not None else None,
                                      v_kmh if v_kmh is not None else None,
                                      dist if dist is not None else None,
                                      True)
                pred_noadj = model_fn(weather if weather else None,
                                      height_cm if height_cm is not None else None,
                                      v_kmh if v_kmh is not None else None,
                                      dist if dist is not None else None,
                                      False)
            except Exception as e:
                log.warning(f"Erreur modèle (ped={ped_id}): {e}")
                pred_adj = pred_noadj = None

            lines += [
                f"pred(adj T): {pred_adj}"   if pred_adj is not None else "pred(adj T): N/A",
                f"pred(adj F): {pred_noadj}" if pred_noadj is not None else "pred(adj F): N/A",
            ]

        draw_box_with_text(img, box, lines, color=(0,255,0))

    return img

# =============================================================================
# Viewer interactif (OpenCV)
# =============================================================================
def run_viewer(base_dir: Path, start_scenario: int, start_frame: int):
    """Boucle interactive OpenCV : navigation scénarios/frames + toggle modèle."""
    scenarios = list_scenarios(base_dir)
    if not scenarios:
        print("Aucun scénario trouvé.")
        return

    # Chargement modèle (optionnel)
    try:
        model_fn = load_model(MODEL_PATH)
    except Exception:
        model_fn = None
        log.info("Modèle non chargé (ce n'est pas bloquant).")

    show_model = RUN_MODEL_DEFAULT

    # Caches pour éviter de recalculer à chaque frame
    weather_cache: Dict[int, Optional[str]] = {}
    speed_map_cache: Dict[int, Dict[int, Optional[float]]] = {}

    # Position scénario initiale
    if start_scenario in scenarios:
        sidx = scenarios.index(start_scenario)
    else:
        sidx = 0

    # Fenêtre OpenCV
    win = "LOKI Viewer"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    while True:
        sid = scenarios[sidx]
        sdir = scenario_dir(base_dir, sid)
        frames = list_frames(sdir)

        if not frames:
            print(f"Pas d'images dans scenario_{sid:03d}.")
            sidx = (sidx + 1) % len(scenarios)
            continue

        # Position frame initiale au début du scénario
        if start_frame in frames:
            fidx = frames.index(start_frame)
            start_frame = frames[0]
        else:
            fidx = 0

        while True:
            fid = frames[fidx]

            # Rendu overlay PIL -> conversion BGR OpenCV
            try:
                pil_img = render_overlay(base_dir, sid, fid, weather_cache, speed_map_cache, show_model, model_fn)
            except Exception as e:
                log.error(f"Erreur render_overlay sur scenario_{sid:03d} frame_{fid:04d}: {e}")
                pil_img = None

            if pil_img is None:
                # image indisponible : affiche un écran placeholder
                disp = np.zeros((720, 1280, 3), dtype=np.uint8)
                cv2.putText(disp, f"scenario_{sid:03d} frame_{fid:04d} (image indisponible)",
                            (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,0,255), 2, cv2.LINE_AA)
            else:
                disp = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

            # Barre d’aide en bas
            helpbar = "j/k=±1  J/K=±10  n/p=scenario ±1  m=toggle model  h=help  q=quit"
            cv2.rectangle(disp, (0, disp.shape[0]-30), (disp.shape[1], disp.shape[0]), (0,0,0), -1)
            cv2.putText(disp, helpbar, (10, disp.shape[0]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1, cv2.LINE_AA)

            # Zoom d’affichage (ne change pas le traitement, juste l’écran)
            SCALE = 1.5
            disp = cv2.resize(disp, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST)

            cv2.imshow(win, disp)
            key = cv2.waitKey(0) & 0xFF

            # Contrôles clavier
            if key in (ord('q'), 27):  # q ou ESC
                cv2.destroyAllWindows()
                return
            elif key == ord('h'):
                print("\nContrôles: j/k=±1  J/K=±10  n/p=scenario ±1  m=toggle model  q=quit\n")
            elif key == ord('m'):
                show_model = not show_model
            elif key == ord('j') or key == ord(' '):
                fidx = min(fidx + 1, len(frames) - 1)
            elif key == ord('k'):
                fidx = max(fidx - 1, 0)
            elif key == ord('J'):
                fidx = min(fidx + 10, len(frames) - 1)
            elif key == ord('K'):
                fidx = max(fidx - 10, 0)
            elif key == ord('n'):
                sidx = (sidx + 1) % len(scenarios)
                break
            elif key == ord('p'):
                sidx = (sidx - 1) % len(scenarios)
                break
            else:
                pass

if __name__ == "__main__":
    run_viewer(BASE_DIR, START_SCENARIO, START_FRAME)
