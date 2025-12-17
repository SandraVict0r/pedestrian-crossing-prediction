# -*- coding: utf-8 -*-
"""
Export nuScenes : annotations piétons (3D) -> CSV d'évaluation du modèle

But
---
Pour chaque piéton (clé = instance_token), le script génère 2 CSV :
  - adj=True  : modèle avec biais sécurité / SCBA activé
  - adj=False : modèle sans SCBA

Chaque ligne = une frame (sample) valide pour ce piéton.
Colonnes principales :
  weather, velocity_kmh, distance_m, real_height_cm, true_label, predicted_label
+ métadonnées utiles : scene_name, instance_token, sample_token, timestamp.

Vitesse ego-vehicle (priorité)
------------------------------
1) CAN bus : vehicle_monitor.vehicle_speed (déjà en km/h)
2) CAN bus : zoe_veh_info (wheel rpm -> km/h)
3) Fallback : Δpose/Δt via ego_pose (km/h)

Vérité terrain (GT crossing) "strict"
-------------------------------------
On définit crossing = True si :
  - le piéton est sur une zone "route" (on_road=True) ET
  - le piéton est devant le véhicule (ahead=True : d_long > 0)
Sinon crossing=False.
Cas particulier : si on_road est inconnu (shapely absent / map invalide) -> frame ignorée.

Filtrage frame strict
---------------------
On conserve uniquement les frames où TOUT est disponible :
  - vitesse ego (km/h)
  - distance ego->piéton (m)
  - hauteur piéton (cm)
  - true_label (GT)
Sinon on ignore la frame.

Progress bars
-------------
Scenes -> Instances -> Frames, via tqdm.
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
# Racine nuScenes : doit contenir (par ex.) v1.0-mini/, maps/, can_bus/
DATAROOT = r"E:\crossing-model\main_experiment\model_validation\datasets\nuscenes"
VERSION  = "v1.0-mini"

# Modèle comportemental (python file importé dynamiquement)
MODEL_PATH = Path(r"E:\crossing-model\main_experiment\model_datas\CNRS_behavior_model.py")

# Dossiers de sortie (2 variantes : adj / no-adj)
OUT_DIR_ADJ   = Path(r"E:\crossing-model\main_experiment\model_validation\evaluation\model_resul_adj_NUSCENES_half_velocity")
OUT_DIR_NOADJ = Path(r"E:\crossing-model\main_experiment\model_validation\evaluation\model_result_no_adj_NUSCENES_half_velocity")
OUT_DIR_ADJ.mkdir(parents=True, exist_ok=True)
OUT_DIR_NOADJ.mkdir(parents=True, exist_ok=True)

# Météo : par défaut "clear"
WEATHER_DEFAULT = "clear"

# CSV externe produit séparément : liste d'images CAM_FRONT considérées "night"
# (utilisé comme lookup : path complet OU basename)
NIGHT_CSV_PATH = Path(r"E:\crossing-model\main_experiment\model_validation\datasets\nuscenes\nuscenes_camfront_weather_night.csv")

# Hauteur (cm) : nuScenes fournit 'size' (m) mais peut être bruité pour certains cas.
# Ici : si height hors bornes [150,200] cm, on remplace par une moyenne par location.
LOC_MEAN_HEIGHT_CM = {
    "boston-seaport":             169.0,
    "singapore-hollandvillage":   165.0,
    "singapore-onenorth":         165.0,
    "singapore-queenstown":       165.0,
}
HEIGHT_MIN_CM = 150.0
HEIGHT_MAX_CM = 200.0

# ===================== LOG =====================
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("nusc_export")

# ===================== DEVKIT =====================
# Devkit nuScenes : objets dataset + accès maps
from nuscenes.nuscenes import NuScenes
from nuscenes.map_expansion.map_api import NuScenesMap

# --- CAN bus API (optionnel) ---
# Si indisponible, on calcule la vitesse via Δpose/Δt.
try:
    from nuscenes.can_bus.can_bus_api import NuScenesCanBus
    HAS_CAN = True
except Exception:
    HAS_CAN = False
    log.warning("CAN bus API indisponible : on utilisera Δpose/Δt si besoin.")

# --- Shapely (optionnel) ---
# Sert à déterminer si un point (x,y) est sur une zone "route" / drivable.
# Si absent, on ne peut pas estimer on_road -> on ignore les frames (GT strict).
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
    """
    Import dynamique d'un fichier .py contenant une fonction pedestrian_behavior_model(...)
    """
    spec = importlib.util.spec_from_file_location("pedestrian_behavior_model", str(model_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "pedestrian_behavior_model"):
        raise AttributeError("pedestrian_behavior_model(...) introuvable.")
    return module.pedestrian_behavior_model

ped_model = load_model(MODEL_PATH)

def to_bool_label(v):
    """
    Normalise la sortie du modèle en chaîne "True"/"False" (ou None).
    - Accepte bool, 0/1, strings, floats…
    """
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"true","1","yes","y","t"}:
        return "True"
    if s in {"false","0","no","n","f"}:
        return "False"
    try:
        # Interprétation probabilité / score
        return "True" if float(s) >= 0.5 else "False"
    except:
        # Fallback booléen Python
        return "True" if bool(v) else "False"

def _norm_path(p: str) -> str:
    """
    Normalise un chemin (utile car le CSV de nuit peut contenir des chemins variés).
    """
    p = str(p).strip().strip('"').strip("'")
    try:
        return os.path.normcase(os.path.normpath(p))
    except Exception:
        return p

def _load_night_sets(csv_path: Path) -> Tuple[Set[str], Set[str]]:
    """
    Charge le CSV listant les images CAM_FRONT 'night'.
    Retourne deux sets :
      - paths normalisés (chemins complets)
      - basenames (noms de fichier seulement)
    Cela permet un match robuste même si le CSV n'a pas exactement la même racine.
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
    """
    True si x peut être converti en float et est fini (pas NaN/inf).
    """
    try:
        return (x is not None) and math.isfinite(float(x))
    except Exception:
        return False

