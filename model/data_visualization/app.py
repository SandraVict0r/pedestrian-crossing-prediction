# app.py
"""
Application Streamlit – Interface principale

Ce fichier est le point d’entrée de l’application Streamlit.
Il gère :
    - la configuration globale (titre, layout)
    - le menu latéral
    - la navigation entre les différentes pages
    - l’appel aux fonctions render() définies dans chaque module du dossier `features/`

Toutes les visualisations et analyses proviennent des scripts du dossier `features`.
Ce fichier ne contient *aucune logique métier* : il orchestre simplement l'affichage.
"""

import streamlit as st
from pathlib import Path

# Import des modules de visualisation (chaque module contient une fonction render())
from features import (
    stats_participants,
    participant_perc_dist_by_velocity_weather,
    avg_perc_dist_by_velocity_err_weather,
    avg_perc_dist_by_weather_err_velocity,
    bar_perception_delta,
    participant_avg_crossing_vs_distance,
    participant_crossing_vs_distance_vwp,
    safety_distance_participant_variables,
)

# ---------------------------------------------------------------------
# Dictionnaire des pages
# ---------------------------------------------------------------------
"""
Clé   = texte affiché dans le menu Streamlit
Valeur = fonction render(base_path) du module correspondant

L'ordre dicté ici est exactement l’ordre du menu dans la barre latérale.
Chaque entrée correspond à un script complet dans /features.
"""
PAGES = {
    "Participant Statistics": stats_participants.render,
    "Perceived Distance by Velocity and Weather per participant":
        participant_perc_dist_by_velocity_weather.render,
    "Avg Perceived Distance by Velocity with Weather Error":
        avg_perc_dist_by_velocity_err_weather.render,
    "Avg Perceived Distance by Weather with Velocity Error":
        avg_perc_dist_by_weather_err_velocity.render,
    "Avg Delta Perception By Weather and Velocity":
        bar_perception_delta.render,
    "Crossing Value vs Distance Pedestrian-Car (V,W) per participant":
        participant_avg_crossing_vs_distance.render,
    "Crossing Value vs Distance Pedestrian-Car (V,W,P) per participant":
        participant_crossing_vs_distance_vwp.render,
    "Pedestrian-Car Gap (Crossing Limit) vs Participant Characteristics":
        safety_distance_participant_variables.render,
}

# ---------------------------------------------------------------------
# Configuration générale de la page Streamlit
# ---------------------------------------------------------------------
"""
page_title  : titre de l’onglet dans le navigateur
layout="wide" : permet d’utiliser toute la largeur de l’écran (important pour des figures Plotly larges)
"""
st.set_page_config(page_title="Main Experiment (Streamlit)", layout="wide")

# Titre de la page principale
st.title("Main Experiment")

# ---------------------------------------------------------------------
# Menu de navigation
# ---------------------------------------------------------------------
"""
selectbox dans la barre latérale (st.sidebar)
→ permet à l’utilisateur de choisir une page parmi la liste des clés du dict PAGES.
"""
page = st.sidebar.selectbox("🧭 Navigation", list(PAGES.keys()))

# Appel dynamique de la page sélectionnée
"""
Chaque module possède une fonction render(base_path: Path)
→ on lui passe Path(".") comme racine du projet
"""
PAGES[page](Path("."))
