
## 1. Structure d’un trial (Expérience 1 et 2)

### 1.1 Début de trial

1. Un script Python envoie une commande (exemple : `-v 40 -d 30 -pos 1 -r True -c True`).

2. Le Blueprint **EyeTracking_Pawn** reçoit les paramètres.

3. Le véhicule est spawné avec :

   * une vitesse cible,
   * une distance initiale,
   * un type de météo,
   * un modèle de véhicule dépendant de la vitesse.

4. Un signal sonore annonce le début du trial.

### 1.2 Phase d’approche du véhicule

* Le véhicule accélère selon une courbe exponentielle personnalisée.
* Sa vitesse converge progressivement vers la vitesse cible.
* Le participant observe la scène en VR.

### 1.3 Interaction du participant

Elle dépend du protocole expérimental (sections 6 et 7).

---

## 2. Expérience 1 — TTC Estimation (Snap Crossing)

### 2.1 Objectif scientifique

Le participant indique l’instant où la voiture atteindrait exactement sa position.

* Il presse **une fois** le trigger droit pour marquer le “snap”.
* En cas de multiples pressions, seule la première valeur valide est utilisée.
* Les irrégularités sont corrigées en post-traitement.

### 2.2 Chronologie du trial

1. Signal sonore, spawn du véhicule
2. Accélération du véhicule
3. Observation
4. Pression du trigger droit → génération du snap
5. Confirmation sonore
6. Disparition du véhicule
7. Sauvegarde (Entrée sur fenetre Unreal) puis validation (Entrée sur terminal)

### 2.3 Données utilisées

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

## 3. Expérience 2 — Continuous Crossing Decision

### 3.1 Objectif scientifique

Le participant indique en continu s’il peut traverser devant la voiture.

* Trigger gauche maintenu : *peut traverser*
* Relâché : *ne peut pas traverser*

### 3.2 Chronologie du trial

1. Signal sonore, spawn du véhicule
2. Mise à jour du signal Crossing à chaque Tick
3. Passage du véhicule et virage
4. Disparition
5. Sauvegarde et validation (idem)

Aucun signal sonore n’est émis lors des pressions.

### 3.3 Données utilisées

**peds.csv**

* `Crossing = 1` tant que le trigger gauche est maintenu
* Enregistrement à 90 Hz

**cars.csv**

* Permet d’identifier le moment exact du passage du véhicule

---

## 4. Comportement logiciel du véhicule

### 4.1 Accélération

Le véhicule utilise :

```
ExponentialCurve.uasset
```

Cette courbe permet une accélération réaliste et cohérente entre trials.

### 4.2 Disparition

Le paramètre `-pos` définit la route utilisée :

* 0 : route maison
* 1 : route opposée
* 2 : route forêt / station-service

Le script Python calcule :

* la distance d’apparition,
* la distance de disparition,
* la direction,
* le modèle de voiture.

### 4.3 Fin du trial

Le véhicule est détruit automatiquement lorsque la distance définie est dépassée.

---

## 5. Organisation des données — Dossiers Logs

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

## 6. Description des CSV

### 6.1 peds.csv

| Colonne             | Description                              |
| ------------------- | ---------------------------------------- |
| Time                | Temps Unreal                             |
| X_pos, Y_pos, Z_pos | Position du participant                  |
| X_rot, Y_rot, Z_rot | Rotation (Euler)                         |
| Crossing            | 1 lors du snap (Exp1) ou pression (Exp2) |

Fréquence : 90 Hz.

### 6.2 cars.csv

| Colonne        | Description           |
| -------------- | --------------------- |
| Time           | Temps réel            |
| Time_estimated | TTC estimé par Python |
| X_pos…         | Position réelle       |
| X_est…         | Position estimée      |
| X_vel…         | Vitesse réelle        |

Les lignes finales nulles signalent la destruction du véhicule.

### 6.3 gaze.csv

| Colonne      | Description                 |
| ------------ | --------------------------- |
| Time         | Temps                       |
| X_origin…    | Position de l’œil           |
| X_direction… | Direction du regard         |
| X_fixation…  | Toujours nul dans ce projet |
| Confidence   | Score entre 0 et 1          |

---

## 7. Résumé des commandes clavier

| Commande       | Fonction                          |
| -------------- | --------------------------------- |
| S              | Sauvegarde + reset buffers        |
| C              | Reset des buffers sans sauvegarde |
| Entrée         | Passage au trial suivant          |
| Trigger droit  | Snap (Exp1)                       |
| Trigger gauche | Crossing continu (Exp2)           |

---

## 8. Erreurs fréquentes et solutions

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

## 9. Liens vers la documentation associée

* EyeTracking_Pawn : `Blueprints/Eye_tracking_pawn.md`
* CSV_File : `Blueprints/CSV_File.md`
* BaseVehiclePawn : `Blueprints/BaseVehiclePawn.md`
* RWText (C++) : `CppClass/RWText.md`
* Guide d’exécution : `setup_and_execution_guide.md`

---

## 10. Analyse post-expérience

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

