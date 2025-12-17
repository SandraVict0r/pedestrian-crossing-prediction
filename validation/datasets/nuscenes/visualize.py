# -*- coding: utf-8 -*-
"""
nuScenes CAM_FRONT viewer (GT robuste + véhicules & passages piétons)
====================================================================

But
---
Viewer interactif (OpenCV) pour inspecter visuellement, frame par frame, des scènes nuScenes (CAM_FRONT) avec :
- Piétons (points + infos : distance ego↔piéton, taille, ahead, GT)
- Véhicules (uniquement ceux annotés 'vehicle.moving')
- Distance véhicule↔piéton (avec contraintes : piéton devant le véhicule, et pas “entre ego et le véhicule”)
- Trait (jaune) entre le véhicule et le piéton retenu + étiquette distance
- Polygones des passages piétons (layer ped_crossing) projetés dans l’image

Hypothèses / choix importants
-----------------------------
- Weather est forcé à "clear" (pas d’annotation météo ici).
- Vitesse ego : CAN prioritaire, sinon roues RPM, sinon Δpose/Δt.
- GT crossing (strict) : (on drivable_area) AND (ahead: d_long > 0).
  -> Si Shapely indisponible : on_drv = None => GT devient N/A (affiché en gris).
- Taille : size[2] (m) -> cm ; si hors [150,200], fallback moyenne par location.
- Les “véhicules pertinents” sont filtrés par attribute_tokens ('vehicle.moving').

Navigation clavier
------------------
j / espace : frame suivante
k         : frame précédente
n         : scène suivante
p         : scène précédente
q / ESC   : quitter
"""

import cv2
import math
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging
from typing import Any

# ======== CONFIG ========
DATAROOT = r"E:\crossing-model\main_experiment\model_validation\datasets\nuscenes"
VERSION  = "v1.0-mini"
CHANNEL  = "CAM_FRONT"

# Ici, la météo n'est pas calculée : elle est fixée.
WEATHER  = "clear"

# Facteur d’affichage (zoom)
SCALE    = 1.2

# Fallback hauteur (cm) selon location
LOC_MEAN_HEIGHT_CM = {
    "boston-seaport":             169.0,
    "singapore-hollandvillage":   165.0,
    "singapore-onenorth":         165.0,
    "singapore-queenstown":       165.0,
}
HEIGHT_MIN_CM = 150.0
HEIGHT_MAX_CM = 200.0

# ======== LOG ========
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("cam_front_viewer")

# ======== DEVKIT ========
from nuscenes.nuscenes import NuScenes
from nuscenes.map_expansion.map_api import NuScenesMap
from nuscenes.utils.data_classes import Box
from nuscenes.utils.geometry_utils import view_points
from pyquaternion import Quaternion

# CAN bus API (optionnel) : permet une vitesse ego plus fiable que Δpose/Δt
try:
    from nuscenes.can_bus.can_bus_api import NuScenesCanBus
    HAS_CAN = True
except Exception:
    HAS_CAN = False
    log.warning("CAN bus API indisponible : fallback Δpose/Δt pour la vitesse.")

# shapely : nécessaire pour tester si un piéton est sur drivable_area (GT robuste)
try:
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from shapely.prepared import prep
    HAS_SHAPELY = True
except Exception:
    HAS_SHAPELY = False
    log.warning("Shapely indisponible : GT 'sur chaussée' désactivé.")

# ======== Helpers géométrie & vitesse ========
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

def long_lat_from_global(point_xyz: np.ndarray, ego_t: np.ndarray, ego_q) -> Tuple[float, float]:
    """
    Retourne (longitudinal, latéral) du point global dans le repère ego.
    Utilisé pour :
    - ahead (d_long > 0)
    - distance ego↔piéton (hypot(d_long,d_lat))
    """
    v = point_xyz - ego_t
    R_ego = quat_wxyz_to_R(*ego_q)
    v_ego = R_ego.T @ v
    return float(v_ego[0]), float(v_ego[1])

