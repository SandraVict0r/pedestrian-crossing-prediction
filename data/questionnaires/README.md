# `data/questionnaires/` — README

## Objectif du dossier

Ce dossier contient **les trois fichiers de questionnaires nécessaires pour enrichir la base MySQL** avec les informations sur les participants :

* informations démographiques
* données subjectives
* consentement éclairé

Ces fichiers sont les **versions brutes**, exportées depuis les formulaires utilisés pendant la collecte.
Ils sont ensuite lus et insérés en base SQL par les scripts :

[`data/database/python/`](../database/python/README.md)

---

# Contenu du dossier

```
questionnaires/
 ┣ participant.csv
 ┣ perception_form.csv
 ┗ consent_form.csv
```

---

#  1. `participant.csv`

Contient **les informations principales de chaque participant**, utilisées pour remplir la table SQL `Participant`.

###  Colonnes réelles :

| Colonne            | Description                                                                                   |
| ------------------ | --------------------------------------------------------------------------------------------- |
| **Participant**    | Identifiant interne                                                                           |
| **Age**            | Âge du participant                                                                            |
| **Sex**            | Man / Woman                                                                                   |
| **Height**         | Taille en cm                                                                                  |
| **Driver_license** | TRUE/FALSE                                                                                    |
| **Scale**          | Score indiquant si le participant pense qu’il aurait agi de la même façon en situation réelle |

---

# 2. `perception_form.csv`

Court questionnaire rempli avant Exp1, portant sur une **évaluation subjective**.

| Colonne         | Description                                                             |
| --------------- | ----------------------------------------------------------------------- |
| **Participant** | Identifiant interne                                                     |
| **Scale**       | Score indiquant si le participant pense qu’il aurait agi pareil en réel |
| **License**     | TRUE/FALSE (permis de conduire)                                         |

---

# 3. `consent_form.csv`

Contient **le consentement éclairé** et quelques métadonnées.

| Colonne            | Description                      |
| ------------------ | -------------------------------- |
| **Participant**    | Identifiant interne              |
| **Heure de début** | Timestamp du début du formulaire |
| **Sex:**           | Sexe (Man/Woman)                 |
| **Age:**           | Âge                              |
| **Height:**        | Taille en cm                     |

---

## Relation entre les fichiers (fusion)

Les fichiers bruts :

* `perception_form.csv`
* `consent_form.csv`

contiennent chacun une partie des informations du participant.

Le fichier :

### **`participant.csv` est la version fusionnée et normalisée**, utilisée comme **référence unique** pour alimenter la base SQL.

Il combine :

* infos démographiques du consentement
* score de vraisemblance + permis (perception)
* identifiant du participant

Ce fichier est celui réellement utilisé par :
 `insert_participant_data_to_mysql.py`

---

# Pipeline global

1. Le participant remplit les formulaires
2. Les scripts Python extraient et valident les colonnes
3. `participant.csv` sert de base d’insertion dans SQL
4. Les données VR de `raw/` se rattachent automatiquement aux participants
5. Le dataset final est généré via `model_datas_request.sql`

---

# Notes importantes

* Ne pas modifier manuellement les CSV
* Garder les fichiers tels qu’exportés
* Les transformations doivent être faites dans Python ou SQL
* Ce dossier ne doit contenir **que les questionnaires bruts**

