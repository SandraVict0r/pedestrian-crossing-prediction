import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
import contextlib
import traceback
import subprocess
import threading
import winsound
import queue
import shutil
import time
import os
import sys
import io

# ============================================================
# run_batches_opt.py (PIE) — Lancer un traitement PIE en batchs
# ------------------------------------------------------------
# Objectif:
#   - Piloter l'exécution d'un script "process_dataset_*" sur PIE
#     en découpant les données en batchs (sets / groupes de vidéos),
#     avec:
#       * une GUI (Tkinter) pour sélectionner les batchs à lancer
#       * de la parallélisation (ProcessPoolExecutor)
#       * un montage local TEMP des images (junction NTFS ou copie)
#       * un log par batch (_batch_logs/batch_X.log)
#
# Pourquoi un dossier TEMP local ?
#   - Pour accélérer l'I/O si tes données sont sur un disque plus lent
#     (ex: HDD externe), en montant/copiantsur un SSD local.
#
# Pourquoi des junctions ?
#   - Junction = "lien de dossier" côté Windows, très rapide à créer,
#     pas de duplication réelle des images (quasi instantané).
#   - Si junction impossible -> fallback copie (plus lent + gros volume).
#
# Entrée / sortie:
#   - Entrée: images_path + annotations_path + annotations_vehicle_path + camera_params
#   - Sortie: output_base (résultats du modèle + logs)
# ============================================================


# =========================
# ======  CONFIGS   =======
# =========================

# Racine PIE
base_path = Path(r"E:/crossing-model/main_experiment/model_validation/datasets/PIE")

# Dossiers PIE attendus
images_path = base_path / "images"
annotations_path = base_path / "annotations"            # <-- on ne copie pas (reste sur disque source)
annotations_vehicle_path = base_path / "annotations_vehicle"
camera_params_path = base_path / "camera_params" / "calibration_data.json"

# Sortie globale des résultats du modèle
output_base = base_path / "model_result_no_adj_PIE_20km_rule"

# Dossier TEMP local conseillé (SSD)
local_tmp_base = Path(r"C:/temp_pie_processing")

# Monter les images via junction (rapide). Si échec -> copie.
USE_JUNCTIONS_FOR_IMAGES = True

