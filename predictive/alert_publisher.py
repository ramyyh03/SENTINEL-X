"""Publication des alertes vers MQTT (pour affichage sur l'OLED de l'ESP32).

Optionnel et dégradé proprement : activé seulement si ALERT_MQTT_ENABLED=true.
L'ESP32 flashé avec -DOLED_ALERTS s'abonne au topic et affiche l'alerte.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    import paho.mqtt.client as mqtt
except ImportError:          # paho absent : publication désactivée proprement
    mqtt = None  # type: ignore

ALERT_TOPIC = os.getenv("ALERT_TOPIC", "sentinel/alerts")
OLED_LARGEUR = 40            # ~largeur lisible sur l'écran OLED de l'ESP32
_client: Any = None          # singleton paresseux (une seule connexion)


def _texte_oled(txt: str) -> str:
    """Nettoie un contexte pour l'OLED (ASCII only : l'écran n'affiche pas les emojis)."""
    propre = (txt or "").encode("ascii", "ignore").decode("ascii")
    propre = re.sub(r"\s+", " ", propre).strip()
    return propre[:OLED_LARGEUR]


def _actif() -> bool:
    """La publication MQTT des alertes est-elle possible ? (activée par défaut).

    Publie les alertes sur le topic pour piloter l'OLED et les LEDs de l'ESP32.
    Dégrade proprement si paho/broker absent.
    """
    return mqtt is not None and os.getenv("ALERT_MQTT_ENABLED", "true").lower() == "true"


def _connecter() -> Any:
    """Crée (une fois) et retourne le client MQTT publisher, ou None si échec."""
    global _client
    if _client is not None:
        return _client
    try:
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                             client_id="sentinel-alert-pub")
    except AttributeError:
        client = mqtt.Client(client_id="sentinel-alert-pub")
    user = os.getenv("MQTT_USER") or None
    if user:
        client.username_pw_set(user, os.getenv("MQTT_PASSWORD") or None)
    try:
        client.connect(os.getenv("MQTT_HOST", "localhost"),
                       int(os.getenv("MQTT_PORT", "1883")), keepalive=30)
        client.loop_start()
        _client = client
    except OSError:
        _client = None
    return _client


def publier_alerte_mqtt(alerte: dict[str, Any]) -> bool:
    """Publie une alerte compacte sur le topic. Jamais bloquant, jamais fatal."""
    if not _actif():
        return False
    client = _connecter()
    if client is None:
        return False
    details = alerte.get("details") or {}
    compacte = {
        "type": alerte.get("type", "ALERTE"),
        "details": {
            "context": _texte_oled(details.get("context", "")),
            "severity": details.get("severity", "WARNING"),  # pilote la LED (rouge si CRITICAL)
        },
    }
    try:
        client.publish(ALERT_TOPIC, json.dumps(compacte, ensure_ascii=False))
        return True
    except (OSError, ValueError):
        return False
