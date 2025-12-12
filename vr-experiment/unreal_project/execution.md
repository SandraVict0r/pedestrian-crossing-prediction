# Procedure d'exécution d'une expérience

Il y a deux alternatives:
- soit lancer un trial unique. Utile pour deboguer les trials.
- soit lancer l'exécution d'une expérience complète (== 27 trials). 

# 1. Lancer un trial via Python

Ouvrir PowerShell dans :

```
C:\Users\carlaue5.3\Documents\pedestrian-crossing-prediction\vr-experiment\scripts\
```

### Exemple

```powershell
py run_trial.py -v 40 -d 60 -pos 2 -r True -c True
```

Paramètres :

* `-pos 2` → position “forêt”
* `-r True -c True` → pluie + nuages
* `-v 40` → 40 km/h
* `-d 60` → disparition du véhicule à 60 m

---

# 2. Exécuter une session complète (27 trials)

Dans `run_full_session.py`, indiquer le fichier Excel, puis :

```powershell
py run_full_session.py
```

Le script :

* lit les 27 trials
* les exécute séquentiellement
* attend une confirmation entre chaque essai

## Comment lancer la bonne expérience ?

Il faut que le script `run_full_session.py` cible le bon fichier d'expérience (généré préalablement). Pour cela il faut (hélas) modifier le code qui contient le chemin vers le fichier en question: 

```python
excel_file = "participant_2_commands_exp2.xlsx"
execute_commands_from_excel(excel_file)
```


## 3 Fin du trial

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


## 4 Sauvegarde d’un trial

À la fin de chaque trial, l’expérimentateur doit impérativement respecter l’ordre suivant :

1. Cliquer sur la fenêtre Unreal (VR Preview) pour lui redonner le focus.

2. Presser S afin d’enregistrer les buffers et les réinitialiser.

3. Revenir dans le terminal Python (PowerShell).

4. Presser Entrée pour lancer le trial suivant.

5. Revenir immédiatement à la fenêtre Unreal.

Cette alternance est obligatoire.
À défaut, le participant subira des saccades ou une perte de fluidité dans le casque, car Unreal perd temporairement le focus et dégrade le rendu VR.

En fin d’expérience, les dossiers de logs doivent être déplacés **hors du répertoire Logs/**.
