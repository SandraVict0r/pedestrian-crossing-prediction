# Unreal Project – VR Experiment

## Documentation du répertoire `unreal_project/`

Ce répertoire contient l’ensemble des éléments nécessaires à l’exécution des expériences VR développées sous Unreal Engine 5.3.2 pour l’étude du comportement piéton (estimation du TTC et décision de traversée).

Il regroupe :

* les Blueprints utilisés pour la logique VR et l’enregistrement des données ;
* la classe C++ personnalisée **RWText**, utilisée pour la création des fichiers et l’écriture en CSV ;
* les éléments de scène (pawns VR, vehicle pawn, éléments d’environnement, interface utilisateur) ;
* les guides détaillant l’installation, l’exécution et le déroulement des expériences.

---

## 1. Structure du répertoire

```
unreal_project/
│
├── Blueprints/
│   ├── *.uasset                 → Blueprints Unreal Engine
│   ├── *.md                     → Documentation associée
│   └── img/                     → Captures d’écran des nœuds et graphes
│
├── CppClass/
│   ├── RWText.h                 → Déclaration de la classe C++
│   ├── RWText.cpp               → Logique d’écriture des fichiers
│   └── RWText.md                → Documentation détaillée
│
├── img/                         → Illustrations du démarrage UE et VR
│
├── experience_flow.md           → Déroulement complet des deux expériences
├── setup_and_execution_guide.md → Guide d’installation et d’exécution
└── README.md                    → Présent document
```

---

## 2. Fonctionnement général

Le projet Unreal constitue l’interface VR utilisée pour exposer le participant aux scénarios expérimentaux.
Il assure la capture des données nécessaires à l’analyse des comportements et interagit avec les scripts Python via CARLA pour recevoir les paramètres d’un essai.

À chaque trial, le système produit trois fichiers CSV :

* `peds.csv` : position et rotation du participant, état de crossing ;
* `cars.csv` : trajectoire, vitesse et événements liés au véhicule ;
* `gaze.csv` : données de suivi oculaire (Meta Quest Pro).

Le pipeline repose sur deux composants principaux :

**CSV_File (Blueprint)** :  génère les chaînes de données, gère les buffers et transmet les informations à la classe C++.
**RWText (C++)** :  crée les répertoires correspondants aux essais et écrit les données dans les fichiers CSV.

---

## 3. Procédure de lancement de l’application VR

La procédure complète de mise en route, incluant les prérequis matériels, la connexion du casque Meta Quest Pro, l’ouverture du projet Unreal modifié, le passage en VR Preview et le lancement des trials via Python,  est documentée dans :

[➡ **`setup_and_execution_guide.md`**](setup_and_execution_guide.md)

Ce guide détaille :

* l’ordre exact des branchements et de mise sous tension ;
* la nécessité d’être dans la “salle grise” Meta Quest Link avant d’ouvrir Unreal ;
* l’ouverture du projet CARLA modifié (`CarlaUnreal.uproject`) ;
* la sélection du mode VR Preview ;
* l’exécution des trials et sessions complètes via les scripts Python ;
* les vérifications préalables à tout essai.

---

## 4. Déroulement des expériences

Le déroulé expérimental complet, la logique des deux expériences, la chronologie détaillée des trials ainsi que la description du pipeline Unreal ↔ Python ↔ CSV sont présentés dans :

[➡ **`experience_flow.md`**](experience_flow.md)

Ce document détaille :

* la structure d’un trial (spawn, approche, interaction, disparition) ;
* les différences entre les expériences Exp1 (TTC Estimation) et Exp2 (Continuous Crossing) ;
* la nature et l’usage des données enregistrées ;
* l’organisation d’une session complète.

---

## 5. Description des principaux Blueprints

### 5.1. EyeTracking_Pawn

Documentation : `Blueprints/Eye_tracking_pawn.md`

Fonctions principales :

* Acquisition de la position et de l’orientation du participant en VR.
* Capture du eye tracking.
* Gestion des interactions (trigger droit pour Exp1, trigger gauche pour Exp2).
* Enregistrement à 90 Hz.

---

### 5.2. BaseVehiclePawn

Documentation : `Blueprints/BaseVehiclePawn.md`

Rôle :

* Réception des paramètres envoyés par Python (vitesse, météo, position).
* Déplacement selon une **ExponentialCurve**.
* Gestion de la disparition automatique du véhicule.
* Transmission des données à `CSV_File`.

---

### 5.3. CSV_File

Documentation : `Blueprints/CSV_File.md`

Rôle :

* Agrégation et bufferisation des données provenant des différents pawns.
* Transmission vers la classe C++ par :

  * `AddToPedsBuffer()`
  * `AddToCarsBuffer()`
  * `AddToGazeBuffer()`
  * `WriteBuffersToFiles()`

---

### 5.4. BP_TrialManager

Conservé pour archivage ; non utilisé dans la version finale.

---

### 5.5. WBP_TrialToast

Interface utilisateur initialement prévue ; désactivée dans la version finale.

---

## 6. Classe C++ RWText

Documentation : `CppClass/RWText.md`

Cette classe gère la création des répertoires et l’écriture des fichiers CSV dans :

```
CarlaUnreal/Logs/<N>/
```

Fonctionnement :

1. Création du dossier lors de la première ligne écrite.
2. Stockage dans des buffers à chaque frame.
3. Appui sur **S** → écriture et nettoyage.
4. Appui sur **C** → nettoyage sans écriture.

---

## 7. Répertoire `/img`

Contient des captures illustrant le lancement d’Unreal, le passage en VR Preview et le chargement de la carte.

---

## 8. Guides inclus dans ce répertoire

* Déroulement des deux expériences : `experience_flow.md`
* Guide d’installation et d’exécution : `setup_and_execution_guide.md`
* Documentation des Blueprints : `Blueprints/README.md`
* Documentation RWText : `CppClass/RWText.md`

---

## 9. Notes de reproductibilité

* Fréquence d’acquisition : 90 Hz.
* Véhicule détruit automatiquement en fin de trial.
* Sauvegarde uniquement via la touche **S**.
* Chaque trial crée un répertoire `Logs/<N>/`.
* Après 27 trials, les dossiers doivent être archivés avant un nouveau participant.

---

## 10. Schéma général du pipeline

```
Python (run_trial.py)
      ↓ paramètres
Unreal Engine (VR Preview)
      ↓ capture VR et eye tracking
EyeTracking_Pawn / BaseVehiclePawn
      ↓ bufferisation
CSV_File (Blueprint)
      ↓ écriture
RWText (C++)
      ↓ export CSV
CarlaUnreal/Logs/<N>/peds.csv
CarlaUnreal/Logs/<N>/cars.csv
CarlaUnreal/Logs/<N>/gaze.csv
```
