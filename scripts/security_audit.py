"""SENTINEL-X — Auto-audit de sécurité (« Suis-je sécurisé ? »).

Vérifie, côté DÉFENSE, les failles classiques de NOTRE propre système, puis
(optionnel) demande à Ollama d'expliquer en clair et de prioriser les correctifs.

Classes de failles vérifiées :
    1. Secrets versionnés par erreur (secrets.h, .env, clés, comptes 2FA)
    2. Dashboard sans authentification (aucun compte créé = accès libre)
    3. XSS : données MQTT affichées sans échappement dans le dashboard
    4. Broker MQTT en clair / anonyme (1883) au lieu de MQTTS (8883 + auth)
    5. API exposée sur le LAN (API_HOST=0.0.0.0) + endpoint d'alertes ouvert
    6. Clé de session Flask absente (sessions non signées)

Usage :
    python scripts/security_audit.py            # audit + rapport
    python scripts/security_audit.py --fix       # applique les correctifs sûrs
    python scripts/security_audit.py --explain    # fait expliquer par Ollama
"""
from __future__ import annotations

import argparse
import os
import secrets as _secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# --- Seuils / constantes (pas de valeurs magiques dispersées) ------------- #
PORT_MQTT_CHIFFRE = 8883
PORT_MQTT_CLAIR = 1883
HOST_EXPOSE_LAN = "0.0.0.0"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

# Fichiers qui ne doivent JAMAIS être suivis par Git (secrets réels).
# NB : un certificat public (.crt) est fait pour être distribué → pas un secret.
# Seule la CLÉ PRIVÉE (.key, ou un .pem contenant « PRIVATE KEY ») est sensible.
SECRETS_INTERDITS = (
    "firmware/include/secrets.h",
    ".env",
    "data/dashboard_users.json",
    "data/.flask_secret",
    "docker/mosquitto/config/passwd",
)
EXTENSIONS_INTERDITES = (".key",)   # clés privées uniquement

# Couleurs ANSI (dégradées proprement si le terminal ne les gère pas).
C_ROUGE, C_JAUNE, C_VERT, C_BLEU, C_GRIS, C_RESET = (
    "\033[91m", "\033[93m", "\033[92m", "\033[96m", "\033[90m", "\033[0m")


@dataclass(frozen=True)
class Constat:
    """Résultat immuable d'un contrôle de sécurité."""

    controle: str
    ok: bool
    gravite: str          # CRITICAL | HIGH | MEDIUM | LOW | OK
    message: str
    correctif: str
    auto_corrigeable: bool = False


# --------------------------------------------------------------------------- #
#  Utilitaires
# --------------------------------------------------------------------------- #
def _fichiers_suivis_git() -> set[str]:
    """Liste les fichiers suivis par Git (vide si hors dépôt)."""
    try:
        sortie = subprocess.run(
            ["git", "ls-files"], cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=10, check=True)
        return set(sortie.stdout.splitlines())
    except (subprocess.SubprocessError, FileNotFoundError):
        return set()


