import pandas as pd
import subprocess
import os

# Fonction pour lire les commandes depuis le fichier Excel et les exécuter
def execute_commands_from_excel(excel_file):
    # Lire le fichier Excel
    df = pd.read_excel(excel_file)

    # Extraire les commandes de la colonne "Command"
    commands = df["Command"].tolist()

    # Exécuter chaque commande une par une
    for idx, command in enumerate(commands):
        print(f"Exécution de : {command}")
        print(f"Trial : {idx + 1}")

        # Exécuter la commande
        process = subprocess.run(command, shell=True)

        # Vérifier si la commande s'est bien exécutée
        if process.returncode != 0:
            print(f"Erreur rencontrée avec : {command}")
            break

        # --- IMPORTANT ---
        # Avant de passer au trial suivant, S'ASSURER QUE LA VOITURE A BIEN DISPARU DANS UNREAL.
        # Sinon : appuyer sur CTRL+C pour interrompre l'exécution,
        # puis relancer à partir de la commande suivante.
        # ------------------

        # Attendre que l'utilisateur appuie sur une touche avant de continuer
        input("Appuyez sur une touche pour exécuter la commande suivante...")

# Exemple d'utilisation
excel_file = ("participant_2_commands_exp2.xlsx")  # Remplacez par le chemin de votre fichier
execute_commands_from_excel(excel_file)
s