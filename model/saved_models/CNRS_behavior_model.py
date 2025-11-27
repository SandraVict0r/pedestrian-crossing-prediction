"""
CNRS_behavior_model.py
----------------------

Pedestrian Non-Crossing Time Threshold Model (final adjusted version)

Ce script implémente le modèle final basé sur :

    T_pred   = a*h + b*h² + c*v + intercept
    T_weather = α_weather * T_pred
    T_end     = T_weather - 2σ_weather + μ_weather   (toujours utilisé)

Interprétation :
    T_end = seuil comportemental : si le temps réel avant collision (TTC_real)
    est inférieur à T_end → le piéton NE traverse PAS.

Décision :
    - Si TTC_real >= T_end  → traverse (True)
    - Si TTC_real <  T_end  → ne traverse pas (False)
"""

from pathlib import Path
import yaml


# ============================================================================
# Chargement du modèle YAML
# ============================================================================

_CACHE = None

def _load_yaml():
    """Charge final_model.yaml (une seule fois)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    yaml_path = Path(__file__).resolve().with_name("final_model.yaml")
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"final_model.yaml introuvable à côté de {__file__}."
        )

    with open(yaml_path, "r", encoding="utf-8") as f:
        _CACHE = yaml.safe_load(f)

    return _CACHE


def _get_coeffs():
    """Retourne les coefficients globaux du modèle."""
    params = _load_yaml()["coefficients_global"]
    return {
        "a": float(params["a_height"]),
        "b": float(params["b_height2"]),
        "c": float(params["c_velocity"]),
        "intercept": float(params["intercept"]),
    }


def _get_weather_params(weather: str):
    """Retourne alpha, mu, sigma pour une météo donnée."""
    all_wp = _load_yaml()["weather_parameters"]
    if weather not in all_wp:
        raise ValueError(f"Météo inconnue : {weather}. Choisir parmi {list(all_wp.keys())}")

    wp = all_wp[weather]
    return {
        "alpha": float(wp["alpha_weather"]),
        "mu": float(wp["bias"]["mu"]),
        "sigma": float(wp["bias"]["sigma"]),
    }


# ============================================================================
# Calcul du seuil T_end
# ============================================================================

def predict_T_end(weather: str, height_cm: float, velocity_kmh: float) -> float:
    """
    Calcule le seuil T_end (en secondes), SEULE version utilisée :

        T_pred    = a*h + b*h² + c*v + intercept
        T_weather = α_weather · T_pred
        T_end     = T_weather - 2σ + μ
    """
    coefs = _get_coeffs()
    wp = _get_weather_params(weather)

    h = float(height_cm)
    v = float(velocity_kmh)

    # Modèle de base
    T_pred = (
        coefs["a"] * h
        + coefs["b"] * (h**2)
        + coefs["c"] * v
        + coefs["intercept"]
    )

    # Effet météo
    T_weather = wp["alpha"] * T_pred

    # Ajustement final (biais V2)
    T_end = T_weather - 2 * wp["sigma"] + wp["mu"]

    return float(T_end)


# ============================================================================
# Décision de traversée + TTC
# ============================================================================

def crossing_decision(
    weather: str,
    height_cm: float,
    velocity_kmh: float,
    distance_m: float,
) -> tuple[bool, float, float]:
    """
    Retourne :
        - decision (bool)
        - T_end (float)
        - TTC_real (float)
    """
    T_end = predict_T_end(weather, height_cm, velocity_kmh)

    v_ms = velocity_kmh * 1000.0 / 3600.0
    if v_ms <= 0:
        return True, T_end, float("inf")   # véhicule arrêté → traverse

    TTC_real = distance_m / v_ms

    decision = TTC_real >= T_end
    return decision, T_end, TTC_real


# Alias historique
def pedestrian_behavior_model(weather, height, velocity, distance):
    decision, _, _ = crossing_decision(weather, height, velocity, distance)
    return decision


# ============================================================================
# CLI simple
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Pedestrian non-crossing threshold model (adjusted version)"
    )
    parser.add_argument("-weather", required=True, choices=["clear", "rain", "night"])
    parser.add_argument("-height", type=float, required=True)
    parser.add_argument("-velocity", type=float, required=True)
    parser.add_argument("-distance", type=float, required=True)

    args = parser.parse_args()

    decision, T_end, TTC_real = crossing_decision(
        args.weather, args.height, args.velocity, args.distance
    )

    print("=== Pedestrian Crossing Model ===")
    print(f"Weather       : {args.weather}")
    print(f"T_end         : {T_end:.3f} s  (adjusted)")
    print(f"TTC_real      : {TTC_real:.3f} s")
    print(f"Decision      : {decision}  (True = cross)")
