# `data/raw/` — README


Le dossier **`data/raw/`** contient **l’ensemble des données brutes collectées dans l’environnement VR** pour les deux expériences du protocole :

* **Expérience 1 (Exp1)** : *Perception de distance et de vitesse*
* **Expérience 2 (Exp2)** : *Décision de traversée / Crossing behavior*

Ces fichiers proviennent directement de l’enregistrement Unreal Engine / VR et n’ont subi **aucune modification**.
Ils sont utilisés :

* par les scripts Python d’insertion (`data/database/python/`)
* pour reconstruire les séquences d’expérimentation
* avant le nettoyage et l’intégration en base SQL (`data/database/sql/`)

---

# Structure générale

Chaque participant possède un dossier nommé :

```
XXX_NN/
```

où `NN` est un identifiant interne **qui ne correspond pas nécessairement** au numéro de participant dans le questionnaire.

Exemple :

```
data/raw/
 ┣ XXX_24/
 ┃ ┣ exp1/
 ┃ ┃ ┣ 1/
 ┃ ┃ ┃ ┣ cars.csv
 ┃ ┃ ┃ ┣ gaze.csv
 ┃ ┃ ┃ ┗ peds.csv
 ┃ ┃ ┣ 2/
 ┃ ┃ ┃ ┗ ...
 ┃ ┃ ┗ ... (jusqu'à 27)
 ┃ ┣ exp2/
 ┃ ┃ ┣ 1/
 ┃ ┃ ┃ ┣ cars.csv
 ┃ ┃ ┃ ┣ gaze.csv
 ┃ ┃ ┃ ┗ peds.csv
 ┃ ┃ ┗ ... (27 essais)
 ┃ ┣ participant_? _commands_exp1.xlsx
 ┃ ┗ participant_? _commands_exp2.xlsx
```

* **Toujours deux expériences : `exp1` et `exp2`**
* **Toujours 27 essais chacun**
* **Chaque essai = 3 fichiers CSV**
* **Les fichiers `.xlsx` ne portent pas le même identifiant que le dossier `XXX_NN`**

---

# Description des fichiers expérimentaux

## 1️ `cars.csv` — Trajectoire du véhicule

Contient l’état de la voiture à chaque frame.

| Colonne                   | Description                           |
| ------------------------- | ------------------------------------- |
| `Time`                    | Timestamp dans la simulation          |
| `Time_estimated`          | Estimation Unreal Engine (inutilisée) |
| `X_pos`, `Y_pos`, `Z_pos` | Position réelle du véhicule           |
| `X_est`, `Y_est`, `Z_est` | Estimation interne (peut rester à 0)  |
| `X_vel`, `Y_vel`, `Z_vel` | Vitesse instantanée                   |
| `Crossing_value`          | Booléan interne (souvent 0)           |


---

## 2 `gaze.csv` — Données du regard

Contient les données du suivi oculaire du participant.

| Colonne                            | Description                                       |
| ---------------------------------- | ------------------------------------------------- |
| `Time`                             | Timestamp                                         |
| `X_origin`, `Y_origin`, `Z_origin` | Position 3D de l’origine du regard (caméra VR)    |
| `X_direction`, ...                 | Vecteur direction du regard                       |
| `X_fixation`, ...                  | Point de fixation estimé (souvent vide si stable) |
| `Confidence`                       | Score de confiance [0–1]                          |


---

## 3 `peds.csv` — Position du piéton

Données de déplacement du participant dans l’environnement VR.

| Colonne                   | Description                  |
| ------------------------- | ---------------------------- |
| `Time`                    | Timestamp                    |
| `X_pos`, `Y_pos`, `Z_pos` | Position 3D du piéton        |
| `X_rot`, `Y_rot`, `Z_rot` | Orientation (yaw/pitch/roll) |


---

## 4 Fichiers `.xlsx` — Log des commandes Exp1 / Exp2

Deux fichiers par participant :

```
participant_<id>_commands_exp1.xlsx
participant_<id>_commands_exp2.xlsx
```

Contiennent :

| Colonne                                 | Description                                     |
| --------------------------------------- | ----------------------------------------------- |
| `Participant`                           | identifiant réel du participant                 |
| `Position (-pos)`                       | position du véhicule                            |
| `Velocity (-v)`                         | vitesse du véhicule                             |
| `Distance (-d)`                         | distance initiale                               |
| `Weather`                               | météo (`clear`, `night`, `rain`)                |
| `Rain (-r)`, `Cloud (-c)`, `Light (-l)` | flags environnement                             |
| `Command`                               | ligne de commande utilisée pour générer l’essai |

**Utilisation** :

* récupération des paramètres expérimentaux
* insertion dans la table SQL `DistanceDisappearance` & `Velocity`
* cohérence exp1/exp2 pour chaque trial

---

# Pipeline d’utilisation des fichiers bruts

### Ces fichiers sont consommés par :

### 1. Les scripts Python :

[`data/database/python/`](../database/python/README.md)

* insertion participants → `Participant`
* reconstruction perception exp1 → `Perception`
* reconstruction crossing exp2 → `Crossing`

### 2. Les scripts SQL :

[`data/database/sql/`](../database/sql/README.md)

* nettoyage (`bad_datas_to_remove.sql`)
* génération du dataset final ML (`model_datas_request.sql`)

### 3. Export du dataset final vers :

`data/processed/` (CSV propres)

---

#  Recommandations

* **Ne jamais modifier** les fichiers dans `raw/`
* Conserver la structure folder/participant/exp/trial exactement
* Vérifier que chaque participant a bien :
  * 27 essais exp1
  * 27 essais exp2
  * 2 fichiers command `.xlsx`
* Utiliser `processed/` pour toute version nettoyée
