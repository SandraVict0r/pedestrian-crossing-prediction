import subprocess
import itertools
import openpyxl
import pandas as pd
import random

# -------------------------------------------------------------------
# Définition des groupes de paramètres pour l'expérience 1
# -------------------------------------------------------------------

# Deux groupes de vitesses possibles
group1 = [20, 40, 60]
group2 = [30, 50, 70]

# Trois types de météo — définis par les flags utilisés par CARLA
# rain, cloud, light
weather = {
    'clear': [False, False, False],
    'night': [False, False, True],
    'rain':  [True,  True,  False]
}

# Trois positions possibles du participant dans la scène CARLA
pos = [0, 1, 2]

# -------------------------------------------------------------------
# Fonction pour générer toutes les combinaisons (groupes vitesse × distance)
# -------------------------------------------------------------------

def generate_all_combinations():
    """
    Retourne toutes les combinaisons possibles des groupes de vitesses
    et des groupes de distances.

    Chaque combinaison correspond à : (velocity_group, distance_group)
    où velocity_group et distance_group sont des tuples de 3 valeurs.
    Exemple : ([20,40,60], [30,50,70])
    """
    combinations = []
    for vel_group in [group1, group2]:
        for dist_group in [group1, group2]:
            combinations.append((tuple(vel_group), tuple(dist_group)))
    return combinations

# -------------------------------------------------------------------
# Génération des commandes (une ligne = un trial)
# -------------------------------------------------------------------

def generate_commands_for_participant(participant_id, velocity_group, distance_group):
    """
    Génère la liste de commandes correspondant à UN participant.

    Un participant réalise :
        - 3 vitesses × 3 distances × 3 météo = 27 trials

    Chaque trial est converti en :
        → une commande Python à exécuter pour lancer run_trial.py
        → un dictionnaire contenant tous les paramètres
    """

    weather_list = list(weather.items())
    commands = []

    # Position aléatoire pour ce participant (0, 1 ou 2)
    position = random.randint(0, 2)

    # Génération des 27 combinaisons pour ce participant
    for velocity in velocity_group:
        for distance in distance_group:
            for weather_type, (rain, cloud, light) in weather_list:

                # Construction de la commande ligne de commande
                # (sera exécutée plus tard dans run_full_session.py)
                command = f"py .\\run_trial.py -v {velocity} -d {distance} -pos {position}"

                # Ajout des flags météo selon les valeurs boolean
                if rain:
                    command += " -r True"
                if cloud:
                    command += " -c True"
                if light:
                    command += " -l True"

                # On stocke toutes les infos du trial dans un dictionnaire
                commands.append({
                    "Participant": participant_id,
                    "Position (-pos)": position,
                    "Velocity (-v)": velocity,
                    "Distance (-d)": distance,
                    "Weather": weather_type,
                    "Rain (-r)": rain,
                    "Cloud (-c)": cloud,
                    "Light (-l)": light,
                    "Command": command
                })

    return commands

# -------------------------------------------------------------------
# Génération des fichiers Excel pour TOUS les participants
# -------------------------------------------------------------------

def generate_files_for_participants(num_participants):
    """
    Répartit équitablement les combinaisons (velocity_group, distance_group)
    entre les participants.

    Chaque participant reçoit :
        → 1 combinaison (velocity_group, distance_group)
        → donc 3×3×3 = 27 trials

    Le but :
        - Équilibrer l'utilisation des différents groupes
        - Mélanger les ordres
        - Exporter un fichier Excel par participant
    """

    # Toutes les combinaisons possibles
    all_combinations = generate_all_combinations()
    num_combinations = len(all_combinations)

    # Nombre de participants ayant la même combinaison
    combinations_per_participant = num_participants // num_combinations

    # Réplication des combinaisons pour couvrir tous les participants
    selected_combinations = all_combinations * combinations_per_participant

    # Ajouter des combinaisons au hasard si participants > combinaisons multiples
    remaining_combinations = num_participants - len(selected_combinations)
    if remaining_combinations > 0:
        selected_combinations += random.sample(all_combinations, remaining_combinations)

    # Mélanger l'ordre des combinaisons
    random.shuffle(selected_combinations)

    # -------------------------------------------------------------------
    # Création d’un fichier Excel pour CHAQUE participant
    # -------------------------------------------------------------------

    for participant_id in range(1, num_participants + 1):

        # Récupérer la combinaison vitesse-distance pour ce participant
        velocity_group, distance_group = selected_combinations[participant_id - 1]

        # Générer les 27 commandes pour ce participant
        commands = generate_commands_for_participant(
            participant_id,
            velocity_group,
            distance_group
        )

        # Mélange des trials pour éviter l'ordre fixe
        df = pd.DataFrame(commands)
        df = df.sample(frac=1).reset_index(drop=True)

        # Export Excel
        output_file = f"participant_{participant_id}_commands_exp1.xlsx"
        df.to_excel(output_file, index=False)
        print(f"Fichier généré pour le participant {participant_id}: {output_file}")

    # Retourne les combinaisons pour vérification
    return selected_combinations


# -------------------------------------------------------------------
# EXÉCUTION DU SCRIPT (génération des fichiers)
# -------------------------------------------------------------------

# Nombre total de participants à générer
num_participants = 10

# Génération des fichiers Excel + récupération des combinaisons utilisées
selected_combinations = generate_files_for_participants(num_participants)

# -------------------------------------------------------------------
# Résumé statistique des combinaisons pour contrôle
# -------------------------------------------------------------------

combination_count = {}
for combination in selected_combinations:
    if combination in combination_count:
        combination_count[combination] += 1
    else:
        combination_count[combination] = 1

print("\nRésumé des combinaisons de groupes de vitesses et de distances :")
for (vel_group, dist_group), count in combination_count.items():
    print(f"Vitesse: {list(vel_group)} - Distance: {list(dist_group)} : {count} fois")
