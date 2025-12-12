# Déroulement complet des expériences VR

Document de référence pour la reproduction et la compréhension du protocole

---

## 1. Introduction

Ce document décrit le déroulement des deux expériences VR utilisées dans la thèse :

1. **Expérience 1 — TTC Estimation Experiment**
   Le participant indique le moment estimé où la voiture atteindrait sa position.

2. **Expérience 2 — Crossing Decision Experiment**
   Le participant indique en continu s’il se sent capable de traverser devant le véhicule approchant.

Les expériences ont été développées sous **Unreal Engine 5.3.2**, intégrant une version modifiée de **CARLA** non disponible publiquement.
Les paramètres expérimentaux (spawn, vitesse, météo, distances) sont contrôlés par des scripts Python.

Les données issues des interactions VR sont automatiquement exportées au format CSV pour analyse.

---

## 2. Vue générale du pipeline

```
+----------------------+         +----------------------------+
| Scripts Python       | spawn   | Unreal Engine 5.3.2        |
| - run_trial.py       +-------> | - EyeTracking_Pawn         |
| - run_full_session.py| params  | - BaseVehiclePawn          |
+-----------+----------+         | - CSV_File (BP) → RWText   |
            |                    +--------------+-------------+
            |                                   |
            | save                               v
            |                          +------------------------------+
            +------------------------->| Dossiers Logs/<N>/           |
                                       | - peds.csv                   |
                                       | - cars.csv                   |
                                       | - gaze.csv                   |
                                       +------------------------------+
```

---

## 3. Déroulé global d’une session

Chaque session suit les étapes suivantes :
1. [Préparer l'expérimentation](prepare_experiment.md)
2. [Péparer le système](setup.md). Unreal Engine doit être lancé **avant** d’appliquer les étapes ci-dessous.
3. Installation du participant. Mettre le casque sur le paricipant et le préparer à faire l'XP.
4. [Exécution du script implémentant l'expérience](execution.md)

---
