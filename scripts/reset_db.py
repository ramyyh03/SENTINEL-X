"""SENTINEL-X — Remet à zéro la base (supprime les données synthétiques/anciennes).

Vide les tables `sensor_data` (mesures) et `alerts` (alertes) pour repartir sur
du RÉEL : seules les futures mesures de l'ESP32 et les vraies alertes s'afficheront.

Usage :
    python scripts/reset_db.py
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "data/sentinel.db")


def reset() -> None:
    """Vide sensor_data et alerts si la base existe."""
    if not DB_PATH.exists():
        print(f"ℹ️ Aucune base à vider ({DB_PATH}).")
        return
    with closing(sqlite3.connect(DB_PATH)) as conn:
        for table in ("sensor_data", "alerts"):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                conn.execute(f"DELETE FROM {table}")
                print(f"🧹 {table} : {n} ligne(s) supprimée(s)")
            except sqlite3.OperationalError:
                print(f"ℹ️ table {table} absente (rien à vider)")
        conn.commit()
    print("✅ Base remise à zéro — seules les données réelles s'afficheront désormais.")


if __name__ == "__main__":
    reset()
