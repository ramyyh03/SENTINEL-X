"""SENTINEL-X — Moniteur série ESP32 : voir les mesures des capteurs en direct.

Ouvre le port série de l'ESP32 (auto-détecté) et affiche ce qu'il imprime :
température (DHT22), humidité, gaz (MQ-2), présence (PIR). Confirme donc que
les CAPTEURS fonctionnent (pas seulement la carte).

Nécessite que l'ESP32 soit FLASHÉ avec le firmware (dossier firmware/).
Aucune install PlatformIO requise (utilise pyserial).

Usage :
    python scripts/esp32_monitor.py                 # auto-détecte le port + écoute 15 s
    python scripts/esp32_monitor.py --port COM3     # port forcé
    python scripts/esp32_monitor.py --seconds 30    # durée d'écoute
"""
from __future__ import annotations

import argparse
import sys
import time

BAUD = 115200
# Mots-clés qui prouvent que des données capteurs arrivent (format du firmware)
MOTS_CAPTEURS = ("T=", "H=", "Gaz", "PIR", "Temp", "Humi", "presence", "PRESENCE")


def trouver_port() -> str | None:
    """Auto-détecte le port série de l'ESP32 (puces CP210x/CH340/Silicon Labs/WCH)."""
    try:
        from serial.tools import list_ports
    except ImportError:
        print("❌ pyserial non installé : venv\\Scripts\\python -m pip install pyserial")
        return None
    cles = ("CP210", "CH340", "CH910", "USB-SERIAL", "SILICON LABS", "WCH", "ESP32")
    for p in list_ports.comports():
        texte = f"{p.description or ''} {p.manufacturer or ''}".upper()
        if any(k in texte for k in cles):
            return p.device
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="SENTINEL-X — Moniteur série ESP32")
    parser.add_argument("--port", default=None, help="port série (ex. COM3) ; auto-détecté sinon")
    parser.add_argument("--seconds", type=int, default=15, help="durée d'écoute (s)")
    parser.add_argument("--baud", type=int, default=BAUD, help="vitesse (défaut 115200)")
    args = parser.parse_args()

    try:
        import serial
    except ImportError:
        print("❌ pyserial non installé : venv\\Scripts\\python -m pip install pyserial")
        return 1

    port = args.port or trouver_port()
    if not port:
        print("❌ ESP32 introuvable (câble USB-C data ? pilote CP210x/CH340 ?).")
        return 1

    try:
        ser = serial.Serial(port, args.baud, timeout=1)
    except serial.SerialException as exc:
        print(f"❌ Ouverture de {port} impossible : {exc}")
        print("   (port déjà utilisé par un autre moniteur ? ferme PlatformIO / l'IDE Arduino.)")
        return 1

    print(f"🔌 Lecture de {port} @ {args.baud} bauds pendant {args.seconds}s… (Ctrl+C pour arrêter)\n")
    fin = time.time() + args.seconds
    total, avec_capteurs = 0, 0
    try:
        while time.time() < fin:
            ligne = ser.readline().decode("utf-8", errors="replace").strip()
            if not ligne:
                continue
            print("   " + ligne)
            total += 1
            if any(mot in ligne for mot in MOTS_CAPTEURS):
                avec_capteurs += 1
    except KeyboardInterrupt:
        print("\n(arrêt demandé)")
    finally:
        ser.close()

    print(f"\n── Résumé : {total} ligne(s) reçue(s), dont {avec_capteurs} avec des mesures capteurs ──")
    if avec_capteurs:
        print("✅ Les capteurs envoient des données (DHT22 / MQ-2 / PIR).")
        return 0
    if total:
        print("⚠️ L'ESP32 parle, mais aucune mesure capteur reconnue "
              "(firmware à flasher ? câblage DHT22/MQ-2/PIR ?).")
    else:
        print("⚠️ Aucune donnée reçue : l'ESP32 est-il FLASHÉ avec le firmware ? "
              "(dossier firmware/ → pio run -t upload)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
