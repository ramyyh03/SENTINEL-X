"""SENTINEL-X — Test d'intégration COMPLET (une seule commande).

Vérifie bout-en-bout : pré-requis, MQTT, SQLite, détecteur d'anomalies, API,
dashboard, et la chaîne complète capteurs → MQTT → SQLite. Le script démarre
lui-même les services dont il a besoin (broker dev + API) puis les arrête.

Cross-plateforme (Windows + macOS + Linux). Aucune dépendance nouvelle.

Usage :
    python scripts/test_full_integration.py            # rapport synthétique
    python scripts/test_full_integration.py --verbose  # + détail de chaque étape

Adaptation au code réel du projet :
    - "InjectionDetector.analyze_message" → predictive.anomaly_detector.Detecteur.detecter
    - "app.py"                           → api/server.py
    - "logs/injection_detections.log"    → logs/predictions.log
    - MQTT : on teste le port défini dans .env (1883 dev ; 8883 TLS = certs CYBER)
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from colorama import Fore, Style, init as colorama_init

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
colorama_init(autoreset=True)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"
ICONE = {PASS: "✅", FAIL: "❌", WARN: "⚠️ ", SKIP: "⏭️ "}
COULEUR = {PASS: Fore.GREEN, FAIL: Fore.RED, WARN: Fore.YELLOW, SKIP: Fore.CYAN}

PY = sys.executable  # même interpréteur (venv) pour les sous-processus
TOPIC = "sentinel/sensors"
DEV_COMPOSE = ["docker", "compose", "-f", str(PROJECT_ROOT / "docker-compose.dev.yml")]

LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOGS_DIR / "test_integration.log", encoding="utf-8")],
)
logger = logging.getLogger("integration")


class Contexte:
    """État partagé entre phases (services démarrés par le script, config)."""

    def __init__(self, verbose: bool) -> None:
        self.verbose = verbose
        self.broker_demarre = False       # True si CE script a lancé le broker
        self.api_proc: subprocess.Popen | None = None
        self.host = os.getenv("MQTT_HOST", "localhost")
        self.port = int(os.getenv("MQTT_PORT", "1883"))
        self.db = PROJECT_ROOT / os.getenv("DB_PATH", "data/sentinel.db")
        self.api_url = os.getenv("API_URL", "http://localhost:3000").rstrip("/")


class TestPhase:
    """Enveloppe une phase : exécute sa fonction, capture l'erreur, mémorise le résultat."""

    def __init__(self, nom: str, fonction) -> None:
        self.nom = nom
        self.fonction = fonction
        self.status = SKIP
        self.detail = ""

    def run(self, ctx: Contexte) -> None:
        try:
            self.status, self.detail = self.fonction(ctx)
        except Exception as exc:  # une phase ne doit jamais casser le rapport
            self.status, self.detail = FAIL, f"{exc.__class__.__name__}: {exc}"
        logger.info("%s -> %s (%s)", self.nom, self.status, self.detail)
        if ctx.verbose:
            print(f"    {COULEUR[self.status]}{ICONE[self.status]} {self.nom} — {self.detail}{Style.RESET_ALL}")


# --------------------------------------------------------------------------- #
#  Utilitaires
# --------------------------------------------------------------------------- #
def _port_ouvert(host: str, port: int, timeout_s: float = 0.5) -> bool:
    try:
        socket.create_connection((host, port), timeout_s).close()
        return True
    except OSError:
        return False


def _attendre(host: str, port: int, timeout_s: int) -> bool:
    fin = time.time() + timeout_s
    while time.time() < fin:
        if _port_ouvert(host, port):
            return True
        time.sleep(0.3)
    return False


def _docker_demarre() -> bool:
    """True si le CLI docker existe ET le moteur tourne (docker info OK)."""
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _broker_up(ctx: Contexte) -> bool:
    """S'assure que le broker dev (1883) tourne ; le démarre via Docker si besoin."""
    if _port_ouvert("localhost", 1883):
        return True
    if shutil.which("docker") is None:
        return False
    subprocess.run(DEV_COMPOSE + ["up", "-d"], cwd=PROJECT_ROOT,
                   capture_output=True, timeout=60)
    ctx.broker_demarre = _attendre("localhost", 1883, 15)
    return ctx.broker_demarre


