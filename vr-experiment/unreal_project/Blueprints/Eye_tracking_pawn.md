# EyeTracking_Pawn — Blueprint Documentation


Ce Blueprint est l’élément central de toute l’expérience VR.
Il fait le lien entre :

* les **actions du participant** (inputs du casque VR et des controllers),
* les données récupérées depuis **CARLA** (position/vitesse du véhicule),
* les **systèmes d’eye-tracking** (Meta Quest Pro),
* les scripts Python (météo, spawn, scénario),
* et le système d’**enregistrement des logs**.

Ce Blueprint agit comme la **carte mère** de l’expérience.

---

#  Contenu du Blueprint

* **Événements principaux :**

  * `Event BeginPlay`
  * `Event Tick`
  * `InputAction Save`
  * `InputAction ClearData`
  * `InputAction Snap_Time` (Exp 1)
  * `InputAxis Press_Cross` (Exp 2)

* **Fonctions internes :**

  * `Get Car`
  * `Get Car Datas`
  * `Snap Cross Time`
  * `Snap Car Pos`
  * `Get Weather`
  * `Set Weather`
  * `Set Fog`
  * `Set Sky`
  * `Clear Data`
  * `Set Intensity`
  * `Get Position`
  * `Set Position`

* **Variables principales :**

| Catégorie                 | Variables                                                                                                                                       |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Environnement / Météo** | Weather, Weather_type, Fog, DayRotation, isWeather                                                                                              |
| **Participant**           | Position, Rotation, PlayerPosition, PlayerRotation, LastLocation, IsPositioned                                                                  |
| **Eye Tracking**          | Gaze Origin, Gaze Direction, Fixation Point, Confidence Value, Left Pupil Diameter, Right Pupil Diameter, Is Left Eye Blink, Is Right Eye Blink |
| **Voiture CARLA**         | BP Car, Car Position, Car Velocity, Time_Car, Pos Estimated, Time Estimated                                                                     |
| **Crossing**              | Crossing, Time_Crossing                                                                                                                         |
| **Divers**                | CurrentLocation, Time, IsCar                                                                                                                    |

Toutes ces variables sont enregistrées frame-by-frame puis sauvegardées à la fin de chaque trial.

---

#  1. BeginPlay – Initialisation du Pawn

![beginplay](img/event_begin_play.png)
Cette section initialise le Pawn lorsqu’Unreal charge la scène VR.

Fonctions principales :

* `Set Tracking Origin → Floor Level`
  Positionne le tracking XR sur le sol de la salle.

* `Set Eye Tracked Player`
  Définit quel contrôleur XR reçoit les données oculaires.

* `Get All Actors Of Class (BP Fog / BP Weather)`
  Récupère les références aux objets de météo pour les modifier dynamiquement.

---

#  2. Enregistrement des données (Save Data)

![savedata](img/save_data.png)

Cette section est déclenchée lorsqu’on appuie sur **S**.
Elle enregistre, dans l’ordre :

### 2.1 Save Peds Data

* Position du participant
* Rotation
* Temps
* Crossing

### 2.2 Save Gaze Data

* Origine du regard
* Direction du regard
* Point de fixation
* Blink gauche/droit
* Confidences
* Pupilles
* Timestamp

### 2.3 Save Car Data

* Position
* Vitesse
* Time_Car (temps interne voiture)
* Pos Estimated / Time Estimated (prédiction)

### 2.4 Clear Data

Efface les buffers pour le trial suivant.

Les fichiers sont écrits dans :

```
C:\Users\carlaue5.3\CarlaUE5\Unreal\CarlaUnreal\Logs
```

---

#  3. Interaction participant — Expérience 1

![snaptime](img/snap_time.png)

###  Contrôle : **Trigger du contrôleur droit**

Le participant appuie **une seule fois** lorsque :

* il décide qu’il peut traverser,
* ou qu’il ne le peut plus.

Cela déclenche :

* `Snap Car Pos` → capture la position du véhicule à l’instant T
* enregistrement du `Time_Crossing`
* log + bip sonore

---

#  4. Interaction participant — Expérience 2

![presscross](img/press_cross.png)

###  Contrôle : **Trigger du contrôleur gauche (continu)**

Le participant :

* **maintient pressé** lorsqu’il pense pouvoir traverser,
* **relâche** lorsqu’il n’est plus sûr.

Un changement d’état déclenche :

* `Snap Cross Time`
* mise à jour de la variable `CrossValue`
* enregistrement du timestamp
* log debug

Cette interaction crée une **courbe continue d’intention**.

---

#  5. Commande ClearData

![cleardata](img/clear_data.PNG)
###  Touche C

Efface les données sans sauvegarder.

**À utiliser seulement pour corriger un bug ou réinitialiser un trial.**
 Sinon : données perdues.

---

#  6. Event Tick — Enregistrement continu (frame-by-frame)

![eventtick](img/event_tick1.PNG) 
![eventtick](img/event_tick2.PNG)

L’Event Tick est très long, il enregistre à chaque **frame** :

### **1. Position & Rotation du participant**

* `Get HMD Data`
* extraction position + quaternion rotation
* normalisation
* stockage dans les arrays dédiés

### **2. Météo**

* vérification si un BP Weather existe
* mise à jour dynamique selon les variables Python

### **3. Position & vitesse de la voiture**

* `Get Car`
* `Get Car Datas`
* mise à jour de Car Position / Velocity

### **4. Eye tracking**

* `Get Gaze Data`
* décomposition : fixation, direction, blink, pupilles
* push dans les arrays de logs

### **5. Time tracking**

* accumulateur interne pour les séries temporelles

---

#  7. Gestion de la météo (exposée au Python)

Le script Python spawn certains véhicules “dummy” utilisés comme indicateurs :

 Voir : [parameters_exposed_to_python.md](../../experiment_design/parameters_exposed_to_python.md)

* Un véhicule différent représente Clear / Night / Rain
* Le Blueprint récupère ces véhicules via :

  * `Get All Actors Of Class`
  * mapping interne vers Weather_type

Le Pawn applique ensuite :

* Fog density
* Sky rotation
* Coloration
* Rain amount
* Lightning / night lighting
* etc.

---

#  8. Sauvegarde et logique de fin de trial

Quand la voiture disparaît dans CARLA (condition dans le script Python),
l’opérateur doit presser :

###  S = Save + Clear (obligatoire entre deux trials)

###  C = Clear Only (optionnel / dépannage)

Chaque trial est indépendant.
Les logs sont ensuite fusionnés en dataset via Python.

---

#  9. Flux de données global (résumé)

```
VR Controllers → Blueprint → Arrays internes → Log (S press)
         CARLA → Python → Spawn + Météo → Blueprint
   Eye Tracking → Blueprint → Logs
```

Le Blueprint orchestre tout :

* inputs du participant
* données voiture
* eye tracking
* météo
* synchronisation temps réel
* flush des données trial par trial
