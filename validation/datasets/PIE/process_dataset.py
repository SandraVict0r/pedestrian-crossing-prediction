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

# =========================
# Chargement dynamique du modèle
# =========================
# On charge le fichier CNRS_behavior_model.py depuis un chemin local,
# puis on utilise module.pedestrian_behavior_model(...)
file_path = r"E:\crossing-model\main_experiment\model_datas\CNRS_behavior_model.py"
spec = importlib.util.spec_from_file_location("pedestrian_behavior_model", file_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# =========================
# Fonctions utilitaires
# =========================

def haversine(lat1, lon1, lat2, lon2):
    """
    Calcule une distance au sol en mètres entre deux points GPS
    via la formule de Haversine.

    ⚠️ Dans ce pipeline PIE, cette distance est utilisée comme proxy
    de "distance ego->piéton" (distance_m) pour alimenter le modèle.
    """
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    R = 6371000
    return R*c

def load_camera_params(camera_params_path):
    """
    Charge le JSON de calibration caméra (intrinsèques K, distorsion D, pitch, etc.).
    """
    with open(camera_params_path, 'r') as f:
        return json.load(f)

def undistort_points(points, K, D):
    """
    Corrige la distorsion sur des points 2D (OpenCV undistortPoints).
    Utile pour limiter les erreurs de taille quand bbox proche des bords.
    """
    points = np.array(points, dtype=np.float32)
    points = np.expand_dims(points, axis=0)
    points_undistorted = cv2.undistortPoints(points, K, D)
    return points_undistorted[0].reshape(-1, 2)

def calculate_real_size(bbox, distance, camera_params):
    """
    Estime la taille réelle (largeur/hauteur) d'un objet à partir :
      - bbox en pixels
      - distance au sol (ici: haversine ego->piéton)
      - calibration (fx, fy, distorsion D) et pitch caméra

    ⚠️ Hypothèse forte : 'distance' correspond bien à la profondeur utile
    pour un calcul perspective simplifié.
    """
    K = np.array(camera_params['K'])
    D = np.array(camera_params['D'])
    cam_pitch_deg = camera_params['cam_pitch_deg']

    xtl, ytl, xbr, ybr = bbox
    width_pixel = xbr - xtl
    height_pixel = ybr - ytl
    if width_pixel <= 0 or height_pixel <= 0:
        return None, None

    f_x = K[0,0]
    f_y = K[1,1]

    # Undistortion des coins bbox (calculé mais non utilisé ensuite ici)
    # -> tu pourrais à terme recalculer width/height avec top_left/bottom_right undistorted
    top_left = undistort_points([(xtl, ytl)], K, D)[0]
    bottom_right = undistort_points([(xbr, ybr)], K, D)[0]

    # Correction pitch simple via cos(pitch)
    cam_pitch_rad = math.radians(cam_pitch_deg)
    real_height_m = (height_pixel * distance) / (f_y * math.cos(cam_pitch_rad))
    real_width_m  = (width_pixel  * distance) / (f_x * math.cos(cam_pitch_rad))
    return real_width_m, real_height_m

def load_pedestrians(xml_path):
    """
    Charge les annotations piétons depuis le XML (format CVAT-like).
    Filtre: ne conserve que les piétons qui ont AU MOINS une frame 'look=looking'.

    Retour:
      - pedestrian_data: {ped_id: [(frame, cross_label), ...]}
      - first_looking_frame: {ped_id: first_frame_where_look=looking}
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    pedestrian_data = defaultdict(list)
    first_looking_frame = {}

    for track in root.findall("track"):
        if track.attrib["label"] == "pedestrian":
            ped_id = None
            looking_frames = []
            crossing_data = []

            for box in track.findall("box"):
                frame = int(box.get("frame"))
                cross_value = None
                for attr in box.findall("attribute"):
                    if attr.get("name") == "id":
                        ped_id = attr.text
                    elif attr.get("name") == "look" and attr.text == "looking":
                        looking_frames.append(frame)
                    elif attr.get("name") == "cross":
                        cross_value = attr.text

                # On garde le label cross uniquement si ped_id déjà connu
                if cross_value and ped_id:
                    crossing_data.append((frame, cross_value))

            if ped_id and looking_frames and crossing_data:
                pedestrian_data[ped_id] = crossing_data
                first_looking_frame[ped_id] = min(looking_frames)

    return pedestrian_data, first_looking_frame

def load_pedestrian_boxes(xml_path, pedestrian_id):
    """
    Récupère les bbox du piéton (par frame) pour un ped_id donné.
    Retour: {frame_id: (xtl, ytl, xbr, ybr)}
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    boxes = {}
    for track in root.findall("track"):
        if track.attrib.get("label") == "pedestrian":
            for box in track.findall("box"):
                pid = box.find("attribute[@name='id']")
                if pid is not None and pid.text == pedestrian_id:
                    fid = int(box.attrib["frame"])
                    xtl = int(float(box.attrib["xtl"]))
                    ytl = int(float(box.attrib["ytl"]))
                    xbr = int(float(box.attrib["xbr"]))
                    ybr = int(float(box.attrib["ybr"]))
                    boxes[fid] = (xtl, ytl, xbr, ybr)
    return boxes

def load_gps_data(xml_path):
    """
    Charge les données OBD/GPS depuis *_obd.xml :
      - latitude / longitude
      - OBD_speed (km/h)
    Retour: {frame_id: {"lat":..., "lon":..., "speed":...}}
    """
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

def annotate_image(img, bbox, distance, real_height, weather, velocity, crossing, cross_label):
    """
    Ajoute un overlay visuel :
      - bbox piéton
      - ligne ego->piéton
      - distance / height / weather / speed
      - GT vs Pred
    Utilisé ici seulement en cas d'erreur (GT != Pred) si save_video=True.
    """
    xtl, ytl, xbr, ybr = bbox
    h, w = img.shape[:2]
    center_pedestrian = ((xtl + xbr) // 2, (ytl + ybr) // 2)
    bottom_center = (w // 2, h)

    cv2.rectangle(img, (xtl, ytl), (xbr, ybr), (0, 255, 0), 2)
    cv2.line(img, bottom_center, center_pedestrian, (0, 0, 255), 2)

    cv2.putText(img, f"{distance:.2f} m", (bottom_center[0]+10, bottom_center[1]-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

    if real_height is not None:
        cv2.putText(img, f"{round(real_height)} cm", (bottom_center[0]+10, bottom_center[1]-40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

    cv2.putText(img, weather, (bottom_center[0]+10, bottom_center[1]-70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

    cv2.putText(img, f"{velocity:.2f} km/h", (bottom_center[0]+10, bottom_center[1]-100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

    color = (0,40,255) if crossing else (0,255,40)
    crossing_text = "crossing" if crossing else "not-crossing"
    cv2.putText(img, crossing_text, (bottom_center[0]+10, bottom_center[1]-130),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    cv2.putText(img, f"GT: {cross_label} | Pred: {crossing}", (10,50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)

    return img

# =========================
# Fonction principale
# =========================

def process_dataset(
    images_path,
    annotations_path,
    annotations_vehicle_path,
    camera_params_path,
    output_path,
    adj,
    intention,
    save_video,
    use_ped_light_override: bool = False,
    use_other_vehicle_model: bool = False
):
    """
    Pipeline PIE "simple":
      - boucle sur sets / vidéos
      - pour chaque vidéo: _process_single_video(...)
    Les flags use_ped_light_override/use_other_vehicle_model sont définis
    mais ne sont PAS utilisés dans cette version (réservés à d'autres variantes).
    """
    images_path = Path(images_path)
    annotations_path = Path(annotations_path)
    annotations_vehicle_path = Path(annotations_vehicle_path)
    output_base = Path(output_path)
    camera_params_path = Path(camera_params_path)

    # Détecter si images_path contient des sets (set01, set02...) ou directement video_*
    sets = sorted(images_path.glob("set*"))
    if len(sets) == 0:
        video_folders = sorted(images_path.glob("video_*"))
        if not video_folders:
            print("Aucun set ni vidéo trouvé dans le dossier images_path")
            return

        # Cas "vidéos direct"
        for video_folder in video_folders:
            set_name = video_folder.parent.name
            video_name = video_folder.name
            _process_single_video(
                set_name, video_name, video_folder,
                annotations_path, annotations_vehicle_path,
                camera_params_path, output_base,
                adj, intention, save_video
            )
    else:
        # Cas standard "sets"
        for set_folder in sets:
            set_name = set_folder.name
            video_folders = sorted(set_folder.glob("video_*"))
            for video_folder in video_folders:
                video_name = video_folder.name
                _process_single_video(
                    set_name, video_name, video_folder,
                    annotations_path, annotations_vehicle_path,
                    camera_params_path, output_base,
                    adj, intention, save_video
                )

def _process_single_video(set_name, video_name, path_imgs,
                          annotations_path, annotations_vehicle_path,
                          camera_params_path, output_base,
                          adj=False, intention=False, save_video=False):
    """
    Traitement d'une vidéo PIE :
      - charge annotations piétons + OBD (GPS/speed)
      - pour chaque piéton admissible: boucle frame
      - calc distance (haversine) + vitesse + taille (1 fois)
      - appelle le modèle + règle vitesse<20
      - export CSV, et optionnellement images/vidéo pour les erreurs uniquement
    """
    print(f"Traitement de {set_name}/{video_name}")

    path_ann = annotations_path / set_name / f"{video_name}_annt.xml"
    path_obd = annotations_vehicle_path / set_name / f"{video_name}_obd.xml"

    # Dossier de sortie par vidéo : "setXX-YYYY"
    output_folder = output_base / f"{set_name}-{video_name.split('_')[-1]}"
    output_folder.mkdir(parents=True, exist_ok=True)

    pedestrian_data, first_looking_frame = load_pedestrians(path_ann)
    camera_params = load_camera_params(camera_params_path)

    print(f"{len(pedestrian_data)} piétons détectés")

    for ped_id, data in pedestrian_data.items():
        frames = [frame for frame, cross in data]
        start_frame = min(frames)

        # Option "intention": on démarre à partir du premier "looking"
        if intention and ped_id in first_looking_frame:
            start_frame = first_looking_frame[ped_id]

        end_frame = max(frames)

        print(f"Piéton {ped_id}")

        comparisons = []  # lignes CSV
        cross_labels = dict(pedestrian_data[ped_id])

        # Sorties
        output_video_path = output_folder / ped_id / "video" / "features_extracted.mp4"
        results_path = output_folder / f"crossing_results_{ped_id}.csv"

        # Si déjà calculé, on skip
        if results_path.exists():
            print(f"CSV déjà existante pour {ped_id}, skip.")
            continue

        pedestrian_boxes = load_pedestrian_boxes(path_ann, ped_id)
        gps_data = load_gps_data(path_obd)

        # Référence distance : on prend lat/lon de la dernière frame du piéton
        if end_frame not in gps_data:
            print(f"Données GPS manquantes pour frame {end_frame}")
            continue
        lat_ref, lon_ref = gps_data[end_frame]["lat"], gps_data[end_frame]["lon"]

        frame_size = None
        has_height = False
        need_annotation = False

        for fid in tqdm(range(start_frame, end_frame+1), desc=f"Frames piéton {ped_id}"):
            img_path = path_imgs / f"{fid:05}.png"
            img = cv2.imread(str(img_path))
            if img is None:
                tqdm.write(f"Image absente frame {fid}")
                continue

            # On exige GPS + bbox à la frame
            if fid not in gps_data or fid not in pedestrian_boxes:
                tqdm.write(f"GPS ou box manquante frame {fid}")
                continue

            # On ne garde que crossing / not-crossing
            cross_label = cross_labels.get(fid, "None")
            if cross_label not in ("crossing", "not-crossing"):
                tqdm.write(f"Label {cross_label}")
                continue

            # Weather: forcé à clear dans cette version
            weather = 'clear'

            # Distance ego->piéton (GPS) + vitesse ego
            lat, lon, velocity = gps_data[fid]["lat"], gps_data[fid]["lon"], gps_data[fid]["speed"]
            distance = haversine(lat, lon, lat_ref, lon_ref)

            bbox = pedestrian_boxes[fid]

            # --- Calcul taille (1 seule fois) ---
            # On refuse si bbox trop proche du bord (risque forte distorsion / bbox tronquée)
            h, w = img.shape[:2]
            margin_x = w * 0.1
            margin_y = h * 0.1
            xtl, ytl, xbr, ybr = bbox

            if not has_height and (xtl < margin_x or xbr > (w - margin_x) or ytl < margin_y or ybr > (h - margin_y)):
                tqdm.write(f"Piéton {ped_id} trop proche bord frame {fid}, skip piéton.")
                break  # on abandonne ce piéton

            if not has_height:
                real_width, real_height_m = calculate_real_size(bbox, distance, camera_params)
                if real_height_m is None:
                    tqdm.write(f"Erreur taille piéton {ped_id} frame {fid}")
                    break
                real_height = real_height_m * 100  # cm

                # Clamp simple (valeurs aberrantes) -> valeur moyenne
                if (real_height < 150) or (real_height > 200):
                    real_height = 171

                has_height = True

            # =========================================================
            # Modèle + règles décisionnelles
            # =========================================================

            # ⚠️ Spécifique à cette variante:
            # tu divises la vitesse par 2 AVANT de l'utiliser:
            velocity = velocity / 2

            # Prédiction du modèle (adj = SCBA on/off)
            crossing = module.pedestrian_behavior_model(weather, real_height, velocity, distance, adj)

            # Règle "voiture lente => elle laisse passer"
            # ⚠️ Attention: ici tu compares la vitesse APRÈS division par 2.
            # Donc "velocity < 20" équivaut à "vitesse OBD < 40 km/h".
            if velocity < 20:
                crossing = True

            # Ground truth booléen
            ground_truth = (cross_label == "crossing")

            # Ligne CSV
            comparisons.append((
                fid, ground_truth, crossing,
                weather, round(real_height,1),
                round(velocity,2), round(distance,2)
            ))

            # Sauvegarde d'images annotées UNIQUEMENT en cas d'erreur et si save_video=True
            if ground_truth != crossing:
                annotated = annotate_image(img, bbox, distance, real_height, weather, velocity, crossing, cross_label)
                need_annotation = True
            else:
                need_annotation = False

            if need_annotation and save_video:
                images_output_folder = output_folder / ped_id / "images"
                images_output_folder.mkdir(parents=True, exist_ok=True)
                frame_output_path = images_output_folder / f"{fid:05}.png"
                cv2.imwrite(str(frame_output_path), annotated)

                # mémoriser taille frame (pour VideoWriter)
                if frame_size is None:
                    frame_size = (annotated.shape[1], annotated.shape[0])

        print("Frames annotées sauvegardées.")

        # =========================================================
        # Création vidéo (à partir des images sauvegardées)
        # =========================================================
        images_folder = output_folder / ped_id / "images"
        if images_folder.exists() and images_folder.is_dir() and save_video:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fps = 24
            video_output_folder = output_folder / ped_id / "video"
            video_output_folder.mkdir(parents=True, exist_ok=True)

            # ⚠️ frame_size peut être None si aucune frame en erreur n'a été sauvegardée
            out = cv2.VideoWriter(str(output_video_path), fourcc, fps, frame_size)

            for fid in tqdm(range(start_frame, end_frame+1), desc="Création vidéo"):
                frame_path = images_folder / f"{fid:05}.png"
                frame = cv2.imread(str(frame_path))
                if frame is not None:
                    out.write(frame)

            out.release()
            print(f"Vidéo enregistrée : {output_video_path}")

        # =========================================================
        # Export CSV (1 fichier par piéton)
        # =========================================================
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with open(results_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["frame","true_label","predicted_label","weather","real_height_cm","velocity_kmh","distance_m"])
            writer.writerows(comparisons)
