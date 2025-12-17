# -*- coding: utf-8 -*-
"""
crossing_decision.py (nuScenes)
==============================

Objectif
--------
Exporter les entrées/sorties de ton modèle sur nuScenes sous forme de CSV,
et (optionnellement) produire des frames annotées + une vidéo **par piéton**.

Différence clé vs script nuScenes "simple"
------------------------------------------
Ici, on ne prend pas systématiquement l’ego-vehicle comme véhicule de référence.
On applique une règle : si un autre véhicule non-ego est plus pertinent (piéton devant lui, moving,
et plus proche que l’ego), alors on utilise sa vitesse + distance pour alimenter le modèle.

Règle (sélection véhicule de référence)
---------------------------------------
Pour un piéton donné dans une frame :
1) On cherche parmi les objets "vehicle.*" celui qui a l’attribut 'vehicle.moving'
2) Le piéton doit être DEVANT ce véhicule (longitudinal > 0 dans le repère du véhicule)
3) On prend le plus proche (distance XY au sol)
4) On ne l’utilise que si sa distance est réellement plus faible que la distance ego→piéton
   (d_veh < d_ego - eps), sinon fallback ego.

Filtrage des frames (pour CSV et prédiction)
--------------------------------------------
- Optionnel : ne garder que les piétons devant l’ego (ahead)
- Optionnel : ne garder que les piétons visibles dans CAM_FRONT avec marge (évite bords/occlusions)
- Toujours strict : ignorer si vitesse/distance/taille/true_label manquent.

GT "crossing" strict (identique au script précédent)
----------------------------------------------------
true_label = 1 si (on_road == True) ET (ahead == True), sinon 0.
Si on_road est inconnu (shapely absent / map invalide) -> frame ignorée.

Sorties
-------
- 2 CSV par instance_token : adj / no-adj
- (option) images annotées : 1 image par frame et par piéton
- (option) vidéo mp4 : 1 vidéo par piéton (concaténation des frames)
"""

import os
import math
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set

import numpy as np
import pandas as pd
from tqdm import tqdm

# ===================== CONFIG =====================
# nuScenes racine : doit contenir v1.0-mini/, maps/, can_bus/ (selon setup)
DATAROOT = r"E:\crossing-model\main_experiment\model_validation\datasets\nuscenes"
VERSION  = "v1.0-mini"
MODEL_PATH = Path(r"E:\crossing-model\main_experiment\model_datas\CNRS_behavior_model.py")

# Dossiers résultats CSV (adj / no-adj)
OUT_DIR_ADJ   = Path(r"E:\crossing-model\main_experiment\model_validation\evaluation\model_result_adj_NUSCENES_20kmh_rule_other_vehicle_scenario\set")
OUT_DIR_NOADJ = Path(r"E:\crossing-model\main_experiment\model_validation\evaluation\model_result_no_adj_NUSCENES_20kmh_rule_other_vehicle_scenario\set")
OUT_DIR_ADJ.mkdir(parents=True, exist_ok=True)
OUT_DIR_NOADJ.mkdir(parents=True, exist_ok=True)

# -------- VISUALISATION / VIDEO --------
SAVE_VIS = True                 # False -> aucun export images/vidéos (CSV seulement)
VIS_DIR = Path(r"E:\crossing-model\main_experiment\model_validation\viz\crossing_decision_frames_20km_rule")
MAKE_VIDEO = True               # True -> construit une vidéo MP4 **par piéton**
VIDEO_FPS = 5
VIS_DIR.mkdir(parents=True, exist_ok=True)

# -------- RÈGLE : activer/désactiver la sélection d'un "autre véhicule" --------
USE_OTHER_VEHICLE_RULE = True   # False -> tout au ego

# -------- FILTRES : ce qui entre réellement dans le dataset d’évaluation --------
PRED_ONLY_AHEAD = True          # si True : on ne conserve que les piétons devant l’ego
PRED_REQUIRE_VISIBLE = True     # si True : on exige que le piéton soit projetable dans CAM_FRONT (avec marge)
PRED_MARGIN_PX = 30             # marge aux bords (pixels)

# -------- Garde-fou : l'autre véhicule doit être significativement plus proche --------
VEH_MUST_BE_CLOSER_THAN_EGO = True
VEH_CLOSER_EPS_M = 0.5          # impose : d_veh < d_ego - 0.5m

# -------- Météo --------
WEATHER_DEFAULT = "clear"
NIGHT_CSV_PATH = Path(r"E:\crossing-model\main_experiment\model_validation\datasets\nuscenes\nuscenes_camfront_weather_night.csv")

# -------- Hauteur --------
# Ici : si la hauteur annotée (size[2]) est hors bornes, fallback sur une moyenne par location.
LOC_MEAN_HEIGHT_CM = {
    "boston-seaport":             169.0,
    "singapore-hollandvillage":   165.0,
    "singapore-onenorth":         165.0,
    "singapore-queenstown":       165.0,
}
HEIGHT_MIN_CM = 150.0
HEIGHT_MAX_CM = 200.0

# ===================== LOG & DEVKIT =====================
import cv2
from nuscenes.nuscenes import NuScenes
from nuscenes.map_expansion.map_api import NuScenesMap
from nuscenes.utils.data_classes import Box
from nuscenes.utils.geometry_utils import view_points
from pyquaternion import Quaternion

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("nusc_export")

# -------- CAN bus --------
# Sert à récupérer une vitesse ego plus fiable que Δpose/Δt
try:
    from nuscenes.can_bus.can_bus_api import NuScenesCanBus
    HAS_CAN = True
