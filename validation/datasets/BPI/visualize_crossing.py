"""
visualize_crossing.py
---------------------

Objectif
--------
Outil d’inspection visuelle permettant de détecter les changements de côté
de la route d’un piéton dans le dataset BPI, en analysant :

    - le signe de `012_lidar_pc_lat` (distance latérale piéton-véhicule)
    - uniquement sur les frames où LiDAR est valide
    - les instants où le signe change : (- → +) ou (+ → -)

Pour chaque événement, le script :
    1. Affiche en console les détails du changement
    2. Charge et affiche (si activé) les images associées aux timestamps
       -> images supposées nommées "<lidar_time_stamp>.png"

Ce script ne produit **aucun fichier de sortie** :
→ il sert uniquement à la validation visuelle / debugging des annotations BPI.

Usage attendu
-------------
- Inspecter les mouvements latéraux du piéton
- Vérifier manuellement qu'un crossing est cohérent
- Visualiser la correspondance frame LiDAR ↔ image

Dépendances optionnelles
------------------------
- matplotlib (affichage)
- cv2 (fallback)
Le script fonctionne en mode console sans affichage si rien n’est installé.

"""

# ======================================================================
# IMPORTS & CONFIGURATION
# ======================================================================

import os, glob, re, sys
import numpy as np
import pandas as pd
from typing import List, Optional

# Encodage UTF-8 console (no-op si unsupported)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ======================================================================
# CHEMINS D’ENTRÉE
# ======================================================================

# CSV issus du dossier BPI après extraction sensorielle
INPUT_DIR = r"C:\Users\svictor\Documents\BPI_Dataset\extracted_csvfiles"

# Dossiers images contenant les frames <timestamp>.png
IMG_ROOTS = [
    r"C:\Users\svictor\Documents\BPI_Dataset\raw_data\data_2018-01-28-14-57-55\image",
    r"C:\Users\svictor\Documents\BPI_Dataset\raw_data\data_2018-01-28-14-58-46\image",
    r"C:\Users\svictor\Documents\BPI_Dataset\raw_data\data_2018-01-28-15-00-12\image",
]

SHOW_IMAGES = True  # désactiver pour mode console uniquement

# Backends d’affichage
try:
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except Exception:
    HAVE_MPL = False

try:
    import cv2
    HAVE_CV2 = True
except Exception:
    HAVE_CV2 = False

# ======================================================================
# UTILITAIRES : Recherche de colonnes et tri temporel
# ======================================================================

def find_col(df: pd.DataFrame, suffix: str) -> str:
    """
    Retourne la colonne qui se termine par `suffix`
    (gère les préfixes numériques comme '000_...').
    """
    if suffix in df.columns:
        return suffix
    hits = [c for c in df.columns if str(c).endswith(suffix)]
    if not hits:
        raise KeyError(f"Colonne se terminant par '{suffix}' introuvable.")
    if len(hits) > 1:
        def prefnum(x):
            m = re.match(r"^(\d+)_", str(x))
            return int(m.group(1)) if m else 10**9
        hits.sort(key=prefnum)
    return hits[0]


def pick_time_col(df: pd.DataFrame) -> str:
    """
    Sélectionne une colonne de temps appropriée pour trier le DataFrame.
    Ignorer 'image_rel_time' pour éviter des collisions.
    """
    priorities = ["001_rel_time", "rel_time", "lidar_rel_time", "can_rel_time", "imu_rel_time"]
    for name in priorities:
        cands = [c for c in df.columns if c.endswith(name) and "image_rel_time" not in c]
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1 and name == "rel_time":
            # Choisir celle avec plus petit préfixe numérique
            def prefnum(x):
                m = re.match(r"^(\d+)_", str(x))
                return int(m.group(1)) if m else 10**9
            return sorted(cands, key=prefnum)[0]

    # fallback
    rels = [c for c in df.columns if c.endswith("rel_time") and "image_rel_time" not in c]
    if rels:
        def prefnum(x):
            m = re.match(r"^(\d+)_", str(x))
            return int(m.group(1)) if m else 10**9
        return sorted(rels, key=prefnum)[0]

    df["_idx"] = np.arange(len(df))
    return "_idx"

