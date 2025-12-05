# Déroulement complet des expériences VR

Document de référence pour la reproduction et la compréhension du protocole

---

## 1. Introduction

Ce document décrit le déroulement des deux expériences VR utilisées dans la thèse :

1. **Expérience 1 — TTC Estimation Experiment**
   Le participant indique le moment estimé où la voiture atteindrait sa position.

2. **Expérience 2 — Crossing Decision Experiment**
   Le participant indique en continu s’il se sent capable de traverser devant le véhicule approchant.

Les expériences ont été développées sous **Unreal Engine 5.3.2**, intégrant une version modifiée de **CARLA** non disponible publiquement.
Les paramètres expérimentaux (spawn, vitesse, météo, distances) sont contrôlés par des scripts Python.

Les données issues des interactions VR sont automatiquement exportées au format CSV pour analyse.

---

## 2. Vue générale du pipeline

```
+----------------------+         +----------------------------+
| Scripts Python       | spawn   | Unreal Engine 5.3.2        |
| - run_trial.py       +-------> | - EyeTracking_Pawn         |
| - run_full_session.py| params  | - BaseVehiclePawn          |
+-----------+----------+         | - CSV_File (BP) → RWText   |
            |                    +--------------+-------------+
            |                                   |
            | save                               v
            |                          +------------------------------+
            +------------------------->| Dossiers Logs/<N>/           |
                                       | - peds.csv                   |
                                       | - cars.csv                   |
                                       | - gaze.csv                   |
                                       +------------------------------+
```

---

## 3. Déroulé global d’une session

Chaque session suit les étapes suivantes :

1. Installation du participant
2. Lancement d’Unreal Engine (VR Preview)
3. Chargement de la scène dans le casque
4. Lancement du script Python
5. Exécution séquentielle des trials
6. Sauvegarde des données
7. Changement d’expérience
8. Export final des logs

---

## 4. Préparation avant chaque session

### 4.1 Activation du VR Preview dans Unreal Engine

Unreal Engine doit être lancé **avant** d’appliquer les étapes ci-dessous.
Si ce n’est pas encore fait, suivre strictement :

[setup and execution](setup_and_execution_guide.md)

Une fois Unreal ouvert et le casque opérationnel :

1. Vérifier que le casque est bien reconnu par Unreal.
2. Dans l’éditeur, sélectionner **Play → VR Preview**.
![vr preview](img/selection_vr_preview.png)
![lancement](img/lancement_simu.png)

### 4.2 Préparation du terminal Python

Selon l’expérience :

* **Expérience 1** : fichier Excel généré via `generate_participant_plan_exp1.py`
* **Expérience 2** : fichier généré via `generate_participant_plan_exp2.py`

Le script `run_full_session.py` :

* lit les paramètres depuis l’Excel,
* exécute chaque trial,
* attend la validation manuelle (touche Entrée) avant de passer au suivant.

---

## 5. Structure d’un trial (Expérience 1 et 2)

### 5.1 Début de trial

1. Un script Python envoie une commande (exemple : `-v 40 -d 30 -pos 1 -r True -c True`).

2. Le Blueprint **EyeTracking_Pawn** reçoit les paramètres.

3. Le véhicule est spawné avec :

   * une vitesse cible,
   * une distance initiale,
   * un type de météo,
   * un modèle de véhicule dépendant de la vitesse.

4. Un signal sonore annonce le début du trial.

### 5.2 Phase d’approche du véhicule

* Le véhicule accélère selon une courbe exponentielle personnalisée.
* Sa vitesse converge progressivement vers la vitesse cible.
* Le participant observe la scène en VR.

### 5.3 Interaction du participant

Elle dépend du protocole expérimental (sections 6 et 7).

### 5.4 Fin du trial

Le trial se termine lorsque :

* le véhicule atteint la distance de disparition définie (**Expérience 1**) ;
* le véhicule passe devant le participant, effectue un virage, puis disparaît (**Expérience 2**).

La destruction de l’acteur véhicule est confirmée côté Python par :

**Véhicule détruit**

### 5.5 Sauvegarde d’un trial

À la fin de chaque trial, l’expérimentateur doit impérativement respecter l’ordre suivant :

1. Cliquer sur la fenêtre Unreal (VR Preview) pour lui redonner le focus.

2. Presser S afin d’enregistrer les buffers et les réinitialiser.

3. Revenir dans le terminal Python (PowerShell).

4. Presser Entrée pour lancer le trial suivant.

5. Revenir immédiatement à la fenêtre Unreal.

Cette alternance est obligatoire.
À défaut, le participant subira des saccades ou une perte de fluidité dans le casque, car Unreal perd temporairement le focus et dégrade le rendu VR.

En fin d’expérience, les dossiers de logs doivent être déplacés hors du répertoire Logs/.

---

## 6. Expérience 1 — TTC Estimation (Snap Crossing)

### 6.1 Objectif scientifique

Le participant indique l’instant où la voiture atteindrait exactement sa position.

* Il presse **une fois** le trigger droit pour marquer le “snap”.
* En cas de multiples pressions, seule la première valeur valide est utilisée.
* Les irrégularités sont corrigées en post-traitement.

### 6.2 Chronologie du trial

1. Signal sonore, spawn du véhicule
2. Accélération du véhicule
3. Observation
4. Pression du trigger droit → génération du snap
5. Confirmation sonore
6. Disparition du véhicule
7. Sauvegarde (S) puis validation (Entrée)

### 6.3 Données utilisées

**peds.csv**

* `Crossing = 1` à l’instant du snap
* Position et rotation du participant
* Horodatage utilisé pour synchronisation avec `cars.csv`

**cars.csv**

* Position et vitesse réelles du véhicule
* Position estimée (depuis Python)
* `Time_estimated` : TTC prévu
* Lignes finales nulles : destruction du véhicule

