import os
import re
import numpy as np
import pandas as pd
from pioneer.das.api.platform import Platform
from math import radians, sin, cos, sqrt, atan2
from tqdm import tqdm
import importlib.util

# ============================================================
# crossing_decision_per_ped.py — PIXSET
# ------------------------------------------------------------
# Objectif :
#   - Parcourir tous les dossiers PIXSET (scénarios)
#   - Extraire, pour chaque frame et chaque piéton détecté:
#       * distance ego↔piéton (m)
#       * vitesse ego (km/h)
#       * taille piéton (cm) (depuis box3D, avec clamp)
#       * météo (classe discrète)
#       * ID piéton (track_id natif si disponible)
#   - Construire un "ground truth strict crossing" (true_label) basé sur
#     la trajectoire relative piéton vs ego dans un repère local (XY),
#     en utilisant un corridor route (lanes * lane_width + buffer).
#   - Appliquer ton modèle CNRS_behavior_model en 2 variantes:
#       * adj=True
#       * adj=False
#   - Sauvegarder un CSV par piéton et par scénario:
#       output/adj/set<scenario>/<scenario>__<ped_id>.csv
#       output/no_adj/set<scenario>/<scenario>__<ped_id>.csv
#
# Sorties principales :
#   - true_label : bool (GT crossing strict)
#   - prediction : bool (modèle)
# ============================================================

# Afficher la progression sur les apply pandas
tqdm.pandas()

