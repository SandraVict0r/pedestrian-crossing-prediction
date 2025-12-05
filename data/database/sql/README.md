#  `data/database/sql/` — README

##  Objectif du dossier

Ce dossier contient **tous les scripts SQL utilisés pour construire la base de données MySQL du projet**, nettoyer certaines données et générer le tableau final utilisé pour l'entraînement des modèles de prédiction du comportement de traversée.

Ces scripts sont exécutés :

1. **après la collecte des données brutes** (`data/raw/`)
2. **après l’insertion dans MySQL** via les scripts Python
3. **avant la génération des CSV propres** stockés dans `data/processed/`

---

##  Contenu du dossier

```
sql/
 ┣ bdd_creator.sql
 ┣ bad_datas_to_remove.sql
 ┗ model_datas_request.sql
```

---

# 1. `bdd_creator.sql` — Création de la base

Script **principal** pour initialiser la base de données :

* crée la base `main_experiment`

* crée les tables :

  * `Participant`
  * `Weather`
  * `Position`
  * `Velocity`
  * `DistanceDisappearance`
  * `Perception`
  * `Crossing`

* insère les paramètres fixes :

  * conditions météo (`clear`, `night`, `rain`)
  * positions (0, 1, 2)
  * vitesses + catégories (`low`, `medium`, `high`)
  * distances + catégories (`pair`, `odd`)

**Ce script doit être exécuté en premier lors d’une reconstruction complète.**

---

# 2. `bad_datas_to_remove.sql` — Suppression des outliers

Ce script retire **les participants/essais identifiés comme outliers**
(ex. enregistrements corrompus, comportement hors protocole, données incomplètes).

Il supprime :

* les entrées correspondantes dans `Perception`
* les entrées correspondantes dans `Crossing`
* le participant dans `Participant`

**Important : ce script est indispensable pour garantir que seuls les essais valides sont conservés.**

---

# 3. `model_datas_request.sql` — Construction du dataset ML

Script qui produit une **vue tabulaire complète**, incluant :

* informations participant
* distances perçues (regroupées : `D_low`, `D_med`, `D_high`)
* distances réelles
* vitesses (exp1 & exp2)
* catégories de conditions expérimentales
* variables dérivées
* **moyennes des Safety Distances** (par vitesse / météo / participant)

Ce script génère **le tableau final utilisé pour entraîner les modèles ML**.

---

##  Export CSV

Une fois la requête exécutée, la table finale doit être exportée en CSV dans :

[`data/processed/`](../../processed/)

C’est ici que se trouvent **tous les jeux de données propres et prêts pour l’entraînement**.

---

#  Dépendances

Ces scripts SQL fonctionnent conjointement avec les scripts Python du dossier :

```
data/database/python/
```

Les scripts Python :

* lisent les données brutes dans `data/raw/`
* extraient les distances perçues (exp1)
* génèrent les séquences de crossing (exp2)
* insèrent toutes les valeurs expérimentales dans MySQL via `db_utils.py`

Ils doivent être exécutés **juste après `bdd_creator.sql`**.

---

#  Pipeline d’utilisation (ordre recommandé)

1. **Créer la base**

   ```
   bdd_creator.sql
   ```

2. **Insérer les données**

   ```
   python insert_participant_data_to_mysql.py
   python insert_perception_experiment_data_to_mysql.py
   python insert_crossing_experiment_data_to_mysql.py
   ```

3. **Supprimer les outliers**

   ```
   bad_datas_to_remove.sql
   ```

4. **Générer la table finale**

   ```
   model_datas_request.sql
   ```

5. **Exporter le résultat**

   * via MySQL Workbench
   * ou via un script Python utilisant pandas
     dans : `data/processed/`

