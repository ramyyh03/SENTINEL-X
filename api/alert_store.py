"""BRIQUE 7 — Stockage des alertes (SQLite, pattern Repository).

Persiste les alertes reçues par l'API dans la MÊME base que la Brique 6
(`data/sentinel.db`), dans une table dédiée `alerts`. Une connexion est ouverte
par opération (Flask sert plusieurs requêtes en parallèle → sûr côté threads).
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_DB_PATH = "data/sentinel.db"
CONNECT_TIMEOUT_SECONDS = 5

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    type TEXT NOT NULL,
    confidence REAL,
    timestamp TEXT,
    details TEXT,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""
INSERT_SQL = (
    "INSERT INTO alerts (source, type, confidence, timestamp, details) "
    "VALUES (:source, :type, :confidence, :timestamp, :details)"
)


class AlertStore:
    """Accès SQLite aux alertes (création table, insertion, lecture)."""

    def __init__(self, db_path: str | None = None) -> None:
        """Résout le chemin de la base (relatif → racine projet) et crée la table."""
        raw = db_path or os.getenv("DB_PATH", DEFAULT_DB_PATH)
        path = Path(raw)
        self.db_path = path if path.is_absolute() else PROJECT_ROOT / path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Ouvre une connexion avec timeout (gère les accès concurrents)."""
        conn = sqlite3.connect(self.db_path, timeout=CONNECT_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Crée le dossier + la table si besoin."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.commit()

    def insert_alert(self, alerte: dict[str, Any]) -> int | None:
        """Insère une alerte (details sérialisé en JSON). Retourne l'id ou None."""
        row = {
            "source": alerte.get("source"),
            "type": alerte.get("type"),
            "confidence": alerte.get("confidence"),
            "timestamp": alerte.get("timestamp"),
            "details": json.dumps(alerte.get("details", {}), ensure_ascii=False),
        }
        try:
            with closing(self._connect()) as conn:
                cur = conn.execute(INSERT_SQL, row)
                conn.commit()
                return cur.lastrowid
        except sqlite3.Error as exc:
            print(f"[DB][ERREUR] Insertion alerte échouée : {exc}")
            return None

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retourne les `limit` dernières alertes (details reconverti en dict)."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        alertes = []
        for r in rows:
            d = dict(r)
            try:
                d["details"] = json.loads(d["details"]) if d["details"] else {}
            except (json.JSONDecodeError, TypeError):
                d["details"] = {}
            alertes.append(d)
        return alertes

    def count(self) -> int:
        """Nombre total d'alertes stockées."""
        with closing(self._connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]

    def vider(self) -> int:
        """Supprime toutes les alertes (repart sur un historique propre)."""
        with closing(self._connect()) as conn:
            n = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            conn.execute("DELETE FROM alerts")
            conn.commit()
            return n


if __name__ == "__main__":        # `python -m api.alert_store` -> vide les alertes
    supprimees = AlertStore().vider()
    print(f"[OK] {supprimees} alerte(s) supprimée(s) — historique remis à zéro.")
