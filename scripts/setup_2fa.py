"""SENTINEL-X — Crée un compte dashboard avec double authentification (2FA/TOTP).

À lancer par l'ADMIN pour donner accès à quelqu'un. Génère un mot de passe +
un secret TOTP, et affiche un QR code à scanner dans **Microsoft Authenticator**
(ou Google Authenticator). Ensuite, la personne se connecte avec :
    identifiant + mot de passe + code à 6 chiffres de l'app.

Usage :
    python scripts/setup_2fa.py --user alice
    python scripts/setup_2fa.py --user bob --password "motdepasse"
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import qrcode  # noqa: E402

from api.auth import creer_utilisateur, uri_provisioning  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="SENTINEL-X — Créer un compte dashboard (2FA)")
    parser.add_argument("--user", default=None, help="identifiant du compte (sinon demandé)")
    parser.add_argument("--password", default=None, help="mot de passe (sinon demandé)")
    args = parser.parse_args()

    args.user = args.user or input("Identifiant du nouveau compte : ").strip()
    if not args.user:
        print("❌ Identifiant vide.")
        return 1
    password = args.password or getpass.getpass("Mot de passe pour ce compte : ")
    if len(password) < 6:
        print("❌ Mot de passe trop court (6 caractères minimum).")
        return 1

    secret = creer_utilisateur(args.user, password)
    uri = uri_provisioning(args.user, secret)

    print(f"\n✅ Compte « {args.user} » créé.\n")
    print("📱 Scanne ce QR code dans Microsoft Authenticator (ou Google Authenticator) :\n")
    qr = qrcode.QRCode(border=1)
    qr.add_data(uri)
    qr.make()
    qr.print_ascii(invert=True)   # QR affiché dans le terminal

    print(f"\n   (si le QR ne passe pas, saisie manuelle de la clé : {secret})")
    print("\nEnsuite, connexion sur http://<IP-du-PC>:3000/login")
    print("avec : identifiant + mot de passe + code à 6 chiffres de l'app.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