def long_lat_from_ref(point_xyz: np.ndarray, ref_t: np.ndarray, ref_q) -> Tuple[float, float]:
    """
    Retourne (longitudinal, latéral) du point global dans le repère d'un objet (véhicule).
    Utilisé pour :
    - tester si un piéton est devant le véhicule (dlong_v > 0)
    """
    v = point_xyz - ref_t
    R_ref = quat_wxyz_to_R(*ref_q)
    v_ref = R_ref.T @ v
    return float(v_ref[0]), float(v_ref[1])

def project_global_to_image(P_glob: np.ndarray, R_cam_glob: np.ndarray, t_cam_glob: np.ndarray,
                            K: np.ndarray, W: int, H: int):
    """
    Projette un point global 3D dans l'image CAM_FRONT.
    Retourne (u,v) ou None si le point est derrière la caméra ou hors champ.
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

# ======== Index scènes -> samples ========
def build_scene_sample_order(nusc: NuScenes):
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

# ======== Ego pose map (pour Δpose/Δt) ========
def ego_pose_by_sample(nusc: NuScenes, prefer_channel="LIDAR_TOP"):
    """
    sample_token -> (ego_translation, ego_rotation_quat, timestamp)
    Choix du capteur : priorité au LIDAR_TOP, sinon un CAM_* keyframe.
    """
    out = {}
    sd_by_sample = {}

    # regroupe les keyframes par sample
    for sd in nusc.sample_data:
        if not sd['is_key_frame']:
            continue
        sd_by_sample.setdefault(sd['sample_token'], []).append(sd)

    # pour chaque sample, on choisit un sample_data (lidar ou caméra) pour lire ego_pose
    for s in nusc.sample:
        s_tok = s['token']
        chosen = None
        if s_tok in sd_by_sample:
            for sd in sd_by_sample[s_tok]:
                cs = nusc.get('calibrated_sensor', sd['calibrated_sensor_token'])
                chan = nusc.get('sensor', cs['sensor_token'])['channel']
                if chan == prefer_channel:
                    chosen = sd
                    break

            # fallback caméra si pas de lidar
            if chosen is None:
                for sd in sd_by_sample[s_tok]:
                    cs = nusc.get('calibrated_sensor', sd['calibrated_sensor_token'])
                    chan = nusc.get('sensor', cs['sensor_token'])['channel']
                    if chan.startswith("CAM_"):
                        chosen = sd
                        break

        if chosen:
            ep = nusc.get('ego_pose', chosen['ego_pose_token'])
            out[s_tok] = (np.array(ep['translation'], float), ep['rotation'], ep['timestamp'])

    return out

# ======== Assign CAN timestamps -> samples ========
def _nn_assign_times(sample_ts_us: np.ndarray, can_ts_us: np.ndarray, can_vals: np.ndarray, max_tdiff_s: float):
    """Assigne à chaque timestamp sample la valeur CAN la plus proche (NN) si |Δt|<=max_tdiff_s."""
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

def _scene_tokens_and_ts(nusc, scene_token: str):
    """Récupère (liste sample_tokens, array timestamps) pour une scène."""
    toks, ts = [], []
    cur = nusc.get('scene', scene_token)['first_sample_token']
    while cur:
        toks.append(cur)
        ts.append(nusc.get('sample', cur)['timestamp'])
        cur = nusc.get('sample', cur)['next']
    return toks, np.array(ts, dtype=np.int64)

def _wheel_rpm_to_kmh(rpm: np.ndarray, wheel_radius_m: float = 0.305) -> np.ndarray:
    """Convertit RPM roues (≈) en km/h via circonférence."""
    circumference = 2.0 * math.pi * float(wheel_radius_m)
    v_mps = (rpm.astype(float) * circumference) / 60.0
    return v_mps * 3.6

def build_speed_map_kmh(nusc: NuScenes, dataroot: str, scene_order) -> Dict[str, float]:
    """
    Construit un mapping sample_token -> vitesse ego (km/h) :
    1) fallback pose Δpose/Δt (toujours calculé)
    2) si CAN dispo : vehicle_monitor.vehicle_speed (km/h)
    3) sinon roues RPM via zoe_veh_info
    """
    # 1) Δpose/Δt
    ego_map = ego_pose_by_sample(nusc)
    pose_speed: Dict[str, float] = {}

    for scene in nusc.scene:
        toks = scene_order[scene['token']]
        prev = None; prev_ts = None
        for tok in toks:
            cur = ego_map.get(tok)
            if cur and prev is not None and prev_ts is not None:
                dist = np.linalg.norm(cur[0] - prev)
                dt = max(1e-6, (cur[2] - prev_ts) * 1e-6)
                pose_speed[tok] = (dist / dt) * 3.6
            if cur:
                prev, prev_ts = cur[0], cur[2]

        # vitesse pour la première frame (forward diff)
        valid = [t for t in toks if t in ego_map]
        if len(valid) >= 2 and valid[0] not in pose_speed:
            p0, ts0 = ego_map[valid[0]][0], ego_map[valid[0]][2]
            p1, ts1 = ego_map[valid[1]][0], ego_map[valid[1]][2]
            pose_speed[valid[0]] = (np.linalg.norm(p1 - p0) / max(1e-6, (ts1 - ts0) * 1e-6)) * 3.6

    if not HAS_CAN:
        return pose_speed

    # 2-3) CAN
    try:
        ncan = NuScenesCanBus(dataroot=dataroot)
        can_blacklist = set(ncan.can_blacklist)
    except Exception as e:
        log.warning(f"CAN init error: {e}")
        return pose_speed

    can_speed: Dict[str, float] = {}
    for scene in nusc.scene:
        name = scene['name']
        toks, ts = _scene_tokens_and_ts(nusc, scene['token'])

        # 2) vehicle_speed direct (déjà km/h)
        veh_kmh = None
        if name not in can_blacklist:
            try:
                msgs = ncan.get_messages(name, 'vehicle_monitor')
                kmh_vals = np.array([m['vehicle_speed'] for m in msgs], dtype=float)
                kmh_ts   = np.array([m['utime'] for m in msgs], dtype=np.int64)
                if len(kmh_vals) > 0:
                    veh_kmh = _nn_assign_times(ts, kmh_ts, kmh_vals, max_tdiff_s=0.5)
            except Exception:
                veh_kmh = None

        # 3) roues RPM -> km/h si vehicle_speed absent
        wheel_kmh = None
        if veh_kmh is None or np.all(np.isnan(veh_kmh)):
            try:
                if name not in can_blacklist:
                    msgs = ncan.get_messages(name, 'zoe_veh_info')
                    if len(msgs) > 0:
                        rpm_mat, tm = [], []
                        for m in msgs:
                            tm.append(int(m['utime']))
                            rpms = [m.get('FL_wheel_speed'), m.get('FR_wheel_speed'),
                                    m.get('RL_wheel_speed'), m.get('RR_wheel_speed')]
                            rpms = [float(x) if x is not None else np.nan for x in rpms]
                            rpm_mat.append(rpms)
                        rpm_mat = np.array(rpm_mat, float)
                        rpm_mean = np.nanmean(np.abs(rpm_mat), axis=1)
                        kmh_vals = _wheel_rpm_to_kmh(rpm_mean)
                        wheel_kmh = _nn_assign_times(ts, np.array(tm, np.int64), kmh_vals, max_tdiff_s=0.5)
            except Exception:
                wheel_kmh = None

        # fusion CAN
        for i, tok in enumerate(toks):
            val = np.nan
            if veh_kmh is not None and i < len(veh_kmh) and not np.isnan(veh_kmh[i]):
                val = veh_kmh[i]
            elif wheel_kmh is not None and i < len(wheel_kmh) and not np.isnan(wheel_kmh[i]):
                val = wheel_kmh[i]
            if not np.isnan(val):
                can_speed[tok] = float(val)

    # CAN prioritaire
    out = dict(pose_speed)
    out.update(can_speed)
    return out

# ======== Drivable cache (GT on_drivable_area) ========
class DrivableCache:
    """
    Prépare une géométrie shapely (union) de drivable_area pour chaque location,
    puis permet des requêtes rapides point-in-polygon.
    """
    def __init__(self, dataroot: str):
        self.dataroot = dataroot
        self.cache: Dict[str, Any] = {}  # location -> prepared geometry (ou None)

    def _get_polygon_obj(self, nmap, token):
        """Compat devkit : get_polygon() ou extract_polygon()."""
        if token is None:
            return None
        try:
            if hasattr(nmap, "get_polygon"):
                return nmap.get_polygon(token)
        except Exception:
            pass
        try:
            if hasattr(nmap, "extract_polygon"):
                return nmap.extract_polygon(token)
        except Exception:
            pass
        return None

    def _collect_layer_polys(self, nmap) -> List[Any]:
        """Récupère tous les polygones drivable_area."""
        polys: List[Any] = []
        for rec in getattr(nmap, "drivable_area", []):
            tok_single = rec.get("polygon_token", None)
            if tok_single:
                poly = self._get_polygon_obj(nmap, tok_single)
                if poly is not None:
                    polys.append(poly)
                continue
            tok_list = rec.get("polygon_tokens", None)
            if tok_list:
                for tok in tok_list:
                    poly = self._get_polygon_obj(nmap, tok)
                    if poly is not None:
                        polys.append(poly)
        return polys

    def get_prepared(self, location: str):
        """Construit et cache la géométrie union pour une location."""
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

        polys = self._collect_layer_polys(nmap)
        if not polys:
            log.warning(f"[{location}] Aucun polygone drivable_area trouvé.")
            self.cache[location] = None
            return None

        try:
            merged = unary_union(polys)
            self.cache[location] = prep(merged)
            log.info(f"[{location}] drivable_area polygones: {len(polys)} (union OK).")
            return self.cache[location]
        except Exception as e:
            log.warning(f"[{location}] union shapely échouée: {e}")
            self.cache[location] = None
            return None

    def is_on_drivable(self, location: str, x: float, y: float) -> Optional[bool]:
        """Retourne True/False si test possible, sinon None."""
        if not HAS_SHAPELY:
            return None
        prep_geom = self.get_prepared(location)
        if prep_geom is None:
            return None
        try:
            p = Point(x, y)
            return bool(prep_geom.contains(p) or prep_geom.touches(p))
        except Exception:
            return None

# ======== Rendu utilitaires ========
def draw_text_bg(img, text, org, font_scale=0.7, color=(255,255,255), bg=(0,0,0), thickness=1):
    """Texte avec fond noir (lisibilité)."""
    (w,h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    x,y = org
    cv2.rectangle(img, (x, y-h-baseline-4), (x+w+6, y+4), bg, -1)
    cv2.putText(img, text, (x+3, y-2), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)
    return (w,h)

def get_ped_crossings(nmap):
    """Extrait les polygones shapely des passages piétons (layer ped_crossing)."""
    polys = []
    for rec in getattr(nmap, "ped_crossing", []):
        try:
            poly = nmap.extract_polygon(rec['polygon_token'])
            if poly is not None:
                polys.append(poly)
        except Exception:
            continue
    return polys

# ======== Annot helpers ========
def has_attr_vehicle_moving(nusc, ann) -> Optional[bool]:
    """
    Lit attribute_tokens :
      True  -> 'vehicle.moving'
      False -> 'vehicle.stopped' ou 'vehicle.parked'
      None  -> indéterminé
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

