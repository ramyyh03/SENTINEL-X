"""BRIQUE 3 — Client MQTT SENTINEL-X.

S'abonne au topic des capteurs, reçoit les mesures (DHT22, MQ-2, PIR)
publiées par l'ESP8266 (ou le simulateur), les valide et les affiche.

Usage :
    python scripts/mqtt_client.py

Config via .env (voir .env.example). Testable SANS matériel grâce au
simulateur : simulate/fake_sensors.py.
"""
from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv

# --- Constantes (pas de valeurs magiques dispersées) ---
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "sentinel/sensors"
TLS_PORT = 8883                       # port chiffré (prod, mercredi)
KEEPALIVE_SECONDS = 60
RECONNECT_MIN_DELAY = 1               # backoff reconnexion : départ
RECONNECT_MAX_DELAY = 30             # backoff reconnexion : plafond
# Champs attendus dans chaque message capteur + type toléré
EXPECTED_FIELDS = {
    "temp": (int, float),
    "humidity": (int, float),
    "gas": (int, float),
    "presence": (int,),
    "timestamp": (str,),
}

# .env à la racine du projet (parent du dossier scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
colorama_init(autoreset=True)


def log(prefix: str, color: str, message: str) -> None:
    """Affiche un log coloré et horodaté-léger (prefix = niveau)."""
    print(f"{color}[{prefix}]{Style.RESET_ALL} {message}")


def read_config() -> dict[str, Any]:
    """Lit la config MQTT depuis l'environnement, avec valeurs par défaut.

    Validation au niveau du bord système : le port doit être un entier.
    """
    raw_port = os.getenv("MQTT_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw_port)
    except ValueError:
        log("ERREUR", Fore.RED, f"MQTT_PORT invalide: {raw_port!r} — fallback {DEFAULT_PORT}")
        port = DEFAULT_PORT
    return {
        "host": os.getenv("MQTT_HOST", DEFAULT_HOST),
        "port": port,
        "user": os.getenv("MQTT_USER") or None,
        "password": os.getenv("MQTT_PASSWORD") or None,
        "topic": os.getenv("MQTT_TOPIC", DEFAULT_TOPIC),
        "ca_cert": os.getenv("MQTT_CA_CERT", str(PROJECT_ROOT / "mosquitto/certs/ca.crt")),
    }


def validate_payload(data: dict[str, Any]) -> list[str]:
    """Retourne la liste des erreurs de validation (vide si le message est OK)."""
    errors: list[str] = []
    for field, types in EXPECTED_FIELDS.items():
        if field not in data:
            errors.append(f"champ manquant: {field}")
        elif not isinstance(data[field], types):
            errors.append(f"type invalide pour {field}: {type(data[field]).__name__}")
    return errors


def make_client() -> mqtt.Client:
    """Crée un client paho compatible API v1 ET v2 (paho-mqtt 1.x / 2.x)."""
    try:
        # paho-mqtt 2.x impose de préciser la version de l'API de callbacks
        return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                           client_id="sentinel-subscriber")
    except AttributeError:
        # paho-mqtt 1.x : ancienne signature
        return mqtt.Client(client_id="sentinel-subscriber")


# --- Callbacks (signatures tolérantes v1/v2 via *args) ---

def on_connect(client: mqtt.Client, userdata: Any, flags: Any,
               reason_code: Any, properties: Any = None) -> None:
    """Appelé à la (re)connexion : on (re)souscrit au topic."""
    topic = userdata["topic"]
    # paho 1.x : reason_code est un int ; paho 2.x : un objet ReasonCode (.value)
    code = getattr(reason_code, "value", reason_code)
    if code == 0:
        log("OK", Fore.GREEN, f"Connecté au broker — abonnement à « {topic} »")
        client.subscribe(topic)
    else:
        log("ERREUR", Fore.RED, f"Connexion refusée (code {reason_code})")


def on_disconnect(client: mqtt.Client, userdata: Any, *args: Any) -> None:
    """Appelé à la déconnexion : paho relance la reconnexion automatiquement."""
    log("WARN", Fore.YELLOW, "Déconnecté — tentative de reconnexion automatique…")


def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
    """Appelé à chaque message : parse, valide et affiche la mesure."""
    try:
        data = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log("ERREUR", Fore.RED, f"JSON invalide sur {msg.topic}: {exc}")
        return

    errors = validate_payload(data)
    if errors:
        log("WARN", Fore.YELLOW, f"Message incomplet: {', '.join(errors)} → {data}")
        return

    presence = "👤 présence" if data["presence"] else "— vide"
    log("MSG", Fore.CYAN,
        f"Message reçu : {data['temp']}°C | {data['humidity']}% | "
        f"gaz {data['gas']}ppm | {presence} | {data['timestamp']}")


def main() -> int:
    """Point d'entrée : configure, connecte et boucle (reconnexion incluse)."""
    config = read_config()
    client = make_client()
    client.user_data_set({"topic": config["topic"]})
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    # Authentification si fournie
    if config["user"]:
        client.username_pw_set(config["user"], config["password"])

    # TLS-ready : activé automatiquement sur le port chiffré (prod, mercredi)
    if config["port"] == TLS_PORT:
        if Path(config["ca_cert"]).exists():
            client.tls_set(ca_certs=config["ca_cert"])
            log("OK", Fore.GREEN, f"TLS activé (CA: {config['ca_cert']})")
        else:
            log("ERREUR", Fore.RED, f"CA introuvable pour TLS: {config['ca_cert']}")
            return 1

    # Reconnexion automatique avec backoff
    client.reconnect_delay_set(min_delay=RECONNECT_MIN_DELAY, max_delay=RECONNECT_MAX_DELAY)

    log("INFO", Fore.MAGENTA,
        f"Connexion à {config['host']}:{config['port']} (topic « {config['topic']} »)… Ctrl+C pour arrêter")

    # Arrêt propre sur Ctrl+C
    signal.signal(signal.SIGINT, lambda *_: (client.disconnect(), sys.exit(0)))

    try:
        client.connect(config["host"], config["port"], keepalive=KEEPALIVE_SECONDS)
    except OSError as exc:
        log("ERREUR", Fore.RED, f"Connexion impossible: {exc}")
        log("INFO", Fore.MAGENTA, "Le broker est-il lancé ? → docker compose -f docker-compose.dev.yml up -d")
        return 1

    client.loop_forever(retry_first_connection=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
