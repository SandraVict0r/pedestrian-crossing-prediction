Parfait, je te réécris la partie **déploiement** pour **ne plus expliquer comment déployer**, mais simplement :

* dire que l’app est prévue pour être déployée sur Streamlit Cloud,
* dire comment **y accéder une fois en ligne**,
* indiquer où mettre le lien,
* garder un README propre et concis.

Voici la version corrigée du README (en français, sans instructions de déploiement), à mettre tel quel dans ton fichier :

---

````markdown
# Application de visualisation des données (Streamlit)

Ce dossier contient une application **Streamlit** permettant d’explorer de manière interactive les données issues des expériences VR utilisées dans le cadre de la thèse.

L’application rassemble l’ensemble des visualisations descriptives :

- statistiques des participants ;
- perception des distances et du temps (réel vs perçu) ;
- influence de la météo et des vitesses ;
- analyse du comportement de traversée ;
- profils individuels des participants ;
- delta perception et barres d’erreur ;
- corrélations entre caractéristiques individuelles et distance de sécurité.

Toute la logique de visualisation est factorisée dans les modules du dossier `features/`.

---

## 1. Structure du dossier

```text
data_visualization/
 ├── app.py                          # Application Streamlit principale
 ├── db_utils.py                     # Fonctions de connexion MySQL
 ├── .env                            # Identifiants DB (non versionné)
 ├── requirements.txt                # Dépendances Python
 ├── start_app.bat                   # Script pratique (Windows)
 ├── .streamlit/
 │    └── config.toml                # Configuration de thème Streamlit
 └── features/
       ├── stats_participants.py
       ├── participant_perc_dist_by_velocity_weather.py
       ├── avg_perc_dist_by_velocity_err_weather.py
       ├── avg_perc_dist_by_weather_err_velocity.py
       ├── bar_perception_delta.py
       ├── participant_avg_crossing_vs_distance.py
       ├── participant_crossing_vs_distance_vwp.py
       └── safety_distance_participant_variables.py
````

---

## 2. Installation locale

### 2.1. Cloner le dépôt

```bash
git clone https://github.com/<utilisateur>/pedestrian-crossing-prediction.git
cd pedestrian-crossing-prediction/model/data_visualization
```

### 2.2. Créer un environnement virtuel

```bash
python -m venv venv
# Sous Linux / macOS :
source venv/bin/activate
# Sous Windows :
venv\Scripts\activate
```

### 2.3. Installer les dépendances

```bash
pip install -r requirements.txt
```

---

## 3. Configuration locale de la base de données

Créer un fichier `.env` dans `model/data_visualization/` :

```env
DB_HOST=localhost
DB_USER=mon_utilisateur
DB_PASSWORD=mon_mot_de_passe
DB_NAME=nom_de_ma_base
```

⚠️ Ce fichier ne doit pas être versionné dans Git.

---

## 4. Lancement de l’application en local

### Option A — via Streamlit

```bash
streamlit run app.py
```

L’application sera accessible à :

**[http://localhost:8501](http://localhost:8501)**

### Option B — via le script Windows

Double-cliquer sur :

```
start_app.bat
```

---

## 5. Accès en ligne à l'application

Cette application peut être déployée sur **Streamlit Community Cloud**.
Une fois déployée, elle sera accessible directement via une URL du type :

```
https://nom-de-votre-application.streamlit.app
```

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://nom-de-ton-app.streamlit.app)


---

## 6. Objectif scientifique

Cette application a été conçue pour :

* faciliter l’exploration interactive des données VR ;
* documenter les figures descriptives présentées dans la thèse ;
* fournir un support d’analyse transparent aux encadrants et évaluateurs ;
* compléter les livrables du projet AI4CCAM.

Elle rend visibles et reproductibles tous les résultats descriptifs utilisés pour la modélisation.

