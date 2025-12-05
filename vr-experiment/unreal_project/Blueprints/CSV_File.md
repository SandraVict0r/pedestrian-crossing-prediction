
#  CSV_File – Blueprint Function Library Documentation


`CSV_File` est une **Blueprint Function Library** utilisée pour transférer les données collectées dans l’expérience VR vers la classe C++ `RWText`.
Elle sert d’interface entre :

* les Blueprints (EyeTracking_Pawn)
* et le backend C++ chargé de **créer les dossiers**, **gérer l’indexation**, et **écrire les CSV**

 Le backend C++ complet est documenté ici :
**[`CppClass/RWtext.md`](../CppClass/RWtext.md)**

 **Important :**
Même si un nœud “Save Cross Data” existe dans les Blueprints, **il n’est jamais utilisé**.
Les fichiers réellement produits sont uniquement :

```
peds.csv
gaze.csv
cars.csv
```

dans un dossier numéroté automatiquement :

```
Logs/<N>/
```

---

#  Fonctions utilisées

---

##  1. Save Peds Data → PedsToCSV (C++)

![Save Peds Data](img/save_peds_data.png)

Sauvegarde :

* position du participant
* rotation
* timestamp
* flag crossing

Fichier généré :

```
Logs/<N>/peds.csv
```

---

##  2. Save Gaze Data → GazeToCSV (C++)

![Save Gaze Data](img/save_gaze_data.png)

Sauvegarde :

* Gaze origin
* Gaze direction
* Fixation point
* Confidence
* time

Fichier généré :

```
Logs/<N>/gaze.csv
```

---

##  3. Save Car Data → CarsToCSV (C++)

![Save Car Data](img/save_car_data.png)

Sauvegarde :

* position du véhicule
* vitesse
* temps réel
* temps estimé
* position estimée

Fichier généré :

```
Logs/<N>/cars.csv
```

---

#  4. Save Cross Data → (non utilisé)

![Save Cross Data](img/save_cross_data.png)

Cette fonction n'est **jamais appelée** dans le pipeline réel.
Aucun fichier `cross.csv` n’est généré.
Les données de traversée doivent être récupérées via :

* la colonne *Crossing* dans `peds.csv`
* les scripts Python d’analyse
* l’état Press/Release dans Experience 2

---

#  Structure réelle des données générées

```
Logs/
    1/
        peds.csv
        gaze.csv
        cars.csv
    2/
        peds.csv
        gaze.csv
        cars.csv
    3/
        peds.csv
        gaze.csv
        cars.csv
```

Chaque appui sur **S** enregistre un nouveau dossier `<N>`.

---

#  Pipeline complet lors du bouton **S** (Save)

```
[1] Save Peds Data    → crée Logs/<N>/peds.csv
[2] Save Gaze Data    → ajoute Logs/<N>/gaze.csv
[3] Save Car Data     → ajoute Logs/<N>/cars.csv
[4] Clear Data        → vide les arrays pour le prochain trial
```

---

#  Backend C++

Toutes les opérations suivantes sont réalisées côté C++ :

* création automatique du dossier `<N>`
* détection du dernier index existant
* écriture des CSV
* mise en forme des lignes (separator `;`)
* logs d’erreurs et création de logs Unreal

 Documentation complète ici :
**[`CppClass/RWtext.md`](../CppClass/RWtext.md)**

