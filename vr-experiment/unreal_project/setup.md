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

Une fois Unreal ouvert et le casque opérationnel il faut activer le VR Preview dans Unreal Engine:

1. Vérifier que le casque est bien reconnu par Unreal.
2. Dans l’éditeur, sélectionner **Play → VR Preview**.
![vr preview](img/selection_vr_preview.png)
![lancement](img/lancement_simu.png)

→ La scène (unique pour toutes les XP) apparaît dans le casque.