# ===================== Géométrie =====================
def quat_wxyz_to_R(qw, qx, qy, qz) -> np.ndarray:
    """
    Convertit un quaternion (w,x,y,z) en matrice de rotation 3x3.
    Utilisé pour transformer les coordonnées globales -> repère ego.
    """
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
    Calcule les coordonnées (longitudinal, latéral) du piéton dans le repère ego :
      v = ped - ego_translation
      v_ego = R^T v
    Retour :
      d_long = v_ego[0] (avant/derrière)
      d_lat  = v_ego[1] (gauche/droite)
    """
    v = ped_xyz - ego_t
    R_ego = quat_wxyz_to_R(*ego_q)
    v_ego = R_ego.T @ v
    return float(v_ego[0]), float(v_ego[1])

def location_mean_height_cm_or_none(loc: Optional[str]) -> Optional[float]:
    """
    Renvoie une hauteur moyenne (cm) selon la location nuScenes, ou None si inconnue.
    """
    key = (loc or "").strip().lower()
    return LOC_MEAN_HEIGHT_CM.get(key)

# ===================== Drivable / Road cache =====================
class RoadUnionCache:
    """
    Prépare pour chaque location une géométrie shapely "route" = union de :
      - drivable_area
      - road_segment
      - lane
    NB: carpark_area est volontairement exclu.
    On stocke une prepared geometry (prep) pour accélérer les tests point-in-polygon.
    """
    def __init__(self, dataroot: str):
        self.dataroot = dataroot
        self.cache: Dict[str, Any] = {}  # location -> prepared geometry (ou None)

    def _get_polygon(self, nmap, token):
        """Récupère un polygone de map API, compatible plusieurs versions devkit."""
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
        """
        Collecte tous les polygones d'une couche (layer) nuScenesMap.
        Supporte:
          - polygon_token (unique)
          - polygon_tokens (liste)
        """
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
        """Construit (si nécessaire) et renvoie la géométrie 'route' préparée pour une location."""
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
        """
        Test point-in-road :
          True  -> dans ou sur la frontière de la géométrie union
          False -> hors union
          None  -> impossible (pas shapely / map non disponible)
        """
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

# ===================== Index & vitesses =====================
def build_scene_order(nusc: NuScenes) -> Dict[str, List[str]]:
    """
    Construit l'ordre temporel des sample_token pour chaque scène.
    (scene_token -> liste ordonnée de sample_token)
    """
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
    """
    Index (sample_token, channel) -> sample_data_token pour les keyframes.
    Sert à récupérer ego_pose et chemins images CAM_FRONT.
    """
    idx = {}
    for sd in nusc.sample_data:
        if not sd.get('is_key_frame', False):
            continue
        cs = nusc.get('calibrated_sensor', sd['calibrated_sensor_token'])
        chan = nusc.get('sensor', cs['sensor_token'])['channel']
        idx[(sd['sample_token'], chan)] = sd['token']
    return idx

def ego_pose_by_sample(nusc: NuScenes, sd_by_chan: Dict[Tuple[str,str], str], prefer_channel="LIDAR_TOP"):
    """
    Map sample_token -> (translation, rotation_quat, timestamp) pour ego_pose.
    Priorité: LIDAR_TOP, sinon fallback sur une caméra.
    """
    out = {}
    for sample in nusc.sample:
        s_tok = sample['token']
        sd_tok = sd_by_chan.get((s_tok, prefer_channel))

        # fallback si pas de lidar keyframe
        if sd_tok is None:
            for alt in ("CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT",
                        "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT"):
                sd_tok = sd_by_chan.get((s_tok, alt))
                if sd_tok is not None:
                    break
            if sd_tok is None:
                continue

        sd = nusc.get('sample_data', sd_tok)
        ep = nusc.get('ego_pose', sd['ego_pose_token'])
        out[s_tok] = (np.array(ep['translation'], float), ep['rotation'], ep['timestamp'])
    return out

def _nn_assign_times(sample_ts_us: np.ndarray, can_ts_us: np.ndarray, can_vals: np.ndarray, max_tdiff_s: float):
    """
    Associe à chaque timestamp de sample (µs) la valeur CAN la plus proche
    (nearest neighbor) si |Δt| <= max_tdiff_s, sinon NaN.
    """
    if len(can_ts_us) == 0:
        return np.full_like(sample_ts_us, np.nan, dtype=float)

    # Mise en temps relatif (s) pour stabilité numérique
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
    """Retourne la séquence (sample_token) et leurs timestamps (µs) pour une scène."""
    toks, ts = [], []
    cur = nusc.get('scene', scene_token)['first_sample_token']
    while cur:
        toks.append(cur)
        smp = nusc.get('sample', cur)
        ts.append(smp['timestamp'])
        cur = smp['next']
    return toks, np.array(ts, dtype=np.int64)

def _wheel_rpm_to_kmh(rpm: np.ndarray, wheel_radius_m: float = 0.305) -> np.ndarray:
    """Conversion RPM -> km/h via rayon de roue supposé."""
    circumference = 2.0 * math.pi * float(wheel_radius_m)
    v_mps = (rpm.astype(float) * circumference) / 60.0
    return v_mps * 3.6

def speed_kmh_map_from_CAN(nusc: NuScenes, dataroot: str, max_tdiff_s: float = 0.5) -> Dict[str, float]:
    """
    Construit sample_token -> speed_kmh via CAN.
    Priorité :
      1) vehicle_monitor.vehicle_speed (déjà km/h)
      2) zoe_veh_info (wheel speeds) -> km/h
    """
    out: Dict[str, float] = {}
    if not HAS_CAN:
        return out

    # Init API CAN + blacklist (certaines scènes n'ont pas CAN exploitable)
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

        # a) vitesse directe (km/h)
        veh_kmh = None
        try:
            if scene_name not in can_blacklist:
                msgs = nusc_can.get_messages(scene_name, 'vehicle_monitor')
                kmh_vals = np.array([m['vehicle_speed'] for m in msgs], dtype=float)  # déjà km/h
                kmh_ts   = np.array([m['utime'] for m in msgs], dtype=np.int64)
                if len(kmh_vals) > 0:
                    veh_kmh = _nn_assign_times(s_ts, kmh_ts, kmh_vals, max_tdiff_s)
        except Exception:
            veh_kmh = None

        # b) roues RPM (fallback si pas de vehicle_monitor)
        wheel_kmh = None
        if veh_kmh is None or np.all(np.isnan(veh_kmh)):
            try:
                if scene_name not in can_blacklist:
                    msgs = nusc_can.get_messages(scene_name, 'zoe_veh_info')
                    if len(msgs) > 0:
                        rpm_mat, ts_list = [], []
                        for m in msgs:
                            ts_list.append(int(m['utime']))
                            rpms = [
                                m.get('FL_wheel_speed'),
                                m.get('FR_wheel_speed'),
                                m.get('RL_wheel_speed'),
                                m.get('RR_wheel_speed'),
                            ]
                            rpms = [float(x) if x is not None else np.nan for x in rpms]
                            rpm_mat.append(rpms)
                        rpm_mat = np.array(rpm_mat, dtype=float)
                        rpm_mean = np.nanmean(np.abs(rpm_mat), axis=1)
                        kmh_vals = _wheel_rpm_to_kmh(rpm_mean)
                        kmh_ts   = np.array(ts_list, dtype=np.int64)
                        wheel_kmh = _nn_assign_times(s_ts, kmh_ts, kmh_vals, max_tdiff_s)
            except Exception:
                wheel_kmh = None

        # c) choix final par sample_token
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
    """
    Fallback vitesse ego via dérivée de position :
      v = ||Δpose|| / Δt
    - backward diff pour les samples suivants
    - forward diff pour le tout premier sample d'une scène
    """
    vmap: Dict[str, float] = {}
    for scene in nusc.scene:
        toks = scene_order[scene['token']]
        prev = None
        prev_ts = None

        for tok in toks:
            cur = ego_pose_map.get(tok)
            if cur and prev is not None and prev_ts is not None:
                dist = np.linalg.norm(cur[0] - prev)
                dt = max(1e-6, (cur[2] - prev_ts) * 1e-6)  # µs -> s
                vmap[tok] = (dist / dt) * 3.6
            if cur:
                prev, prev_ts = cur[0], cur[2]

        # forward diff pour la première frame si besoin
        valid = [t for t in toks if ego_pose_map.get(t)]
        if len(valid) >= 2:
            t0, t1 = valid[0], valid[1]
            if vmap.get(t0) is None:
                p0, ts0 = ego_pose_map[t0][0], ego_pose_map[t0][2]
                p1, ts1 = ego_pose_map[t1][0], ego_pose_map[t1][2]
                vmap[t0] = (np.linalg.norm(p1 - p0) / max(1e-6, (ts1 - ts0) * 1e-6)) * 3.6
    return vmap

# ===================== Export par piéton (instance_token) =====================
def process_all(nusc: NuScenes):
    """
    Pipeline global :
    - indexation samples (ordre, keyframes, ego_pose)
    - construction speed_map (pose + CAN prioritaire)
    - construction road_cache (union de polygones route)
    - group annotations piétons par instance_token
    - pour chaque scène -> pour chaque instance -> pour chaque frame:
        - compute distance/height/weather/true_label
        - filtrage strict
        - prédictions modèle (adj / noadj)
        - écriture 2 CSV
    """
    scene_order = build_scene_order(nusc)
    sd_by_chan  = index_sd_by_channel(nusc)
    ego_map     = ego_pose_by_sample(nusc, sd_by_chan, prefer_channel="LIDAR_TOP")

    # Chargement des images "night" (lookup CAM_FRONT)
    night_full_set, night_base_set = _load_night_sets(NIGHT_CSV_PATH)

    def weather_for_sample(sample_token: str) -> str:
        """
        Détermine la météo à partir d'une liste externe d'images CAM_FRONT considérées "night".
        Si pas de CAM_FRONT keyframe : fallback à WEATHER_DEFAULT.
        """
        sd_tok = sd_by_chan.get((sample_token, "CAM_FRONT"))
        if sd_tok is None:
            return WEATHER_DEFAULT

        sd = nusc.get('sample_data', sd_tok)

        # filename est relatif à DATAROOT (ex: samples/CAM_FRONT/xxx.jpg)
        rel = sd['filename']
        full = _norm_path(os.path.join(DATAROOT, rel))
        base = os.path.basename(full)

        if full in night_full_set or base in night_base_set:
            return "night"
        return "clear"

    # ---- vitesses ----
    # v_pose = fallback Δpose/Δt
    v_pose = speed_kmh_map_from_pose(nusc, scene_order, ego_map)
    # v_can = CAN (prioritaire si dispo)
    v_can  = speed_kmh_map_from_CAN(nusc, dataroot=DATAROOT, max_tdiff_s=0.5)

    # speed_map final : CAN écrase pose quand disponible
    speed_map: Dict[str, float] = dict(v_pose)
    speed_map.update(v_can)

    # Cache routes (drivable/road/lane)
    road_cache = RoadUnionCache(dataroot=DATAROOT)

    # ---- index piétons par instance_token ----
    ped_instances: Dict[str, List[dict]] = {}
    for ann in nusc.sample_annotation:
        if ann['category_name'].startswith('human.pedestrian'):
            ped_instances.setdefault(ann['instance_token'], []).append(ann)

    # map sample_token -> scene
    sample_to_scene = {}
    for scene in nusc.scene:
        tok = scene['first_sample_token']
        while tok:
            sample_to_scene[tok] = scene
            tok = nusc.get('sample', tok)['next']

    # Progression scènes
    with tqdm(total=len(nusc.scene), desc="Scenes", position=0) as p_scenes:
        for scene in nusc.scene:
            scene_tok  = scene['token']
            scene_name = scene['name']
            location   = nusc.get('log', scene['log_token'])['location']

            # set des sample_tokens de la scène pour filtrer vite
            s_tokens = set(scene_order[scene_tok])

            # liste des instances (piétons) présentes dans cette scène
            inst_tokens = [
                it for it, anns in ped_instances.items()
                if any(a['sample_token'] in s_tokens for a in anns)
            ]

            # Progression instances
            with tqdm(total=len(inst_tokens), desc=f"Instances {scene_name}", position=1, leave=False) as p_inst:
                for inst_tok in inst_tokens:
                    # Annotations de cette instance dans cette scène, triées temporellement
                    anns = [a for a in ped_instances[inst_tok] if a['sample_token'] in s_tokens]
                    anns.sort(key=lambda a: nusc.get('sample', a['sample_token'])['timestamp'])

                    rows = []

                    # Progression frames
                    with tqdm(total=len(anns), desc="Frames", position=2, leave=False) as p_frames:
                        for ann in anns:
                            s_tok = ann['sample_token']

                            # On doit pouvoir obtenir ego_pose pour construire repère ego
                            if s_tok not in ego_map:
                                p_frames.update(1)
                                continue
                            ego_t, ego_q, ts = ego_map[s_tok]

                            # vitesse ego (km/h)
                            v_kmh = speed_map.get(s_tok, None)

                            # position piéton (global)
                            ped_xyz = np.array(ann['translation'], float)

                            # hauteur piéton (size[2] en mètres -> cm)
                            # NB: si hors bornes, fallback sur moyenne par location
                            try:
                                h_cm = float(ann['size'][2]) * 100.0
                            except Exception:
                                h_cm = None
                            if (h_cm is None) or not (HEIGHT_MIN_CM <= h_cm <= HEIGHT_MAX_CM):
                                loc_mean = location_mean_height_cm_or_none(location)
                                if loc_mean is not None:
                                    h_cm = loc_mean

                            # distance & ahead (dans repère ego)
                            d_long, d_lat = long_lat_from_global(ped_xyz, ego_t, ego_q)
                            distance_m = float(math.hypot(d_long, d_lat))
                            ahead = d_long > 0

                            # on_road: test sur union drivable/road/lane
                            on_road = road_cache.is_on_road(location, ped_xyz[0], ped_xyz[1]) if HAS_SHAPELY else None

                            # true_label strict : si on_road connu
                            true_label = None
                            if on_road is not None:
                                true_label = int(bool(on_road and ahead))

                            # filtrage strict frame (tout doit être connu)
                            if not (finite(v_kmh) and finite(distance_m) and finite(h_cm) and (true_label is not None)):
                                p_frames.update(1)
                                continue

                            # météo (night vs clear)
                            weather = weather_for_sample(s_tok)

                            # base row = features pour modèle + méta
                            base_row = {
                                "scene_name": scene_name,
                                "instance_token": inst_tok,
                                "sample_token": s_tok,
                                "timestamp": ts,
                                "weather": weather,
                                # NOTE: tu as un commentaire "half speed rule" ici.
                                # Si tu veux effectivement diviser par 2, fais-le explicitement.
                                "velocity_kmh": float(v_kmh),  # /2 for half speed rule
                                "distance_m": float(distance_m),
                                "real_height_cm": float(h_cm),
                                "true_label": int(true_label),
                            }

                            # Prédictions modèle (adj / noadj)
                            def predict(adj_flag: bool):
                                try:
                                    crossing = ped_model(
                                        base_row["weather"],
                                        base_row["real_height_cm"],
                                        base_row["velocity_kmh"],
                                        base_row["distance_m"],
                                        bool(adj_flag)
                                    )
                                    # Règle optionnelle (désactivée ici):
                                    # if base_row["velocity_kmh"] < 20 :
                                    #     crossing = True
                                    return crossing
                                except Exception as e:
                                    log.warning(f"Model error ({scene_name}, inst={inst_tok}): {e}")
                                    return None

                            # On stocke "True"/"False" (string), plus robuste pour CSV
                            row_adj   = dict(base_row); row_adj["predicted_label"]   = to_bool_label(predict(True))
                            row_noadj = dict(base_row); row_noadj["predicted_label"] = to_bool_label(predict(False))

                            rows.append((row_adj, row_noadj))
                            p_frames.update(1)

                    # Écriture : uniquement si au moins une frame valide
                    if rows:
                        df_adj   = pd.DataFrame([r[0] for r in rows])
                        df_noadj = pd.DataFrame([r[1] for r in rows])
                        fname = f"NUSC_{scene_name}_inst-{inst_tok}.csv"
                        df_adj.to_csv(OUT_DIR_ADJ / fname,   index=False, encoding="utf-8")
                        df_noadj.to_csv(OUT_DIR_NOADJ / fname, index=False, encoding="utf-8")

                    p_inst.update(1)

            p_scenes.update(1)

# ===================== MAIN =====================
if __name__ == "__main__":
    # Chargement dataset via devkit nuScenes
    nusc = NuScenes(version=VERSION, dataroot=DATAROOT, verbose=False)
    process_all(nusc)