# ========= Modèle =========
# Chargement dynamique de ton modèle (fichier externe)
file_path = r"E:\crossing-model\main_experiment\model_datas\CNRS_behavior_model.py"
spec = importlib.util.spec_from_file_location("pedestrian_behavior_model", file_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# ========= Paramètres I/O =========
root_dataset     = r'E:\crossing-model\main_experiment\model_validation\datasets\PIXSET\dataset'
output_csv_dir   = r'E:\crossing-model\main_experiment\model_validation\datasets\PIXSET\output'
weather_csv_path = os.path.join(root_dataset, 'weather.csv')

# Dossiers de sortie: on sépare adj / no_adj
os.makedirs(output_csv_dir, exist_ok=True)
adj_dir    = os.path.join(output_csv_dir, "adj")
no_adj_dir = os.path.join(output_csv_dir, "no_adj")
os.makedirs(adj_dir, exist_ok=True)
os.makedirs(no_adj_dir, exist_ok=True)

# ========= CSV des voies =========
# lanes_per_video.csv apporte:
#   - lanes_estimated : nb de voies estimé
#   - location_primary : typologie (highway, boulevard, downtown, suburban)
LANES_CSV_PATH = os.path.join(root_dataset, 'lanes_per_video.csv')
df_lanes = pd.read_csv(LANES_CSV_PATH)
lanes_lookup = dict(zip(df_lanes['video_id'].astype(str), df_lanes['lanes_estimated']))
loc_lookup   = dict(zip(df_lanes['video_id'].astype(str),
                        df_lanes.get('location_primary', pd.Series([None]*len(df_lanes)))))

# ========= Constantes / helpers =========
# Largeur de voie typique selon le type de route (approx.)
LANE_WIDTH_BY_LOC = {'highway': 3.7, 'boulevard': 3.5, 'downtown': 3.2, 'suburban': 3.25}
DEFAULT_LANE_WIDTH = 3.5

# Si nb de voies absent, fallback
ASSUME_LANES_IF_NONE = 2

# Buffer "trottoir" ajouté au corridor route
SIDEWALK_BUFFER_M = 1.0

# Hauteur fallback (cm) si height box3D incohérente
AVG_CANADIAN_CM = 171.0  # si taille hors [150,200], on remplace par 171

# --- IDs PixSet possibles selon versions/outils ---
# Selon l’API / version PIONEER, l’ID du track peut être stocké sous des champs différents.
CAND_ID_KEYS = ['track_id', 'tracking_id', 'id', 'uuid', 'uid', 'instance_id', 'object_id']


def extract_track_ids(boxes3d):
    """
    Tente d'extraire des IDs persistants pour chaque box3D.
    IMPORTANT:
      - Ici on refuse les fallback "fabriqués" (index i), car on veut un vrai ID.
      - Si aucun ID n'est disponible, la frame est ignorée (plus bas).
    """
    for m in ('get_track_ids', 'get_ids', 'track_ids', 'ids'):
        if hasattr(boxes3d, m):
            try:
                arr = getattr(boxes3d, m)()
                if arr is not None:
                    return np.asarray(arr).astype(str)
            except Exception:
                pass

    # Fallback: attributes / get_attributes
    for m in ('attributes', 'get_attributes'):
        if hasattr(boxes3d, m):
            try:
                attrs = getattr(boxes3d, m)()
                if isinstance(attrs, dict):
                    for k in CAND_ID_KEYS:
                        if k in attrs:
                            return np.asarray(attrs[k]).astype(str)
                if isinstance(attrs, (list, tuple)) and len(attrs) and isinstance(attrs[0], dict):
                    for k in CAND_ID_KEYS:
                        if k in attrs[0]:
                            return np.array([str(a.get(k)) for a in attrs])
            except Exception:
                pass

    # Fallback via getters unitaires
    for k in CAND_ID_KEYS:
        for m in ('get_attribute', 'get_field'):
            if hasattr(boxes3d, m):
                try:
                    arr = getattr(boxes3d, m)(k)
                    if arr is not None:
                        return np.asarray(arr).astype(str)
                except Exception:
                    pass
        m = 'get_' + k
        if hasattr(boxes3d, m):
            try:
                arr = getattr(boxes3d, m)()
                if arr is not None:
                    return np.asarray(arr).astype(str)
            except Exception:
                pass
    return None


def safe_pick_id(ids_array, i):
    """Retourne ids_array[i] si valide (non vide / non NaN), sinon None."""
    try:
        val = ids_array[i]
        if val is None:
            return None
        s = str(val).strip()
        if s.lower() == 'nan' or s == '':
            return None
        return s
    except Exception:
        return None


def sanitize_filename(name: str) -> str:
    """
    Nettoie les noms de fichiers:
      - conserve A-Z, a-z, 0-9, _ et -
      - remplace le reste par '_'
    """
    return re.sub(r'[^A-Za-z0-9_\-]+', '_', str(name)).strip('_') or 'unknown'


def haversine_distance(lat1, lon1, lat2, lon2):
    """Distance (m) via Haversine (exacte sphérique, pas un XY local)."""
    R = 6371000
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def get_weather_class(folder_name, weather_csv_path):
    """
    Convertit weather.csv -> classe discrète utilisée par ton modèle.
    Logique:
      - si snow ou twilight => ignore scénario (None)
      - night => 'night'
      - rain/clouds => 'rain'
      - day => 'clear'
    """
    try:
        df_weather = pd.read_csv(weather_csv_path)
        row = df_weather[df_weather['folder'] == folder_name]
        if row.empty:
            return None
        row = row.iloc[0]

        # règle d'exclusion
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
        tqdm.write(f"Erreur météo pour {folder_name}: {e}")
        return None


def get_lanes_and_loc(folder_name: str):
    """
    Récupère (lanes_estimated, location_primary) pour un scénario.
    Tolère un matching "prefix" si les IDs diffèrent légèrement.
    """
    vid = str(folder_name)
    if vid in lanes_lookup:
        return lanes_lookup[vid], loc_lookup.get(vid)
    for k in lanes_lookup.keys():
        if k.startswith(vid) or vid.startswith(k):
            return lanes_lookup[k], loc_lookup.get(k)
    return None, None


def lane_width(location_primary, lanes):
    """
    Déduit une largeur de voie (m):
      - priorité: type de route (location_primary)
      - sinon: heuristique nb voies
      - sinon: DEFAULT_LANE_WIDTH
    """
    if isinstance(location_primary, str):
        lw = LANE_WIDTH_BY_LOC.get(location_primary.lower())
        if lw is not None:
            return lw
    if lanes is not None:
        if lanes >= 6: return 3.7
        if lanes >= 4: return 3.5
    return DEFAULT_LANE_WIDTH


def ll_to_xy(lat, lon, lat0, lon0):
    """
    Projection equirectangulaire locale (m) autour de (lat0, lon0).
    Ici utilisée pour:
      - trajectoire ego
      - trajectoire piéton
    afin de calculer des distances latérales signées.
    """
    R = 6371000.0
    lat  = np.asarray(lat, dtype=float);  lon  = np.asarray(lon, dtype=float)
    lat0 = float(lat0); lon0 = float(lon0)
    lat_r  = np.radians(lat);  lon_r  = np.radians(lon)
    lat0_r = np.radians(lat0); lon0_r = np.radians(lon0)
    x = R * (lon_r - lon0_r) * np.cos(0.5 * (lat_r + lat0_r))
    y = R * (lat_r - lat0_r)
    return x, y


def heading_tangent(x, y):
    """
    Calcule la tangente t̂ (direction de l’ego) et la normale n̂ par frame.
    - t̂ = gradient normalisé de (x,y)
    - n̂ = rotation de t̂ de +90° ([-ty, tx])

    NOTE:
      - si l'ego est quasi immobile (gradient nul), on propage la dernière direction valide.
    """
    x = np.asarray(x); y = np.asarray(y)
    dx = np.gradient(x); dy = np.gradient(y)
    norm = np.hypot(dx, dy)

    t = np.zeros((len(x), 2), dtype=float)
    nz = norm > 1e-6
    t[nz, 0] = dx[nz] / norm[nz]; t[nz, 1] = dy[nz] / norm[nz]

    last = np.array([1.0, 0.0])
    for k in range(len(x)):
        if nz[k]:
            last = t[k]
        else:
            t[k] = last

    n = np.stack([-t[:,1], t[:,0]], axis=1)
    return t, n


def strict_crossing_mask(d_lat, corridor_half, lane_w):
    """
    Détecte une traversée "stricte" via la distance latérale signée d_lat.

    Idée:
      - On calcule d_lat = projection du vecteur (ped - ego) sur la normale n̂
      - Une traversée est détectée si:
          * le signal passe significativement d'un côté à l'autre (pos ET neg)
          * l'amplitude est suffisante (min_span)
          * le piéton a passé assez de frames dans le corridor (in_corr)

    Retour:
      - un masque booléen, généralement on marque "in_corr" (dans la chaussée)
        si les conditions de traversée sont satisfaites.
    """
    x = np.asarray(d_lat, dtype=float)
    if len(x) == 0:
        return np.zeros(0, dtype=bool)

    # Lissage médian (k=5 ~0.5s @10Hz)
    k = 5
    pad = k // 2
    x_pad = np.pad(x, (pad, pad), mode='edge')
    x_s = np.array([np.median(x_pad[i:i+k]) for i in range(len(x))])

    # Seuils stricts
    eps_sign = max(0.25 * lane_w, 0.5)     # seuil pour déclarer "côté +/−"
    min_span = max(1.0 * lane_w, 2.0)      # amplitude min entre min et max du signal
    min_frames_in_corridor = 3             # présence min dans la chaussée

    # "Dans la route"
    in_corr = np.abs(x_s) <= corridor_half

    # "Côtés" robustes
    s = np.zeros_like(x_s, dtype=int)
    s[x_s >= +eps_sign] = +1
    s[x_s <= -eps_sign] = -1

    has_pos = np.any(s == +1)
    has_neg = np.any(s == -1)
    amp_ok = (np.nanmax(x_s) - np.nanmin(x_s)) >= min_span
    corr_ok = in_corr.sum() >= min_frames_in_corridor

    has_cross = bool(has_pos and has_neg and amp_ok and corr_ok)
    if not has_cross:
        return np.zeros_like(in_corr, dtype=bool)

    # Ici, GT strict = frames dans la chaussée si traversée détectée
    return in_corr


def compute_height_cm(dimensions_i):
    """
    Convertit la hauteur (m) issue de dimensions[i][2] -> cm.
    Clamp :
      - si hors [150,200] => AVG_CANADIAN_CM (=171 cm)
    """
    try:
        h_m = float(dimensions_i[2])  # hauteur (m)
    except Exception:
        return AVG_CANADIAN_CM

    h_cm = h_m * 100.0
    if not (150.0 <= h_cm <= 200.0):
        return AVG_CANADIAN_CM
    return float(h_cm)


# ========= Dossiers =========
# On ignore "predictions" car ce n'est pas un scénario source.
folder_list = [
    f for f in os.listdir(root_dataset)
    if os.path.isdir(os.path.join(root_dataset, f)) and f != "predictions"
]


# ============================================================
# Boucle principale scénario par scénario
# ============================================================
for folder_name in tqdm(folder_list, desc="📂 Dossiers", unit="folder"):
    dataset_path = os.path.join(root_dataset, folder_name)

    # ---------- Lanes & typologie ----------
    lanes, location_primary = get_lanes_and_loc(folder_name)

    # Si lanes==0 => cas parking_lot / pas de route => pas de crossing à détecter
    if lanes == 0:
        tqdm.write(f"⛔ Dossier ignoré (parking_lot / 0 voie): {folder_name}")
        continue

    lanes_eff = lanes if (lanes is not None and not pd.isna(lanes)) else ASSUME_LANES_IF_NONE
    lane_w = lane_width(location_primary, lanes_eff)

    # Corridor route : moitié largeur totale route + buffer trottoir
    corridor_half = (lanes_eff * lane_w) / 2.0 + SIDEWALK_BUFFER_M

    # ---------- Sous-dossiers sortie ----------
    # tu préfixes "set" pour rester cohérente avec ta logique PIE
    folder_path = "set" + str(folder_name)
    adj_sdir   = os.path.join(adj_dir,   folder_path)
    noadj_sdir = os.path.join(no_adj_dir, folder_path)
    os.makedirs(adj_sdir, exist_ok=True)
    os.makedirs(noadj_sdir, exist_ok=True)

    # ---------- Chargement PIXSET via PIONEER ----------
    # synchronized : aligne 3 streams :
    #   - image flir (pas utilisée directement ici)
    #   - boxes3d deepen
    #   - navigation (gps+vel)
    try:
        pf = Platform(dataset_path)
        sync = pf.synchronized(sync_labels=[
            'flir_bbfc_flimg',
            'pixell_bfc_box3d-deepen',
            'sbgekinox_bcc_navposvel'
        ], tolerance_us=1e6)
    except Exception as e:
        tqdm.write(f"⚠️ Erreur chargement {folder_name}: {e}")
        continue

    annotations = []

    # ---------- Météo ----------
    weather_class = get_weather_class(folder_name, weather_csv_path)
    if weather_class is None:
        tqdm.write(f"⛔ Dossier ignoré (météo): {folder_name}")
        continue

    # ========================================================
    # Extraction frame par frame
    # ========================================================
    frames_bar = tqdm(range(len(sync)), leave=False, desc=f"🎞️ {folder_name}", unit="frame")
    frames_bar.set_postfix(lanes=lanes_eff, lane_w=lane_w, half_m=round(corridor_half, 2))

    for frame_idx in frames_bar:
        frame = sync[frame_idx]
        try:
            # ----------------- Ego state -----------------
            ego_sample = frame['sbgekinox_bcc_navposvel']
            raw_data = ego_sample.raw

            ego_lat = raw_data['latitude']
            ego_lon = raw_data['longitude']

            # vitesse (NED) -> norme -> km/h
            v_n, v_e, v_d = raw_data['velocity_n'], raw_data['velocity_e'], raw_data['velocity_d']
            ego_speed_kmh = sqrt(v_n**2 + v_e**2 + v_d**2) * 3.6

            # ----------------- Boxes 3D -----------------
            boxes3d = frame['pixell_bfc_box3d-deepen']
            categories = boxes3d.get_categories()
            dimensions = boxes3d.get_dimensions()
            centers    = boxes3d.get_centers()

            # IDs natifs :
            # - si on ne peut pas identifier les tracks de manière stable, on ignore la frame
            track_ids = extract_track_ids(boxes3d)
            if track_ids is None or len(track_ids) != len(categories):
                tqdm.write(f"⚠️ Pas d'IDs valides -> frame ignorée ({folder_name}, frame {frame_idx})")
                continue

            # ----------------- Piétons uniquement -----------------
            for i, category in enumerate(categories):
                if category != 'pedestrian':
                    continue

                ped_id = safe_pick_id(track_ids, i)
                if ped_id is None:
                    continue

                # Position piéton :
                # - centers[i] est dans le repère de la box
                # - compute_transform + transform_pts : passage dans le repère monde
                center = centers[i]
                transform = boxes3d.compute_transform(i)
                world_pos = boxes3d.transform_pts(transform, np.array([center]))[0]

                # Dans ton mapping :
                #   world_pos[0] ~ nord (m)
                #   world_pos[1] ~ est  (m)
                d_north = world_pos[0]
                d_east  = world_pos[1]

                # Convertir déplacement (m) -> delta lat/lon approx
                d_lat = d_north / 111320
                d_lon = d_east / (40075000 * cos(radians(ego_lat)) / 360)

                ped_lat = ego_lat + d_lat
                ped_lon = ego_lon + d_lon

                # Distance ego-ped (m)
                dist_m = haversine_distance(ego_lat, ego_lon, ped_lat, ped_lon)

                # Taille piéton depuis dimensions (m -> cm), clamp
                taille_cm = compute_height_cm(dimensions[i])

                annotations.append({
                    "scenario": folder_name,
                    "frame_id": frame_idx,
                    "taille_cm": taille_cm,
                    "dist_m": dist_m,
                    "ego_speed_kmh": ego_speed_kmh,
                    "ego_lat": ego_lat,
                    "ego_lon": ego_lon,
                    "ped_lat": ped_lat,
                    "ped_lon": ped_lon,
                    "weather": weather_class,
                    "pedestrian_id": ped_id
                })

        except Exception as e:
            tqdm.write(f"⚠️ Erreur frame {frame_idx} dans {folder_name}: {e}")
            continue

    # Construction DF scénario
    df = pd.DataFrame(annotations)
    if df.empty:
        tqdm.write(f"⚠️ Aucune donnée pour {folder_name}, CSV ignoré.")
        continue

    # ========================================================
    # Ground Truth "strict crossing"
    # ========================================================
    # Idée:
    #   - construire la trajectoire ego XY (référence)
    #   - calculer la normale n̂(frame)
    #   - pour chaque track piéton:
    #       d_lat(frame) = projection(ped-ego, n̂)
    #       mask_cross = strict_crossing_mask(d_lat, corridor_half, lane_w)
    #
    # Le GT final marque True uniquement les frames "dans la chaussée"
    # lorsque la condition de traversée complète est satisfaite.
    ego_df = df[['frame_id','ego_lat','ego_lon']].drop_duplicates('frame_id').sort_values('frame_id')
    lat0, lon0 = ego_df.iloc[0][['ego_lat','ego_lon']]

    ego_x, ego_y = ll_to_xy(ego_df['ego_lat'].values, ego_df['ego_lon'].values, lat0, lon0)
    _, N = heading_tangent(ego_x, ego_y)

    # Dicos: frame_id -> (x,y) / (nx,ny)
    ego_xy = {int(fid): (float(x), float(y)) for fid, x, y in zip(ego_df['frame_id'], ego_x, ego_y)}
    ego_n  = {int(fid): (float(nx), float(ny)) for fid, (nx, ny) in zip(ego_df['frame_id'], N)}

    df['true_label'] = False

    n_tracks = int(df['pedestrian_id'].nunique())
    tracks_bar = tqdm(total=n_tracks, leave=False, desc="🏃 pistes", unit="track")

    for ped_id, g in df.groupby('pedestrian_id'):
        g = g.sort_values('frame_id')

        # Piéton XY
        px, py = ll_to_xy(g['ped_lat'].values, g['ped_lon'].values, lat0, lon0)
        fids = g['frame_id'].astype(int).values

        # Ego XY + normale correspondantes (alignées sur fids)
        ex = np.array([ego_xy[f][0] for f in fids], dtype=float)
        ey = np.array([ego_xy[f][1] for f in fids], dtype=float)
        nx = np.array([ego_n[f][0]  for f in fids], dtype=float)
        ny = np.array([ego_n[f][1]  for f in fids], dtype=float)

        # Vecteur relatif ego->piéton
        rx = px - ex
        ry = py - ey

        # Distance latérale signée (projection sur la normale)
        d_lat = rx * nx + ry * ny

        # Masque crossing strict (dans corridor si traversée détectée)
        mask_cross = strict_crossing_mask(d_lat, corridor_half, lane_w)
        if np.any(mask_cross):
            df.loc[g.index[mask_cross], 'true_label'] = True

        tracks_bar.update(1)

    tracks_bar.close()

    # ========================================================
    # Prédictions (adj / no_adj)
    # ========================================================
    def predict_row(row, adj_value: bool):
        """
        Appel ton modèle:
          pedestrian_behavior_model(weather, height_cm, ego_speed_kmh, dist_m, adj)
        """
        return module.pedestrian_behavior_model(
            row['weather'],
            float(row['taille_cm']),
            float(row['ego_speed_kmh']),
            float(row['dist_m']),
            bool(adj_value)
        )

    df_adj   = df.copy()
    df_noadj = df.copy()

    # progress_apply => lent si énorme volume, mais permet la barre.
    df_adj['prediction']   = df_adj.progress_apply(lambda r: predict_row(r, True),  axis=1)
    df_noadj['prediction'] = df_noadj.progress_apply(lambda r: predict_row(r, False), axis=1)

    # ========================================================
    # Sauvegarde "un CSV par piéton"
    # ========================================================
    # Tu gardes ainsi des fichiers petits et faciles à tracer/visualiser.
    n_written_adj = 0
    n_written_no  = 0

    for ped_id, g_adj in df_adj.groupby('pedestrian_id'):
        fname = f"{sanitize_filename(folder_name)}__{sanitize_filename(ped_id)}.csv"

        g_no = df_noadj[df_noadj['pedestrian_id'] == ped_id]

        g_adj = g_adj.sort_values('frame_id')
        g_no  = g_no.sort_values('frame_id')

        adj_path   = os.path.join(adj_sdir,   fname)
        noadj_path = os.path.join(noadj_sdir, fname)

        g_adj.to_csv(adj_path, index=False)
        g_no.to_csv(noadj_path, index=False)

        n_written_adj += 1
        n_written_no  += 1

    # ========================================================
    # Résumé console (debug / monitoring)
    # ========================================================
    n_frames = len(df)
    n_true_frames = int(df['true_label'].sum())
    n_cross_tracks = int(df.groupby('pedestrian_id')['true_label'].any().sum())

    tqdm.write(
        f"✅ {folder_name} -> folder_path={folder_path} | lanes={lanes_eff}, lane_w={lane_w:.2f}m, "
        f"corridor_half={corridor_half:.2f}m | frames={n_frames}, "
        f"tracks={n_tracks}, crossing_tracks={n_cross_tracks}, "
        f"true_frames={n_true_frames}, files(adj/no_adj)={n_written_adj}/{n_written_no}"
    )