except Exception:
    HAS_CAN = False
    log.warning("CAN bus API indisponible : on utilisera Δpose/Δt si besoin.")

# -------- Shapely --------
# Indispensable ici si on veut produire un GT strict basé sur "on_road"
try:
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from shapely.prepared import prep
    HAS_SHAPELY = True
except Exception:
    HAS_SHAPELY = False
    log.warning("Shapely indisponible : impossible d'évaluer 'on_road' -> les frames seront ignorées.")

# ===================== Modèle =====================
import importlib.util

def load_model(model_path: Path):
    """Import dynamique d’un fichier .py contenant pedestrian_behavior_model(...)."""
    spec = importlib.util.spec_from_file_location("pedestrian_behavior_model", str(model_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "pedestrian_behavior_model"):
        raise AttributeError("pedestrian_behavior_model(...) introuvable.")
    return module.pedestrian_behavior_model

ped_model = load_model(MODEL_PATH)

def to_bool_label(v):
    """Normalise une prédiction en 'True'/'False' (string) ou None."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"true","1","yes","y","t"}:
        return "True"
    if s in {"false","0","no","n","f"}:
        return "False"
    try:
        return "True" if float(s) >= 0.5 else "False"
    except:
        return "True" if bool(v) else "False"

def _norm_path(p: str) -> str:
    """Normalise un chemin pour matching robustes (night CSV)."""
    p = str(p).strip().strip('"').strip("'")
    try:
        return os.path.normcase(os.path.normpath(p))
    except Exception:
        return p

def _load_night_sets(csv_path: Path) -> Tuple[Set[str], Set[str]]:
    """
    Charge le CSV listant les images "night".
    Retourne (full_paths_set, basenames_set).
    """
    paths, bases = set(), set()
    try:
        df = pd.read_csv(csv_path)
        if "image_path" not in df.columns:
            log.warning(f"CSV nuit sans colonne 'image_path' : {csv_path}")
            return paths, bases
        for p in df["image_path"].dropna().astype(str):
            npth = _norm_path(p)
            paths.add(npth)
            bases.add(os.path.basename(npth))
        log.info(f"NIGHT CSV: {len(paths)} images chargées depuis {csv_path}")
    except Exception as e:
        log.warning(f"Impossible de lire le CSV nuit ({csv_path}): {e}")
    return paths, bases

def finite(x) -> bool:
    """True si convertible en float et fini."""
    try:
        return (x is not None) and math.isfinite(float(x))
    except Exception:
        return False

# ===================== Géométrie / Projections =====================
def quat_wxyz_to_R(qw, qx, qy, qz) -> np.ndarray:
    """Quaternion (w,x,y,z) -> matrice de rotation 3x3."""
    w, x, y, z = float(qw), float(qx), float(qy), float(qz)
    xx, yy, zz = x*x, y*y, z*z
    xy, xz, yz = x*y, x*z, y*z
    wx, wy, wz = w*x, w*y, w*z
    return np.array([
        [1-2*(yy+zz),   2*(xy-wz),   2*(xz+wy)],
        [  2*(xy+wz), 1-2*(xx+zz),   2*(yz-wx)],
        [  2*(xz-wy),   2*(yz+wx), 1-2*(xx+yy)]
    ], dtype=float)

def long_lat_from_global(ped_xyz: np.ndarray, ego_t: np.ndarray, ego_q: List[float]) -> Tuple[float, float]:
    """
    (longitudinal, latéral) du piéton dans le repère ego.
    Utilisé pour (ahead) et distance ego↔piéton.
    """
    v = ped_xyz - ego_t
    R_ego = quat_wxyz_to_R(*ego_q)
    v_ego = R_ego.T @ v
    return float(v_ego[0]), float(v_ego[1])

def long_lat_from_ref(point_xyz: np.ndarray, ref_t: np.ndarray, ref_q: List[float]) -> Tuple[float, float]:
    """
    (longitudinal, latéral) d’un point dans le repère d’un véhicule "ref" non-ego.
    Sert à tester "piéton devant véhicule" (long>0).
    """
    v = point_xyz - ref_t
    R_ref = quat_wxyz_to_R(*ref_q)
    v_ref = R_ref.T @ v
    return float(v_ref[0]), float(v_ref[1])

def project_global_to_image(P_glob: np.ndarray, R_cam_glob: np.ndarray, t_cam_glob: np.ndarray,
                            K: np.ndarray, W: int, H: int):
    """
    Projette un point global (XYZ) dans l'image CAM_FRONT.
    Retourne (u,v) pixels si point devant la caméra et dans les bornes image, sinon None.
    """
    X = P_glob - t_cam_glob
    p_cam = R_cam_glob.T @ X
    if p_cam[2] <= 0:
        return None
    u = K[0,0]*(p_cam[0]/p_cam[2]) + K[0,2]
    v = K[1,1]*(p_cam[1]/p_cam[2]) + K[1,2]
    if not (0 <= u < W and 0 <= v < H):
        return None
    return (int(u), int(v))

def draw_text_bg(img, text, org, font_scale=0.6, color=(255,255,255), bg=(0,0,0), thickness=1):
    """Helper overlay texte avec rectangle de fond (lisible sur image)."""
    (w,h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    x,y = org
    cv2.rectangle(img, (x, y-h-baseline-4), (x+w+6, y+4), bg, -1)
    cv2.putText(img, text, (x+3, y-2), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)
    return (w,h)

def is_inside_with_margin(pt: Optional[Tuple[int,int]], W: int, H: int, margin: int) -> bool:
    """Vérifie que le point projeté est à l'intérieur, en laissant une marge aux bords."""
    if pt is None:
        return False
    u, v = pt
    return (margin <= u < (W - margin)) and (margin <= v < (H - margin))

# ===================== Drivable / Road cache =====================
class RoadUnionCache:
    """
    Union shapely "route" = drivable_area ∪ road_segment ∪ lane.
    carpark_area est exclu (choix volontaire pour un GT plus "route-like").
    """
    def __init__(self, dataroot: str):
        self.dataroot = dataroot
        self.cache: Dict[str, Any] = {}

    def _get_polygon(self, nmap, token):
        if token is None:
            return None
        if hasattr(nmap, "get_polygon"):
            try:
                return nmap.get_polygon(token)
            except Exception:
                pass
        if hasattr(nmap, "extract_polygon"):
            try:
                return nmap.extract_polygon(token)
            except Exception:
                pass
        return None

    def _collect_layer(self, nmap, layer: str) -> List[Any]:
        """Collecte tous les polygones d'une couche (layer) nuScenesMap."""
        polys: List[Any] = []
        if not hasattr(nmap, layer):
            return polys
        for rec in getattr(nmap, layer):
            tok_single = rec.get("polygon_token")
            if tok_single:
                poly = self._get_polygon(nmap, tok_single)
                if poly is not None:
                    polys.append(poly)
                continue
            tok_list = rec.get("polygon_tokens")
            if tok_list:
                for tok in tok_list:
                    poly = self._get_polygon(nmap, tok)
                    if poly is not None:
                        polys.append(poly)
        return polys

    def get_prepared_union(self, location: str):
        """Construit et met en cache la géométrie union pour la location."""
        if not HAS_SHAPELY:
            return None
        if location in self.cache:
            return self.cache[location]
        try:
            nmap = NuScenesMap(dataroot=self.dataroot, map_name=location)
        except Exception as e:
            log.warning(f"[{location}] NuScenesMap init failed: {e}")
            self.cache[location] = None
            return None

        layers = ["drivable_area", "road_segment", "lane"]
        polys: List[Any] = []
        for lyr in layers:
            polys += self._collect_layer(nmap, lyr)

        if not polys:
            log.warning(f"[{location}] Aucun polygone (drivable/road/lane) trouvé.")
            self.cache[location] = None
            return None

        try:
            merged = unary_union(polys)
            self.cache[location] = prep(merged)
            log.info(f"[{location}] union routes: {len(polys)} polygons (OK).")
            return self.cache[location]
        except Exception as e:
            log.warning(f"[{location}] union shapely échouée: {e}")
            self.cache[location] = None
            return None

    def is_on_road(self, location: str, x: float, y: float) -> Optional[bool]:
        """Point-in-road. Retourne None si shapely/map indisponibles."""
        if not HAS_SHAPELY:
            return None
        prep_geom = self.get_prepared_union(location)
        if prep_geom is None:
            return None
        try:
            p = Point(x, y)
            return bool(prep_geom.contains(p) or prep_geom.touches(p))
        except Exception:
            return None

# ===================== Index & vitesses ego =====================
def build_scene_order(nusc: NuScenes) -> Dict[str, List[str]]:
    """scene_token -> liste ordonnée de sample_token."""
    order = {}
    for scene in nusc.scene:
        toks = []
        cur = scene['first_sample_token']
        while cur:
            toks.append(cur)
            cur = nusc.get('sample', cur)['next']
        order[scene['token']] = toks
    return order

def index_sd_by_channel(nusc: NuScenes) -> Dict[Tuple[str,str], str]:
    """(sample_token, channel) -> sample_data_token keyframe."""
    idx = {}
    for sd in nusc.sample_data:
        if not sd.get('is_key_frame', False):
            continue
        cs = nusc.get('calibrated_sensor', sd['calibrated_sensor_token'])
        chan = nusc.get('sensor', cs['sensor_token'])['channel']
        idx[(sd['sample_token'], chan)] = sd['token']
    return idx

def ego_pose_by_sample(nusc: NuScenes, sd_by_chan: Dict[Tuple[str,str], str], prefer_channel="LIDAR_TOP"):
    """sample_token -> (ego_translation, ego_quat, timestamp)."""
    out = {}
    for sample in nusc.sample:
        s_tok = sample['token']
        sd_tok = sd_by_chan.get((s_tok, prefer_channel))

        # fallback si pas de lidar keyframe
        if sd_tok is None:
            for alt in ("CAM_FRONT","CAM_FRONT_LEFT","CAM_FRONT_RIGHT","CAM_BACK","CAM_BACK_LEFT","CAM_BACK_RIGHT"):
                sd_tok = sd_by_chan.get((s_tok, alt))
                if sd_tok is not None:
                    break
            if sd_tok is None:
                continue

        sd = nusc.get('sample_data', sd_tok)
        ep = nusc.get('ego_pose', sd['ego_pose_token'])
        out[s_tok] = (np.array(ep['translation'], float), ep['rotation'], ep['timestamp'])
    return out

# ---- vitesse CAN (ego) + fallback Δpose/Δt (ego) ----
# (Identique au script précédent, juste recopié ici)

def _nn_assign_times(sample_ts_us: np.ndarray, can_ts_us: np.ndarray, can_vals: np.ndarray, max_tdiff_s: float):
    """NN assign CAN->sample si |Δt|<=max_tdiff_s, sinon NaN."""
    if len(can_ts_us) == 0:
        return np.full_like(sample_ts_us, np.nan, dtype=float)
    s0 = float(sample_ts_us[0]); c0 = float(can_ts_us[0])
    st = (sample_ts_us - s0) / 1e6
    ct = (can_ts_us   - c0) / 1e6
    out = np.full(st.shape, np.nan, dtype=float)
    for i, t in enumerate(st):
        j = int(np.argmin(np.abs(ct - t)))
        if abs(ct[j] - t) <= max_tdiff_s:
            out[i] = float(can_vals[j])
    return out

def _scene_sample_tokens_and_ts(nusc, scene_token: str) -> Tuple[List[str], np.ndarray]:
    toks, ts = [], []
    cur = nusc.get('scene', scene_token)['first_sample_token']
    while cur:
        toks.append(cur)
        smp = nusc.get('sample', cur)
        ts.append(smp['timestamp'])
        cur = smp['next']
    return toks, np.array(ts, dtype=np.int64)

def _wheel_rpm_to_kmh(rpm: np.ndarray, wheel_radius_m: float = 0.305) -> np.ndarray:
    circumference = 2.0 * math.pi * float(wheel_radius_m)
    v_mps = (rpm.astype(float) * circumference) / 60.0
    return v_mps * 3.6

def speed_kmh_map_from_CAN(nusc: NuScenes, dataroot: str, max_tdiff_s: float = 0.5) -> Dict[str, float]:
    """sample_token -> vitesse ego (km/h) via CAN (vehicle_speed puis wheel rpm)."""
    out: Dict[str, float] = {}
    if not HAS_CAN:
        return out
    try:
        nusc_can = NuScenesCanBus(dataroot=dataroot)
        can_blacklist = set(nusc_can.can_blacklist)
    except Exception as e:
        log.warning(f"NuScenesCanBus init error: {e}")
        return out

    for scene in nusc.scene:
        scene_name  = scene['name']
        scene_token = scene['token']
        s_tokens, s_ts = _scene_sample_tokens_and_ts(nusc, scene_token)

        # a) vehicle_speed direct (km/h)
        veh_kmh = None
        try:
            if scene_name not in can_blacklist:
                msgs = nusc_can.get_messages(scene_name, 'vehicle_monitor')
                kmh_vals = np.array([m['vehicle_speed'] for m in msgs], dtype=float)
                kmh_ts   = np.array([m['utime'] for m in msgs], dtype=np.int64)
                if len(kmh_vals) > 0:
                    veh_kmh = _nn_assign_times(s_ts, kmh_ts, kmh_vals, max_tdiff_s)
        except Exception:
            veh_kmh = None

        # b) wheel rpm -> km/h
        wheel_kmh = None
        if veh_kmh is None or np.all(np.isnan(veh_kmh)):
            try:
                if scene_name not in can_blacklist:
                    msgs = nusc_can.get_messages(scene_name, 'zoe_veh_info')
                    if len(msgs) > 0:
                        rpm_mat, ts_list = [], []
                        for m in msgs:
                            ts_list.append(int(m['utime']))
                            rpms = [m.get('FL_wheel_speed'), m.get('FR_wheel_speed'),
                                    m.get('RL_wheel_speed'), m.get('RR_wheel_speed')]
                            rpms = [float(x) if x is not None else np.nan for x in rpms]
                            rpm_mat.append(rpms)
                        rpm_mat = np.array(rpm_mat, dtype=float)
                        rpm_mean = np.nanmean(np.abs(rpm_mat), axis=1)
                        kmh_vals = _wheel_rpm_to_kmh(rpm_mean)
                        kmh_ts   = np.array(ts_list, dtype=np.int64)
                        wheel_kmh = _nn_assign_times(s_ts, kmh_ts, kmh_vals, max_tdiff_s)
            except Exception:
                wheel_kmh = None

        # c) fusion finale
        for i, s_tok in enumerate(s_tokens):
            val = np.nan
            if veh_kmh is not None and i < len(veh_kmh) and not np.isnan(veh_kmh[i]):
                val = veh_kmh[i]
            elif wheel_kmh is not None and i < len(wheel_kmh) and not np.isnan(wheel_kmh[i]):
                val = wheel_kmh[i]
            if not np.isnan(val):
                out[s_tok] = float(val)

    return out

def speed_kmh_map_from_pose(nusc: NuScenes,
                            scene_order: Dict[str, List[str]],
                            ego_pose_map: Dict[str, Tuple[np.ndarray, List[float], int]]) -> Dict[str, float]:
    """Fallback vitesse ego via Δpose/Δt."""
    vmap: Dict[str, float] = {}
    for scene in nusc.scene:
        toks = scene_order[scene['token']]
        prev = None; prev_ts = None
        for tok in toks:
            cur = ego_pose_map.get(tok)
            if cur and prev is not None and prev_ts is not None:
                dist = np.linalg.norm(cur[0] - prev)
                dt = max(1e-6, (cur[2] - prev_ts) * 1e-6)
                vmap[tok] = (dist / dt) * 3.6
            if cur:
                prev, prev_ts = cur[0], cur[2]
        # forward diff pour la première
        valid = [t for t in toks if ego_pose_map.get(t)]
        if len(valid) >= 2:
            t0, t1 = valid[0], valid[1]
            if vmap.get(t0) is None:
                p0, ts0 = ego_pose_map[t0][0], ego_pose_map[t0][2]
                p1, ts1 = ego_pose_map[t1][0], ego_pose_map[t1][2]
                vmap[t0] = (np.linalg.norm(p1 - p0) / max(1e-6, (ts1 - ts0) * 1e-6)) * 3.6
    return vmap

# ===================== Sélection véhicule (moving & long>0) =====================
def has_attr_vehicle_moving(nusc, ann) -> Optional[bool]:
    """
    Interprète les attribute_tokens du véhicule :
      - True  si 'vehicle.moving' présent
      - False si 'vehicle.stopped' ou 'vehicle.parked' présent
      - None  sinon (inconnu)
    """
    toks = ann.get('attribute_tokens') or []
    if not toks:
        return None
    try:
        names = [nusc.get('attribute', t)['name'] for t in toks]
    except Exception:
        return None
    if any('vehicle.moving' in a for a in names):
        return True
    if any(('vehicle.stopped' in a) or ('vehicle.parked' in a) for a in names):
        return False
    return None

def safe_box_velocity_ms(nusc, ann_token: str) -> Optional[np.ndarray]:
    """
    Récupère la vitesse d'une box annotation (m/s) via devkit.
    ⚠️ Peut retourner NaN / erreurs selon samples -> on protège.
    """
    try:
        v = np.array(nusc.box_velocity(ann_token), dtype=float)
        if np.any(np.isnan(v)):
            return None
        return v
    except Exception:
        return None

def select_vehicle_for_ped_long_gt0(
    nusc: NuScenes,
    ped_ann: dict,
    vehicle_anns: List[dict],
    use_cone_deg: Optional[float] = None
) -> Optional[Tuple[dict, float, float]]:
    """
    Sélectionne le véhicule "moving" le plus proche tel que le piéton soit DEVANT ce véhicule.

    Retour :
      (veh_ann, dist_m, veh_speed_kmh)
    où dist_m = distance XY (au sol) entre le centre du véhicule et le centre du piéton.

    Paramètre optionnel:
      use_cone_deg : si non None, impose un cône (filtre latéral) autour de l'axe longitudinal.
    """
    P = np.array(ped_ann['translation'], float)
    best = None

    for veh in vehicle_anns:
        # 1) doit être explicitement "moving"
        mv = has_attr_vehicle_moving(nusc, veh)
        if mv is not True:
            continue

        V = np.array(veh['translation'], float)
        Q = veh['rotation']

        # 2) le piéton doit être devant le véhicule dans SON repère
        long_v, lat_v = long_lat_from_ref(P, V, Q)
        if long_v <= 0.0:
            continue

        # 3) option : filtre conique latéral (si activé)
        if use_cone_deg is not None and abs(lat_v) > math.tan(math.radians(use_cone_deg)) * long_v:
            continue

        # 4) vitesse véhicule via box_velocity (m/s) -> km/h
        v_ms = safe_box_velocity_ms(nusc, veh['token'])
        if v_ms is None:
            continue
        veh_speed_kmh = float(np.linalg.norm(v_ms[:2])) * 3.6

        # 5) distance XY
        dist_m = float(np.linalg.norm((P - V)[:2]))

        cand = (veh, dist_m, veh_speed_kmh)
        if (best is None) or (dist_m < best[1]):
            best = cand

    return best

# ===================== VISU helpers + cache =====================
def get_cam_front_sd(nusc: NuScenes, sample_token: str) -> Optional[dict]:
    """
    Récupère le sample_data CAM_FRONT correspondant au sample_token.
    ⚠️ Implémentation naïve : parcourt nusc.sample_data (peut être coûteux).
    """
    for sd in nusc.sample_data:
        if sd['sample_token'] == sample_token and sd['is_key_frame']:
            cs = nusc.get('calibrated_sensor', sd['calibrated_sensor_token'])
            chan = nusc.get('sensor', cs['sensor_token'])['channel']
            if chan == "CAM_FRONT":
                return sd
    return None

# Cache intrinsics/extrinsics caméra (évite recalcul à chaque frame)
_CAM_INTR_CACHE: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray, int, int, str]] = {}

