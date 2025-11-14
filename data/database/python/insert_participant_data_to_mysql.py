import pandas as pd
from db_utils import get_db_connection
import os

# Connexion MySQL (chargée via db_utils + .env)
conn, cursor = get_db_connection()

# Vider la table avant insertion (reset complet)
cursor.execute("DELETE FROM Participant")

# Base path dynamique : le CSV est dans data/participants/participant.csv
# Le chemin est construit à partir du dossier racine du repo.
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
base_path = os.path.join(repo_root, "data", "questionnaires", "participant.csv")

# Chargement du fichier participant.csv
df = pd.read_csv(base_path, sep=';')

# Insertion ligne par ligne
for index, row in df.iterrows():

    participant_id = row['Participant'] if pd.notna(row['Participant']) else None
    age            = row['Age']        if pd.notna(row['Age'])        else None
    sex            = row['Sex']        if pd.notna(row['Sex'])        else None
    height         = row['Height']     if pd.notna(row['Height'])     else None

    driver_license = (
        1 if row['Driver_license'] == True else
        0 if row['Driver_license'] == False else
        None
    )

    scale = row['Scale'] if pd.notna(row['Scale']) else None

    cursor.execute("""
        INSERT INTO Participant (participant_id, age, sex, height, driver_license, scale) 
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        participant_id,
        age,
        sex,
        height,
        driver_license,
        scale
    ))

# Sauvegarde SQL
conn.commit()

cursor.close()
conn.close()