def _make_client():
    import paho.mqtt.client as mqtt
    try:
        return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        return mqtt.Client()


def _compter_sensor_data(ctx: Contexte) -> int:
    import sqlite3
    with sqlite3.connect(ctx.db) as conn:
        try:
            return conn.execute("SELECT COUNT(*) FROM sensor_data").fetchone()[0]
        except sqlite3.OperationalError:
            return -1  # table absente


# --------------------------------------------------------------------------- #
#  Phases 1 → 7
# --------------------------------------------------------------------------- #
def phase_prechecks(ctx: Contexte) -> tuple[str, str]:
    """1. Docker, .env, base, fichiers IA. (Le broker est démarré par le script si besoin.)"""
    fatals, reserves = [], []

    # Fichiers IA indispensables
    fichiers = ["scripts/mqtt_client.py", "predictive/anomaly_detector.py",
                "api/server.py", "simulate/fake_sensors_esp32.py", "predictive/collector.py"]
    manquants = [f for f in fichiers if not (PROJECT_ROOT / f).exists()]
    if manquants:
        fatals.append("fichiers manquants: " + ", ".join(manquants))

    # .env
    if not (PROJECT_ROOT / ".env").exists():
        fatals.append(".env absent (cp .env.example .env)")
    elif os.getenv("MQTT_HOST") not in ("localhost", "127.0.0.1"):
        reserves.append(f"MQTT_HOST inattendu: {os.getenv('MQTT_HOST')}")

    # Docker (nécessaire pour MQTT + E2E)
    if shutil.which("docker") is None:
        reserves.append("Docker absent → MQTT/E2E seront KO")

    # Base (créée par la Brique 3 ; sinon la phase SQLite le signalera)
    if not ctx.db.exists():
        reserves.append("data/sentinel.db absent")

    if fatals:
        return FAIL, " ; ".join(fatals + reserves)
    if reserves:
        return WARN, " ; ".join(reserves)
    return PASS, "Docker, .env, base, fichiers IA OK"


def phase_mqtt(ctx: Contexte) -> tuple[str, str]:
    """2. Connexion broker + publish/subscribe aller-retour."""
    if not _docker_demarre():
        return SKIP, ("Docker non installé" if shutil.which("docker") is None
                      else "Docker installé mais non démarré (lance Docker Desktop)")
    if not _broker_up(ctx):
        return FAIL, "broker injoignable (Docker démarré mais compose KO)"
    recu: list[bool] = []
    sub = _make_client()
    sub.on_message = lambda *a: recu.append(True)
    try:
        if ctx.port == 8883:  # mode prod TLS (certs CYBER requis)
            ca = PROJECT_ROOT / "docker/mosquitto/certs/ca.crt"
            if not ca.exists():
                return SKIP, "8883 TLS : certs CYBER absents (voir security/gen-certs.sh)"
            sub.tls_set(ca_certs=str(ca))
        sub.connect("localhost", 1883 if ctx.port != 8883 else 8883, 10)
    except Exception as exc:
        return FAIL, f"connexion échouée: {exc}"
    sub.subscribe(TOPIC)
    sub.loop_start()
    time.sleep(1)
    pub = _make_client()
    pub.connect("localhost", 1883, 10)
    pub.publish(TOPIC, '{"temp":22,"humidity":40,"gas":100,"presence":0,"timestamp":"2026-10-06T00:00:00Z"}')
    time.sleep(1.5)
    sub.loop_stop(); sub.disconnect(); pub.disconnect()
    return (PASS, f"publish/subscribe OK (port {ctx.port})") if recu else (FAIL, "message non reçu")


def phase_sqlite(ctx: Contexte) -> tuple[str, str]:
    """3. La table sensor_data existe et contient des données."""
    if not ctx.db.exists():
        return FAIL, f"base absente: {ctx.db}"
    n = _compter_sensor_data(ctx)
    if n < 0:
        return FAIL, "table sensor_data absente (lancer la Brique 3)"
    if n == 0:
        return WARN, "table présente mais vide (0 ligne)"
    return PASS, f"sensor_data OK ({n} lignes)"


