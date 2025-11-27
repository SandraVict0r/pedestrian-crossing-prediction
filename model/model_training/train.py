"""
train.py — Training script for the analytical pedestrian behavior model
------------------------------------------------------------------------

Ce script reproduit le pipeline du notebook `model.ipynb` :

1. Charger les 9 CSV dans data/processed/
2. Concatener en un seul DataFrame
3. Ajouter la colonne 'weather' à partir du nom de fichier
4. Calculer velocity_ms et avg_safety_time
5. Construire les features (height, height^2, velocity_exp2)
6. Filtrer les outliers (avg_safety_time < 7 s)
7. Split global train/test (80/20)
8. Cross-validation 10-folds sur le train :
      - apprendre les coefficients fixes (a, b, c, intercept)
      - estimer les alpha_weather (clear, rain, night)
9. Recalibrer les biais (mu, sigma) par meteo (logique Model V2)
10. Évaluer le modele sur le test (avec et sans biais)
11. Exporter tous les parametres dans `model/saved_models/final_model.yaml`
12. Sauvegarder un rapport texte dans `model/model_training/logs/performance.txt`

Usage :
    Depuis le dossier model/model_training/ :
        python train.py
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Dict, Any

import numpy as np
import pandas as pd
import yaml

from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import train_test_split, KFold


# -------------------------------------------------------------------------
# Parametres globaux (alignes sur le notebook)
# -------------------------------------------------------------------------

# Repo root : .../pedestrian-crossing-prediction
BASE_DIR = Path(__file__).resolve().parents[2]

PROCESSED_FOLDER = BASE_DIR / "data" / "processed"
SAVE_DIR = Path(__file__).resolve().parent.parent / "saved_models"
LOG_DIR = Path(__file__).resolve().parent / "logs"

SAVE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Parametres de filtrage et de features
SAFETY_TIME_LIMIT = 7.0
WEATHER_COL = "weather"

FEATURES_GLOBAL = ["height", "height^2", "velocity_exp2"]
TARGET = "avg_safety_time"

# Parametres d'entraînement global (Cellule 4)
TEST_SIZE_GLOBAL = 0.2
RANDOM_STATE_GLOBAL = 42
N_SPLITS_CV = 10
SHUFFLE_CV = True

# Parametres du pipeline V2 pour les biais (Cellule 5)
V2_TEST_SIZE_MAIN = 0.3
V2_RANDOM_STATE_MAIN = 253
V2_N_ITER = 10


# -------------------------------------------------------------------------
# Fonctions utilitaires de chargement et preparation
# -------------------------------------------------------------------------

def load_csv_files(folder_path: Path) -> pd.DataFrame:
    """
    Charge tous les fichiers CSV du dossier `data/processed/` et ajoute une colonne
    'weather' extraite du nom de fichier : <weather>_<condition>.csv.
    """
    all_files = [fp for fp in folder_path.iterdir() if fp.suffix == ".csv"]
    if not all_files:
        raise FileNotFoundError(f"Aucun CSV trouve dans {folder_path}")

    datas = pd.DataFrame()

    for file in all_files:
        filename = file.name

        if "_" not in filename:
            # On ignore les fichiers qui ne respectent pas le pattern
            print(f" Fichier ignore (nom inattendu) : {filename}")
            continue

        weather = filename.split("_")[0]
        df = pd.read_csv(file)
        df[WEATHER_COL] = weather
        datas = pd.concat([datas, df], ignore_index=True)

    # Conversion vitesse (km/h -> m/s)
    if "velocity_exp2" not in datas.columns:
        raise KeyError("Colonne 'velocity_exp2' manquante dans les CSV.")

    datas["velocity_ms"] = datas["velocity_exp2"] * (5.0 / 18.0)

    # Temps de securite moyen
    datas["avg_safety_time"] = datas["avg_safety_distance"] / datas["velocity_ms"]

    datas = datas.dropna()

    return datas


def prepare_data(datas: pd.DataFrame, limit: float | None = None) -> pd.DataFrame:
    """
    Ajoute les features necessaires au modele :
      - height^2
    Et applique un filtre sur avg_safety_time si limit est specifie.
    """
    df = datas.copy()

    if limit is not None:
        df = df[df["avg_safety_time"] < limit].copy()

    df["height^2"] = df["height"] ** 2

    return df


# -------------------------------------------------------------------------
# Fonctions pour le modele global (Cellule 4)
# -------------------------------------------------------------------------

def cross_validation_global(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    weather_train: pd.Series,
) -> tuple[np.ndarray, float, Dict[str, float]]:
    """
    Reproduit la logique de la Cellule 4 :
    - KFold 10 folds
    - entraînement d'un modele lineaire global
    - estimation des coefficients et des alpha_weather
    """
    kf = KFold(
        n_splits=N_SPLITS_CV,
        shuffle=SHUFFLE_CV,
        random_state=RANDOM_STATE_GLOBAL,
    )

    coefs_cv = []
    alphas_cv: Dict[str, list[float]] = {
        w: [] for w in weather_train.unique()
    }

    for fold_idx, (train_idx, val_idx) in enumerate(kf.split(X_train), start=1):
        X_tr, X_val = X_train.iloc[train_idx], X_train.iloc[val_idx]
        y_tr, y_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
        weather_val = weather_train.iloc[val_idx]

        model = LinearRegression()
        model.fit(X_tr, y_tr)
        y_val_pred = model.predict(X_val)

        df_val = pd.DataFrame(
            {"y_true": y_val, "y_pred": y_val_pred, WEATHER_COL: weather_val}
        )

        # stocker coefficients
        coefs_cv.append(np.append(model.coef_, model.intercept_))

        # alphas par meteo
        for w in alphas_cv.keys():
            subset = df_val[df_val[WEATHER_COL] == w]
            if len(subset) == 0:
                continue
            alpha_w = subset["y_true"].mean() / subset["y_pred"].mean()
            alphas_cv[w].append(alpha_w)

        print(f"  Fold {fold_idx}/{N_SPLITS_CV} termine.")

    coefs_cv = np.array(coefs_cv)  # shape: (folds, 4)

    coef_means = coefs_cv[:, :3].mean(axis=0)
    intercept_mean = float(coefs_cv[:, 3].mean())

    alpha_means = {w: float(np.mean(vals)) for w, vals in alphas_cv.items()}

    return coef_means, intercept_mean, alpha_means


# -------------------------------------------------------------------------
# Fonctions pour les biais V2 par meteo (Cellule 5 reproduite)
# -------------------------------------------------------------------------

def select_predictors_v2(datas: pd.DataFrame, weather_condition: str) -> tuple[pd.DataFrame, pd.Series]:
    """
    Selectionne les predicteurs pour la logique V2, filtres par meteo.
    Utilise :
        - height
        - velocity_exp2
        - height^2
    """
    df = datas[datas[WEATHER_COL] == weather_condition].copy()

    X = df[["height", "velocity_exp2", "height^2"]]
    y = df["avg_safety_time"]

    return X, y


def train_and_evaluate_model_v2(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    test_size: float = 0.2,
    n_iter: int = V2_N_ITER,
) -> Dict[str, Any]:
    """
    Moyenne les coefficients sur n_iter splits internes du train,
    avec random_state = 0..n_iter-1 (logique Model V2).
    """
    all_coefs = []
    all_intercepts = []

    mse_list, rmse_list, r2_list, mae_list = [], [], [], []

    for seed in range(n_iter):
        X_tr, X_te, y_tr, y_te = train_test_split(
            X_train, y_train, test_size=test_size, random_state=seed
        )

        model = LinearRegression()
        model.fit(X_tr, y_tr)
        y_pred = model.predict(X_te)

        mse = mean_squared_error(y_te, y_pred)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_te, y_pred)
        mae = mean_absolute_error(y_te, y_pred)

        mse_list.append(mse)
        rmse_list.append(rmse)
        r2_list.append(r2)
        mae_list.append(mae)

        all_coefs.append(model.coef_)
        all_intercepts.append(model.intercept_)

    return {
        "coefs": np.mean(all_coefs, axis=0),
        "intercept": float(np.mean(all_intercepts)),
        "metrics": {
            "mse": float(np.mean(mse_list)),
            "rmse": float(np.mean(rmse_list)),
            "r2": float(np.mean(r2_list)),
            "mae": float(np.mean(mae_list)),
        },
    }


def prediction_v2(
    X: pd.DataFrame,
    y: pd.Series,
    coefs: np.ndarray,
    intercept: float,
) -> tuple[np.ndarray, Dict[str, float]]:
    """
    Applique l'equation V2 :
        y_pred = intercept + a*height + b*velocity_exp2 + c*height^2
    Et renvoie les metriques (MAE, MSE, R2, ME, STD des erreurs).
    """
    a, b, c = coefs
    y_pred = intercept + a*X["height"] + b*X["velocity_exp2"] + c*X["height^2"]

    errors = y - y_pred
    abs_errors = np.abs(errors)

    return y_pred, {
        "mse": mean_squared_error(y, y_pred),
        "rmse": float(np.sqrt(mean_squared_error(y, y_pred))),
        "r2": r2_score(y, y_pred),
        "mae": float(abs_errors.mean()),
        "me": float(errors.mean()),
        "std": float(errors.std()),
    }


def compute_bias_for_weather_v2(
    datas: pd.DataFrame,
    weather: str,
    test_size_main: float = V2_TEST_SIZE_MAIN,
    random_state_main: int = V2_RANDOM_STATE_MAIN,
    n_iter: int = V2_N_ITER,
) -> Dict[str, Any]:
    """
    Reproduit la fonction modeling(datas_until_7, weather) de Model V2 :
    - filtre par meteo
    - split 70/30 (random_state = 253)
    - moyenne des coefficients sur 10 sous-modeles
    - biais (me, std) calcule sur le TRAIN
    """
    X, y = select_predictors_v2(datas, weather_condition=weather)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size_main, random_state=random_state_main
    )

    result = train_and_evaluate_model_v2(X_train, y_train, n_iter=n_iter)
    coefs = result["coefs"]
    intercept = result["intercept"]

    y_pred_train, metrics_train = prediction_v2(X_train, y_train, coefs, intercept)

    return {
        "coefs": coefs,
        "intercept": intercept,
        "train_metrics": metrics_train,
        "bias": {
            "mu": metrics_train["me"],
            "sigma": metrics_train["std"],
        },
    }


# -------------------------------------------------------------------------
# Évaluation et metriques
# -------------------------------------------------------------------------

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    errors = y_true - y_pred
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "R2": float(r2_score(y_true, y_pred)),
        "ME": float(errors.mean()),
        "STD": float(errors.std()),
    }


def predict_final_one(
    weather: str,
    height: float,
    velocity_exp2: float,
    coef_means: np.ndarray,
    intercept_mean: float,
    alpha_means: Dict[str, float],
    bias_v2: Dict[str, Dict[str, float]],
) -> Dict[str, float]:
    """
    Reproduit la fonction predict_final du notebook :
      - modele global base
      - multiplicateur meteo alpha_weather
      - biais V2 (mu, sigma) par meteo
    """
    if weather not in alpha_means:
        raise ValueError(f"Meteo inconnue: {weather}")

    a, b, c = coef_means
    base_pred = a*height + b*(height**2) + c*velocity_exp2 + intercept_mean

    alpha = alpha_means[weather]
    mu = bias_v2[weather]["mu"]
    sigma = bias_v2[weather]["sigma"]

    pred_weather = alpha * base_pred
    pred_final = pred_weather - 2*sigma + mu

    return {
        "no_bias": float(pred_weather),
        "final": float(pred_final),
    }


# -------------------------------------------------------------------------
# Script principal
# -------------------------------------------------------------------------

def main() -> None:
    # 1) Chargement et preparation
    print(f" Chargement des donnees depuis : {PROCESSED_FOLDER}")
    datas = load_csv_files(PROCESSED_FOLDER)

    print(" Preparation des donnees...")
    datas_until_limit = prepare_data(datas, SAFETY_TIME_LIMIT)

    print(
        f"Filtrage avg_safety_time < {SAFETY_TIME_LIMIT} s : "
        f"{len(datas_until_limit)} lignes conservees."
    )

    # 2) Construction X, y, weather
    X = datas_until_limit[FEATURES_GLOBAL]
    y = datas_until_limit[TARGET]
    weather = datas_until_limit[WEATHER_COL]

    # 3) Split global 80/20 (Cellule 4)
    X_train, X_test, y_train, y_test, weather_train, weather_test = train_test_split(
        X, y, weather,
        test_size=TEST_SIZE_GLOBAL,
        random_state=RANDOM_STATE_GLOBAL,
    )

    print(f" Taille train : {len(X_train)}, taille test : {len(X_test)}")

    # 4) Cross-validation globale (coeffs + alpha_weather)
    print(f" Cross-validation {N_SPLITS_CV}-fold sur le train...")
    coef_means, intercept_mean, alpha_means = cross_validation_global(
        X_train, y_train, weather_train
    )

    print("\n=== Coefficients globaux (moyenne CV) ===")
    for name, val in zip(FEATURES_GLOBAL, coef_means):
        print(f"  {name:10s} : {val:.4f}")
    print(f"  intercept  : {intercept_mean:.4f}")

    print("\n=== Alphas meteo (moyenne CV) ===")
    for w, a in alpha_means.items():
        print(f"  {w:6s} : {a:.4f}")

    # 5) Biais V2 par meteo
    print("\n Calcul des biais V2 par meteo (mu, sigma)...")
    bias_v2: Dict[str, Dict[str, float]] = {}
    for w in ["clear", "rain", "night"]:
        res = compute_bias_for_weather_v2(datas_until_limit, w)
        bias_v2[w] = res["bias"]
        print(
            f"  {w:6s} : mu={res['bias']['mu']:.4f}, "
            f"sigma={res['bias']['sigma']:.4f}"
        )

    # 6) Évaluation sur le test (avec et sans biais)
    print("\n Evaluation sur le test (avec et sans biais)...")
    y_true_test = y_test.to_numpy()

    y_pred_no_bias = []
    y_pred_final = []

    for i in range(len(X_test)):
        h = X_test.iloc[i]["height"]
        v = X_test.iloc[i]["velocity_exp2"]
        w = weather_test.iloc[i]

        preds = predict_final_one(
            weather=w,
            height=h,
            velocity_exp2=v,
            coef_means=coef_means,
            intercept_mean=intercept_mean,
            alpha_means=alpha_means,
            bias_v2=bias_v2,
        )

        y_pred_no_bias.append(preds["no_bias"])
        y_pred_final.append(preds["final"])

    y_pred_no_bias = np.array(y_pred_no_bias)
    y_pred_final = np.array(y_pred_final)

    metrics_no_bias = compute_metrics(y_true_test, y_pred_no_bias)
    metrics_final = compute_metrics(y_true_test, y_pred_final)

    print("\n=== Performances globales sur le test ===")
    print("Sans biais :")
    for k, v in metrics_no_bias.items():
        print(f"  {k:6s} : {v:.4f}")

    print("Avec biais (V2) :")
    for k, v in metrics_final.items():
        print(f"  {k:6s} : {v:.4f}")

    # 7) Export YAML
    export_data = {
        "model_info": {
            "name": "Pedestrian_Pedestrian_Model",
            "version": "1.0",
            "description": (
                "Modele analytique predictif du temps minimal de non-traversee "
                "incluant coefficients globaux, alphas meteo, et biais (mu, sigma) "
                "du pipeline V2."
            ),
            "generated_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "coefficients_global": {
            "a_height": float(coef_means[0]),
            "b_height2": float(coef_means[1]),
            "c_velocity": float(coef_means[2]),
            "intercept": float(intercept_mean),
        },
        "weather_parameters": {},
        "metrics_test": {
            "no_bias": metrics_no_bias,
            "final": metrics_final,
        },
    }

    for w in ["clear", "rain", "night"]:
        export_data["weather_parameters"][w] = {
            "alpha_weather": alpha_means[w],
            "bias": bias_v2[w],
        }

    output_file = SAVE_DIR / "final_model.yaml"
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(export_data, f, allow_unicode=True, sort_keys=False)

    print(f"\n Modele exporte dans : {output_file.resolve()}")

    # 8) Rapport texte
    report_lines = [
        "=== Model Training Report ===",
        "",
        f"Generated on : {export_data['model_info']['generated_on']}",
        "",
        "Global coefficients (CV mean):",
        *(f"  {name:10s}: {val:.4f}" for name, val in zip(FEATURES_GLOBAL, coef_means)),
        f"  intercept : {intercept_mean:.4f}",
        "",
        "Alphas (per weather):",
        *(f"  {w:6s}: {a:.4f}" for w, a in alpha_means.items()),
        "",
        "Bias V2 (mu, sigma) per weather:",
        *(f"  {w:6s}: mu={bias_v2[w]['mu']:.4f}, sigma={bias_v2[w]['sigma']:.4f}"
          for w in ["clear", "rain", "night"]),
        "",
        "Test performance (no bias):",
        *(f"  {k:6s}: {v:.4f}" for k, v in metrics_no_bias.items()),
        "",
        "Test performance (final model with bias):",
        *(f"  {k:6s}: {v:.4f}" for k, v in metrics_final.items()),
        "",
    ]

    perf_path = LOG_DIR / "performance.txt"
    with open(perf_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"Rapport de performance sauvegarde dans : {perf_path.resolve()}")


if __name__ == "__main__":
    main()
