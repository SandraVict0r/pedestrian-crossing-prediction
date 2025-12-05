# RWText — Backend C++ pour l’export des données expérimentales


La classe `URWText` implémente le backend C++ responsable de l’écriture de l’ensemble des données enregistrées au cours des expériences VR.
Elle est exposée à Unreal Engine sous la forme d’une **Blueprint Function Library**, ce qui permet son appel direct depuis les Blueprints sans instanciation.

Elle intervient dans l’export des :

* trajectoires du participant,
* trajectoires réelles et estimées du véhicule,
* données de suivi oculaire,
* signal de crossing (optionnel, non utilisé dans la version finale).

Les Blueprints qui en dépendent sont :

* [`CSV_File` —](../Blueprints/CSV_File.md) gestion des buffers et déclenchement des sauvegardes,
* [`EyeTracking_Pawn` —](../Blueprints/Eye_tracking_pawn.md) collecte des données VR et oculaires,
* [`BaseVehiclePawn` —](../Blueprints/BaseVehiclePawn.md) acquisition des données véhicule.

---

# Structure de la classe

`RWText` est constituée de deux fichiers :

* **`RWText.h`** : déclarations, fonctions exposées aux Blueprints
* **`RWText.cpp`** : implémentation détaillée (gestion des chemins, création des répertoires, génération des CSV)

Définition de la classe :

```cpp
UCLASS()
class CARLA_API URWText : public UBlueprintFunctionLibrary
```

Caractéristiques :

* aucune instance nécessaire (toutes les fonctions sont statiques),
* bibliothèque accessible directement dans les Blueprints,
* intégration dans le module C++ du plugin CARLA.

---

# Répertoire d’export : `Logs/<N>/`

Les exportations sont réalisées dans :

```
<UnrealProject>/Logs/<N>/
```

où `<N>` est un entier automatiquement incrémenté à chaque trial.
La création du répertoire est assurée **uniquement par `PedsToCSV()`**, les fichiers suivants (`cars.csv`, `gaze.csv`) étant ensuite écrits dans le même dossier.

Chaque trial produit ainsi un dossier autonome :

```
Logs/
 ├── 1/
 │    ├── peds.csv
 │    ├── cars.csv
 │    └── gaze.csv
 ├── 2/
 │    ├── peds.csv
 │    ├── cars.csv
 │    └── gaze.csv
 ...
```

Ce mécanisme garantit une séparation stricte des essais pour les analyses post-expérience.

---

# Fonctions exposées

Les fonctions suivantes sont disponibles directement depuis les Blueprints.

---

## 1. LoadTxt

```cpp
static bool LoadTxt(FString FileName, FString& SaveText);
```

Lecture d’un fichier texte brut.
Utilisée principalement à des fins de diagnostic ou pour charger des configurations simples.

---

## 2. SaveTxt

```cpp
static bool SaveTxt(FString SaveText, FString FileName);
```

Écriture d’une chaîne de caractères dans un fichier texte.
Non utilisée par le pipeline VR, mais disponible pour des utilitaires internes.

---

## 3. PedsToCSV — Création du répertoire `Logs/<N>/`

```cpp
static bool PedsToCSV(TArray<FVector> pos_vector,
                      TArray<FVector> rot_vector,
                      TArray<float> time,
                      TArray<float> crossing);
```

Cette fonction constitue le point d’entrée du pipeline d’export.
Elle :

* crée un nouveau dossier `Logs/<N>`,
* génère `peds.csv`,
* initialise l’environnement pour les autres fichiers du même trial.

Format du fichier :

```
Time;X_pos;Y_pos;Z_pos;X_rot;Y_rot;Z_rot;Crossing
```

La fonction est appelée lorsque l’expérimentateur presse la touche **S** dans Unreal.

---

## 4. CarsToCSV

```cpp
static bool CarsToCSV(TArray<FVector> pos_vector,
                      TArray<FVector> vel_vector,
                      TArray<float> time,
                      TArray<float> time_estimated,
                      TArray<FVector> pos_estimated);
```

Écrit les données relatives au véhicule dans :

```
Logs/<N>/cars.csv
```

Format :

```
Time;Time_estimated;X_pos;Y_pos;Z_pos;X_est;Y_est;Z_est;X_vel;Y_vel;Z_vel
```

Le fichier combine :

