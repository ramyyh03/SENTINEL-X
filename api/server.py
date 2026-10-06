"""BRIQUE 7 — Serveur de réception des alertes SENTINEL-X (Flask).

Reçoit les alertes POSTées par les Briques 5 (Vision) et 6 (Prédictif), les
valide, les stocke en SQLite (table `alerts`) et les affiche sur un dashboard.

Pourquoi Flask : micro-framework minimal, parfait pour un serveur d'alertes
simple (3 routes) sans la lourdeur d'un gros framework. Cross-plateforme
(Windows inclus), aucune dépendance système.

Endpoints :
    POST /api/v1/alerts   reçoit + valide + stocke une alerte  → 201
    GET  /dashboard       page HTML (50 dernières alertes, auto-refresh 5 s)
    GET  /health          état du serveur (JSON)

Sécurité (couche HTTP uniquement — ne double PAS le TLS/auth MQTT du CYBER) :
    - validation stricte du JSON + Content-Type obligatoire
    - rate limiting basique (100 req/min par IP)
    - log de chaque requête avec IP source
    - bind sur 127.0.0.1 par défaut (ne pas exposer sur le LAN sans raison)
    NB : le chiffrement HTTPS de l'API reste une tâche CYBER (voir SECURITE.md).
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from api.alert_store import AlertStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# --- Config (surchargeable via .env) ---
API_HOST = os.getenv("API_HOST", "127.0.0.1")   # local par défaut (sécurité)
API_PORT = int(os.getenv("API_PORT", "3000"))
RATE_MAX = int(os.getenv("API_RATE_MAX", "100"))     # requêtes max…
RATE_WINDOW_S = int(os.getenv("API_RATE_WINDOW", "60"))  # …par fenêtre (s) et par IP

# --- Champs obligatoires de l'alerte (format immuable) + types tolérés ---
CHAMPS_REQUIS: dict[str, tuple] = {
    "source": (str,),
    "type": (str,),
    "confidence": (int, float),
    "timestamp": (str,),
    "details": (dict,),
}

# --- Logging (console + fichier) ---
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOGS_DIR / "api.log", encoding="utf-8"),
              logging.StreamHandler()],
)
logger = logging.getLogger("sentinel-api")

_DEMARRAGE = time.monotonic()
_requetes_par_ip: dict[str, deque] = defaultdict(deque)


def valider_alerte(data: object) -> list[str]:
    """Valide le format de l'alerte. Retourne la liste des erreurs (vide si OK)."""
    if not isinstance(data, dict):
        return ["le corps doit être un objet JSON"]
    erreurs: list[str] = []
    for champ, types in CHAMPS_REQUIS.items():
        if champ not in data:
            erreurs.append(f"champ manquant: {champ}")
        elif not isinstance(data[champ], types):
            erreurs.append(f"type invalide pour {champ} "
                           f"(attendu {types[0].__name__})")
    # Bornes métier : confidence dans [0,1]
    conf = data.get("confidence")
    if isinstance(conf, (int, float)) and not 0.0 <= conf <= 1.0:
        erreurs.append("confidence hors bornes (attendu 0.0–1.0)")
    return erreurs


def _rate_limit_ok(ip: str) -> bool:
    """Vrai si l'IP n'a pas dépassé RATE_MAX requêtes sur la fenêtre glissante."""
    maintenant = time.monotonic()
    fenetre = _requetes_par_ip[ip]
    while fenetre and fenetre[0] < maintenant - RATE_WINDOW_S:
        fenetre.popleft()
    if len(fenetre) >= RATE_MAX:
        return False
    fenetre.append(maintenant)
    return True


def _severite(alerte: dict) -> str:
    """Sévérité pour l'affichage : lue dans details, sinon déduite de la confidence."""
    sev = (alerte.get("details") or {}).get("severity")
    if sev:
        return str(sev).upper()
    conf = alerte.get("confidence") or 0
    if conf >= 0.8:
        return "CRITICAL"
    if conf >= 0.6:
        return "WARNING"
    if conf >= 0.4:
        return "INFO"
    return "LOW"


# Couleurs : CRITICAL rouge · WARNING/HIGH orange · INFO/MEDIUM jaune · LOW vert
_COULEURS = {
    "CRITICAL": "#c0392b", "WARNING": "#e67e22", "HIGH": "#e67e22",
    "INFO": "#f1c40f", "MEDIUM": "#f1c40f", "LOW": "#27ae60",
}


