"""BRIQUE 6 — Orchestration de l'IA prédictive SENTINEL-X.

Trois sous-commandes :
    train    : génère les données → entraîne Forest+LOF → évalue (+ ARIMA optionnel)
    detect   : lit data/sentinel.db en continu → détecte → alerte → POST vers l'API
    replay   : rejoue data/training_data.csv (test autonome, sans DB ni broker)

Usage :
    python -m predictive.main_brique6 train
    python -m predictive.main_brique6 detect [--once]
    python -m predictive.main_brique6 replay
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv

from predictive import arima_trainer
from predictive.alert_aggregator import Agregateur
from predictive.alert_generator import generer_alerte
from predictive.anomaly_detector import Detecteur
from predictive.baseline_analyzer import baseline

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
colorama_init(autoreset=True)

LOGS_DIR = PROJECT_ROOT / "logs"
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "data/sentinel.db")
TRAINING_CSV = PROJECT_ROOT / "data" / "training_data.csv"
# Endpoint complet : soit API_ENDPOINT explicite, soit construit depuis
# API_URL + API_ALERTS_ENDPOINT (robuste à un .env qui n'aurait que l'URL de base).
_API_URL = os.getenv("API_URL", "http://localhost:3000")
_API_PATH = os.getenv("API_ALERTS_ENDPOINT", "/api/v1/alerts")
API_ENDPOINT = os.getenv("API_ENDPOINT") or f"{_API_URL.rstrip('/')}/{_API_PATH.lstrip('/')}"
BUFFER_MAX = 120          # tampon des lectures récentes (pour les features)
POLL_SECONDS = 2          # fréquence de scrutation de la base
COLS = ["timestamp", "temp", "humidity", "gas", "presence"]


def log(prefix: str, color: str, message: str) -> None:
    """Log console coloré."""
    print(f"{color}[{prefix}]{Style.RESET_ALL} {message}")


def _append_log(nom: str, ligne: str) -> None:
    """Ajoute une ligne à un fichier de logs/ (créé si besoin)."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / nom, "a", encoding="utf-8") as fh:
        fh.write(ligne + "\n")


def poster_alerte(alerte: dict) -> bool:
    """POST l'alerte vers l'API DEV. Tolérant : si l'API est absente, on log et on continue."""
    try:
        r = requests.post(API_ENDPOINT, json=alerte, timeout=2)
        return 200 <= r.status_code < 300
    except requests.RequestException as exc:
        log("API", Fore.YELLOW, f"API injoignable ({exc.__class__.__name__}) — alerte loggée seulement")
        return False


# --------------------------------------------------------------------------- #
#  TRAIN
# --------------------------------------------------------------------------- #
def cmd_train() -> int:
    """Pipeline complet d'entraînement + évaluation."""
    from predictive import data_generator, forest_trainer, metrics_evaluator

    if os.getenv("GENERATE_SYNTHETIC_DATA", "true").lower() == "true" or not TRAINING_CSV.exists():
        data = data_generator.generer()
        log("DATA", Fore.CYAN, f"{len(data)} lectures synthétiques générées")

    res = forest_trainer.entrainer()
    log("TRAIN", Fore.GREEN, f"Forest + LOF entraînés ({res['metadata']['n_features']} features)")

    metrics = metrics_evaluator.evaluer(res["labels"], res["scores_ensemble"], res["metadata"]["threshold"])
    metrics_evaluator.afficher(metrics)

    if os.getenv("ARIMA_ENABLED", "false").lower() == "true":
        log("ARIMA", Fore.CYAN, str(arima_trainer.entrainer()))

    log("OK", Fore.GREEN, "Entraînement terminé → models/ + logs/training_metrics.json")
    return 0


# --------------------------------------------------------------------------- #
#  DÉTECTION (temps réel sur sentinel.db)
# --------------------------------------------------------------------------- #
def _traiter_lecture(detecteur: Detecteur, agregateur: Agregateur,
                     buffer: deque, row: dict) -> None:
    """Score une lecture, génère/agrège l'alerte, log et POST si anomalie."""
    buffer.append({k: row[k] for k in COLS})
    df = pd.DataFrame(list(buffer))
    detection = detecteur.detecter(df)

    _append_log("predictions.log",
                f"{row['timestamp']} score={detection['anomaly_score']} "
                f"votes={detection['model_votes']} anomaly={detection['is_anomaly']}")

    if not detection["is_anomaly"]:
        return

    valeurs = {k: row[k] for k in ("temp", "humidity", "gas", "presence")}
    alerte = generer_alerte(detection, valeurs, baseline(df), row["timestamp"])
    maintenant = _parse_ts(row["timestamp"])
    emise = agregateur.soumettre(alerte, maintenant)

    if emise is None:
        return  # supprimée par coalescence (comptée)

    sev = emise["details"]["severity"]
    couleur = Fore.RED if sev == "CRITICAL" else (Fore.YELLOW if sev == "WARNING" else Fore.CYAN)
    log("ANOMALY", couleur,
        f"score={emise['confidence']} [{sev}] → {emise['details']['context']}")
    _append_log("alerts.log", json.dumps(emise, ensure_ascii=False))
    poster_alerte(emise)


