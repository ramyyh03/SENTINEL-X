"""SENTINEL-X — Healthcheck complet (une commande pour tout tester).

Lance et vérifie chaque brique, puis affiche un RAPPORT clair OK / FAIL / SKIP.
Cross-plateforme (Windows + macOS + Linux). Les tests nécessitant Docker sont
automatiquement ignorés (SKIP) si Docker est absent.

Usage :
    python scripts/healthcheck.py            # tout
    python scripts/healthcheck.py --quick    # saute les tests lourds (Docker, Vision)
"""
from __future__ import annotations

import argparse
import importlib
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

OK, FAIL, SKIP = "OK", "FAIL", "SKIP"
COULEUR = {OK: Fore.GREEN, FAIL: Fore.RED, SKIP: Fore.YELLOW}


# --------------------------------------------------------------------------- #
#  Tests individuels : chacun retourne (status, détail)
# --------------------------------------------------------------------------- #
def t_dependances() -> tuple[str, str]:
    """Toutes les dépendances Python s'importent-elles ?"""
    paquets = ["cv2", "ultralytics", "sklearn", "pandas", "numpy", "scipy",
               "paho.mqtt.client", "requests", "dotenv", "colorama", "flask"]
    manquants = [p for p in paquets if not _importable(p)]
    if manquants:
        return FAIL, f"manquants: {', '.join(manquants)} (make install)"
    return OK, f"{len(paquets)} paquets OK"


def t_structure() -> tuple[str, str]:
    """Les fichiers/dossiers clés du projet sont-ils présents ?"""
    requis = [
        "Makefile", "requirements.txt", "README.md",
        "firmware/src/main.cpp", "vision/detector.py",
        "predictive/main_brique6.py", "predictive/forest_trainer.py",
        "scripts/mqtt_client.py", "simulate/fake_sensors_esp32.py",
        "docker/docker-compose.yml", "docker/mosquitto/config/mosquitto.conf",
    ]
    absents = [p for p in requis if not (PROJECT_ROOT / p).exists()]
    if absents:
        return FAIL, f"absents: {', '.join(absents)}"
    return OK, f"{len(requis)} fichiers clés présents"


def t_brique3_sqlite() -> tuple[str, str]:
    """BRIQUE 3 : le collector SQLite insère-t-il une mesure ?"""
    import tempfile

    from predictive.collector import SQLiteCollector

    tmp = tempfile.mkdtemp()
    try:
        col = SQLiteCollector(db_path=str(Path(tmp) / "test.db"))
        rid = col.insert_reading(
            {"timestamp": "2026-10-06T00:00:00Z", "temp": 22.0,
             "humidity": 45.0, "gas": 120, "presence": 0})
        ok = bool(rid) and col.count() == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # Windows : tolère un fichier encore verrouillé
    return (OK, "insertion + lecture SQLite OK") if ok else (FAIL, "insertion SQLite échouée")


