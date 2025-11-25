"""
train.py — Training script for the analytical pedestrian behavior model
------------------------------------------------------------------------

Ce script reproduit la procédure d'entraînement utilisée pour dériver
les coefficients du modèle analytique final (CNRS_behavior_model.py).

Pipeline :
    1. Charger les 9 CSV de data/processed/
    2. Concaténer en un seul DataFrame
    3. Ajouter la colonne 'weather' à partir du nom de fichier
    4. Calculer velocity_ms et avg_safety_time
    5. Construire les features polynomiales (height^2, etc.)
    6. Filtrer les outliers (avg_safety_time < safety_time_limit)
    7. Spliter en train/test (80/20)
    8. Cross-validation 10-folds :
          - apprendre les coefficients fixes (a, b, c, intercept)
          - estimer les alpha(weather)
    9. Entraîner le modèle final sur le train complet
   10. Calculer les alphas finaux
   11. Évaluer sur test (MAE, RMSE, R²)
   12. Sauvegarder coefficients + alphas + métriques dans un YAML
   13. Sauvegarder un rapport texte de performance

Usage :
    Depuis le dossier model/model_training/ :

        python train.py

"""

import os
from pathlib import Path
import yaml
import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score
from sklearn.model_selection import train_test_split, KFold


# -------------------------------------------------------------------------
# Chargement de la configuration
# -------------------------------------------------------------------------
CONFIG_PATH = Path(__file__).parent / "config.yaml"


with open(CONFIG_PATH, "r") as f:
    cfg = yaml.safe_load(f)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_FOLDER = BASE_DIR / "data" / "processed"

COEFF_SAVE_PATH = Path(cfg["paths"]["save_coefficients"])
LOG_DIR = Path(cfg["paths"]["logs"])

SAFETY_TIME_LIMIT = cfg["data"]["safety_time_limit"]
FEATURES = cfg["features"]["predictors"]
TARGET = cfg["features"]["target"]
WEATHER_COL = cfg["features"]["weather_column"]

TEST_SIZE = cfg["training"]["test_size"]
RANDOM_STATE = cfg["training"]["random_state"]
N_SPLITS_CV = cfg["training"]["n_splits_cv"]
SHUFFLE_CV = cfg["training"]["shuffle_cv"]


# -------------------------------------------------------------------------
# Création des dossiers de sortie si nécessaire
# -------------------------------------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)
COEFF_SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------------------------------
# Fonctions utilitaires
# -------------------------------------------------------------------------
def load_csv_files(folder_path: Path) -> pd.DataFrame:
    """
    Charge tous les fichiers CSV d'un dossier et ajoute une colonne 'weather'
    extraite du nom de fichier : <weather>_<condition>.csv

    Exemple de noms attendus :
        - clear_high.csv
        - rain_low.csv
        - night_medium.csv
    """
    all_files = [fp for fp in folder_path.iterdir() if fp.suffix == ".csv"]

    datas = pd.DataFrame()

    for file in all_files:
        filename = file.name

        # extraire 'weather' (clear / rain / night)
        if "_" in filename:
            weather = filename.split("_")[0]
        else:
            # si le fichier ne respecte pas le pattern, on l'ignore
            continue

        df = pd.read_csv(file)
        df[WEATHER_COL] = weather

        datas = pd.concat([datas, df], ignore_index=True)

    # conversion de la vitesse (km/h -> m/s)
    # velocity_exp2 doit exister dans les CSV d'origine
    datas["velocity_ms"] = datas["velocity_exp2"] * (5.0 / 18.0)

    # temps de sécurité moyen = distance de sécurité / vitesse
    datas["avg_safety_time"] = datas["avg_safety_distance"] / datas["velocity_ms"]

    # suppression des lignes avec valeurs manquantes
    datas = datas.dropna()

    return datas


