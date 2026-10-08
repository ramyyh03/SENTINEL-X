"""SENTINEL-X — Prépare le fichier secrets.h de l'ESP32.

- Détecte l'IP du PC (le broker) et la pré-remplit dans secrets.h.
- Crée firmware/include/secrets.h (si absent) avec les #define prêts.
- Ouvre le fichier pour que tu saisisses seulement le WiFi + le mot de passe.

secrets.h est gitignoré : il ne part JAMAIS sur GitHub.

Usage :
    python scripts/config_esp32.py
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRETS = PROJECT_ROOT / "firmware" / "include" / "secrets.h"

TEMPLATE = """#pragma once
// SENTINEL-X — Config EN DUR de l'ESP32 (secrets.h) — GITIGNORE, ne jamais pousser.
// Remplis WIFI_SSID et WIFI_PASSWORD, enregistre, puis flashe :
//   pio run -e esp32dev-secrets -t upload

#define WIFI_SSID     "A_REMPLIR"      // <-- nom de ton reseau WiFi
#define WIFI_PASSWORD "A_REMPLIR"      // <-- mot de passe du WiFi
#define BROKER_IP     "{ip}"           // IP du PC-broker (detectee automatiquement)
"""


def ip_locale() -> str:
    """IP du PC sur le réseau (celle de la route par défaut, pas WSL/virtuelle)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))     # pas de trafic réel : juste pour lire l'IP de sortie
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "192.168.1.100"


def ouvrir(path: Path) -> None:
    """Ouvre le fichier dans l'éditeur par défaut (notepad sur Windows)."""
    try:
        if os.name == "nt":
            subprocess.Popen(["notepad", str(path)])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-t", str(path)])
        else:
            subprocess.run(["xdg-open", str(path)])
    except Exception:
        print(f"   (ouvre-le manuellement : {path})")


def main() -> int:
    ip = ip_locale()
    print(f"IP du PC detectee (= IP du broker) : {ip}")

    if SECRETS.exists():
        # On met A JOUR seulement BROKER_IP, en PRESERVANT le WiFi saisi.
        contenu = SECRETS.read_text(encoding="utf-8")
        nouveau, n = re.subn(r'#define\s+BROKER_IP\s+"[^"]*"',
                             f'#define BROKER_IP     "{ip}"', contenu)
        if n == 0:                                   # pas de ligne BROKER_IP -> on l'ajoute
            nouveau = contenu.rstrip() + f'\n#define BROKER_IP     "{ip}"\n'
        SECRETS.write_text(nouveau, encoding="utf-8")
        print(f"[OK] BROKER_IP mis a jour -> {ip}  (WiFi preserve)")
        print("Reflashe maintenant :  make.bat flash-full")
    else:
        SECRETS.parent.mkdir(parents=True, exist_ok=True)
        SECRETS.write_text(TEMPLATE.format(ip=ip), encoding="utf-8")
        print(f"[OK] secrets.h cree avec BROKER_IP = {ip}")
        print("Remplis WIFI_SSID + WIFI_PASSWORD, enregistre, puis : make.bat flash-full")
        ouvrir(SECRETS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
