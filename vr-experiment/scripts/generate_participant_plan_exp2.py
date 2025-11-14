import random
import openpyxl
from openpyxl import Workbook

# -------------------------------------------------------------------
# PARAMÈTRES DE L’EXPÉRIENCE 2
# -------------------------------------------------------------------

# Deux groupes possibles pour les vitesses du véhicule.
# Un groupe sera choisi ALÉATOIREMENT pour chaque participant.
groups = [
    [20, 40, 60],
    [30, 50, 70]
]

# Trois types de météo, encodés sous la forme attendue par le script CARLA :
# rain, cloud, light (booleans).
weather = {
    'clear': [False, False, False],
    'night': [False, False, True],
    'rain':  [True,  True,  False]
}

# Trois positions différentes possibles du "player" dans la scène CARLA.
pos = [0, 1, 2]

# Liste des participants (10 participants numérotés de 1 à 10)
participants = list(range(1, 11))

# Compteur pour vérifier la distribution des groupes de vitesses entre participants.
group_counts = {str(groups[0]): 0, str(groups[1]): 0}

# -------------------------------------------------------------------
# FONCTION : Génération des 27 commandes d’un participant (Expérience 2)
# -------------------------------------------------------------------

def generate_commands_for_participant(participant_id):
    """
    Génère toutes les commandes pour UN participant.

    Dans l'Expérience 2 :
       - Un seul groupe de vitesse est choisi pour le participant.
       - Pour chaque vitesse du groupe :
           - toutes les météos sont testées
           - toutes les positions sont testées

    Cela produit :
        3 vitesses × 3 météos × 3 positions = 27 TRIALS.

    Chaque trial est enregistré sous forme de commande Python permettant
    d’exécuter run_trial.py .
    """

    # Sélection aléatoire d'un des deux groupes (Ex : [20,40,60])
    group = random.choice(groups)
    group_counts[str(group)] += 1  # On note l'utilisation du groupe pour analyse

    commands = []

    # Parcours des vitesses dans le groupe sélectionné
    for velocity in group:
        # Parcours des types de météo
        for weather_type, weather_values in weather.items():
            rain, cloud, light = weather_values

            # Parcours des trois positions possibles
            for position in pos:

                # Construction de la commande pour run_trial.py
                command = f"py .\\run_trial.py -v {velocity} -pos {position}"

                # Ajout des drapeaux météo
                if rain:
                    command += " -r True"
                if cloud:
                    command += " -c True"
                if light:
                    command += " -l True"

                # Stockage de TOUTES les infos pour Excel
                commands.append({
                    "Participant": participant_id,
                    "Position (-pos)": position,
                    "Velocity (-v)": velocity,
                    "Weather": weather_type,
                    "Rain (-r)": "VRAI" if rain else "FAUX",
                    "Cloud (-c)": "VRAI" if cloud else "FAUX",
                    "Light (-l)": "VRAI" if light else "FAUX",
                    "Command": command
                })

    # Mélange aléatoire de l’ordre des trials
    random.shuffle(commands)

    return commands

# -------------------------------------------------------------------
# GÉNÉRATION D'UN FICHIER EXCEL PAR PARTICIPANT
# -------------------------------------------------------------------

for participant_id in participants:

    # Générer les 27 commandes pour ce participant
    commands = generate_commands_for_participant(participant_id)

    # Création du classeur Excel
    wb = Workbook()
    ws = wb.active
    ws.title = f"Participant_{participant_id}"

    # En-têtes des colonnes
    headers = [
        "Participant", "Position (-pos)", "Velocity (-v)",
        "Weather", "Rain (-r)", "Cloud (-c)", "Light (-l)", "Command"
    ]
    ws.append(headers)

    # Écriture des commandes dans le tableau Excel
    for cmd in commands:
        ws.append([
            cmd["Participant"],
            cmd["Position (-pos)"],
            cmd["Velocity (-v)"],
            cmd["Weather"],
            cmd["Rain (-r)"],
            cmd["Cloud (-c)"],
            cmd["Light (-l)"],
            cmd["Command"]
        ])

    # Sauvegarde du fichier
    excel_filename = f"participant_{participant_id}_commands_exp2.xlsx"
    wb.save(excel_filename)
    print(f"Fichier Excel créé pour Participant {participant_id} : {excel_filename}")

# -------------------------------------------------------------------
# BILAN DES GROUPES UTILISÉS
# -------------------------------------------------------------------

print("\n=== Répartition des groupes choisis ===")
for group, count in group_counts.items():
    print(f"Groupe {group} choisi {count} fois.")
