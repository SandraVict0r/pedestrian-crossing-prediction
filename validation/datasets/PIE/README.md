## README PIE — structure & objectifs

*(Ce dépôt ne contient pas les données brutes du dataset PIE.)*

Le **PIE dataset** (*Pedestrian Intention Estimation*) contient des scènes réelles annotées (piétons, véhicules, intentions/attributs, etc.). Ici, PIE sert à tester la **généralisation du modèle entraîné en VR**, avec plusieurs variantes : biais sécurité (SCBA), règles contextuelles (feux/crosswalk/other vehicle), mode intention, etc.

---

## 1) Contenu réel du dossier

```
PIE/
 ├── model_result_*                   # sorties CSV (plusieurs variantes)
 │   ├── model_result_adj_*           # avec SCBA (adj=True)
 │   └── model_result_no_adj_*        # sans SCBA (adj=False)
 │
 ├── add_annotation.py                # GUI Tkinter pour annoter "behavior" des véhicules (PIE XML)
 ├── crossing_decision.py             # ancienne version: export/vidéo par piéton (plus “monolithique”)
 ├── process_dataset.py               # pipeline baseline (ego only + règles simples)
 ├── process_dataset_scenario_v3.py   # pipeline principal (ego + scénarios + règles)
 └── run_batches_opt.py               # GUI batch + parallélisation + logs
```

---

## 2) Ce qui est fourni / non fourni

| Élément                               | Présent ? | Description                                            |
| ------------------------------------- | --------: | ------------------------------------------------------ |
| Scripts d’annotation / évaluation PIE |        ✔️ | export CSV + règles + batch runner                     |
| Résultats finaux (.csv)               |        ✔️ | multiples variantes (adj/no-adj, intention, scénarios) |
| Données brutes PIE (images + XML)     |         ❌ | à télécharger via la source officielle PIE             |
| Assets lourds (frames, vidéos, etc.)  |         ❌ | non redistribuables dans ce repo                       |

---
Oui, il manque clairement la section “récupérer PIE”. Voilà un bloc README prêt à coller, dans le même style que ton README LOKI.

---

### Comment obtenir le dataset PIE

⚠️ **Les données brutes PIE (images + annotations) ne sont pas incluses dans ce dépôt.**
Pour réexécuter les scripts, il faut télécharger PIE depuis la source officielle GitHub :

* Repo PIE : `https://github.com/aras62/PIE`

#### 1) Cloner le dépôt PIE

```bash
git clone https://github.com/aras62/PIE.git
cd PIE
```

#### 2) Télécharger les données PIE

Dans le dépôt PIE, suis les instructions de téléchargement (liens + scripts fournis par les auteurs).
En pratique, tu dois récupérer au minimum :

* **les frames images** (organisées par `setXX/video_YYYY/xxxxx.png`)
* **les annotations XML** (`setXX/video_YYYY_annt.xml`)
* **les fichiers OBD/GPS** (`setXX/video_YYYY_obd.xml`) si tu utilises la vitesse/distance comme dans nos scripts

#### 3) Organiser PIE localement (structure attendue par ce repo)

Nos scripts supposent une structure du type :

```
PIE/
 ├── images/
 │   ├── set01/
 │   │   ├── video_0001/
 │   │   │   ├── 00000.png
 │   │   │   └── ...
 │   │   └── ...
 │   └── set06/...
 │
 ├── annotations/
 │   ├── set01/
 │   │   ├── video_0001_annt.xml
 │   │   └── ...
 │   └── ...
 │
 ├── annotations_vehicle/
 │   ├── set01/
 │   │   ├── video_0001_obd.xml
 │   │   └── ...
 │   └── ...
 │
 └── camera_params/
     └── calibration_data.json
```

💡 Ensuite, adapte les chemins dans nos scripts (ou mets à jour `base_path`) pour pointer vers ton dossier PIE local.

---

Si tu veux, je peux aussi te rédiger une version “ultra claire” avec un mini check-list (“si tu n’as pas `annotations_vehicle`, voilà ce qui casse / ce qui reste utilisable”) pour éviter que quelqu’un clone ton repo et se bloque.

## 3) Comment lire tes dossiers `model_result_*` (la “carte”)

### A. `adj` vs `no_adj`

* `model_result_adj_*` → **SCBA activé** (`adj=True` dans `pedestrian_behavior_model(...)`)
* `model_result_no_adj_*` → **SCBA désactivé** (`adj=False`)

### B. `intention` vs pas intention

