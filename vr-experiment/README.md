# Pedestrian-Crossing Behavior – VR Experiment  

Ce répertoire contient l’ensemble des composants nécessaires à la réalisation et à l’analyse des deux expériences VR développées dans le cadre du projet AI4CCAM :

- **Expérience 1 — TTC Estimation Experiment**  
- **Expérience 2 — Crossing Decision Experiment**

Les expériences reposent sur l’intégration de Python, Unreal Engine 5.3.2, CARLA, Meta Quest Pro et un pipeline d’écriture CSV temps réel.

Ce document décrit le pipeline global **dans l’ordre chronologique** et renvoie vers la documentation détaillée présente dans les sous-dossiers.

---

## 1. Objectif général

Le répertoire `vr-experiment/` rassemble tous les éléments nécessaires pour :

- générer les plans d’expérience propres à chaque participant ;
- exécuter les expériences VR sous Unreal Engine 5.3.2 + CARLA modifié ;
- enregistrer des données synchronisées (piéton, véhicule, regard) ;
- analyser les comportements via des interfaces Streamlit.

Les deux expériences sont décrites en détail dans :

[`unreal_project/experience_flow.md`](unreal_project/experience_flow.md)

---

## 2. Pipeline global : du démarrage à l’analyse

Cette section donne la vue d’ensemble du pipeline. Les détails opérationnels (captures, paramètres, commandes exactes) sont fournis dans les fichiers référencés.

### 2.1. Préparer le casque et lancer Unreal

L’ensemble de la procédure matérielle et logicielle (branchement du Meta Quest Pro, gestion de Meta Quest Link, contraintes de mise à jour, condition de la “salle grise”, lancement du projet Unreal modifié, passage en VR Preview) est décrit dans :

[`unreal_project/setup_and_execution_guide.md`](unreal_project/setup_and_execution_guide.md)

Ce guide doit impérativement être suivi avant de lancer les scripts Python.

---

### 2.2. Générer le plan d’expérience du participant

Les fichiers Excel décrivant la séquence des essais (vitesse, distance, météo, position) sont générés via les scripts du dossier `scripts/`.

- Plan Expérience 1 : `scripts/generate_participant_plan_exp1.py`  
- Plan Expérience 2 : `scripts/generate_participant_plan_exp2.py`

Description du design expérimental et des paramètres transmis à Python :

- [`experiment_design/README.md`](experiment_design/README.md)  
- [`experiment_design/parameters_exposed_to_python.md`](experiment_design/parameters_exposed_to_python.md)  
- [`experiment_design/scripts_usage.md`](experiment_design/scripts_usage.md)

Vue d’ensemble des scripts Python :

[`scripts/README.md`](scripts/README.md)

---

### 2.3. Lancer les trials (Python → Unreal Engine)

Deux modes d’exécution sont prévus :

- **Session complète** (lecture séquentielle du fichier Excel, 27 essais)  
  - `scripts/run_full_session.py`

- **Trial individuel** (commande unique, utile pour les tests)  
  - `scripts/run_trial.py`

Le comportement attendu (relation entre commandes Python, apparition du véhicule, interaction du participant, sauvegarde des données) est décrit dans :

[`unreal_project/experience_flow.md`](unreal_project/experience_flow.md)

Les détails d’appel des scripts sont documentés dans :

[`experiment_design/scripts_usage.md`](experiment_design/scripts_usage.md)

---

### 2.4. Enregistrement des données (Unreal -> CSV)

À chaque essai, Unreal Engine écrit les données brutes dans :

```text
C:\Users\carlaue5\CarlaUE5\Unreal\CarlaUnreal\Logs\<N>\
````

Les fichiers principaux sont :

* `peds.csv` : trajectoire et état de crossing du participant ;
* `cars.csv` : trajectoire et vitesse du véhicule ;
* `gaze.csv` : données de suivi oculaire (Expérience 1).

Le pipeline complet d’écriture (Blueprints + C++) est décrit dans :

* [`unreal_project/Blueprints/CSV_File.md`](unreal_project/Blueprints/CSV_File.md)
* [`unreal_project/CppClass/RWText.md`](unreal_project/CppClass/RWText.md)
* [`unreal_project/Blueprints/README.md`](unreal_project/Blueprints/README.md)

---

### 2.5. Analyse post-expérience (Streamlit)

Les analyses se font à partir du dossier `Logs/` contenant :

* le fichier Excel (`exp1*.xlsx` ou `exp2*.xlsx`) ;
* un dossier numéroté par essai (`1/`, `2/`, …) avec les CSV correspondants.

#### Expérience 1 — TTC Estimation Experiment

Lancement :

```bash
streamlit run analysis/analyze_exp1_log.py
```

Fonctionnalités (vue d’ensemble) :

* comparaison temps perçu vs temps théorique ;
* erreurs (biais, MAE, RMSE, % d’essais corrects) ;
* visualisations par vitesse, distance, météo.

Détails :

[`analysis/README.md`](analysis/README.md)

#### Expérience 2 — Crossing Decision Experiment

Lancement :

```bash
streamlit run analysis/analyze_exp2_log.py
```

Fonctionnalités (vue d’ensemble) :

* calcul de la distance de sécurité au moment où le participant cesse de vouloir traverser ;
* agrégations par vitesse, météo, position ;
* courbes crossing (0/1) vs distance pour chaque position.

Détails :

[`analysis/README.md`](analysis/README.md)

---

## 3. Structure du répertoire

```text
vr-experiment/
 ├── analysis/                 # Analyse Exp1 & Exp2 (Streamlit)
 ├── experiment_design/        # Design expérimental et paramètres Python↔UE
 ├── scripts/                  # Plans, orchestration des trials et sessions
 ├── unreal_project/           # Éléments Unreal Engine 5.3.2 + CARLA modifié
 └── README.md                 # Présent document
```

---

## 4. Documentation de référence

| Sujet                                      | Lien                                                                                                     |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Déroulement complet des essais             | [`unreal_project/experience_flow.md`](unreal_project/experience_flow.md)                                 |
| Guide de configuration & exécution (VR/UE) | [`unreal_project/setup_and_execution_guide.md`](unreal_project/setup_and_execution_guide.md)             |
| Design expérimental                        | [`experiment_design/README.md`](experiment_design/README.md)                                             |
| Paramètres Python → Unreal                 | [`experiment_design/parameters_exposed_to_python.md`](experiment_design/parameters_exposed_to_python.md) |
| Usage détaillé des scripts                 | [`experiment_design/scripts_usage.md`](experiment_design/scripts_usage.md)                               |
| Vue d’ensemble des scripts                 | [`scripts/README.md`](scripts/README.md)                                                                 |
| Analyse Exp1 & Exp2                        | [`analysis/README.md`](analysis/README.md)                                                               |
| Blueprints Unreal                          | [`unreal_project/Blueprints/README.md`](unreal_project/Blueprints/README.md)                             |
| CSV Logic (Blueprint)                      | [`unreal_project/Blueprints/CSV_File.md`](unreal_project/Blueprints/CSV_File.md)                         |
| C++ RWText                                 | [`unreal_project/CppClass/RWText.md`](unreal_project/CppClass/RWText.md)                                 |

