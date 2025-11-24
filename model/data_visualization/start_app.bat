@echo off
REM ---------------------------------------------------------
REM Script de lancement local de l’application Streamlit
REM ---------------------------------------------------------

REM %~dp0 = répertoire où se trouve ce fichier .bat
REM cd /d = permet de changer de disque + dossier
cd /d "%~dp0"

REM Désactive la collecte de statistiques anonymes de Streamlit
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

REM Lancement de l’application :
REM   --server.address : adresse locale (127.0.0.1)
REM   --server.port    : port fixe (8501)
REM   app.py           : fichier principal Streamlit
streamlit run app.py --server.address=127.0.0.1 --server.port=8501
