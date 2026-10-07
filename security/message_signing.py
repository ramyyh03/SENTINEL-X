"""Signature HMAC-SHA256 des messages capteurs (anti-injection).

Problème résolu : sur un broker MQTT ouvert, n'importe qui peut publier un faux
message (cf. REDTEAM-PLAYBOOK). Avec une clé secrète PARTAGÉE entre l'ESP32 et
le serveur, chaque message porte une signature `sig`. Un message sans la bonne
clé produit une signature invalide → il est rejeté. L'attaquant ne connaît pas
la clé, donc il ne peut pas forger un message accepté.

Choix d'implémentation : on signe une CHAÎNE CANONIQUE (ordre et format des
champs figés) plutôt que le JSON brut. Ainsi l'ESP32 (C/mbedtls) et Python
produisent exactement les mêmes octets, sans dépendre du formatage JSON.

Format canonique :  temp|humidity|gas|presence|timestamp
    ex.  "23.4|51.0|180|1|2026-10-07T12:00:00Z"
    (temp/humidity à 1 décimale, gas/presence entiers, timestamp tel quel)
"""
from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Any

CHAMP_SIGNATURE = "sig"


def message_canonique(data: dict[str, Any]) -> str:
    """Construit la chaîne déterministe signée (identique côté ESP32)."""
    return (f"{float(data['temp']):.1f}|{float(data['humidity']):.1f}|"
            f"{int(data['gas'])}|{int(data['presence'])}|{data['timestamp']}")


def signer(data: dict[str, Any], secret: str) -> str:
    """Retourne la signature HMAC-SHA256 hexadécimale du message."""
    canonique = message_canonique(data).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), canonique, sha256).hexdigest()


def verifier(data: dict[str, Any], signature: str, secret: str) -> bool:
    """Vrai si la signature correspond. Comparaison à temps constant (anti-timing)."""
    if not signature:
        return False
    try:
        attendue = signer(data, secret)
    except (KeyError, ValueError, TypeError):
        return False
    return hmac.compare_digest(attendue, signature)