def prepare_data(datas: pd.DataFrame, limit: float | None = None) -> pd.DataFrame:
    """
    Ajoute les features polynomiales pour height et velocity_exp2.
    Si limit est spécifié, filtre les observations avec avg_safety_time < limit.
    """
    if limit is not None:
        datas = datas[datas["avg_safety_time"] < limit].copy()

    # Puissances de la taille
    datas["height^2"] = datas["height"] ** 2
    datas["height^3"] = datas["height"] ** 3
    datas["height^4"] = datas["height"] ** 4

    # Puissances de la vitesse (km/h)
    datas["velocity_exp2^2"] = datas["velocity_exp2"] ** 2
    datas["velocity_exp2^3"] = datas["velocity_exp2"] ** 3
    datas["velocity_exp2^4"] = datas["velocity_exp2"] ** 4

    return datas


# -------------------------------------------------------------------------
# Pipeline d'entraînement principal
# -------------------------------------------------------------------------
def main():
    # === 1) Charger et préparer les données ===
    print(f"Chargement des données depuis : {PROCESSED_FOLDER}")
    datas = load_csv_files(PROCESSED_FOLDER)

    print("Préparation des données (ajout des features polynomiales)...")
    all_datas = prepare_data(datas)  # version sans filtre, si besoin
    datas_until_limit = prepare_data(datas, SAFETY_TIME_LIMIT)

    print(f"Filtrage sur avg_safety_time < {SAFETY_TIME_LIMIT} s : "
          f"{len(datas_until_limit)} observations conservées.")

    # === 2) Définir X, y et météo ===
    X = datas_until_limit[FEATURES]
    y = datas_until_limit[TARGET]
    weather = datas_until_limit[WEATHER_COL]

    # === 3) Split global 80/20 ===
    X_train, X_test, y_train, y_test, weather_train, weather_test = train_test_split(
        X, y, weather, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )

    print(f"Taille train : {len(X_train)}, taille test : {len(X_test)}")

    # === 4) Cross-validation K-fold sur train ===
    print(f"Cross-validation {N_SPLITS_CV}-fold sur le train...")

    kf = KFold(n_splits=N_SPLITS_CV, shuffle=SHUFFLE_CV, random_state=RANDOM_STATE)

    # dictionnaire pour stocker les alphas météo par fold
    alphas_cv = {w: [] for w in weather.unique()}
    coefs_cv = []

    for fold_idx, (train_idx, val_idx) in enumerate(kf.split(X_train), start=1):
        X_tr, X_val = X_train.iloc[train_idx], X_train.iloc[val_idx]
        y_tr, y_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
        weather_tr = weather_train.iloc[train_idx]
        weather_val = weather_train.iloc[val_idx]

        # Entraînement modèle global sans météo
        model = LinearRegression()
        model.fit(X_tr, y_tr)

        # Prédictions sur val
        y_val_pred = model.predict(X_val)

        # Calcul alpha météo sur val
        df_val = pd.DataFrame({
            "y_true": y_val,
            "y_pred": y_val_pred,
            WEATHER_COL: weather_val
        })

        # Stocker coefficients fixes (a, b, c, intercept)
        coefs_cv.append(np.append(model.coef_, model.intercept_))

        # Calcul alphas par météo pour ce fold
        for w in alphas_cv.keys():
            subset = df_val[df_val[WEATHER_COL] == w]
            if len(subset) == 0:
                continue
            alpha = subset["y_true"].mean() / subset["y_pred"].mean()
            alphas_cv[w].append(alpha)

        print(f"  Fold {fold_idx}/{N_SPLITS_CV} terminé.")

    # === 5) Moyennes et std des coefs et alphas ===
    coefs_cv = np.array(coefs_cv)  # shape = (folds, 4) → [a, b, c, intercept]
    coef_means = coefs_cv[:, :3].mean(axis=0)
    coef_stds = coefs_cv[:, :3].std(axis=0)
    intercept_mean = coefs_cv[:, 3].mean()
    intercept_std = coefs_cv[:, 3].std()

    alpha_means = {w: float(np.mean(vals)) for w, vals in alphas_cv.items()}
    alpha_stds = {w: float(np.std(vals)) for w, vals in alphas_cv.items()}

    print("\n=== Résultats Cross-validation (moyenne +/- std) ===")
    for var, mean_, std_ in zip(FEATURES, coef_means, coef_stds):
        print(f"  {var}: {mean_:.4f} +/- {std_:.4f}")
    print(f"  intercept: {intercept_mean:.4f} +/- {intercept_std:.4f}")

    print("\nCoefficients multiplicateurs alpha par météo (mean +/- std):")
    for w in alpha_means.keys():
        print(f"  {w}: {alpha_means[w]:.4f} +/- {alpha_stds[w]:.4f}")

    # === 6) Entraînement final sur tout le train ===
    print("\nEntraînement du modèle final sur le train 80%...")
    final_model = LinearRegression()
    final_model.fit(X_train, y_train)

    # Prédictions globales sur train complet
    y_train_pred = final_model.predict(X_train)
    df_train = pd.DataFrame({
        "y_true": y_train,
        "y_pred": y_train_pred,
        WEATHER_COL: weather_train
    })

    # Alphas finaux sur train complet
    alphas_final = {}
    for w in alpha_means.keys():
        subset = df_train[df_train[WEATHER_COL] == w]
        if len(subset) == 0:
            continue
        alphas_final[w] = float(subset["y_true"].mean() / subset["y_pred"].mean())

    a, b, c = final_model.coef_
    intercept = float(final_model.intercept_)

    print("\n=== Équation factorisée finale après entraînement complet sur train 80% ===")
    for w, alpha in alphas_final.items():
        print(
            f"{w} : y = {alpha:.4f} * "
            f"({a:.4f}*height + {b:.4f}*height^2 + {c:.4f}*velocity_exp2 + {intercept:.4f})"
        )

    # === 7) Évaluation sur test 20% ===
    y_test_pred = final_model.predict(X_test)

    mae_test = mean_absolute_error(y_test, y_test_pred)
    rmse_test = root_mean_squared_error(y_test, y_test_pred)
    r2_test = r2_score(y_test, y_test_pred)

    print("\n=== Évaluation sur test 20% ===")
    print(f"MAE : {mae_test:.4f}")
    print(f"RMSE: {rmse_test:.4f}")
    print(f"R²  : {r2_test:.4f}")

    # === 8) Sauvegarde des coefficients et alphas ===
    learned_params = {
        "coefficients": {
            "height": float(a),
            "height^2": float(b),
            "velocity": float(c),
            "intercept": intercept,
        },
        "alphas": alphas_final,
        "alphas_cv_mean": alpha_means,
        "alphas_cv_std": alpha_stds,
        "coefs_cv_mean": {
            "height": float(coef_means[0]),
            "height^2": float(coef_means[1]),
            "velocity": float(coef_means[2]),
            "intercept": float(intercept_mean),
        },
        "coefs_cv_std": {
            "height": float(coef_stds[0]),
            "height^2": float(coef_stds[1]),
            "velocity": float(coef_stds[2]),
            "intercept": float(intercept_std),
        },
        "metrics_test": {
            "MAE": float(mae_test),
            "RMSE": float(rmse_test),
            "R2": float(r2_test),
        },
        "config_used": cfg,
    }

    with open(COEFF_SAVE_PATH, "w") as f:
        yaml.dump(learned_params, f)

    print(f"\nParamètres appris sauvegardés dans : {COEFF_SAVE_PATH}")

    # === 9) Rapport texte dans logs/performance.txt ===
    report = [
        "=== Model Training Report ===",
        "",
        "Coefficients (final model):",
        f"  height     : {a:.4f}",
        f"  height^2   : {b:.4f}",
        f"  velocity   : {c:.4f}",
        f"  intercept  : {intercept:.4f}",
        "",
        "Alphas (final, par météo):",
        *(f"  {w}: {alpha:.4f}" for w, alpha in alphas_final.items()),
        "",
        "Test set performance:",
        f"  MAE  : {mae_test:.4f}",
        f"  RMSE : {rmse_test:.4f}",
        f"  R²   : {r2_test:.4f}",
        "",
    ]

    report_text = "\n".join(report)
    perf_path = LOG_DIR / "performance.txt"
    with open(perf_path, "w") as f:
        f.write(report_text)

    print(f"Rapport de performance sauvegardé dans : {perf_path}")


if __name__ == "__main__":
    main()
