# 📘 **Blueprint Overview**

*(Version mise à jour avec BaseVehiclePawn et lien vers BaseVehiclePawn.md)*

Ce document présente l’ensemble des Blueprints utilisés dans le projet Unreal de l’expérience VR.
Il décrit leur rôle, leur état d’utilisation (actif ou non), et fait le lien vers les documents détaillés pour les Blueprints essentiels.

Les deux Blueprints les plus importants disposent de leur documentation complète :

- **[EyeTracking_Pawn.md](Eye_tracking_pawn.md)**
- **[CSV_File.md](CSV_File.md)**

Le Blueprint du véhicule CARLA modifié, **BaseVehiclePawn**, aura une documentation spécifique disponible ici :

**[BaseVehiclePawn.md](BaseVehiclePawn.md)** 

---

# Contenu du dossier Blueprints

```
Blueprints/
│
├── Eye_tracking_pawn.uasset
├── Eye_tracking_pawn.md
│
├── CSV_file.uasset
├── CSV_File.md
│
├── BaseVehiclePawn.uasset
├── BP_Fog.uasset
├── BP_TrialManager.uasset
├── VR_pawn.uasset
│
├── beep-104060.uasset
├── ExponentialCurve.uasset
│
├── M_blue.uasset
├── M_red.uasset
├── M_white.uasset
│
└── WBP_TrialToast.uasset
```

Les sections ci-dessous expliquent chacun de ces Blueprints.

---

#  1. EyeTracking_Pawn (PRINCIPAL)

 Documentation complète : **[Eye_tracking_pawn.md](Eye_tracking_pawn.md)**
Blueprint central qui gère tout le comportement VR, eye tracking, logging, météo dynamique et interactions de l’expérience.

---

#  2. CSV_File (PRINCIPAL)

Documentation complète : **[CSV_File.md](CSV_File.md)**
Blueprint interface qui appelle les fonctions C++ du backend `RWtext` pour écrire les CSV logs.

---

# 3. BaseVehiclePawn (IMPORTANT)

Documentation : **[BaseVehiclePawn.md](BaseVehiclePawn.md)** 

Blueprint modifié du véhicule CARLA utilisé pour :

* ajuster l’accélération du véhicule,
* utiliser `ExponentialCurve` pour atteindre plus rapidement la vitesse cible,
* garantir une vitesse stable et cohérente avec le protocole expérimental.

Ce Blueprint contient les modifications nécessaires pour que le véhicule :

* se comporte correctement dans CARLA version Unreal,
* reste synchro avec Python, y compris lors du spawn via script.

---

# 4. BP_Fog

Blueprint contrôlant la couche de brouillard.
Appelé par EyeTracking_Pawn lors de la météo `"rain"`.

---

# 5. beep-104060

Sound cue utilisé pour :

* indiquer le début d’un trial
* notifier le participant que la voiture spawnée est en approche

---

# 6. BP_TrialManager

Un système de toast (UI) pour afficher :

* prédiction instantanée
* état du participant

**Actuellement désactivé** : doit être placé dans la map pour fonctionner.

---

# 7. ExponentialCurve

Fonction mathématique utilisée dans BaseVehiclePawn :

* augmente progressivement l’accélération du véhicule
* donne un ressenti plus naturel
* garantit que la vitesse cible est atteinte rapidement

---

# 8. VR_Pawn

Version Unreal Engine 4 du pawn VR.
Conservée uniquement pour référence historique.

---

# 9. M_blue / M_red / M_white

Matériaux appliqués aux véhicules spawn pour :

* sedan → bleu
* camionnette → blanc
* city car → rouge

---

# 10. WBP_TrialToast

Widget du toast UI.
Fait partie de BP_TrialManager mais désactivé.

