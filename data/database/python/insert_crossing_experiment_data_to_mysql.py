import os
import numpy as np
import pandas as pd
import json
import mysql.connector
from tqdm import tqdm
from dotenv import load_dotenv
from db_utils import get_db_connection

# ------------------------------------------------------------
# Connexion MySQL via un helper externe
# ------------------------------------------------------------
conn, cursor = get_db_connection()

# ------------------------------------------------------------
# Réinitialisation de la table Crossing
# ------------------------------------------------------------
cursor.execute("DELETE FROM Crossing")

# ------------------------------------------------------------
# Détection automatique du chemin racine du repository
# Le script se trouve dans : pedestrian-crossing-prediction/data/mysql_scripts/
# On remonte de 2 niveaux → pedestrian-crossing-prediction/
# ------------------------------------------------------------
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dossier contenant les données VR brutes :
# pedestrian-crossing-prediction/data/raw/
base_path = os.path.join(repo_root, "data", "raw")

# ------------------------------------------------------------
# Parcours des dossiers participants (format XXX_24, XXX_03, ...)
# ------------------------------------------------------------
for participant in os.listdir(base_path):

    # Chaque participant réel commence par "XXX"
    if "XXX" in participant:

        participant_id = participant
        print(participant_id)

        # ------------------------------------------------------------
        # Position du piéton dépend de la version de la scène
        # (certains participants ont position[1]=2665, d'autres 3665)
        # ------------------------------------------------------------
        pos = [14343.0, 3665.0, 13317.0]   # valeurs standards
        if int(participant_id[-2:]) > 34:  # participants tardifs → modif pos1
            pos = [14343.0, 2665.0, 13317.0]

        # Chemin vers le dossier du participant
        path = os.path.join(base_path, participant_id)
        part_folders = os.listdir(path)

        # ------------------------------------------------------------
        # Recherche du plan d’expérience Exp2 (fichier Excel)
        # ------------------------------------------------------------
        for file in os.listdir(path):
            if file.endswith("exp2.xlsx"):

                input_path = os.path.join(path, file)
                inputs = pd.read_excel(input_path)

                # Paramètres Exp2 pour chaque trial (27 lignes)
                velocity = inputs['Velocity (-v)'].values
                position = inputs['Position (-pos)'].values
                weather  = inputs['Weather'].values

                # Buffers de stockage
                crossing_value = [np.array([]) for _ in range(27)]
                distance_car_ped = [np.array([]) for _ in range(27)]
                start_crossing_values = np.zeros(27)
                stop_crossing_values  = np.zeros(27)
                safety_distance_values = np.zeros(27)

                # ------------------------------------------------------------
                # Recherche du dossier exp2/ contenant 1..27
                # ------------------------------------------------------------
                for folder in part_folders:
                    if folder == 'exp2':

                        folder_path = os.path.join(path, folder)
                        subfolders = os.listdir(folder_path)

                        # ------------------------------------------------------------
                        # Parcours des 27 trials
                        # ------------------------------------------------------------
                        for subfolder in tqdm(subfolders, desc="Trial", leave=True):

                            csv_path = os.path.join(folder_path, subfolder)

                            # Chargement des données véhicule & piéton
                            cars = pd.read_csv(os.path.join(csv_path, "cars.csv"), sep=';')
                            peds = pd.read_csv(os.path.join(csv_path, "peds.csv"), sep=';')

                            # Normalisation colonnes
                            cars = cars[['Time', 'X_pos']].rename(columns={'X_pos': 'X_cars'})
                            peds = peds[['Time', 'Crossing']]

                            # Fusion synchronisée par Time
                            peds = pd.merge(peds, cars, on="Time", how="inner")
                            peds = peds.dropna()
                            peds = peds[peds['X_cars'] != 0]  # voiture visible seulement

                            # ------------------------------------------------------------
                            # Correction du "Crossing" :
                            # - trouve le 1er 1
                            # - met tout avant à 1
                            # - round sur les valeurs non 0/1 (cas VR)
                            # ------------------------------------------------------------
                            first_one_index = peds[peds['Crossing'] == 1].index[0]
                            peds.loc[:first_one_index-1, 'Crossing'] = 1
                            peds['Crossing'] = peds['Crossing'].apply(
                                lambda x: round(x) if x not in [0, 1] else x
                            )

                            # ------------------------------------------------------------
                            # Distance voiture → piéton
                            # Conversion cm → mètres
                            # ------------------------------------------------------------
                            dist = (peds['X_cars'].values - pos[position[int(subfolder)-1]]) / 100
                            crossing = peds['Crossing'].values

                            distance_car_ped[int(subfolder) - 1] = np.array(dist, dtype=float)
                            crossing_value[int(subfolder) - 1]   = np.array(crossing, dtype=float)

                            # ------------------------------------------------------------
                            # Détection des transitions Cross :
                            #   0 -> 1 = début crossing
                            #   1 -> 0 = fin crossing
                            # ------------------------------------------------------------
                            start_crossing_value = False
                            stop_crossing_value  = False

                            for index in range(len(peds)-1):
                                row = peds.iloc[index]
                                next_row = peds.iloc[index + 1]

                                if start_crossing_value and stop_crossing_value:
                                    break

                                if row['Crossing'] != next_row['Crossing']:

                                    if (row['Crossing'] == 0) and (next_row['Crossing'] == 1):
                                        start_crossing = row['X_cars']
                                        start_crossing_value = True

                                    elif (row['Crossing'] == 1) and (next_row['Crossing'] == 0):
                                        stop_crossing = row['X_cars']
                                        stop_crossing_value = True

                            # Valeurs manquantes
                            if not start_crossing_value:
                                start_crossing = None
                            if not stop_crossing_value:
                                stop_crossing = None

                            # ------------------------------------------------------------
                            # Safety Distance
                            # Distance entre stop_crossing et position piéton
                            # ------------------------------------------------------------
                            if stop_crossing is not None:
                                safety_distance = abs(
                                    (stop_crossing - pos[position[int(subfolder)-1]]) / 100
                                )
                            else:
                                safety_distance = None

                            safety_distance_values[int(subfolder) - 1] = safety_distance

                # ------------------------------------------------------------
                # Insertion SQL pour les 27 trials
                # ------------------------------------------------------------
                for i in range(27):
                    crossing_val = crossing_value[i].tolist()
                    dist_val = distance_car_ped[i].tolist()

                    crossing_value_json = json.dumps(crossing_val, separators=(',', ':'))
                    distance_car_ped_json = json.dumps(dist_val, separators=(',', ':'))

                    position_val = int(position[i]) if position[i] is not None else None
                    velocity_val = float(velocity[i]) if velocity[i] is not None else None
                    weather_val = weather[i] if weather[i] is not None else None
                    safety_distance_val = (
                        float(safety_distance_values[i])
                        if safety_distance_values[i] is not None
                        else None
                    )

                    cursor.execute("""
                        INSERT INTO Crossing (
                            participant_id, weather_id, position_id, velocity_id,
                            distance_car_ped, crossing_value, safety_distance
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        participant_id,
                        weather_val,
                        position_val,
                        velocity_val,
                        distance_car_ped_json,
                        crossing_value_json,
                        safety_distance_val
                    ))

# ------------------------------------------------------------
# Commit final + fermeture connexion
# ------------------------------------------------------------
conn.commit()
cursor.close()
conn.close()
