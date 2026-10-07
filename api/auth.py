"""BRIQUE 7 (sécurité) — Authentification locale du dashboard : mot de passe + 2FA (TOTP).

- Mot de passe stocké **haché** (jamais en clair).
- Double authentification via une app **Authenticator** (Microsoft/Google…) : code à
  6 chiffres (standard TOTP, RFC 6238), vérifié localement — aucun cloud requis.
- L'admin crée un compte par personne autorisée (scripts/setup_2fa.py). Les autres
  n'ont que la **vue** (lecture seule).

Fichier des comptes : data/dashboard_users.json  (gitignoré — contient des secrets).
"""
from __future__ import annotations

import json
from functools import wraps
from pathlib import Path

import pyotp
from flask import redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

PROJECT_ROOT = Path(__file__).resolve().parent.parent
USERS_FILE = PROJECT_ROOT / "data" / "dashboard_users.json"


def _charger() -> dict:
    """Charge le fichier des comptes (vide si absent)."""
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _sauver(users: dict) -> None:
    """Écrit le fichier des comptes (créé le dossier si besoin)."""
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def creer_utilisateur(username: str, password: str) -> str:
    """Crée (ou met à jour) un compte. Retourne le secret TOTP (à scanner)."""
    users = _charger()
    secret = pyotp.random_base32()
    users[username] = {
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "totp_secret": secret,
    }
    _sauver(users)
    return secret


def uri_provisioning(username: str, secret: str, issuer: str = "SENTINEL-X") -> str:
    """URI otpauth:// à encoder en QR pour l'app Authenticator."""
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def verifier(username: str, password: str, code: str) -> bool:
    """Vérifie le trio identifiant + mot de passe + code TOTP (2FA)."""
    user = _charger().get(username)
    if not user:
        return False
    if not check_password_hash(user["password_hash"], password):
        return False
    # valid_window=1 : tolère un décalage d'horloge d'un intervalle (30 s)
    return pyotp.TOTP(user["totp_secret"]).verify(str(code).strip(), valid_window=1)


def login_required(view):
    """Décorateur : exige une connexion. Si AUCUN compte n'existe encore, l'accès
    reste ouvert (pour ne pas se verrouiller dehors) ; dès qu'un compte est créé,
    le login + 2FA devient obligatoire."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if comptes_existants() and not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def comptes_existants() -> bool:
    """True s'il y a au moins un compte configuré."""
    return bool(_charger())
