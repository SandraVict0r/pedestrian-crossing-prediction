# app.py
import streamlit as st
from pathlib import Path

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

PAGES = {
    "Participant Statistics": stats_participants.render,
    "Perceived Distance by Velocity and Weather per participant": participant_perc_dist_by_velocity_weather.render,
    "Avg Perceived Distance by Velocity with Weather Error": avg_perc_dist_by_velocity_err_weather.render,
    "Avg Perceived Distance by Weather with Velocity Error": avg_perc_dist_by_weather_err_velocity.render,
    "Avg Delta Perception By Weather and Velocity": bar_perception_delta.render,
    "Crossing Value vs Distance Pedestrian-Car (V,W) per participant": participant_avg_crossing_vs_distance.render,
    "Crossing Value vs Distance Pedestrian-Car (V,W,P) per participant": participant_crossing_vs_distance_vwp.render,
    "Pedestrian-Car Gap (Crossing Limit) vs Participant Characteristics": safety_distance_participant_variables.render,
}

st.set_page_config(page_title="Main Experiment (Streamlit)", layout="wide")
st.title("Main Experiment")

page = st.sidebar.selectbox("🧭 Navigation", list(PAGES.keys()))
PAGES[page](Path("."))
