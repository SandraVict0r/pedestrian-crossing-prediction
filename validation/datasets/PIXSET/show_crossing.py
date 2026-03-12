import os
import pandas as pd
import matplotlib.pyplot as plt

# Dossier racine contenant les sous-dossiers avec les CSV
root_dir = r"E:\crossing-model\main_experiment\model_validation\datasets\PIXSET\output\no_adj"

for subdir, _, files in os.walk(root_dir):
    for file in files:
        if not file.endswith(".csv"):
            continue

        csv_path = os.path.join(subdir, file)
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            print(f"Erreur lecture {file}: {e}")
            continue

        if df.empty or 'pedestrian_id' not in df.columns:
            continue

        # Vérifier que les colonnes nécessaires existent
        required_cols = ['frame_id', 'ego_lon', 'ego_lat', 'pedestrian_id',
                         'ped_lon', 'ped_lat', 'true_label', 'prediction']
        if not all(col in df.columns for col in required_cols):
            print(f"Colonnes manquantes dans {file}, ignoré.")
            continue

        # Trier par frame
        df = df.sort_values('frame_id')

        fig, ax = plt.subplots(figsize=(10, 8))

        # Trajectoire du véhicule
        ax.plot(df['ego_lon'], df['ego_lat'], color='blue', label='Véhicule')

        # Pour éviter doublons dans la légende
        crossing_labels_done = set()

        # Trajectoires piétons
        for ped_id in df['pedestrian_id'].dropna().unique():
            df_ped = df[df['pedestrian_id'] == ped_id]
            if df_ped.empty:
                continue

            # Vérité terrain
            df_cross = df_ped[df_ped['true_label'] == True]
            df_noncross = df_ped[df_ped['true_label'] == False]

            # Prédiction crossing
            df_pred_cross = df_ped[df_ped['prediction'] == True]

            # Non-crossing (vérité terrain)
            if not df_noncross.empty:
                ax.plot(df_noncross['ped_lon'], df_noncross['ped_lat'],
                        color='lightgray', linestyle='dashed', linewidth=1)

            # Crossing (vérité terrain)
            if not df_cross.empty:
                label = None
                if ped_id not in crossing_labels_done:
                    label = f'Piéton {ped_id} (crossing GT)'
                    crossing_labels_done.add(ped_id)
                ax.plot(df_cross['ped_lon'], df_cross['ped_lat'],
                        color='red', linewidth=2, label=label)

            # Prédiction crossing
            if not df_pred_cross.empty:
                ax.plot(df_pred_cross['ped_lon'], df_pred_cross['ped_lat'],
                        color='green', linewidth=2, linestyle='solid', alpha=0.6,
                        label=f'Prediction {ped_id}')

        ax.set_title(f"Trajectoires - {file}")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.axis('equal')
        ax.legend()
        ax.grid(True)

        plt.show()
