# Préparation avant chaque session complète

## 1. Générer les fichiers d'expérimentation

Pour chaque participant il faut exécuter une expérimentation complète. Cette expérimentation est contenue dans un fichier (excel) **généré pour l'occasion**.

Selon l’expérience il faut donc identifier le bon fichier à exécuter:

* **Expérience 1** : fichier Excel généré via `generate_participant_plan_exp1.py`
* **Expérience 2** : fichier généré via `generate_participant_plan_exp2.py`

Il faut donc avant toute chose générer un fichier ecel d'expérimentation:

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

