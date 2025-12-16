# app.py
# -*- coding: utf-8 -*-
"""
LOKI Weather Annotator — Streamlit (propre & cliquable)

But :
- Afficher une image (frame) aléatoire d’un scénario LOKI (scenario_000, scenario_001, ...)
- Annoter la météo du scénario via 4 gros boutons : Rain / Clear / Night / Other
- Au clic : sauvegarde immédiate dans un CSV + passage automatique au prochain scénario non annoté
- Permet aussi : reshuffle image, ignorer scénario, annuler le dernier tag

Sortie :
- CSV `_weather_annotations.csv` créé/édité dans le dossier LOKI
  colonnes : (scenario_id, weather)
"""

from pathlib import Path
import re, random
import pandas as pd
from PIL import Image
import streamlit as st

# ================== CONFIG PAR DÉFAUT ==================
# Chemin par défaut vers le dossier contenant les dossiers scenario_***
BASE_DIR_DEFAULT = r"E:\crossing-model\main_experiment\model_validation\datasets\loki_data"

# Nom du fichier de sortie des annotations
OUTPUT_CSV_NAME = "_weather_annotations.csv"

# Liste des labels UI (affichage) et leur valeur normalisée (stockée dans le CSV)
LABELS = [
    ("🌧️ Rain",  "rain"),
    ("☀️ Clear", "clear"),
    ("🌙 Night", "night"),
    ("❓ Other", "other"),
]

# Regex pour identifier les dossiers "scenario_000", "scenario_001", ...
RE_SCEN  = re.compile(r"^scenario_(\d{3})$")

# Regex pour identifier les frames "image_0001.png/jpg/jpeg" (insensible à la casse)
RE_FRAME = re.compile(r"image_(\d{4})\.(png|jpg|jpeg)$", re.IGNORECASE)

# Config Streamlit
st.set_page_config(page_title="LOKI Weather Annotator", layout="wide")

# ================== STYLES ==================
# CSS pour grossir les boutons et rendre l’UI plus lisible (cards, badges, etc.)
st.markdown("""
<style>
/* boutons bien gros */
.stButton>button {
  width: 100%;
  height: 72px;
  font-size: 22px;
  font-weight: 600;
  border-radius: 12px;
}
.bigstat { font-size: 18px; }
.badge {
  display:inline-block;
  padding:4px 10px;
  border-radius: 999px;
  background:#222; color:#fff; font-weight:600; margin-left:6px;
}
.card {
  border: 1px solid #eee; border-radius:12px; padding:14px; background:#fafafa;
}
</style>
""", unsafe_allow_html=True)

# ================== HELPERS ==================
def list_scenarios(base_dir: Path):
    """
    Parcourt base_dir et retourne la liste triée des scenario_id (int),
    en ne gardant que les dossiers dont le nom matche scenario_***.
    """
    sids = []
    for d in base_dir.iterdir():
        if d.is_dir():
            m = RE_SCEN.match(d.name)
            if m:
                sids.append(int(m.group(1)))
    return sorted(sids)

def list_frames(sdir: Path):
    """
    Liste les frames d’un dossier scénario (image_****.png/jpg/jpeg) et retourne les ids triés.
    """
    fids = []
    for p in sdir.iterdir():
        m = RE_FRAME.match(p.name)
        if m:
            fids.append(int(m.group(1)))
    return sorted(fids)

def scenario_dir(base_dir: Path, sid: int) -> Path:
    """Construit le chemin vers un dossier scenario_XXX à partir de son id."""
    return base_dir / f"scenario_{sid:03d}"

def image_path_for_frame(sdir: Path, fid: int) -> Path:
    """
    Retourne le chemin de la frame image_{fid} en testant successivement :
    png -> jpg -> jpeg
    (utile si le dataset mélange les extensions).
    """
    p = sdir / f"image_{fid:04d}.png"
    if p.exists(): return p
    p = sdir / f"image_{fid:04d}.jpg"
    if p.exists(): return p
    p = sdir / f"image_{fid:04d}.jpeg"
    return p  # peut ne pas exister, on gère plus bas

