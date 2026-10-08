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

import html
import logging
import os
import socket
import sqlite3
import threading
import time
from datetime import timezone as _tz

import requests
from collections import defaultdict, deque
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import (Flask, jsonify, redirect, request, send_file, session,
                   url_for)

from api.alert_store import AlertStore
from api import auth

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
    app.secret_key = _secret_key()  # nécessaire aux sessions (login)
    magasin = store or AlertStore()

    # Préchauffe Mistral en arrière-plan : charge le modèle en RAM dès le
    # démarrage pour que le 1er « Tester l'IA » réponde vite (sinon ~30-60 s).
    _demarrer_prechauffe_ollama()

    @app.get("/login")
    def login():
        return _page_login()

    @app.post("/login")
    def login_post():
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        code = request.form.get("code", "")
        if auth.verifier(u, p, code):
            session["user"] = u
            logger.info("Connexion dashboard réussie : %s", u)
            return redirect(url_for("dashboard"))
        logger.warning("Connexion dashboard refusée : %s", u)
        return _page_login(erreur="Identifiant, mot de passe ou code 2FA invalide."), 401

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

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

    @app.get("/api/v1/status")
    def statut_systeme():
        return jsonify(_statut_systeme(magasin.db_path))

    @app.get("/api/v1/context")
    @auth.login_required
    def contexte():
        return jsonify(_contexte_ia(magasin))

    @app.get("/app")
    @auth.login_required
    def cockpit():
        return _page_cockpit()

    @app.get("/dashboard")
    @auth.login_required
    def dashboard():
        return _page_dashboard(magasin.recent(50))

    @app.get("/api/v1/alerts-rows")
    @auth.login_required
    def alerts_rows():
        return _lignes_alertes(magasin.recent(50))

    @app.get("/live")
    @auth.login_required
    def live():
        return _page_live(_lire_capteurs(magasin.db_path, 20))

    @app.get("/api/v1/live-body")
    @auth.login_required
    def live_body():
        return _corps_live(_lire_capteurs(magasin.db_path, 20))

    @app.get("/camera")
    @auth.login_required
    def camera():
        return _page_camera()

    @app.get("/security")
    @auth.login_required
    def security():
        return _page_security()

    @app.post("/api/v1/security-fix")
    @auth.login_required
    def security_fix():
        return jsonify(_appliquer_correctifs_securite())

    @app.get("/camera/frame")
    @auth.login_required
    def camera_frame():
        if LATEST_FRAME.exists():
            return send_file(LATEST_FRAME, mimetype="image/jpeg")
        return ("", 204)  # pas encore d'image (vision pas lancée)

    # --- Ollama (optionnel : diagnostic en langage naturel, dégradé si absent) ---
    @app.get("/api/v1/ollama-status")
    def ollama_status():
        return jsonify(_ollama_status())

    @app.post("/api/v1/ollama")
    def ollama_chat():
        data = request.get_json(silent=True) or {}
        reponse = _ollama_ask(data.get("question", ""), data.get("context"))
        code = 200 if reponse.get("answer") else 503
        return jsonify(reponse), code

    # --- Simulateur d'anomalie (démo) : injecte une alerte de test ---
    @app.post("/api/v1/simulate")
    @auth.login_required
    def simulate():
        type_anom = (request.get_json(silent=True) or {}).get("type", "gas_spike")
        alerte = _alerte_simulee(type_anom)
        magasin.insert_alert(alerte)
        logger.info("Alerte SIMULÉE injectée : %s", type_anom)
        return jsonify({"status": "injected", "type": type_anom}), 201

    @app.after_request
    def _pas_de_cache(resp):
        """Empêche le cache des pages HTML : on voit toujours la dernière interface."""
        if resp.mimetype == "text/html":
            resp.headers["Cache-Control"] = "no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
        return resp

    return app


LATEST_FRAME = PROJECT_ROOT / "data" / "captures" / "latest.jpg"


def _secret_key() -> str:
    """Clé secrète des sessions : via .env, sinon générée et persistée localement."""
    import secrets as _secrets
    key = os.getenv("FLASK_SECRET_KEY")
    if key:
        return key
    f = PROJECT_ROOT / "data" / ".flask_secret"
    try:
        if f.exists():
            return f.read_text(encoding="utf-8").strip()
        key = _secrets.token_hex(32)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(key, encoding="utf-8")
        return key
    except OSError:
        return _secrets.token_hex(32)


