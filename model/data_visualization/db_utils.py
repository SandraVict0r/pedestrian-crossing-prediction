# db_utils.py
import os
from pathlib import Path
import streamlit as st
import mysql.connector
def _load_env():
    """Charge .env s’il est présent (sans planter si python-dotenv manque)."""
    try:
        from dotenv import load_dotenv
        # Cherche un .env juste à côté de ce fichier
        load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=False)
    except Exception:
        # Pas de python-dotenv ? Pas grave, on lit directement os.environ
        pass

def _read_env():
    _load_env()
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    name = os.getenv("DB_NAME")
    port = int(os.getenv("DB_PORT", "3306") or 3306)

    missing = [k for k, v in {
        "DB_HOST": host, "DB_USER": user, "DB_PASSWORD": password, "DB_NAME": name
    }.items() if not v]
    if missing:
        raise RuntimeError(
            "Variables d’environnement DB manquantes: " + ", ".join(missing) +
            ". Crée un fichier .env à la racine (voir README) ou exporte-les dans ton shell."
        )
    return host, user, password, name, port



def get_db_connection():
    conn = mysql.connector.connect(
        host=st.secrets["DB_HOST"],
        port=int(st.secrets["DB_PORT"]),
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        database=st.secrets["DB_NAME"]
    )
    cursor = conn.cursor()
    return conn, cursor

def get_py_db_connection():
    """
    Connexion via PyMySQL (optionnel). Retourne (conn, cursor).
    """
    host, user, password, name, port = _read_env()
    try:
        import pymysql
        conn = pymysql.connect(
            host=host, user=user, password=password, database=name, port=port,
            charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor
        )
        cursor = conn.cursor()
        return conn, cursor
    except Exception as e:
        raise RuntimeError(f"Échec connexion MySQL (PyMySQL): {e}")
