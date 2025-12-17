# **nuScenes Dataset — Scripts d’évaluation & résultats du modèle**

*(Ce dépôt ne contient pas les données brutes du dataset nuScenes)*

Le **nuScenes dataset** (Motional) est un dataset multimodal de conduite autonome (RGB multi-caméras, LiDAR, cartes HD, annotations 3D, CAN bus) utilisé ici pour tester la **généralisation** de notre modèle de prédiction de traversée piétonne (entraîné en VR), **sans fine-tuning**.

---

## 1. Objectif du dossier

Ce dossier rassemble :

* les **scripts de prétraitement / décision** pour exécuter notre modèle sur **nuScenes**,
* des fichiers auxiliaires (ex. liste d’images de nuit),
* et la documentation pour **reproduire l’évaluation** localement.

⚠️ **Les données brutes nuScenes ne sont pas redistribuables ici** : elles doivent être téléchargées depuis les sources officielles.

---

## 2. Contenu réel du dossier

```
nuscenes/
 ├── crossing_decision.py
 ├── crossing_decision_other_vehicule.py
 ├── visualize.py
 │
 ├── nuscenes_camfront_weather_night.csv
 ├── urls.txt
 └── README.md
```

### Ce qui est fourni / non fourni

| Élément                       | Présent ? | Description                                                      |
| ----------------------------- | --------: | ---------------------------------------------------------------- |
| Scripts d’évaluation nuScenes |        ✔️ | Export CSV + règles décisionnelles + visualisation               |
| Liste “night” CAM_FRONT       |        ✔️ | `nuscenes_camfront_weather_night.csv` (mapping images → `night`) |
| `urls.txt`                    |        ✔️ | Liens pratiques (dataset/devkit/ressources)                      |
| Données brutes nuScenes       |         ❌ | À télécharger via nuScenes / S3 (selon votre accès)              |

---

## 3. Comment obtenir nuScenes (obligatoire pour réexécuter les scripts)

### 3.1 Télécharger les données

1. Crée un compte / demande d’accès sur le site nuScenes.
2. Télécharge au minimum :

* **nuScenes meta + samples** (images keyframes)
* **maps** (cartes HD)
* **(optionnel mais recommandé)** **CAN bus expansion** si tu veux la vitesse “propre” via CAN.

Le **devkit** pointe vers la page officielle de téléchargement et mentionne explicitement l’extension CAN bus. ([GitHub][1])
Quand l’accès web est pénible (pages JS), certains miroirs/entrées de téléchargement passent via le registre AWS. ([Registre des données ouvertes sur AWS][2])

### 3.2 Installer le devkit nuScenes

Le code repose sur **nuscenes-devkit** (API `NuScenes`, `NuScenesMap`, `NuScenesCanBus`, etc.). Le dépôt officiel est ici : ([GitHub][1])

Installe ensuite les dépendances Python typiques (à adapter à ton environnement) :

* `nuscenes-devkit`
* `numpy`, `pandas`, `tqdm`
* `shapely` *(pour calculer “on road / drivable”)*
* `opencv-python` *(pour les viewers et overlays)*
* `pyquaternion`

> Remarque : si **Shapely** n’est pas installé, tes scripts **ignorent** les frames car le GT “on road” ne peut pas être évalué (comportement volontaire et “strict”).

---

## 4. Organisation attendue sur disque

Les scripts supposent un `DATAROOT` nuScenes contenant (au minimum) :

```
<dataroot>/
 ├── v1.0-mini/                 # ou v1.0-trainval / v1.0-test selon ton cas
 ├── maps/
 └── can_bus/                   # si CAN bus expansion est installée
```

⚠️ Dans tes scripts, `DATAROOT` est un chemin Windows (`E:\...`). Adapte-le à ta machine.

---

## 5. Scripts fournis

## 5.1 `crossing_decision.py` — Export CSV “ego-only” (adj / no-adj)

### But

Exporter **2 CSV par piéton** (`instance_token`) :

* une version **SCBA activé** (`adj=True`)
* une version **sans SCBA** (`adj=False`)

### Entrées utilisées

* **Vitesse ego (km/h)** : priorité CAN `vehicle_monitor.vehicle_speed`, sinon `zoe_veh_info` (RPM → km/h), sinon fallback **Δpose/Δt**.
* **Distance ego↔piéton (m)** : distance 2D au sol à partir du repère ego (long/lat).
* **Taille piéton (cm)** : via `ann['size'][2]` (m→cm), clamp/fallback **moyenne par location** si hors `[150, 200]`.
* **Weather** : `night` si l’image CAM_FRONT est listée dans `nuscenes_camfront_weather_night.csv`, sinon `clear`.
* **GT crossing (strict)** :

  * `true_label = 1` si le piéton est **sur la route** *ET* **devant l’ego** (`d_long > 0`)
  * si `on_road` est inconnu → frame ignorée (filtrage strict)