def t_brique3_mqtt() -> tuple[str, str]:
    """BRIQUE 3 : aller-retour MQTT réel (publish → subscribe) via le broker Docker."""
    if shutil.which("docker") is None:
        return SKIP, "Docker non installé"
    # Le CLI existe-t-il ET le moteur tourne-t-il ? (docker info échoue si non démarré)
    try:
        if subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode != 0:
            return SKIP, "Docker installé mais non démarré (lance Docker Desktop)"
    except (OSError, subprocess.TimeoutExpired):
        return SKIP, "Docker installé mais non démarré (lance Docker Desktop)"
    compose = ["docker", "compose", "-f", str(PROJECT_ROOT / "docker-compose.dev.yml")]
    try:
        subprocess.run(compose + ["up", "-d"], cwd=PROJECT_ROOT,
                       capture_output=True, timeout=60, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return FAIL, f"broker KO ({exc.__class__.__name__})"
    try:
        if not _attendre_port("localhost", 1883, 15):
            return FAIL, "broker injoignable sur 1883"
        recu = _mqtt_roundtrip()
        return (OK, "publish/subscribe MQTT OK") if recu else (FAIL, "message non reçu")
    finally:
        subprocess.run(compose + ["down"], cwd=PROJECT_ROOT,
                       capture_output=True, timeout=30)


def t_brique5_vision() -> tuple[str, str]:
    """BRIQUE 5 : YOLOv8n se charge et traite des frames simulées."""
    import numpy as np

    from vision.detector import VisionDetector, frame_simulee

    det = VisionDetector()
    t0 = time.perf_counter()
    for i in range(3):
        det.detecter(frame_simulee(i))
    ms = (time.perf_counter() - t0) / 3 * 1000
    return OK, f"YOLOv8n charge + inférence ~{ms:.0f} ms/frame"


def t_brique6_predictif() -> tuple[str, str]:
    """BRIQUE 6 : pipeline entraînement + métrique de surveillance (rappel épisode)."""
    from predictive import data_generator, forest_trainer, metrics_evaluator

    data_generator.generer()
    res = forest_trainer.entrainer()
    m = metrics_evaluator.evaluer(res["labels"], res["scores_ensemble"],
                                  res["metadata"]["threshold"])
    rec = m["recall_episodes"]
    if rec >= 0.9:
        return OK, f"rappel épisode={rec:.2f}, ROC-AUC={m['roc_auc']:.2f}"
    return FAIL, f"rappel épisode trop bas ({rec:.2f})"


def t_brique7_api() -> tuple[str, str]:
    """BRIQUE 7 : l'API valide, stocke et expose /health (test in-process)."""
    import tempfile

    from api.alert_store import AlertStore
    from api.server import create_app

    tmp = tempfile.mkdtemp()
    try:
        app = create_app(AlertStore(db_path=str(Path(tmp) / "t.db")))
        c = app.test_client()
        ok = c.post("/api/v1/alerts", json={
            "source": "ia_vision", "type": "intrusion_detected", "confidence": 0.9,
            "timestamp": "2026-10-06T10:00:00Z", "details": {}})
        bad = c.post("/api/v1/alerts", json={"source": "x"})  # invalide
        health = c.get("/health")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # Windows : tolère un fichier encore verrouillé
    if ok.status_code == 201 and bad.status_code == 400 and health.status_code == 200:
        return OK, f"/alerts (201/400) + /health OK ({health.get_json()['status']})"
    return FAIL, f"codes inattendus: {ok.status_code}/{bad.status_code}/{health.status_code}"


def t_firmware() -> tuple[str, str]:
    """FIRMWARE : le code publie bien en MQTT au bon topic + capteurs présents."""
    cpp = (PROJECT_ROOT / "firmware/src/main.cpp").read_text(encoding="utf-8")
    ini = (PROJECT_ROOT / "firmware/platformio.ini").read_text(encoding="utf-8")
    attendus = ["sentinel/sensors", "PIN_MQ2", "PIN_PIR", "mqtt.publish"]
    manquants = [a for a in attendus if a not in cpp]
    if manquants:
        return FAIL, f"main.cpp incomplet: {', '.join(manquants)}"
    if "PubSubClient" not in ini or "WiFiManager" not in ini:
        return FAIL, "platformio.ini : libs MQTT/WiFi manquantes"
    return OK, "MQTT + MQ-2 + PIR + WiFiManager présents"


def t_securite() -> tuple[str, str]:
    """SÉCURITÉ : broker prod en TLS/auth + aucun secret suivi par Git."""
    conf = (PROJECT_ROOT / "docker/mosquitto/config/mosquitto.conf").read_text(encoding="utf-8")
    if "8883" not in conf or "allow_anonymous false" not in conf:
        return FAIL, "config prod sans TLS 8883 / sans auth"
    try:
        suivis = subprocess.run(["git", "ls-files"], cwd=PROJECT_ROOT,
                                capture_output=True, text=True, timeout=15).stdout
    except Exception:
        suivis = ""
    fuites = [l for l in suivis.splitlines()
              if l.endswith(".key") or l.endswith("/passwd") or l.endswith("secrets.h")]
    if fuites:
        return FAIL, f"SECRET suivi par Git: {', '.join(fuites)}"
    return OK, "TLS 8883 + auth ; aucun secret dans Git"


# --------------------------------------------------------------------------- #
#  Utilitaires
# --------------------------------------------------------------------------- #
def _importable(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


def _attendre_port(host: str, port: int, timeout_s: int) -> bool:
    fin = time.time() + timeout_s
    while time.time() < fin:
        try:
            socket.create_connection((host, port), 0.5).close()
            return True
        except OSError:
            time.sleep(0.3)
    return False


def _mqtt_roundtrip() -> bool:
    """Publie un message et vérifie qu'un abonné le reçoit (round-trip réel)."""
    import json

    import paho.mqtt.client as mqtt

    recu: list[bool] = []
    topic = "sentinel/sensors"

    def make():
        try:
            return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            return mqtt.Client()

    sub = make()
    sub.on_message = lambda *a: recu.append(True)
    sub.connect("localhost", 1883, 30)
    sub.subscribe(topic)
    sub.loop_start()
    time.sleep(1)
    pub = make()
    pub.connect("localhost", 1883, 30)
    pub.publish(topic, json.dumps({"temp": 22, "humidity": 40, "gas": 100,
                                   "presence": 0, "timestamp": "2026-10-06T00:00:00Z"}))
    time.sleep(1.5)
    sub.loop_stop()
    sub.disconnect()
    pub.disconnect()
    return bool(recu)


# --------------------------------------------------------------------------- #
#  Orchestration + rapport
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="SENTINEL-X — Healthcheck")
    parser.add_argument("--quick", action="store_true",
                        help="saute les tests lourds (Docker/MQTT, Vision)")
    args = parser.parse_args()

    tests = [
        ("Dépendances Python", t_dependances),
        ("Structure projet", t_structure),
        ("Brique 3 — SQLite", t_brique3_sqlite),
        ("Brique 7 — API /health", t_brique7_api),
        ("Firmware ESP32", t_firmware),
        ("Sécurité (CYBER)", t_securite),
        ("Brique 6 — Prédictif", t_brique6_predictif),
    ]
    if not args.quick:
        tests.append(("Brique 3 — MQTT (Docker)", t_brique3_mqtt))
        tests.append(("Brique 5 — Vision (YOLO)", t_brique5_vision))

    print(f"\n{Style.BRIGHT}🛡️  SENTINEL-X — Rapport de santé{Style.RESET_ALL}")
    print("─" * 60)
    resultats = []
    for label, fn in tests:
        print(f"  … {label}", end="", flush=True)
        try:
            status, detail = fn()
        except Exception as exc:  # un test ne doit jamais casser le rapport
            status, detail = FAIL, f"{exc.__class__.__name__}: {exc}"
        resultats.append((label, status, detail))
        print(f"\r  {COULEUR[status]}[{status:4}]{Style.RESET_ALL} {label} — {detail}")

    print("─" * 60)
    n_ok = sum(1 for _, s, _ in resultats if s == OK)
    n_fail = sum(1 for _, s, _ in resultats if s == FAIL)
    n_skip = sum(1 for _, s, _ in resultats if s == SKIP)
    verdict = (f"{Fore.GREEN}✅ TOUT EST BON" if n_fail == 0
               else f"{Fore.RED}❌ {n_fail} test(s) en échec")
    print(f"{verdict}{Style.RESET_ALL}  "
          f"({n_ok} OK · {n_fail} FAIL · {n_skip} SKIP sur {len(resultats)})\n")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