def ego_speed_vec_world(nusc, sample_token: str):
    """
    Vitesse 3D de l'ego (m/s) estimée par différence de positions ego_pose prev/next.
    ⚠️ Sert uniquement à afficher une vitesse relative véhicule (pas une vérité absolue).
    """
    smp = nusc.get('sample', sample_token)

    def _pose(tok):
        # ⚠️ implémentation naïve : boucle sur sample_data pour retrouver un keyframe -> OK pour viewer
        for sd in nusc.sample_data:
            if sd['sample_token'] == tok and sd['is_key_frame']:
                ep = nusc.get('ego_pose', sd['ego_pose_token'])
                return np.array(ep['translation'], float), int(ep['timestamp'])
        return None, None

    t_cur, ts_cur = _pose(sample_token)
    if t_cur is None:
        return None

    vs = []
    if smp['prev']:
        t_prev, ts_prev = _pose(smp['prev'])
        if t_prev is not None:
            dt = (ts_cur - ts_prev) * 1e-6
            if dt > 1e-6:
                vs.append((t_cur - t_prev) / dt)

    if smp['next']:
        t_next, ts_next = _pose(smp['next'])
        if t_next is not None:
            dt = (ts_next - ts_cur) * 1e-6
            if dt > 1e-6:
                vs.append((t_next - t_cur) / dt)

    if not vs:
        return None
    return np.mean(np.stack(vs), axis=0)  # (3,) m/s