* la trajectoire réelle du véhicule CARLA,
* la trajectoire estimée (définie par Python),
* les vitesses issues de CARLA,
* les horodatages synchronisés.

---

## 5. GazeToCSV

```cpp
static bool GazeToCSV(TArray<FVector> gaze_origin,
                      TArray<FVector> gaze_direction,
                      TArray<FVector> fixation_point,
                      TArray<float> confidence_value,
                      TArray<float> time);
```

Export des signaux oculaires (Meta XR) au format :

```
Time;X_origin;Y_origin;Z_origin;X_direction;Y_direction;Z_direction;X_fixation;Y_fixation;Z_fixation;Confidence
```

Dans la configuration actuelle, `fixation_point` n’est pas renseigné par Meta Quest Pro (toujours nul).

---

## 6. CrossToCSV *(non utilisé)*

```cpp
static bool CrossToCSV(TArray<float> time,
                       TArray<float> crossing);
```

Fonction prévue initialement pour exporter un fichier `cross.csv`.
Aucune partie du projet final ne l’appelle.

---

## 7. GetDirectories

```cpp
static TArray<FString> GetDirectories();
```

Retourne la liste des sous-répertoires existants dans `Logs/`.
Elle est utilisée pour déterminer le prochain identifiant `<N>` lors de la création d’un nouveau trial.

---

# Schéma du pipeline d’écriture

```
EyeTracking_Pawn -------------------------------+
                                                |
                                                v
                                   CSV_File (Blueprint layer)
                              (gestion des buffers et appels C++)
                                                |
                                                v
                                        RWText (C++)
                              (création dossier + écriture CSV)
                                                |
                   +-------------+--------------+----------------+
                   |             |                               |
                peds.csv      cars.csv                      gaze.csv
```

---

# Points techniques importants

* Conçu spécifiquement pour **Unreal Engine 5.3.2**.
* Intégré au plugin CARLA et non au contenu Blueprint classique.
* Chemins d’accès dépendants de Windows (convention du projet).
* CSV avec séparateur `;` pour compatibilité Excel (locale FR).
* Écriture synchrone : l’intégrité des fichiers est garantie dès validation par la touche **S**.

---

# Documentation complémentaire

* [`CSV_File.md`](../Blueprints/CSV_File.md) — interface Blueprint
* [`EyeTracking_Pawn.md`](../Blueprints/Eye_tracking_pawn.md) — données VR + eye tracking
* [`BaseVehiclePawn.md`](../Blueprints/BaseVehiclePawn.md) — données véhicule

---

# Intégration dans l’arborescence Unreal Engine

La classe doit impérativement être placée dans le module C++ du plugin CARLA :

```
CarlaUnreal/
 └── Plugins/
     └── Carla/
         └── Source/
             └── Carla/
                 ├── Public/
                 │     └── RWText.h
                 └── Private/
                       └── RWText.cpp
```

Chemins spécifiques de la machine d’acquisition :

```
C:\Users\carlaue5.3\CarlaUE5\Unreal\CarlaUnreal\Plugins\Carla\Source\Carla\Public\RWText.h
C:\Users\carlaue5.3\CarlaUE5\Unreal\CarlaUnreal\Plugins\Carla\Source\Carla\Private\RWText.cpp
```

---

# Procédure en cas d’absence de RWText.*

Si le plugin CARLA a été remplacé ou mis à jour, il est possible que `RWText.*` soit absent.
Reconstruction manuelle :

1. Créer une nouvelle classe C++ via **Tools → New C++ Class**.
2. Choisir **Blueprint Function Library**.
3. Nommer la classe `RWText`.
4. L’associer au module **Carla** (ou `CarlaUnreal` si non disponible).
5. Remplacer le contenu généré par les versions fournies dans ce dépôt.
6. Recompiler le projet.

Note : le plugin CARLA n’étant pas prévu initialement pour UE5.3.2, un **Rebuild complet** peut être requis.

---

# Compilation

Après ajout ou modification des fichiers :

* Recompiler via Unreal Engine (popup « Recompile »), ou
* Utiliser Visual Studio : *Build → Rebuild*, ou
* Lancer une compilation manuelle :

```
UnrealBuildTool.exe CarlaUnrealEditor Win64 Development
```

Si la compilation échoue, les Blueprints dépendants (`CSV_File`, `EyeTracking_Pawn`, `BaseVehiclePawn`) ne seront pas disponibles et le pipeline VR deviendra inopérant.
