

#  BaseVehiclePawn – Blueprint véhicule modifié (CARLA)

**Chemin (version modifiée incluse dans ce dépôt) :**
`vr-experiment/unreal_project/Blueprints/BaseVehiclePawn.uasset`

**Chemin du blueprint CARLA original dans le projet Unreal :**

```
C:\Users\carlaue5.3\CarlaUE5\Unreal\CarlaUnreal\Content\Carla\Blueprints\Vehicles
```

> ℹ Le fichier fourni dans le dépôt GitHub correspond à une **version modifiée** du blueprint véhicule de CARLA.
> Cette modification ne se trouve pas dans l’installation CARLA standard et sera perdue en cas de mise à jour du plugin ou de réinstallation.
> Une re-intégration manuelle sera alors nécessaire.

---

##  Vue d’ensemble

`BaseVehiclePawn` est une version modifiée du blueprint véhicule par défaut de CARLA.
Cette version enrichie ajoute un enregistrement continu :

* de la trajectoire réelle du véhicule,
* de la trajectoire estimée (valeurs reçues via les paramètres Python),
* des vitesses réelles,
* des horodatages synchronisés.

Ces données sont nécessaires pour l’analyse de l’expérience VR et pour comparer les trajectoires **réelles** et **prédites** lors du modèle de comportement piéton.

Le blueprint est utilisé pour tous les véhicules générés pendant les trials.

---

#  Modifications ajoutées au Blueprint

La logique personnalisée se trouve dans **Event Tick** :

![basevehiclepawn](img/vehicle_pawn.PNG)

Ci-dessous se trouve la description détaillée de ce qui a été ajouté.

---

## 1. Enregistrement de la position réelle

À chaque tick :

* `Get Actor Location` → ajout dans le tableau **Position**
* `Get Velocity` → ajout dans le tableau **Velocity**

Ces tableaux ne sont pas stockés dans ce blueprint directement, mais transmis à l’`EyeTracking_Pawn`, qui centralise toutes les données avant export.

---

## 2. Enregistrement de la position estimée et du temps estimé

Pour évaluer les prédictions du modèle, deux flux supplémentaires sont enregistrés :

* **PosEstimated**
* **TimeEstimated**

Ces valeurs proviennent des paramètres envoyés lors du lancement du trial via le script Python (`generate_one_car.py` / `run_trial.py`).
Elles sont donc synchronisées avec la logique côté CARLA.

---

## 3. Gestion des horodatages

Le nœud `Get Game Time in Seconds` est utilisé pour générer un timestamp uniforme.
Ce timestamp est ajouté :

* dans `Time` (temps réel),
* dans `TimeEstimated` (temps estimé),
* et indirectement dans les fichiers `cars.csv`.

L’objectif est d’assurer une synchronisation parfaite entre toutes les séries temporelles.

---

#  Résumé du flux de données

| Signal           | Source                     | Stockage                           | Sauvegarde CSV    |
| ---------------- | -------------------------- | ---------------------------------- | ----------------- |
| Position réelle  | `Get Actor Location`       | `EyeTracking_Pawn.Position[]`      | `Save Car Data`   |
| Vitesse réelle   | `Get Velocity`             | `EyeTracking_Pawn.CarVelocity[]`   | `Save Car Data`   |
| Position estimée | Paramètre Python           | `EyeTracking_Pawn.PosEstimated[]`  | `Save Car Data`   |
| Temps estimé     | Paramètre Python           | `EyeTracking_Pawn.TimeEstimated[]` | `Save Car Data`   |
| Horodatage       | `Get Game Time in Seconds` | Tous les tableaux de temps         | Tous fichiers CSV |

---

#  Documentation associée

Ce blueprint s’intègre dans un pipeline complet avec :

*  **[EyeTracking_Pawn.md](../Blueprints/Eye_tracking_pawn.md)**
  Acteur principal du participant, centralise les données et interagit avec CARLA.

*  **[CSV_File.md](../Blueprints/CSV_File.md)**
  Bibliothèque Blueprint responsable de la conversion des données en CSV.

*  **[RWText.md](../CppClass/RWText.md)** *(backend C++)*
  Gestion des fichiers, création des dossiers, écriture disque.

---

#  Notes d’utilisation

* Le blueprint n’altère pas la physique du véhicule.
* Les modifications concernent uniquement l’enregistrement des données.
* En cas de mise à jour du plugin CARLA ou de ré-importation du dossier `Carla/`, les modifications devront être réappliquées manuellement.
* Cette implémentation est spécifique au projet **Unreal Engine 5.3.2 + CARLA modifié** utilisé dans la thèse.
  Elle n’est pas compatible telle quelle avec les distributions officielles de CARLA.

