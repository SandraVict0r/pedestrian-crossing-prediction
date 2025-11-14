
# 📁 `data/database/` — README (VERSION MYSQL WORKBENCH)

## 🎯 Objectif du dossier

Ce dossier contient **tous les éléments nécessaires pour créer et alimenter la base de données MySQL du projet** :

* scripts SQL
* scripts Python d’insertion des données VR
* fichier `.env` pour la connexion
* procédure complète via **MySQL Workbench**

---

# 🛠️ 1. Installer MySQL + MySQL Workbench

Télécharger MySQL (inclut Workbench) :
🔗 [https://dev.mysql.com/downloads/windows/installer/](https://dev.mysql.com/downloads/windows/installer/)
(Sélectionner *MySQL Installer Community*)

Lors de l’installation :

* créer un mot de passe pour l’utilisateur `root`
* installer **MySQL Server** + **MySQL Workbench**

Pour lancer Workbench :
👉 Ouvrir *MySQL Workbench*
👉 Cliquer sur la connexion locale (ex : "Local instance MySQL80")

---

# 🗄️ 2. Créer la base de données dans Workbench

Dans MySQL Workbench :

1. Ouvrir un nouvel onglet SQL (icône *Create new SQL tab*)
2. Copier :

```sql
CREATE DATABASE main_experiment;
```

3. Cliquer sur **⚡ Execute**

La base apparaît dans l’onglet de gauche sous "Schemas".

---

# 🔐 3. Configurer le fichier `.env`

Le fichier `.env` (dans `data/database/python/.env`) contient les identifiants de connexion utilisés par les scripts Python.

Format :

```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=VOTRE_MOT_DE_PASSE
DB_NAME=main_experiment
```

⚠️ **NE JAMAIS le mettre sur GitHub.**
Ajouter `.env` au `.gitignore`.

---

# 📂 4. Structure du dossier

```
database/
 ┣ python/   → scripts d’insertion des données VR
 ┣ sql/      → scripts SQL
 ┗ README.md
```

### 🔗 Liens vers les README détaillés

* 📦 Scripts Python → [`python/README.md`](python/README.md)
* 🗄️ Scripts SQL → [`sql/README.md`](sql/README.md)

---

# 🚀 5. Pipeline d’utilisation (100% MySQL Workbench)

## 🔹 Étape 1 — Créer les tables

Dans Workbench :

1. Ouvrir `data/database/sql/bdd_creator.sql`
2. Exécuter le script avec le bouton **⚡ Execute**

Ce script :

* crée toutes les tables
* insère les paramètres fixes
* prépare la base à recevoir les données VR

---

## 🔹 Étape 2 — Vérifier le `.env`

S’assurer que :

```
data/database/python/.env
```

contient bien les infos de ta connexion Workbench.

---

## 🔹 Étape 3 — Importer les participants (Python)

Dans VS Code ou un terminal :

```
python insert_participant_data_to_mysql.py
```

Le script utilise `.env` pour se connecter à MySQL Workbench.

---

## 🔹 Étape 4 — Importer les données VR Exp1 (Perception)

```
python insert_perception_experiment_data_to_mysql.py
```

Ce script parcourt `data/raw/.../exp1/`.

---

## 🔹 Étape 5 — Importer les données VR Exp2 (Crossing)

```
python insert_crossing_experiment_data_to_mysql.py
```

---

## 🔹 Étape 6 — Nettoyer les outliers

Dans Workbench :

1. Ouvrir `bad_datas_to_remove.sql`
2. ⚡ Exécuter

Ce script supprime les participants/essais identifiés comme outliers.

---

## 🔹 Étape 7 — Générer le dataset final

Toujours dans Workbench :

1. Ouvrir `model_datas_request.sql`
2. ⚡ Exécuter

Le script génère la table / vue finale.

Ensuite exporter les résultats :

👉 **File ▸ Export Results**
👉 Format : **CSV**
👉 Destination : `data/processed/`

---

# 📌 Notes importantes

* Le `.env` n’est **jamais** partagé
* MySQL Workbench est utilisé pour **toutes** les exécutions SQL
* Les scripts Python doivent être exécutés **après** la création des tables
* `data/processed/` contient **tous les CSV finaux**, y compris ceux utilisés pour le modèle ML
