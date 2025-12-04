"""
annotate_weather_gui.py
-----------------------

Objectif
--------
Ce script fournit une **interface graphique d’annotation manuelle de la météo**
pour les CSV du dataset BPI (ou tout dataset compatible).  
Il associe chaque ligne d’un CSV à une image vidéo, puis permet
d’annoter la météo correspondante parmi :

    - clear
    - rain
    - night

L’outil permet :
- de visualiser image par image,
- de corriger / avancer / revenir,
- d’annoter par boutons ou raccourcis clavier,
- d’enregistrer automatiquement toutes les N annotations,
- de sauvegarder dans le même fichier ou dans un fichier suffixé `_weather.csv`.

Entrées :
---------
- Un fichier CSV contenant une colonne `image_frame` et une colonne `number`.
- Un ou plusieurs dossiers contenant les images extraites (ex : `sync_image/`).

Sorties :
---------
- Le CSV enrichi d’une colonne `weather`.
- Fichier écrit soit *in-place*, soit `<fichier>_weather.csv`.

Clavier :
---------
c → clear  
r → rain  
n → night  
flèche droite / PageDown → suivant  
flèche gauche / PageUp → précédent  
s → sauvegarde partielle  
q / esc → sauvegarde + quitter

Utilisation :
-------------
Mode fichier unique :
    python annotate_weather_gui.py --csv A02.csv --images raw_data/.../sync_image

Mode batch :
    python annotate_weather_gui.py --input-dir extracted_csvfiles --images raw_data/.../sync_image

"""

# ======================================================================
# IMPORTS
# ======================================================================

import os, sys, glob, re, argparse
from pathlib import Path
import pandas as pd
import numpy as np
import cv2
import matplotlib.pyplot as plt
from matplotlib.widgets import Button

# Extensions d’images gérées
IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp")

# ======================================================================
# UTILITAIRES : colonnes & index images
# ======================================================================

def find_col(df, suffix):
    """
    Recherche une colonne : match par suffixe.
    Exemple : '072_image_frame' correspond à suffix 'image_frame'.
    """
    hits = [c for c in df.columns if c.endswith(suffix)]
    if not hits:
        raise KeyError(f"Colonne se terminant par '{suffix}' introuvable.")
    return hits[0]


def scan_images_make_index(image_dirs):
    """
    Parcourt récursivement une liste de dossiers d’images.
    Extrait un ID numérique de frame depuis le nom de fichier.
    Crée un index : frame_id → chemin image.

    Si plusieurs images partagent le même frame_id,
    conserve celle avec le nom le plus court (souvent celle du dataset).
    """
    idx = {}
    for d in image_dirs:
        if not os.path.isdir(d):
            continue

        for p in glob.glob(os.path.join(d, "**", "*"), recursive=True):
            if not p.lower().endswith(IMG_EXTS):
                continue

            name = os.path.basename(p)
            matches = list(re.finditer(r"(\d+)", name))
            if not matches:
                continue

            fid = int(matches[-1].group(1))  # dernière séquence numérique du nom
            if fid not in idx or len(Path(p).name) < len(Path(idx[fid]).name):
                idx[fid] = p

    return idx


def make_output_path(csv_path, inplace=False):
    """Construit le chemin de sortie : soit écrasement, soit suffixe `_weather.csv`."""
    if inplace:
        return csv_path
    p = Path(csv_path)
    return str(p.with_name(p.stem + "_weather" + p.suffix))


def imread_color(path):
    """Lecture OpenCV + conversion BGR → RGB pour Matplotlib."""
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return None
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

# ======================================================================
# CLASSE PRINCIPALE D’ANNOTATION
# ======================================================================

