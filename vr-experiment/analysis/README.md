# Analysis – README

Ce dossier regroupe les outils d’analyse associés aux deux expériences VR :

* **Expérience 1 – TTC Estimation Experiment**  
  Analyse du temps perçu par le participant pour l’arrivée du véhicule.

* **Expérience 2 – Crossing Decision Experiment**  
  Analyse du signal de décision de traversée et de la distance véhicule–piéton.

Les deux outils sont implémentés en Python/Streamlit afin de permettre une visualisation immédiate après chaque session, à partir des fichiers CSV générés par Unreal Engine.

---

## Structure

```

analysis/
│
├── analyze_exp1_log.py   # Analyse Expérience 1 (TTC perçu)
└── analyze_exp2_log.py   # Analyse Expérience 2 (Crossing/Distance)

````

---

## Prérequis

Installer les dépendances :

```bash
pip install streamlit plotly pandas numpy openpyxl
````

---

## Exécution des outils

### Expérience 1

```bash
streamlit run analyze_exp1_log.py
```

### Expérience 2

```bash
streamlit run analyze_exp2_log.py
```

---

## Organisation attendue du dossier Logs

Les scripts lisent les données produites par Unreal Engine dans :

```
C:\Users\<USER>\CarlaUE5\Unreal\CarlaUnreal\Logs\
```

Organisation standard :

```
Logs/
│
├── exp1.xlsx   # ou exp2.xlsx : plan d’expérience
├── 1/
│   ├── cars.csv
│   ├── peds.csv
│   └── gaze.csv   # uniquement Expérience 1
├── 2/
│   ├── cars.csv
│   ├── peds.csv
│   └── gaze.csv
...
```

Contraintes :

* chaque essai doit avoir été sauvegardé à l’aide de la touche `S` dans Unreal ;
* le plan d’expérience doit se trouver au même niveau que les dossiers numérotés ;
* les CSV doivent être ceux générés via le backend C++ `RWText`.

---

## Description des outils

### analyze_exp1_log.py — TTC Estimation Experiment

Cet outil reconstruit pour chaque essai :

* le temps de disparition du véhicule (analyse du `X_pos`) ;
* l’instant du snap (trigger) ;
* le temps perçu par le participant ;
* l’erreur relative au temps réel calculé via les paramètres du trial.

Métriques produites :

* biais ;
* MAE ;
* RMSE ;
* écart-type ;
* pourcentage d’essais corrects (selon une tolérance configurable).

Visualisations incluses :

* temps perçu vs temps réel ;
* histogrammes d’erreurs ;
* boxplots (vitesse, météo, distance) ;
* tableau récapitulatif des essais.

---

### analyze_exp2_log.py — Crossing Decision Experiment

Cet outil analyse le comportement de décision en continu.
Il reconstruit :

* le signal Crossing normalisé en valeurs binaires ;
* la série temporelle du gap (distance véhicule–piéton) ;
* la distance de sécurité, définie comme la distance au moment de la première transition Crossing 1→0.

Indicateurs disponibles :

* distance de sécurité par essai ;
* agrégats par vitesse, météo et position.

Visualisations incluses :

* barplots des distances de sécurité ;
* heatmaps vitesse × météo ;
* courbes Crossing vs Distance par position ;
* tableau des essais.

Cet outil n’est pas destiné à calculer une estimation de type TTC ou « opportunité temporelle », la tâche expérimentale ne reposant sur aucune estimation explicite.

---

## Notes d’utilisation

* Les scripts opèrent en lecture seule : aucune donnée n’est modifiée.
* Les CSV doivent être complets et correctement sauvegardés (`S` puis `Entrée` entre chaque trial).
* Les fichiers doivent être strictement conformes au format généré par `RWText` (séparateur `;`).
* L’analyse échoue si le plan d’expérience associé (exp1.xlsx ou exp2.xlsx) est absent ou mal nommé.

---

## Documentation liée

* [Protocole complet des expériences](../unreal_project/experience_flow.md)

* [Scripts Python de session](../scripts/README.md)

* [Plans d’expérience](../experiment_design/README.md)

* [Pipeline Unreal → CSV (Blueprints + backend C++)](../unreal_project/README.md)