def get_cam_intrinsics_cached(nusc: NuScenes, sd_cam: dict, dataroot: str):
    """
    Prépare les matrices pour projeter du global vers l'image CAM_FRONT :
      - R_cam_glob, t_cam_glob (pose caméra dans le repère global)
      - K (intrinsics)
      - W,H de l'image (charge l'image une fois)
      - img_path

    Cache par sample_data_token.
    """
    sd_tok = sd_cam['token']
    if sd_tok in _CAM_INTR_CACHE:
        return _CAM_INTR_CACHE[sd_tok]

    cs = nusc.get('calibrated_sensor', sd_cam['calibrated_sensor_token'])
    ep = nusc.get('ego_pose', sd_cam['ego_pose_token'])

    cam_R_ego = quat_wxyz_to_R(*cs['rotation'])
    cam_t_ego = np.array(cs['translation'], float)

    ego_R_glob = quat_wxyz_to_R(*ep['rotation'])
    ego_t_glob = np.array(ep['translation'], float)

    # caméra dans global : R = R_ego * R_cam,  t = t_ego + R_ego * t_cam
    R_cam_glob = ego_R_glob @ cam_R_ego
    t_cam_glob = ego_t_glob + ego_R_glob @ cam_t_ego

    K = np.array(cs['camera_intrinsic'], float)

    img_path = str(Path(dataroot) / sd_cam['filename'])
    img = cv2.imread(img_path)
    if img is None:
        W = H = 0
    else:
        H, W = img.shape[:2]

    _CAM_INTR_CACHE[sd_tok] = (R_cam_glob, t_cam_glob, K, W, H, img_path)
    return _CAM_INTR_CACHE[sd_tok]

