"""
CNRS_behavior_model.py
----------------------

Pedestrian Crossing Behavior Model
Developed as part of the PhD thesis:
"A Neuroscience-Based Robust AI Model for Predicting Pedestrian Crossing Behavior
by Autonomous Vehicles"

This script implements a deterministic analytical model predicting whether a pedestrian
will decide to cross in front of an oncoming vehicle based on:

    - weather condition (clear, rain, night)
    - pedestrian height (cm)
    - vehicle velocity (km/h)
    - distance between vehicle and pedestrian (m)

The model combines:
    - perceptual scaling (weather-dependent α correction)
    - biomechanical parameters (height, height²)
    - vehicle kinematics (velocity in km/h)
    - empirical correction terms (standard deviation, ME)

It returns a binary decision:
    → True  = pedestrian decides to cross
    → False = pedestrian decides NOT to cross

This file can be called:
    - as a Python module (import)
    - as a standalone CLI tool (python CNRS_behavior_model.py …)

"""

import argparse


def pedestrian_behavior_model(weather, height, velocity, distance, use_adjusted=False):
    """
    Predicts whether a pedestrian will cross based on perceptual and kinematic variables.

    Parameters
    ----------
    weather : str
        One of {"clear", "rain", "night"}. Weather influences perceptual scaling α.
    height : float
        Pedestrian height in centimeters.
    velocity : float
        Vehicle speed in km/h.
    distance : float
        Current distance between the vehicle and the pedestrian in meters.
    use_adjusted : bool, optional
        If True, uses the adjusted decision threshold:
            predicted_time - 2 * std + ME
        Otherwise uses the raw predicted time.

    Returns
    -------
    bool
        True  → pedestrian decides to cross
        False → pedestrian decides NOT to cross

    Notes
    -----
    predicted_time corresponds to the internal perceptual estimate of time-to-collision
    based on the model. If real_time < predicted_time → collision perceived as imminent.
    """

    # -------------------------
    # Model coefficients
    # -------------------------

    # Base coefficients derived from fitting behavioural data (height, height², velocity)
    coefs_mean = {
        'height': -1.3614,
        'height^2': 0.0039,
        'velocity': -0.0540,
        'intercept': 126.0592
    }

    # Weather-dependent perceptual scaling α
    alphas_mean = {
        'clear': 1.0385,
        'night': 1.0008,
        'rain': 0.9681
    }

    # Standard deviations for each weather condition (uncertainty correction)
    stds = {
        'clear': 1.0,
        'night': 0.94,
        'rain': 0.72
    }

    # Mean error adjustments for model calibration
    mes = {
        'clear': 0.04,
        'night': 0.00,
        'rain': 0.00
    }

    # -------------------------
    # Check that weather is valid
    # -------------------------
    if weather not in alphas_mean:
        raise ValueError(
            f"Weather '{weather}' not recognized. "
            f"Choose among {list(alphas_mean.keys())}"
        )

    # Extract α for weather
    alpha = alphas_mean[weather]

    # Extract base coefficients
    a = coefs_mean['height']
    b = coefs_mean['height^2']
    c = coefs_mean['velocity']
    intercept = coefs_mean['intercept']

    # -------------------------
    # Compute predicted perceptual time-to-collision (perceptual TTC)
    # -------------------------
    predicted_time = alpha * (a * height + b * height**2 + c * velocity + intercept)

    # Adjusted decision threshold (more conservative)
    adjusted_time = predicted_time - 2 * stds[weather] + mes[weather]

    # -------------------------
    # Compute real TTC based on vehicle kinematics
    # Convert velocity from km/h → m/s
    # -------------------------
    velocity_m_s = velocity * 1000 / 3600

    # Avoid division by zero if input velocity = 0
    if velocity_m_s <= 0:
        velocity_m_s = 1e-9

    real_time = distance / velocity_m_s

    # -------------------------
    # Decision rule
    # -------------------------
    threshold = adjusted_time if use_adjusted else predicted_time

    # If the real TTC is smaller than perceptual TTC → pedestrian perceives danger → no crossing
    if real_time < threshold:
        return False
    else:
        return True


# ------------------------------------------------------------------------------
# CLI Interface
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pedestrian crossing behavior model (thesis version)"
    )

    parser.add_argument("-weather", required=True,
                        choices=['clear', 'rain', 'night'],
                        help="Weather condition")

    parser.add_argument("-height", type=float, required=True,
                        help="Pedestrian height in cm")

    parser.add_argument("-velocity", type=float, required=True,
                        help="Ego vehicle velocity in km/h")

    parser.add_argument("-distance", type=float, required=True,
                        help="Distance between ego vehicle and pedestrian in meters")

    parser.add_argument("--use_adjusted", action='store_true',
                        help="Use adjusted threshold (predicted_time - 2*std + ME)")

    args = parser.parse_args()

    decision = pedestrian_behavior_model(
        args.weather, args.height, args.velocity, args.distance, args.use_adjusted
    )

    print(f"Crossing decision: {decision}")