# ======================================================================
# DÉTECTION DES CHANGEMENTS DE SIGNE pc_lat
# ======================================================================

def detect_sign_changes(pc_lat: np.ndarray, valid_mask: np.ndarray, sort_index: np.ndarray):
    """
    Détecte les transitions de signe de 012_lidar_pc_lat
    exclusivement sur les frames où LiDAR est valide.

    Retour : liste d’événements :
        {
            "idx_prev": index frame précédente,
            "idx_curr": index frame actuelle,
            "sign_prev": -1 ou +1,
            "sign_curr": -1 ou +1
        }
    """
    events = []
    I = sort_index[valid_mask[sort_index]]
    if I.size == 0:
        return events

    last_sign = 0
    last_idx = None

    for idx in I:
        val = pc_lat[idx]
        if not np.isfinite(val):
            continue

        s = -1 if val < 0 else (1 if val > 0 else 0)
        if s == 0:
            continue  # ignorer les zéros

        if last_sign == 0:
            last_sign, last_idx = s, idx
            continue

        if s != last_sign:
            events.append({
                "idx_prev": int(last_idx),
                "idx_curr": int(idx),
                "sign_prev": int(last_sign),
                "sign_curr": int(s),
            })
            last_sign, last_idx = s, idx

    return events

# ======================================================================
# RECHERCHE DES IMAGES <timestamp>.png
# ======================================================================

def _png_candidates_from_ts(ts_val) -> List[str]:
    """
    Génère les variantes plausibles du nom de l'image correspondant à
    005_lidar_time_stamp.
    """
    out = []
    if ts_val is None:
        return out

    s = str(ts_val).strip()
    if s:
        out.append(s)
        out.append(s.replace(" ", "").replace("'", "").replace('"', ""))

    try:
        as_int = int(float(s))
        if str(as_int) not in out:
            out.append(str(as_int))
    except Exception:
        pass

    return out


def find_image_path(ts_val) -> Optional[str]:
    """Retourne la première image existante correspondant au timestamp."""
    bases = _png_candidates_from_ts(ts_val)
    for root in IMG_ROOTS:
        if not os.path.isdir(root):
            continue
        for base in bases:
            p = os.path.join(root, base + ".png")
            if os.path.isfile(p):
                return p
    return None

# ======================================================================
# AFFICHAGE DES IMAGES
# ======================================================================

def _load_rgb(path: str) -> Optional[np.ndarray]:
    """Charge une image en RGB (matplotlib ou cv2)."""
    try:
        if HAVE_MPL:
            import matplotlib.image as mpimg
            return mpimg.imread(path)
        elif HAVE_CV2:
            img = cv2.imread(path)
            if img is None:
                return None
            return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        else:
            return None
    except Exception:
        return None


