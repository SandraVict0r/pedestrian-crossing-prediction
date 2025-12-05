# CARLA–Unreal–VR : Guide de configuration et d’exécution

### Version spécifique à ce projet, non compatible avec la version publique actuelle de CARLA

## Important

Ce projet repose sur une version **modifiée et non publique** de CARLA intégrée à **Unreal Engine 5.3.2**, développée avant la compatibilité officielle UE5.
Afin de garantir la stabilité du système, il faut **utiliser exclusivement l’installation présente sur “la tour d’Amaury”**.

Toute mise à jour non contrôlée pourrait rendre l’environnement incompatible.

---

# 1. Matériel et logiciels requis

## Casque VR

* **Meta Quest Pro**
* Utilisation obligatoire via **Quest Link** (connexion par câble USB-C)

## Logiciels

* Meta Quest Link (installé)
* Unreal Engine 5.3.2
* Version CARLA modifiée (préinstallée)
* Python 3.x
  Scripts utilisés :

```
C:\Users\carlaue5.3\Documents\pedestrian-crossing-prediction\vr-experiment\scripts\
```

## Configuration du casque (déjà effectuée)

* Mode développeur activé
* Eye tracking activé
* Guardian désactivé

### À propos des mises à jour Meta (casque + Meta Quest Link / Drive)

**Ne jamais installer de mises à jour Meta, sauf si le système vous y contraint absolument.**

Raison :
Meta peut modifier le fonctionnement du Quest Link ou des drivers sans avertissement.
Or, notre version de CARLA et d’Unreal Engine 5.3.2 est **ancienne et très spécifique**.
Une mise à jour du casque ou de Meta Quest Link **risque de casser totalement la compatibilité VR**.

Dans le casque :

* les mises à jour automatiques peuvent se lancer lorsque vous l’éteignez. Une fenêtre apparaît : **annuler systématiquement la mise à jour** ;
---

# 2. Branchement du casque et précautions

## 2.1. Ordre correct : **brancher le casque avant d’allumer le PC**

1. PC éteint
2. Brancher le **câble USB-C côté PC**
3. Brancher le **câble côté casque** en pivot (haut → bas)
   ![Branchement](img/branchement.png)
4. Allumer le casque
5. Allumer ensuite le PC

## 2.2. Fragilité du connecteur

* ne pas brancher le casque lorsqu’il est porté ;
* ne jamais forcer ;
* toujours engager la partie supérieure du connecteur en premier.

## 2.3. Message “Débris détectés dans le port USB”

Message fréquent et généralement sans importance.

Procédure :

1. Débrancher côté casque, puis côté PC
2. Valider le message dans le casque avec les contrôleurs
3. Rebrancher côté PC, puis côté casque,
4. Si le message réapparaît, recommencer

---

# 3. Vérification essentielle : être dans la *salle grise*

Après branchement :

* écran de chargement du casque
* puis **salle grise infinie**
* avec un panneau d’applications flottant (dont *Unreal Editor*)

Cela indique que **Meta Quest Link est actif**.

**Unreal Engine ne doit être lancé que si cette salle est visible.**

Si la salle n’apparaît pas :

1. Éteindre complètement le casque
2. Redémarrer le PC
3. Recommencer la procédure de branchement

---

# 4. Lancer Unreal Engine (depuis la salle grise)

Sur le bureau :

**CarlaUnreal – Raccourci**

Cible :

```
C:\Users\carlaue5.3\CarlaUE5\Unreal\CarlaUnreal\CarlaUnreal.uproject
```

La carte VR se charge automatiquement.

---

# 5. Activer la simulation VR

Dans Unreal :

1. Ouvrir les modes de prévisualisation
2. Sélectionner **VR Preview**
3. Cliquer sur **Play (VR Preview)**

→ La scène apparaît dans le casque.

---

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