### Sorties

* Un CSV par piéton, avec colonnes :
  `weather, velocity_kmh, distance_m, real_height_cm, true_label, predicted_label`
* Export séparé dans deux dossiers (adj / no-adj) définis par `OUT_DIR_ADJ` et `OUT_DIR_NOADJ`.

### Lancer

```bash
python crossing_decision.py
```

---

## 5.2 `crossing_decision_other_vehicule.py` — Règle “autre véhicule” + VISU + vidéos

### But

Même objectif que `crossing_decision.py` (CSV adj/no-adj par piéton), mais avec une **règle supplémentaire** :

> Pour chaque piéton, on cherche un **véhicule non-ego** annoté `vehicle.moving` tel que le piéton soit **devant** ce véhicule (long>0 dans le repère véhicule).
> On choisit le **plus proche** et on l’utilise comme véhicule de référence **uniquement s’il est vraiment plus proche que l’ego** (marge `VEH_CLOSER_EPS_M`).
> Sinon, fallback = ego.

### Filtres (importants)

* `PRED_ONLY_AHEAD`: conserve seulement les piétons **devant l’ego**
* `PRED_REQUIRE_VISIBLE`: impose que le piéton soit **visible dans CAM_FRONT** avec marge pixels (évite les points aux bords/frames douteuses)
* Filtrage strict si une info manque (vitesse, distance, taille, GT)

### VISU (optionnel)

Si `SAVE_VIS=True`, le script :

* enregistre **des frames annotées** (overlays : inputs modèle, GT, prédictions, bbox véhicule sélectionné, ligne V↔P, distances),
* et si `MAKE_VIDEO=True`, génère une **vidéo MP4 par piéton** (toutes ses frames, triées par timestamp).

### Sorties

* CSV adj/no-adj dans `OUT_DIR_ADJ` et `OUT_DIR_NOADJ`
* Frames annotées dans `VIS_DIR/<scene>/ped_<id>/...`
* Vidéos MP4 dans `VIS_DIR/<scene>/<scene>_ped_<id>.mp4`

### Lancer

```bash
python crossing_decision_other_vehicule.py
```

---

## 5.3 `visualize.py` — Viewer interactif CAM_FRONT (inspection qualitative)

### But

Un viewer OpenCV pour **inspecter visuellement** :

* la position des **piétons** (distance ego↔piéton, taille, ahead),
* le **GT crossing** via “drivable area” (selon la variante du script),
* les **véhicules `vehicle.moving`** (bbox),
* la **distance véhicule↔piéton** selon des règles (piéton devant le véhicule, pas “entre ego et véhicule”),
* et l’affichage des **passages piétons** (layer map `ped_crossing`) quand disponible.

### Commandes clavier

* `j/k` : frame ±1
* `n/p` : scène ±1
* `q` ou `ESC` : quitter

### Lancer

```bash
python visualize.py
```

---

## 6. Weather : `nuscenes_camfront_weather_night.csv`

Ce fichier sert de “ground truth météo” minimaliste :

* si `CAM_FRONT/xxx.jpg` ∈ liste → `weather="night"`
* sinon `weather="clear"`

(Le script compare soit le **chemin complet normalisé**, soit le **basename** de l’image.)

---

## 7. Reproduire l’évaluation (résumé)

1. Télécharger nuScenes + organiser `DATAROOT` (`v1.0-mini/`, `maps/`, `can_bus/` si dispo). ([GitHub][1])
2. Installer `nuscenes-devkit` + dépendances (shapely/opencv…). ([GitHub][1])
3. Lancer :

```bash
python crossing_decision.py
python crossing_decision_other_vehicule.py
python visualize.py
```

---

## 8. Remarques importantes

* **Filtrage strict** : les scripts préfèrent ignorer une frame plutôt que d’introduire une valeur par défaut (sauf fallback “moyenne de taille par location”).
* **CAN bus** : si absent, la vitesse ego bascule sur Δpose/Δt (moins robuste).
* Les chemins Windows (`E:\...`) doivent être adaptés (y compris les dossiers de sortie).
* Les CSV sont exportés **par piéton (`instance_token`)** pour garder une granularité compatible avec ton analyse “par agent”.
