from pioneer.das.api.platform import Platform
import numpy as np
import os
import matplotlib.pyplot as plt
from math import radians, sin, cos, sqrt, atan2
np.int = int  # Patch temporaire pour compatibilité

# Haversine entre deux positions (lat, lon) en degrés
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # rayon moyen de la Terre en mètres
    phi1, phi2 = radians(lat1), radians(lat2)
    delta_phi = radians(lat2 - lat1)
    delta_lambda = radians(lon2 - lon1)

    a = sin(delta_phi / 2.0) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2.0) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c

# Chemins
dataset_path = r'C:\Users\svictor\Documents\PIXSET\dataset\20200610_185206_part1_5095_5195'
output_dir = r'C:\Users\svictor\Documents\PIXSET\output'
os.makedirs(output_dir, exist_ok=True)

# Chargement de la plateforme
pf = Platform(dataset_path)
sync = pf.synchronized(sync_labels=[
    'flir_bbfc_flimg',
    'pixell_bfc_box3d-deepen',
    'sbgekinox_bcc_navposvel'
], tolerance_us=1e6)

for frame_idx in range(len(sync)):
    frame = sync[frame_idx]
    print(frame.available_calibrations)


    image_sample = frame['flir_bbfc_flimg']
    image = image_sample.raw

    # Ego position GPS
    ego_sample = frame['sbgekinox_bcc_navposvel']
    raw_data = ego_sample.raw
    ego_lat = raw_data['latitude']
    ego_lon = raw_data['longitude']
    ego_alt = raw_data['altitude']

    # Boîtes 3D détectées
    boxes3d = frame['pixell_bfc_box3d-deepen']
    categories = boxes3d.get_categories()
    dimensions = boxes3d.get_dimensions()
    centers = boxes3d.get_centers()
    rotations = boxes3d.get_rotations()

    pedestrians = []

    for i, category in enumerate(categories):
        if category == 'pedestrian':
            taille_cm = dimensions[i][2] * 100



            # Centroid de la boîte 3D (XYZ en repère monde)
            center = centers[i]  # [x, y, z] en mètres

            # Obtenir la matrice de transformation pour le piéton
            transform = boxes3d.compute_transform(i)

            # Appliquer la transformation au centre uniquement
            pedestrian_world_pos = boxes3d.transform_pts(transform, np.array([center]))[0]

            # Convertir le piéton en coordonnées géographiques (simplification : ego lat/lon + delta local)
            # ⚠️ approximation valable si distance < quelques centaines de mètres
            d_north = pedestrian_world_pos[0]  # x
            d_east = pedestrian_world_pos[1]   # y

            d_lat = d_north / 111320  # 1 deg latitude = ~111.32 km
            d_lon = d_east / (40075000 * cos(radians(ego_lat)) / 360)  # corrige longitude selon latitude

            ped_lat = ego_lat + d_lat
            ped_lon = ego_lon + d_lon

            dist_m = haversine_distance(ego_lat, ego_lon, ped_lat, ped_lon)

            # Boîte locale centrée en (0,0,0)
            half_dims = dimensions[i] / 2
            box_corners_local = np.array([
                [+half_dims[0], +half_dims[1], -half_dims[2]],
                [+half_dims[0], -half_dims[1], -half_dims[2]],
                [-half_dims[0], -half_dims[1], -half_dims[2]],
                [-half_dims[0], +half_dims[1], -half_dims[2]],
                [+half_dims[0], +half_dims[1], +half_dims[2]],
                [+half_dims[0], -half_dims[1], +half_dims[2]],
                [-half_dims[0], -half_dims[1], +half_dims[2]],
                [-half_dims[0], +half_dims[1], +half_dims[2]],
            ])

            box_corners_world = boxes3d.transform_pts(transform, box_corners_local)

            pedestrians.append({
                'taille_cm': taille_cm,
                'dist_m': dist_m,
                'corners': box_corners_world
            })

    if not pedestrians:
        continue

    # Visualisation
    plt.figure(figsize=(12, 8))
    plt.imshow(image)
    plt.axis('off')

    for ped in pedestrians:
        pts2d = image_sample.project_pts(ped['corners'])
        keep = (pts2d[:, 0] >= 0) & (pts2d[:, 0] < image.shape[1]) & \
               (pts2d[:, 1] >= 0) & (pts2d[:, 1] < image.shape[0])
        pts2d = pts2d[keep]
        if pts2d.shape[0] == 0:
            continue

        x_min, y_min = pts2d.min(axis=0)
        x_max, y_max = pts2d.max(axis=0)

        rect = plt.Rectangle((x_min, y_min), x_max - x_min, y_max - y_min,
                             edgecolor='lime', linewidth=2, fill=False)
        plt.gca().add_patch(rect)

        plt.text(x_min, y_min - 10,
                 f"{ped['taille_cm']:.1f} cm | {ped['dist_m']:.1f} m",
                 color='lime', fontsize=12, weight='bold')

    plt.title(f"Frame {frame_idx} - {len(pedestrians)} piétons détectés")
    save_path = os.path.join(output_dir, f'frame_{frame_idx:04d}.png')
    plt.savefig(save_path, bbox_inches='tight', pad_inches=0)
    plt.close()

    print(f"Frame {frame_idx} enregistrée avec {len(pedestrians)} piétons.")

print("Tout est terminé. Images sauvegardées dans :", output_dir)