def load_annotations(csv_path: Path) -> dict:
    """
    Charge le CSV d’annotations si présent, et retourne un dict :
    { scenario_id (int) : weather (str) }
    Robuste : si CSV absent/corrompu -> retourne {}.
    """
    if not csv_path.exists():
        return {}
    try:
        df = pd.read_csv(csv_path)
        return {
            int(r["scenario_id"]): str(r["weather"]).strip().lower()
            for _, r in df.iterrows()
            if pd.notna(r["scenario_id"])
        }
    except Exception:
        return {}

def save_annotations(csv_path: Path, mapping: dict):
    """
    Écrit l’état courant des annotations dans le CSV.
    On trie par scenario_id pour garder un fichier stable et lisible.
    """
    items = sorted(mapping.items(), key=lambda x: x[0])
    df = pd.DataFrame(items, columns=["scenario_id", "weather"])
    df.to_csv(csv_path, index=False, encoding="utf-8")

def next_unlabeled(scenarios, ann_map, cur_idx):
    """
    Retourne l’index du prochain scénario non annoté (dans la liste `scenarios`).
    - On cherche en “wrap-around” après cur_idx.
    - Si tout est annoté, on retourne simplement le scénario suivant.
    """
    n = len(scenarios)
    for k in range(1, n + 1):
        idx = (cur_idx + k) % n
        if scenarios[idx] not in ann_map:
            return idx
    return (cur_idx + 1) % n

# ================== SIDEBAR (chemin & options) ==================
# Permet de changer le dossier dataset sans modifier le script.
st.sidebar.header("⚙️ Paramètres")
base_dir_str = st.sidebar.text_input(
    "Dossier LOKI (contient scenario_000, 001, ...)",
    value=BASE_DIR_DEFAULT
)

# Path resolved pour éviter les surprises (relative paths, etc.)
base_dir = Path(base_dir_str).resolve()
csv_path = base_dir / OUTPUT_CSV_NAME

# Layout : grande colonne image + colonne contrôles à droite
col_left, col_right = st.columns([3, 2])

# ================== INITIALISATION ÉTAT ==================
# Streamlit rerun souvent : on stocke l’état dans session_state
if "scenarios" not in st.session_state:
    st.session_state.scenarios = []
if "ann" not in st.session_state:
    st.session_state.ann = {}
if "sidx" not in st.session_state:
    st.session_state.sidx = 0  # index courant dans la liste scenarios
if "rand_frame" not in st.session_state:
    st.session_state.rand_frame = None  # frame aléatoire “stable” jusqu’à reshuffle
if "history" not in st.session_state:
    st.session_state.history = []  # pile (scenario_id, old_value) pour Annuler

# ================== CHARGEMENT DATA ==================
# Lecture dossier + CSV à chaque run (rapide, et garantit sync si fichier modifié)
with st.spinner("Chargement des scénarios..."):
    if base_dir.exists():
        scenarios = list_scenarios(base_dir)
        ann = load_annotations(csv_path)
    else:
        scenarios, ann = [], {}

st.session_state.scenarios = scenarios
st.session_state.ann = ann

# ================== BARRE HAUTE ==================
st.title("LOKI — Weather Annotator (propre)")

# Gestion erreurs tôt
if not base_dir.exists():
    st.error(f"Chemin invalide: {base_dir}")
    st.stop()

if not scenarios:
    st.warning("Aucun dossier `scenario_***` trouvé.")
    st.stop()

# Stats progression : combien annotés sur le total
total = len(scenarios)
done = len(ann)
progress = done / total

# Petite “card” de statut + barre de progression
st.markdown(
    f'<div class="card"><span class="bigstat">Dossier :</span> {base_dir} '
    f'&nbsp;&nbsp; <span class="bigstat">Progression :</span> '
    f'{done}/{total} <span class="badge">{int(progress*100)}%</span></div>',
    unsafe_allow_html=True
)
st.progress(progress)

