# 📁 `model_evaluation/` — README

*Analyses comportementales & validation du modèle analytique final*

Ce dossier contient l’ensemble des notebooks utilisés pour **analyser**, **interpréter** et **valider** le modèle analytique final de prédiction du comportement de traversée du piéton.

Les analyses reposent sur :

* le modèle final sauvegardé dans `saved_models/final_model.yaml`,
* les données VR prétraitées,
* les sorties du pipeline de modélisation (performances, résidus, effets météo, etc.).

Les notebooks sont directement accessibles via **JupyterLite** 👇

---

## 🚀 Ouvrir les notebooks dans JupyterLite

### 🔹 Analyse comportementale (XAI)

[![Launch Model Behavior Analysis](https://img.shields.io/badge/Open%20Behavior%20Analysis-%F0%9F%93%88-blue?style=for-the-badge)](https://sandravict0r.github.io/pedestrian-crossing-prediction/lab/index.html?path=model/model_evaluation/model_behavior_analysis.ipynb)

---

### 🔹 Analyse de performance & validation

[![Launch Model Performance Analysis](https://img.shields.io/badge/Open%20Performance%20Analysis-%F0%9F%93%8A-green?style=for-the-badge)](https://sandravict0r.github.io/pedestrian-crossing-prediction/lab/index.html?path=model/model_evaluation/model_performance_analysis.ipynb)

---

# 📁 Contenu du dossier

```
model/
 └── model_evaluation/
       ├── model_behavior_analysis.ipynb
       ├── model_performance_analysis.ipynb
       └── README.md   ← (ce fichier)
```

---

# 1. 🎯 Objectifs des notebooks

## **1.1. model_behavior_analysis.ipynb**

Notebook d’interprétabilité du modèle analytique.

Ce notebook fournit :

* Heatmaps 2D (partial dependence) :
  **Distance × Vitesse**, **Distance × Taille**, **Vitesse × Météo**, etc.
* Analyses XAI globales :
  **PCA**, **t-SNE**, **UMAP**
* Visualisation de la géométrie de la décision
  (zones traversée / non-traversée)
* Interprétation scientifique des comportements selon :

  * vitesse du véhicule
  * distance au véhicule
  * hauteur du piéton
  * météo

### ✔️ Questions auxquelles répond ce notebook

* Comment le modèle décide-t-il d’une traversée ?
* Quels facteurs modifient la frontière décisionnelle ?
* Comment les variables interagissent-elles dans l’espace 4D ?
* Le modèle reproduit-il le comportement observé en VR ?

---

## **1.2. model_performance_analysis.ipynb**

Notebook de validation statistique et comportementale.

Il implémente et explore :

* Le pipeline complet d’entraînement :

  * split 80/20 par participant
  * régression linéaire
  * calcul des coefficients météo (α_w)
  * calcul du seuil ajusté (µ, σ)
* L’évaluation sur le test set :

  * MAE, RMSE, R²
  * distribution des résidus
  * test de Shapiro–Wilk
  * corrélation de Pearson
* Graphiques de validation :

  * scatter y_pred vs y_true
  * *binned trend* (moyenne + SE)
  * comparaison prédiction brute vs prédiction ajustée
* Analyse des erreurs selon :

  * hauteur des participants
  * vitesse du véhicule
  * météo

### ✔️ Questions auxquelles répond ce notebook

* Le modèle estime-t-il correctement le seuil décisionnel T_end ?
* Quelle est la marge d’erreur selon la météo ?
* Le modèle présente-t-il un biais systémique ?
* Quels sont les sous-groupes humains les plus difficiles à prédire ?
* Comment se comporte la version ajustée du seuil (T_end_adj) ?

---

# 2. 🔬 Résumé scientifique du pipeline d’évaluation

Le modèle analytique final prédit un seuil comportemental minimal :

$$
T_{end}(h,v,w) = \alpha_w \big( a h + b h^2 + c v + \text{intercept} \big) - 2\sigma_w + \mu_w
$$

où :

* (h) = hauteur du piéton
* (v) = vitesse du véhicule
* (w) = météo (clear, night, rain)
* (\alpha_w) = correction perceptive météo
* (\sigma_w, \mu_w) = correction comportementale (biais perceptif + marge de sécurité)

La décision finale est :

$$
\text{Traverse si } TTC \ge T_{end}
\qquad\text{où}\qquad
TTC = \frac{d}{v_{\text{m/s}}}
$$

Les notebooks permettent de :

- comprendre le rôle exact de chaque variable
- valider le modèle sur données VR réelles
- visualiser toutes les régions de l’espace de décision
- garantir la robustesse du seuil ajusté transmis aux partenaires industriels

---

# 3. 📈 Visualisations clés produites

* Heatmaps décisionnelles 2D
* PCA : structure globale du modèle
* t-SNE : structure locale & micro-clusters
* UMAP : compromis global/local
* Distribution des résidus
* Courbe prédiction vs vérité
* Courbe prédiction brute vs ajustée
* Boxplots des erreurs selon height, speed, weather

---

# 4. 🧪 Reproductibilité

Les notebooks nécessitent :

```
Python 3.10+
numpy
pandas
matplotlib
seaborn
scikit-learn
scipy
umap-learn
pyyaml
```

Ils reposent sur :

* `/saved_models/final_model.yaml`
* `/model_datas/` (données VR prétraitées)