def show_pair(img_prev: Optional[str], img_curr: Optional[str], title: str):
    """
    Affiche 1 ou 2 images côte-à-côte selon disponibilité.
    Pause jusqu’à interaction utilisateur.
    """
    if not SHOW_IMAGES:
        return

    if not HAVE_MPL and not HAVE_CV2:
        print("[INFO] Aucun backend (matplotlib/cv2) disponible.")
        return

    im1 = _load_rgb(img_prev) if img_prev else None
    im2 = _load_rgb(img_curr) if img_curr else None

    if im1 is None and im2 is None:
        print("[INFO] Aucune image à afficher.")
        return

    # --- Avec Matplotlib ---
    if HAVE_MPL:
        import matplotlib.pyplot as plt
        ncols = 2 if (im1 is not None and im2 is not None) else 1
        fig, axes = plt.subplots(1, ncols, figsize=(10, 5))
        if ncols == 1:
            axes = [axes]

        if im1 is not None:
            axes[0].imshow(im1)
            axes[0].set_title("prev")
            axes[0].axis("off")
        else:
            axes[0].axis("off")

        if ncols == 2:
            axes[1].imshow(im2)
            axes[1].set_title("curr")
            axes[1].axis("off")

        fig.suptitle(title)
        plt.tight_layout()
        plt.show(block=False)
        print("Press a key in the figure window to continue...")
        try:
            plt.waitforbuttonpress(0)
        except Exception:
            pass
        plt.close(fig)
        return

    # --- Fallback OpenCV ---
    if HAVE_CV2:
        if im1 is None:
            im_show = im2
        elif im2 is None:
            im_show = im1
        else:
            # concat horizontale
            h = min(im1.shape[0], im2.shape[0])
            scale_resize = lambda img: cv2.resize(img, (int(img.shape[1] * (h / img.shape[0])), h))
            im_show = np.hstack([scale_resize(im1), scale_resize(im2)])

        if im_show is not None:
            cv2.imshow(title, cv2.cvtColor(im_show, cv2.COLOR_RGB2BGR))
            print("Press any key in the window to continue...")
            cv2.waitKey(0)
            cv2.destroyAllWindows()

# ======================================================================
# TRAITEMENT D’UN FICHIER CSV
# ======================================================================

def process_csv(path: str):
    base = os.path.basename(path)

    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception as e:
        print(f"[WARN] {base}: lecture impossible: {e}")
        return

    # Colonnes nécessaires
    try:
        time_col   = pick_time_col(df)
        pc_lat_col = find_col(df, "lidar_pc_lat")     # 012_lidar_pc_lat
        valid_col  = find_col(df, "lidar_is_valid")   # 002_lidar_is_valid
        ts_col     = find_col(df, "lidar_time_stamp") # 005_lidar_time_stamp
    except KeyError as e:
        print(f"[WARN] {base}: {e}")
        return

    # Trier temporellement
    df = df.sort_values(by=[time_col]).reset_index(drop=True)
    order = df.index.to_numpy()

    pc_lat  = pd.to_numeric(df[pc_lat_col], errors="coerce").astype(float).to_numpy()
    valid   = (pd.to_numeric(df[valid_col], errors="coerce") == 1).to_numpy()
    rel_t   = pd.to_numeric(df[time_col], errors="coerce").astype(float).to_numpy()
    ts_vals = df[ts_col]

    # Détection des événements de crossing
    events = detect_sign_changes(pc_lat, valid, order)

    if not events:
        print(f"[INFO] {base}: aucun changement de signe détecté.")
        return

    print(f"\n=== {base} : {len(events)} événement(s) crossing détecté(s) ===")

    for k, ev in enumerate(events, 1):
        i, j = ev["idx_prev"], ev["idx_curr"]
        direction = "-to+" if ev["sign_prev"] < ev["sign_curr"] else "+to-"

        vi, vj = pc_lat[i], pc_lat[j]
        rt_i, rt_j = rel_t[i], rel_t[j]
        ts_i, ts_j = ts_vals.iloc[i], ts_vals.iloc[j]

        img_i = find_image_path(ts_i)
        img_j = find_image_path(ts_j)

        print(f"[{k:02d}] {base} | idx {i}->{j} | dir {direction} | "
              f"pc_lat {vi:.6f}->{vj:.6f} | t {rt_i:.3f}s->{rt_j:.3f}s")
        print(f"     img_prev: {img_i if img_i else 'NON TROUVÉE'}")
        print(f"     img_curr: {img_j if img_j else 'NON TROUVÉE'}")

        title = f"{base} [{k}/{len(events)}] {direction} | {vi:.3f}->{vj:.3f} | t {rt_i:.2f}s->{rt_j:.2f}s"
        show_pair(img_i, img_j, title)

# ======================================================================
# MAIN
# ======================================================================

def main():
    files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.csv")))
    if not files:
        print(f"Aucun CSV trouvé dans {INPUT_DIR}")
        return

    for f in files:
        process_csv(f)

if __name__ == "__main__":
    main()