* `*_intention_*` → l’évaluation commence **à partir de la première frame où `look="looking"`** (proxy intention/attention)
* sans `intention` → l’évaluation commence au **premier frame disponible** pour le piéton (sur la fenêtre annotée “cross”)

### C. variantes vitesse / règle 20 km/h

* `*_half_velocity*` → vitesse ego **divisée par 2** avant prédiction (stress-test / calibration)
* `*_20km_rule` ou `*_20kmh_rule` → règle : **si vitesse < 20 km/h ⇒ crossing=True**
  (hypothèse: véhicule a ralenti / cède le passage)

### D. scénarios contextuels (dans `process_dataset_scenario_v3.py`)

Ces dossiers correspondent à l’activation de règles supplémentaires via flags :

* `*_green_light_scenario*` : feu piéton vert + piéton sur crosswalk ⇒ crossing=True
* `*_red_light_scenario*` : feu piéton rouge proche ⇒ crossing=False
* `*_crossing_street_scenario*` : logique “crosswalk + feu” (selon tes flags)
* `*_other_vehicle_scenario*` : décision basée sur un **autre véhicule** (`behavior ∈ {ahead, in the next lane}`) plutôt que l’ego
* `*_all_scenario_*` : combine les règles (avec une **priorité stricte**: red light > green/crosswalk > other vehicle > ego)



### E. “batch2”

* `*_batch2` = même pipeline, mais exécuté en plusieurs runs / batches via `run_batches_opt.py` (pratique pour relancer partiellement).

---

## 4) Scripts fournis

### 1) `add_annotation.py` — Annotation manuelle du comportement des véhicules (PIE)

GUI Tkinter qui parcourt les boxes `vehicle` de type `car` dans les XML PIE et ajoute un attribut :

`behavior ∈ {parked, ahead, oncoming, in the next lane, other}`

* Ignore les boxes déjà annotées (`attribute name="behavior"`)
* Affiche l’image + bbox du véhicule + ID
* Sauvegarde les XML modifiés à la fin (“Sauvegarder et quitter”)

Usage :

```bash
python add_annotation.py
```

Sortie : modification **in-place** des XML dans `annotations_root`.

---

### 2) `crossing_decision.py` — Export “ancienne version” (ego only, images d’erreurs)

Script monolithique qui :

* charge `CNRS_behavior_model.py`
* lit piétons (`cross`), bboxes, OBD GPS
* calcule distance via haversine (référence dernière frame)
* estime une taille (mais dans ton extrait tu forces `real_height = 174`)
* produit CSV par piéton + sauvegarde images (et vidéo) uniquement sur frames où GT ≠ prédiction

Usage :

```bash
python crossing_decision.py
```

---

### 3) `process_dataset.py` — Pipeline baseline (simple)

Version pipeline “propre” (traitement set/video → piétons → frames) avec :

* calcul taille (avec undistort)
* modèle sur ego
* option `intention` (start à first looking)
* option `save_video`
* règles simples (dans ta version: `velocity = velocity/2` + `if velocity < 20: crossing=True`)

Usage (appelé directement ou via un runner) :

```python
from process_dataset import process_dataset
process_dataset(..., adj=False, intention=False, save_video=False)
```

---

### 4) `process_dataset_scenario_v3.py` — Pipeline principal (scénarios + règles)

C’est **la version à privilégier** pour les expériences PIE “finales”.

Ajouts clés :

* Support règles contextuelles :

  * feu piéton vert + crosswalk (“crossing street”)
  * feu piéton rouge (“red light”)
  * other vehicle (“ahead / in the next lane”) avec estimation distance au sol
* Colonne `scenario` dans les CSV (quelle règle a gagné)
* Option `save_video=True` : sauvegarde overlays (piéton + crosswalk + feux + véhicules)

---

### 5) `run_batches_opt.py` — Lancer PIE en batchs (GUI + parallélisation)

GUI Tkinter pour sélectionner des batches (sets/groupes de vidéos), puis exécuter en parallèle :

* montage des images en TEMP (junction NTFS ou copie)
* appel `process_dataset_scenario_v3.process_dataset(...)`
* logs batch par batch dans `output_base/_batch_logs/`

Usage :

```bash
python run_batches_opt.py
```

---

## 5) Format des CSV (PIE)

**Baseline (`process_dataset.py`)**

* `frame, true_label, predicted_label, weather, real_height_cm, velocity_kmh, distance_m`

**Scénarios (`process_dataset_scenario_v3.py`)**

* mêmes colonnes + :
* `scenario`
* infos véhicule “other vehicle” si utilisé :

  * `veh_distance_m, veh_velocity_kmh_used, veh_behavior, veh_bbox_*`
