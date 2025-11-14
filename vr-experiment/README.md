# 📘 *Pedestrian-Crossing Behavior – VR Experiment*

### **README global du dossier `vr-experiment/`**

Ce dossier contient l’ensemble des éléments nécessaires pour reproduire les deux expériences VR utilisées dans la thèse :

* **Expérience 1 – TTC Estimation Experiment**
* **Expérience 2 – Crossing Decision Experiment**

Le pipeline combine :

* **Python** (contrôle des trials, génération des plans, logs),
* **Unreal Engine 5.3.2** (logiciel VR, capture des données, interaction),
* **CARLA** (simulation du véhicule),
* **Meta Quest Pro** (VR + eye tracking),
* **CSV + Streamlit** (analyses post-expérimentales).

Ce README présente une vue d’ensemble du système et redirige vers la documentation détaillée dans chaque sous-dossier.

---

# 📑 **SOMMAIRE**

1. [Objectif général](#objectif-général)
2. [Architecture complète du dossier](#architecture-complète-du-dossier)
3. [Description des deux expériences](#description-des-deux-expériences)
4. [Questionnaires administrés avant et après la session](#questionnaires-administrés-avant-et-après-la-session)
5. [Pipeline global Python → Unreal Engine → CSV](#pipeline-global-python--unreal-engine--csv)
6. [Documentation des sous-dossiers](#documentation-des-sous-dossiers)

   * [analysis/](#analysis)
   * [experiment_design/](#experiment_design)
   * [scripts/](#scripts)
   * [unreal_project/](#unreal_project)
7. [Données générées pendant l’expérience](#données-générées-pendant-lexpérience)
8. [Vue globale : liens vers tous les documents](#vue-globale--liens-vers-tous-les-documents)
9. [Licence & Contact](#licence--contact)

---

# 🎯 **Objectif général**

Le dossier **vr-experiment/** rassemble tout ce qui est nécessaire pour :

* **générer** des plans d’expérience pour chaque participant,
* **lancer** les expériences VR,
* **faire interagir** le participant avec un véhicule simulé,
* **enregistrer** des données synchronisées (peds.csv, cars.csv, gaze.csv),
* **analyser** les performances du participant via interfaces Streamlit.

Les expériences étudient :

### ✔️ **Expérience 1 — TTC Estimation**

Le participant indique le moment où la voiture aurait dû arriver à sa hauteur (*snap*).

### ✔️ **Expérience 2 — Crossing Decision**

Le participant maintient ou relâche le trigger selon s’il se sent capable ou non de traverser.

Pour le protocole complet :
👉 **[`unreal_project/experience_flow.md`](unreal_project/experience_flow.md)**

---

# 🏗️ **Architecture complète du dossier**

```
vr-experiment/
 ┣ analysis/                      → Analyse exp1 et exp2 (Streamlit)
 ┣ experiment_design/             → Plans d’expériences + paramètres
 ┣ scripts/                       → Scripts Python de session
 ┣ unreal_project/                → Éléments à intégrer dans un projet UE 5.3.2 basé sur CARLA
 ┗ README.md                      → (ce fichier)
```

---

# 🧪 **Description des deux expériences**

## 🟦 Expérience 1 — *TTC Estimation (Snap Crossing)*

* La voiture s’approche puis disparaît.
* Le participant appuie **une fois** sur le trigger droit lorsqu’il estime que la voiture **arrive à sa hauteur**.
* L’expérience comporte **27 trials** (3 vitesses × 3 distances × 3 météos).

Docs :
👉 [`unreal_project/experience_flow.md`](unreal_project/experience_flow.md)

Analyse :
👉 [`analysis/analyze_exp1_log.py`](analysis/analyze_exp1_log.py)

---

## 🟩 Expérience 2 — *Crossing Decision (Continuous Crossing)*

* Le participant presse/relâche le trigger gauche pour indiquer son intention de traverser.
* La voiture passe, tourne, disparaît.
* **27 trials** (3 vitesses × 3 météos × 3 positions).

Docs :
👉 [`unreal_project/experience_flow.md`](unreal_project/experience_flow.md)

Analyse :
👉 [`analysis/analyze_exp2_log.py`](analysis/analyze_exp2_log.py)

---

# 📝 **Questionnaires administrés avant et après la session**

Deux formulaires entourent chaque session VR.

## 1️⃣ **Formulaire d’introduction – Avant Expérience 1**

Objectifs :
✔ consentement
✔ infos personnelles minimales
✔ contexte de conduite
✔ validation des critères d’inclusion

🔗 **Lien** :
[https://forms.cloud.microsoft/Pages/ResponsePage.aspx?id=DQSIkWdsW0yxEjajBLZtrQAAAAAAAAAAAANAAcdoUPFUNDVITzFQSkFITVpKUlc0Q1k3Q0ZZNDNRWS4u](https://forms.cloud.microsoft/Pages/ResponsePage.aspx?id=DQSIkWdsW0yxEjajBLZtrQAAAAAAAAAAAANAAcdoUPFUNDVITzFQSkFITVpKUlc0Q1k3Q0ZZNDNRWS4u)

⚠️ Les réponses **ne sont pas stockées dans ce dépôt** pour raisons de confidentialité.

---

## 2️⃣ **Formulaire de fin de session – Après Expérience 2**

Objectifs :
✔ évaluer le réalisme de la scène
✔ mesurer le confort VR
✔ recueillir un retour qualitatif sur les deux expériences

🔗 **Lien** :
[https://docs.google.com/forms/d/e/1FAIpQLSee3-RP90WYL8t5XZD118lLd8cJj1gC3f70bW23GU-gKFW6og/viewform?usp=header](https://docs.google.com/forms/d/e/1FAIpQLSee3-RP90WYL8t5XZD118lLd8cJj1gC3f70bW23GU-gKFW6og/viewform?usp=header)

⚠️ Les réponses sont conservées séparément et anonymisées avant analyse.

---

# 🔁 **Pipeline global Python → Unreal Engine → CSV**

```
generate_participant_plan_*.py
       ↓ Excel
run_full_session.py
       ↓ commande trial
Unreal Engine 5.3.2 (VR Preview)
       ↓ capture 90 Hz
CSV_File (Blueprint)
       ↓ buffers
RWText (C++) 
       ↓ écriture
Logs/<N>/peds.csv, cars.csv, gaze.csv
       ↓
analysis/ (Streamlit)
```

Docs :
👉 [`unreal_project/README.md`](unreal_project/README.md)

---

# 📂 **Documentation des sous-dossiers**

---

## 📊 **analysis/**

📄 Documentation :
👉 [`analysis/README.md`](analysis/README.md)

Scripts Streamlit :

* Exp1 → [`analysis/analyze_exp1_log.py`](analysis/analyze_exp1_log.py)
* Exp2 → [`analysis/analyze_exp2_log.py`](analysis/analyze_exp2_log.py)

---

## 🧪 **experiment_design/**

📄 Documentation :
👉 [`experiment_design/README.md`](experiment_design/README.md)

* Paramètres exposés à Python →
  👉 [`experiment_design/parameters_exposed_to_python.md`](experiment_design/parameters_exposed_to_python.md)

* Usage des scripts →
  👉 [`experiment_design/scripts_usage.md`](experiment_design/scripts_usage.md)

---

## 🐍 **scripts/**

📄 Documentation :
👉 [`scripts/README.md`](scripts/README.md)

Scripts :

* Plan Exp1 → [`scripts/generate_participant_plan_exp1.py`](scripts/generate_participant_plan_exp1.py)
* Plan Exp2 → [`scripts/generate_participant_plan_exp2.py`](scripts/generate_participant_plan_exp2.py)
* Session complète → [`scripts/run_full_session.py`](scripts/run_full_session.py)
* Trial individuel → [`scripts/run_trial.py`](scripts/run_trial.py)

---

## 🕶️ **unreal_project/**

Ce dossier contient **des éléments destinés à être importés dans un projet Unreal Engine 5.3.2 basé sur CARLA**, pas un projet complet.

📄 Documentation principale :
👉 [`unreal_project/README.md`](unreal_project/README.md)

Blueprints UE :

* EyeTracking Pawn → [`unreal_project/Blueprints/Eye_tracking_pawn.md`](unreal_project/Blueprints/Eye_tracking_pawn.md)
* Vehicle Pawn → [`unreal_project/Blueprints/BaseVehiclePawn.md`](unreal_project/Blueprints/BaseVehiclePawn.md)
* CSV logic → [`unreal_project/Blueprints/CSV_File.md`](unreal_project/Blueprints/CSV_File.md)

C++ RWText :
👉 [`unreal_project/CppClass/RWText.md`](unreal_project/CppClass/RWText.md)

---

# 📥 **Données générées pendant l’expérience**

Les données ne sont **pas dans ce dépôt**.
Elles sont créées automatiquement par Unreal Engine :

```
C:\Users\carlaue5.3\CarlaUE5\Unreal\CarlaUnreal\Logs\<N>\
```

Chaque dossier `<N>` contient :

* `peds.csv`
* `cars.csv`
* `gaze.csv`

Ces données alimentent ensuite les outils `analysis/`.

---

# 🔗 **Vue globale : liens vers tous les documents**

| Catégorie                    | Lien                                                                                                        |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Déroulement complet          | 👉 [`unreal_project/experience_flow.md`](unreal_project/experience_flow.md)                                 |
| Exécution Unreal + Python    | 👉 [`unreal_project/setup_and_execution_guide.md`](unreal_project/setup_and_execution_guide.md)             |
| Design expérimental          | 👉 [`experiment_design/README.md`](experiment_design/README.md)                                             |
| Paramètres Python → UE       | 👉 [`experiment_design/parameters_exposed_to_python.md`](experiment_design/parameters_exposed_to_python.md) |
| Usage des scripts            | 👉 [`experiment_design/scripts_usage.md`](experiment_design/scripts_usage.md)                               |
| Documentation scripts Python | 👉 [`scripts/README.md`](scripts/README.md)                                                                 |
| Analyse Exp1                 | 👉 [`analysis/README.md`](analysis/README.md#expérience-1)                                                  |
| Analyse Exp2                 | 👉 [`analysis/README.md`](analysis/README.md#expérience-2)                                                  |
| Blueprints Unreal            | 👉 [`unreal_project/Blueprints/README.md`](unreal_project/Blueprints/README.md)                             |
| Vehicle Pawn                 | 👉 [`unreal_project/Blueprints/BaseVehiclePawn.md`](unreal_project/Blueprints/BaseVehiclePawn.md)           |
| EyeTracking Pawn             | 👉 [`unreal_project/Blueprints/Eye_tracking_pawn.md`](unreal_project/Blueprints/Eye_tracking_pawn.md)       |
| CSV Logic                    | 👉 [`unreal_project/Blueprints/CSV_File.md`](unreal_project/Blueprints/CSV_File.md)                         |
| RWText C++                   | 👉 [`unreal_project/CppClass/RWText.md`](unreal_project/CppClass/RWText.md)                                 |

---

# 📌 **Licence & Contact**

**Auteur : Sandra Victor — CNRS / LIRMM
Projet européen AI4CCAM**

Pour toute question technique ou demande de reproduction :
📧 **[sandra.victor@outlook.fr](mailto:sandra.victor@outlook.fr)**

L’ensemble des guides, blueprints, scripts Python et outils d’analyse est disponible dans les sous-dossiers du répertoire `vr-experiment/`.

