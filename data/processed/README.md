# `data/processed/` — README

## Objectif du dossier

Ce dossier contient **les jeux de données nettoyés, structurés et prêts pour l’analyse ou l’entraînement des modèles**.

Les CSV présents ici proviennent :

1. de la reconstruction VR → SQL,
2. du nettoyage (outliers),
3. de la requête finale `model_datas_request.sql`.

Ils constituent **la source unique fiable** pour toute analyse scientifique.

---

#  Contenu

```
processed/
 ┣ clear_low.csv
 ┣ clear_medium.csv
 ┣ clear_high.csv
 ┣ rain_low.csv
 ┣ rain_medium.csv
 ┣ rain_high.csv
 ┣ night_low.csv
 ┣ night_medium.csv
 ┗ night_high.csv
```

Chacun de ces fichiers représente :

* une **condition météo** (`clear`, `rain`, `night`)
* × une **catégorie de vitesse** (`low`, `medium`, `high`)
 **Chaque CSV regroupe tous les participants + tous les essais valides** correspondant à cette condition.

---

# Utilisation des fichiers

Ces CSV sont utilisés pour :

### **Modélisation en Python (entraînement + évaluation)**
 Les scripts de modélisation se trouvent dans :
 [`model/`](../../model/)

### Analyses comportementales

Distances perçues, distances réelles, TTC estimé, Safety Margins…

### Visualisations scientifiques

Boîtes à moustaches, distributions, heatmaps, analysis per météo / vitesse…

---

# Notes importantes

* Les fichiers ici sont **propres, complets et prêts à être utilisés**.
* **Aucune donnée brute** ne doit être placée ici.
* Le nettoyage ou la transformation **se fait ailleurs**, pas dans ce dossier.
* Les fichiers sont compatibles directement avec :

  ```python
  import pandas as pd
  df = pd.read_csv("data/processed/clear_low.csv")
  ```

