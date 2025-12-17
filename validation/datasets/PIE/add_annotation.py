import os
import cv2
from lxml import etree
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from PIL import Image, ImageTk

# ============================================================
# add_annotation.py — PIE vehicle behavior annotation GUI
# ------------------------------------------------------------
# Objectif:
#   Ajouter (ou corriger) un attribut XML nommé "behavior" pour
#   des bounding boxes de véhicules dans les annotations PIE.
#
# Contexte PIE:
#   - Les annotations sont stockées en XML (format type CVAT).
#   - Les véhicules sont des "track" label="vehicle"
#   - Chaque "box" correspond à une frame et contient des attributs
#     (type, id, etc.). Ici, on enrichit avec un attribut "behavior".
#
# Principe:
#   1) Parcourir tous les XML d’annotations.
#   2) Collecter uniquement les boxes de véhicules de type "car"
#      qui n’ont PAS encore d’attribut "behavior".
#   3) Afficher image + bbox dans une GUI Tkinter.
#   4) L’utilisateur clique sur un bouton de comportement
#      -> l’attribut behavior est écrit dans l’XML (en mémoire).
#   5) À la fin / sur demande: sauvegarde des XML modifiés.
# ============================================================

# === CONFIGURATION ===
# Chemin racine des annotations PIE (structuré par "set")
annotations_root = r"E:\crossing-model\main_experiment\model_validation\datasets\PIE\annotations"
# Chemin racine des images PIE (structuré par "set/video")
images_root = r"E:\crossing-model\main_experiment\model_validation\datasets\PIE\images"


# ============================================================
# 1) COLLECTE DES BOXES À ANNOTER
# ------------------------------------------------------------
# On récupère toutes les boxes de véhicules:
#   - track label="vehicle"
#   - box avec attribute type == "car"
#   - box sans attribute "behavior" (pour éviter de re-annoter)
#
# Note:
#   On garde une référence directe vers:
#     - l'objet XML "box" (pour modification in-place)
#     - le "tree" XML (pour sauvegarde)
#     - le chemin image_dir (pour afficher la frame)
# ============================================================
def collect_vehicle_boxes(annotations_root, images_root):
    all_boxes = []

    # Parcourt chaque dossier de set (ex: set01, set02, etc.)
    for set_dir in os.listdir(annotations_root):
        set_path = os.path.join(annotations_root, set_dir)
        if not os.path.isdir(set_path):
            continue

        # Parcourt les XML (souvent suffixés "_annt.xml")
        for xml_file in os.listdir(set_path):
            if not xml_file.endswith(".xml"):
                continue

            xml_path = os.path.join(set_path, xml_file)
            set_name = set_dir

            # Convention: le nom de la vidéo est le nom du fichier sans "_annt.xml"
            video_name = xml_file.replace("_annt.xml", "")

            # Chemin attendu des images correspondantes
            image_dir = os.path.join(images_root, set_name, video_name)

            # Charge le XML
            try:
                tree = etree.parse(xml_path)
            except Exception as e:
                print(f"Erreur en lisant {xml_path}: {e}")
                continue
            root = tree.getroot()

            # Chaque "track" correspond à un objet suivi dans le temps
            for track in root.findall("track"):
                if track.attrib.get("label") != "vehicle":
                    continue

                # Chaque "box" = bbox à une frame donnée
                for box in track.findall("box"):
                    vehicle_type = None
                    vehicle_id = None

                    # Récupère les attributs "type" et "id"
                    for attr in box.findall("attribute"):
                        if attr.attrib["name"] == "type":
                            vehicle_type = attr.text
                        if attr.attrib["name"] == "id":
                            vehicle_id = attr.text

                    # Skip si déjà annoté (évite doublons / correction accidentelle)
                    if any(attr.attrib.get("name") == "behavior" for attr in box.findall("attribute")):
                        continue

                    # On ne garde que les voitures (pas bus/truck/etc.)
                    if vehicle_type == "car":
                        all_boxes.append({
                            "box": box,                 # objet XML modifiable
                            "vehicle_id": vehicle_id,   # id textuel (utile affichage)
                            "frame": int(box.attrib["frame"]),
                            "image_dir": image_dir,     # dossier des frames png
                            "xml_path": xml_path,       # pour savoir quel fichier sauver
                            "tree": tree                # arbre XML complet
                        })

    return all_boxes