# ================== SÉLECTION SCÉNARIO COURANT ==================
# Si on est tombé sur un scénario déjà annoté, on saute au prochain non annoté
if scenarios[st.session_state.sidx] in ann and done < total:
    st.session_state.sidx = next_unlabeled(scenarios, ann, st.session_state.sidx)

sid = scenarios[st.session_state.sidx]
sdir = scenario_dir(base_dir, sid)

# Liste des frames disponibles dans ce scénario
frames = list_frames(sdir)
if not frames:
    # Si un scénario n’a aucune image, on passe au suivant
    st.info(f"Pas d'image pour scenario_{sid:03d}. On passe au suivant.")
    st.session_state.sidx = next_unlabeled(scenarios, ann, st.session_state.sidx)
    st.rerun()

# Choix d’une frame aléatoire mais "stable" tant qu’on ne clique pas "Autre image"
if st.session_state.rand_frame is None or st.session_state.rand_frame not in frames:
    st.session_state.rand_frame = random.choice(frames)

fid = st.session_state.rand_frame
img_path = image_path_for_frame(sdir, fid)

# ================== COLONNE IMAGE ==================
with col_left:
    st.subheader(f"scenario_{sid:03d} — image_{fid:04d}")

    # Affichage image si elle existe
    if img_path.exists():
        img = Image.open(img_path)
        st.image(img, use_column_width=True)
    else:
        st.warning(f"Image manquante: {img_path.name}")

    # Boutons utilitaires sous l’image
    c1, c2, c3 = st.columns(3)

    # Reshuffle : changer juste la frame affichée (sans changer de scénario)
    if c1.button("🔀 Autre image", use_container_width=True):
        st.session_state.rand_frame = random.choice(frames)
        st.rerun()

    # Skip : passer au scénario suivant sans écrire d’annotation
    if c2.button("⏭️ Ignorer (sans annoter)", use_container_width=True):
        st.session_state.sidx = (st.session_state.sidx + 1) % len(scenarios)
        st.session_state.rand_frame = None
        st.rerun()

    # Undo : annuler la dernière annotation (pile history)
    if c3.button(
        "↩️ Annuler dernier tag",
        use_container_width=True,
        disabled=(len(st.session_state.history) == 0)
    ):
        if st.session_state.history:
            last_sid, prev = st.session_state.history.pop()
            if prev is None:
                st.session_state.ann.pop(last_sid, None)
            else:
                st.session_state.ann[last_sid] = prev
            save_annotations(csv_path, st.session_state.ann)
        st.rerun()

# ================== COLONNE CONTRÔLES ==================
with col_right:
    st.subheader("Choisis la météo")

    # Affiche valeur courante si déjà annotée
    current = ann.get(sid)
    st.markdown(f"**Actuel :** `{current}`" if current else "*Non annoté*")

    # Boutons météo : au clic -> sauvegarde + next scénario non annoté
    for label, value in LABELS:
        if st.button(label, key=f"btn_{value}"):
            # Historique pour permettre Undo
            st.session_state.history.append((sid, ann.get(sid, None)))

            # Écrit annotation en mémoire + sur disque (CSV)
            st.session_state.ann[sid] = value
            save_annotations(csv_path, st.session_state.ann)

            # Avance au prochain scénario non annoté
            st.session_state.sidx = next_unlabeled(
                scenarios, st.session_state.ann, st.session_state.sidx
            )

            # Reset frame aléatoire pour le prochain scénario
            st.session_state.rand_frame = None
            st.rerun()

    st.divider()

    # Export rapide CSV (utile si tu veux le télécharger sans aller dans le dossier)
    df_dl = pd.DataFrame(
        sorted(st.session_state.ann.items()),
        columns=["scenario_id", "weather"]
    )

    st.download_button(
        "⬇️ Télécharger le CSV",
        data=df_dl.to_csv(index=False).encode("utf-8"),
        file_name=OUTPUT_CSV_NAME,
        mime="text/csv",
        use_container_width=True
    )

# ================== BAS DE PAGE ==================
st.caption(
    "Clic = sauvegarde instantanée + passage automatique au scénario suivant. "
    "Tu peux relancer l'app à tout moment : elle reprend où tu t'es arrêté."
)
