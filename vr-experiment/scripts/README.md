# Scripts Python — Gestion des Sessions VR

Ce dossier contient les scripts Python utilisés pour exécuter les expériences VR (Expérience 1 et Expérience 2).
Ils assurent :

* la génération des plans d’expérience (Excel),
* le lancement et le contrôle des trials,
* la communication avec Unreal Engine via CARLA,
* l'automatisation d’une session complète de 27 trials.

---

# 1. Liste des scripts

| Script                                  | Rôle                                                                                       |
| --------------------------------------- | ------------------------------------------------------------------------------------------ |
| **`generate_participant_plan_exp1.py`** | Génère un fichier Excel contenant 27 commandes pour l’Expérience 1 (TTC estimation).       |
| **`generate_participant_plan_exp2.py`** | Génère un fichier Excel contenant 27 commandes pour l’Expérience 2 (Crossing continu).     |
| **`run_trial.py`**                      | Exécute un seul trial : spawn du véhicule avec les paramètres donnés en ligne de commande. |
| **`run_full_session.py`**               | Exécute automatiquement une liste de trials en lisant un fichier Excel (Exp1 ou Exp2).     |

---

# 2. Génération des plans d’expérience (`generate_participant_plan_exp1.py` / `exp2.py`)

Chaque script génère un fichier Excel **participant_plan_expX.xlsx** contenant 27 lignes correspondant aux 27 trials d’un participant.

### Expérience 1 (TTC Estimation)

Les 27 trials couvrent toutes les combinaisons :

* **3 vitesses**
* **3 distances de disparition**
* **3 conditions météo**

Chaque ligne contient les arguments destinés à `run_trial.py`.

### Expérience 2 (Crossing Continu)

Les 27 trials couvrent :

* **3 vitesses**
* **3 météos**
* **3 positions du participant dans la carte**

---

# 3. Exécution d’un trial (`run_trial.py`)

`run_trial.py` est appelé soit :

* manuellement (pour tester un trial),
* automatiquement via `run_full_session.py`.

##  Commande générale

```bash
python run_trial.py [OPTIONS]
```

## Liste complète des arguments supportés

### Paramètres expérimentaux

| Argument      | Alias  | Type        | Rôle                                                                      |
| ------------- | ------ | ----------- | ------------------------------------------------------------------------- |
| `--velocity`  | `-v`   | int         | Vitesse cible du véhicule (km/h).                                         |
| `--disappear` | `-d`   | float       | Distance où le véhicule sera détruit (Exp1) ou dépassement trajet (Exp2). |
| `--position`  | `-pos` | int (0/1/2) | Position du participant dans la carte CARLA.                              |
| `--lights`    | `-l`   | bool        | Active phares / variations lumière.                                       |
| `--clouds`    | `-c`   | bool        | Active nuages / surcouche météo.                                          |
| `--rain`      | `-r`   | bool        | Active pluie (détermine aussi le modèle de véhicule).                     |

### Paramètres CARLA

| Argument        | Alias | Type | Description                                         |
| --------------- | ----- | ---- | --------------------------------------------------- |
| `--host`        |       | str  | Adresse IP du serveur CARLA (`127.0.0.1`).          |
| `--port`        | `-p`  | int  | Port CARLA (`2000`).                                |
| `--filterv`     | `-bp` | str  | Filtre Blueprint du véhicule (normal, sport, etc.). |
| `--generationv` |       | str  | Génération de véhicules CARLA (“All”).              |
| `--tm-port`     |       | int  | Port du Traffic Manager.                            |
| `--asynch`      |       | flag | Mode asynchrone.                                    |
| `--hybrid`      |       | flag | Mode hybride.                                       |
| `--seed`        | `-s`  | int  | Seed aléatoire (reproductibilité).                  |
| `--seedw`       |       | int  | Seed météo.                                         |

### Paramètres "hero" / affichage

| Argument         | Type | Description                                        |
| ---------------- | ---- | -------------------------------------------------- |
| `--hero`         | flag | Définit ce véhicule comme véhicule "joueur" CARLA. |
| `--respawn`      | flag | Permet le respawn automatique.                     |
| `--no-rendering` | flag | Mode sans rendu (debug).                           |

---

# 4. Exécution d'une session complète (`run_full_session.py`)

`run_full_session.py` lit un fichier Excel contenant les paramètres de 27 trials, et exécute :

1. Trial 1
2. Attente touche **Entrée**
3. Trial 2
4. …
5. Jusqu’au trial 27

## Commande

```bash
python run_full_session.py
```

Au lancement, le script :

1. ouvre une fenêtre pour **sélectionner le fichier Excel** (Exp1 ou Exp2),
2. charge la liste des commandes,
3. lance `run_trial.py` 27 fois,
4. attend **Entrée** à la fin de chaque trial,
5. recommence jusqu’à épuisement des lignes.

---

# 5. Organisation d'une ligne Excel

Chaque ligne contient une commande complète :

```text
--velocity 40 --disappear 30 --position 1 --rain True
```

ou pour exp2 :

```text
--velocity 30 --position 2 --clouds True
```

Les scripts ne modifient pas ces commandes :
 **elles sont envoyées telles quelles** à `run_trial.py`.

---

# 6. Exemples d’utilisation

### Lancer un trial unique

```bash
python run_trial.py -v 40 -d 30 -pos 1 -r True
```

### Lancer une session complète

```bash
python run_full_session.py
```

Puis sélectionner le fichier Excel généré par :

* `generate_participant_plan_exp1.py`
  ou
* `generate_participant_plan_exp2.py`

### Générer un plan d’expérience

```bash
python generate_participant_plan_exp1.py
```

---

# 7. Documentation liée

* [**Déroulement complet des expériences**](../unreal_project/experience_flow.md)

* [**Design expérimental & paramètres exposés à Python**](../experiment_design/README.md)

* [**Pipeline Unreal vers CSV (Blueprints & C++)**](../unreal_project/README.md)

* [**Analyse des données enregistrées**](../analysis/README.md)

---

#  8. Notes de reproductibilité

* Les plans d’expérience sont générés aléatoirement (ordre des 27 trials).
* Les scripts doivent être lancés **pendant que VR Preview est actif** dans Unreal Engine.
* La sauvegarde des CSV dépend de la touche **S** pressée dans Unreal.


