# 📁 `model/data_visualization/` — README

## 🎯 Objectif du dossier

Le dossier **`model/data_visualization/`** regroupe l’ensemble des outils nécessaires pour :

1. **Explorer et visualiser** les données issues des expériences VR (Exp1 & Exp2).
2. Fournir une **application Streamlit interactive** permettant d’explorer trajectoires, perceptions et profils de crossing.
3. Centraliser les **scripts analytiques** utilisés pour générer les figures descriptives du manuscrit.
4. Permettre une **lecture rapide, reproductible et intuitive** des données avant la modélisation.

Ce dossier fait partie du pipeline général :

📥 `data/processed/` → **Visualisation Streamlit** → 🔍 Analyse → 📦 `model/`

---

## 📦 Structure du dossier

```
data_visualization/
 ├── app.py
 ├── db_utils.py
 ├── requirements.txt
 ├── start_app.bat
 ├── .streamlit/
 │    └── config.toml
 ├── .env
 └── features/
       ├── stats_participants.py
       ├── participant_perc_dist_by_velocity_weather.py
       ├── avg_perc_dist_by_velocity_err_weather.py
       ├── avg_perc_dist_by_weather_err_velocity.py
       ├── bar_perception_delta.py
       ├── participant_avg_crossing_vs_distance.py
       ├── participant_crossing_vs_distance_vwp.py
       └── safety_distance_participant_variables.py
```

---

## 🌐 Lien vers l’application Streamlit en ligne

L’application est accessible ici :

[https://pedestrian-crossing-prediction-vvnmvqnpb8g2wsdmparca8.streamlit.app/](https://pedestrian-crossing-prediction-vvnmvqnpb8g2wsdmparca8.streamlit.app/) 

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://pedestrian-crossing-prediction-vvnmvqnpb8g2wsdmparca8.streamlit.app/)

---

# 🧠 Rôle des sous-dossiers

## 📁 `features/` — Scripts de visualisation analytique

Chaque script correspond à un **module indépendant**, appelé depuis `app.py`.
Tu trouveras ci-dessous **la fonction de chaque fichier**, courte et claire.

---

### 📌 `stats_participants.py`

Analyse descriptive des participants :

* histogrammes d’âge, taille, score de réalisme, sexe, permis
* ajout de *mean ± std* sous forme de "barre verticale"
* reproduit les figures statistiques du manuscrit

---

### 📌 `participant_perc_dist_by_velocity_weather.py`

Analyse perception individuelle :

* distance perçue vs distance réelle
* temps perçu vs temps réel
* **couleurs = vitesse**, **symboles = météo**
* permet d’observer les biais de perception **pour un participant donné**

---

### 📌 `avg_perc_dist_by_velocity_err_weather.py`

Perception moyenne par vitesse :

* moyenne des distances perçues pour chaque groupe de vitesse
* barres d’erreur provenant des conditions météo
* deux figures empilées :
  (1) temps réel/perçu
  (2) distance réelle/perçue

---

### 📌 `avg_perc_dist_by_weather_err_velocity.py`

Perception moyenne par météo :

* moyenne des distances perçues par météo (clear / rain / night)
* barres d’erreur selon les groupes de vitesse
* deux sous-graphiques : distance & temps

---

### 📌 `bar_perception_delta.py`

Analyse du **delta perception** :
Δ = perception – réalité

* graphiques en barres regroupés par météo
* graphiques en barres regroupés par vitesse
* erreurs ± std
* idéal pour comprendre **la surestimation / sous-estimation** par conditions

---

### 📌 `participant_avg_crossing_vs_distance.py`

Profil moyen de crossing par participant :

* reproduction du modèle seuil crossing = f(distance)
* une figure par météo (clear, rain, night)
* ajout **moyenne ± std** de la distance limite (safety distance)
* couleurs par vitesse

---

### 📌 `participant_crossing_vs_distance_vwp.py`

Profil de crossing par :
→ **Vitesse × Météo × Position**

* grille 3×3 (3 météo × 3 positions)
* courbes par essai réel, décalées par vitesse
* permet de visualiser la **variabilité intra-participant**

---

### 📌 `safety_distance_participant_variables.py`

Corrélations entre caractéristiques individuelles et distance de sécurité :

* corrélation Pearson & Spearman
* par météo × vitesse + global
* tableau interactif avec surbrillance des p-values < 0.01
* visualisation des relations : âge, sexe, taille, permis, scale

---

---

## 📁 Racine — Application Streamlit

### 🌐 `app.py`

Interface principale :

* configuration Streamlit (layout, titre)
* menu latéral
* routage vers les pages du dossier `features/`

---

### 🗄️ `db_utils.py`

Gestion de la connexion :

* **local** via `.env`
* **cloud** via `st.secrets` (AlwaysData → Streamlit Cloud)

---

### ⚙️ `requirements.txt`

Dépendances Python :

* streamlit
* pandas
* numpy
* plotly
* mysql-connector-python
* scipy
* (et autres utilitaires nécessaires)

---

### ▶️ `start_app.bat`

Lancement rapide local (Windows) 

# 🔄 Pipeline d’utilisation

1. **Préparer la base MySQL locale**

   Suivre les instructions détaillées ici :
   👉 `data/database/README.md`
   (création de la base, exécution des scripts SQL, insertion des données Exp1/Exp2, configuration du `.env`)

2. **Configurer l’accès à la base en local**

   Mettre ses identifiant dans le `.env` dans `model/data_visualization/`
     avec :

     ```
     DB_HOST=localhost
     DB_PORT=3306
     DB_USER=xxx
     DB_PASSWORD=xxx
     DB_NAME=main_experiment   (ou le nom choisi)
     ```

3. **Installer les dépendances**

   ```
   pip install -r requirements.txt
   ```

4. **Lancer l’application Streamlit en local**
   Depuis `model/data_visualization/` :

   ```
   streamlit run app.py
   ```

   Ou utiliser le raccourci Windows :

   ```
   start_app.bat
   ```

5. **Explorer les données**
   L’application permet d’explorer :

   * perception (distance & temps perçu)
   * seuils de crossing
   * profils individuels
   * delta perception
   * statistiques des participants
   * corrélations (caractéristiques ↔ safety distance)

---


# 📌 Notes

* `.env` ne doit **jamais** être versionné.
* La version cloud repose exclusivement sur `st.secrets`.
* L’app ne modifie jamais les données : lecture seule.
* Les scripts du dossier `features/` produisent des **analyses descriptives**, pas de transformation.
