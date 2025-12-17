import csv
import json
import xml.etree.ElementTree as ET
import math
import cv2
import os
from collections import defaultdict
import numpy as np
from tqdm import tqdm
import importlib.util
from pathlib import Path

# ============================================================
# crossing_decision.py (PIE) — Évaluation du modèle sur PIE
# ------------------------------------------------------------
# Objectif:
#   - Charger les annotations piétons (XML "annt") et les données véhicule (XML "obd")
#   - Sélectionner des piétons ayant AU MOINS un "look=looking"
#   - Pour chaque frame valide d'un piéton :
#       - récupérer GT "cross" (crossing / not-crossing)
#       - estimer distance véhicule↔piéton via GPS (Haversine)
#       - récupérer vitesse via OBD_speed (déjà km/h dans ton XML)
#       - estimer hauteur via bbox + calibration (mais ici finalement tu fixes à 174 cm)
#       - appeler pedestrian_behavior_model(..., adj=False)
#       - stocker comparaison (frame, true_label, predicted_label, features)
#       - si erreur (GT != pred), sauvegarder une image annotée
#   - Exporter un CSV par piéton
#   - Construire une vidéo à partir des frames annotées (si elles existent)
#
# ⚠️ Notes importantes:
#   - La "distance" est calculée par GPS entre la position de la frame courante
#     et la position GPS de la DERNIÈRE frame du piéton (end_frame) => proxy TTC/distance.
#   - Hauteur: calcul prévu, mais dans ce script tu overrides avec real_height = 174.
#   - Les images annotées ne sont générées que pour les erreurs (GT != pred).
#   - La vidéo est reconstruite en relisant toutes les frames du range, mais seules
#     celles sauvegardées existent => la plupart seront manquantes.
# ============================================================


