

# 📘 **README — Unreal Blueprints Integration (UE 5.3.2)**

## Communication entre CARLA (Python) et Unreal Engine via Blueprints

Ce document explique comment l’expérience VR utilise **des véhicules spawnés dans CARLA** comme *tokens* pour transmettre des paramètres au projet Unreal Engine 5.3.2.

Ce mécanisme est crucial :
* **CARLA ne peut pas passer directement des variables Python aux Blueprints Unreal**,
* donc les Blueprints lisent la présence et le type d’acteurs spawnés pour déterminer la configuration du trial.

Ce système fonctionne pour **l’expérience 1 et 2**, pilotées par ton script Python (run_trial.py).

---

# 🧩 **1. Vue générale du système**

Lorsque `run_trial.py` démarre un trial, il spawn **trois acteurs CARLA** :

1. **Vehicle Blueprint** (véhicule autopiloté principal)
2. **Weather Blueprint** (token météo)
3. **Player Blueprint** (ancrage / repère player)

Unreal lit ensuite :

* **leur type (blueprint class)**
* **leur position (spawn point)**
* **leur ordre d’apparition**

pour sélectionner la configuration correcte.

---

# 🚗 2. Vehicle Blueprint (véhicule autopiloté)

### *Blueprint UE associé :* `BP_ExperimentController` ou équivalent dans ton projet

Ce véhicule est utilisé pour :

* l’animation de l’expérience (approche du véhicule),
* le calcul visuel du TTC,
* l’affichage de la dynamique dans la scène VR.

Dans Unreal :

* Le Blueprint événementiel **BeginPlay** détecte ce véhicule (par son Tag ou Class).
* Il est enregistré comme **véhicule principal**.
* Les scripts VR utilisent ce véhicule pour lire sa position et mettre à jour l’environnement VR.

**Ce n’est PAS un véhicule affiché seulement visuellement : c’est la source principale du mouvement de la scène.**

---

# 🌦️ 3. Weather Blueprint (token météo)

CARLA spawn un véhicule spécial selon la météo :

| Paramètres Python       | Blueprint CARLA  | Interprétation Unreal |
| ----------------------- | ---------------- | --------------------- |
| `[False, False, False]` | Chevrolet Impala | Clear weather         |
| `[False, False, True]`  | Dodge Charger    | Night / lights on     |
| `[True, True, False]`   | Ford Taxi        | Rain + clouds         |

## ➤ Comment Unreal lit la météo ?

Dans Unreal :

1. Un Blueprint (souvent `BP_EnvironmentController`) scanne les acteurs présents dans la scène CARLA importée.
2. Si un véhicule est détecté :

   * **de type Impala → Clear**
   * **de type Charger → Night / lights**
   * **de type Taxi → Rain**
3. Le Blueprint applique alors :

   * les paramètres de SkyAtmosphere
   * les PostProcessVolume
   * les Niagara effects (rain)
   * les lights

➡ **Le véhicule n’est pas affiché au joueur : il est utilisé comme variable de configuration.**

---

# 🧍 4. Player Blueprint (ancrage player)

Même s’il n’est plus directement visible dans la version finale, Unreal s’en sert toujours.

Il permet à Unreal de savoir :

* où placer le player dans le monde UE
* quelle orientation adopter
* quel “design d’expérience” activer (exp 1 ou 2)
* où positionner la caméra, les colliders, les triggers
* la zone de crossing (ligne virtuelle)

## ➤ Lecture par Unreal

Dans `BP_PlayerController` ou `BP_ExperimentController` :

* Unreal scanne les acteurs CARLA pour trouver le “player token”.
* Sa **classe** et **position** définissent :

  * le scénario (exp 1 ou exp 2)
  * l’emplacement initial du piéton VR
  * la logique spécifique (ex : animations, hints, resets…)

➡ **Même s’il n’apparaît pas visuellement, ce Blueprint est obligatoire.**

---

# 🔧 5. Localisation des Blueprints et dépendances

### Principaux Blueprints Unreal utilisés dans l’expérience

| Blueprint UE                | Rôle                                             |
| --------------------------- | ------------------------------------------------ |
| `BP_ExperimentController`   | Logique générale du trial (début, fin, triggers) |
| `BP_EnvironmentController`  | Sélection de météo via vehicle token             |
| `BP_PlayerControllerVR`     | Gestion du piéton / caméras                      |
| `BP_PlayerStartTokenReader` | Lecture du player blueprint CARLA                |
| `BP_MeteorologySwitcher`    | Activation pluie / ciel / lumières               |

*(Noms à adapter selon ton projet si besoin — je peux te les renommer si tu me envoies une capture du Content Browser.)*

---

# 📡 6. Comment Unreal lit les “tokens” (processus exact)

1. **Au lancement**, un Blueprint (souvent dans le Level Blueprint) exécute :

   ```
   Get All Actors of Class (Vehicle)
   ```

2. Pour chaque acteur, il vérifie sa **classe** :

   * `class contains "impala"` → `Weather = Clear`
   * `class contains "charger"` → `Weather = Lights`
   * `class contains "taxi"`   → `Weather = Rain`

3. Il vérifie aussi sa **position dans la map** ou son **SpawnPoint index** pour :

   * déduire le scénario (exp1/exp2)
   * initialiser le player à la bonne distance
   * placer la caméra VR correctement

4. Il applique les réglages météo, lumière et environnement.

➡ **Donc les Blueprints Unreal ne reçoivent pas directement les arguments Python, mais lisent l’état du monde CARLA.**

---

# 📝 7. Bonnes pratiques pour modifier ou étendre ce système

* Ne jamais supprimer les trois spawn CARLA (vehicle, weather, player)
* Ne jamais renommer les Blueprints détectés sans mettre à jour la table de lecture
* Pour ajouter une nouvelle météo :

  * ajouter un nouveau blueprint token dans Python
  * l’ajouter dans le Blueprint “switch” dans UE
* Pour ajouter une nouvelle expérience (Exp3) :

  * ajouter une nouvelle position Player ou un nouveau Player BP
  * adapter le Level Blueprint

