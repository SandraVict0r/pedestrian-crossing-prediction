# *VR Experiment Analysis* — README

### `data_analysis_exp1.ipynb` & `data_analysis_exp2.ipynb`

Ce dossier regroupe les deux notebooks d’analyse utilisés pour extraire, visualiser et interpréter les résultats des deux expériences VR de la thèse.

---

# Objectif global

Ces notebooks permettent d’explorer :

* **l’estimation du temps de collision (TTC)** – *Expérience 1*
* **la décision de traverser** selon la vitesse, la météo et les caractéristiques individuelles – *Expérience 2*

Ils fournissent toutes les figures, statistiques et vérifications nécessaires à la rédaction du manuscrit (chapitres résultats et discussion).

---

# Contenus

---

## 1️ `data_analysis_exp1.ipynb` — *Perception du TTC*

### Objectif

Analyser comment les participants estiment le **TTC** (Time-To-Collision) lorsque la voiture disparaît à différentes distances.

### Contenu

* Chargement des données MySQL (`Perception`)
* Calcul TTC réel vs perçu
* Calcul de l’erreur : `error_ttc = perceived_time - real_time`

### Analyses réalisées

* Statistiques descriptives (mean, median, MAE, biais)
* Histogrammes / boxplots
* Effets :

  * vitesse
  * météo
  * distance d’apparition
* Courbe « difficulté d’estimation du TTC »
* Tests (ANOVA, Kruskal–Wallis, Tukey/Dunn)
* Corrélations
* Heatmaps
* Analyse des effets individuels (âge, taille, sexe, permis)
* Modèles mixtes (random intercept = participant_id)

### Intérêt scientifique

* Seuil critique autour de **5 s** pour une estimation fiable.
* Variabilité individuelle faible mais détectable.
* Influence claire des conditions environnementales.

---

## 2 `data_analysis_exp2.ipynb` — *Décision de traversée*

### Objectif

Analyser comment les participants évaluent **leur capacité à traverser** avant l'arrivée de la voiture.

### Variables clés

* `T_end` → seuil temporel
* `D_end` → seuil spatial

### Contenu

* Chargement des données (`Crossing`) + fusion participant
* Construction des variables
* Catégories météo / vitesse / morphologie

### Analyses réalisées

* Descriptifs (T_end, D_end)
* QQ-plots / normalité
* Corrélations + modèles polynomiaux
* Effets :

  * météo
  * sexe
  * permis
  * quartiles d’âge
  * quartiles de taille
* Visualisations avancées :

  * LOWESS
  * polynômes
  * barplots croisés
* Détection des outliers
* Tableaux de synthèse

### Intérêt scientifique

* Influence forte de la météo et de la vitesse.
* Effet morphologique (taille) modéré mais présent.
* Variabilité bien plus élevée que dans l’estimation du TTC.

---

# Complémentarité des deux notebooks

| Analyse                          | Expérience 1        | Expérience 2               |
| -------------------------------- | ------------------- | -------------------------- |
| Estimation du TTC                | ✔                   | ✖                          |
| Décision de traversée            | ✖                   | ✔                          |
| Effet vitesse / météo            | ✔                   | ✔                          |
| Effet caractéristiques individus | ✔                   | ✔                          |
| Modèles statistiques             | post-hoc / mixtes   | poly / LOWESS              |
| Résultats dans la thèse          | Chapitre perception | Chapitre crossing / modèle |

---

# Exécuter les notebooks dans votre navigateur (JupyterLite)

## Notebook Expérience 1
[![Launch Exp1](https://img.shields.io/badge/Open%20Exp1%20Notebook-%F0%9F%93%88-blue?style=for-the-badge)](https://sandravict0r.github.io/pedestrian-crossing-prediction/lab/index.html?path=data_analysis_exp1.ipynb)

## Notebook Expérience 2

[![Launch Exp2](https://img.shields.io/badge/Open%20Exp2%20Notebook-%F0%9F%96%A5%EF%B8%8F-purple?style=for-the-badge)](https://sandravict0r.github.io/pedestrian-crossing-prediction/lab/index.html?path=data_analysis_exp2.ipynb)
---

# Pré-requis techniques

Les notebooks nécessitent :

```
pandas
numpy
matplotlib
seaborn
scipy
statsmodels
scikit_posthocs
sklearn
mysql-connector-python
```

Connexion MySQL gérée via :
`../data/database/db_utils.py`

