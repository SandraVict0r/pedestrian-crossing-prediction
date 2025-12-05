# `saved_models/` — README

## Objectif du dossier

Le dossier **`saved_models/`** contient les artefacts finaux du **modèle analytique de prédiction du seuil minimal de non-traversée** développé dans la thèse.

Il regroupe :

1. **`final_model.yaml`**
   → Fichier d’export contenant les coefficients globaux, les paramètres météo (`alpha_weather`), les biais comportementaux (`mu`, `sigma`) et les métriques de test.

2. **`CNRS_behavior_model.py`**
   → Implémentation opérationnelle du modèle :

   * chargement automatique du YAML
   * calcul du seuil comportemental ($T_{\text{end}}$)
   * décision de traversée via le TTC réel

Ce dossier constitue **la couche d’inférence** du projet, indépendante de l’entraînement.

---

# Structure du dossier

```
saved_models/
 ├── CNRS_behavior_model.py     # Module Python utilisable directement
 └── final_model.yaml           # Paramètres exportés du modèle entraîné
```

---

# Contenu de `final_model.yaml`

Le fichier contient **tous les paramètres nécessaires** pour reproduire le modèle final.

## **1. Informations générales**

```yaml
model_info:
  name: Pedestrian_Pedestrian_Model
  version: "1.0"
  generated_on: "2025-11-26 15:58:27"
  description: Modele analytique predictif du temps minimal de non-traversee...
```

## **2. Coefficients globaux**

Appris via la régression linéaire (CV 10 folds) :

```yaml
coefficients_global:
  a_height: -1.3614
  b_height2: 0.00387
  c_velocity: -0.05401
  intercept: 126.05919
```

Ils définissent :

$$
T_{\text{pred}} = a h + b h^2 + c v + \text{intercept}
$$

## **3. Paramètres météo**

Pour chaque météo :

* multiplicateur météo ( \alpha )
* biais comportementaux Model V2 (µ, σ)

```yaml
weather_parameters:
  clear:
    alpha_weather: 1.0385
    bias:
      mu: 0.0386
      sigma: 1.0008
```

Formule finale pour le seuil comportemental :

$$
T_{\text{end}} =

\alpha_{\text{weather}}
\left(
a h + b h^2 + c v + \text{intercept}
\right)

* 2\sigma_{\text{weather}}

- \mu_{\text{weather}}
$$

## **4. Métriques sur le jeu de test**

Le YAML contient également :

* performances **sans biais**
* performances **avec biais (modèle conservateur)**

Cette section est informative mais non utilisée par `CNRS_behavior_model.py`.

---

# Fonctionnement de `CNRS_behavior_model.py`

Le module Python fournit :

###  Chargement automatique du YAML

via `_load_yaml()` (cache interne), aucune dépendance externe.

###  Extraction des paramètres

* `_get_coeffs()` : coefficients globaux
* `_get_weather_params()` : alpha + µ + σ pour la météo choisie

###  Fonction principale : calcul du seuil ($T_{\text{end}}$)

```python
T_end = predict_T_end(weather, height_cm, velocity_kmh)
```

Cette fonction applique exactement le modèle final :

$$
T_{\text{end}} =
\alpha (a h + b h^2 + c v + \text{intercept})

* 2\sigma

- \mu
  $$

### Décision de traversée

```python
decision, T_end, TTC_real = crossing_decision(
    weather="rain",
    height_cm=172,
    velocity_kmh=40,
    distance_m=25
)
```

La règle comportementale :

* si $(TTC_{\text{real}} \ge T_{\text{end}})$ → **traverse (True)**
* sinon → **ne traverse pas (False)**

Signification :

* **$T_{end}$** = seuil psychophysique estimé par le modèle
* **$TTC_{real}$** = temps réel avant collision du véhicule

---

#  Exemple d’utilisation dans un script Python

```python
from CNRS_behavior_model import predict_T_end, crossing_decision

# 1. Calcul du seuil
T_end = predict_T_end(
    weather="clear",
    height_cm=170,
    velocity_kmh=50
)
print("T_end =", T_end)

# 2. Décision de traversée
decision, T_end, TTC_real = crossing_decision(
    weather="clear",
    height_cm=170,
    velocity_kmh=50,
    distance_m=20
)

print("T_end:", T_end)
print("TTC_real:", TTC_real)
print("Traverse ?", decision)
```

Sortie typique :

```
T_end = 3.52 s
TTC_real = 2.88 s
Traverse ? False
```

---

# Exemple d’utilisation en ligne de commande (CLI intégré)

Le module peut être utilisé directement :

```bash
python CNRS_behavior_model.py \
    -weather clear \
    -height 170 \
    -velocity 50 \
    -distance 20
```

→ affiche :

```
=== Pedestrian Crossing Model ===
Weather       : clear
T_end         : 3.520 s  (adjusted)
TTC_real      : 2.880 s
Decision      : False  (True = cross)
```

---

# Notes importantes

* `final_model.yaml` doit rester **dans le même dossier** que `CNRS_behavior_model.py`.
* Le modèle utilise uniquement **height, velocity_kmh, météo et distance**.
* Aucun réentraînement n’est nécessaire pour utiliser le modèle.
* Le modèle est **déterministe**, **interprétable** et **faible coût computatif**.
* La décision modélisée correspond à une **non-traversée anticipée** (comportement conservateur).