def draw_vehicle_box(img, veh_ann, R_cam_glob, t_cam_glob, K, color=(255,0,0), thick=2):
    """
    Dessine une bbox 3D projetée (approx via corners -> min/max rectangle) pour le véhicule sélectionné.
    Retourne (p1,p2) si visible, sinon None.
    """
    box = Box(veh_ann['translation'], veh_ann['size'], Quaternion(veh_ann['rotation']))
    # passage global -> caméra (traduction + rotation)
    box.translate(-t_cam_glob)
    box.rotate(Quaternion(matrix=R_cam_glob.T))

    corners = box.corners()
    H, W = img.shape[:2]
    if np.all(corners[2, :] <= 0):
        return None

    pts_2d = view_points(corners, K, normalize=True)[:2, :].T
    xmin, ymin = np.min(pts_2d[:,0]), np.min(pts_2d[:,1])
    xmax, ymax = np.max(pts_2d[:,0]), np.max(pts_2d[:,1])

    # rejette si hors image
    if xmax < 0 or ymax < 0 or xmin >= W or ymin >= H:
        return None

    p1 = (int(max(0, xmin)), int(max(0, ymin)))
    p2 = (int(min(W-1, xmax)), int(min(H-1, ymax)))
    cv2.rectangle(img, p1, p2, color, thick)
    return (p1, p2)