def _page_login(erreur: str = "") -> str:
    """Page de connexion : identifiant + mot de passe + code 2FA (TOTP)."""
    msg = f'<div class="err">{erreur}</div>' if erreur else ""
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SENTINEL-X — Connexion</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#1b1f23; color:#e6e6e6; margin:0;
         display:flex; min-height:100vh; align-items:center; justify-content:center; }}
  form {{ background:#24292e; border:1px solid #30363d; border-radius:12px; padding:28px; width:300px; }}
  h1 {{ font-size:18px; margin:0 0 4px; }} .s {{ color:#8b949e; font-size:12px; margin-bottom:18px; }}
  label {{ display:block; font-size:12px; color:#adbac7; margin:12px 0 4px; }}
  input {{ width:100%; box-sizing:border-box; padding:9px; border-radius:6px; border:1px solid #30363d;
          background:#1b1f23; color:#e6e6e6; font-size:14px; }}
  button {{ width:100%; margin-top:18px; padding:10px; border:0; border-radius:6px; background:#238636;
           color:#fff; font-weight:700; font-size:14px; cursor:pointer; }}
  .err {{ background:#c0392b; color:#fff; padding:8px; border-radius:6px; font-size:13px; margin-bottom:12px; }}
</style></head>
<body>
  <form method="post" action="/login">
    <h1>🛡️ SENTINEL-X</h1>
    <div class="s">Connexion sécurisée (mot de passe + code Authenticator)</div>
    {msg}
    <label>Identifiant</label><input name="username" autofocus required>
    <label>Mot de passe</label><input name="password" type="password" required>
    <label>Code 2FA (6 chiffres)</label><input name="code" inputmode="numeric" pattern="[0-9]*" required>
    <button type="submit">Se connecter</button>
  </form>
</body></html>"""


def _lire_capteurs(db_path, limit: int = 20) -> list[dict]:
    """Lit les dernières mesures capteurs (table sensor_data, même base que Brique 3/6)."""
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT timestamp, temp, humidity, gas, presence "
                "FROM sensor_data ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error:
        return []  # table pas encore créée (aucune donnée capteur)


MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
ESP32_FRAIS_S = 15          # une mesure plus récente = ESP32/capteurs « connectés »
OLLAMA_MODELE = os.getenv("OLLAMA_MODEL", "mistral")


def _tcp_ouvert(host: str, port: int, timeout: float = 1.5) -> bool:
    """Teste si un port TCP accepte une connexion (broker MQTT joignable ?)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _age_derniere_mesure(db_path) -> float | None:
    """Âge (secondes) de la dernière mesure capteur, ou None si aucune."""
    lignes = _lire_capteurs(db_path, 1)
    if not lignes:
        return None
    ts = str(lignes[0].get("timestamp", ""))
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except (ValueError, AttributeError):
        return None


def _statut_systeme(db_path) -> dict:
    """Analyse complète : chaque brique est-elle connectée et fonctionnelle ?"""
    ollama = _ollama_status()
    mistral_ok = ollama.get("online") and any(
        OLLAMA_MODELE in (m or "") for m in ollama.get("models", []))
    age = _age_derniere_mesure(db_path)
    esp32_ok = age is not None and age <= ESP32_FRAIS_S
    ensemble_ok = (PROJECT_ROOT / "models" / "ensemble" / "ensemble_metadata.json").exists()
    # Webcam « live » : l'image annotée est rafraîchie récemment par la vision.
    cam_age = (time.time() - LATEST_FRAME.stat().st_mtime) if LATEST_FRAME.exists() else None
    cam_ok = cam_age is not None and cam_age <= ESP32_FRAIS_S

    composants = {
        "api": {"ok": True, "label": "API serveur"},
        "broker": {"ok": _tcp_ouvert(MQTT_HOST, MQTT_PORT), "label": f"Broker MQTT ({MQTT_PORT})"},
        "esp32": {"ok": esp32_ok, "label": "ESP32 / capteurs",
                  "detail": "aucune mesure" if age is None else f"dernière mesure il y a {int(age)} s"},
        "webcam": {"ok": cam_ok, "label": "Webcam (vision YOLO)",
                   "detail": "flux actif" if cam_ok else "pas de flux (webcam branchée ?)"},
        "detection": {"ok": ensemble_ok, "label": "Détection IA (ensemble 6.3)",
                      "detail": "modèle chargé" if ensemble_ok else "non entraîné (make train-ensemble)"},
        "ollama": {"ok": bool(ollama.get("online")), "label": "Ollama (serveur local)"},
        "ia": {"ok": bool(mistral_ok), "label": "IA Mistral fonctionnelle",
               "detail": "mistral prêt" if mistral_ok else "modèle mistral absent (ollama pull mistral)"},
    }
    tout_ok = all(c["ok"] for c in composants.values())
    return {"tout_ok": tout_ok, "composants": composants,
            "maj": datetime.now(timezone.utc).strftime("%H:%M:%S UTC")}


NIVEAU_FENETRE_S = 30          # une alerte "colore" l'état pendant 30 s


def _niveau_alerte(latest: dict | None) -> tuple[str, str]:
    """État global (vert/orange/rouge) selon la dernière alerte récente.

    vert = normal · orange = avertissement récent · rouge = alerte critique récente.
    Retourne (niveau, label).
    """
    if not latest:
        return "vert", "Normal"
    age = _age_depuis(latest.get("timestamp"))
    if age is None or age > NIVEAU_FENETRE_S:
        return "vert", "Normal"
    sev = (latest.get("details") or {}).get("severity", "INFO")
    if sev in ("CRITICAL", "HIGH"):
        return "rouge", "Alerte critique"
    if sev == "WARNING":
        return "orange", "Avertissement"
    return "vert", "Normal"      # INFO = pas d'alarme -> reste vert


def _age_depuis(ts) -> float | None:
    """Âge en secondes d'un timestamp ISO, ou None si illisible."""
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except (ValueError, AttributeError, TypeError):
        return None


def _contexte_ia(magasin) -> dict:
    """Résumé de l'état réel (capteurs + alertes) donné à l'IA et au temps réel."""
    mesures = _lire_capteurs(magasin.db_path, 1)
    d = mesures[0] if mesures else {}
    alertes = magasin.recent(5)
    latest = alertes[0] if alertes else None
    niveau, niveau_label = _niveau_alerte(latest)
    presence = "oui" if d.get("presence") else "non"
    resume = (
        f"Mesures actuelles : température {d.get('temp', '?')} °C, "
        f"humidité {d.get('humidity', '?')} %, gaz {d.get('gas', '?')} (0=air propre), "
        f"présence {presence}. "
        f"{magasin.count()} alerte(s) au total."
    )
    if latest:
        details = latest.get("details") or {}
        resume += (f" Dernière alerte : {latest.get('type', '?')} "
                   f"[{details.get('severity', '?')}] — {details.get('context', '')}.")
    return {"resume": resume, "sensors": d, "alerts_count": magasin.count(),
            "latest_alert": latest, "niveau": niveau, "niveau_label": niveau_label,
            "maj": datetime.now(timezone.utc).strftime("%H:%M:%S")}


_SECU_COULEURS = {"CRITICAL": "#e74c3c", "HIGH": "#e74c3c", "MEDIUM": "#f39c12",
                  "LOW": "#3498db", "OK": "#2ecc71"}


def _page_cockpit() -> str:
    """Cockpit pro : analyse temps réel + caméra live + chat IA (données) + alertes."""
    return """<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SENTINEL-X</title>
<style>
  *{box-sizing:border-box} html,body{height:100%}
  body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#0d1117;color:#e6edf3;margin:0;
       display:grid;grid-template-rows:auto 1fr;height:100vh;overflow:hidden}
  /* En-tête */
  header{padding:12px 18px;background:#161b22;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:14px}
  header h1{font-size:17px;margin:0;font-weight:700;letter-spacing:.3px}
  #verdict{font-size:13px;font-weight:600;padding:4px 10px;border-radius:20px;background:#21262d}
  .etat{font-size:14px;font-weight:800;padding:5px 14px;border-radius:20px;background:#0d1117;border:1px solid #30363d;letter-spacing:.3px}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.45}}
  .etat.pulse{animation:pulse 1s infinite}
  .clock{margin-left:auto;color:#8b949e;font-size:12px;font-variant-numeric:tabular-nums}
  /* Corps : contenu + chat */
  main{display:grid;grid-template-columns:1fr 360px;min-height:0}
  .content{min-height:0;overflow-y:auto;padding:14px 18px;display:flex;flex-direction:column;gap:14px}
  /* Cartes de statut */
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:12px 14px}
  .card .k{font-weight:600;font-size:13px;display:flex;align-items:center}
  .card .d{color:#8b949e;font-size:11px;margin-top:5px}
  .dot{width:9px;height:9px;border-radius:50%;margin-right:8px;display:inline-block;box-shadow:0 0 6px currentColor}
  /* Onglets + vue */
  .panel{background:#161b22;border:1px solid #30363d;border-radius:12px;overflow:hidden;display:flex;flex-direction:column;flex:1;min-height:360px}
  .tabs{display:flex;gap:4px;padding:8px;border-bottom:1px solid #30363d;background:#0f141a}
  .tabs button{flex:0 0 auto;background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:8px;
               padding:7px 14px;font-size:13px;cursor:pointer;transition:.15s}
  .tabs button.on{background:#1f6feb;border-color:#1f6feb}
  .tabs button:hover{border-color:#58a6ff}
  iframe{width:100%;flex:1;border:0;background:#fff}
  /* Chat latéral */
  .chat{background:#0f141a;border-left:1px solid #30363d;display:flex;flex-direction:column;min-height:0}
  .chat .top{padding:12px 14px;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:10px;background:#161b22}
  .chat .top b{font-size:14px} .chat .top .d{color:#8b949e;font-size:11px}
  .camwrap{position:relative;margin:10px 12px 0;border-radius:10px;overflow:hidden;border:1px solid #30363d;background:#000}
  .camwrap img{width:100%;height:150px;object-fit:cover;display:block}
  .camwrap .lbl{position:absolute;top:6px;left:8px;background:rgba(0,0,0,.55);font-size:10px;padding:2px 7px;border-radius:10px;color:#7ee787}
  .msgs{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px}
  .msg{max-width:88%;padding:9px 12px;border-radius:12px;font-size:13px;line-height:1.45;white-space:pre-wrap;word-wrap:break-word}
  .msg.ia{background:#161b22;border:1px solid #30363d;align-self:flex-start;border-bottom-left-radius:3px}
  .msg.me{background:#1f6feb;align-self:flex-end;border-bottom-right-radius:3px}
  .msg.sys{background:transparent;color:#8b949e;font-size:11px;align-self:center;text-align:center;padding:2px}
  .chips{display:flex;flex-wrap:wrap;gap:6px;padding:0 12px 8px}
  .chips button{background:#21262d;border:1px solid #30363d;color:#adbac7;border-radius:14px;padding:4px 10px;font-size:11px;cursor:pointer}
  .chips button:hover{border-color:#58a6ff;color:#fff}
  .composer{display:flex;gap:8px;padding:10px 12px;border-top:1px solid #30363d;background:#161b22}
  .composer input{flex:1;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:10px;padding:9px 12px;font-size:13px}
  .composer input:focus{outline:none;border-color:#1f6feb}
  .composer button{background:#1f6feb;border:0;color:#fff;border-radius:10px;padding:0 14px;cursor:pointer;font-size:15px}
  .composer button:disabled{opacity:.5;cursor:default}
  /* Toast d'alerte */
  #toast{position:fixed;top:16px;left:50%;transform:translateX(-50%) translateY(-120%);transition:.35s;
         z-index:50;min-width:320px;max-width:560px;padding:12px 16px;border-radius:12px;
         box-shadow:0 10px 30px rgba(0,0,0,.5);font-size:14px;font-weight:600;display:flex;align-items:center;gap:10px}
  #toast.show{transform:translateX(-50%) translateY(0)}
  @media(max-width:860px){main{grid-template-columns:1fr} .chat{display:none}}
</style></head>
<body>
  <header>
    <h1>🛡️ SENTINEL-X</h1>
    <span id="etat" class="etat">● —</span>
    <span id="verdict">Analyse…</span>
    <span class="clock" id="clock">—</span>
  </header>
  <main>
    <section class="content">
      <div class="cards" id="cards"></div>
      <div class="panel">
        <div class="tabs">
          <button class="on" data-url="/dashboard">🚨 Alertes</button>
          <button data-url="/live">📊 Capteurs</button>
          <button data-url="/camera">🎥 Caméra</button>
          <button data-url="/security">🛡️ Sécurité</button>
        </div>
        <iframe id="vue" src="/dashboard"></iframe>
      </div>
    </section>
    <aside class="chat">
      <div class="top"><span style="font-size:18px">🤖</span><div><b>Assistant Mistral</b><div class="d">connecté à tes données</div></div></div>
      <div class="camwrap"><img id="cam" alt="webcam"><span class="lbl">● WEBCAM LIVE</span></div>
      <div class="msgs" id="msgs"></div>
      <div class="chips">
        <button onclick="ask('Quel est l\\'état des capteurs ?')">État capteurs</button>
        <button onclick="ask('Y a-t-il une alerte à surveiller ?')">Alertes ?</button>
        <button onclick="ask('Le niveau de gaz est-il normal ?')">Gaz normal ?</button>
      </div>
      <div class="composer">
        <input id="q" placeholder="Pose une question sur le système…" onkeydown="if(event.key==='Enter')send()">
        <button id="sendbtn" onclick="send()">➤</button>
      </div>
    </aside>
  </main>
  <div id="toast"></div>
<script>
  // --- onglets ---
  document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{
    document.getElementById('vue').src=b.dataset.url;
    document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('on')); b.classList.add('on');
  });
  // --- statut (cartes + verdict) ---
  async function refreshStatus(){
    try{
      const s=await (await fetch('/api/v1/status')).json();
      const v=document.getElementById('verdict');
      v.textContent=s.tout_ok?'✅ Tout opérationnel':'⚠️ À vérifier';
      v.style.background=s.tout_ok?'#132d1e':'#3a2d12'; v.style.color=s.tout_ok?'#3fb950':'#d29922';
      const g=document.getElementById('cards'); g.innerHTML='';
      for(const k in s.composants){const c=s.composants[k];const col=c.ok?'#3fb950':'#f85149';
        g.innerHTML+=`<div class="card"><div class="k"><span class="dot" style="color:${col};background:${col}"></span>${c.label}</div>`
          +`<div class="d">${c.ok?'connecté':'non connecté'}${c.detail?(' · '+c.detail):''}</div></div>`;}
    }catch(e){document.getElementById('verdict').textContent='API injoignable';}
  }
  // --- caméra live (rapide) ---
  function majCam(){document.getElementById('cam').src='/camera/frame?t='+Date.now();}
  // --- contexte + alertes temps réel ---
  let ctxResume=''; let lastAlertTs;
  const SEV={CRITICAL:'#f85149',HIGH:'#f85149',WARNING:'#d29922',INFO:'#58a6ff'};
  async function pollContext(){
    try{
      const c=await (await fetch('/api/v1/context')).json();
      ctxResume=c.resume||'';
      document.getElementById('clock').textContent=c.maj||'';
      // Indicateur d'état coloré (reflète les LEDs de l'ESP32)
      const NIV={vert:'#3fb950',orange:'#d29922',rouge:'#f85149'};
      const e=document.getElementById('etat'), col=NIV[c.niveau]||'#3fb950';
      e.textContent='● '+(c.niveau_label||'Normal');
      e.style.color=col; e.style.borderColor=col; e.style.boxShadow='0 0 10px '+col+'55';
      e.classList.toggle('pulse', c.niveau==='rouge');
      const la=c.latest_alert, ts=la?la.timestamp:null;
      if(lastAlertTs===undefined){lastAlertTs=ts;}       // init sans toast
      else if(ts && ts!==lastAlertTs){toast(la);lastAlertTs=ts;}
    }catch(e){}
  }
  function toast(a){
    const d=a.details||{}, sev=d.severity||'WARNING', col=SEV[sev]||'#d29922';
    const t=document.getElementById('toast');
    t.style.background=col; t.style.color='#0d1117';
    t.innerHTML='🚨 <b>ALERTE '+sev+'</b> — '+(a.type||'')+' : '+(d.context||'');
    t.classList.add('show'); clearTimeout(window._tt);
    window._tt=setTimeout(()=>t.classList.remove('show'),8000);
  }
  // --- chat IA (avec données réelles en contexte) ---
  const msgs=document.getElementById('msgs');
  function bubble(txt,cls){const m=document.createElement('div');m.className='msg '+cls;m.textContent=txt;msgs.appendChild(m);msgs.scrollTop=msgs.scrollHeight;return m;}
  bubble('Bonjour 👋 Je suis Mistral, connecté à tes capteurs. Pose-moi une question sur l\\'état du système.','ia');
  function ask(q){document.getElementById('q').value=q;send();}
  async function send(){
    const inp=document.getElementById('q'), btn=document.getElementById('sendbtn');
    const q=inp.value.trim(); if(!q) return;
    bubble(q,'me'); inp.value=''; btn.disabled=true;
    const wait=bubble('… Mistral réfléchit (données en cours)','ia');
    try{
      const r=await fetch('/api/v1/ollama',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({question:q, context:ctxResume})});
      const d=await r.json();
      wait.textContent=d.answer || ('⚠️ '+(d.error||'IA indisponible')+' '+(d.suggestion||''));
    }catch(e){wait.textContent='❌ IA injoignable';}
    btn.disabled=false; inp.focus();
  }
  // --- boucles (réactives) ---
  refreshStatus(); setInterval(refreshStatus,2500);
  pollContext();   setInterval(pollContext,900);     // alertes/état quasi temps réel
  majCam();        setInterval(majCam,350);           // caméra fluide
</script>
</body></html>"""


def _appliquer_correctifs_securite() -> dict:
    """Applique les correctifs SÛRS automatiquement, liste ce qui reste manuel."""
    try:
        from scripts.security_audit import appliquer_correctifs, lancer_controles
        constats = lancer_controles()
        actions = appliquer_correctifs(constats)
        constats = lancer_controles()   # ré-audit après correction
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erreur": str(exc), "actions": [], "manuel": []}

    manuel = [{"controle": c.controle, "correctif": c.correctif}
              for c in constats if not c.ok]
    return {"ok": True, "actions": actions, "manuel": manuel,
            "message": (f"{len(actions)} correctif(s) appliqué(s) automatiquement."
                        if actions else "Rien à corriger automatiquement.")}


def _page_security() -> str:
    """Page web « Suis-je sécurisé ? » : lance l'audit et affiche le rapport."""
    try:
        from scripts.security_audit import lancer_controles
        constats = lancer_controles()
    except Exception as exc:  # noqa: BLE001 — l'audit ne doit jamais casser l'UI
        return f"<p style='color:#e74c3c'>Audit indisponible : {html.escape(str(exc))}</p>"

    echecs = [c for c in constats if not c.ok]
    critiques = [c for c in echecs if c.gravite in ("CRITICAL", "HIGH")]
    if not echecs:
        verdict, vcoul = "✅ Système sain", "#2ecc71"
    elif critiques:
        verdict, vcoul = "⚠️ NON SÉCURISÉ", "#e74c3c"
    else:
        verdict, vcoul = "🟡 À renforcer", "#f39c12"

    lignes = ""
    for c in constats:
        coul = _SECU_COULEURS.get(c.gravite, "#7f8c8d")
        icone = "✓" if c.ok else "✗"
        correctif = (f"<div class='fix'>→ {html.escape(c.correctif)}</div>"
                     if not c.ok and c.correctif else "")
        lignes += (
            f"<tr>"
            f"<td style='text-align:center;color:{coul};font-weight:700'>{icone}</td>"
            f"<td>{html.escape(c.controle)}</td>"
            f"<td><span class='badge' style='background:{coul}'>{c.gravite}</span></td>"
            f"<td class='details'>{html.escape(c.message)}{correctif}</td>"
            f"</tr>")

    maj = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8">
<title>SENTINEL-X — Sécurité</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#1b1f23; color:#e6e6e6; margin:0; padding:24px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  .sub {{ color:#8b949e; font-size:13px; margin-bottom:16px; }}
  .verdict {{ font-size:18px; font-weight:700; color:{vcoul}; margin:12px 0; }}
  table {{ width:100%; border-collapse:collapse; background:#24292e; border-radius:8px; overflow:hidden; }}
  th, td {{ padding:10px 12px; text-align:left; font-size:13px; border-bottom:1px solid #30363d; vertical-align:top; }}
  th {{ background:#2d333b; color:#adbac7; text-transform:uppercase; font-size:11px; letter-spacing:.5px; }}
  .badge {{ color:#111; font-weight:700; padding:2px 8px; border-radius:10px; font-size:11px; }}
  .details {{ color:#adbac7; max-width:520px; }}
  .fix {{ color:#8b949e; font-size:12px; margin-top:4px; font-style:italic; }}
  button {{ background:#2d333b; color:#e6e6e6; border:1px solid #30363d; border-radius:6px; padding:6px 10px; cursor:pointer; }}
</style></head>
<body>
  <h1>🛡️ SENTINEL-X — Suis-je sécurisé ?</h1>
  <div class="sub">Audit {maj} · <a href="/dashboard" style="color:#58a6ff;text-decoration:none">→ alertes</a> · <a href="/live" style="color:#58a6ff;text-decoration:none">→ capteurs</a> · <a href="/logout" style="color:#8b949e;text-decoration:none">déconnexion</a></div>
  <div class="verdict">{verdict} — {len(echecs)} point(s), dont {len(critiques)} critique(s)/élevé(s)</div>
  <table>
    <tr><th></th><th>Contrôle</th><th>Gravité</th><th>Détail & correctif</th></tr>
    {lignes}
  </table>
  <p style="margin-top:14px">
    <button onclick="location.reload()">↻ Relancer l'audit</button>
    <button onclick="corriger()" style="background:#2ea043;color:#fff;font-weight:700">🔧 Corriger automatiquement</button>
    <span id="fixout" style="margin-left:10px;color:#adbac7;font-size:13px"></span>
  </p>
<script>
  async function corriger(){{
    const out = document.getElementById('fixout');
    out.textContent = 'Correction en cours…';
    try {{
      const r = await fetch('/api/v1/security-fix', {{method:'POST'}});
      const d = await r.json();
      if (!d.ok) {{ out.textContent = '❌ ' + (d.erreur || 'échec'); return; }}
      let msg = '✅ ' + d.message;
      if (d.manuel && d.manuel.length) msg += ' · ' + d.manuel.length + ' point(s) à faire à la main';
      out.textContent = msg;
      setTimeout(function(){{ location.reload(); }}, 1500);
    }} catch(e) {{ out.textContent = '❌ serveur injoignable'; }}
  }}
</script>
</body></html>"""


def _lignes_alertes(alertes: list[dict]) -> str:
    """Construit les lignes <tr> du tableau d'alertes (échappées anti-XSS)."""
    lignes = ""
    for a in alertes:
        sev = _severite(a)
        couleur = _COULEURS.get(sev, "#7f8c8d")
        details = a.get("details") or {}
        ctx = details.get("context")
        if not ctx and details.get("persons_detected") is not None:
            ctx = f"{details['persons_detected']} personne(s) détectée(s)"
        # Anti-XSS : on ÉCHAPPE toute donnée (une mesure MQTT injectée pourrait
        # contenir du <script>). Le <span> des votes, lui, est construit par nous.
        contexte = html.escape(str(ctx or ""))
        votes = details.get("model_votes")
        if votes:
            contexte += " · <span style='color:#8b949e'>" + html.escape(
                " ".join(f"{k[:3]}:{v}" for k, v in votes.items())) + "</span>"
        lignes += (
            f"<tr>"
            f"<td>{html.escape(str(a.get('timestamp', '')))}</td>"
            f"<td>{html.escape(str(a.get('source', '')))}</td>"
            f"<td>{html.escape(str(a.get('type', '')))}</td>"
            f"<td style='text-align:center'>{html.escape(str(a.get('confidence', '')))}</td>"
            f"<td><span class='badge' style='background:{couleur}'>{sev}</span></td>"
            f"<td class='details'>{contexte}</td>"
            f"</tr>"
        )
    if not lignes:
        lignes = "<tr><td colspan='6' style='text-align:center;color:#888'>Aucune alerte pour l'instant</td></tr>"
    return lignes


def _page_dashboard(alertes: list[dict]) -> str:
    """Construit la page HTML du dashboard (mise à jour fluide en AJAX, sans reload)."""
    lignes = _lignes_alertes(alertes)
    maj = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8">
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
  <div class="sub"><span id="maj">{maj}</span> · rafraîchi en continu · <a href="/live" style="color:#58a6ff;text-decoration:none">→ capteurs</a> · <a href="/camera" style="color:#58a6ff;text-decoration:none">→ caméra</a> · <a href="/security" style="color:#58a6ff;text-decoration:none">→ sécurité</a> · <a href="/logout" style="color:#8b949e;text-decoration:none">déconnexion</a></div>
  <div style="margin:10px 0;font-size:13px">🧪 <b>Simulateur</b> :
    <button onclick="inj('gas_spike')">Fuite gaz</button>
    <button onclick="inj('temp_jump')">Surchauffe</button>
    <button onclick="inj('intrusion')">Intrusion</button>
    &nbsp;·&nbsp;<span id="ostat">Ollama…</span>
  </div>
  <div style="margin:10px 0;font-size:13px">🤖
    <input id="q" placeholder="Demander à Ollama (ex: pourquoi le gaz est haut ?)" style="width:55%;padding:6px;background:#1b1f23;color:#e6e6e6;border:1px solid #30363d;border-radius:6px">
    <button onclick="ask()">Demander</button>
    <div id="rep" style="margin-top:8px;color:#adbac7"></div>
  </div>
<script>
// Mise à jour FLUIDE du tableau (sans recharger la page -> ne vide plus les champs).
function majAlertes(){{
  fetch('/api/v1/alerts-rows').then(function(r){{return r.text();}}).then(function(h){{
    document.getElementById('corps').innerHTML = h;
    document.getElementById('maj').textContent = new Date().toLocaleTimeString();
  }}).catch(function(){{}});
}}
function inj(t){{fetch('/api/v1/simulate',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{type:t}})}}).then(majAlertes);}}
fetch('/api/v1/ollama-status').then(function(r){{return r.json();}}).then(function(d){{document.getElementById('ostat').textContent=d.online?'🟢 Ollama en ligne':'🔴 Ollama hors ligne';}});
function ask(){{var q=document.getElementById('q').value;document.getElementById('rep').textContent='…';fetch('/api/v1/ollama',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{question:q}})}}).then(function(r){{return r.json();}}).then(function(d){{document.getElementById('rep').textContent=d.answer||('⚠️ '+(d.error||'')+' '+(d.suggestion||''));}});}}
setInterval(majAlertes, 2000);   // rafraîchit juste les données, pas la page
</script>
  <table>
    <thead><tr><th>Timestamp</th><th>Source</th><th>Type</th><th>Confiance</th><th>Sévérité</th><th>Détails</th></tr></thead>
    <tbody id="corps">{lignes}</tbody>
  </table>
</body></html>"""


def _corps_live(mesures: list[dict]) -> str:
    """Construit le corps (cartes + tableau) de la page capteurs en direct."""
    if not mesures:
        return ("<p style='color:#8b949e'>Aucune mesure pour l'instant. "
                "Lance la Brique 3 (ESP32 ou simulateur) → les valeurs s'afficheront ici.</p>")
    d = mesures[0]  # mesure la plus récente
    presence = int(d.get("presence") or 0)
    gaz = float(d.get("gas") or 0)
    # code couleur (comme l'OLED) : présence rouge, gaz élevé orange
    c_pres = "#c0392b" if presence else "#27ae60"
    c_gaz = "#e67e22" if gaz >= 200 else "#58a6ff"   # gaz normalisé : >200 = gaz présent
    cartes = (
        f"<div class='grid'>"
        f"<div class='card'><div class='k'>Température</div><div class='v'>{html.escape(str(d.get('temp','--')))} °C</div></div>"
        f"<div class='card'><div class='k'>Humidité</div><div class='v'>{html.escape(str(d.get('humidity','--')))} %</div></div>"
        f"<div class='card'><div class='k'>Gaz (MQ-2)</div><div class='v' style='color:{c_gaz}'>{int(gaz)}</div></div>"
        f"<div class='card'><div class='k'>Présence (PIR)</div><div class='v' style='color:{c_pres}'>"
        f"{'🚶 OUI' if presence else '— non'}</div></div>"
        f"</div>"
    )
    rangs = ""
    for m in mesures:
        pres = "🚶" if int(m.get("presence") or 0) else "—"
        rangs += (f"<tr><td>{html.escape(str(m.get('timestamp','')))}</td>"
                  f"<td>{html.escape(str(m.get('temp','')))}</td>"
                  f"<td>{html.escape(str(m.get('humidity','')))}</td>"
                  f"<td>{int(float(m.get('gas') or 0))}</td>"
                  f"<td style='text-align:center'>{pres}</td></tr>")
    return cartes + (
        "<table><thead><tr><th>Timestamp</th><th>Temp °C</th><th>Humi %</th>"
        "<th>Gaz</th><th>Présence</th></tr></thead><tbody>" + rangs + "</tbody></table>")


def _page_live(mesures: list[dict]) -> str:
    """Page capteurs en direct — mise à jour fluide en AJAX (sans reload)."""
    maj = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8">
<title>SENTINEL-X — Capteurs en direct</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#1b1f23; color:#e6e6e6; margin:0; padding:24px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  .sub {{ color:#8b949e; font-size:13px; margin-bottom:16px; }}
  a {{ color:#58a6ff; text-decoration:none; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin-bottom:20px; }}
  .card {{ background:#24292e; border:1px solid #30363d; border-radius:10px; padding:16px; }}
  .k {{ color:#8b949e; font-size:12px; text-transform:uppercase; letter-spacing:.5px; }}
  .v {{ font-size:30px; font-weight:700; margin-top:6px; }}
  table {{ width:100%; border-collapse:collapse; background:#24292e; border-radius:8px; overflow:hidden; }}
  th, td {{ padding:8px 12px; text-align:left; font-size:13px; border-bottom:1px solid #30363d; }}
  th {{ background:#2d333b; color:#adbac7; font-size:11px; text-transform:uppercase; }}
</style></head>
<body>
  <h1>🛡️ SENTINEL-X — Capteurs en direct</h1>
  <div class="sub"><span id="maj">{maj}</span> · rafraîchi en continu · <a href="/dashboard">→ alertes</a> · <a href="/camera">→ caméra</a></div>
  <div id="corps">{_corps_live(mesures)}</div>
<script>
  function majLive(){{
    fetch('/api/v1/live-body').then(function(r){{return r.text();}}).then(function(h){{
      document.getElementById('corps').innerHTML = h;
      document.getElementById('maj').textContent = new Date().toLocaleTimeString();
    }}).catch(function(){{}});
  }}
  setInterval(majLive, 1500);
</script>
</body></html>"""


def _page_camera() -> str:
    """Page caméra : affiche la dernière image annotée (YOLO), rafraîchie ~1 s."""
    return """<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8">
<title>SENTINEL-X — Caméra</title>
<style>
  body { font-family: system-ui, sans-serif; background:#1b1f23; color:#e6e6e6; margin:0; padding:24px; text-align:center; }
  h1 { font-size:20px; }
  a { color:#58a6ff; text-decoration:none; }
  img { max-width:min(640px,95vw); border:2px solid #30363d; border-radius:10px; margin-top:12px; background:#000; }
  .sub { color:#8b949e; font-size:13px; }
</style></head>
<body>
  <h1>🛡️ SENTINEL-X — Caméra (vision IA)</h1>
  <div class="sub">Webcam externe + détection de personnes · <a href="/dashboard">alertes</a> · <a href="/live">capteurs</a></div>
  <div><img id="cam" src="/camera/frame" alt="flux camera"></div>
  <div class="sub" id="etat">Connexion au flux…</div>
<script>
  setInterval(function () {
    document.getElementById('cam').src = '/camera/frame?t=' + Date.now();
  }, 800);
  document.getElementById('cam').onerror = function () {
    document.getElementById('etat').textContent =
      "Aucun flux : lance la vision (make.bat detect-vision --camera 1).";
  };
  document.getElementById('cam').onload = function () {
    document.getElementById('etat').textContent = "Flux en direct";
  };
</script>
</body></html>"""


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))  # 1ʳᵉ réponse = chargement RAM


def _ollama_status() -> dict:
    """Vérifie si Ollama tourne en local (dégradé sinon)."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        if r.status_code == 200:
            return {"online": True, "models": [m.get("name") for m in r.json().get("models", [])]}
    except requests.RequestException:
        pass
    return {"online": False, "hint": "Démarrer Ollama : ollama serve (puis ollama pull mistral)"}


def _prechauffe_ollama() -> None:
    """Charge le modèle Mistral en RAM (1 requête bidon). Silencieux si absent."""
    try:
        requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": OLLAMA_MODEL, "prompt": "ok", "stream": False,
                            "options": {"num_predict": 1}}, timeout=OLLAMA_TIMEOUT)
    except requests.RequestException:
        pass


def _demarrer_prechauffe_ollama() -> None:
    """Lance le préchauffage dans un thread démon (ne bloque pas le démarrage)."""
    threading.Thread(target=_prechauffe_ollama, daemon=True).start()


SYSTEME_SENTINELX = (
    "Tu es l'assistant IA intégré de SENTINEL-X, un système de SURVEILLANCE IoT "
    "intelligent (workshop EPSI, équipe 6). Tu connais tout le projet :\n"
    "- Matériel : un ESP32 lit la température et l'humidité (DHT22), le gaz/fumée "
    "(MQ-2, auto-calibré : 0 au repos), la présence (PIR), affiche sur un écran OLED "
    "et pilote 3 LEDs de statut (vert=normal, orange=avertissement, rouge=critique).\n"
    "- Transmission : l'ESP32 envoie en WiFi via MQTT (broker Mosquitto) au PC.\n"
    "- IA sur le PC : détection d'anomalies par un ENSEMBLE (Isolation Forest + LOF + "
    "ECOD + Gradient Boosting), surveillance de la santé des capteurs, et VISION par "
    "caméra (YOLOv8) qui détecte les personnes.\n"
    "- Dashboard web sécurisé : login + 2FA (TOTP), anti-XSS, audit de sécurité "
    "automatique, signature HMAC anti-injection, secrets protégés.\n"
    "Tu réponds aux questions sur le projet ET sur l'état actuel des capteurs. "
    "Sois clair, concret et bref (1 à 3 phrases)."
)


def _ollama_ask(question: str, context=None) -> dict:
    """Pose une question à Ollama avec le contexte COMPLET du projet + les données live."""
    if not question:
        return {"error": "question vide"}
    prompt = (f"{SYSTEME_SENTINELX}\n\nÉTAT ACTUEL DU SYSTÈME : {context}\n\n"
              f"QUESTION DE L'UTILISATEUR : {question}\n\nTa réponse :")
    try:
        # Timeout large : la 1ʳᵉ requête charge le modèle en RAM (20-60 s sur CPU).
        r = requests.post(f"{OLLAMA_URL}/api/generate",
                          json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                                "options": {"temperature": 0.3}}, timeout=OLLAMA_TIMEOUT)
        if r.status_code == 200:
            return {"answer": r.json().get("response", "").strip(), "source": OLLAMA_MODEL}
        return {"error": f"Ollama a répondu {r.status_code}",
                "suggestion": f"modèle « {OLLAMA_MODEL} » installé ? → ollama pull {OLLAMA_MODEL}"}
    except requests.Timeout:
        return {"error": "Mistral met du temps à charger — réessaie dans 30 s",
                "suggestion": "la 1ʳᵉ réponse charge le modèle en mémoire"}
    except requests.RequestException:
        pass
    return {"error": "Ollama non disponible", "suggestion": "ollama serve puis ollama pull mistral"}


def _alerte_simulee(type_anom: str) -> dict:
    """Construit une alerte de TEST (simulateur de démo)."""
    import random
    presets = {
        "gas_spike": {"gas": 3500, "temp": 24, "humidity": 45, "presence": 0, "ctx": "Pic de gaz (fuite ?)"},
        "temp_jump": {"gas": 150, "temp": 55, "humidity": 30, "presence": 0, "ctx": "Surchauffe (température anormale)"},
        "intrusion": {"gas": 120, "temp": 23, "humidity": 50, "presence": 1, "ctx": "Présence inattendue"},
    }
    p = presets.get(type_anom, presets["gas_spike"])
    return {
        "source": "ia_predictive", "type": "anomaly_detected",
        "confidence": round(random.uniform(0.8, 0.95), 2),
        "timestamp": datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "details": {"severity": "CRITICAL", "context": f"[SIMULÉ] {p['ctx']}",
                    "current_values": {"temp": p["temp"], "humidity": p["humidity"],
                                       "gas": p["gas"], "presence": p["presence"]},
                    "recommendation": "Alerte de test (simulateur)"},
    }


def main() -> int:
    """Lance le serveur (bloquant)."""
    app = create_app()
    logger.info("API SENTINEL-X démarrée sur http://%s:%s (dashboard /dashboard)",
                API_HOST, API_PORT)
    # threaded=True : plusieurs visiteurs du dashboard servis en parallèle
    app.run(host=API_HOST, port=API_PORT, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
