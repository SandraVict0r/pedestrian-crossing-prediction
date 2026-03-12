import os
import numpy as np
import pandas as pd
from math import radians, cos
from tqdm import tqdm

# ============================================================
# annotation_crossing.py — PIXSET
# ------------------------------------------------------------
# Objectif :
#   Annoter automatiquement, dans chaque CSV PIXSET (un scénario / une séquence),
#   les frames où un piéton est considéré en "crossing" (traversée),
#   en détectant un croisement "strict" entre la trajectoire piéton et la trajectoire ego.
#
# Méthode (résumé) :
#   1) Convertir les positions GPS (lat/lon) en coordonnées XY (mètres) dans un repère local.
#   2) Pour chaque piéton :
#        - construire les segments consécutifs de sa trajectoire (P1->P2)
#        - construire les segments consécutifs de l'ego sur les mêmes frames (Q1->Q2)
#        - détecter s'il existe une intersection segment/segment (croisement strict)
#   3) Si intersection détectée :
#        - définir "la frame de croisement" (cross_frame)
#        - estimer si le piéton est du "même côté" ou "côté opposé" par rapport
#          à la direction de l’ego juste avant le croisement (produit vectoriel)
#        - appliquer une marge en mètres AVANT/APRÈS cette frame
#          (OPPOSITE_MARGIN_M ou SAME_MARGIN_M) le long de la trajectoire piéton
#        - marquer ces frames comme crossing=True et stocker crossing_frame_id
#
# Sortie :
#   Le CSV est ré-écrit (in-place) avec deux colonnes ajoutées :
#     - crossing: bool
#     - crossing_frame_id: Int64 (frame_id de l'intersection "strict")
# ============================================================

# ====== Config ======
csv_dir = r"C:\Users\svictor\Documents\PIXSET\output"

# Marges (en mètres) autour du point de croisement :
# - si le piéton vient "en face" (opposite) => on marque plus large
# - si le piéton est "même côté" (same) => marge plus petite
OPPOSITE_MARGIN_M   = 7.0
SAME_MARGIN_M       = 3.5


# ============================================================
# Conversion lat/lon -> mètres (repère local)
# ============================================================
def latlon_to_xy_m(lat, lon, lat0, lon0):
    """
    Conversion locale lat/lon -> XY (m) autour d’un point de référence (lat0, lon0).

    Approximation equirectangulaire :
      - 1 degré latitude ~ 111,320 m
      - 1 degré longitude ~ 111,320 * cos(lat0) m

    Suffisant pour des zones petites / séquences courtes (PIXSET).
    """
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * cos(radians(lat0))

    # x ~ Est/Ouest, y ~ Nord/Sud
    x = (lon - lon0) * m_per_deg_lon
    y = (lat - lat0) * m_per_deg_lat
    return x, y


def cumulative_euclid(x, y):
    """
    Distance cumulée (m) le long d'une trajectoire (x(t), y(t)).
    Renvoie un vecteur cum_dist tel que cum_dist[i] = distance parcourue de 0 à i.
    """
    if len(x) <= 1:
        return np.zeros_like(x, dtype=float)
    return np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])


# ============================================================
# Détection d'intersection segments (vectorisée)
# ============================================================
def orient(ax, ay, bx, by, cx, cy):
    """
    Orientation (produit vectoriel 2D) du triplet (A,B,C).
    >0 : C à gauche de AB
    <0 : C à droite de AB
    =0 : colinéaire
    """
    return (cy - ay) * (bx - ax) - (by - ay) * (cx - ax)


