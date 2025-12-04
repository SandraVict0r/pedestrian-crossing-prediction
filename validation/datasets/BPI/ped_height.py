"""
ped_height.py
--------------

Objectif
--------
Estimer la **taille du piéton en centimètres** pour chaque frame d’un dataset
BPI-like, en utilisant :

1. **LiDAR** (méthode principale)
2. **Fallback image (keypoints)** si la focale f_px est connue

Le module :
- charge les nuages de points (.pcd/.ply/.bin/.mat),
- recadre autour de la position LiDAR du piéton,
- estime le sol local,
- calcule la hauteur du piéton,
- filtre les valeurs aberrantes,
- fournit une estimation *par frame* + la source utilisée.

Sorties :
---------
Deux Series Pandas alignées avec le DataFrame d'entrée :
    - ped_height_cm : taille estimée en cm
    - height_source : "lidar:ok", "lidar:too_few_points", "image:ok", "none", etc.

Méthode :
---------
LiDAR :
    hauteur = percentile_99(z) - z_ground

Image (fallback) :
    stature ≈ (h_pix / f_px) * distance / eye_ratio

Compatibilité :
---------------
Utilisé dans :
    annotate_crossing.py
    annotate_crossing_intention.py

Dépendances optionnelles :
--------------------------
open3d : lecture .pcd / .ply  
scipy  : lecture .mat  
Si absents → le code gère proprement les fallback et avertissements.

"""

# ======================================================================
# IMPORTS & CONFIG
# ======================================================================

import os, glob, re, sys, contextlib
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# Réduction de la verbosité Open3D (avant import !)
# ----------------------------------------------------------------------
os.environ.setdefault("OPEN3D_VERBOSITY_LEVEL", "Error")

try:
    import open3d as o3d
    try:
        o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Fatal)
    except Exception:
        pass
    _HAS_O3D = True
except Exception:
    o3d = None
    _HAS_O3D = False

# ======================================================================
# OUTILS : Suppression temporaire stdout/stderr C (Open3D)
# ======================================================================