# ===================== Export par piéton + VISU =====================
def process_all(nusc: NuScenes):
    """
    Pipeline global :
    - pré-index scenes/samples/ego_pose/CAM_FRONT + météo night/clear
    - vitesses ego (CAN prioritaire)
    - group annotations piétons par instance
    - pour chaque frame valide :
        - calcule ego distance + ahead + on_road
        - applique filtres (ahead + visibilité)
        - choisit véhicule de référence (ego ou autre véhicule moving devant)
        - produit 2 rows (adj/noadj) + optionnel overlay image
    - écriture CSV par instance_token
    - optionnel : vidéo MP4 par piéton (concat frames)
    """
    # --- Index de base ---
    scene_order = build_scene_order(nusc)
    sd_by_chan  = index_sd_by_channel(nusc)
    ego_map     = ego_pose_by_sample(nusc, sd_by_chan, prefer_channel="LIDAR_TOP")

    night_full_set, night_base_set = _load_night_sets(NIGHT_CSV_PATH)
    road_cache = RoadUnionCache(dataroot=DATAROOT)

    # --- Vitesse ego (km/h) : pose fallback + CAN prioritaire ---
    v_pose = speed_kmh_map_from_pose(nusc, scene_order, ego_map)
    v_can  = speed_kmh_map_from_CAN(nusc, dataroot=DATAROOT, max_tdiff_s=0.5)
    speed_map: Dict[str, float] = dict(v_pose)
    speed_map.update(v_can)

    # --- Index piétons par instance_token ---
    ped_instances: Dict[str, List[dict]] = {}
    for ann in nusc.sample_annotation:
        if ann['category_name'].startswith('human.pedestrian'):
            ped_instances.setdefault(ann['instance_token'], []).append(ann)

    # --- map sample->scene (utile si besoin) ---
    sample_to_scene = {}
    for scene in nusc.scene:
        tok = scene['first_sample_token']
        while tok:
            sample_to_scene[tok] = scene
            tok = nusc.get('sample', tok)['next']

    def weather_for_sample(sample_token: str) -> str:
        """night/clear à partir du CSV externe + CAM_FRONT filename."""
        sd_tok = sd_by_chan.get((sample_token, "CAM_FRONT"))
        if sd_tok is None:
            return WEATHER_DEFAULT
        sd = nusc.get('sample_data', sd_tok)
        rel = sd['filename']
        full = _norm_path(os.path.join(DATAROOT, rel))
        base = os.path.basename(full)
        return "night" if (full in night_full_set or base in night_base_set) else "clear"

    # --- Buffer des frames par piéton pour la vidéo ---
    ped_frame_paths: Dict[str, List[str]] = {}  # instance_token -> [paths jpg]

    # Progression scènes
    with tqdm(total=len(nusc.scene), desc="Scenes", position=0) as p_scenes:
        for scene in nusc.scene:
            scene_tok  = scene['token']
            scene_name = scene['name']
            location   = nusc.get('log', scene['log_token'])['location']
            s_tokens   = set(scene_order[scene_tok])

            # instances piétons présentes dans cette scène
            inst_tokens = [
                it for it, anns in ped_instances.items()
                if any(a['sample_token'] in s_tokens for a in anns)
            ]

            with tqdm(total=len(inst_tokens), desc=f"Instances {scene_name}", position=1, leave=False) as p_inst:
                for inst_tok in inst_tokens:
                    # frames de ce piéton dans cette scène
                    anns = [a for a in ped_instances[inst_tok] if a['sample_token'] in s_tokens]
                    anns.sort(key=lambda a: nusc.get('sample', a['sample_token'])['timestamp'])

                    rows = []

                    with tqdm(total=len(anns), desc="Frames", position=2, leave=False) as p_frames:
                        for ann in anns:
                            s_tok = ann['sample_token']

                            # ego pose obligatoire
                            if s_tok not in ego_map:
                                p_frames.update(1)
                                continue
                            ego_t, ego_q, ts = ego_map[s_tok]

                            # vitesse ego (km/h)
                            v_kmh_ego = speed_map.get(s_tok, None)

                            # position piéton (global)
                            ped_xyz = np.array(ann['translation'], float)

                            # hauteur (cm) : size[2]*100 avec fallback location
                            try:
                                h_cm = float(ann['size'][2]) * 100.0
                            except Exception:
                                h_cm = None
                            if (h_cm is None) or not (HEIGHT_MIN_CM <= h_cm <= HEIGHT_MAX_CM):
                                loc_mean = LOC_MEAN_HEIGHT_CM.get((location or "").lower())
                                if loc_mean is not None:
                                    h_cm = loc_mean

                            # distance ego -> piéton et test ahead
                            d_long_ego, d_lat_ego = long_lat_from_global(ped_xyz, ego_t, ego_q)
                            distance_ego_m = float(math.hypot(d_long_ego, d_lat_ego))
                            ahead = d_long_ego > 0

                            # on_road (strict GT)
                            on_road = road_cache.is_on_road(location, ped_xyz[0], ped_xyz[1]) if HAS_SHAPELY else None

                            true_label = None
                            if on_road is not None:
                                true_label = int(bool(on_road and ahead))

                            # ----------------- FILTRES DATASET -----------------
                            # 1) ahead seulement (si activé)
                            if PRED_ONLY_AHEAD and not ahead:
                                p_frames.update(1)
                                continue

                            # 2) visibilité dans CAM_FRONT avec marge (si activé)
                            if PRED_REQUIRE_VISIBLE:
                                sd_cam_pred = get_cam_front_sd(nusc, s_tok)
                                if sd_cam_pred is None:
                                    p_frames.update(1)
                                    continue
                                R_cam_glob_pred, t_cam_glob_pred, K_pred, W0, H0, _imgp = get_cam_intrinsics_cached(
                                    nusc, sd_cam_pred, DATAROOT
                                )
                                if W0 <= 0 or H0 <= 0:
                                    p_frames.update(1)
                                    continue
                                ped_uv_pred = project_global_to_image(ped_xyz, R_cam_glob_pred, t_cam_glob_pred, K_pred, W0, H0)
                                if not is_inside_with_margin(ped_uv_pred, W0, H0, PRED_MARGIN_PX):
                                    p_frames.update(1)
                                    continue
                            # ----------------- FIN FILTRES -----------------

                            # ----------------- RÈGLE : choisir un véhicule de référence -----------------
                            # ⚠️ Ici tu reconstruis la liste des annotations du sample en parcourant nusc.sample_annotation
                            # pour chaque frame : c’est correct mais coûteux (O(N) par frame).
                            sample_anns = [a for a in nusc.sample_annotation if a['sample_token'] == s_tok]
                            veh_anns = [a for a in sample_anns if a['category_name'].startswith('vehicle.')]

                            veh_sel = select_vehicle_for_ped_long_gt0(
                                nusc=nusc, ped_ann=ann, vehicle_anns=veh_anns, use_cone_deg=None
                            ) if USE_OTHER_VEHICLE_RULE else None

                            # Valeurs par défaut : ego
                            ref_velocity_kmh = v_kmh_ego
                            ref_distance_m   = distance_ego_m
                            rule_ref = "ego_fallback"
                            rule_vehicle = None

                            # Si un véhicule "moving & devant" est trouvé, on ne le prend que s'il est vraiment plus proche
                            if USE_OTHER_VEHICLE_RULE and veh_sel is not None:
                                veh_ann, dist_m, veh_speed_kmh = veh_sel
                                if (not VEH_MUST_BE_CLOSER_THAN_EGO) or (dist_m < distance_ego_m - VEH_CLOSER_EPS_M):
                                    ref_velocity_kmh = veh_speed_kmh
                                    ref_distance_m   = dist_m
                                    rule_ref = "vehicle_moving_long>0"
                                    rule_vehicle = veh_ann
                                elif VEH_MUST_BE_CLOSER_THAN_EGO:
                                    log.debug(
                                        f"Skip veh: d_veh={dist_m:.1f}m >= d_ego={distance_ego_m:.1f}m - {VEH_CLOSER_EPS_M:.1f}"
                                    )
                            # ----------------- FIN RÈGLE -----------------

                            # Filtrage strict : il faut toutes les features + true_label
                            if not (finite(ref_velocity_kmh) and finite(ref_distance_m) and finite(h_cm) and (true_label is not None)):
                                p_frames.update(1)
                                continue

                            weather = weather_for_sample(s_tok)

                            base_row = {
                                "scene_name": scene_name,
                                "instance_token": inst_tok,
                                "sample_token": s_tok,
                                "timestamp": ts,
                                "weather": weather,
                                "velocity_kmh": float(ref_velocity_kmh),
                                "distance_m": float(ref_distance_m),
                                "real_height_cm": float(h_cm),
                                "true_label": int(true_label),
                            }

                            # ----------------- PRÉDICTION MODÈLE -----------------
                            def predict(adj_flag: bool):
                                """
                                Appel du modèle + règle additionnelle :
                                ⚠️ Ici tu forces crossing=True si v<20 km/h (règle de sécurité).
                                => Important de le documenter comme "post-processing decision rule".
                                """
                                try:
                                    crossing = ped_model(
                                        base_row["weather"],
                                        base_row["real_height_cm"],
                                        base_row["velocity_kmh"],
                                        base_row["distance_m"],
                                        bool(adj_flag)
                                    )
                                    # Post-rule explicite (20 km/h)
                                    if base_row["velocity_kmh"] < 20:
                                        crossing = True
                                    return crossing
                                except Exception as e:
                                    log.warning(f"Model error ({scene_name}, inst={inst_tok}): {e}")
                                    return None

                            row_adj   = dict(base_row); row_adj["predicted_label"]   = to_bool_label(predict(True))
                            row_noadj = dict(base_row); row_noadj["predicted_label"] = to_bool_label(predict(False))
                            rows.append((row_adj, row_noadj))
                            # ----------------- FIN PRÉDICTION -----------------

                            # =============== VISU (optionnel) ===============
                            if SAVE_VIS:
                                sd_cam = get_cam_front_sd(nusc, s_tok)
                                if sd_cam is not None:
                                    R_cam_glob, t_cam_glob, K, W, H, img_path = get_cam_intrinsics_cached(nusc, sd_cam, DATAROOT)
                                    if W > 0 and H > 0:
                                        img = cv2.imread(img_path)
                                        if img is not None:
                                            # Piéton : point projeté + id
                                            ped_uv = project_global_to_image(ped_xyz, R_cam_glob, t_cam_glob, K, W, H)
                                            if ped_uv is not None:
                                                cv2.circle(img, ped_uv, 7, (0,255,255), -1, cv2.LINE_AA)
                                                draw_text_bg(
                                                    img,
                                                    f"ped {ann['instance_token'][:8]}",
                                                    (ped_uv[0]+10, max(0, ped_uv[1]-10))
                                                )

                                            # Véhicule sélectionné par la règle : bbox + ligne veh->ped
                                            if rule_vehicle is not None:
                                                _ = draw_vehicle_box(img, rule_vehicle, R_cam_glob, t_cam_glob, K, color=(255,0,0), thick=2)
                                                veh_center = np.array(rule_vehicle['translation'], float)
                                                veh_uv = project_global_to_image(veh_center, R_cam_glob, t_cam_glob, K, W, H)
                                                if ped_uv is not None and veh_uv is not None:
                                                    cv2.line(img, veh_uv, ped_uv, (0,255,255), 2, cv2.LINE_AA)

                                            # Bandeau texte : inputs + GT + preds + règle appliquée
                                            l1 = f"{scene_name} | {sd_cam['channel']} | weather:{weather}"
                                            l2 = f"in: v={base_row['velocity_kmh']:.1f} km/h  d_ref={base_row['distance_m']:.1f} m  d_ego={distance_ego_m:.1f} m"
                                            if veh_sel is not None:
                                                l2 += f"  d_veh={veh_sel[1]:.1f} m"
                                            l3 = f"GT:{base_row['true_label']}  pred_adj:{row_adj['predicted_label']}  pred_noadj:{row_noadj['predicted_label']}"
                                            if rule_vehicle is not None:
                                                l4 = (
                                                    f"rule:vehicle_moving_long>0 | veh:{rule_vehicle['instance_token'][:8]} | "
                                                    f"d_vp:{base_row['distance_m']:.1f} m | v_veh:{base_row['velocity_kmh']:.1f} km/h"
                                                )
                                            else:
                                                l4 = "rule:ego_fallback | ref=ego"

                                            for i, s in enumerate([l1, l2, l3, l4]):
                                                draw_text_bg(img, s, (10, 30 + i*26), font_scale=0.7, bg=(0,0,0))

                                            # Sauvegarde : une frame par piéton et par timestamp
                                            ped_dir = VIS_DIR / scene_name / f"ped_{inst_tok[:8]}"
                                            ped_dir.mkdir(parents=True, exist_ok=True)
                                            fname = f"{scene_name}_t{ts}_{inst_tok[:8]}.jpg"
                                            fpath = str(ped_dir / fname)
                                            cv2.imwrite(fpath, img)

                                            # Stocke le path pour construire la vidéo ensuite
                                            ped_frame_paths.setdefault(inst_tok, []).append(fpath)

                            p_frames.update(1)

                    # ----------------- ÉCRITURE CSV par piéton -----------------
                    if rows:
                        df_adj   = pd.DataFrame([r[0] for r in rows])
                        df_noadj = pd.DataFrame([r[1] for r in rows])
                        base = f"NUSC_{scene_name}_inst-{inst_tok}.csv"
                        df_adj.to_csv(OUT_DIR_ADJ / base,   index=False, encoding="utf-8")
                        df_noadj.to_csv(OUT_DIR_NOADJ / base, index=False, encoding="utf-8")

                    p_inst.update(1)
            p_scenes.update(1)

    # ===================== VIDÉO (optionnel) — PAR PIÉTON =====================
    if SAVE_VIS and MAKE_VIDEO:
        for inst_tok, paths in ped_frame_paths.items():
            if not paths:
                continue

            # Tri : ici tu relies le tri au nom (timestamp inclus).
            # Ça marche tant que la convention fname est conservée.
            paths_sorted = sorted(paths)
            first = cv2.imread(paths_sorted[0])
            if first is None:
                continue
            H, W = first.shape[:2]

            # Infère scene_name depuis le chemin : .../<scene_name>/ped_xxxxxxxx/<file>.jpg
            try:
                scene_name = Path(paths_sorted[0]).parts[-3]
            except Exception:
                scene_name = "unknown_scene"

            vdir = VIS_DIR / scene_name
            vdir.mkdir(parents=True, exist_ok=True)
            vpath = str(vdir / f"{scene_name}_ped_{inst_tok[:8]}.mp4")

            writer = cv2.VideoWriter(vpath, cv2.VideoWriter_fourcc(*"mp4v"), VIDEO_FPS, (W, H))
            for pth in paths_sorted:
                frame = cv2.imread(pth)
                if frame is None:
                    continue
                if frame.shape[:2] != (H, W):
                    frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_LINEAR)
                writer.write(frame)
            writer.release()

            log.info(f"[VIDEO PED] {inst_tok[:8]} -> {vpath}")

# ===================== MAIN =====================
if __name__ == "__main__":
    nusc = NuScenes(version=VERSION, dataroot=DATAROOT, verbose=False)
    process_all(nusc)
