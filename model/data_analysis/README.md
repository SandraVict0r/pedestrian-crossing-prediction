# 📘 *VR Experiment Analysis* — README

### `data_analysis_exp1.ipynb` & `data_analysis_exp2.ipynb`

Ce dossier regroupe les deux notebooks d’analyse utilisés pour extraire, visualiser et interpréter les résultats des deux expériences VR de la thèse :

---

# 🎯 Objectif global

Ces notebooks permettent d’explorer :

* **l’estimation du temps de collision (TTC)** par les participants  *Expérience 1*
* **la décision de traverser** selon vitesse, météo et caractéristiques individuelles  *Expérience 2*

Ils fournissent toutes les figures, statistiques et vérifications nécessaires à la rédaction du manuscrit (chapitres résultats et discussion).

---

# 📁 Les deux notebooks

## 1️⃣ `data_analysis_exp1.ipynb` — *Perception du TTC*

### Objectif

Analyser comment les participants estiment le **TTC** (Time-To-Collision) lorsque la voiture disparaît à différentes distances.

### Contenu

- Chargement des données MySQL (table `Perception`)
- Calcul TTC réel vs TTC perçu
- Calcul de l’erreur TTC :
`error_ttc = perceived_time – real_time`

### Analyses réalisées

* Statistiques descriptives (mean, median, MAE, biais)
* Histogrammes + boxplots
* Effet :

  * vitesse du véhicule
  * météo
  * distance d’apparition
* Analyse de la difficulté d’estimation en fonction du TTC réel
* ANOVA / Kruskal–Wallis + post-hoc (Tukey, Dunn)
* Corrélations (Pearson)
* Heatmaps
* Étude de l’impact des variables participants :

  * âge (quartiles)
  * taille (quartiles)
  * sexe
  * permis
* Modèles mixtes (effet aléatoire → participant_id)

### Intérêt scientifique

- Détection du seuil critique ≈ **5 secondes** : en-dessous → estimation fiable ; au-dessus → taux d’erreurs augmente.
- Identification des biais de perception selon conditions.
- Effets individuels faibles mais mesurables.

---

## 2️⃣ `data_analysis_exp2.ipynb` — *Décision de traversée*

### Objectif

Analyser comment les participants évaluent **leur capacité à traverser** la route avant l’arrivée de la voiture.

### Variables clés

* **T_end** → seuil de sécurité en *temps*
* **D_end** → seuil de sécurité en *mètres*

### Contenu

- Chargement des données MySQL (table `Crossing`)
- Fusion avec `Participant`
- Construction des variables continues/catégorielles
- Classes : météo, vitesse, quartiles morphologiques

### Analyses réalisées

* Statistiques descriptives (T_end, D_end)
* QQ-plots + tests de normalité
* Corrélations et modèles polynomiaux (R², résidus)
* Effets de :

  * météo (clear / rain / night)
  * sexe
  * permis
  * quartiles d’âge
  * quartiles de taille
* Visualisations avancées :

  * LOWESS (vitesse × météo)
  * polynômes (taille × météo)
  * barplots croisés (ex. météo × sexe)
* Détection des outliers
* Tableaux de synthèse pour toutes les variables

### Intérêt scientifique

- Montre que la **météo et la vitesse** influencent fortement les seuils de sécurité.
- Montre que la **taille** influence légèrement la perception du gap.
- Confirme que les décisions de traversée sont beaucoup plus variables que l’estimation du TTC.


# 🧪 Complémentarité des deux notebooks

| Analyse                          | Expérience 1           | Expérience 2                |
| -------------------------------- | ---------------------- | --------------------------- |
| Estimation du TTC                | ✔ Objectif principal   | ✖                           |
| Décision de traversée            | ✖                      | ✔ Objectif principal        |
| Effet vitesse / météo            | ✔                      | ✔                           |
| Effet caractéristiques individus | ✔                      | ✔                           |
| Modèles statistiques             | descriptifs + post-hoc | descriptifs + poly + LOWESS |
| Résultats utilisés dans la thèse | Chap. perception       | Chap. crossing / modèle     |

Ensemble, ils permettent de **caractériser l’ensemble du processus cognitif** :
perception → estimation du TTC → décision de traversée.

---

#  Exécuter directement dans le navigateur (JupyterLite)

##  Notebook Expérience 1

👉 **[Ouvrir dans JupyterLite](https://jupyterlite.github.io/demo/lab/index.html?path=/notebooks/data_analysis_exp1.ipynb)**

## 📄 Notebook Expérience 2

👉 **[Ouvrir dans JupyterLite](https://jupyterlite.github.io/demo/lab/index.html?path=/notebooks/data_analysis_exp2.ipynb)**

> ⚠️ Si tu actives GitHub Pages, je peux te générer des liens **directement depuis ton repo**, beaucoup plus propres.

---

# 🛠 Pré-requis techniques

Les notebooks nécessitent :

```
pandas
numpy
matplotlib
seaborn
scipy
statsmodels
scikit_posthocs
sklearn
mysql-connector-python
```

Connexion MySQL gérée via :
`../data/database/db_utils.py`
(expliquer comment dans le README de la base de données).