class Annotator:
    """
    Gestion complète de l’annotation image → météo.
    Gère :
    - le CSV
    - l’état de navigation
    - affichage image
    - annotation
    - sauvegardes périodiques
    - raccourcis clavier
    """
    def __init__(self, csv_path, image_index, inplace=False, autosave_every=10):
        self.csv_path = csv_path
        self.image_index = image_index
        self.inplace = inplace
        self.autosave_every = max(0, int(autosave_every))

        # Chargement CSV
        self.df = pd.read_csv(csv_path)
        self.image_frame_col = find_col(self.df, "image_frame")   # ex: 072_image_frame
        self.number_col      = find_col(self.df, "number")        # ex: 000_number

        # Ajouter colonne weather si absente
        if "weather" not in self.df.columns:
            self.df["weather"] = np.nan

        # Ordre initial : index du dataframe
        self.indices = list(self.df.index)
        self.i = 0  # pointeur courant

        # Continuer au 1er NaN si déjà partiellement annoté
        nan_positions = np.where(self.df["weather"].isna())[0]
        if len(nan_positions) > 0:
            self.i = int(nan_positions[0])

        # ----------------------------------------------------------------------
        # Interface Matplotlib : image + boutons
        # ----------------------------------------------------------------------
        self.fig, self.ax = plt.subplots(figsize=(10, 6))
        plt.subplots_adjust(bottom=0.22)
        self.img_artist = None
        self.title_txt = self.ax.set_title("")
        self.ax.axis("off")

        # Boutons météo
        ax_clear = plt.axes([0.10, 0.05, 0.10, 0.075])
        ax_rain  = plt.axes([0.21, 0.05, 0.10, 0.075])
        ax_night = plt.axes([0.32, 0.05, 0.10, 0.075])

        # Navigation
        ax_prev  = plt.axes([0.48, 0.05, 0.10, 0.075])
        ax_next  = plt.axes([0.59, 0.05, 0.10, 0.075])
        ax_skip  = plt.axes([0.70, 0.05, 0.10, 0.075])
        ax_save  = plt.axes([0.81, 0.05, 0.12, 0.075])

        # Actions boutons
        self.btn_clear = Button(ax_clear, "Clear")
        self.btn_rain  = Button(ax_rain,  "Rain")
        self.btn_night = Button(ax_night, "Night")
        self.btn_prev  = Button(ax_prev,  "Prev")
        self.btn_next  = Button(ax_next,  "Next")
        self.btn_skip  = Button(ax_skip,  "Skip")
        self.btn_save  = Button(ax_save,  "Save & Quit")

        self.btn_clear.on_clicked(lambda e: self.set_weather_and_next("clear"))
        self.btn_rain.on_clicked(lambda e: self.set_weather_and_next("rain"))
        self.btn_night.on_clicked(lambda e: self.set_weather_and_next("night"))
        self.btn_prev.on_clicked(lambda e: self.move(-1))
        self.btn_next.on_clicked(lambda e: self.move(+1))
        self.btn_skip.on_clicked(lambda e: self.skip())
        self.btn_save.on_clicked(lambda e: self.save_and_quit())

        # Raccourcis clavier
        self.cid_key = self.fig.canvas.mpl_connect('key_press_event', self.on_key)

        # Première image
        self.refresh()

    # ----------------------------------------------------------------------
    # Gestion de l'affichage
    # ----------------------------------------------------------------------
    def current_row_info(self):
        """Retourne : (row_idx, row, frame_id, image_path)."""
        idx = self.indices[self.i]
        row = self.df.loc[idx]

        try:
            fid = int(row[self.image_frame_col])
        except Exception:
            fid = None

        img_path = self.image_index.get(fid, None) if fid is not None else None
        return idx, row, fid, img_path

    def draw_image(self, img):
        """Affiche une image dans l’axe."""
        if self.img_artist is None:
            self.img_artist = self.ax.imshow(img)
        else:
            self.img_artist.set_data(img)
        self.ax.axis("off")

    def refresh(self):
        """Met à jour l’affichage pour la ligne courante."""
        idx, row, fid, img_path = self.current_row_info()

        title = (
            f"{os.path.basename(self.csv_path)} | row {idx} | frame={fid} "
            f"| number={row[self.number_col]} | weather={row['weather']}"
        )
        self.title_txt.set_text(title)

        if img_path and os.path.exists(img_path):
            img = imread_color(img_path)
            if img is not None:
                self.draw_image(img)
            else:
                self.draw_placeholder(f"Image illisible:\n{img_path}")
        else:
            self.draw_placeholder("Image introuvable\n(frame non mappé)")

        self.fig.canvas.draw_idle()

    def draw_placeholder(self, msg):
        """Affiche un message à la place d’une image manquante."""
        self.ax.clear()
        self.ax.axis("off")
        self.ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=14)

    # ----------------------------------------------------------------------
    # Annotation
    # ----------------------------------------------------------------------
    def set_weather_and_next(self, label):
        idx, _, _, _ = self.current_row_info()
        self.df.at[idx, "weather"] = label

        if self.autosave_every and (self.i % self.autosave_every == 0):
            self.save(progress_only=True)

        self.move(+1)

    # ----------------------------------------------------------------------
    # Navigation
    # ----------------------------------------------------------------------
    def move(self, delta):
        """Déplacement dans le CSV."""
        self.i = max(0, min(len(self.indices) - 1, self.i + delta))
        self.refresh()

    def skip(self):
        """Passe à la ligne suivante sans annotation."""
        self.move(+1)

    # ----------------------------------------------------------------------
    # Clavier
    # ----------------------------------------------------------------------
    def on_key(self, event):
        """Gestion des raccourcis clavier."""
        key = (event.key or "").lower()

        if key == 'c':
            self.set_weather_and_next("clear")
        elif key == 'r':
            self.set_weather_and_next("rain")
        elif key == 'n':
            self.set_weather_and_next("night")
        elif key in ['right', 'pagedown']:
            self.move(+1)
        elif key in ['left', 'pageup']:
            self.move(-1)
        elif key == 's':
            self.save(progress_only=True)
        elif key in ['q', 'escape']:
            self.save_and_quit()

    # ----------------------------------------------------------------------
    # Sauvegarde
    # ----------------------------------------------------------------------
    def save(self, progress_only=False):
        """Sauvegarde du DataFrame complet."""
        out_path = make_output_path(self.csv_path, inplace=self.inplace)
        self.df.to_csv(out_path, index=False, encoding="utf-8")
        if not progress_only:
            print(f"[SAVE] {out_path}")

    def save_and_quit(self):
        """Sauvegarde finale + fermeture GUI."""
        self.save(progress_only=False)
        plt.close(self.fig)

