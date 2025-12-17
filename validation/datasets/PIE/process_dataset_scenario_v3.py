import os
from pathlib import Path
import cv2
from tqdm import tqdm
import importlib.util
import math
import csv
from collections import defaultdict
import numpy as np
import json
import xml.etree.ElementTree as ET

# ------------------------------------------------------------------
# DEBUG: dessiner crosswalk + feux "en hint" même si la rule sélectionnée
#       n'est pas crossing street / red light
# ------------------------------------------------------------------
DEBUG_DRAW_SIGNALIZATION_WHEN_NOT_SELECTED = True

# Distance en dessous de laquelle on considère qu’un véhicule a "dépassé" le piéton
# (dans l'espace de distance sol approx véhicule<->piéton calculée via modèle)
PASSED_VEHICLE_DISTANCE_EPS = 0.2  # mètres

# =========================
# Chargement du modèle externe
# =========================
# Le modèle "CNRS_behavior_model.py" est chargé dynamiquement pour éviter
# d'en faire une dépendance pip/packagée. On récupère ensuite
# module.pedestrian_behavior_model(...)
file_path = r"E:\crossing-model\main_experiment\model_datas\CNRS_behavior_model.py"
spec = importlib.util.spec_from_file_location("pedestrian_behavior_model", file_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# =========================
# Utils généraux
# =========================
def haversine(lat1, lon1, lat2, lon2):
    """
    Distance en mètres entre deux points GPS (WGS84) via formule de Haversine.

    ⚠️ Ici cette distance est utilisée comme:
      - "distance ego->piéton" (au sol) dans PIE,
      - et sert aussi comme proxy de "profondeur" Z_ped pour certains calculs.
    """
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    R = 6371000
    return R*c

def load_camera_params(camera_params_path):
    """Charge le JSON de calibration (intrinsèques K, pitch, etc.)."""
    with open(camera_params_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_cam_height_m(camera_params):
    """
    Récupère la hauteur caméra si dispo.
    Accepte:
      - cam_height_m
      - cam_height_mm (converti en m)

    Utilisé pour estimer la profondeur au sol d’un point via un modèle plan-sol.
    """
    if "cam_height_m" in camera_params and camera_params["cam_height_m"] is not None:
        return float(camera_params["cam_height_m"])
    if "cam_height_mm" in camera_params and camera_params["cam_height_mm"] is not None:
        return float(camera_params["cam_height_mm"]) / 1000.0
    return None

def calculate_real_size(bbox, distance, camera_params):
    """
    Estime taille réelle d'un objet à partir de:
      - taille bbox en pixels
      - distance au sol (ici distance GPS ego->piéton)
      - calibration (fx, fy) + pitch caméra

    ⚠️ Hypothèses:
      - le piéton est approximativement à la distance 'distance'
      - correction pitch simple via cos(pitch)
    """
    K = np.array(camera_params['K'])
    cam_pitch_deg = camera_params['cam_pitch_deg']

    xtl, ytl, xbr, ybr = bbox
    width_pixel = xbr - xtl
    height_pixel = ybr - ytl
    if width_pixel <= 0 or height_pixel <= 0:
        return None, None

    f_x = K[0,0]
    f_y = K[1,1]
    cam_pitch_rad = math.radians(cam_pitch_deg)

    real_height_m = (height_pixel * distance) / (f_y * math.cos(cam_pitch_rad))
    real_width_m  = (width_pixel  * distance) / (f_x * math.cos(cam_pitch_rad))
    return real_width_m, real_height_m

# =========================
# Géométrie / IoU / Proximité
# =========================
def iou(a, b):
    """Intersection over Union entre deux bbox 2D (xtl,ytl,xbr,ybr)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1); inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2); inter_y2 = min(ay2, by2)
    iw = max(0.0, inter_x2 - inter_x1); ih = max(0.0, inter_y2 - inter_y1)
    inter = iw * ih
    area_a = max(0.0, (ax2-ax1)) * max(0.0, (ay2-ay1))
    area_b = max(0.0, (bx2-bx1)) * max(0.0, (by2-by1))
    union = area_a + area_b - inter if (area_a + area_b - inter) > 0 else 1e-9
    return inter / union

def inter_over_ped_area(ped_box, cross_box):
    """Intersection / aire bbox piéton: utile pour tester si piéton est sur crosswalk."""
    px1, py1, px2, py2 = ped_box
    cx1, cy1, cx2, cy2 = cross_box
    ix1, iy1 = max(px1, cx1), max(py1, cy1)
    ix2, iy2 = min(px2, cx2), min(py2, cy2)
    iw, ih = max(0.0, ix2-ix1), max(0.0, iy2-iy1)
    inter = iw*ih
    ped_area = max(0.0, (px2-px1)) * max(0.0, (py2-py1))
    return inter / (ped_area + 1e-9)

def point_in_box(x, y, box, pad=0):
    """Test point dans bbox (avec padding optionnel)."""
    x1, y1, x2, y2 = box
    return (x1 - pad) <= x <= (x2 + pad) and (y1 - pad) <= y <= (y2 + pad)

def ped_foot_point(ped_box):
    """Point 'pied' approx du piéton: centre-bas de bbox."""
    x1, y1, x2, y2 = ped_box
    return (0.5*(x1+x2), y2)

def bottom_center(box):
    """Centre-bas de bbox (utilisé comme point de contact sol approx)."""
    x1, y1, x2, y2 = box
    return 0.5*(x1+x2), y2

def bbox_height(b):
    return float(b[3] - b[1])

def bbox_width(b):
    return float(b[2] - b[0])

def bbox_center_x(b):
    return 0.5 * (float(b[0] + b[2]))

def x_overlap_amount(b1, b2):
    """Longueur d'overlap horizontal entre deux bbox."""
    return max(0.0, min(b1[2], b2[2]) - max(b1[0], b2[0]))

def draw_vehicle_bbox(img, bbox, label, color_bgr, thickness=2):
    """Dessin simple bbox véhicule + texte."""
    x1, y1, x2, y2 = map(int, bbox)
    cv2.rectangle(img, (x1, y1), (x2, y2), color_bgr, thickness)
    cv2.putText(img, label, (x1, max(0, y1-5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_bgr, 2)

# =========================
# Chargement annotations piétons
# - On conserve uniquement les piétons qui ont au moins une frame "looking"
# - On garde les labels cross ("crossing"/"not-crossing") par frame
# =========================
def load_pedestrians(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    pedestrian_data = defaultdict(list)
    first_looking_frame = {}

    for track in root.findall("track"):
        if track.attrib.get("label") == "pedestrian":
            ped_id = None
            looking_frames = []
            crossing_data = []

            for box in track.findall("box"):
                frame = int(box.get("frame"))
                cross_value = None

                for attr in box.findall("attribute"):
                    name = (attr.get("name") or "").strip().lower()
                    val  = (attr.text or "").strip()

                    if name == "id":
                        ped_id = val
                    elif name == "look" and val.lower() == "looking":
                        looking_frames.append(frame)
                    elif name == "cross":
                        cross_value = val

                # On stocke les labels cross frame par frame
                if cross_value and ped_id:
                    crossing_data.append((frame, cross_value))

            # Filtre: ne conserver que les piétons qui ont "looking" au moins une fois
            # et un minimum de labels cross disponibles
            if ped_id and looking_frames and crossing_data:
                pedestrian_data[ped_id] = crossing_data
                first_looking_frame[ped_id] = min(looking_frames)

    return pedestrian_data, first_looking_frame

def load_pedestrian_boxes(xml_path, pedestrian_id):
    """Charge la bbox du piéton id pour chaque frame."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    boxes = {}
    for track in root.findall("track"):
        if track.attrib.get("label") == "pedestrian":
            for box in track.findall("box"):
                pid = box.find("attribute[@name='id']")
                if pid is not None and pid.text == pedestrian_id:
                    fid = int(box.attrib["frame"])
                    xtl = float(box.attrib["xtl"])
                    ytl = float(box.attrib["ytl"])
                    xbr = float(box.attrib["xbr"])
                    ybr = float(box.attrib["ybr"])
                    boxes[fid] = (xtl, ytl, xbr, ybr)
    return boxes

def load_gps_data(xml_path):
    """Charge lat/lon + vitesse OBD (km/h) par frame depuis *_obd.xml."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    gps = {}
    for frame in root.findall("frame"):
        fid = int(frame.attrib["id"])
        gps[fid] = {
            "lat": float(frame.attrib["latitude"]),
            "lon": float(frame.attrib["longitude"]),
            "speed": float(frame.attrib["OBD_speed"])
        }
    return gps

# =========================
# Crosswalks + feux piétons + état (vert/rouge/...)
# =========================
def load_crosswalk_and_ped_lights_with_state(xml_path):
    """
    Parse le même fichier d'annotation XML:
      - track label="crosswalk": bbox crosswalk
      - track label="traffic_light": on garde uniquement type=pedestrian + état
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    crosswalk_boxes = defaultdict(list)
    ped_lights = defaultdict(list)

    for track in root.findall("track"):
        label = track.attrib.get("label")
        if label in ("crosswalk", "traffic_light"):
            for box in track.findall("box"):
                frame_id = int(box.attrib["frame"])
                xtl = float(box.attrib["xtl"]); ytl = float(box.attrib["ytl"])
                xbr = float(box.attrib["xbr"]); ybr = float(box.attrib["ybr"])

                if label == "crosswalk":
                    crosswalk_boxes[frame_id].append((xtl, ytl, xbr, ybr))

                elif label == "traffic_light":
                    # On filtre sur les feux piétons uniquement
                    is_ped = False
                    state = "unknown"

                    for attr in box.findall("attribute"):
                        n = (attr.get("name") or "").strip().lower()
                        v = (attr.text or "").strip().lower()
                        if n == "type" and v == "pedestrian":
                            is_ped = True
                        if n in ("status","state","color"):
                            if "green" in v: state = "green"
                            elif "red"  in v: state = "red"
                            elif "yellow" in v: state = "yellow"
                            else: state = "unknown"

                    if is_ped:
                        ped_lights[frame_id].append({"bbox": (xtl, ytl, xbr, ybr), "state": state})

    return crosswalk_boxes, ped_lights

def get_ped_light_state_for_bbox(fid, ped_box, ped_lights, proximity_px=260):
    """
    Associe au piéton le feu piéton "le plus proche" dans l'image (distance pixels)
    par rapport au point pied du piéton.

    Retourne:
      (state, bbox_du_feu) ou ("unknown", None)
    """
    footx, footy = ped_foot_point(ped_box)
    best = None
    best_d2 = None

    for entry in ped_lights.get(fid, []):
        (lx1, ly1, lx2, ly2) = entry["bbox"]
        lcx, lcy = 0.5*(lx1+lx2), 0.5*(ly1+ly2)
        d2 = (lcx-footx)**2 + (lcy-footy)**2
        if best is None or d2 < best_d2:
            best, best_d2 = entry, d2

    if best is None:
        return "unknown", None
    if (best_d2 ** 0.5) > proximity_px:
        return "unknown", None
    return best.get("state","unknown"), best["bbox"]

def crosswalk_green_select(fid, ped_box, crosswalk_boxes, ped_lights,
                           iou_thr=0.003, ped_inter_thr=0.02, foot_pad_px=14):
    """
    Règle "crossing street":
      - feu piéton vert proche du piéton
      - piéton considéré "sur crosswalk" (IoU / inter / pied dans bbox)

    Retour: (ok, cw_bbox, light_bbox)
    """
    cws = crosswalk_boxes.get(fid, [])
    if not cws:
        return False, None, None

    # feu vert proche ?
    state_near_ped, light_near_ped_bbox = get_ped_light_state_for_bbox(fid, ped_box, ped_lights)
    if state_near_ped != "green" or light_near_ped_bbox is None:
        return False, None, None

    footx, footy = ped_foot_point(ped_box)

    best_cw = None
    best_score = None
    for cw in cws:
        on_cw = (
            iou(ped_box, cw) >= iou_thr or
            inter_over_ped_area(ped_box, cw) >= ped_inter_thr or
            point_in_box(footx, footy, cw, pad=foot_pad_px)
        )
        if not on_cw:
            continue

        # Score: IoU + intersection - distance (heuristique)
        cx1, cy1, cx2, cy2 = cw
        ccx, ccy = 0.5*(cx1+cx2), 0.5*(cy1+cy2)
        d2 = (ccx-footx)**2 + (ccy-footy)**2
        score = 5.0 * iou(ped_box, cw) + 3.0 * inter_over_ped_area(ped_box, cw) - 0.001 * d2

        if best_cw is None or score > best_score:
            best_cw, best_score = cw, score

    if best_cw is None:
        return False, None, None

    return True, best_cw, light_near_ped_bbox

# =========================
# Véhicules + "behavior" + distance véhicule↔piéton au sol
# =========================
def load_vehicles_with_behavior(xml_path, frame_id):
    """
    Extrait toutes les bbox véhicule à la frame donnée.
    On récupère l'attribut "behavior" (si présent):
      - prioritaire au niveau box
      - sinon fallback au niveau track

    Retour:
      [{bbox, behavior, track_id}, ...]
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    res = []

    for track in root.findall("track"):
        if track.attrib.get("label") != "vehicle":
            continue

        track_id = track.attrib.get("id")

        # behavior fallback au niveau track
        track_behavior = None
        if "behavior" in track.attrib:
            track_behavior = (track.attrib.get("behavior") or "").strip().lower()
        if not track_behavior:
            for attr in track.findall("attribute"):
                if (attr.get("name") or "").strip().lower() == "behavior":
                    track_behavior = (attr.text or "").strip().lower()

        for box in track.findall("box"):
            if int(box.attrib.get("frame")) != frame_id:
                continue

            xtl = float(box.attrib["xtl"]); ytl = float(box.attrib["ytl"])
            xbr = float(box.attrib["xbr"]); ybr = float(box.attrib["ybr"])

            # behavior au niveau box (prioritaire)
            behavior_box = None
            for attr in box.findall("attribute"):
                if (attr.get("name") or "").strip().lower() == "behavior":
                    behavior_box = (attr.text or "").strip().lower()
                    break

            behavior = behavior_box if behavior_box else track_behavior

            res.append({
                "bbox": (xtl, ytl, xbr, ybr),
                "behavior": behavior,
                "track_id": track_id
            })

    return res

def lateral_X_at_depth(u, Z, K):
    """Convertit un pixel u à une coordonnée latérale X à profondeur Z (modèle pinhole)."""
    fx = K[0,0]; cx = K[0,2]
    return ((u - cx) / max(1e-9, fx)) * Z

def estimate_depth_from_ground_ratio(Z_ped, ped_box, obj_box, K):
    """
    Fallback historique:
      Z_obj = Z_ped * ( (yb_p - cy) / (yb_o - cy) )
    basé sur la position verticale des points bas (sol) dans l'image.
    """
    cy = K[1,2]
    _, yb_p = bottom_center(ped_box)
    _, yb_o = bottom_center(obj_box)
    eps = 1e-6
    Z_obj = Z_ped * (max(eps, yb_p - cy) / max(eps, yb_o - cy))
    return max(0.05, min(5000.0, float(Z_obj)))

def estimate_depth_ground_model(yb, K, cam_pitch_deg, cam_height_m):
    """
    Estimation Z d'un point au SOL (contact) depuis sa coordonnée yb.

    Hypothèse: plan-sol + caméra à hauteur H + pitch θ.
    (Formule heuristique pratique pour transformer pixel->Z)
    """
    fy = K[1,1]; cy = K[1,2]
    theta = math.radians(cam_pitch_deg)
    v = (yb - cy)
    num = cam_height_m * (fy * math.cos(theta) - v * math.sin(theta))
    den = (v * math.cos(theta) + fy * math.sin(theta))
    eps = 1e-6
    Z = num / max(eps, den)
    return float(max(0.05, min(5000.0, Z)))

def vehicle_to_ped_ground_distance(Z_ped, ped_box, veh_box, camera_params):
    """
    Approx distance au sol entre piéton et véhicule:
      d = sqrt( (Z_p - Z_v)^2 + (X_p - X_v)^2 )

    Z_v:
      - si cam_height_m disponible: modèle plan-sol via y bas
      - sinon: fallback ratio basé sur Z_ped
    """
    K = np.array(camera_params['K'])
    cam_pitch_deg = float(camera_params.get('cam_pitch_deg', 0.0))
    cam_height_m = get_cam_height_m(camera_params)

    u_ped, yb_p = bottom_center(ped_box)
    u_veh, yb_v = bottom_center(veh_box)

    if cam_height_m is not None:
        try:
            Z_veh = estimate_depth_ground_model(yb_v, K, cam_pitch_deg, float(cam_height_m))
        except Exception:
            Z_veh = estimate_depth_from_ground_ratio(Z_ped, ped_box, veh_box, K)
    else:
        Z_veh = estimate_depth_from_ground_ratio(Z_ped, ped_box, veh_box, K)

    X_ped = lateral_X_at_depth(u_ped, Z_ped, K)
    X_veh = lateral_X_at_depth(u_veh, Z_veh, K)

    dZ = Z_ped - Z_veh
    dX = X_ped - X_veh
    d = (dZ**2 + dX**2) ** 0.5

    return float(max(0.01, min(1e4, d))), float(max(0.05, min(5000.0, Z_veh)))

def pick_closest_behavior_vehicle(vehicles, ped_box, Z_ped, camera_params,
                                  not_passed_margin_m=0.5, lateral_factor=1.2):
    """
    Sélection du véhicule "pertinent" pour la rule 'other vehicle'.

    Objectif:
      - on ne veut considérer que des véhicules:
        * behavior ∈ {"ahead", "in the next lane"}
        * encore "devant" le piéton dans l'axe Z (Z_veh < Z_ped - marge)
      - passe 1 stricte: overlap horizontal OU centres proches (gating latéral)
      - passe 2 relâchée: si aucun strict, on prend le plus proche parmi les admissibles
        sans gating latéral (mais toujours Z_veh < Z_ped - marge)

    Retour:
      (vehicule_dict, d_other) ou (None, None)
    """
    ALLOWED = {"ahead", "in the next lane"}

    def lateral_ok(vbbox):
        ped_w = max(1.0, bbox_width(ped_box))
        cx_p = bbox_center_x(ped_box)
        cx_v = bbox_center_x(vbbox)
        overlap = x_overlap_amount(vbbox, ped_box) > 0.0
        close_centers = abs(cx_v - cx_p) <= max(lateral_factor * ped_w, 10.0)
        return overlap or close_centers

    best = None
    best_d = None

    strict_candidates = []
    loose_candidates  = []

    for v in vehicles:
        beh = (v.get("behavior") or "").strip().lower()
        if beh not in ALLOWED:
            continue

        d_other, Z_veh = vehicle_to_ped_ground_distance(Z_ped, ped_box, v["bbox"], camera_params)

        # filtre "pas encore passé" (toujours devant)
        if Z_veh >= (Z_ped - not_passed_margin_m):
            continue

        entry = (v, d_other, Z_veh)

        if lateral_ok(v["bbox"]):
            strict_candidates.append(entry)
        else:
            loose_candidates.append(entry)

    # passe 1: stricts
    for v, d_other, Z_veh in strict_candidates:
        if (best is None) or (d_other < best_d):
            best, best_d = v, d_other

    # passe 2: loose si aucun strict
    if best is None and loose_candidates:
        for v, d_other, Z_veh in loose_candidates:
            if (best is None) or (d_other < best_d):
                best, best_d = v, d_other

    return best, best_d

# =========================
# Annotation image (overlay)
# - bbox piéton + infos (distance, speed, weather, etc.)
# - bbox crosswalk + feu piéton si rule active
# - bbox véhicules (couleurs différenciées)
# - hints optionnels (debug)
# =========================
def annotate_image(
    img, bbox, distance, real_height, weather, velocity,
    crossing, cross_label, scenario_tag,
    veh_distance=None, veh_velocity=None, veh_behavior=None, veh_bbox=None,
    crosswalk_bbox=None, ped_light_bbox=None,                       # actifs
    crosswalk_bbox_hint=None, ped_light_bbox_hint=None,             # hints
    ped_light_state_hint=None
):
    xtl, ytl, xbr, ybr = map(int, bbox)
    h, w = img.shape[:2]
    center_pedestrian = ((xtl + xbr) // 2, (ytl + ybr) // 2)
    bottom_center_pt = (w // 2, h)

    # bbox piéton (vert) + ligne ego->piéton (rouge)
    cv2.rectangle(img, (xtl, ytl), (xbr, ybr), (0, 255, 0), 2)
    cv2.line(img, bottom_center_pt, center_pedestrian, (0, 0, 255), 2)

    # véhicule utilisé (other vehicle): bbox bleu épaisse
    if scenario_tag == "other vehicle" and veh_bbox is not None:
        vxtl, vytl, vxbr, vybr = map(int, veh_bbox)
        cv2.rectangle(img, (vxtl, vytl), (vxbr, vybr), (255, 0, 0), 3)
        cv2.putText(img, "vehicle", (vxtl, max(0, vytl-5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

    # crosswalk + feu piéton (actifs si rule crossing street / red light)
    if scenario_tag in ("crossing street", "red light"):
        if crosswalk_bbox is not None:
            cxtl, cytl, cxbr, cybr = map(int, crosswalk_bbox)
            cv2.rectangle(img, (cxtl, cytl), (cxbr, cybr), (0, 255, 255), 2)
            cv2.putText(img, "crosswalk", (cxtl, max(0, cytl-5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        if ped_light_bbox is not None:
            lxtl, lytl, lxbr, lybr = map(int, ped_light_bbox)
            cv2.rectangle(img, (lxtl, lytl), (lxbr, lybr), (255, 0, 255), 2)
            label = "ped light (green)" if scenario_tag == "crossing street" else "ped light (red)"
            cv2.putText(img, label, (lxtl, max(0, lytl-5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

    # hints (debug) si rule non sélectionnée
    if scenario_tag not in ("crossing street", "red light") and DEBUG_DRAW_SIGNALIZATION_WHEN_NOT_SELECTED:
        if crosswalk_bbox_hint is not None:
            cxtl, cytl, cxbr, cybr = map(int, crosswalk_bbox_hint)
            cv2.rectangle(img, (cxtl, cytl), (cxbr, cybr), (160, 200, 200), 2)
            cv2.putText(img, "crosswalk (hint)", (cxtl, max(0, cytl-5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (160, 200, 200), 2)
        if ped_light_bbox_hint is not None:
            lxtl, lytl, lxbr, lybr = map(int, ped_light_bbox_hint)
            cv2.rectangle(img, (lxtl, lytl), (lxbr, lybr), (200, 160, 220), 2)
            state_txt = f"ped light ({ped_light_state_hint or 'unk'})"
            cv2.putText(img, state_txt, (lxtl, max(0, lytl-5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 160, 220), 2)

    # Bloc infos (distance / height / weather / speed / pred)
    cv2.putText(img, f"{distance:.2f} m", (bottom_center_pt[0]+10, bottom_center_pt[1]-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)
    if real_height is not None:
        cv2.putText(img, f"{round(real_height)} cm", (bottom_center_pt[0]+10, bottom_center_pt[1]-40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)
    cv2.putText(img, weather, (bottom_center_pt[0]+10, bottom_center_pt[1]-70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)
    cv2.putText(img, f"{velocity:.2f} km/h", (bottom_center_pt[0]+10, bottom_center_pt[1]-100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

    color = (0,40,255) if crossing else (0,255,40)
    cv2.putText(img, "crossing" if crossing else "not-crossing",
                (bottom_center_pt[0]+10, bottom_center_pt[1]-130),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # GT vs Pred
    cv2.putText(img, f"GT: {cross_label} | Pred: {crossing}", (10,50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)

    # Rule appliquée pour la frame
    cv2.putText(img, f"Rule: {scenario_tag}", (10,90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,200,0), 2)

    # Infos véhicule si rule other vehicle
    if scenario_tag == "other vehicle" and (veh_distance is not None or veh_velocity is not None or veh_behavior is not None):
        cv2.putText(img, f"Veh: {veh_behavior or ''}", (10,130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200,255,0), 2)
        txt = ""
        if veh_distance is not None: txt += f"d={veh_distance:.1f}m"
        if veh_velocity is not None: txt += (" | " if txt else "") + f"v={veh_velocity:.1f} km/h"
        if txt:
            cv2.putText(img, txt, (10,160),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200,255,0), 2)

    return img

# =========================
# Hints (crosswalk / feu) pour affichage debug
# =========================
def nearest_crosswalk_and_light(fid, ped_box, crosswalk_boxes, ped_lights):
    """
    Renvoie:
      - une crosswalk "la plus pertinente" (overlap ou la plus proche)
      - le feu piéton le plus proche (pixel)
      - l'état du feu associé (state)
    Utilisé uniquement pour l'affichage debug quand la rule sélectionnée n'est pas
    "crossing street" / "red light".
    """
    cw_hint = None
    best_cw_score = None
    footx, footy = ped_foot_point(ped_box)

    for cw in crosswalk_boxes.get(fid, []):
        overlap = iou(ped_box, cw) + inter_over_ped_area(ped_box, cw)
        if overlap > 0:
            score = 1000.0 + overlap
        else:
            cx1, cy1, cx2, cy2 = cw
            ccx, ccy = 0.5*(cx1+cx2), 0.5*(cy1+cy2)
            d2 = (ccx-footx)**2 + (ccy-footy)**2
            score = -d2
        if best_cw_score is None or score > best_cw_score:
            best_cw_score = score
            cw_hint = cw

    light_hint = None
    light_state_hint = None
    best_d2 = None
    for entry in ped_lights.get(fid, []):
        (lx1, ly1, lx2, ly2) = entry["bbox"]
        lcx, lcy = 0.5*(lx1+lx2), 0.5*(ly1+ly2)
        d2 = (lcx-footx)**2 + (lcy-footy)**2
        if best_d2 is None or d2 < best_d2:
            best_d2 = d2
            light_hint = entry["bbox"]
            light_state_hint = entry.get("state","unknown")

    return cw_hint, light_hint, light_state_hint

# =========================
# Pipeline principal (API)
# =========================
def process_dataset(
    images_path,
    annotations_path,
    annotations_vehicle_path,
    camera_params_path,
    output_path,
    adj: bool = True,
    intention: bool = False,
    save_video: bool = False,
    # --- rules flags ---
    use_green_light_rule: bool = False,
    use_red_light_rule: bool = False,
    # compat: ancien flag => active green + red
    use_crosswalk_rule: bool = False,
    use_other_vehicle_model: bool = False,
    fps_images: int = 25
):
    """
    Point d'entrée appelé par run_batches_opt (ou un appel direct).

    images_path:
      - soit .../images avec des sous-dossiers setXX/video_YYYY
      - soit directement un dossier contenant video_YYYY (cas batch monté)
    """
    images_path = Path(images_path)
    annotations_path = Path(annotations_path)
    annotations_vehicle_path = Path(annotations_vehicle_path)
    output_base = Path(output_path)
    camera_params_path = Path(camera_params_path)

    # Cas normal: images_path contient set01, set02, ...
    sets = sorted(images_path.glob("set*"))

    # Cas batch: images_path peut contenir directement des video_*
    if len(sets) == 0:
        video_folders = sorted(images_path.glob("video_*"))
        if not video_folders:
            print("Aucun set ni vidéo trouvé dans le dossier images_path")
            return
        for video_folder in video_folders:
            set_name = video_folder.parent.name   # peut être "images" ou "set03" selon montage
            video_name = video_folder.name
            _process_single_video(
                set_name, video_name, video_folder,
                annotations_path, annotations_vehicle_path,
                camera_params_path, output_base,
                adj, intention, save_video,
                use_green_light_rule, use_red_light_rule, use_crosswalk_rule,
                use_other_vehicle_model, fps_images
            )
    else:
        for set_folder in sets:
            set_name = set_folder.name
            video_folders = sorted(set_folder.glob("video_*"))
            for video_folder in video_folders:
                video_name = video_folder.name
                _process_single_video(
                    set_name, video_name, video_folder,
                    annotations_path, annotations_vehicle_path,
                    camera_params_path, output_base,
                    adj, intention, save_video,
                    use_green_light_rule, use_red_light_rule, use_crosswalk_rule,
                    use_other_vehicle_model, fps_images
                )

def _process_single_video(set_name, video_name, path_imgs, annotations_path, annotations_vehicle_path,
                          camera_params_path, output_base, adj, intention, save_video,
                          use_green_light_rule, use_red_light_rule, use_crosswalk_rule,
                          use_other_vehicle_model, fps_images):
    """
    Traitement complet d'une vidéo PIE (setXX/video_YYYY):
      - charge annotations piétons, GPS, crosswalks, feux, véhicules
      - pour chaque piéton admissible:
          * boucle frame par frame
          * calc distance (GPS->ref) + vitesse
          * calc taille piéton (une fois)
          * applique rules (priorité)
          * sauvegarde CSV (et images/vidéo si save_video)
    """
    print(f"Traitement de {set_name}/{video_name}")

    # Fichiers annotations (piétons, crosswalk, feux, véhicules) et OBD (gps/speed)
    path_ann = annotations_path / set_name / f"{video_name}_annt.xml"
    path_obd = annotations_vehicle_path / set_name / f"{video_name}_obd.xml"

    # Dossier de sortie par vidéo
    output_folder = output_base / f"{set_name}-{video_name.split('_')[-1]}"
    output_folder.mkdir(parents=True, exist_ok=True)

    # Charge piétons + frame de premier "looking"
    pedestrian_data, first_looking_frame = load_pedestrians(path_ann)

    # Calibration caméra
    camera_params = load_camera_params(camera_params_path)

    # Crosswalks + feux
    crosswalk_boxes, ped_lights = load_crosswalk_and_ped_lights_with_state(path_ann)

    print(f"{len(pedestrian_data)} piétons détectés")

    # Compat: use_crosswalk_rule active green+red
    use_green_rule = bool(use_green_light_rule or use_crosswalk_rule)
    use_red_rule   = bool(use_red_light_rule   or use_crosswalk_rule)

    # =========================================================
    # Loop piétons
    # =========================================================
    for ped_id, data in pedestrian_data.items():
        frames = [frame for frame, cross in data]
        start_frame = min(frames)

        # mode "intention": démarrer au premier regard du piéton (looking)
        if intention and ped_id in first_looking_frame:
            start_frame = first_looking_frame[ped_id]

        end_frame = max(frames)

        print(f"Piéton {ped_id}")

        # Sorties
        comparisons = []  # lignes CSV
        cross_labels = dict(pedestrian_data[ped_id])
        output_video_path = output_folder / ped_id / "video" / "features_extracted.mp4"
        results_path = output_folder / f"crossing_results_{ped_id}.csv"

        # Skip si déjà traité
        if results_path.exists():
            print(f"CSV déjà existante pour {ped_id}, skip.")
            continue

        pedestrian_boxes = load_pedestrian_boxes(path_ann, ped_id)
        gps_data = load_gps_data(path_obd)

        # Référence: dernière frame (end_frame) utilisée comme point "piéton"
        # => distance = haversine(lat,lon, lat_ref,lon_ref)
        if end_frame not in gps_data:
            print(f"Données GPS manquantes pour frame {end_frame}")
            continue
        lat_ref, lon_ref = gps_data[end_frame]["lat"], gps_data[end_frame]["lon"]

        frame_size = None
        has_height = False

        # Persistance: mémoriser les véhicules "passés" pour ne plus les considérer
        passed_vehicle_ids = set()

        # =========================================================
        # Loop frames
        # =========================================================
        for fid in tqdm(range(start_frame, end_frame+1), desc=f"Frames piéton {ped_id}"):
            img_path = path_imgs / f"{fid:05}.png"
            img = cv2.imread(str(img_path))
            if img is None:
                tqdm.write(f"Image absente/corrompue frame {fid}")
                continue

            # On exige GPS + bbox piéton à la frame
            if fid not in gps_data or fid not in pedestrian_boxes:
                tqdm.write(f"GPS ou box manquante frame {fid}")
                continue

            # Label GT: crossing / not-crossing uniquement
            cross_label = cross_labels.get(fid, "None")
            if cross_label not in ("crossing", "not-crossing"):
                tqdm.write(f"Label {cross_label}")
                continue

            bbox = pedestrian_boxes[fid]

            # Weather PIE: ici forcé à "clear" (annotation météo non incluse ici)
            weather = 'clear'

            # Vitesse ego (OBD_speed) + distance (haversine vers point de ref)
            lat, lon, velocity = gps_data[fid]["lat"], gps_data[fid]["lon"], gps_data[fid]["speed"]
            Z_ped = haversine(lat, lon, lat_ref, lon_ref)  # proxy profondeur/distance ego->piéton

            # --- calcul taille piéton: une seule fois, si bbox pas proche bord ---
            h, w = img.shape[:2]
            margin_x = w * 0.1
            margin_y = h * 0.1
            xtl, ytl, xbr, ybr = bbox

            # Si on n'a pas encore la taille et que le piéton est trop proche du bord, on skip le piéton entier
            if not has_height and (xtl < margin_x or xbr > (w - margin_x) or ytl < margin_y or ybr > (h - margin_y)):
                tqdm.write(f"Piéton {ped_id} trop proche bord frame {fid}, skip piéton.")
                break

            if not has_height:
                _, real_height_m = calculate_real_size(bbox, Z_ped, camera_params)
                if real_height_m is None:
                    tqdm.write(f"Erreur taille piéton {ped_id} frame {fid}")
                    break
                real_height = real_height_m * 100  # cm

                # Clamp simple: si hors [150,200] -> valeur moyenne
                if (real_height < 150) or (real_height > 200):
                    real_height = 171

                has_height = True

            # =========================================================
            # ===== RÈGLES (ordre de priorité STRICT) ==================
            # ---------------------------------------------------------
            # 0) Base: modèle ego (distance ego->piéton + vitesse ego)
            # 0bis) 20km/h rule: si vitesse < 20 => crossing True
            # 1) RED LIGHT (si activée): si feu piéton rouge => crossing False (override)
            # 2) GREEN + CROSSWALK (si activée): feu vert + piéton sur crosswalk => crossing True (override)
            # 3) OTHER VEHICLE (si activée): sélectionner véhicule ahead/next lane et appeler modèle sur dist véhicule
            # =========================================================
            scenario_tag = "ego"

            # 0) modèle sur ego-distance
            crossing = module.pedestrian_behavior_model(weather, real_height, velocity, Z_ped, adj)

            # 0bis) règle conservatrice: si véhicule lent => autoriser crossing
            if velocity < 20:
                crossing = True

            # éléments utilisés pour dessin (si rule active)
            crosswalk_bbox_draw = None
            ped_light_bbox_draw = None

            vehicles_here = []  # véhicules à cette frame (chargés si besoin)

            # 1) RED LIGHT RULE (priorité absolue)
            red_state, red_bbox = get_ped_light_state_for_bbox(fid, bbox, ped_lights)
            if use_red_rule and (red_state == "red") and (red_bbox is not None):
                scenario_tag = "red light"
                crossing = False
                ped_light_bbox_draw = red_bbox

                # utile pour overlay debug (bbox véhicules)
                vehicles_here = load_vehicles_with_behavior(path_ann, fid)

            else:
                # 2) GREEN LIGHT + CROSSWALK RULE
                cross_ok, cw_bbox, pl_bbox = (False, None, None)
                if use_green_rule:
                    cross_ok, cw_bbox, pl_bbox = crosswalk_green_select(
                        fid, bbox, crosswalk_boxes, ped_lights,
                        iou_thr=0.003, ped_inter_thr=0.02, foot_pad_px=14
                    )
                if cross_ok:
                    scenario_tag = "crossing street"
                    crossing = True
                    crosswalk_bbox_draw = cw_bbox
                    ped_light_bbox_draw = pl_bbox

                    vehicles_here = load_vehicles_with_behavior(path_ann, fid)

                else:
                    # 3) OTHER VEHICLE (ahead / in the next lane) + persistance
                    veh_used = None
                    veh_distance = None
                    veh_behavior = None

                    vehicles_here = load_vehicles_with_behavior(path_ann, fid)

                    if use_other_vehicle_model:
                        # Exclure véhicules déjà "passés" pour ce piéton
                        if passed_vehicle_ids:
                            vehicles_here = [v for v in vehicles_here if v.get("track_id") not in passed_vehicle_ids]

                        veh_used, d_other = pick_closest_behavior_vehicle(
                            vehicles_here, bbox, Z_ped, camera_params,
                            not_passed_margin_m=0.5,
                            lateral_factor=1.2
                        )

                        if veh_used is not None and d_other is not None:
                            # Si la distance tend vers 0 => véhicule considéré dépassé, on le blacklist
                            if d_other <= PASSED_VEHICLE_DISTANCE_EPS:
                                tid = veh_used.get("track_id")
                                if tid is not None:
                                    passed_vehicle_ids.add(tid)
                                veh_used = None
                            else:
                                veh_behavior = veh_used["behavior"]
                                veh_distance = d_other

                                # vitesse utilisée pour le modèle: ici on réutilise velocity ego (fallback simple)
                                veh_velocity_used = velocity

                                crossing = module.pedestrian_behavior_model(
                                    weather, real_height, veh_velocity_used, veh_distance, adj
                                )
                                scenario_tag = "other vehicle"

            ground_truth = (cross_label == "crossing")

            # --- Hints signalisation (debug) si rule ≠ crossing street/red light
            crosswalk_bbox_hint = None
            ped_light_bbox_hint = None
            ped_light_state_hint = None
            if scenario_tag not in ("crossing street", "red light") and DEBUG_DRAW_SIGNALIZATION_WHEN_NOT_SELECTED:
                crosswalk_bbox_hint, ped_light_bbox_hint, ped_light_state_hint = nearest_crosswalk_and_light(
                    fid, bbox, crosswalk_boxes, ped_lights
                )

            # --- Préparer overlay autres véhicules:
            #     * BLEU: behavior admissible (ahead / next lane)
            #     * ORANGE: autres behavior / inconnu
            ALLOWED = {"ahead", "in the next lane"}
            blue_vehicles = []
            orange_vehicles = []

            used_tid = None
            if locals().get("veh_used") is not None and scenario_tag == "other vehicle":
                used_tid = veh_used.get("track_id")

            for v in (vehicles_here or []):
                tid = v.get("track_id")
                if used_tid is not None and tid == used_tid:
                    continue  # évite doublon (déjà dessiné comme véhicule utilisé)
                beh_raw = v.get("behavior")
                beh = (beh_raw or "").strip().lower()
                lbl = f"vehicle ({beh if beh else 'pas de behavior'})"
                if beh in ALLOWED:
                    blue_vehicles.append((v["bbox"], lbl))
                else:
                    orange_vehicles.append((v["bbox"], lbl))

            # --- Sauvegarde images/vidéo si demandé
            veh_bbox = None
            veh_distance_log = ""
            veh_velocity_log = ""
            veh_behavior_log = ""

            if scenario_tag == "other vehicle" and (locals().get("veh_used") is not None):
                veh_bbox = veh_used["bbox"]
                veh_distance_log = round(veh_distance, 2) if veh_distance is not None else ""
                veh_velocity_log = round(velocity, 2) if velocity is not None else ""
                veh_behavior_log = veh_used["behavior"]

            if save_video:
                annotated = annotate_image(
                    img, bbox, Z_ped, real_height, weather, velocity,
                    crossing, cross_label, scenario_tag,
                    veh_distance=(veh_distance if veh_bbox is not None else None),
                    veh_velocity=(velocity if veh_bbox is not None else None),
                    veh_behavior=(veh_behavior_log if veh_bbox is not None else None),
                    veh_bbox=veh_bbox,
                    crosswalk_bbox=crosswalk_bbox_draw,
                    ped_light_bbox=ped_light_bbox_draw,
                    crosswalk_bbox_hint=crosswalk_bbox_hint,
                    ped_light_bbox_hint=ped_light_bbox_hint,
                    ped_light_state_hint=ped_light_state_hint
                )

                # Dessin des autres véhicules
                for b, lbl in blue_vehicles:
                    draw_vehicle_bbox(annotated, b, lbl, (255, 0, 0), thickness=2)
                for b, lbl in orange_vehicles:
                    draw_vehicle_bbox(annotated, b, lbl, (0, 165, 255), thickness=2)

                images_output_folder = output_folder / ped_id / "images"
                images_output_folder.mkdir(parents=True, exist_ok=True)
                frame_output_path = images_output_folder / f"{fid:05}.png"
                cv2.imwrite(str(frame_output_path), annotated)

                if frame_size is None:
                    frame_size = (annotated.shape[1], annotated.shape[0])

            # --- Ligne CSV
            veh_bbox_vals = ("","","","")
            if veh_bbox is not None:
                vx1, vy1, vx2, vy2 = veh_bbox
                veh_bbox_vals = (round(vx1,2), round(vy1,2), round(vx2,2), round(vy2,2))

            comparisons.append((
                fid, ground_truth, crossing,
                weather, round(real_height,1),
                round(velocity,2), round(Z_ped,2), scenario_tag,
                veh_distance_log, veh_velocity_log, veh_behavior_log,
                *veh_bbox_vals
            ))

        # =========================================================
        # Vidéo (si save_video): concat de toutes les images .png
        # =========================================================
        if save_video and frame_size is not None:
            images_folder = output_folder / ped_id / "images"
            if images_folder.exists() and images_folder.is_dir():
                pngs = sorted(images_folder.glob("*.png"))
                if pngs:
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    fps = fps_images if fps_images > 0 else 24
                    video_output_folder = output_folder / ped_id / "video"
                    video_output_folder.mkdir(parents=True, exist_ok=True)
                    out = cv2.VideoWriter(str(output_video_path), fourcc, fps, frame_size)
                    for p in pngs:
                        frame = cv2.imread(str(p))
                        if frame is not None:
                            out.write(frame)
                    out.release()
                    print(f"Vidéo enregistrée : {output_video_path}")

        # =========================================================
        # CSV final (1 CSV par piéton)
        # =========================================================
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with open(results_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "frame","true_label","predicted_label","weather",
                "real_height_cm","velocity_kmh","distance_m","scenario",
                "veh_distance_m","veh_velocity_kmh_used","veh_behavior",
                "veh_bbox_xtl","veh_bbox_ytl","veh_bbox_xbr","veh_bbox_ybr"
            ])
            writer.writerows(comparisons)

        print(f"CSV sauvegardé pour piéton {ped_id} : {results_path}")