def segments_intersections_matrix(P1x, P1y, P2x, P2y, Q1x, Q1y, Q2x, Q2y):
    """
    Test d'intersection strict segment/segment, en mode matrice.
    - Les segments P (piéton) sont indexés i
    - Les segments Q (ego) sont indexés j
    Renvoie une matrice bool inter[i,j].

    Remarque:
      - Condition "stricte" : o1*o2 < 0 & o3*o4 < 0
        => exclut les cas colinéaires / tangences parfaites.
      - Filtre AABB (Axis-Aligned Bounding Box) pour éviter des faux positifs.
    """
    # Broadcast pour obtenir une matrice i x j
    P1x = P1x[:, None]; P1y = P1y[:, None]
    P2x = P2x[:, None]; P2y = P2y[:, None]
    Q1x = Q1x[None, :]; Q1y = Q1y[None, :]
    Q2x = Q2x[None, :]; Q2y = Q2y[None, :]

    o1 = orient(P1x, P1y, P2x, P2y, Q1x, Q1y)
    o2 = orient(P1x, P1y, P2x, P2y, Q2x, Q2y)
    o3 = orient(Q1x, Q1y, Q2x, Q2y, P1x, P1y)
    o4 = orient(Q1x, Q1y, Q2x, Q2y, P2x, P2y)

    # Intersection "stricte"
    inter = (o1 * o2 < 0) & (o3 * o4 < 0)

    # Filtre bounding box (AABB) : les rectangles englobants doivent se chevaucher
    aabb = (
        (np.maximum(P1x, P2x) >= np.minimum(Q1x, Q2x)) &
        (np.maximum(Q1x, Q2x) >= np.minimum(P1x, P2x)) &
        (np.maximum(P1y, P2y) >= np.minimum(Q1y, Q2y)) &
        (np.maximum(Q1y, Q2y) >= np.minimum(P1y, P2y))
    )
    return inter & aabb


def compute_side_xy(ped_x, ped_y, ego1_x, ego1_y, ego2_x, ego2_y):
    """
    Classement "same" vs "opposite" côté piéton par rapport au déplacement de l’ego,
    juste avant l'intersection.

    On calcule le signe du produit vectoriel :
      - d = ego2 - ego1  (direction de déplacement ego)
      - v = ped  - ego1  (vecteur vers le piéton)
      cross = d x v

    Ici :
      cross < 0 => 'opposite'
      sinon    => 'same'
    (le mapping dépend du repère choisi ; l'important est la cohérence.)
    """
    vx = ped_x - ego1_x
    vy = ped_y - ego1_y
    dx = ego2_x - ego1_x
    dy = ego2_y - ego1_y
    cross = dx * vy - dy * vx
    return 'opposite' if cross < 0 else 'same'


