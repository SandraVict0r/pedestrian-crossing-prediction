# Procedure d'exécution d'une expérience


## 1. Lancer le script

Il y a deux alternatives:
- soit lancer un trial unique. Utile pour deboguer les trials.
- soit lancer l'exécution d'une expérience complète (== 27 trials). 


### Lancer un trial via Python

Ouvrir PowerShell dans :

```
C:\Users\carlaue5.3\Documents\pedestrian-crossing-prediction\vr-experiment\scripts\
```

#### Exemple

```powershell
py run_trial.py -v 40 -d 60 -pos 2 -r True -c True
```

Paramètres :

* `-pos 2` → position “forêt”
* `-r True -c True` → pluie + nuages
* `-v 40` → 40 km/h
* `-d 60` → disparition du véhicule à 60 m

---

### Exécuter une session complète (27 trials)

Dans `run_full_session.py` :

```powershell
py run_full_session.py
```

Le script :

* lit les 27 trials
* les exécute séquentiellement
* attend une confirmation entre chaque essai

## 3. Demander au particiant de faire la bonne actions

Suivant l'expérimentation, le participant doit réaliser des actions différentes pour atteindre des objctifs différents:

- **Expérience 1** : avec manette **droite** il doit appuyer sur la gachette **après** que la voiture est disparue **quand il pense** que la voiture est arrivée devant lui. Voir [cette page](anatomy_of_an_experiment.md#2-expérience-1--ttc-estimation-snap-crossing) pour plus de détails.
- **Expérience 2** :  avec manette **gauche** il doit maintenir la gachette appuyée **tant qu'il pense qu'il peut traverser** et la relacher **tant qu'il pense qu'il ne peut pas traverser**. Devrait commencer avec la gachette pressée. Voir [cette page](anatomy_of_an_experiment.md#3-expérience-2--continuous-crossing-decision) pour plus de détails.


## 3. Fin du trial

Le trial se termine lorsque :

* le véhicule atteint la distance de disparition définie (**Expérience 1**) ;
* le véhicule passe devant le participant, effectue un virage, puis disparaît (**Expérience 2**).

La destruction de l’acteur véhicule est confirmée côté Python par : **"Véhicule détruit"**

### !! Vérification indispensable !!

Avant d’appuyer sur **Entrée** entre 2 trials il **FAUT**:

* vérifier que le véhicule a **disparu dans Unreal**
* sinon :
  * stopper avec `CTRL + C`
  * corriger
  * passer au trial suivant


## 4. Sauvegarde d’un trial

À la fin de chaque trial, l’expérimentateur doit impérativement respecter l’ordre suivant :

1. Cliquer sur la fenêtre Unreal (VR Preview) pour lui redonner le focus.

2. Presser **Entrée** afin d’enregistrer les buffers et les réinitialiser. Cela écrit les fichiers dans un sous dossier **Logs/<n>** ou `n` est le numéro du trial courant (incrmental par rapport aux dossier logs existants).

3. Revenir dans le terminal Python (PowerShell).

4. Presser **Entrée** pour lancer le trial suivant.

5. Revenir immédiatement à la fenêtre Unreal.

Cette alternance est obligatoire.
À défaut, le participant subira des saccades ou une perte de fluidité dans le casque, car Unreal perd temporairement le focus et dégrade le rendu VR.

## 5. Exporter les logs

En fin d’expérience, les dossiers de logs doivent être déplacés **hors du répertoire Logs/**. Il faut les déplacer dans un répertoire corresondant au couple personne/expérimentation.