# ============================================================
# 2) GUI TKINTER — ANNOTATION INTERACTIVE
# ------------------------------------------------------------
# UI:
#   - un canvas image (1280x720)
#   - un texte d’état (id véhicule, frame, progression)
#   - une barre de progression
#   - des boutons "behavior" (parked, ahead, oncoming, etc.)
#   - un bouton "Sauvegarder et quitter"
#
# Comportement:
#   - load_next(): charge la prochaine box, affiche image + bbox
#   - annotate(): écrit/écrase l'attribut "behavior" sur la box courante
#   - save_all(): écrit sur disque uniquement les XML modifiés
# ============================================================
class AnnotatorApp:
    def __init__(self, master, boxes):
        self.master = master
        self.boxes = boxes
        self.index = 0  # index de la box courante dans self.boxes

        # Pour éviter d’écrire tous les XML: on garde seulement ceux modifiés
        self.modified_xml_paths = set()

        # Zone image
        self.canvas = tk.Canvas(master, width=1280, height=720)
        self.canvas.pack()

        # Label "infos" (id véhicule, frame)
        self.label = tk.Label(master, text="", font=("Helvetica", 16))
        self.label.pack()

        # Label status (progression, chemin image, etc.)
        self.status = tk.Label(master, text="", font=("Helvetica", 14), fg="blue")
        self.status.pack()

        # Progressbar (nombre total de boxes à annoter)
        self.progress = ttk.Progressbar(master, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(pady=5)
        self.progress["maximum"] = len(self.boxes)

        # Boutons comportements
        self.buttons_frame = tk.Frame(master)
        self.buttons_frame.pack()

        # Liste des comportements possibles (à adapter selon ton protocole PIE)
        self.behaviors = ["parked", "ahead", "oncoming", "in the next lane", "other"]
        for b in self.behaviors:
            btn = tk.Button(self.buttons_frame, text=b, command=lambda b=b: self.annotate(b))
            btn.pack(side=tk.LEFT, padx=10, pady=10)

        # Bouton de sortie contrôlée
        self.quit_button = tk.Button(master, text="Sauvegarder et quitter", command=self.quit_app)
        self.quit_button.pack(pady=10)

        # Intercepte la fermeture fenêtre (croix) pour éviter pertes
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Charge la première box
        self.load_next()

    def load_next(self):
        """
        Charge la prochaine bbox à annoter:
          - récupère l'image frame correspondante
          - dessine rectangle + id du véhicule
          - affiche dans le canvas (redimensionné 1280x720)
        """
        if self.index >= len(self.boxes):
            messagebox.showinfo("Fini", "Toutes les boîtes ont été annotées.")
            self.save_all()
            self.master.quit()
            return

        entry = self.boxes[self.index]
        box = entry["box"]
        frame_number = entry["frame"]
        vehicle_id = entry["vehicle_id"]

        # Convention: images nommées 00000.png, 00001.png, etc.
        img_path = os.path.join(entry["image_dir"], f"{frame_number:05d}.png")
        if not os.path.exists(img_path):
            # Si une image manque, on skip la box
            print(f"Image introuvable: {img_path}")
            self.index += 1
            self.load_next()
            return

        img = cv2.imread(img_path)

        # Coordonnées bbox (stockées en float dans le XML)
        xtl = int(float(box.attrib["xtl"]))
        ytl = int(float(box.attrib["ytl"]))
        xbr = int(float(box.attrib["xbr"]))
        ybr = int(float(box.attrib["ybr"]))

        # Dessin bbox + id
        cv2.rectangle(img, (xtl, ytl), (xbr, ybr), (0, 255, 0), 2)
        cv2.putText(img, vehicle_id, (xtl, ytl - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # Conversion OpenCV(BGR) -> PIL(RGB) -> Tkinter
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb)
        img_pil = img_pil.resize((1280, 720), Image.Resampling.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(img_pil)

        # Affiche dans canvas
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)

        # Infos UI
        self.label.config(text=f"Vehicle ID: {vehicle_id} | Frame: {frame_number}")

        # ⚠️ Ici tu écrases deux fois status: la 2e ligne remplace la 1re.
        # Si tu veux afficher les deux infos, concatène dans une seule string.
        self.status.config(text=f"Boîte {self.index + 1} sur {len(self.boxes)}")
        self.status.config(text=f"Path : {img_path}")

        self.progress["value"] = self.index

    def annotate(self, behavior):
        """
        Ajoute (ou remplace) l'attribut XML <attribute name="behavior">...</attribute>
        sur la box courante.

        Sécurité:
          - on re-vérifie que type == "car"
          - on supprime d'abord un éventuel behavior existant (évite doublon)
        """
        entry = self.boxes[self.index]
        box = entry["box"]

        # Vérification type car (double check)
        is_vehicle = False
        for attr in box.findall("attribute"):
            if attr.attrib["name"] == "type" and attr.text == "car":
                is_vehicle = True
        if not is_vehicle:
            print(f"[WARN] La box à l’index {self.index} n’est pas un véhicule de type 'car'")
            self.index += 1
            self.load_next()
            return

        # Supprimer un ancien attribut behavior si présent (normalement non, vu le filtrage)
        for attr in box.findall("attribute"):
            if attr.attrib["name"] == "behavior":
                box.remove(attr)

        # Ajouter le nouvel attribut behavior
        new_attr = etree.Element("attribute", name="behavior")
        new_attr.text = behavior
        box.append(new_attr)

        # Marque le XML comme modifié pour sauvegarde sélective
        self.modified_xml_paths.add(entry["xml_path"])

        # Passe à la box suivante
        self.index += 1
        self.load_next()

    def save_all(self):
        """
        Sauvegarde sur disque uniquement les XML modifiés.
        Affiche une petite fenêtre "Sauvegarde en cours..." pour feedback utilisateur.
        """
        if not self.modified_xml_paths:
            print("Aucune modification à sauvegarder.")
            return

        save_window = tk.Toplevel(self.master)
        save_window.title("Sauvegarde")
        save_window.geometry("300x80")
        save_window.transient(self.master)
        save_window.grab_set()

        label = tk.Label(save_window, text="Sauvegarde en cours...", font=("Helvetica", 14))
        label.pack(expand=True, pady=20)
        self.master.update()

        # Écrit chaque fichier XML modifié
        for path in self.modified_xml_paths:
            # On récupère l'objet tree associé à ce xml_path (référence partagée)
            tree = next(e["tree"] for e in self.boxes if e["xml_path"] == path)
            tree.write(path, pretty_print=True, xml_declaration=True, encoding="utf-8")

        label.config(text="Sauvegarde terminée ✔")
        self.master.update()
        save_window.after(1000, save_window.destroy)

    def on_closing(self):
        """
        Gestion de la fermeture via la croix fenêtre.
        Par défaut, on avertit que les annotations non sauvées seront perdues.
        """
        if messagebox.askokcancel("Quitter", "Voulez-vous quitter ? Les annotations en cours ne seront pas sauvegardées."):
            self.master.destroy()

    def quit_app(self):
        """Sortie propre: sauvegarde puis fermeture."""
        self.save_all()
        self.master.destroy()


# ============================================================
# 3) MAIN
# ------------------------------------------------------------
# - Collecte toutes les boxes à annoter
# - Lance l'UI
# ============================================================
if __name__ == "__main__":
    all_boxes = collect_vehicle_boxes(annotations_root, images_root)
    root_tk = tk.Tk()
    root_tk.title("Annotation des comportements véhicules - PIE")
    app = AnnotatorApp(root_tk, all_boxes)
    root_tk.mainloop()
