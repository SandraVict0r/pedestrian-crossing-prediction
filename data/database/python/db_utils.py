import os
from dotenv import load_dotenv
import mysql.connector

def get_db_connection():
    """
    Établit une connexion MySQL en utilisant les variables d'environnement
    stockées dans un fichier .env (non versionné).

    Le fichier .env doit définir :
        DB_HOST=
        DB_USER=
        DB_PASSWORD=
        DB_NAME=
        DB_PORT=

    Cette fonction retourne :
        - conn  : objet connexion MySQL
        - cursor : curseur simple (tuple-based)
    """

    # Charge les variables définies dans .env
    # ⚠️ Le chemin n'est pas explicitement défini ici : load_dotenv()
    #     recherche un fichier .env dans le répertoire courant OU au-dessus.
    #     → L'utilisateur DOIT créer son propre .env et NE PAS le publier.
    load_dotenv()

    # Lecture des variables d'environnement
    db_host = os.getenv('DB_HOST')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')
    db_port = os.getenv('DB_PORT')

    # Connexion MySQL standard (mysql-connector)
    conn = mysql.connector.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        port=db_port,
        database=db_name
    )
    cursor = conn.cursor()
    return conn, cursor


# Variante : connexion via PyMySQL avec curseur dict
import pymysql

def get_py_db_connection():
    """
    Variante de connexion utilisant PyMySQL.
    Retourne un curseur dict (clé → valeur), utile pour les requêtes plus structurées.
    """

    conn = pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        port=int(os.getenv('DB_PORT')),
        database=os.getenv('DB_NAME'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    cursor = conn.cursor()
    return conn, cursor