def _lire(path: Path) -> str:
    """Lit un fichier texte, chaîne vide si absent/illisible."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


# --------------------------------------------------------------------------- #
#  Contrôles (une fonction = une faille, retourne un Constat immuable)
# --------------------------------------------------------------------------- #
def _pem_contient_cle_privee(chemin: str) -> bool:
    """Un .pem n'est sensible que s'il contient une CLÉ PRIVÉE (pas un cert public)."""
    if not chemin.endswith(".pem"):
        return False
    return "PRIVATE KEY" in _lire(PROJECT_ROOT / chemin)


def controle_secrets_versionnes(suivis: set[str]) -> Constat:
    """Faille 1 : un secret committé est un secret fuité."""
    fuites = [f for f in suivis
              if f in SECRETS_INTERDITS
              or f.endswith(EXTENSIONS_INTERDITES)
              or _pem_contient_cle_privee(f)]
    if fuites:
        return Constat(
            "Secrets dans Git", False, "CRITICAL",
            f"{len(fuites)} fichier(s) sensible(s) suivi(s) : {', '.join(fuites)}",
            "git rm --cached <fichier> + vérifier .gitignore + ROTATER le secret exposé",
            auto_corrigeable=False)
    return Constat("Secrets dans Git", True, "OK",
                   "Aucun secret suivi par Git.", "")


def controle_dashboard_auth() -> Constat:
    """Faille 2 : sans compte créé, le dashboard est ouvert à tous."""
    comptes = PROJECT_ROOT / "data" / "dashboard_users.json"
    contenu = _lire(comptes).strip()
    a_des_comptes = bool(contenu) and contenu not in ("{}", "[]")
    if not a_des_comptes:
        return Constat(
            "Auth dashboard", False, "HIGH",
            "Aucun compte 2FA : le dashboard est accessible sans mot de passe.",
            "make setup-2fa (crée un compte admin + 2FA ; l'accès se verrouille ensuite)",
            auto_corrigeable=False)
    return Constat("Auth dashboard", True, "OK",
                   "Au moins un compte 2FA existe : l'accès est verrouillé.", "")


def controle_xss() -> Constat:
    """Faille 3 : données MQTT rendues sans html.escape = XSS stocké."""
    server = _lire(PROJECT_ROOT / "api" / "server.py")
    if "import html" in server and server.count("html.escape") >= 5:
        return Constat("Échappement XSS", True, "OK",
                       "Les données capteurs sont échappées avant affichage.", "")
    return Constat(
        "Échappement XSS", False, "HIGH",
        "Des champs capteurs semblent affichés sans html.escape (XSS possible).",
        "Entourer toute donnée externe de html.escape(str(...)) dans api/server.py",
        auto_corrigeable=False)


def controle_mqtt_chiffre() -> Constat:
    """Faille 4 : broker en clair/anonyme = lecture + injection libres."""
    port = int(os.getenv("MQTT_PORT", str(PORT_MQTT_CLAIR)))
    if port == PORT_MQTT_CHIFFRE:
        return Constat("MQTT chiffré", True, "OK",
                       f"MQTT sur {port} (TLS + auth attendus).", "")
    return Constat(
        "MQTT chiffré", False, "MEDIUM",
        f"MQTT sur {port} (en clair, anonyme). Acceptable en DÉMO sur hotspot isolé, "
        "mais lecture et injection restent possibles depuis le réseau.",
        "Production : MQTTS 8883 + mot de passe + signature HMAC des messages "
        "(voir BRIQUES/BROKER-MQTT.md)",
        auto_corrigeable=False)


def controle_hmac_injection() -> Constat:
    """Faille 4bis : sans HMAC, un faux message MQTT est accepté (injection)."""
    secret = os.getenv("MQTT_HMAC_SECRET") or ""
    strict = os.getenv("MQTT_HMAC_STRICT", "false").lower() == "true"
    if secret and strict:
        return Constat("Anti-injection HMAC", True, "OK",
                       "HMAC strict : tout message non signé ou falsifié est rejeté.", "")
    if secret:
        return Constat(
            "Anti-injection HMAC", True, "OK",
            "HMAC actif (souple) : un faux message signé est rejeté ; "
            "les messages non signés restent tolérés.", "")
    return Constat(
        "Anti-injection HMAC", False, "MEDIUM",
        "Pas de clé HMAC : n'importe qui sur le réseau peut injecter un faux "
        "message capteur (cf. REDTEAM-PLAYBOOK, mode --inject).",
        "Définir MQTT_HMAC_SECRET dans .env + flasher l'ESP32 avec -DUSE_HMAC "
        "(même clé dans secrets.h)",
        auto_corrigeable=False)


def controle_api_exposee() -> Constat:
    """Faille 5 : API exposée LAN + endpoint d'alertes sans auth."""
    host = os.getenv("API_HOST", "127.0.0.1").split("#")[0].strip()
    if host == HOST_EXPOSE_LAN:
        return Constat(
            "Exposition API", False, "MEDIUM",
            "API_HOST=0.0.0.0 : nécessaire pour l'accès jury, mais /api/v1/alerts "
            "n'est pas authentifié → n'importe qui sur le hotspot peut injecter une alerte.",
            "Garder 0.0.0.0 pour la démo, mais signer les alertes (HMAC) et/ou "
            "restreindre par IP source du firmware",
            auto_corrigeable=False)
    return Constat("Exposition API", True, "OK",
                   f"API_HOST={host} (accès local uniquement).", "")