# ============================================================
# Chargement dynamique du modèle (CNRS_behavior_model.py)
# ------------------------------------------------------------
# - On importe un module python depuis un chemin absolu
# - Puis on utilisera module.pedestrian_behavior_model(...)
# ============================================================
file_path = r"E:\crossing-model\main_experiment\model_datas\CNRS_behavior_model.py"
spec = importlib.util.spec_from_file_location("pedestrian_behavior_model", file_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# ------------------------------------------
# Fonctions utilitaires
# ------------------------------------------

def haversine(lat1, lon1, lat2, lon2):
    """
    Calcule la distance (mètres) entre deux points GPS (lat/lon)
    via la formule de Haversine (Terre assimilée à une sphère).

    Utilisation ici:
      distance = dist(GPS_frame, GPS_frame_fin)
    """
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    R = 6371000  # rayon Terre (m)
    return R * c

def load_camera_params(camera_params_path):
    """Charge un JSON contenant calibration caméra (matrice K, distorsion D, pitch...)."""
    with open(camera_params_path, 'r') as file:
        camera_params = json.load(file)
    return camera_params

def undistort_points(points, K, D):
    """
    Corrige la distorsion sur des points image (x,y) via OpenCV.
    - K : matrice intrinsèque
    - D : coefficients distorsion
    """
    points = np.array(points, dtype=np.float32)
    points = np.expand_dims(points, axis=0)  # (1, N, 2)
    points_undistorted = cv2.undistortPoints(points, K, D)
    return points_undistorted[0].reshape(-1, 2)

def calculate_real_size(bbox, distance, camera_params):
    """
    Estime largeur/hauteur réelles (mètres) d'un objet à partir:
      - bbox en pixels
      - distance (m)
      - calibration (K, D) + pitch caméra

    Approche:
      real_height ≈ (height_px * distance) / (f_y * cos(pitch))
      real_width  ≈ (width_px  * distance) / (f_x * cos(pitch))

    ⚠️ Ici, "distance" vient du GPS (haversine), donc ce n'est pas une vraie distance caméra↔piéton,
    mais un proxy lié au déplacement véhicule.
    """
    K = np.array(camera_params['K'])
    D = np.array(camera_params['D'])
    cam_pitch_deg = camera_params['cam_pitch_deg']

    xtl, ytl, xbr, ybr = bbox
    width_pixel = xbr - xtl
    height_pixel = ybr - ytl

    if width_pixel <= 0 or height_pixel <= 0:
        print(f"Erreur: Dimensions de la bounding box non valides: {bbox}")
        return None, None

    f_x = K[0, 0]
    f_y = K[1, 1]

    # Undistortion (surtout utile près des bords image)
    top_left = undistort_points([(xtl, ytl)], K, D)[0]
    bottom_right = undistort_points([(xbr, ybr)], K, D)[0]
    # NB: top_left / bottom_right ne sont pas utilisés ensuite pour recalculer width/height_px,
    # donc la correction est actuellement "préparée" mais pas exploitée.

    cam_pitch_rad = math.radians(cam_pitch_deg)

    real_height_m = (height_pixel * distance) / (f_y * math.cos(cam_pitch_rad))
    real_width_m  = (width_pixel  * distance) / (f_x * math.cos(cam_pitch_rad))

    return real_width_m, real_height_m


# ------------------------------------------
# Chargement des données XML
# ------------------------------------------

def load_pedestrians(xml_path):
    """
    Parse le XML d’annotations (video_XXXX_annt.xml) et retourne:
      pedestrian_data[ped_id] = [(frame, cross_value), ...]

    Filtrage:
      - track label == "pedestrian"
      - on garde seulement les piétons qui ont AU MOINS une frame avec look="looking"
      - on collecte uniquement les frames où 'cross' est présent
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    pedestrian_data = defaultdict(list)

    for track in root.findall("track"):
        if track.attrib["label"] == "pedestrian":
            ped_id = None
            has_looking = False

            # 1) détecter l'id et vérifier si "look=looking" apparaît au moins une fois
            for box in track.findall("box"):
                for attr in box.findall("attribute"):
                    if attr.get("name") == "id":
                        ped_id = attr.text
                    elif attr.get("name") == "look" and attr.text == "looking":
                        has_looking = True

            # 2) si piéton valable, collecter (frame, cross)
            if has_looking and ped_id is not None:
                for box in track.findall("box"):
                    frame = int(box.get("frame"))
                    cross_value = None
                    for attr in box.findall("attribute"):
                        if attr.get("name") == "cross":
                            cross_value = attr.text
                    if cross_value is not None:
                        pedestrian_data[ped_id].append((frame, cross_value))

    return pedestrian_data

def load_pedestrian_boxes(xml_path, pedestrian_id):
    """
    Récupère la bbox (xtl, ytl, xbr, ybr) du piéton 'pedestrian_id' pour chaque frame.
    Retour:
      boxes[frame_id] = (xtl, ytl, xbr, ybr)
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    boxes = {}
    for track in root.findall("track"):
        if track.attrib["label"] == "pedestrian":
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
    Parse un XML OBD/GPS (video_XXXX_obd.xml) et construit:
      gps[fid] = {"lat": ..., "lon": ..., "speed": ...}

    NB:
      - speed est lu depuis l'attribut "OBD_speed" (supposé km/h).
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


# ------------------------------------------
# Annotation visuelle d'une frame (debug erreurs)
# ------------------------------------------

def annotate_image(img, bbox, distance, real_height, weather, velocity, crossing, cross_label):
    """
    Ajoute sur l'image:
      - bbox piéton
      - ligne "ego" (bas-centre image) -> centre piéton
      - textes: distance, height, weather, velocity, decision, GT vs pred
    """
    xtl, ytl, xbr, ybr = bbox
    h, w = img.shape[:2]
    center_pedestrian = ((xtl + xbr) // 2, (ytl + ybr) // 2)
    bottom_center = (w // 2, h)

    cv2.rectangle(img, (xtl, ytl), (xbr, ybr), (0, 255, 0), 2)
    cv2.line(img, bottom_center, center_pedestrian, (0, 0, 255), 2)

    cv2.putText(img, f"{distance:.2f} m", (bottom_center[0] + 10, bottom_center[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    if real_height is not None:
        cv2.putText(img, f"{round(real_height)} cm", (bottom_center[0] + 10, bottom_center[1] - 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    cv2.putText(img, weather, (bottom_center[0] + 10, bottom_center[1] - 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    cv2.putText(img, f"{velocity:.2f} km/h", (bottom_center[0] + 10, bottom_center[1] - 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    # Affichage décision (couleur différente si crossing vs not-crossing)
    if crossing:
        color = (0, 40, 255)      # rouge/orange
        crossing_text = "crossing"
    else:
        color = (0, 255, 40)      # vert
        crossing_text = "not-crossing"

    cv2.putText(img, crossing_text, (bottom_center[0] + 10, bottom_center[1] - 130),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # Bandeau en haut: GT label texte + bool pred
    cv2.putText(img, f"GT: {cross_label} | Pred: {crossing}", (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

    return img


# ----------------------------
# PARAMÈTRES / PATHS
# ----------------------------
# Structure attendue:
#   PIE/
#     images/setXX/video_XXXX/*.png
#     annotations/setXX/video_XXXX_annt.xml
#     annotations_vehicle/setXX/video_XXXX_obd.xml
#     camera_params/calibration_data.json
#     model_result.../  (sorties)
# ----------------------------

base_path = Path(r"E:/crossing-model/main_experiment/model_validation/datasets/PIE")

images_path = base_path / "images"
annotations_path = base_path / "annotations"
annotations_vehicle_path = base_path / "annotations_vehicle"

# Dossier de sortie (ici: no_adj + "height_calculated" même si height est fixé à 174 plus bas)
output_base = base_path / "model_result_no_adj_&_height_calculated"

camera_params_path = base_path / "camera_params" / "calibration_data.json"


# ============================================================
# Boucle principale: sets -> videos -> piétons
# ============================================================

# Parcourt tous les sets (set01, set02, ...) présents dans images/
for set_folder in sorted(images_path.glob("set*")):
    set_name = set_folder.name  # ex: set01

    # Parcourt toutes les vidéos dans le set
    for video_folder in sorted(set_folder.glob("video_*")):
        video_name = video_folder.name  # ex: video_0001

        # Chemins associés à cette vidéo
        path_imgs = video_folder
        path_ann = annotations_path / set_name / f"{video_name}_annt.xml"
        path_obd = annotations_vehicle_path / set_name / f"{video_name}_obd.xml"

        # Sortie: un dossier par couple set-video (ex: set01-0001)
        output_folder = output_base / f"{set_name}-{video_name.split('_')[-1]}"
        output_folder.mkdir(parents=True, exist_ok=True)

        print(f"Traitement de {set_name}/{video_name}")
        print(f" - Images: {path_imgs}")
        print(f" - Annotations: {path_ann}")
        print(f" - OBD: {path_obd}")
        print(f" - Output: {output_folder}")

        os.makedirs(output_folder, exist_ok=True)

        # ----------------------------
        # Chargement des données
        # ----------------------------
        pedestrian_data = load_pedestrians(path_ann)
        print(len(pedestrian_data), " pedestrians")

        # ============================================================
        # Pour chaque piéton retenu:
        #   - identifie sa plage de frames (min..max)
        #   - extrait bbox + gps + calibration
        #   - calcule features + prediction frame par frame
        #   - export CSV + images des erreurs + vidéo
        # ============================================================
        for ped_id, data in pedestrian_data.items():
            frames = [frame for frame, cross in data]
            start_frame = min(frames)
            end_frame = max(frames)

            print(ped_id)

            comparisons = []  # (frame, true_label, predicted_label, weather, height, velocity, distance)
            cross_labels = dict(pedestrian_data[ped_id])  # {frame: "crossing"/"not-crossing"/...}

            # Vidéo sortie par piéton (chemin)
            output_video_path = output_folder / ped_id / "video" / f"features_extracted.mp4"

            # CSV sortie par piéton (au niveau du dossier video)
            results_path = output_folder / f"crossing_results_{ped_id}.csv"

            # Si déjà calculé, on skip (évite re-run)
            if results_path.exists():
                print(f" CSV déjà existante pour le piéton {ped_id}, on passe au suivant.")
                continue

            pedestrian_boxes = load_pedestrian_boxes(path_ann, ped_id)
            gps_data = load_gps_data(path_obd)
            camera_params = load_camera_params(camera_params_path)

            # ------------------------------------------------------------
            # Référence GPS = position à end_frame (frame finale piéton)
            # => distance = dist(frame_courante, frame_finale)
            # ------------------------------------------------------------
            if end_frame not in gps_data:
                print(f"❌ Données GPS manquantes pour la frame {end_frame}")
                exit()

            lat_ref, lon_ref = gps_data[end_frame]["lat"], gps_data[end_frame]["lon"]

            # ----------------------------
            # Traitement frame par frame
            # ----------------------------
            frame_size = None
            has_height = False

            for fid in tqdm(range(start_frame, end_frame + 1), desc=f"Traitement des frames {ped_id}"):
                img_path = os.path.join(path_imgs, f"{fid:05}.png")
                img = cv2.imread(img_path)
                if img is None:
                    tqdm.write(f"⚠️ Image non trouvée pour frame {fid}")
                    continue

                # On exige GPS + bbox à la frame
                if fid not in gps_data or fid not in pedestrian_boxes:
                    tqdm.write(f"⚠️ GPS ou box manquante pour frame {fid}")
                    continue

                # GT cross (string)
                cross_label = cross_labels.get(fid, "None")
                # Filtre strict : on garde uniquement "crossing" ou "not-crossing"
                if (cross_label != "crossing") and (cross_label != "not-crossing"):
                    continue

                # Weather: ici fixé à 'clear' (pas d'annotation météo PIE dans ce script)
                weather = 'clear'

                # Distance + vitesse:
                # - vitesse lue dans gps_data[fid]["speed"] (OBD_speed)
                # - distance GPS frame->end_frame (m)
                lat, lon, velocity = gps_data[fid]["lat"], gps_data[fid]["lon"], gps_data[fid]["speed"]
                distance = haversine(lat, lon, lat_ref, lon_ref)

                # Height: calculée une seule fois (has_height) si bbox pas près des bords
                bbox = pedestrian_boxes[fid]

                if not has_height:
                    xtl, ytl, xbr, ybr = bbox
                    h, w = img.shape[:2]

                    # marge (10%) : si bbox touche trop les bords => on abandonne tout le piéton
                    margin_x = w * 0.1
                    margin_y = h * 0.1
                    if xtl < margin_x or xbr > (w - margin_x) or ytl < margin_y or ybr > (h - margin_y):
                        tqdm.write(f"⛔️ Piéton {ped_id} trop proche du bord à la frame {fid} — ignoré.")
                        break  # stop ce piéton

                    real_width, real_height_m = calculate_real_size(bbox, distance, camera_params)

                    if real_height_m is None:
                        tqdm.write(f"⚠️ Échec calcul taille pour {ped_id} à frame {fid}")
                        break

                    # Normalement: real_height = real_height_m * 100
                    # Mais ici tu forces une valeur constante (debug/ablation)
                    # real_height = real_height_m * 100
                    real_height = 174
                    has_height = True

                # ============================================================
                # Prédiction du modèle (adj=False)
                # Entrées attendues: (weather, height_cm, velocity_kmh, distance_m, adj_flag)
                # ============================================================
                crossing = module.pedestrian_behavior_model(weather, real_height, velocity, distance, False)

                # Conversion GT string -> bool
                ground_truth = False if cross_label == "not-crossing" else True

                # Stocker la ligne CSV
                comparisons.append((
                    fid,
                    ground_truth,
                    crossing,
                    weather,
                    round(real_height, 1),
                    round(velocity, 2),
                    round(distance, 2)
                ))

                # Sauvegarder uniquement les erreurs en images annotées
                if ground_truth != crossing:
                    annotated = annotate_image(img, bbox, distance, real_height, weather, velocity, crossing, cross_label)

                    images_output_folder = output_folder / ped_id / "images"
                    images_output_folder.mkdir(parents=True, exist_ok=True)

                    frame_output_path = images_output_folder / f"{fid:05}.png"
                    cv2.imwrite(str(frame_output_path), annotated)

                    # mémoriser la taille pour créer la vidéo ensuite
                    if frame_size is None:
                        frame_size = (annotated.shape[1], annotated.shape[0])

            print("✅ Toutes les frames annotées ont été sauvegardées.")

            # ============================================================
            # Création vidéo (à partir des images annotées)
            # ------------------------------------------------------------
            # ⚠️ Ici tu boucles sur toutes les frames start..end,
            # mais seules les frames où GT!=pred existent sur disque.
            # => la plupart des cv2.imread(frame_path) renverront None.
            # => la vidéo ne contiendra que les frames existantes.
            # ============================================================

            images_folder = output_folder / ped_id / "images"
            if images_folder.exists() and images_folder.is_dir():
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                fps = 24

                video_output_folder = output_folder / ped_id / "video"
                video_output_folder.mkdir(parents=True, exist_ok=True)

                # NB: frame_size peut rester None s'il n'y a AUCUNE erreur => VideoWriter invalide
                out = cv2.VideoWriter(output_video_path, fourcc, fps, frame_size)

                for fid in tqdm(range(start_frame, end_frame + 1), desc="Construction de la vidéo"):
                    frame_path = output_folder / ped_id / "images" / f"{fid:05}.png"
                    frame = cv2.imread(str(frame_path))
                    if frame is not None:
                        out.write(frame)

                out.release()
                print(f"🎬 Vidéo enregistrée : {output_video_path}")

            # ============================================================
            # Export CSV (un fichier par piéton)
            # ============================================================
            results_path.parent.mkdir(parents=True, exist_ok=True)
            with open(results_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["frame", "true_label", "predicted_label",
                                 "weather", "real_height_cm", "velocity_kmh", "distance_m"])
                writer.writerows(comparisons)