---

## 7. Expérience 2 — Continuous Crossing Decision

### 7.1 Objectif scientifique

Le participant indique en continu s’il peut traverser devant la voiture.

* Trigger gauche maintenu : *peut traverser*
* Relâché : *ne peut pas traverser*

### 7.2 Chronologie du trial

1. Signal sonore, spawn du véhicule
2. Mise à jour du signal Crossing à chaque Tick
3. Passage du véhicule et virage
4. Disparition
5. Sauvegarde et validation

Aucun signal sonore n’est émis lors des pressions.

### 7.3 Données utilisées

**peds.csv**

* `Crossing = 1` tant que le trigger gauche est maintenu
* Enregistrement à 90 Hz

**cars.csv**

* Permet d’identifier le moment exact du passage du véhicule

---

## 8. Comportement logiciel du véhicule

### 8.1 Accélération

Le véhicule utilise :

```
ExponentialCurve.uasset
```

Cette courbe permet une accélération réaliste et cohérente entre trials.

### 8.2 Disparition

Le paramètre `-pos` définit la route utilisée :

* 0 : route maison
* 1 : route opposée
* 2 : route forêt / station-service

Le script Python calcule :

* la distance d’apparition,
* la distance de disparition,
* la direction,
* le modèle de voiture.

### 8.3 Fin du trial

Le véhicule est détruit automatiquement lorsque la distance définie est dépassée.

---

## 9. Organisation des données — Dossiers Logs

Les fichiers sont générés dans :

```
C:\Users\carlaue5.3\CarlaUE5\Unreal\CarlaUnreal\Logs\<N>\
```

Où :

* `<N>` est un entier croissant,
* chaque trial produit un nouveau dossier,
* la création du dossier se fait lorsque la première ligne est écrite.

Contenu :

```
peds.csv
cars.csv
gaze.csv
```

(`cross.csv` existe dans RWText mais n’est pas utilisé.)

---

## 10. Description des CSV

### 10.1 peds.csv

| Colonne             | Description                              |
| ------------------- | ---------------------------------------- |
| Time                | Temps Unreal                             |
| X_pos, Y_pos, Z_pos | Position du participant                  |
| X_rot, Y_rot, Z_rot | Rotation (Euler)                         |
| Crossing            | 1 lors du snap (Exp1) ou pression (Exp2) |

Fréquence : 90 Hz.

### 10.2 cars.csv

| Colonne        | Description           |
| -------------- | --------------------- |
| Time           | Temps réel            |
| Time_estimated | TTC estimé par Python |
| X_pos…         | Position réelle       |
| X_est…         | Position estimée      |
| X_vel…         | Vitesse réelle        |

Les lignes finales nulles signalent la destruction du véhicule.

### 10.3 gaze.csv

| Colonne      | Description                 |
| ------------ | --------------------------- |
| Time         | Temps                       |
| X_origin…    | Position de l’œil           |
| X_direction… | Direction du regard         |
| X_fixation…  | Toujours nul dans ce projet |
| Confidence   | Score entre 0 et 1          |

---

## 11. Résumé des commandes clavier

| Commande       | Fonction                          |
| -------------- | --------------------------------- |
| S              | Sauvegarde + reset buffers        |
| C              | Reset des buffers sans sauvegarde |
| Entrée         | Passage au trial suivant          |
| Trigger droit  | Snap (Exp1)                       |
| Trigger gauche | Crossing continu (Exp2)           |

---

## 12. Erreurs fréquentes et solutions

**Aucun CSV généré**
→ Vérifier que la touche S a été pressée avant Entrée.

**Valeurs nulles dans gaze.csv**
→ Relancer VR Preview.

**Le véhicule n’apparaît pas**
→ La carte n’est pas entièrement chargée.

**Le véhicule ne disparaît pas**
→ Paramètre `-d` incorrect ou mauvaise position.

**Incohérence dans les playlists Python**
→ Vérifier la correspondance avec le fichier Excel.

---

## 13. Liens vers la documentation associée

* EyeTracking_Pawn : `Blueprints/Eye_tracking_pawn.md`
* CSV_File : `Blueprints/CSV_File.md`
* BaseVehiclePawn : `Blueprints/BaseVehiclePawn.md`
* RWText (C++) : `CppClass/RWText.md`
* Guide d’exécution : `setup_and_execution_guide.md`

---

## 14. Analyse post-expérience

Les outils d’analyse permettent un retour immédiat auprès du participant et une vérification de la qualité des enregistrements.

### Localisation des scripts

```
vr-experiment/analysis/
```

Scripts :

* `analyze_exp1_log.py`
* `analyze_exp2_log.py`

Ils utilisent les fichiers :

```
CarlaUnreal/Logs/<N>/
```

### Analyse Exp1

* Détection du temps de disparition
* Détection du snap
* Calcul TTC perçu / TTC réel / erreur
* Visualisations interactives
* Statistiques : biais, MAE, RMSE, pourcentage correct
* Inspection détaillée d’un trial

### Analyse Exp2

* Reconstruction du signal Crossing
* Gap voiture–piéton
* Détection de la première transition 1→0
* Calcul EOCI (distance/vitesse)
* Visualisations : heatmaps, barplots, courbes Crossing vs Gap

### Workflow d’analyse

1. Déplacer les dossiers `<N>` dans un dossier local
2. Exécuter via Streamlit :

```
streamlit run analyze_exp1_log.py
streamlit run analyze_exp2_log.py
```

3. Le fichier Excel de l’expérience doit être présent dans le même dossier
4. Les résultats s’affichent dans une interface web locale

### Usage auprès du participant

Les graphiques permettent un retour immédiat et facilitent la validation des enregistrements (eye-tracking, signal Crossing).

