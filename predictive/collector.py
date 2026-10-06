"""BRIQUE 3 (extension) — Collecteur SQLite SENTINEL-X.

Persiste chaque mesure capteur reçue par MQTT dans une base SQLite locale.
`sentinel.db` devient la SOURCE DE VÉRITÉ des séries temporelles : la Brique 6
(Isolation Forest) lira directement cette table pour détecter les anomalies.

Pourquoi SQLite : base embarquée, sans serveur, zéro configuration, parfaite
pour un historique local sur le PC. Le fichier .db n'est jamais commité.

Test rapide (sans MQTT) :
    python -c "from predictive.collector import SQLiteCollector; \
        c = SQLiteCollector(); \
        print(c.insert_reading({'temp':23.5,'humidity':45.2,'gas':150,'presence':0,'timestamp':'2026-10-05T12:00:00Z'}))"
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Racine projet = parent du dossier predictive/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_DB_PATH = "data/sentinel.db"
CONNECT_TIMEOUT_SECONDS = 5  # attente si la base est verrouillée (DB locked)

# Table des séries temporelles capteurs
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    temp REAL,
    humidity REAL,
    gas REAL,
    presence INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""
INSERT_SQL = (
    "INSERT INTO sensor_data (timestamp, temp, humidity, gas, presence) "
    "VALUES (:timestamp, :temp, :humidity, :gas, :presence)"
)


class SQLiteCollector:
    """Encapsule l'accès SQLite (pattern Repository léger).

    Une connexion est ouverte PAR opération : SQLite n'aime pas qu'une même
    connexion traverse plusieurs threads, et le callback MQTT tourne dans un
    thread réseau distinct. Ouvrir/fermer à chaque insert reste rapide et
    évite tout problème de thread.
    """

    def __init__(self, db_path: str | None = None) -> None:
        """Résout le chemin de la base et crée la table si besoin."""
        raw = db_path or os.getenv("DB_PATH", DEFAULT_DB_PATH)
        path = Path(raw)
        # Chemin relatif → relatif à la racine du projet (pas au cwd)
        self.db_path = path if path.is_absolute() else PROJECT_ROOT / path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Ouvre une connexion avec timeout (gère les verrous concurrents)."""
        return sqlite3.connect(self.db_path, timeout=CONNECT_TIMEOUT_SECONDS)

    def _init_db(self) -> None:
        """Crée le dossier parent + le fichier .db + la table au premier appel."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.commit()

    def insert_reading(self, data: dict[str, Any]) -> int | None:
        """Insère une mesure et renvoie son id, ou None en cas d'erreur.

        `data` doit contenir : timestamp, temp, humidity, gas, presence.
        On ne lève pas : une erreur de stockage ne doit pas tuer la réception MQTT.
        """
        row = {
            "timestamp": data.get("timestamp"),
            "temp": data.get("temp"),
            "humidity": data.get("humidity"),
            "gas": data.get("gas"),
            "presence": data.get("presence"),
        }
        try:
            with closing(self._connect()) as conn:
                cursor = conn.execute(INSERT_SQL, row)
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as exc:
            # Erreurs possibles : base verrouillée, corrompue, disque plein…
            print(f"[DB][ERREUR] Échec insertion SQLite : {exc}")
            return None

    def insert_many(self, readings: list[dict[str, Any]]) -> int:
        """Insère plusieurs mesures en UNE connexion (initialisation/seed rapide).

        Retourne le nombre de lignes insérées (0 en cas d'erreur).
        """
        rows = [{
            "timestamp": d.get("timestamp"), "temp": d.get("temp"),
            "humidity": d.get("humidity"), "gas": d.get("gas"),
            "presence": d.get("presence"),
        } for d in readings]
        try:
            with closing(self._connect()) as conn:
                conn.executemany(INSERT_SQL, rows)
                conn.commit()
                return len(rows)
        except sqlite3.Error as exc:
            print(f"[DB][ERREUR] Insertion multiple échouée : {exc}")
            return 0

    def count(self) -> int:
        """Nombre de lignes stockées (utile pour les tests/validation)."""
        with closing(self._connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM sensor_data").fetchone()[0]