def controle_cle_session() -> Constat:
    """Faille 6 : sans clé de session persistante, les sessions sont fragiles."""
    cle = PROJECT_ROOT / "data" / ".flask_secret"
    if cle.exists() and cle.stat().st_size >= 16:
        return Constat("Clé de session Flask", True, "OK",
                       "Clé de session présente (cookies de login signés).", "")
    return Constat(
        "Clé de session Flask", False, "LOW",
        "Clé de session absente : elle sera régénérée à chaque démarrage "
        "(déconnexions intempestives).",
        "Générer data/.flask_secret (fait automatiquement avec --fix)",
        auto_corrigeable=True)


def lancer_controles() -> list[Constat]:
    """Exécute tous les contrôles dans l'ordre de gravité décroissante."""
    suivis = _fichiers_suivis_git()
    return [
        controle_secrets_versionnes(suivis),
        controle_dashboard_auth(),
        controle_xss(),
        controle_mqtt_chiffre(),
        controle_hmac_injection(),
        controle_api_exposee(),
        controle_cle_session(),
    ]


# --------------------------------------------------------------------------- #
#  Correctifs automatiques (uniquement les SÛRS et non destructifs)
# --------------------------------------------------------------------------- #
def appliquer_correctifs(constats: list[Constat]) -> list[str]:
    """Applique les correctifs auto-corrigeables. Retourne la liste des actions."""
    actions: list[str] = []
    for c in constats:
        if c.ok or not c.auto_corrigeable:
            continue
        if c.controle == "Clé de session Flask":
            cle = PROJECT_ROOT / "data" / ".flask_secret"
            cle.parent.mkdir(parents=True, exist_ok=True)
            cle.write_text(_secrets.token_hex(32), encoding="utf-8")
            actions.append(f"Clé de session générée → {cle.relative_to(PROJECT_ROOT)}")
    actions.extend(_durcir_permissions())
    return actions


def _durcir_permissions() -> list[str]:
    """Restreint les droits des fichiers sensibles (lecture propriétaire only)."""
    actions: list[str] = []
    sensibles = (".env", "data/.flask_secret", "data/dashboard_users.json")
    for rel in sensibles:
        f = PROJECT_ROOT / rel
        if not f.exists():
            continue
        try:
            if (f.stat().st_mode & 0o077) != 0:   # déjà restreint ? on ne refait rien
                f.chmod(0o600)
                actions.append(f"Droits restreints (600) → {rel}")
        except OSError:
            pass   # Windows gère peu chmod : sans effet, mais jamais bloquant
    return actions


# --------------------------------------------------------------------------- #
#  Explication Ollama (optionnelle, dégradée proprement)
# --------------------------------------------------------------------------- #
def expliquer_avec_ollama(constats: list[Constat]) -> str:
    """Demande à Ollama une synthèse priorisée en clair. Vide si indisponible."""
    try:
        import requests
    except ImportError:
        return ""
    echecs = [c for c in constats if not c.ok]
    if not echecs:
        return ""
    liste = "\n".join(f"- [{c.gravite}] {c.controle} : {c.message}" for c in echecs)
    prompt = (
        "Tu es analyste cybersécurité. Voici les failles détectées sur un système "
        f"IoT de surveillance (ESP32 + MQTT + dashboard Flask) :\n{liste}\n\n"
        "En 3 à 5 phrases, explique le risque réel et donne l'ordre de correction "
        "le plus efficace. Sois concret, pas de généralités.")
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate",
                          json={"model": OLLAMA_MODEL, "prompt": prompt,
                                "stream": False, "options": {"temperature": 0.3}},
                          timeout=20)
        if r.status_code == 200:
            return r.json().get("response", "").strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


