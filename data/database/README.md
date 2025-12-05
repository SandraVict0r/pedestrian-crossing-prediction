# `data/database/` — README

## Objectif du dossier

Le dossier **`data/database/`** regroupe tous les éléments nécessaires pour :

1. **Construire la base MySQL** utilisée comme structure intermédiaire entre les données brutes et les données processed.
2. **Insérer automatiquement** les données issues des expériences VR (Exp1 & Exp2) ainsi que les informations du questionnaire.
3. **Nettoyer la base** (suppression d’outliers).
4. **Générer la table finale** utilisée pour produire les CSV propres dans `data/processed/`.

---

##  Structure du dossier

```
database/
 ┣ python/   → scripts d’insertion (participants, exp1, exp2)
 ┣ sql/      → scripts SQL (création, nettoyage, extraction finale)
 ┗ README.md ← (ce fichier)
```

###  Sous-README détaillés

*  Scripts Python : [`python/README.md`](./python/README.md)
*  Scripts SQL : [`sql/README.md`](./sql/README.md)


##  Modèle conceptuel de données (UML)

La base MySQL utilisée pour structurer les données VR repose sur un modèle relationnel simple, organisé autour des entités suivantes :

* **Participant**
* **Perception** (Exp1)
* **Crossing** (Exp2)
* **DistanceDisappearance** (paramètres exp1)
* **Velocity** (vitesses + catégories)
* **Weather** (conditions météo)
* **Position** (positions relatives dans l’environnement)

Les relations assurent la cohérence entre les données brutes, les paramètres expérimentaux et les observations des participants.

###  **Diagramme UML de la base MySQL**

![UML schema of MySQL database](/data/img/uml_diagram.png)

Ce diagramme montre :

* les **tables** et leurs **attributs principaux**,
* les relations **1 → *** entre participant ↔ essais,
* le lien bidirectionnel entre les expériences (Perception, Crossing) et les paramètres expérimentaux (Weather, Velocity, DistanceDisappearance, Position),
* la structure qui permet d'agréger l’ensemble des données dans la requête finale (`model_datas_request.sql`).

---

#  Rôle des sous-dossiers

##  `python/` — Insertion automatique des données

Ce dossier contient :

* `db_utils.py` — connexion MySQL + helpers
* `insert_participant_data_to_mysql.py`
* `insert_perception_experiment_data_to_mysql.py`
* `insert_crossing_experiment_data_to_mysql.py`

Ces scripts :

* lisent les fichiers de `data/raw/`
* reconstruisent les essais exp1/exp2
* alimentent les tables : `Participant`, `Perception`, `Crossing`, etc.

---

##  `sql/` — Construction + nettoyage + extraction finale

Contient :

* `bdd_creator.sql` — création complète de la base + tables fixes
* `bad_datas_to_remove.sql` — suppression des outliers
* `model_datas_request.sql` — génération du tableau final pour `processed/`

---

#  Pipeline d’utilisation (vue d’ensemble)

1. **Créer la base** via `bdd_creator.sql`
2. **Configurer `.env`** (connexion MySQL)
3. **Insérer les données** avec les scripts Python
4. **Nettoyer les données** (`bad_datas_to_remove.sql`)
5. **Générer la table finale** (`model_datas_request.sql`)
6. **Exporter en CSV** dans `data/processed/`

Les instructions détaillées sont disponibles dans les sous-README.

---

#  Notes

* `.env` ne doit jamais être versionné.
* L’exécution SQL peut se faire via MySQL Workbench ou CLI.
* Toutes les transformations doivent passer par la base -> ne **jamais modifier `raw/`**.
* Les CSV finaux sont produits dans `data/processed/`.