def phase_detecteur(ctx: Contexte) -> tuple[str, str]:
    """4. Le détecteur d'anomalies tourne sans erreur sur les dernières lectures."""
    import sqlite3

    import pandas as pd

    from predictive.anomaly_detector import Detecteur

    try:
        detecteur = Detecteur()
    except FileNotFoundError:
        return FAIL, "modèles absents (lancer : make train)"
    with sqlite3.connect(ctx.db) as conn:
        try:
            df = pd.read_sql_query(
                "SELECT timestamp,temp,humidity,gas,presence FROM sensor_data "
                "ORDER BY id DESC LIMIT 5", conn)
        except Exception:
            return FAIL, "lecture sensor_data impossible"
    if df.empty:
        return WARN, "aucune donnée à analyser"
    res = detecteur.detecter(df.iloc[::-1].reset_index(drop=True))
    return PASS, f"score calculé = {res['anomaly_score']} (votes {res['model_votes']})"


def phase_api(ctx: Contexte) -> tuple[str, str]:
    """5. L'API répond : POST /api/v1/alerts (201) + GET /health (200)."""
    import requests

    _assurer_api(ctx)
    alerte = {"source": "ia_vision", "type": "intrusion_detected", "confidence": 0.9,
              "timestamp": "2026-10-06T10:00:00Z", "details": {}}
    try:
        p = requests.post(f"{ctx.api_url}/api/v1/alerts", json=alerte, timeout=3)
        h = requests.get(f"{ctx.api_url}/health", timeout=3)
    except requests.RequestException as exc:
        return FAIL, f"API injoignable: {exc.__class__.__name__}"
    if p.status_code == 201 and h.status_code == 200:
        return PASS, f"POST 201 + /health 200 ({h.json().get('alerts_count')} alertes)"
    return FAIL, f"codes inattendus POST={p.status_code} health={h.status_code}"


def phase_dashboard(ctx: Contexte) -> tuple[str, str]:
    """6. GET /dashboard renvoie 200 (HTML)."""
    import requests

    _assurer_api(ctx)
    try:
        r = requests.get(f"{ctx.api_url}/dashboard", timeout=3)
    except requests.RequestException as exc:
        return FAIL, f"dashboard injoignable: {exc.__class__.__name__}"
    if r.status_code == 200 and b"SENTINEL-X" in r.content:
        return PASS, "dashboard 200 (HTML servi)"
    return FAIL, f"status {r.status_code}"


def phase_e2e(ctx: Contexte) -> tuple[str, str]:
    """7. Chaîne complète : simulateur → mqtt_client → SQLite (+ détection)."""
    if not _docker_demarre():
        return SKIP, ("Docker non installé" if shutil.which("docker") is None
                      else "Docker installé mais non démarré (lance Docker Desktop)")
    if not _broker_up(ctx):
        return FAIL, "broker indisponible pour l'E2E"
    avant = max(_compter_sensor_data(ctx), 0)

    client = subprocess.Popen([PY, "scripts/mqtt_client.py"], cwd=PROJECT_ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)  # laisser l'abonné se connecter
    subprocess.run([PY, "simulate/fake_sensors_esp32.py", "--simulate"],
                   cwd=PROJECT_ROOT, capture_output=True, timeout=60)
    time.sleep(1)
    client.terminate()
    try:
        client.wait(timeout=5)
    except subprocess.TimeoutExpired:
        client.kill()

    apres = max(_compter_sensor_data(ctx), 0)
    delta = apres - avant

    # Détection : produit-elle des logs ?
    subprocess.run([PY, "-m", "predictive.main_brique6", "detect", "--once"],
                   cwd=PROJECT_ROOT, capture_output=True, timeout=60)
    log_detect = (LOGS_DIR / "predictions.log").exists()

    if delta >= 5 and log_detect:
        return PASS, f"+{delta} lignes en base + détection loggée"
    if delta >= 1:
        return WARN, f"partiel : +{delta} ligne(s) (attendu ~10), détection={'oui' if log_detect else 'non'}"
    return FAIL, "aucune donnée arrivée en base (MQTT→SQLite KO)"


