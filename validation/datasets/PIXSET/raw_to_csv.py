import os
import numpy as np
import pandas as pd
from pioneer.das.api.platform import Platform
from math import radians, sin, cos, sqrt, atan2
import uuid
from tqdm import tqdm  # ✅ pour la barre de progression en console

# === Distance haversine ===
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# === Générer un ID piéton unique ===
def generate_id():
    return str(uuid.uuid4())[:8]

# === Mappage météo ===
def get_weather_class(folder_name, weather_csv_path):
    try:
        df_weather = pd.read_csv(weather_csv_path)
        row = df_weather[df_weather['folder'] == folder_name]
        if row.empty:
            return None
        row = row.iloc[0]
        if not pd.isna(row.get('snow')) or not pd.isna(row.get('twilight')):
            return None
        if not pd.isna(row.get('night')):
            return 'night'
        elif not pd.isna(row.get('rain')) or not pd.isna(row.get('clouds')):
            return 'rain'
        elif not pd.isna(row.get('day')):
            return 'clear'
        else:
            return None
    except Exception as e:
        print(f"Erreur météo pour {folder_name}: {e}")
        return None

# === Dossiers ===
root_dataset = r'C:\Users\svictor\Documents\PIXSET\dataset'
output_csv_dir = r'C:\Users\svictor\Documents\PIXSET\output'
weather_csv_path = os.path.join(root_dataset, 'weather.csv')
os.makedirs(output_csv_dir, exist_ok=True)

# === Traitement des dossiers ===
folder_list = [
    f for f in os.listdir(root_dataset)
    if os.path.isdir(os.path.join(root_dataset, f)) and f != "predictions"
]

for folder_name in tqdm(folder_list, desc="📂 Dossiers"):
    dataset_path = os.path.join(root_dataset, folder_name)

    try:
        pf = Platform(dataset_path)
        sync = pf.synchronized(sync_labels=[
            'flir_bbfc_flimg',
            'pixell_bfc_box3d-deepen',
            'sbgekinox_bcc_navposvel'
        ], tolerance_us=1e6)
    except Exception as e:
        print(f"⚠️ Erreur chargement {folder_name}: {e}")
        continue

    tracked_pedestrians = {}
    ASSOCIATION_THRESHOLD = 1.5  # mètres
    annotations = []

    weather_class = get_weather_class(folder_name, weather_csv_path)
    if weather_class is None:
        print(f"⛔ Dossier ignoré (météo): {folder_name}")
        continue

    for frame_idx in tqdm(range(len(sync)), leave=False, desc=f"🎞️ {folder_name}"):
        frame = sync[frame_idx]

        try:
            ego_sample = frame['sbgekinox_bcc_navposvel']
            raw_data = ego_sample.raw
            ego_lat = raw_data['latitude']
            ego_lon = raw_data['longitude']
            ego_alt = raw_data['altitude']

            v_n, v_e, v_d = raw_data['velocity_n'], raw_data['velocity_e'], raw_data['velocity_d']
            ego_speed_mps = sqrt(v_n**2 + v_e**2 + v_d**2)

            boxes3d = frame['pixell_bfc_box3d-deepen']
            categories = boxes3d.get_categories()
            dimensions = boxes3d.get_dimensions()
            centers = boxes3d.get_centers()

            for i, category in enumerate(categories):
                if category != 'pedestrian':
                    continue

                center = centers[i]
                transform = boxes3d.compute_transform(i)
                world_pos = boxes3d.transform_pts(transform, np.array([center]))[0]

                d_north = world_pos[0]
                d_east = world_pos[1]
                d_lat = d_north / 111320
                d_lon = d_east / (40075000 * cos(radians(ego_lat)) / 360)
                ped_lat = ego_lat + d_lat
                ped_lon = ego_lon + d_lon

                dist_m = haversine_distance(ego_lat, ego_lon, ped_lat, ped_lon)

                matched_id = None
                for pid, pdata in tracked_pedestrians.items():
                    prev = pdata["position"]
                    if np.linalg.norm(np.array(prev) - np.array(world_pos[:2])) < ASSOCIATION_THRESHOLD:
                        matched_id = pid
                        break

                if matched_id is None:
                    matched_id = generate_id()

                tracked_pedestrians[matched_id] = {
                    "position": world_pos[:2],
                    "last_position": world_pos[:2],
                    "frame": frame_idx
                }

                annotations.append({
                    "frame_id": frame_idx,
                    "taille_cm": dimensions[i][2] * 100,
                    "dist_m": dist_m,
                    "ego_speed_mps": ego_speed_mps,
                    "ego_lat": ego_lat,
                    "ego_lon": ego_lon,
                    "ped_lat": ped_lat,
                    "ped_lon": ped_lon,
                    "weather": weather_class,
                    "pedestrian_id": matched_id
                })

        except Exception as e:
            print(f"⚠️ Erreur frame {frame_idx} dans {folder_name}: {e}")
            continue

    df = pd.DataFrame(annotations)
    csv_path = os.path.join(output_csv_dir, f"{folder_name}.csv")
    df.to_csv(csv_path, index=False)