# Parallélisme:
# - traitement I/O heavy => inutile de monter à 16 workers
# - heuristique: max 4 ou CPU/2
CPU_COUNT = os.cpu_count() or 4
MAX_WORKERS = max(1, min(4, CPU_COUNT // 2))

# ============================================================
# Définition des "batches"
# ------------------------------------------------------------
# Chaque batch est une liste de chemins images:
#   - soit un set complet (images/set01)
#   - soit une vidéo (images/set03/video_0001)
# L'idée: isoler des groupes de vidéos pour mieux répartir la charge.
# ============================================================
batches = [
    [images_path / "set01"],
    [images_path / "set02"],
    [images_path / "set05"],
    [images_path / "set03" / f"video_{i:04d}" for i in range(1, 5)],
    [images_path / "set03" / f"video_{i:04d}" for i in range(5, 10)],
    [images_path / "set03" / f"video_{i:04d}" for i in range(10, 15)],
    [images_path / "set03" / f"video_{i:04d}" for i in range(15, 20)],
    [images_path / "set04" / f"video_{i:04d}" for i in range(1, 5)],
    [images_path / "set04" / f"video_{i:04d}" for i in range(5, 10)],
    [images_path / "set04" / f"video_{i:04d}" for i in range(10, 15)],
    [images_path / "set04" / f"video_{i:04d}" for i in range(15, 17)],
    [images_path / "set06" / f"video_{i:04d}" for i in range(1, 5)],
    [images_path / "set06" / f"video_{i:04d}" for i in range(5, 10)]
]


# =========================
# ======  HELPERS   =======
# =========================

def beep_ok():
    """Petit bip de succès (Windows)."""
    try:
        winsound.Beep(1200, 200)
    except Exception:
        pass

def beep_err():
    """Bip plus grave pour erreur."""
    try:
        winsound.Beep(400, 500)
    except Exception:
        pass

def clean_folder(path: Path, retries=6, delay=0.5):
    """
    Supprime un dossier avec plusieurs tentatives.
    Utile sur Windows quand des handles fichiers restent ouverts un peu.
    """
    for _ in range(retries):
        try:
            if path.exists():
                shutil.rmtree(path)
            return
        except Exception:
            time.sleep(delay)
    # dernier essai en mode tolérant
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)

def make_parent(p: Path):
    """Crée les parents du chemin p (sans créer p)."""
    p.parent.mkdir(parents=True, exist_ok=True)

def make_junction(src: Path, dst: Path) -> bool:
    """
    Crée une junction NTFS (dossier -> dossier):
      mklink /J "dst" "src"
    Retourne True si succès.

    ⚠️ Remarques:
      - nécessite souvent d'être en contexte permettant mklink
        (parfois admin selon policy Windows).
      - si dst existe, on le supprime.
    """
    try:
        if dst.exists():
            shutil.rmtree(dst)
        make_parent(dst)
        subprocess.check_call(
            ['cmd', '/c', 'mklink', '/J', str(dst), str(src)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception:
        return False

def link_or_copy_dir(src: Path, dst: Path, prefer_junction=True):
    """
    Monte src -> dst:
      - si prefer_junction: tente junction
      - sinon (ou si échec): copie le dossier
    Retourne "junction" ou "copy" (pour logging).
    """
    if dst.exists():
        shutil.rmtree(dst)

    if prefer_junction and make_junction(src, dst):
        return "junction"

    # fallback: copie réelle (lent + volumineux)
    shutil.copytree(src, dst)
    return "copy"


# =========================
# ==  WORKER (PROCESS)  ===
# =========================

def process_single_batch(batch_index: int):
    """
    Fonction exécutée dans un PROCESS séparé (ProcessPoolExecutor).

    Étapes:
      1) Créer un dossier TEMP local: C:/temp_pie_processing/batch_X/
      2) Monter les images du batch dans batch_X/images/
         - via junction (rapide) ou copie (fallback)
      3) Lancer process_dataset(...) en lui passant:
         - images_path = images_tmp_dir (TEMP)
         - annotations_path = annotations_path (chemin réel)
         - annotations_vehicle_path = ... (chemin réel)
         - camera_params_path = ... (chemin réel)
         - output_path = output_base
         + flags de règles / options
      4) Capturer stdout/stderr dans un fichier log batch_X.log
      5) Nettoyer le TEMP
      6) Retourner un tuple (batch_index, durée, status, log_path)

    Pourquoi import "process_dataset" dans la fonction ?
      - Sous Windows, multiprocessing spawn relance un nouvel interpréteur.
      - Les imports doivent être "safe" et faits dans le worker.
    """
    from pathlib import Path
    import time
    import sys
    import contextlib

    start_time = time.time()

    # Le script appelé (pipeline principal)
    # ⚠️ Il faut que ce module soit importable (dans le même dossier ou PYTHONPATH).
    from process_dataset_scenario_v3 import process_dataset

    # Dossier TEMP local propre à ce batch
    batch_tmp_dir = local_tmp_base / f"batch_{batch_index+1}"
    images_tmp_dir = batch_tmp_dir / "images"

    # Nettoyage avant de commencer
    clean_folder(batch_tmp_dir)
    images_tmp_dir.mkdir(parents=True, exist_ok=True)

    # Dossier logs dans output_base
    out_logs_dir = output_base / "_batch_logs"
    out_logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_logs_dir / f"batch_{batch_index+1}.log"

    # Redirection stdout/stderr vers le log
    with open(log_path, "w", encoding="utf-8") as log_file, \
         contextlib.redirect_stdout(log_file), \
         contextlib.redirect_stderr(log_file):

        print(f"[batch {batch_index+1}] START at {datetime.now().isoformat(timespec='seconds')}")
        print(f"Using tmp dir: {batch_tmp_dir}")
        link_modes = []

        try:
            # ------------------------------------------------------------
            # Monter uniquement les IMAGES du batch dans TEMP
            # ------------------------------------------------------------
            for video_folder in batches[batch_index]:
                if not video_folder.exists():
                    print(f"WARNING: {video_folder} n'existe pas, skip.")
                    continue

                # Cas 1: on a un set complet (images/set01)
                if video_folder.name.startswith("set"):
                    dst = images_tmp_dir / video_folder.name
                    mode = link_or_copy_dir(video_folder, dst, prefer_junction=USE_JUNCTIONS_FOR_IMAGES)
                    link_modes.append((video_folder, mode))

                # Cas 2: on a une vidéo (images/set03/video_0001)
                else:
                    dst = images_tmp_dir / video_folder.parent.name / video_folder.name
                    make_parent(dst)
                    mode = link_or_copy_dir(video_folder, dst, prefer_junction=USE_JUNCTIONS_FOR_IMAGES)
                    link_modes.append((video_folder, mode))

            print("Mounting modes:", ", ".join(f"{p.name}:{m}" for p, m in link_modes) or "none")

            # ------------------------------------------------------------
            # Appel du pipeline principal
            # - images_path: TEMP
            # - annotations/camera: chemins réels (pas de copie)
            # ------------------------------------------------------------
            process_dataset(
                images_path=images_tmp_dir,
                annotations_path=annotations_path,
                annotations_vehicle_path=annotations_vehicle_path,
                camera_params_path=camera_params_path,
                output_path=output_base,

                # Options du pipeline
                adj=False,
                intention=False,
                save_video=False,

                # Règles contextuelles (désactivées ici)
                use_green_light_rule=False,
                use_red_light_rule=False,
                use_crosswalk_rule=False,
                use_other_vehicle_model=False,
            )

            status = "OK"

        except Exception as e:
            # En cas d'erreur, on log la stacktrace complète
            status = f"ERROR: {repr(e)}"
            print("\n=== STACK TRACE ===")
            traceback.print_exc()

        finally:
            # Nettoyage TEMP (même si erreur)
            try:
                clean_folder(batch_tmp_dir)
            except Exception:
                print("WARNING: cleanup failed for", batch_tmp_dir)

            dur = round(time.time() - start_time, 2)
            print(f"[batch {batch_index+1}] END status={status} duration={dur}s")

    return (batch_index, dur, status, str(log_path))


# =========================
# =========  GUI  =========
# =========================

class BatchApp(tk.Tk):
    """
    Interface GUI:
      - liste de checkboxes (un par batch)
      - bouton start (lance en thread un ProcessPoolExecutor)
      - barre de progression
      - console logs (ScrolledText)
      - bouton "ouvrir dossier logs"
    """
    def __init__(self):
        super().__init__()
        self.title("Traitement batch PIE (optimisé)")
        self.geometry("820x560")

        self.selected_batches = []
        self.completed = 0

        # Queue thread-safe: permet aux workers (thread) de pousser des updates UI
        self.q = queue.Queue()

        # ----------------------------
        # Checkboxes de sélection batchs
        # ----------------------------
        self.vars = []
        frm = tk.Frame(self)
        frm.pack(fill='x', padx=10, pady=10)

        tk.Label(frm, text="Sélection des batches:", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        for i, batch in enumerate(batches):
            names = []
            for p in batch:
                # affichage lisible: "set01" ou "set03/video_0001"
                if p.name.startswith("set"):
                    names.append(p.name)
                else:
                    names.append(f"{p.parent.name}/{p.name}")

            text = f"Batch {i+1}: {', '.join(names)}"
            var = tk.IntVar()
            cb = tk.Checkbutton(frm, text=text, variable=var)
            cb.pack(anchor='w')
            self.vars.append(var)

        # ----------------------------
        # Boutons actions
        # ----------------------------
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)

        self.start_btn = tk.Button(btn_frame, text="Lancer le traitement", command=self.start_processing, width=22)
        self.start_btn.pack(side='left', padx=6)

        self.open_logs_btn = tk.Button(btn_frame, text="Ouvrir dossier logs", command=self.open_logs, width=20)
        self.open_logs_btn.pack(side='left', padx=6)

        self.quit_btn = tk.Button(btn_frame, text="Quitter", command=self.quit, width=12)
        self.quit_btn.pack(side='left', padx=6)

        # ----------------------------
        # Progress bar
        # ----------------------------
        self.progress = ttk.Progressbar(self, length=700, mode='determinate')
        self.progress.pack(pady=10)

        # ----------------------------
        # Zone logs (console)
        # ----------------------------
        self.log_area = scrolledtext.ScrolledText(self, height=16, state='disabled', font=("Consolas", 9))
        self.log_area.pack(fill='both', expand=True, padx=10, pady=10)

        # Scheduler: lit régulièrement la queue (pour mettre à jour UI)
        self.after(120, self._drain_queue)

    # ---- UI helpers (main thread only) ----
    def _log_main(self, message: str):
        """Ajoute une ligne dans la console UI (thread principal uniquement)."""
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {message}\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')

    def _drain_queue(self):
        """
        Lit tous les messages disponibles dans self.q et met à jour l'UI.
        Types:
          - ("log", str)
          - ("progress", int)
          - ("done", None)
        """
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._log_main(payload)
                elif kind == "progress":
                    self.progress['value'] = payload
                elif kind == "done":
                    self.start_btn.config(state='normal')
                    beep_ok()
        except queue.Empty:
            pass
        self.after(120, self._drain_queue)

    def log(self, message):
        """Alias safe: log depuis main thread."""
        self._log_main(message)

    # ---- Actions ----
    def open_logs(self):
        """Ouvre le dossier des logs batch dans l'explorateur Windows."""
        logs_dir = output_base / "_batch_logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(logs_dir))

    def start_processing(self):
        """
        Démarre le traitement:
          - récupère les batchs cochés
          - prépare progressbar
          - lance un thread (daemon) qui gère le ProcessPoolExecutor
        """
        self.selected_batches = [i for i, var in enumerate(self.vars) if var.get() == 1]
        if not self.selected_batches:
            messagebox.showwarning("Attention", "Veuillez sélectionner au moins un batch.")
            return

        self.start_btn.config(state='disabled')
        self.progress['maximum'] = len(self.selected_batches)
        self.progress['value'] = 0
        self.completed = 0

        self.log(
            f"Début traitement de {len(self.selected_batches)} batch(s) | "
            f"workers={MAX_WORKERS} | junctions_images={USE_JUNCTIONS_FOR_IMAGES}"
        )

        # On lance un thread pour ne pas bloquer l'UI
        threading.Thread(target=self.run_batches, daemon=True).start()

    def run_batches(self):
        """
        Exécuté dans un thread:
          - démarre un pool de processus
          - soumet un job par batch sélectionné
          - récupère les résultats au fur et à mesure (as_completed)
          - push des updates dans la queue UI
        """
        try:
            with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(process_single_batch, i): i for i in self.selected_batches}

                for future in as_completed(futures):
                    try:
                        batch_index, duration, status, log_path = future.result()
                        self.completed += 1

                        msg = f"Batch {batch_index+1} terminé en {duration:.2f}s | {status} | log: {log_path}"
                        self.q.put(("log", msg))
                        self.q.put(("progress", self.completed))
                        self.q.put(("log", ""))

                        # bip selon succès/échec
                        if status.startswith("OK"):
                            beep_ok()
                        else:
                            beep_err()

                    except Exception as e:
                        self.completed += 1
                        self.q.put(("log", f"Batch FAILED (exception): {repr(e)}"))
                        self.q.put(("progress", self.completed))
                        beep_err()

        finally:
            self.q.put(("log", "Tous les batchs sont terminés."))
            self.q.put(("done", None))


# =========================
# ========= MAIN ==========
# =========================

if __name__ == "__main__":
    """
    Point d'entrée.

    ⚠️ Windows + multiprocessing:
      - Il faut que ce fichier soit exécuté comme script principal
        (pas importé) sinon spawn peut relancer l'UI.
      - Il faut que 'process_dataset_scenario_v3.py' soit importable
        depuis le répertoire courant ou via PYTHONPATH.

    Option si besoin:
      sys.path.append("...") pour ajouter dynamiquement ton repo.
    """
    app = BatchApp()
    app.mainloop()