# ======================================================================
# Fonctions utilitaires (mode fichier / batch)
# ======================================================================

def run_single(csv_path, image_dirs, inplace=False, autosave_every=10, image_index_cache=None):
    """Exécute l’outil sur un seul CSV."""
    if image_index_cache is None:
        print("[INFO] Scan des images…")
        image_index = scan_images_make_index(image_dirs)
        print(f"[INFO] Frames indexées : {len(image_index)}")
    else:
        image_index = image_index_cache

    annot = Annotator(csv_path, image_index, inplace=inplace, autosave_every=autosave_every)
    plt.show()

    annot.save(progress_only=False)
    return image_index


def run_batch(input_dir, image_dirs, inplace=False, autosave_every=10, pattern="*.csv"):
    """
    Mode batch : annote tous les CSV d’un dossier.
    """
    files = sorted([
        p for p in glob.glob(os.path.join(input_dir, pattern))
        if "explain" not in os.path.basename(p).lower()
    ])

    if not files:
        print(f"[INFO] Aucun CSV trouvé dans {input_dir}")
        return

    print(f"[INFO] CSV à annoter : {len(files)}")
    print("[INFO] Scan des images (unique)…")
    image_index = scan_images_make_index(image_dirs)
    print(f"[INFO] Frames indexées : {len(image_index)}")

    for i, f in enumerate(files, 1):
        print(f"\n[FILE {i}/{len(files)}] {f}")
        annot = Annotator(f, image_index, inplace=inplace, autosave_every=autosave_every)
        plt.show()
        annot.save(progress_only=False)

# ======================================================================
# MAIN
# ======================================================================

def main():
    ap = argparse.ArgumentParser(description="Annotateur manuel de météo (clear/rain/night) basé sur images.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--csv", help="Chemin d’un CSV unique.")
    g.add_argument("--input-dir", help="Traiter tous les CSV d’un dossier.")

    ap.add_argument("--images", nargs="+", required=True,
                    help="Dossiers contenant les images associées aux frames.")
    ap.add_argument("--inplace", action="store_true",
                    help="Écrase le CSV source au lieu de créer *_weather.csv")
    ap.add_argument("--autosave-every", type=int, default=10,
                    help="Sauvegarde automatique toutes les N annotations (0 = off)")
    ap.add_argument("--pattern", default="*.csv",
                    help="Pattern pour --input-dir (défaut : *.csv)")

    args = ap.parse_args()

    if args.csv:
        run_single(
            csv_path=args.csv,
            image_dirs=args.images,
            inplace=args.inplace,
            autosave_every=args.autosave_every
        )
    else:
        run_batch(
            input_dir=args.input-dir,
            image_dirs=args.images,
            inplace=args.inplace,
            autosave_every=args.autosave_every,
            pattern=args.pattern
        )

if __name__ == "__main__":
    main()
