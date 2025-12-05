import pandas as pd
import subprocess
import os

# =============================================================================
# Exécution séquentielle d'une session complète d'essais CARLA/Unreal
# ---------------------------------------------------------------------
# Ce script lit un fichier Excel contenant les commandes Python à exécuter
# pour chaque trial (souvent générées automatiquement par un script dédié).
#
# Pour chaque ligne :
#   1. La commande est exécutée dans un sous-processus.
#   2. L’opérateur doit valider que la voiture a bien disparu dans Unreal.
#   3. L'utilisateur confirme manuellement avant de lancer le trial suivant.
#
# Ce script assure un pilotage fiable et reproductible d'une session complète,
# en laissant à l'opérateur le contrôle des transitions critiques.
# =============================================================================


def execute_commands_from_excel(excel_file):
    """
    Exécute séquentiellement les commandes listées dans un fichier Excel.

    Paramètres
    ----------
    excel_file : str ou Path
        Chemin vers un fichier .xlsx contenant au minimum une colonne "Command".

    Fonctionnement
    --------------
    - Lecture des commandes dans l’ordre.
    - Exécution via subprocess.run(..., shell=True).
    - Pause après chaque trial pour validation manuelle.
    """

    # Lecture du fichier Excel contenant les commandes (colonne "Command")
    df = pd.read_excel(excel_file)

    if "Command" not in df.columns:
        raise ValueError(
            f"Le fichier '{excel_file}' ne contient pas de colonne 'Command'."
        )

    commands = df["Command"].tolist()

    # Boucle principale — chaque ligne correspond à un trial
    for idx, command in enumerate(commands):
        print(f"\n--- Trial {idx + 1} ------------------------------------------------")
        print(f"Commande : {command}")

        # Exécution de la commande Python
        process = subprocess.run(command, shell=True)

        # Gestion d'erreur basique : arrêt immédiat si le sous-processus échoue
        if process.returncode != 0:
            print(f"Erreur : la commande ci-dessus a échoué (code {process.returncode}).")
            print("Arrêt du script.")
            break

        # ---------------------------------------------------------------------
        # Étape critique : validation que la voiture a complètement disparu.
        #
        # Si la voiture est encore visible dans l'environnement Unreal :
        #   - Ne PAS poursuivre.
        #   - Interrompre ce script via CTRL+C.
        #   - Corriger la situation, puis relancer le script en reprenant
        #     à partir de la ligne Excel correspondante.
        #
        # L'enchaînement automatique sans validation visuelle peut provoquer
        # des collisions logiques entre les trials et compromettre les logs.
        # ---------------------------------------------------------------------

        # Pause opérateur : validation manuelle avant de passer au trial suivant
        input("Appuyez sur Entrée pour lancer la commande suivante...")



# =============================================================================
# Exemple d'utilisation
# Remplacer par le chemin du fichier Excel correspondant au participant.
# =============================================================================

excel_file = "participant_2_commands_exp2.xlsx"
execute_commands_from_excel(excel_file)
