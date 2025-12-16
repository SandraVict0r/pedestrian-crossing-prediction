# **LOKI Dataset — Scripts d’annotation & résultats du modèle**

*(Ce dépôt ne contient pas les données brutes du dataset LOKI)*

Le **LOKI Dataset** (Honda Research Institute) est un dataset multimodal de scènes urbaines (RGB, LiDAR, annotations 2D/3D, odométrie) capturé à **5 FPS**, utilisé ici pour tester la **généralisation de notre modèle de prédiction de traversée piétonne**, entraîné en VR.

---

## 1. **Objectif du dossier**

Ce dossier rassemble :

* les **scripts d’annotation et de prétraitement** utilisés pour tester notre modèle sur le **dataset LOKI**,
* les **résultats finaux du modèle**, exportés sous forme de fichiers `.csv`,
  avec différentes **configurations décisionnelles** :

  * avec ou sans biais sécurité (SCBA),
  * avec ou sans règles supplémentaires sur la vitesse du véhicule.

⚠️ **Les données brutes du dataset LOKI ne sont pas incluses**, conformément aux conditions de diffusion du dataset original.

---

## 2. **Contenu réel du dossier**

```
LOKI/
 ├── model_resul_adj_LOKI_20kmh_rule/
 ├── model_resul_adj_LOKI_half_velocity/
 ├── model_resul_adj_LOKI_half_velocity_20kmh_rule/
 ├── model_resul_adj_LOKI_v2/
 │
 ├── model_result_no_adj_LOKI_20kmh_rule/
 ├── model_result_no_adj_LOKI_half_velocity/
 ├── model_result_no_adj_LOKI_half_velocity_20kmh_rule/
 ├── model_result_no_adj_LOKI_v2/
 │    └── (*.csv par piéton et par scénario)
 │
 ├── _weather_annotations.csv
 │
 ├── annotate_weather.py
 ├── crossing_decision.py
 ├── visualize_annpt.py
 └── README.md
```

---

## 3. **Ce qui est fourni / non fourni**

| Élément                           | Présent ? | Description                                        |
| --------------------------------- | --------- | -------------------------------------------------- |
| Scripts d’annotation LOKI         | ✔️        | Météo, export CSV, visualisation                   |
| Résultats finaux du modèle (.csv) | ✔️        | Plusieurs variantes (adj / no-adj, règles vitesse) |
| Données brutes LOKI               | ❌         | Non redistribuables                                |
| Images / LiDAR originaux          | ❌         | À télécharger via HRI                              |

---

## 4. **Comment obtenir le dataset LOKI (obligatoire pour réexécuter les scripts)**

Les données doivent être récupérées depuis la plateforme officielle :

🔗 **[https://usa.honda-ri.com/loki](https://usa.honda-ri.com/loki)**

L’accès nécessite généralement :

* une **demande académique**,
* une utilisation **non commerciale**.

Le dataset doit ensuite être organisé localement sous la forme :

```
loki_data/
 ├── scenario_000/
 │    ├── image_0000.png
 │    ├── label2d_0000.json
 │    ├── label3d_0000.txt
 │    ├── odom_0000.txt
 │    └── ...
 ├── scenario_001/
 └── ...
```

---

## 5. **Scripts fournis**

### **1) `annotate_weather.py` — Annotation manuelle de la météo**

Interface graphique (Streamlit) permettant d’annoter **la météo à l’échelle du scénario** :

* `clear`
* `rain`
* `night`
* `other`

Fonctionnement :

* une image aléatoire est affichée pour chaque scénario,
* un clic sur un bouton = sauvegarde immédiate + scénario suivant.

Lancement :

```bash
streamlit run annotate_weather.py
```

Sortie générée :

```
_weather_annotations.csv
```

Format :

| scenario_id | weather |
| ----------- | ------- |
| 12          | rain    |
| 13          | clear   |

---

### **2) `crossing_decision.py` — Export des résultats du modèle**

Script principal d’**évaluation du modèle sur LOKI**.

Il combine :

* météo (depuis `_weather_annotations.csv`),
* vitesse ego-vehicle (calculée via odométrie à 5 FPS),
* distance piéton–véhicule (3D),
* hauteur réelle du piéton (issue des annotations 3D),
* vérité terrain (`true_label`) issue des annotations d’actions LOKI.

Pour chaque piéton et chaque frame, le script exporte :

* la prédiction du modèle **avec ou sans biais sécurité (SCBA)**,
* selon plusieurs **règles décisionnelles**.

#### Variantes exportées

| Dossier                       | Description                           |
| ----------------------------- | ------------------------------------- |
| `model_resul_adj_LOKI_v2`     | Modèle avec SCBA                      |
| `model_result_no_adj_LOKI_v2` | Modèle sans SCBA                      |
| `*_half_velocity`             | Vitesse ego divisée par 2             |
| `*_20kmh_rule`                | Forçage crossing si vitesse < 20 km/h |
| `*_half_velocity_20kmh_rule`  | Combinaison des deux règles           |

Lancement :

```bash
python crossing_decision.py
```

---

### **3) `visualize_annpt.py` — Visualisation et inspection qualitative**

Viewer interactif (OpenCV) pour **inspecter visuellement** les décisions du modèle :

Affiche :

* boîtes 2D piétons & véhicules,
* distance 3D,
* hauteur piéton,
* vitesse ego,
* label GT,
* **optionnellement** les prédictions du modèle.

Commandes clavier :

| Touche  | Action                                |
| ------- | ------------------------------------- |
| `j / k` | frame ±1                              |
| `J / K` | frame ±10                             |
| `n / p` | scénario ±1                           |
| `m`     | activer / désactiver affichage modèle |
| `q`     | quitter                               |

Lancement :

```bash
python visualize_annpt.py
```

---

## 6. **Format des fichiers CSV exportés**

Chaque fichier correspond à **un piéton dans un scénario donné**.

Colonnes principales :

| Colonne           | Description                 |
| ----------------- | --------------------------- |
| `scenario_id`     | Identifiant du scénario     |
| `frame_id`        | Identifiant de la frame     |
| `pedestrian_id`   | ID du piéton                |
| `weather`         | Météo annotée               |
| `velocity_kmh`    | Vitesse du véhicule (km/h)  |
| `distance_m`      | Distance 3D véhicule–piéton |
| `real_height_cm`  | Taille réelle du piéton     |
| `true_label`      | Traversée réelle (GT)       |
| `predicted_label` | Sortie du modèle            |
| `adj`             | Mode SCBA activé ou non     |

---

## 7. **Reproduire l’évaluation (optionnel)**

1. Télécharger et organiser le dataset LOKI localement
2. Annoter la météo :

```bash
streamlit run annotate_weather.py
```

3. Exporter les décisions du modèle :

```bash
python crossing_decision.py
```

4. Vérifier visuellement :

```bash
python visualize_annpt.py
```

---

## 8. **Remarques importantes**

* Le modèle est **entraîné exclusivement en VR** ; LOKI est utilisé ici **sans fine-tuning**.
* L’objectif est une **évaluation de généralisation** en conditions réelles.
* Les chemins Windows (`E:\...`) doivent être adaptés à votre machine.
* Le framerate **5 FPS** est une hypothèse clé pour le calcul des vitesses.

---

Si tu veux, je peux maintenant :

* t’écrire la **phrase parfaite de méthode** pour la thèse (section *Real-world validation on LOKI*),
* ou te générer une **table récapitulative des variantes** (pour un papier IEEE / HRI).