def create_app(store: AlertStore | None = None) -> Flask:
    """Fabrique l'application Flask (factory → facile à tester via test_client)."""
    app = Flask(__name__)
    magasin = store or AlertStore()

    @app.post("/api/v1/alerts")
    def recevoir_alerte():
        ip = request.remote_addr or "?"
        logger.info("POST /api/v1/alerts depuis %s", ip)

        if not _rate_limit_ok(ip):
            logger.warning("Rate limit dépassé pour %s", ip)
            return jsonify({"error": "trop de requêtes (rate limit)"}), 429
        if not request.is_json:
            return jsonify({"error": "Content-Type: application/json requis"}), 415

        data = request.get_json(silent=True)
        erreurs = valider_alerte(data)
        if erreurs:
            logger.warning("Alerte rejetée (%s) : %s", ip, erreurs)
            return jsonify({"error": "format invalide", "details": erreurs}), 400

        alert_id = magasin.insert_alert(data)
        if alert_id is None:
            return jsonify({"error": "échec stockage"}), 500
        logger.info("Alerte #%s stockée : %s / %s (conf=%s)",
                    alert_id, data["source"], data["type"], data["confidence"])
        return jsonify({"status": "stored", "id": alert_id}), 201

    @app.get("/health")
    def sante():
        secondes = int(time.monotonic() - _DEMARRAGE)
        uptime = f"{secondes // 3600}h{(secondes % 3600) // 60:02d}m{secondes % 60:02d}s"
        return jsonify({"status": "ok", "alerts_count": magasin.count(), "uptime": uptime})

    @app.get("/dashboard")
    def dashboard():
        return _page_dashboard(magasin.recent(50))

    return app


def _page_dashboard(alertes: list[dict]) -> str:
    """Construit la page HTML du dashboard (CSS inline, auto-refresh 5 s)."""
    lignes = ""
    for a in alertes:
        sev = _severite(a)
        couleur = _COULEURS.get(sev, "#7f8c8d")
        details = a.get("details") or {}
        contexte = details.get("context") or details.get("persons_detected", "")
        lignes += (
            f"<tr>"
            f"<td>{a.get('timestamp', '')}</td>"
            f"<td>{a.get('source', '')}</td>"
            f"<td>{a.get('type', '')}</td>"
            f"<td style='text-align:center'>{a.get('confidence', '')}</td>"
            f"<td><span class='badge' style='background:{couleur}'>{sev}</span></td>"
            f"<td class='details'>{contexte}</td>"
            f"</tr>"
        )
    if not lignes:
        lignes = "<tr><td colspan='6' style='text-align:center;color:#888'>Aucune alerte pour l'instant</td></tr>"

    maj = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>SENTINEL-X — Alertes</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#1b1f23; color:#e6e6e6; margin:0; padding:24px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  .sub {{ color:#8b949e; font-size:13px; margin-bottom:16px; }}
  table {{ width:100%; border-collapse:collapse; background:#24292e; border-radius:8px; overflow:hidden; }}
  th, td {{ padding:10px 12px; text-align:left; font-size:13px; border-bottom:1px solid #30363d; }}
  th {{ background:#2d333b; color:#adbac7; text-transform:uppercase; font-size:11px; letter-spacing:.5px; }}
  tr:hover {{ background:#2d333b; }}
  .badge {{ color:#111; font-weight:700; padding:2px 8px; border-radius:10px; font-size:11px; }}
  .details {{ color:#adbac7; max-width:380px; }}
</style></head>
<body>
  <h1>🛡️ SENTINEL-X — Dashboard des alertes</h1>
  <div class="sub">{len(alertes)} dernière(s) alerte(s) · rafraîchi toutes les 5 s · {maj}</div>
  <table>
    <thead><tr><th>Timestamp</th><th>Source</th><th>Type</th><th>Confiance</th><th>Sévérité</th><th>Détails</th></tr></thead>
    <tbody>{lignes}</tbody>
  </table>
</body></html>"""


def main() -> int:
    """Lance le serveur (bloquant)."""
    app = create_app()
    logger.info("API SENTINEL-X démarrée sur http://%s:%s (dashboard /dashboard)",
                API_HOST, API_PORT)
    app.run(host=API_HOST, port=API_PORT, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
