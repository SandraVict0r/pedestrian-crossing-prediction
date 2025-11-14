# 📊 Analysis – README

Ce dossier contient les outils d’analyse des deux expériences VR :

* **Expérience 1 – TTC Estimation experiment**
* **Expérience 2 – Crossing Decision experiment**

Les deux outils sont développés sous **Streamlit** et permettent de visualiser les résultats immédiatement après la passation d’un participant à partir des fichiers CSV générés par Unreal Engine.

---

# 📁 Structure

```
analysis/
│
├── analyze_exp1_log.py   # Analyse TTC (Expérience 1)
└── analyze_exp2_log.py   # Analyse Crossing/Distance + EOCI (Expérience 2)
```

---

# ▶️ Prérequis

Installer les dépendances :

```bash
pip install streamlit plotly pandas numpy openpyxl
```

---

# ▶️ Lancer une analyse

## **Expérience 1**

```bash
streamlit run analyze_exp1_log.py
```

## **Expérience 2**

```bash
streamlit run analyze_exp2_log.py
```

---

# 📂 Organisation attendue du dossier Logs

Ces scripts analysent les résultats générés par Unreal Engine :

```
C:\Users\<USER>\CarlaUE5\Unreal\CarlaUnreal\Logs\
```

Chaque essai génère un dossier numéroté :

```
Logs/
│
├── exp1.xlsx   # ou exp2.xlsx
├── 1/
│   ├── cars.csv
│   ├── peds.csv
│   └── gaze.csv   # exp1 uniquement
├── 2/
│   ├── cars.csv
│   ├── peds.csv
│   └── gaze.csv
...
```

---

# 🧪 Description des outils

## ✔️ **analyze_exp1_log.py** — TTC Estimation Experiment

Analyse :

* l’instant précis de disparition de la voiture
* le moment du snap (trigger)
* le temps perçu vs le temps réel
* erreurs : biais, MAE, RMSE, % correct

Graphiques :

* perçu vs réel
* histogramme des erreurs
* boxplots météo / vitesse / distance

---

## ✔️ **analyze_exp2_log.py** — Crossing Decision Experiment

Analyse :

* la distance de sécurité (moment du passage 1→0)
* l’**EOCI** : Estimated Opportunity to Cross Interval
* courbes crossing/distance par position et météo

Graphiques :

* barplots EOCI par vitesse et météo
* heatmaps vitesse × météo
* courbes crossing vs distance

---

# 🧷 Notes importantes

* Les scripts ne modifient pas les données.
* L’utilisateur doit avoir correctement sauvegardé chaque trial (`S`).
* Les CSV doivent respecter le format produit par Unreal Engine → `RWText`.

---

# 🔗 Documentation liée

* 📘 **Protocole complet des expériences**
  → [unreal_project/experience_flow.md](../unreal_project/experience_flow.md)

* 📘 **Scripts Python de session (spawn trials)**
  → [scripts/README.md](../scripts/README.md)

* 📘 **Plans d’expérience & paramètres exposés**
  → [experiment_design/README.md](../experiment_design/README.md)

* 📘 **Pipeline Unreal → CSV (Blueprints + C++)**
  → [unreal_project/README.md](../unreal_project/README.md)


