#  **README — `experiment_design/`**

Conception du plan d’expérience, paramètres transmis à Unreal Engine et règles de génération des fichiers Excel utilisés pour piloter les sessions VR.

---

#  1. Objectif du dossier

Ce dossier contient :

* la **description du plan expérimental** pour les deux expériences VR :

  * **Expérience 1 — TTC Estimation Experiment**
  * **Expérience 2 — Crossing Decision Experiment**
* la **liste complète des paramètres contrôlés** et exposés à Python,
* la documentation des **scripts de génération des plans participants**,
* la logique utilisée par **run_full_session.py** pour piloter la session.

Il sert de **référence conceptuelle** pour comprendre comment chaque trial est défini.

---

#  2. Structure du dossier

```
experiment_design/
│
├── parameters_exposed_to_python.md
└── scripts_usage.md
```

- **`parameters_exposed_to_python.md`**
→ décrit chaque paramètre transmis de Python à Unreal (via `run_trial.py`)

- **`scripts_usage.md`**
→ documentation des scripts de génération (`generate_participant_plan_exp1.py`, `...exp2.py`)

---

#  3. Résumé du plan d’expérience

##  Expérience 1 — TTC Estimation Experiment

**Objectif :** le participant indique le moment où la voiture devrait arriver à sa hauteur (pression unique du trigger droit).

### Paramètres manipulés

* **3 vitesses** (km/h)
* **3 distances de disparition** (m)
* **3 météos** (pluie / nuages / lumières)

→ **27 trials** générés aléatoirement (= 3×3×3).

---

##  Expérience 2 — Crossing Decision Experiment

**Objectif :** le participant indique en continu s’il peut traverser (trigger gauche maintenu / relâché).

### Paramètres manipulés

* **3 vitesses** (km/h)
* **3 positions du participant** dans la scène
* **3 météos**

→ **27 trials** (= 3×3×3).

---

#  4. Génération des plans participants (Excel)

Les scripts suivants créent automatiquement les fichiers Excel :

```
scripts/generate_participant_plan_exp1.py
scripts/generate_participant_plan_exp2.py
```

Chaque fichier contient une ligne par trial, incluant :

| Colonne      | Exp1 | Exp2 | Description                           |
| ------------ | ---- | ---- | ------------------------------------- |
| trial        | ✔️   | ✔️   | numéro du trial                       |
| velocity_kmh | ✔️   | ✔️   | vitesse cible                         |
| disappear_m  | ✔️   | —    | distance de disparition               |
| position     | —    | ✔️   | index position (0,1,2)                |
| weather      | ✔️   | ✔️   | condition météo                       |
| Other meta   | ✔️   | ✔️   | graines, identifiants, booleans météo |

Ces fichiers sont lus automatiquement par :

```
scripts/run_full_session.py
```

---

#  5. Paramètres réellement transmis à Unreal Engine

Ces paramètres proviennent **exclusivement** de `run_trial.py`.
Il n’existe **pas** de paramètre `--experiment`.

##  Paramètres généraux CARLA

| Paramètre    | CLI              | Exemple     | Description                  |
| ------------ | ---------------- | ----------- | ---------------------------- |
| host         | `--host`         | `127.0.0.1` | Adresse CARLA                |
| port         | `-p` / `--port`  | `2000`      | Port CARLA                   |
| tm-port      | `--tm-port`      | `8000`      | Port Traffic Manager         |
| asynch       | `--asynch`       | flag        | Mode asynchrone              |
| hybrid       | `--hybrid`       | flag        | Mode hybride                 |
| no-rendering | `--no-rendering` | flag        | Désactive le rendu graphique |
| hero         | `--hero`         | flag        | Active vue "hero"            |
| respawn      | `--respawn`      | flag        | Respawn automatique          |
| seed         | `-s`             | `42`        | Seed aléatoire               |
| seedw        | `--seedw`        | `0`         | Seed météo                   |

---

##  Paramètres contrôlant le véhicule

| Paramètre           | CLI                                                            | Description |
| ------------------- | -------------------------------------------------------------- | ----------- |
| `--velocity`, `-v`  | vitesse cible (km/h)                                           |             |
| `--disappear`, `-d` | distance où le véhicule doit être détruit                      |             |
| `--filterv`, `-bp`  | type de blueprint (normal / sport / emergency selon ton setup) |             |
| `--generationv`     | génération blueprint                                           |             |

---

##  Paramètres météo

Trois booleans simples (influencent aussi le type de véhicule) :

| Paramètre        | CLI     | Exemple |
| ---------------- | ------- | ------- |
| `--rain`, `-r`   | `True`  |         |
| `--clouds`, `-c` | `False` |         |
| `--lights`, `-l` | `True`  |         |

---

##  Paramètres du participant

| Paramètre            | CLI      | Exemple |
| -------------------- | -------- | ------- |
| `--position`, `-pos` | `-pos 2` |         |

→ détermine où apparaît le participant :

* 0 = route maisons
* 1 = route opposée
* 2 = forêt/station-service

---

#  6. Logique d’appel : run_full_session.py → run_trial.py

Pour chaque ligne de l’Excel :

```
python run_trial.py -v <speed> -pos <position> -r <bool> -c <bool> -l <bool> -d <distance>
```

Puis :

* le participant réalise le trial
* au signal "Actor destroyed"
* l’expérimentateur presse :

  * **S** → save + clear
  * **Entrée** → trial suivant

---

##  7. Lien direct vers les fichiers

-  [**Paramètres exposés à Python**](./parameters_exposed_to_python.md)

- [**Usage des scripts de génération et session**](./scripts_usage.md)

- [**Détails du pipeline Unreal / VR**](../unreal_project/README.md)

- [**Déroulement complet des expériences**](../unreal_project/experience_flow.md)

---

#  8. Notes et bonnes pratiques

* Toujours vérifier que la **météo est cohérente** entre Python et Unreal (type de véhicule choisi).
* Les scripts Excel doivent être régénérés pour chaque participant.

---

#  9. Annexes techniques

Pour toute extension, nouvelle version, ou migration UE5/CARLA, se référer aux Blueprints documentés :

* [`EyeTracking_Pawn.md`](../unreal_project/Blueprints/Eye_tracking_pawn.md)
* [`CSV_File.md`](../unreal_project/Blueprints/CSV_File.md)
* [`BaseVehiclePawn.md`](../unreal_project/Blueprints/BaseVehiclePawn.md)
* [`RWText.md`](../unreal_project/CppClass/RWText.md)


