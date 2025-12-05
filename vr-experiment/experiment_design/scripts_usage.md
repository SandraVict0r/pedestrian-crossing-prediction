# **Scripts de génération et d’exécution des trials**

## VR Experiment — CARLA × Unreal Engine 5.3.2

Ce document décrit les scripts Python utilisés pour :

* générer automatiquement les plans de passation pour chaque participant,
* lancer un trial individuel dans CARLA,
* exécuter toute une session (27 trials) pour un participant.

Ces scripts sont situés dans :

```
C:\Users\carlaue5.3\Documents\pedestrian-crossing-prediction\vr-experiment\scripts\
```

Ils fonctionnent en combinaison avec la logique Unreal Engine décrite dans : [**`parameters_exposed_to_python.md`**](parameters_exposed_to_python.md)

---

# **Liste des scripts**

| Script                                          | Rôle                                                                                                | Expérience |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------- | ---------- |
| `generate_participant_plan_exp1.py`             | Génère le plan de 27 trials pour Expérience 1 (vitesse × distance × météo)                          | Exp 1      |
| `generate_participant_plan_exp2.py`             | Génère le plan de 27 trials pour Expérience 2 (un groupe de vitesses × météo × positions)           | Exp 2      |
| `run_trial.py` *(ancien : generate_one_car.py)* | Exécute un seul trial dans CARLA/Unreal avec les paramètres fournis                                 | Exp 1 & 2  |
| `run_full_session.py`                           | Exécute séquentiellement les 27 trials d’un participant (lecture Excel → exécution trial par trial) | Exp 1 & 2  |

---

#  **1. Description détaillée des scripts**

---

##  **`generate_participant_plan_exp1.py`**

### Objectif

Génère un fichier Excel par participant contenant **27 commandes** pour Expérience 1.

Chaque commande correspond à :

* une vitesse parmi un groupe de vitesses,
* une distance d’apparition du véhicule,
* un type de météo : *clear / night / rain*,
* une position du player (0,1,2).

Résultat :
`participant_<ID>_commands_exp1.xlsx`

### Contenu de chaque ligne

* Velocity
* Distance
* Weather
* Position
* Command (ligne Python pour lancer le trial)

### Lancer le script

```bash
py generate_participant_plan_exp1.py
```

---

##  **`generate_participant_plan_exp2.py`**

### Objectif

Génère un plan de 27 trials par participant pour Expérience 2.

Différence avec Exp 1 :

* ici **un seul groupe de vitesses** est tiré aléatoirement pour tout le participant,
* mais les météos et positions sont combinées avec toutes les vitesses du groupe.

 Résultat :
`participant_<ID>_commands_exp2.xlsx`

### Lancer le script

```bash
py generate_participant_plan_exp2.py
```

---

##  **`run_trial.py`**

*(ex `generate_one_car.py`, mais sans modifier ton code)*

### Objectif

Lance **un seul trial** en :

1. se connectant au serveur CARLA,
2. définissant météo / position / vitesse selon les arguments,
3. spawnant 3 “tokens” (véhicule, météo, player) utilisés par Unreal :

   * voir  [`parameters_exposed_to_python.md`](parameters_exposed_to_python.md)
4. pilotant le véhicule jusqu’à disparition.

### Exemple d’appel (issu des fichiers Excel)

```bash
 py run_trial.py -v 40 -d 60 -pos 2 -r True -c True
```
Cette commande téléporte le participant à la 3e position dans la foret (-pos 2) , affiche la météo rain (-r True -c True), spawn un vehicle de type sedan qui aura une vitesse de 40 km/h et disparaitra à 60 m du piéton.
### Important

Unreal doit détecter la disparition du véhicule (condition de fin du trial).

---

##  **`run_full_session.py`**

### Objectif

Exécuter **les 27 trials** d’un participant à partir du fichier Excel généré.

### Fonctionnement

1. Lit la colonne `Command` du fichier Excel
2. Exécute chaque commande l’une après l’autre
3. Affiche le numéro du trial
4. Attend une validation utilisateur entre chaque trial

>  **Très important pour l’opérateur VR**
> Avant d'appuyer sur *Entrée* pour lancer le trial suivant :
>  **vérifier dans Unreal que la voiture a bien disparu**
> (sinon, interrompre avec `CTRL+C`, ajuster, puis reprendre au trial suivant)

### Lancer la session

```bash
py run_full_session.py
```

---

#  **2. Ordre d’exécution complet (passation VR)**

1. **Générer les plans de passation**

   * Exp 1 :

     ```bash
     py generate_participant_plan_exp1.py
     ```
   * Exp 2 :

     ```bash
     py generate_participant_plan_exp2.py
     ```

2. **Sélectionner le fichier du participant**

   * Exemple : `participant_2_commands_exp1.xlsx`

3. **Lancer la session complète**

   ```bash
   py run_full_session.py
   ```

4. **À chaque trial**

   * vérifier que CARLA/Unreal a correctement lancé la scène
   * une fois terminé :
     - vérifier que la voiture a disparu
     - appuyer sur *Entrée* pour passer au trial suivant

---

#  **3. Points critiques à surveiller pendant la passation**

###  Vérifier que CARLA et Unreal sont bien connectés

* CARLA doit tourner en mode *server*
* Unreal doit être en mode VR preview

###  Ne jamais relancer Unreal entre deux trials

* cela casse la synchro des tokens
* utiliser les pauses entre les trials pour corriger des problèmes

###  Toujours vérifier la disparition du véhicule avant d’appuyer sur Entrée

###  Si un trial échoue

* le script s’arrête automatiquement
* relancer manuellement à partir du trial suivant
* noter le numéro du trial à répéter

---

#  **4. Référence importante**

Pour comprendre **comment les variables Python (météo, position, vitesse)** sont interprétées par Unreal :

 Voir : [parameters_exposed_to_python.md](./parameters_exposed_to_python.md)


Ce fichier décrit comment les Blueprints Unreal détectent les “tokens” spawnés par CARLA (véhicule, météo, player) afin d’activer les bonnes conditions visuelles et logiques.