# ============================================================
# Traitement d'un fichier CSV (in-place)
# ============================================================
def process_file(path):
    """
    Lit un CSV PIXSET, détecte les crossings stricts pour chaque piéton,
    puis écrit le même CSV avec les colonnes:
      - crossing (bool)
      - crossing_frame_id (Int64)
    Retourne : (nb_piétons_uniques, nb_crossings_detectés)
    """
    try:
        df = pd.read_csv(path)
    except Exception:
        # Fichier illisible => on compte 0
        return 0, 0

    # Colonnes minimales attendues
    required = ['frame_id','ego_lon','ego_lat','pedestrian_id','ped_lon','ped_lat']
    if df.empty or any(c not in df.columns for c in required):
        return 0, 0

    # Trier par frame pour garantir l'ordre temporel
    df = df.sort_values('frame_id').reset_index(drop=True)

    # Colonnes de sortie (initialisées à "pas crossing")
    df['crossing'] = False
    df['crossing_frame_id'] = pd.NA

    # Référence lat/lon pour passer en mètres : median ego (robuste aux outliers)
    lat0 = df['ego_lat'].dropna().median()
    lon0 = df['ego_lon'].dropna().median()

    # Projection locale (mètres) pour piéton et ego
    df['ped_x'], df['ped_y'] = latlon_to_xy_m(df['ped_lat'], df['ped_lon'], lat0, lon0)
    df['ego_x'], df['ego_y'] = latlon_to_xy_m(df['ego_lat'], df['ego_lon'], lat0, lon0)

    total_detected = 0
    ped_ids = df['pedestrian_id'].dropna().unique()

    # ----------------------------------------
    # Boucle piéton par piéton
    # ----------------------------------------
    for ped_id in ped_ids:
        # Trajectoire piéton (sur toutes ses frames)
        df_ped = df[df['pedestrian_id'] == ped_id].sort_values('frame_id')

        # Trajectoire ego restreinte aux mêmes frames que df_ped
        # (on suppose que la voiture a 1 ligne par frame_id dans df)
        df_veh = df[df['frame_id'].isin(df_ped['frame_id'])].sort_values('frame_id')

        if len(df_ped) < 2 or len(df_veh) < 2:
            continue

        # Segments piéton (P1->P2) et ego (Q1->Q2)
        P1x, P1y = df_ped['ped_x'].values[:-1], df_ped['ped_y'].values[:-1]
        P2x, P2y = df_ped['ped_x'].values[1:],  df_ped['ped_y'].values[1:]
        Q1x, Q1y = df_veh['ego_x'].values[:-1], df_veh['ego_y'].values[:-1]
        Q2x, Q2y = df_veh['ego_x'].values[1:],  df_veh['ego_y'].values[1:]

        # Matrice intersection (i segments piéton) x (j segments ego)
        inter_mat = segments_intersections_matrix(P1x, P1y, P2x, P2y, Q1x, Q1y, Q2x, Q2y)
        if not inter_mat.any():
            continue

        # On prend la PREMIÈRE intersection trouvée (ordre de argwhere)
        ped_seg_idx, veh_seg_idx = np.argwhere(inter_mat)[0]

        # Frame associée au début du segment piéton qui intersecte
        cross_frame = df_ped.iloc[ped_seg_idx]['frame_id']
        total_detected += 1

        # On regarde juste AVANT cross_frame pour définir le côté
        try:
            pre = df_ped[df_ped['frame_id'] < cross_frame].iloc[-1]
            ego1 = df_veh[df_veh['frame_id'] < cross_frame].iloc[-2]
            ego2 = df_veh[df_veh['frame_id'] < cross_frame].iloc[-1]
        except IndexError:
            # pas assez d'historique => skip
            continue

        side = compute_side_xy(
            pre['ped_x'], pre['ped_y'],
            ego1['ego_x'], ego1['ego_y'],
            ego2['ego_x'], ego2['ego_y']
        )

        # Marge (m) à appliquer autour de l'intersection
        dist_required = OPPOSITE_MARGIN_M if side == 'opposite' else SAME_MARGIN_M

        # Distance cumulée le long de la trajectoire piéton
        cum_dist = cumulative_euclid(df_ped['ped_x'].values, df_ped['ped_y'].values)

        # Index (dans df_ped) de la frame d'intersection
        cross_idx = df_ped.index.get_loc(df_ped[df_ped['frame_id'] == cross_frame].index[0])

        # Étendre vers l'arrière jusqu'à atteindre dist_required
        start_idx = cross_idx
        while start_idx > 0 and (cum_dist[cross_idx] - cum_dist[start_idx]) < dist_required:
            start_idx -= 1

        # Étendre vers l'avant jusqu'à atteindre dist_required
        end_idx = cross_idx
        while end_idx < len(df_ped) - 1 and (cum_dist[end_idx] - cum_dist[cross_idx]) < dist_required:
            end_idx += 1

        # Frames considérées "crossing" autour du point de croisement strict
        crossing_frames = df_ped.iloc[start_idx:end_idx + 1]['frame_id']

        # Écriture dans le DF global
        df.loc[
            (df['pedestrian_id'] == ped_id) & (df['frame_id'].isin(crossing_frames)),
            'crossing'
        ] = True

        df.loc[
            (df['pedestrian_id'] == ped_id) & (df['frame_id'].isin(crossing_frames)),
            'crossing_frame_id'
        ] = cross_frame

    # Typage nullable Int64 (Pandas)
    df['crossing_frame_id'] = df['crossing_frame_id'].astype('Int64')

    # Sauvegarde IN-PLACE (attention: écrase le CSV d'origine)
    df.to_csv(path, index=False)

    return len(ped_ids), total_detected


# ============================================================
# Boucle principale : traite tous les CSV du dossier
# ============================================================
for file in tqdm([f for f in os.listdir(csv_dir) if f.endswith(".csv")], desc="Fichiers CSV"):
    total_ped, detected = process_file(os.path.join(csv_dir, file))
    print(f"{file}: {detected}/{total_ped} piétons détectés en croisement strict")
