import os
import numpy as np
import pandas as pd
import mysql.connector
from tqdm import tqdm
from db_utils import get_db_connection

# ------------------------------------------------------------
# Connexion à MySQL via une fonction utilitaire centralisée
# ------------------------------------------------------------
conn, cursor = get_db_connection()

# ------------------------------------------------------------
# Réinitialise complètement la table Perception
# ------------------------------------------------------------
cursor.execute("DELETE FROM Perception")

# ------------------------------------------------------------
# Détection automatique du chemin racine du repository
# pour revenir à : pedestrian-crossing-prediction/data/raw/
# ------------------------------------------------------------
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
base_path = os.path.join(repo_root, "data", "raw")

# ------------------------------------------------------------
# Parcours des dossiers participants (ex: XXX_24)
# ------------------------------------------------------------
for participant in os.listdir(base_path):
    # Tous les participants VR commencent par "XXX"
    if "XXX" in participant:
        participant_id = participant  # ID = nom du dossier
        path = os.path.join(base_path, participant_id)
        part_folders = os.listdir(path)

        # ------------------------------------------------------------
        # Recherche du fichier Excel de plan expérimental (exp1)
        # Exemple : participant_X_commands_exp1.xlsx
        # ------------------------------------------------------------
        for file in os.listdir(path):
            if file.endswith("exp1.xlsx"):
                input_path = os.path.join(path, file)

                # Lecture du plan d’expérience (27 trials)
                inputs = pd.read_excel(input_path)
                distance_disappearance = inputs['Distance (-d)'].values
                velocity = inputs['Velocity (-v)'].values
                position = inputs['Position (-pos)'].values
                weather = inputs['Weather'].values

                # Buffer où sera stockée la distance perçue
                perceived_distance = [None for _ in range(27)]

                # ------------------------------------------------------------
                # Recherche du dossier exp1/
                # Chaque sous-dossier 1..27 contient cars.csv, gaze.csv, peds.csv
                # ------------------------------------------------------------
                for folder in part_folders:
                    if folder == 'exp1':
                        folder_path = os.path.join(path, folder)
                        subfolders = os.listdir(folder_path)

                        # Parcours des 27 sous-dossiers (1,2,3,...,27)
                        for subfolder in tqdm(subfolders, desc=f"Trials for {participant_id}", leave=True):

                            # Chargement des données véhicule du trial
                            csv_path = os.path.join(folder_path, subfolder)
                            cars = pd.read_csv(os.path.join(csv_path, "cars.csv"), sep=';')

                            # ------------------------------------------------------------
                            # Calcul PERCU (distance perçue)
                            # Basé sur :
                            #   - t1 = moment où X_pos devient 0 après disparition du véhicule
                            #   - t2 = moment où Time_estimated devient non nul
                            #   - v  = vitesse réelle du trial
                            #   - d  = v * (t2 - t1)
                            #
                            # Si valeurs introuvables → None
                            # ------------------------------------------------------------
                            try:
                                # Moment disparition visuelle du véhicule (X_pos == 0)
                                t1 = cars[cars['X_pos'] == 0]['Time'].iloc[1]

                                # Moment où participant pense que la voiture arrive (first non-zero)
                                t2_series = cars[cars['Time_estimated'] != 0]['Time']

                                if not t2_series.empty:
                                    t2 = t2_series.iloc[0]
                                    delta_t = t2 - t1
                                    v = velocity[int(subfolder) - 1] / 3.6  # conversion km/h → m/s
                                    d = v * delta_t
                                    perceived_distance[int(subfolder) - 1] = d
                                else:
                                    perceived_distance[int(subfolder) - 1] = None

                            # Problème si index introuvable (ex : pas assez de lignes)
                            except (IndexError, ValueError):
                                perceived_distance[int(subfolder) - 1] = None

                # ------------------------------------------------------------
                # Insertion SQL après calcul des 27 trials
                # ------------------------------------------------------------
                for i in range(len(perceived_distance)):
                    participant_id_sql = str(participant_id)
                    perceived_distance_sql = float(perceived_distance[i]) if perceived_distance[i] is not None else None
                    velocity_sql = float(velocity[i]) if not pd.isna(velocity[i]) else None
                    distance_sql = float(distance_disappearance[i]) if not pd.isna(distance_disappearance[i]) else None
                    weather_sql = str(weather[i]) if not pd.isna(weather[i]) else None

                    cursor.execute("""
                        INSERT INTO Perception (participant_id, perceived_distance, weather_id, velocity_id, distance_id) 
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        participant_id_sql,
                        perceived_distance_sql,
                        weather_sql,
                        velocity_sql,
                        distance_sql
                    ))

# ------------------------------------------------------------
# Commit final et fermeture connexion MySQL
# ------------------------------------------------------------
conn.commit()
cursor.close()
conn.close()

print("Insertion des données terminée avec succès.")
