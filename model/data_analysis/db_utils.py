# db_utils.py
"""
Utilitaires de connexion MySQL pour l’application Streamlit.

Ce module fournit deux façons de se connecter à MySQL :

1) get_db_connection()
   → Utilisé *par Streamlit Cloud*.
     Les identifiants sont lus dans st.secrets (fichier secrets.toml sur Streamlit Cloud).
     C’est la méthode standard pour les apps déployées.

2) get_py_db_connection()
   → Connexion via PyMySQL pour un usage local.
     Les identifiants sont lus dans un fichier .env local (ou dans les variables d’environnement).

Ce découplage permet :
    - une execution locale facilement paramétrable
    - un déploiement propre sur Streamlit Cloud sans exposer de mots de passe
"""

import os
from pathlib import Path
import streamlit as st
import mysql.connector


# ----------------------------------------------------------------------
# Chargement manuel du .env (optionnel)
# ----------------------------------------------------------------------
def _load_env():
    """
    Charge un fichier .env placé à côté de db_utils.py (model/data_visualization/.env).
    Cette fonction :
        - utilise python-dotenv si installé
        - n’échoue pas si python-dotenv n’est pas disponible
    Cela permet une exécution locale robuste et silencieuse.
    """
    try:
        from dotenv import load_dotenv
        # Charge un fichier .env situé dans le même dossier que ce script
        load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=False)
    except Exception:
        # python-dotenv non installé → on ignore et on lit os.environ directement
        pass


def _read_env():
    """
    Lecture des variables d’environnement pour une connexion locale.
    Utilisée par get_py_db_connection().

    Variables requises :
        DB_HOST
        DB_USER
        DB_PASSWORD
        DB_NAME
        DB_PORT     (optionnel, défaut = 3306)

    Si une variable manque → RuntimeError explicite.
    """
    _load_env()

    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    name = os.getenv("DB_NAME")
    port = int(os.getenv("DB_PORT", "3306") or 3306)

    # Vérification des variables obligatoires
    missing = [
        k for k, v in {
            "DB_HOST": host,
            "DB_USER": user,
            "DB_PASSWORD": password,
            "DB_NAME": name
        }.items()
        if not v
    ]
    if missing:
        raise RuntimeError(
            "Variables d’environnement DB manquantes : " + ", ".join(missing) +
            ". Crée un fichier .env (voir README) ou exporte-les dans ton terminal."
        )

    return host, user, password, name, port


# ----------------------------------------------------------------------
# Connexion MySQL pour Streamlit Cloud
# ----------------------------------------------------------------------
def get_db_connection():
    """
    Connexion MySQL privilégiée pour Streamlit Cloud.

    Streamlit Cloud ne permet pas d’utiliser un .env :
    → Les identifiants doivent être dans `.streamlit/secrets.toml`
      et sont accessibles via st.secrets.

    Cette fonction est appelée par tous les scripts du dossier /features.
    Elle retourne :
        conn   : connexion MySQL ouverte
        cursor : curseur mysql.connector
    """
    conn = mysql.connector.connect(
        host=st.secrets["DB_HOST"],
        port=int(st.secrets["DB_PORT"]),
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        database=st.secrets["DB_NAME"]
    )
    cursor = conn.cursor()
    return conn, cursor


# ----------------------------------------------------------------------
# Connexion locale MySQL via PyMySQL
# ----------------------------------------------------------------------
def get_py_db_connection():
    """
    Connexion alternative utilisant PyMySQL (mode local).

    Usage :
        - développement local
        - tests unitaires
        - scripts Python non-Streamlit

    Lecture des identifiants par .env ou variables d’environnement
    (via _read_env()).

    Retourne :
        conn   : connexion PyMySQL
        cursor : curseur PyMySQL (DictCursor)

    Erreurs explicites si la connexion échoue.
    """
    host, user, password, name, port = _read_env()

    try:
        import pymysql
        conn = pymysql.connect(
            host=host,
            user=user,
            password=password,
            database=name,
            port=port,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
        cursor = conn.cursor()
        return conn, cursor

    except Exception as e:
        raise RuntimeError(f"Échec connexion MySQL (PyMySQL) : {e}")
