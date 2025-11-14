# 📁 `data/database/python/` — README

## 🎯 Objectif du dossier

Ce dossier contient l’ensemble des **scripts Python utilisés pour insérer les données expérimentales** (VR exp1 & exp2, participants, perceptions et crossing sequences) dans la base MySQL construite via les scripts SQL du dossier parent.

Ces scripts constituent **le pipeline d’import automatique** des données brutes (`data/raw/`) vers la base `main_experiment`.

---

## 📂 Contenu du dossier

```
python/
 ┣ .env
 ┣ db_utils.py
 ┣ insert_crossing_experiment_data_to_mysql.py
 ┣ insert_participant_data_to_mysql.py
 ┗ insert_perception_experiment_data_to_mysql.py
```

---

# 1. `.env` — Paramètres de connexion

Ce fichier contient les **informations de connexion MySQL**, typiquement :

```
DB_HOST=...
DB_PORT=3306
DB_USER=...
DB_PASSWORD=...
DB_NAME=main_experiment
```

⚠️ **Ne jamais versionner ce fichier sur GitHub** (sécurité).
Ajouter `.env` au `.gitignore`.

---

# 2. `db_utils.py` — Fonctions utilitaires

Ce module regroupe toutes les fonctions partagées :

* ouverture/fermeture de connexion MySQL
* exécution de requêtes
* insertion sécurisée (prévention injection SQL)
* logs d’état
* helpers pour les scripts d’import

Tous les autres scripts utilisent ses fonctions pour standardiser les interactions avec MySQL.

---

# 3. `insert_participant_data_to_mysql.py` — Import des participants

Script d’insertion des données du questionnaire `participant.csv` (dans `data/questionnaires/`).

Il :

* lit les données brutes du questionnaire
* vérifie les entrées (types, valeurs manquantes)
* alimente la table `Participant`
* crée les relations nécessaires avec les tables paramétriques

C’est **le premier script à exécuter** après `bdd_creator.sql`.

---

# 4. `insert_perception_experiment_data_to_mysql.py` — Import exp1 (perception)

Ce script traite les données de l’expérience VR **Exp1 (perception)**, présentes dans :

```
data/raw/XXX_XX/exp1/<trial_id>/{cars.csv, gaze.csv, peds.csv}
```

Il :

* lit les fichiers bruts de chaque trial
* reconstruit la séquence expérimentale
* calcule les distances perçues (selon ton protocole exp1)
* alimente la table `Perception`

Ce script doit être lancé **après l’import des participants**.

---

# 5. `insert_crossing_experiment_data_to_mysql.py` — Import exp2 (crossing)

Ce script traite les données de l’expérience **Exp2 (crossing)**, donnant la table `Crossing`.

Il :

* lit les fichiers bruts exp2 dans `data/raw/…`
* reconstruit les épisodes de traversée
* génère les séquences nécessaires (temps, vitesse, distances, décisions)
* insère les lignes correspondantes dans la table `Crossing`

Il doit être exécuté **après** `insert_perception_experiment_data_to_mysql.py`.

---

# ▶️ Pipeline d’exécution recommandé

1. **Créer la base**

   ```
   mysql < bdd_creator.sql
   ```

2. **Importer les participants**

   ```
   python insert_participant_data_to_mysql.py
   ```

3. **Importer exp1 (perception)**

   ```
   python insert_perception_experiment_data_to_mysql.py
   ```

4. **Importer exp2 (crossing)**

   ```
   python insert_crossing_experiment_data_to_mysql.py
   ```

5.  Nettoyer les outliers via

   ```
   mysql < bad_datas_to_remove.sql
   ```

6. Générer le dataset final via

   ```
   mysql < model_datas_request.sql
   ```