# --------------------------------------------------------------------------- #
#  Gestion de l'API (démarrage/arrêt par le script)
# --------------------------------------------------------------------------- #
def _assurer_api(ctx: Contexte) -> None:
    """Démarre l'API en arrière-plan si elle ne tourne pas déjà."""
    host, port = "localhost", int(os.getenv("API_PORT", "3000"))
    if _port_ouvert(host, port):
        return
    if ctx.api_proc is None:
        ctx.api_proc = subprocess.Popen([PY, "-m", "api.server"], cwd=PROJECT_ROOT,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _attendre(host, port, 10)


def _nettoyer(ctx: Contexte) -> None:
    """Arrête les services démarrés par le script (API, broker dev)."""
    if ctx.api_proc is not None:
        ctx.api_proc.terminate()
        try:
            ctx.api_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ctx.api_proc.kill()
    if ctx.broker_demarre:
        subprocess.run(DEV_COMPOSE + ["down"], cwd=PROJECT_ROOT, capture_output=True, timeout=30)


# --------------------------------------------------------------------------- #
#  Rapport
# --------------------------------------------------------------------------- #
def _rapport(phases: list[TestPhase]) -> int:
    largeur = 49
    print()
    print("┌" + "─" * largeur + "┐")
    print("│ " + f"{Style.BRIGHT}SENTINEL-X INTEGRATION TEST REPORT{Style.RESET_ALL}".ljust(largeur + 8) + "│")
    print("├" + "─" * largeur + "┤")
    for p in phases:
        detail = f" ({p.detail})" if p.status in (FAIL, WARN) else ""
        ligne = f"{ICONE[p.status]} {p.nom}{detail}"
        # ljust approximatif (les emojis comptent large) : on tronque proprement
        ligne = ligne[:largeur - 2]
        print("│ " + COULEUR[p.status] + ligne.ljust(largeur - 1) + Style.RESET_ALL + "│")
    print("├" + "─" * largeur + "┤")

    n = len(phases)
    ok = sum(1 for p in phases if p.status == PASS)
    fails = [p for p in phases if p.status == FAIL]
    warns = [p for p in phases if p.status == WARN]
    skips = [p for p in phases if p.status == SKIP]
    if not fails and not warns and not skips:
        verdict = f"{Fore.GREEN}✅ READY"
    elif not fails:
        verdict = f"{Fore.YELLOW}⚠️  READY (avec réserves)"
    else:
        verdict = f"{Fore.RED}❌ NON PRÊT"
    print("│ " + f"GLOBAL SCORE: {ok}/{n}  {verdict}{Style.RESET_ALL}".ljust(largeur + 8) + "│")
    print("└" + "─" * largeur + "┘")

    if fails or warns or skips:
        print("\nDétails :")
        for p in fails + warns + skips:
            print(f"  {COULEUR[p.status]}{ICONE[p.status]} {p.nom}{Style.RESET_ALL} : {p.detail}")
    print(f"\n📄 Log complet : logs/test_integration.log")
    return 1 if fails else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SENTINEL-X — Test d'intégration complet")
    parser.add_argument("--verbose", action="store_true", help="affiche le détail de chaque étape")
    args = parser.parse_args()

    ctx = Contexte(args.verbose)
    phases = [
        TestPhase("Pre-Checks", phase_prechecks),
        TestPhase("MQTT Connectivity", phase_mqtt),
        TestPhase("SQLite Data", phase_sqlite),
        TestPhase("Injection Detector", phase_detecteur),
        TestPhase("API Connectivity", phase_api),
        TestPhase("Dashboard Connectivity", phase_dashboard),
        TestPhase("E2E Full Chain", phase_e2e),
    ]
    print(f"{Style.BRIGHT}🛡️  SENTINEL-X — Test d'intégration complet…{Style.RESET_ALL}")
    try:
        for phase in phases:
            if not args.verbose:
                print(f"  … {phase.nom}", end="", flush=True)
            phase.run(ctx)
            if not args.verbose:
                print(f"\r  {COULEUR[phase.status]}{ICONE[phase.status]} {phase.nom}{' ' * 20}{Style.RESET_ALL}")
    finally:
        _nettoyer(ctx)

    return _rapport(phases)


if __name__ == "__main__":
    sys.exit(main())
