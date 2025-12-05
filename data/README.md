# *Pedestrian-Crossing Behavior – Data Pipeline*

### **README global du dossier `data/`**

Ce dossier contient **toutes les données utilisées dans la thèse**, ainsi que l’ensemble des scripts nécessaires pour :

* stocker
* structurer
* nettoyer
* transformer
* exporter
  les données finales prêtes pour la modélisation.

Il couvre toute la chaîne :

- **VR Raw Data**
- **Insertion dans MySQL**
- **Nettoyage + Agrégation SQL**
- **Export CSV final**
- **Utilisation dans le dossier `model/`**

Ce README présente une vue d’ensemble et redirige vers la documentation détaillée de chaque sous-dossier.

---

# **SOMMAIRE**

1. [Objectif général](#objectif-général)
2. [Architecture complète du dossier](#architecture-complète-du-dossier)
3. [Description des sous-dossiers](#description-des-sous-dossiers)
4. [Pipeline global des données (raw → processed)](#pipeline-global-des-données-raw--processed)
5. [Relations entre données VR, questionnaires et MySQL](#relations-entre-données-vr-questionnaires-et-mysql)
6. [Vue globale : liens vers tous les README internes](#vue-globale--liens-vers-tous-les-readme-internes)

---


# **Architecture complète du dossier**

```
data/
 ┣ database/           → Base SQL + scripts Python
 ┣ processed/          → CSV propres et prêts pour la modélisation
 ┣ questionnaires/     → Formulaires bruts des participants
 ┣ raw/                → Données VR brutes (Exp1 & Exp2)
 ┗ README.md           → (ce fichier)
```

---

# **Description des sous-dossiers**

---

## 1️ `data/raw/` — Données VR brutes

Contient **tous les enregistrements VR** : `cars.csv`, `peds.csv`, `gaze.csv`,
organisés par participant / expérience / trial.

 Documentation : [`raw/README.md`](raw/README.md)

---

## 2️ `data/questionnaires/` — Formulaires bruts

Regroupe :

* **consentement**
* **informations personnelles**
* **questionnaire de perception**

Documentation : [`questionnaires/README.md`](questionnaires/README.md)

 **Note :**
`participant.csv` = **fusion** automatique de `perception_form.csv` + `consent_form.csv`.

---

## 3 `data/database/` — Pipeline SQL complet

Ce dossier contient :

* scripts SQL : création + nettoyage + extraction
* scripts Python : insertion VR + participant + perception
* fichier `.env` (non versionné)

Documentation : [`database/README.md`](database/README.md)

Sous-documents :

* Python : [`database/python/README.md`](database/python/README.md)
* SQL : [`database/sql/README.md`](database/sql/README.md)

---

## 4 `data/processed/` — CSV propres pour la modélisation

Contient les **9 jeux de données finaux**, séparés par :

* météo (`clear`, `rain`, `night`)
* vitesse (`low`, `medium`, `high`)

Documentation : [`processed/README.md`](processed/README.md)

Ces fichiers alimentent directement le dossier : `model/`

---

# **Pipeline global des données **

```
data/raw/
       ↓ parsing
database/python/*.py
       ↓ insertion SQL
database/sql/bdd_creator.sql
       ↓ nettoyage
database/sql/bad_datas_to_remove.sql
       ↓ agrégation
database/sql/model_datas_request.sql
       ↓ export MySQL Workbench
data/processed/*.csv
       ↓
model/  (entraînement ML)
```

---

# **Relations entre données VR, questionnaires et MySQL**

### • `questionnaires/`

→ crée **participant.csv**, qui alimente la table SQL `Participant`

### • `raw/`

→ fourni les fichiers VR bruts pour Exp1 et Exp2

### • `database/python/`

→ lit `raw/` et `participant.csv`
→ insère dans les tables SQL (`Participant`, `Perception`, `Crossing`, etc.)

### • `database/sql/`

→ nettoie la base
→ assemble toutes les tables en une vue finale

### • `processed/`

→ export CSV final
→ utilisé dans `model/`

---

#  **Vue globale : liens vers tous les README internes**

| Dossier            | Documentation                                               |
| ------------------ | ----------------------------------------------------------- |
| VR Brutes          |  [`raw/README.md`](raw/README.md)                         |
| Questionnaires     |  [`questionnaires/README.md`](questionnaires/README.md)   |
| Base SQL globale   |  [`database/README.md`](database/README.md)               |
| Scripts Python SQL |  [`database/python/README.md`](database/python/README.md) |
| Scripts SQL        |  [`database/sql/README.md`](database/sql/README.md)       |
| CSV finaux         |  [`processed/README.md`](processed/README.md)             |