def _parse_ts(ts: str) -> datetime:
    """Parse un timestamp ISO 8601 (avec ou sans Z) en datetime aware."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


def cmd_detect(once: bool) -> int:
    """Boucle de détection temps réel sur data/sentinel.db."""
    if not DB_PATH.exists():
        log("ERREUR", Fore.RED, f"Base introuvable : {DB_PATH} — lance d'abord la Brique 3")
        return 1
    try:
        detecteur = Detecteur()
    except FileNotFoundError as exc:
        log("ERREUR", Fore.RED, str(exc))
        return 1

    agregateur = Agregateur(
        min_interval_s=int(os.getenv("ALERT_MIN_INTERVAL", "60")),
        window_s=int(os.getenv("ALERT_WINDOW", "300")),
    )
    buffer: deque = deque(maxlen=BUFFER_MAX)
    dernier_id = 0
    log("INFO", Fore.MAGENTA,
        f"Détection démarrée (seuil={detecteur.threshold}, API={API_ENDPOINT}). Ctrl+C pour arrêter.")

    while True:
        for row in _lire_nouvelles_lignes(dernier_id):
            dernier_id = row["id"]
            _traiter_lecture(detecteur, agregateur, buffer, row)
        if once:
            break
        time.sleep(POLL_SECONDS)
    log("OK", Fore.GREEN, f"Terminé (dernier id traité = {dernier_id}).")
    return 0


def _lire_nouvelles_lignes(dernier_id: int) -> list[dict]:
    """Retourne les lignes de sensor_data d'id > dernier_id (ordre chronologique)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, timestamp, temp, humidity, gas, presence "
            "FROM sensor_data WHERE id > ? ORDER BY id", (dernier_id,))
        return [dict(r) for r in cur.fetchall()]


# --------------------------------------------------------------------------- #
#  REPLAY (test autonome sur le CSV synthétique)
# --------------------------------------------------------------------------- #
def cmd_replay() -> int:
    """Rejoue le CSV synthétique dans le détecteur (sans DB ni broker)."""
    if not TRAINING_CSV.exists():
        log("ERREUR", Fore.RED, "data/training_data.csv absent — lance : make train")
        return 1
    try:
        detecteur = Detecteur()
    except FileNotFoundError as exc:
        log("ERREUR", Fore.RED, str(exc))
        return 1

    df = pd.read_csv(TRAINING_CSV)
    agregateur = Agregateur()
    buffer: deque = deque(maxlen=BUFFER_MAX)
    alertes = 0
    for _, r in df.iterrows():
        row = {k: r[k] for k in COLS}
        buffer.append(row)
        det = detecteur.detecter(pd.DataFrame(list(buffer)))
        if det["is_anomaly"]:
            valeurs = {k: r[k] for k in ("temp", "humidity", "gas", "presence")}
            alerte = generer_alerte(det, valeurs, baseline(pd.DataFrame(list(buffer))), row["timestamp"])
            if agregateur.soumettre(alerte, _parse_ts(row["timestamp"])) is not None:
                alertes += 1
    log("OK", Fore.GREEN, f"Replay terminé : {alertes} alerte(s) émise(s) sur {len(df)} lectures.")
    return 0


def main() -> int:
    """Point d'entrée CLI."""
    parser = argparse.ArgumentParser(description="SENTINEL-X — IA prédictive (Brique 6)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("train", help="génère + entraîne + évalue")
    p_detect = sub.add_parser("detect", help="détection temps réel sur sentinel.db")
    p_detect.add_argument("--once", action="store_true", help="traite les lignes existantes puis s'arrête")
    sub.add_parser("replay", help="rejoue le CSV synthétique (test autonome)")
    args = parser.parse_args()

    if args.cmd == "train":
        return cmd_train()
    if args.cmd == "detect":
        return cmd_detect(args.once)
    return cmd_replay()


if __name__ == "__main__":
    sys.exit(main())
