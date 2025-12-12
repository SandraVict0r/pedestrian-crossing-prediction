# Pour comprendre le déroulement complet des expériences

Avant de lancer les scripts Python, consulter :

[**→ `experience_flow.md`**](experience_flow.md)

Ce document décrit :

* le déroulement d’un trial (spawn, accélération, tracking, destruction du véhicule) ;
* la logique des deux expériences (TTC Estimation et Crossing Decision) ;
* les fichiers générés et leur contenu.

---

# 6. Lancer un trial via Python

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

# 7. Exécuter une session complète (27 trials)

Dans `run_full_session.py`, indiquer le fichier Excel, puis :

```powershell
py run_full_session.py
```

Le script :

* lit les 27 trials
* les exécute séquentiellement
* attend une confirmation entre chaque essai

## Vérification indispensable

Avant d’appuyer sur **Entrée** :

* vérifier que le véhicule a **disparu dans Unreal**
* sinon :

  * stopper avec `CTRL + C`
  * corriger
  * passer au trial suivant

Pour la logique détaillée du déroulement expérimental :

[**→ `experience_flow.md`**](experience_flow.md)