@contextlib.contextmanager
def _suppress_c_stdout_stderr():
    """
    Supprime temporairement les messages C++ / Open3D
    (utile pour éviter le spam dans les notebooks).
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        old_stdout_fd = os.dup(1)
        old_stderr_fd = os.dup(2)
        with open(os.devnull, "wb") as devnull:
            os.dup2(devnull.fileno(), 1)
            os.dup2(devnull.fileno(), 2)
            try:
                yield
            finally:
                os.dup2(old_stdout_fd, 1)
                os.dup2(old_stderr_fd, 2)
                os.close(old_stdout_fd)
                os.close(old_stderr_fd)
    except Exception:
        yield

# ======================================================================
# HELPERS : colonnes, dossiers, chargement de nuages de points
# ======================================================================

def _find_col(df, suffix):
    """ Trouve une colonne du DF se terminant par `suffix`. """
    hits = [c for c in df.columns if str(c).endswith(suffix)]
    if not hits:
        raise KeyError(f"Colonne se terminant par '{suffix}' introuvable.")
    return hits[0]


def _candidate_dirs_from_root(pcl_root):
    """
    Déduit les dossiers potentiels contenant les nuages de points
    à partir de la racine de session.
    """
    cands = [pcl_root]
    base = os.path.basename(pcl_root).lower()

    # Déjà un dossier LiDAR
    if base.startswith("sync_") or base in ("pcl1", "pcl2"):
        roots = [pcl_root]
    else:
        # Sinon essayer des dossiers standard
        roots = [
            os.path.join(pcl_root, sub)
            for sub in ("sync_pcl1", "sync_pcl1_mat", "pcl1", "pcl2")
        ]

    for d in roots:
        if os.path.isdir(d) and d not in cands:
            cands.append(d)

    return cands


def _load_pointcloud_for_frame(pcl_root, lidar_frame):
    """
    Recherche le fichier point cloud correspondant au frame donné.
    Supporte : .pcd / .ply / .bin / .mat
    """
    fid = int(lidar_frame)
    frame_strs = [f"{fid:06d}", f"{fid:05d}", str(fid)]
    candidate_dirs = _candidate_dirs_from_root(pcl_root)

    exts = [".pcd", ".ply", ".bin", ".mat"]

    for base in candidate_dirs:
        for s in frame_strs:
            for ext in exts:
                pats = glob.glob(os.path.join(base, f"*{s}*{ext}"))
                if pats:
                    pats.sort(key=lambda p: len(os.path.basename(p)))
                    return pats[0]
    return None


def _read_pointcloud(path):
    """
    Lit un nuage de points depuis différents formats.
    Retourne un tableau (N,3) float32.
    """
    ext = os.path.splitext(path)[1].lower()

    if ext in [".pcd", ".ply"]:
        if not _HAS_O3D:
            raise RuntimeError("open3d requis pour .pcd/.ply")
        with _suppress_c_stdout_stderr():
            pcd = o3d.io.read_point_cloud(path)
        return np.asarray(pcd.points)

    elif ext == ".bin":
        pts = np.fromfile(path, dtype=np.float32).reshape(-1, 4)[:, :3]
        return pts

    elif ext == ".mat":
        try:
            from scipy.io import loadmat
        except Exception as e:
            raise RuntimeError("scipy requis pour .mat") from e

        m = loadmat(path)
        # Recherche heuristique
        for k in ["points", "pc", "xyz", "XYZ", "cloud", "pts"]:
            if k in m:
                arr = np.asarray(m[k]).reshape(-1, np.asarray(m[k]).shape[-1])
                if arr.shape[1] >= 3:
                    return arr[:, :3]

        # Dernier recours : recherche de matrice 2D assez large
        for v in m.values():
            a = np.asarray(v)
            if a.ndim == 2 and (a.shape[1] >= 3 or a.shape[0] >= 3):
                a = a if a.shape[1] >= 3 else a.T
                return a[:, :3]

        raise ValueError(f"Impossible d'extraire XYZ depuis {path}")

    else:
        raise ValueError(f"Format point cloud non supporté : {ext}")

# ======================================================================
# PRÉ-TRAITEMENT SPATIAL (crop + sol)
# ======================================================================

def _crop_around(points_xyz, center_xy, box_xy=(2.5, 2.0)):
    """ Coupe un rectangle centré sur (ped_x, ped_y). """
    x, y = points_xyz[:, 0], points_xyz[:, 1]
    cx, cy = center_xy
    mask = (np.abs(x - cx) <= box_xy[0]) & (np.abs(y - cy) <= box_xy[1])
    return points_xyz[mask]


def _remove_ground_local(points_xyz, quantile_ground=0.1):
    """
    Estime le sol local comme le quantile bas de z.
    Filtre les extrêmes > p99.5.
    """
    if points_xyz.size == 0:
        return np.nan, points_xyz

    z = points_xyz[:, 2]
    z_ground = np.nanpercentile(z, quantile_ground * 100.0)
    z_hi = np.nanpercentile(z, 99.5)
    keep = (z >= z_ground) & (z <= z_hi)
    return z_ground, points_xyz[keep]

# ======================================================================
# ESTIMATION DE LA TAILLE : LiDAR & Image
# ======================================================================

def estimate_height_from_lidar(pcl_root, lidar_frame, ped_x, ped_y,
                               crop_box=(2.5, 2.0), head_q=99.0,
                               min_points=15):
    """
    Estime la hauteur (m) du piéton depuis LiDAR.
    Procédure :
      1. Charge point cloud du frame.
      2. Recadre autour du piéton (crop_box).
      3. Estime sol local.
      4. Hauteur = percentile_99(z) - z_ground.
      5. Filtre hors bornes.

    Retour :
        (hauteur_m, source)
    """
    pcl_path = _load_pointcloud_for_frame(pcl_root, lidar_frame)
    if pcl_path is None:
        return np.nan, "no_pcl_file"

    pts = _read_pointcloud(pcl_path)
    sub = _crop_around(pts, (ped_x, ped_y), crop_box)

    if sub.shape[0] < min_points:
        return np.nan, f"too_few_points({sub.shape[0]})"

    z_ground, sub2 = _remove_ground_local(sub)
    if not np.isfinite(z_ground) or sub2.shape[0] < max(10, min_points // 2):
        return np.nan, "bad_ground"

    z_head = np.nanpercentile(sub2[:, 2], head_q)
    h = float(z_head - z_ground)

    if h <= 0:
        return np.nan, "non_positive_height"

    if h < 0.9 or h > 2.5:  # valeurs réalistes adultes
        return np.nan, "height_out_of_range"

    return h, "ok"


def estimate_height_from_keypoints(row, f_px=None, eye_ratio=0.94):
    """
    Estimation fallback via taille en pixels :
        stature ≈ (h_pix / f_px) * distance / eye_ratio
    """
    if f_px is None or not np.isfinite(f_px):
        return np.nan, "no_focal"

    # Recherche keypoints
    def endwith(cols, suffixes):
        return [c for c in cols if any(str(c).endswith(s) for s in suffixes)]

    eye_keys = endwith(row.index, ("r_eye_y", "l_eye_y", "r_ear_y", "l_ear_y"))
    ank_keys = endwith(row.index, ("l_ankle_y", "r_ankle_y"))

    if not eye_keys or not ank_keys:
        return np.nan, "no_keypoints"

    eye_y = np.nanmin([row[k] for k in eye_keys])
    ankle_y = np.nanmax([row[k] for k in ank_keys])

    if not (np.isfinite(eye_y) and np.isfinite(ankle_y)):
        return np.nan, "no_keypoints"

    h_pix = float(ankle_y - eye_y)
    if h_pix <= 0:
        return np.nan, "bad_pixel_height"

    ped_x = row.get("006_lidar_ped_x", row.get("lidar_ped_x", np.nan))
    ped_y = row.get("007_lidar_ped_y", row.get("lidar_ped_y", np.nan))

    if not np.isfinite(ped_x) or not np.isfinite(ped_y):
        return np.nan, "no_lidar_xy"

    dist = float(np.hypot(ped_x, ped_y))

    eye_height_m = (h_pix / f_px) * dist
    stature_m = eye_height_m / eye_ratio

    if stature_m < 0.9 or stature_m > 2.5:
        return np.nan, "fallback_out_of_range"

    return stature_m, "ok"

# ======================================================================
# FONCTION PRINCIPALE APPLIQUÉE AU DATAFRAME
# ======================================================================

def estimate_ped_height_cm_for_df(df, pcl_root,
                                  f_px=None,
                                  crop_box=(2.5, 2.0),
                                  head_q=99.0,
                                  min_points=15):
    """
    Applique l’estimation de taille à chaque ligne du DataFrame.
    Retour :
        Series(height_cm), Series(source)
    """
    n_col  = _find_col(df, "number")
    fr_col = _find_col(df, "lidar_frame")
    x_col  = _find_col(df, "lidar_ped_x")
    y_col  = _find_col(df, "lidar_ped_y")

    heights_cm = np.full(len(df), np.nan)
    sources = np.array(["none"] * len(df), dtype=object)

    for i, row in df.iterrows():
        try:
            # Tentative LiDAR
            h_m, src = estimate_height_from_lidar(
                pcl_root=pcl_root,
                lidar_frame=row[fr_col],
                ped_x=row[x_col],
                ped_y=row[y_col],
                crop_box=crop_box,
                head_q=head_q,
                min_points=min_points
            )
            if np.isfinite(h_m):
                heights_cm[i] = h_m * 100.0
                sources[i] = f"lidar:{src}"
                continue

            # Fallback image
            if f_px is not None:
                h_m, src2 = estimate_height_from_keypoints(row, f_px=f_px)
                if np.isfinite(h_m):
                    heights_cm[i] = h_m * 100.0
                    sources[i] = f"image:{src2}"
                else:
                    sources[i] = f"fail:{src}->{src2}"
            else:
                sources[i] = f"lidar:{src}"

        except Exception as e:
            sources[i] = f"error:{e}"

    return (
        pd.Series(heights_cm, index=df.index, name="ped_height_cm"),
        pd.Series(sources,     index=df.index, name="height_source")
    )

# ======================================================================
# DIAGNOSTIC OPTIONNEL
# ======================================================================

def debug_frame(pcl_root, lidar_frame, ped_x, ped_y, crop_box=(2.5, 2.0)):
    """
    Renvoie quelques indicateurs utiles pour debugging des frames.
    """
    path = _load_pointcloud_for_frame(pcl_root, lidar_frame)
    if not path:
        return {"status": "no_file"}

    pts = _read_pointcloud(path)
    total = int(pts.shape[0]) if pts.ndim == 2 else 0
    sub = _crop_around(pts, (ped_x, ped_y), crop_box)

    return {
        "status": "ok",
        "file": os.path.basename(path),
        "total_points": total,
        "in_crop": int(sub.shape[0]),
        "crop_box": crop_box
    }
