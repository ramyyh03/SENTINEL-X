"""SENTINEL-X — Lanceur UNIQUE (une seule commande, sans terminaux visibles).

Démarre le broker MQTT, l'API, l'ingestion et la détection EN ARRIÈRE-PLAN
(aucune fenêtre ne s'ouvre), attend que l'API réponde, puis ouvre le dashboard
dans le navigateur. Affiche enfin l'état : ce qui fonctionne, ce qui manque.

Usage :
    python scripts/launch_all.py          # lance tout + ouvre le navigateur
    python scripts/launch_all.py --stop    # arrête les processus lancés
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

LOGS = PROJECT_ROOT / "logs"
PORT = os.getenv("API_PORT", "3000")
URL_DASHBOARD = f"http://localhost:{PORT}/dashboard"
URL_SECURITE = f"http://localhost:{PORT}/security"
URL_COCKPIT = f"http://localhost:{PORT}/app"
URL_HEALTH = f"http://localhost:{PORT}/health"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
IS_WINDOWS = os.name == "nt"
ATTENTE_API_S = 25          # délai max d'attente que l'API réponde

# Processus à lancer en arrière-plan : (nom, commande, fichier de log)
# La vision (webcam) est incluse pour que la caméra soit LIVE dans l'app ;
# elle se coupe proprement toute seule si aucune webcam n'est branchée.
SERVICES = (
    ("api", [sys.executable, "-m", "api.server"], "api.log"),
    ("ingest", [sys.executable, "scripts/mqtt_client.py"], "ingest.log"),
    ("detect", [sys.executable, "-m", "predictive.main_brique6", "detect"], "detect.log"),
    ("vision", [sys.executable, "-m", "vision.detector"], "vision.log"),
)


def _popen_cache(cmd: list[str], log_path: Path) -> subprocess.Popen:
    """Lance une commande détachée, SANS fenêtre, sorties redirigées vers un log."""
    flags = 0
    if IS_WINDOWS:
        # CREATE_NO_WINDOW (0x08000000) : aucune console ne s'ouvre.
        # CREATE_NEW_PROCESS_GROUP (0x00000200) : survit à la fermeture du lanceur.
        flags = 0x08000000 | 0x00000200
    log = open(log_path, "a", encoding="utf-8")
    # Force l'UTF-8 dans les process enfants : sinon, sous Windows (cp1252),
    # imprimer un caractère comme « → » ou un emoji fait planter le service
    # (UnicodeEncodeError) dès que la sortie est redirigée vers un fichier.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.Popen(
        cmd, cwd=str(PROJECT_ROOT), stdout=log, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, creationflags=flags, env=env,
        start_new_session=not IS_WINDOWS)


def vider_alertes() -> None:
    """Vide l'historique des alertes avant de démarrer (fini les anciennes alertes).

    Via un sous-processus isolé : évite tout souci de chemin d'import depuis le lanceur.
    """
    try:
        subprocess.run(
            [sys.executable, "-m", "api.alert_store"],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=15, check=False)
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        print(f"[WARN] alertes non videes : {exc}")


def demarrer_broker() -> bool:
    """Démarre le broker MQTT dev (Docker). Tolérant si Docker est absent."""
    try:
        subprocess.run(
            ["docker", "compose", "-f", "docker-compose.dev.yml", "up", "-d"],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=60, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def demarrer_services() -> dict[str, int]:
    """Lance API + ingestion + détection en arrière-plan. Retourne les PID."""
    LOGS.mkdir(parents=True, exist_ok=True)
    pids: dict[str, int] = {}
    for nom, cmd, logfile in SERVICES:
        proc = _popen_cache(cmd, LOGS / logfile)
        pids[nom] = proc.pid
        (LOGS / f"{nom}.pid").write_text(str(proc.pid), encoding="utf-8")
    return pids


def attendre_api() -> bool:
    """Attend que l'API réponde (health). Vrai si prête dans le délai imparti."""
    for _ in range(ATTENTE_API_S):
        try:
            if requests.get(URL_HEALTH, timeout=1).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def ollama_pret() -> bool:
    """Ollama tourne-t-il et répond-il ? (mistral déjà téléchargé)."""
    try:
        return requests.get(f"{OLLAMA_URL}/api/tags", timeout=2).status_code == 200
    except requests.RequestException:
        return False


def arreter() -> None:
    """Arrête les processus lancés (via les .pid) et le broker."""
    import signal
    for nom, _, _ in SERVICES:
        pidfile = LOGS / f"{nom}.pid"
        if not pidfile.exists():
            continue
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"[STOP] {nom} (pid {pid}) arrêté")
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass
        pidfile.unlink(missing_ok=True)
    subprocess.run(["docker", "compose", "-f", "docker-compose.dev.yml", "down"],
                   cwd=str(PROJECT_ROOT), capture_output=True)


def _rapport(broker_ok: bool, api_ok: bool, ollama_ok: bool) -> None:
    """Affiche l'état final : ce qui fonctionne, ce qui manque."""
    oui, non = "✅", "❌"
    print("\n==================  ÉTAT DU SYSTÈME  ==================")
    print(f"  {oui if broker_ok else non} Broker MQTT (Docker, port 1883)")
    print(f"  {oui if api_ok else non} API + Dashboard (port {PORT})")
    print(f"  {oui if api_ok else non} Ingestion capteurs + détection IA (arrière-plan)")
    print(f"  {oui if ollama_ok else non} Ollama / Mistral (chat + audit expliqué)")
    print("======================================================")
    print(f"  Dashboard : {URL_DASHBOARD}")
    print(f"  Sécurité  : {URL_SECURITE}")
    if not broker_ok:
        print("  ⚠️  Docker non lancé → démarre Docker Desktop puis relance.")
    if not ollama_ok:
        print("  ⚠️  Ollama injoignable → vérifie qu'il tourne (ollama list).")
    print("  Arrêt : python scripts/launch_all.py --stop")


def main() -> int:
    """Point d'entrée : lance tout, ouvre le navigateur, affiche l'état."""
    if "--stop" in sys.argv:
        arreter()
        return 0

    print("SENTINEL-X — démarrage en arrière-plan…")
    vider_alertes()                 # repart sur un historique propre (pas d'anciennes alertes)
    broker_ok = demarrer_broker()
    demarrer_services()
    api_ok = attendre_api()
    ollama_ok = ollama_pret()

    if api_ok:
        webbrowser.open(URL_COCKPIT)   # cockpit tout-en-un (analyse + pages web)
    _rapport(broker_ok, api_ok, ollama_ok)
    return 0 if api_ok else 1


if __name__ == "__main__":
    sys.exit(main())
