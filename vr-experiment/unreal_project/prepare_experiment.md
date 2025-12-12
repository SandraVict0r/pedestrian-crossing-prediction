# Préparation avant chaque session complète

Pour chaque participant il faut exécuter une expérimentation complète. Cette expérimentation est contenue dans un fichier (excel) **généré pour l'occasion**.


## 1. Configurer le générateur de mission

La première etape consiste à configurer le générateur qui est un script python. 

Selon l’expérience il faut donc identifier le bon fichier à exécuter:

* **Expérience 1** : fichier Excel généré via `generate_participant_plan_exp1.py`
* **Expérience 2** : fichier généré via `generate_participant_plan_exp2.py`

La configuration consiste à définir le **nombre de participants**:

### Expérience 1

ligne 170, définir le nombre de participants (modifier 10):

```
num_participants = 10
```

### Expérience 2

ligne 28, définir le nombre de participants (modifier 11):

```
# Liste des participants (10 participants numérotés de 1 à 10)
participants = list(range(1, 11))
```

Note: Utile seulement is plusieurs participants, sinon rentrer la valeur `1`. 

## 2. Générer les fichiers d'expérimentation

Il faut maintenant générer un fichier excel d'expérimentation:

* pour **Expérience 1** :
```
cd <install_folder>/vr-experiments/scripts/
generate_participant_plan_exp1.py
```

* pour **Expérience 2** :
```
cd <install_folder>/vr-experiments/scripts/
generate_participant_plan_exp2.py
```

**Remarques:**
+ Ces scripts ne requièrent **aucun paramètre**.
+ Ils doivent être exécutés dans le répertoire `script`
+ Ils génèrent le fichier expérimentation dans le répertoire `script`

## 2. Préparer le script pour exécuter l'expérimentation

Il faut que le script `run_full_session.py` cible le bon fichier d'expérience (généré préalablement). Pour cela il faut (hélas) modifier le code qui contient le chemin vers le fichier en question: 

```python
excel_file = "partic.ipant_2_commands_exp2.xlsx"
execute_commands_from_excel(excel_file)
```

# 3. Vérification préliminaire

Il faut vérifier que le dossier **Logs** est **VIDE**.

