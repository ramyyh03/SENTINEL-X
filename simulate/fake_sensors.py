"""BRIQUE 3 — Simulateur de capteurs ESP8266 (SENTINEL-X).

Publie des mesures RÉALISTES sur le topic MQTT des capteurs, pour permettre
de développer et tester la chaîne IA SANS attendre le câblage de l'ESP8266.

Usage :
    python simulate/fake_sensors.py            # publie en continu (toutes les 2s)
    python simulate/fake_sensors.py --simulate # publie 10 cycles puis s'arrête

Config via .env (mêmes MQTT_HOST / MQTT_PORT que le client).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv

# --- Constantes ---
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "sentinel/sensors"
PUBLISH_INTERVAL_SECONDS = 2.0
SIMULATE_CYCLES = 10                 # nb de cycles en mode --simulate
# Plages réalistes des capteurs
TEMP_RANGE = (20.0, 30.0)            # DHT22 — °C
HUMIDITY_RANGE = (30.0, 70.0)        # DHT22 — %
GAS_RANGE = (100, 200)              # MQ-2 — ppm (valeur ambiante normale)
PRESENCE_PROBABILITY = 0.3          # PIR — proba qu'il y ait quelqu'un

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
colorama_init(autoreset=True)


def log(prefix: str, color: str, message: str) -> None:
    """Affiche un log coloré."""
    print(f"{color}[{prefix}]{Style.RESET_ALL} {message}")


def read_config() -> dict[str, Any]:
    """Lit host/port/topic depuis l'environnement avec valeurs par défaut."""
    try:
        port = int(os.getenv("MQTT_PORT", str(DEFAULT_PORT)))
    except ValueError:
        port = DEFAULT_PORT
    return {
        "host": os.getenv("MQTT_HOST", DEFAULT_HOST),
        "port": port,
        "user": os.getenv("MQTT_USER") or None,
        "password": os.getenv("MQTT_PASSWORD") or None,
        "topic": os.getenv("MQTT_TOPIC", DEFAULT_TOPIC),
    }


def generate_reading() -> dict[str, Any]:
    """Génère une mesure capteur réaliste (nouvel objet immuable à chaque appel)."""
    return {
        "temp": round(random.uniform(*TEMP_RANGE), 1),
        "humidity": round(random.uniform(*HUMIDITY_RANGE), 1),
        "gas": random.randint(*GAS_RANGE),
        "presence": 1 if random.random() < PRESENCE_PROBABILITY else 0,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def make_client() -> mqtt.Client:
    """Crée un client paho compatible paho-mqtt 1.x ET 2.x."""
    try:
        return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                           client_id="sentinel-fake-esp8266")
    except AttributeError:
        return mqtt.Client(client_id="sentinel-fake-esp8266")


def run(cycles: int | None) -> int:
    """Publie des mesures. `cycles=None` = infini ; sinon N cycles puis stop."""
    config = read_config()
    client = make_client()
    if config["user"]:
        client.username_pw_set(config["user"], config["password"])

    try:
        client.connect(config["host"], config["port"], keepalive=60)
    except OSError as exc:
        log("ERREUR", Fore.RED, f"Connexion impossible à {config['host']}:{config['port']} — {exc}")
        log("INFO", Fore.MAGENTA, "Lancer le broker : docker compose -f docker-compose.dev.yml up -d")
        return 1

    client.loop_start()
    mode = f"{cycles} cycles" if cycles else "continu (Ctrl+C pour arrêter)"
    log("INFO", Fore.MAGENTA, f"Simulateur ESP8266 → {config['host']}:{config['port']} / "
                              f"« {config['topic']} » — mode {mode}")

    count = 0
    try:
        while cycles is None or count < cycles:
            reading = generate_reading()
            client.publish(config["topic"], json.dumps(reading))
            count += 1
            log("PUB", Fore.GREEN, f"#{count} publié : {reading}")
            time.sleep(PUBLISH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        log("INFO", Fore.MAGENTA, "Arrêt demandé.")
    finally:
        client.loop_stop()
        client.disconnect()

    log("OK", Fore.GREEN, f"Terminé — {count} message(s) publié(s).")
    return 0


def main() -> int:
    """Parse les arguments et lance la simulation."""
    parser = argparse.ArgumentParser(description="Simulateur de capteurs ESP8266 (SENTINEL-X)")
    parser.add_argument("--simulate", action="store_true",
                        help=f"publie {SIMULATE_CYCLES} cycles puis s'arrête (sinon: continu)")
    args = parser.parse_args()
    return run(cycles=SIMULATE_CYCLES if args.simulate else None)


if __name__ == "__main__":
    sys.exit(main())
