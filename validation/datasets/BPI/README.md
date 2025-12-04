
# 📘 **BPI_Dataset — Scripts d’annotation & résultats du modèle**

*(Ce dépôt ne contient pas les données brutes du BPI Dataset)*

## 1. 🎯 **Objectif du dossier**

Ce dossier rassemble :

* les **scripts d’annotation et de prétraitement** utilisés pour tester notre modèle de comportement piéton sur le **BPI Dataset**,
* ainsi que **les fichiers annotés finaux** générés par nos scripts (avec et sans ajustement SCBA, avec et sans intention).

- **Les données brutes du BPI Dataset ne sont pas incluses**, conformément à la licence du projet original.
- Ce dossier fournit uniquement **les sorties finales**, prêtes à être utilisées pour la validation de notre modèle dans la thèse.

---

# 2. 📦 Contenu réel du dépôt

```
BPI/
 ├── extracted_csvfiles_annotated_adj_false/
 ├── extracted_csvfiles_annotated_adj_false_intention/
 ├── extracted_csvfiles_annotated_adj_true/
 ├── extracted_csvfiles_annotated_adj_true_intention/
 │    └── (*.csv annotés)
 │
 ├── annotate_crossing.py
 ├── annotate_crossing_intention.py
 ├── annotate_weather_gui.py
 ├── ped_height.py
 ├── visualize_crossing.py
 └── README.md
```

### **Ce qui est fournis**

| Élément                                         | Présent ? | Description                                                           |
| ----------------------------------------------- | --------- | --------------------------------------------------------------------- |
| Scripts d’annotation                            | ✔️        | Utilisés pour générer GT, intentions, météo, etc.                     |
| Sorties `.csv` annotées                         | ✔️        | Résultats finaux du modèle (adj / no-adj, intention / pas intention). |
| Données brutes BPI                              | ❌         | Trop volumineuses + non redistribuables.                              |
| CSV fusionnés d’origine (`extracted_csvfiles/`) | ❌         | Fournis dans le dépôt officiel BPI, non ici.                          |

---

# 3. 📥 Comment obtenir les données du BPI Dataset (obligatoire si vous voulez réexécuter les scripts)

Les données originales doivent être téléchargées depuis le dépôt officiel :

🔗 **[https://github.com/wuhaoran111/BPI_Dataset](https://github.com/wuhaoran111/BPI_Dataset)**

Vous y trouverez :

* `raw_data/data_2018-...`
* scripts d’extraction pour produire
  `extracted_csvfiles/*.csv` et `cyclist_extracted_csvfiles/*.csv`

💡 *Ces CSV sont utilisés comme entrée par nos scripts d’annotation.*

---

# 4. 📂 Organisation attendue pour réexécuter le pipeline

Si vous souhaitez reproduire les annotations, vous devez reconstruire localement la structure suivante :

```
BPI_Dataset_local/
 ├── raw_data/
 │    ├── data_2018-01-28-14-57-55/
 │    ├── data_2018-01-28-14-58-46/
 │    └── data_2018-01-28-15-00-12/
 │
 ├── extracted_csvfiles/
 │    ├── A02.csv
 │    ├── A09.csv
 │    └── ...
 │
 ├── scripts/ (facultatif)
 │
 └── (tes scripts)
```

Ensuite, les scripts présents dans TON repo peuvent être utilisés pour générer les fichiers annotés.

---

# 5. 🧰 Description des scripts fournis

### **1) `annotate_crossing.py`**

Annoter automatiquement :

* labels `true_label` (sur la route ou non via LiDAR),
* prédictions du modèle,
* hauteur piéton (estimée via LiDAR),
* vitesse véhicule & distance,
* version ajustée et non ajustée du modèle (`adj=True/False`).

Produit automatiquement :

```
extracted_csvfiles_annotated_adj_false/
extracted_csvfiles_annotated_adj_true/
```

---

### **2) `annotate_crossing_intention.py`**

Ajoute une estimation **d’intention de traverser**, basée sur :

* l’orientation de la tête / corps (fenêtres angulaires),
* la position relative dans le LiDAR.

Produit :

```
extracted_csvfiles_annotated_adj_false_intention/
extracted_csvfiles_annotated_adj_true_intention/
```

---

### **3) `annotate_weather_gui.py`**

Interface graphique (Matplotlib) permettant de **corriger ou ajouter manuellement** les labels météo :

* clear
* rain
* night

Affiche l’image associée à chaque frame.

---

### **4) `ped_height.py`**

Estimation robuste de la hauteur piéton :

* via LiDAR (filtrage spatial + percentile),
* fallback image (si keypoints et focale disponibles).

---

### **5) `visualize_crossing.py`**

Détecte les changements de signe de `lidar_pc_lat`, donc les passages de trottoir.

Affiche :

* temps de l’événement,
* coordonnées LiDAR,
* images avant / après le crossing.

---

# 6. 🧪 Reproduire l’annotation (optionnel)

Une fois les données et CSV d’origine récupérés :

### 1) Annoter crossing

```
python annotate_crossing.py
```

### 2) Annoter intention

```
python annotate_crossing_intention.py
```

### 3) Annoter météo (manuel)

```
python annotate_weather_gui.py --input-dir extracted_csvfiles --images raw_data/.../image
```

### 4) Visualiser événements crossing

```
python visualize_crossing.py
```

---

# 7. 📝 Format des fichiers annotés

Chaque `.csv` contient :

| Colonne             | Description                      |
| ------------------- | -------------------------------- |
| `true_label`        | Crossing détecté via LiDAR       |
| `predicted_label`   | Sortie du modèle                 |
| `weather`           | Label météo                      |
| `ped_height_cm`     | Hauteur estimée                  |
| `vehicle_speed_kmh` | Vitesse véhicule                 |
| `distance_m`        | Distance véhicule–piéton         |
| `adj`               | Mode ajusté (SCBA) activé ou non |

---