# --------------------------------------------------------------------------- #
#  Rapport
# --------------------------------------------------------------------------- #
_COULEUR_GRAVITE = {
    "CRITICAL": C_ROUGE, "HIGH": C_ROUGE, "MEDIUM": C_JAUNE,
    "LOW": C_BLEU, "OK": C_VERT}


def afficher_rapport(constats: list[Constat]) -> int:
    """Affiche le rapport coloré. Retourne le code de sortie (0 = sain)."""
    echecs = [c for c in constats if not c.ok]
    critiques = [c for c in echecs if c.gravite in ("CRITICAL", "HIGH")]

    print(f"\n{C_BLEU}╔══════════════════════════════════════════════════╗")
    print(f"║   SENTINEL-X — Suis-je sécurisé ?                 ║")
    print(f"╚══════════════════════════════════════════════════╝{C_RESET}\n")

    for c in constats:
        couleur = _COULEUR_GRAVITE.get(c.gravite, C_GRIS)
        icone = "✓" if c.ok else "✗"
        print(f"{couleur}[{icone}] {c.controle:<22} {c.gravite}{C_RESET}")
        print(f"    {c.message}")
        if not c.ok and c.correctif:
            print(f"    {C_GRIS}→ {c.correctif}{C_RESET}")
        print()

    if not echecs:
        print(f"{C_VERT}✓ Système sain : aucune faille détectée.{C_RESET}\n")
        return 0
    verdict = "NON SÉCURISÉ" if critiques else "À RENFORCER"
    couleur = C_ROUGE if critiques else C_JAUNE
    print(f"{couleur}⚠  {verdict} : {len(echecs)} point(s), "
          f"dont {len(critiques)} critique(s)/élevé(s).{C_RESET}\n")
    return 1 if critiques else 0


def main() -> int:
    """Point d'entrée CLI."""
    p = argparse.ArgumentParser(description="Auto-audit de sécurité SENTINEL-X")
    p.add_argument("--fix", action="store_true",
                   help="applique les correctifs sûrs (clé de session…)")
    p.add_argument("--explain", action="store_true",
                   help="fait expliquer/prioriser les failles par Ollama")
    args = p.parse_args()

    constats = lancer_controles()

    if args.fix:
        actions = appliquer_correctifs(constats)
        for a in actions:
            print(f"{C_VERT}[FIX] {a}{C_RESET}")
        if actions:
            constats = lancer_controles()   # re-contrôle après correction

    code = afficher_rapport(constats)

    if args.explain:
        print(f"{C_BLEU}── Analyse Ollama ──{C_RESET}")
        synthese = expliquer_avec_ollama(constats)
        print(synthese if synthese
              else f"{C_GRIS}Ollama indisponible (ollama serve + ollama pull mistral).{C_RESET}")
        print()
    return code


if __name__ == "__main__":
    sys.exit(main())


# ─────────────────────────────────────────────────────────────────────────
# 📘 Ce que j'ai fait
# ─────────────────────────────────────────────────────────────────────────
# Ce script répond à ta demande « quand je demande si je suis sécurisé, ça
# vérifie tout et ça me sécurise ». Il contrôle 6 classes de failles RÉELLES
# de NOTRE système (secrets versionnés, dashboard sans auth, XSS, MQTT en
# clair, API exposée, clé de session), affiche un verdict clair, et avec
# --fix applique les correctifs SÛRS automatiquement (ex. génération de la
# clé de session). Les correctifs risqués (retirer un secret de Git, rotation
# de clé) ne sont JAMAIS faits en douce : le script affiche la commande exacte
# pour que tu décides. Avec --explain, Ollama traduit les failles en langage
# clair et te donne l'ordre de correction — en dégradant proprement s'il est
# absent. C'est de la DÉFENSE : on audite notre propre maison, pas celle des
# autres.