# ======== Rendu principal ========
def render_sample(nusc: NuScenes, sample_token: str, chan: str,
                  speed_map: Dict[str, float], drv_cache: DrivableCache):
    """
    Rend une image annotée pour un sample_token :
    - charge l'image CAM_FRONT
    - calcule extrinsics/intrinsics
    - affiche piétons (GT + distance + taille)
    - affiche véhicules moving (bbox) + distance au piéton retenu + ligne
    - affiche ped_crossings (polygones) projetés
    """
    # --- retrouve le sample_data token pour le canal cible ---
    sd_token = None
    for sd in nusc.sample_data:
        if sd['sample_token'] == sample_token and sd['is_key_frame']:
            cs = nusc.get('calibrated_sensor', sd['calibrated_sensor_token'])
            ch = nusc.get('sensor', cs['sensor_token'])['channel']
            if ch == chan:
                sd_token = sd['token']
                break
    if sd_token is None:
        return None

    sd = nusc.get('sample_data', sd_token)

    # --- charge l'image ---
    img_path = str(Path(DATAROOT) / sd['filename'])
    img = cv2.imread(img_path)
    if img is None:
        return None

    # --- extrinsics/intrinsics CAM_FRONT ---
    cs = nusc.get('calibrated_sensor', sd['calibrated_sensor_token'])
    cam_R_ego = quat_wxyz_to_R(*cs['rotation'])
    cam_t_ego = np.array(cs['translation'], float)

    ep = nusc.get('ego_pose', sd['ego_pose_token'])
    ego_R_glob = quat_wxyz_to_R(*ep['rotation'])
    ego_t_glob = np.array(ep['translation'], float)

    # caméra dans global
    R_cam_glob = ego_R_glob @ cam_R_ego
    t_cam_glob = ego_t_glob + ego_R_glob @ cam_t_ego

    K = np.array(cs['camera_intrinsic'], float)

    # --- retrouve scene & location (naïf mais OK viewer) ---
    scene = None
    for sc in nusc.scene:
        cur = sc['first_sample_token']
        while cur:
            if cur == sd['sample_token']:
                scene = sc
                break
            cur = nusc.get('sample', cur)['next']
        if scene:
            break

    scene_name = scene['name'] if scene else "unknown"
    location = nusc.get('log', scene['log_token'])['location'] if scene else "unknown"

    # --- vitesse ego (km/h) ---
    speed_kmh = speed_map.get(sd['sample_token'], None)

    # Bandeau header
    header = (
        f"{scene_name} | {chan} | Weather: {WEATHER} | Speed: {speed_kmh:.1f} km/h"
        if speed_kmh is not None
        else f"{scene_name} | {chan} | Weather: {WEATHER} | Speed: N/A"
    )
    draw_text_bg(img, header, (10, 30), font_scale=0.8, bg=(0,0,0))

    # --- récupère annotations piétons / véhicules sur ce sample ---
    anns_ped = [
        a for a in nusc.sample_annotation
        if a['sample_token'] == sd['sample_token'] and a['category_name'].startswith('human.pedestrian')
    ]
    anns_car = [
        a for a in nusc.sample_annotation
        if a['sample_token'] == sd['sample_token'] and a['category_name'].startswith('vehicle.')
    ]

    H, W = img.shape[:2]

    # =======================================================================
    # PIÉTONS : points + infos + GT
    # =======================================================================
    for ann in anns_ped:
        ped_xyz = np.array(ann['translation'], float)

        # distance & ahead dans repère ego
        d_long, d_lat = long_lat_from_global(ped_xyz, ego_t_glob, ep['rotation'])
        distance_m = float(math.hypot(d_long, d_lat))
        ahead = d_long > 0

        # hauteur (cm) avec fallback location
        try:
            h_cm = float(ann['size'][2]) * 100.0
        except Exception:
            h_cm = None
        if (h_cm is None) or not (HEIGHT_MIN_CM <= h_cm <= HEIGHT_MAX_CM):
            loc_mean = LOC_MEAN_HEIGHT_CM.get(location.lower())
            if loc_mean is not None:
                h_cm = loc_mean

        # on_drivable (si shapely dispo)
        on_drv = drv_cache.is_on_drivable(location, ped_xyz[0], ped_xyz[1]) if HAS_SHAPELY else None

        # GT crossing strict : sur drivable_area & ahead
        true_label = (on_drv is True) and ahead if (on_drv is not None) else None

        # projection du centre piéton dans l'image
        X = ped_xyz - t_cam_glob
        p_cam = R_cam_glob.T @ X
        if p_cam[2] <= 0:
            continue
        u = K[0,0]* (p_cam[0]/p_cam[2]) + K[0,2]
        v = K[1,1]* (p_cam[1]/p_cam[2]) + K[1,2]
        if not (0 <= u < W and 0 <= v < H):
            continue

        # couleur : vert=GT True, orange=GT False, gris=GT inconnu
        color = (
            (0,255,0) if true_label
            else (0,140,255) if (true_label is not None)
            else (128,128,128)
        )
        cv2.circle(img, (int(u), int(v)), 6, color, -1, cv2.LINE_AA)

        # étiquette multi-lignes
        lines = [
            f"id:{ann['instance_token'][:8]}",
            f"dist:{distance_m:.1f}m",
            f"h:{h_cm:.0f}cm" if h_cm is not None else "h:N/A",
            f"on_drv:{'T' if on_drv else ('F' if on_drv is False else 'NA')}",
            f"ahead:{'T' if ahead else 'F'}",
            f"GT:{'T' if true_label else ('F' if true_label is not None else 'N/A')}",
        ]
        y0 = int(max(0, v - 10))
        for i, t in enumerate(lines[::-1]):
            draw_text_bg(img, t, (int(u)+10, y0 - i*22), font_scale=0.6, bg=(0,0,0))

    # Prépare (token -> position) pour calculs véhicule↔piéton
    ped_list = [(ann['instance_token'], np.array(ann['translation'][:2], float)) for ann in anns_ped]
    ped_xyz_by_token = {a['instance_token']: np.array(a['translation'], float) for a in anns_ped}

    # =======================================================================
    # VÉHICULES : uniquement ceux avec 'vehicle.moving'
    # + distance au piéton le plus proche (avec contraintes)
    # + trait (jaune) véhicule↔piéton retenu
    # =======================================================================

    # vitesse ego monde (m/s), uniquement pour afficher une vitesse relative objet (optionnel)
    v_ego_world = ego_speed_vec_world(nusc, sd['sample_token'])

    # paramètres du filtrage de piétons candidats pour un véhicule
    AHEAD_LONG_MIN = 0.0   # piéton considéré "devant le véhicule" si dlong_v > 0
    LATERAL_GAP_MAX = 3.0  # bande latérale : pour exclure les piétons “entre ego et véhicule”

    for ann in anns_car:
        # 1) Filtre 'vehicle.moving'
        moving_flag = has_attr_vehicle_moving(nusc, ann)
        if moving_flag is not True:
            continue

        # 2) Dessin bbox 3D projetée
        box = Box(ann['translation'], ann['size'], Quaternion(ann['rotation']))
        box.translate(-t_cam_glob)
        box.rotate(Quaternion(matrix=R_cam_glob.T))

        corners = box.corners()
        if np.all(corners[2, :] <= 0):
            continue

        pts_2d = view_points(corners, K, normalize=True)[:2, :].T
        xmin, ymin = np.min(pts_2d[:, 0]), np.min(pts_2d[:, 1])
        xmax, ymax = np.max(pts_2d[:, 0]), np.max(pts_2d[:, 1])
        if xmax < 0 or ymax < 0 or xmin >= W or ymin >= H:
            continue

        p1 = (int(max(0, xmin)), int(max(0, ymin)))
        p2 = (int(min(W-1, xmax)), int(min(H-1, ymax)))
        cv2.rectangle(img, p1, p2, (255, 0, 0), 2)

        # 3) vitesse relative affichée (devkit box_velocity - ego_speed_vec_world)
        v_kmh_txt = "N/A"
        try:
            v_obj = np.array(nusc.box_velocity(ann['token']), dtype=float)  # m/s world
            if not np.any(np.isnan(v_obj)):
                if v_ego_world is not None:
                    v_obj = v_obj - v_ego_world
                v_xy_ms = float(np.linalg.norm(v_obj[:2]))
                v_kmh_txt = f"{v_xy_ms*3.6:.0f}"
        except Exception:
            pass

        # 4) sélection du piéton candidat le plus proche avec contraintes :
        #    - piéton DEVANT le véhicule (repère véhicule)
        #    - piéton PAS “entre ego et le véhicule” (repère ego + fenêtre latérale)
        veh_t = np.array(ann['translation'], float)   # (x,y,z) global
        veh_q = ann['rotation']                      # quaternion du véhicule

        # Position du véhicule dans repère ego (sert au test “entre”)
        veh_long_ego, veh_lat_ego = long_lat_from_global(veh_t, ego_t_glob, ep['rotation'])

        candidates = []  # (ped_token, dist_m)

        for ped_tok, ped_xy in ped_list:
            # 4.1 test "devant véhicule"
            ped_xyz_for_ref = np.array([ped_xy[0], ped_xy[1], veh_t[2]])
            dlong_v, dlat_v = long_lat_from_ref(ped_xyz_for_ref, veh_t, veh_q)
            if dlong_v <= AHEAD_LONG_MIN:
                continue

            # 4.2 exclut si piéton est entre ego et le véhicule (dans une bande latérale)
            ped_long_ego, ped_lat_ego = long_lat_from_global(
                np.array([ped_xy[0], ped_xy[1], veh_t[2]]),
                ego_t_glob,
                ep['rotation']
            )
            if (ped_long_ego < veh_long_ego) and (abs(ped_lat_ego - veh_lat_ego) <= LATERAL_GAP_MAX):
                continue

            # 4.3 distance XY
            dist_m = float(np.linalg.norm(veh_t[:2] - ped_xy))
            candidates.append((ped_tok, dist_m))

        # retient le piéton le plus proche parmi les candidats
        if candidates:
            ped_id_min, dmin = min(candidates, key=lambda x: x[1])
            d_txt = f"{dmin:.1f}"
            ped_id_txt = ped_id_min[:8]
        else:
            ped_id_min, dmin = None, None
            d_txt = "N/A"
            ped_id_txt = ""

        # 5) labels véhicule
        veh_type = ann['category_name'].split('.', 1)[-1]
        l1 = f"{veh_type} | v_rel:{v_kmh_txt}km/h"
        l2 = f"d_ped_min:{d_txt}m" + (f" id:{ped_id_txt}" if ped_id_txt else "")
        y_text = max(0, p1[1] - 6)
        draw_text_bg(img, l1, (p1[0], y_text), font_scale=0.6, bg=(0,0,0))
        draw_text_bg(img, l2, (p1[0], y_text - 22), font_scale=0.6, bg=(0,0,0))

        # 6) ligne (jaune) véhicule↔piéton retenu + distance
        if ped_id_min is not None:
            ped_xyz = ped_xyz_by_token.get(ped_id_min, None)
            if ped_xyz is not None:
                pt_veh = project_global_to_image(veh_t, R_cam_glob, t_cam_glob, K, W, H)
                pt_ped = project_global_to_image(ped_xyz, R_cam_glob, t_cam_glob, K, W, H)
                if pt_veh is not None and pt_ped is not None:
                    cv2.line(img, pt_veh, pt_ped, (0, 255, 255), 2, cv2.LINE_AA)
                    cv2.circle(img, pt_veh, 5, (0, 255, 255), -1, cv2.LINE_AA)
                    cv2.circle(img, pt_ped, 5, (0, 255, 255), -1, cv2.LINE_AA)
                    mid = ((pt_veh[0]+pt_ped[0])//2, (pt_veh[1]+pt_ped[1])//2)
                    draw_text_bg(img, f"{dmin:.1f} m", mid, font_scale=0.6, bg=(0,0,0))

    # =======================================================================
    # PASSAGES PIÉTONS : couche ped_crossing projetée
    # =======================================================================
    try:
        nmap = NuScenesMap(dataroot=DATAROOT, map_name=location)
        crossings = get_ped_crossings(nmap)

        for poly in crossings:
            coords = np.array(poly.exterior.coords)  # (N,2) global (x,y)
            pts = []

            # ⚠️ Ici tu fixes z=0.0 : c’est un choix de visualisation (pas forcément le sol réel).
            for (x, y) in coords:
                X = np.array([x, y, 0.0]) - t_cam_glob
                p_cam = R_cam_glob.T @ X
                if p_cam[2] <= 0:
                    continue
                u = int(K[0,0] * (p_cam[0]/p_cam[2]) + K[0,2])
                v = int(K[1,1] * (p_cam[1]/p_cam[2]) + K[1,2])
                pts.append((u, v))

            if len(pts) >= 2:
                cv2.polylines(img, [np.array(pts, np.int32)], isClosed=True, color=(0, 0, 255), thickness=2)

    except Exception as e:
        log.warning(f"Erreur passage piéton: {e}")

    # zoom (affichage)
    if abs(SCALE - 1.0) > 1e-3:
        img = cv2.resize(img, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_LINEAR)

    return img

# ======== Viewer interactif ========
def run_viewer():
    """
    Boucle interactive :
    - itère sur les scènes
    - filtre les samples qui ont CAM_FRONT keyframe
    - affiche chaque frame annotée
    """
    nusc = NuScenes(version=VERSION, dataroot=DATAROOT, verbose=False)
    scene_order = build_scene_sample_order(nusc)
    speed_map = build_speed_map_kmh(nusc, DATAROOT, scene_order)
    drv_cache = DrivableCache(dataroot=DATAROOT)

    scenes = nusc.scene
    if not scenes:
        print("Aucune scène.")
        return

    sidx = 0
    win = "nuScenes CAM_FRONT (GT)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    while True:
        scene = scenes[sidx]
        s_tokens = scene_order[scene['token']]

        # garde uniquement les samples qui possèdent le channel voulu (CAM_FRONT)
        cam_samples = []
        for s_tok in s_tokens:
            has = False
            # ⚠️ scan naïf sur sample_data : OK viewer, mais pas optimal.
            for sd in nusc.sample_data:
                if sd['sample_token'] == s_tok and sd['is_key_frame']:
                    cs = nusc.get('calibrated_sensor', sd['calibrated_sensor_token'])
                    ch = nusc.get('sensor', cs['sensor_token'])['channel']
                    if ch == CHANNEL:
                        has = True
                        break
            if has:
                cam_samples.append(s_tok)

        if not cam_samples:
            sidx = (sidx + 1) % len(scenes)
            continue

        fidx = 0
        while True:
            img = render_sample(nusc, cam_samples[fidx], CHANNEL, speed_map, drv_cache)

            if img is None:
                disp = np.zeros((720, 1280, 3), dtype=np.uint8)
                cv2.putText(disp, "Image indisponible", (40, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            else:
                disp = img

            # barre d’aide
            helpbar = "j/k=±1  n/p=scène ±1  q=quit"
            cv2.rectangle(disp, (0, disp.shape[0]-28), (disp.shape[1], disp.shape[0]), (0,0,0), -1)
            cv2.putText(disp, helpbar, (10, disp.shape[0]-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1, cv2.LINE_AA)

            cv2.imshow(win, disp)
            key = cv2.waitKey(0) & 0xFF

            if key in (ord('q'), 27):
                cv2.destroyAllWindows()
                return
            elif key == ord('j') or key == ord(' '):
                fidx = min(fidx + 1, len(cam_samples)-1)
            elif key == ord('k'):
                fidx = max(fidx - 1, 0)
            elif key == ord('n'):
                sidx = (sidx + 1) % len(scenes)
                break
            elif key == ord('p'):
                sidx = (sidx - 1) % len(scenes)
                break

if __name__ == "__main__":
    run_viewer()
