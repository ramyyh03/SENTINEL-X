#!/usr/bin/env python3
"""Génère la documentation technique PDF de SENTINEL-X (reportlab).

Usage :
    ./venv/bin/python scripts/generer_doc_pdf.py
    -> docs/SENTINEL-X-Documentation.pdf

Le contenu est piloté par des données (listes de blocs) : facile à maintenir.
Les emojis sont remplacés par des marqueurs ASCII ([ROUGE], [OK]...) car les
polices de base de reportlab ne les affichent pas.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SORTIE = PROJECT_ROOT / "docs" / "SENTINEL-X-Documentation.pdf"

# --- Palette -------------------------------------------------------------- #
BLEU_FONCE = colors.HexColor("#0b2545")
BLEU = colors.HexColor("#13315c")
ACCENT = colors.HexColor("#1f6feb")
GRIS = colors.HexColor("#5b6773")
GRIS_CLAIR = colors.HexColor("#eef2f7")
VERT = colors.HexColor("#2e7d32")
ORANGE = colors.HexColor("#ed6c02")
ROUGE = colors.HexColor("#c62828")

_EMOJIS = {
    "🔥": "[FEU]", "💨": "[GAZ]", "🌡️": "[TEMP]", "🌡": "[TEMP]", "👥": "[FOULE]",
    "👤": "[PRESENCE]", "💧": "[HUMIDITE]", "🎥": "[CAMERA]", "🟢": "[VERT]",
    "🟡": "[JAUNE]", "🔴": "[ROUGE]", "✅": "[OK]", "→": "->", "≥": ">=",
    "≤": "<=", "–": "-", "—": "-", "«": '"', "»": '"', "’": "'",
}


def clean(txt: str) -> str:
    """Remplace les emojis/caractères hors latin-1 pour un rendu PDF propre."""
    for k, v in _EMOJIS.items():
        txt = txt.replace(k, v)
    # Supprime tout caractère restant non représentable en latin-1 (emojis...).
    txt = txt.encode("latin-1", "ignore").decode("latin-1")
    return re.sub(r"[ \t]+", " ", txt).strip()


# --- Styles --------------------------------------------------------------- #
_base = getSampleStyleSheet()
S = {
    "h1": ParagraphStyle("h1", parent=_base["Heading1"], fontName="Helvetica-Bold",
                         fontSize=18, textColor=BLEU_FONCE, spaceBefore=6, spaceAfter=10,
                         leading=22),
    "h2": ParagraphStyle("h2", parent=_base["Heading2"], fontName="Helvetica-Bold",
                         fontSize=13, textColor=BLEU, spaceBefore=10, spaceAfter=6,
                         leading=16),
    "body": ParagraphStyle("body", parent=_base["BodyText"], fontName="Helvetica",
                           fontSize=10, textColor=colors.HexColor("#1a1a1a"),
                           leading=14.5, alignment=TA_JUSTIFY, spaceAfter=6),
    "bullet": ParagraphStyle("bullet", parent=_base["BodyText"], fontName="Helvetica",
                             fontSize=10, leading=14, leftIndent=14, bulletIndent=4,
                             alignment=TA_LEFT, spaceAfter=3),
    "mono": ParagraphStyle("mono", parent=_base["BodyText"], fontName="Courier",
                           fontSize=8.5, textColor=colors.HexColor("#0b2545"),
                           backColor=GRIS_CLAIR, leading=12, leftIndent=6, rightIndent=6,
                           spaceBefore=4, spaceAfter=8, borderPadding=6),
    "cellh": ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=9,
                            textColor=colors.white, leading=11),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.8,
                           textColor=colors.HexColor("#1a1a1a"), leading=11),
    "faqq": ParagraphStyle("faqq", fontName="Helvetica-Bold", fontSize=10,
                           textColor=BLEU, leading=13, spaceBefore=8, spaceAfter=2),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=30,
                            textColor=BLEU_FONCE, alignment=TA_CENTER, leading=36),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=14,
                               textColor=GRIS, alignment=TA_CENTER, leading=20),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=11,
                           textColor=colors.HexColor("#1a1a1a"), alignment=TA_CENTER,
                           leading=18),
}


def P(txt, style="body"):
    return Paragraph(clean(txt), S[style])


def bullets(items):
    return [Paragraph(clean(f"&bull;&nbsp;&nbsp;{i}"), S["bullet"]) for i in items]


def mono(lines):
    return Paragraph("<br/>".join(clean(l).replace(" ", "&nbsp;") for l in lines), S["mono"])


def table(data, col_widths, header=True):
    rows = []
    for r, row in enumerate(data):
        cells = []
        for c in row:
            st = "cellh" if (header and r == 0) else "cell"
            cells.append(Paragraph(clean(str(c)), S[st]))
        rows.append(cells)
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c9d4e0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), BLEU),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_CLAIR])]
    else:
        style += [("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, GRIS_CLAIR])]
    t.setStyle(TableStyle(style))
    return t


# ========================================================================== #
#  CONTENU
# ========================================================================== #
def section_1():
    return [
        P("1. Vue d'ensemble & architecture", "h1"),
        P("SENTINEL-X est un systeme de surveillance IoT intelligent : une carte "
          "ESP32 equipee de capteurs mesure l'environnement, transmet ses mesures "
          "en MQTT, et un PC les analyse (IA predictive + vision par ordinateur) "
          "pour produire un etat de securite unique (vert / jaune / rouge), affiche "
          "dans une application de bureau et renvoye vers l'ecran OLED et les LEDs de "
          "la carte."),
        P("Chaine de traitement (flux de donnees)", "h2"),
        mono([
            "ESP32 (DHT22 + MQ-2 + PIR + OLED + LEDs)",
            "   |  WiFi 2.4 GHz  -- MQTT (topic sentinel/sensors) -->",
            "Broker MQTT Mosquitto (Docker, port 1883 dev / 8883 TLS)",
            "   |  ingestion (scripts/mqtt_client.py, verif HMAC) -->",
            "Base SQLite  data/sentinel.db  (table sensor_data)",
            "   |                                   |",
            "   v                                   v",
            "IA predictive (Brique 6)        Vision YOLOv8n (Brique 5)",
            "ensemble + correlation          data/vision_status.json",
            "   |                                   |",
            "   +----------------+------------------+",
            "                    v",
            "        API Flask (api/server.py, port 3000)",
            "        etat consolide vert/jaune/rouge",
            "            |                        |",
            "   MQTT sentinel/alerts         App bureau (pywebview)",
            "   -> OLED + LEDs ESP32         + dashboard web",
        ]),
        P("Les briques du projet", "h2"),
        *bullets([
            "<b>Brique 3 - Ingestion</b> : reception MQTT, verification de signature "
            "HMAC, ecriture dans SQLite.",
            "<b>Brique 5 - Vision</b> : detection de personnes par YOLOv8n sur le flux "
            "webcam, nombre de personnes ecrit dans vision_status.json.",
            "<b>Brique 6 - IA predictive</b> : scoring d'anomalies (ensemble de modeles) "
            "et fusion multi-capteurs scientifique (correlation.py).",
            "<b>Brique 7 - API & stockage</b> : API REST Flask, stockage des alertes, "
            "dashboard securise, assistant IA.",
            "<b>App bureau</b> : fenetre pywebview (Edge WebView2 sous Windows) qui "
            "affiche le cockpit tout-en-un.",
        ]),
    ]


def section_2():
    pins = [
        ["Composant", "Role", "Broche ESP32", "Remarque"],
        ["DHT22", "Temperature + humidite", "GPIO 4", "Capteur numerique"],
        ["MQ-2", "Gaz / fumee", "GPIO 34 (ADC1)", "Auto-calibre, valeur normalisee (0 = air propre)"],
        ["PIR HC-SR501", "Presence / mouvement", "GPIO 27", "Entree INPUT_PULLDOWN"],
        ["OLED SSD1306", "Afficheur local 128x64", "I2C SDA 21 / SCL 22", "Adresses 0x3C ou 0x3D (scan auto)"],
        ["LED verte", "Etat normal", "D26", "Tout va bien"],
        ["LED orange", "Avertissement / deconnecte", "D14", "Alerte jaune"],
        ["LED rouge", "Alerte critique", "D13", "Alerte rouge"],
    ]
    return [
        P("2. Materiel ESP32 & capteurs", "h1"),
        P("La carte ESP32 lit trois capteurs, affiche l'etat en local sur un ecran "
          "OLED et trois LEDs, et communique en WiFi 2.4 GHz (l'ESP32 ne gere pas le "
          "5 GHz)."),
        table(pins, [3.2 * cm, 3.6 * cm, 3.4 * cm, 5.3 * cm]),
        P("Auto-calibration du capteur de gaz", "h2"),
        P("Le MQ-2 a besoin de chauffer. Au demarrage, le firmware ignore la premiere "
          "minute (chauffe) puis mesure la valeur de repos (air propre) comme ligne de "
          "base. Les mesures envoyees sont NORMALISEES : 0 = air propre, et la valeur "
          "monte quand du gaz/fumee est present. C'est plus lisible et comparable entre "
          "cartes."),
        P("Robustesse", "h2"),
        *bullets([
            "L'OLED est detectee par scan I2C : si elle est absente, le systeme "
            "continue (capteurs, WiFi, MQTT, LEDs) sans bloquer.",
            "En cas de perte WiFi, l'ESP32 ne redemarre pas en boucle : il continue en "
            "local et tente de se reconnecter.",
        ]),
    ]


def section_3():
    return [
        P("3. MQTT & securite de la communication (TLS, HMAC)", "h1"),
        P("La communication entre l'ESP32 et le PC passe par un broker MQTT Mosquitto "
          "(conteneur Docker). Deux topics sont utilises :"),
        *bullets([
            "<b>sentinel/sensors</b> : l'ESP32 publie ses mesures (temperature, "
            "humidite, gaz, presence) en JSON.",
            "<b>sentinel/alerts</b> : le serveur publie l'etat consolide (severite + "
            "contexte) que l'ESP32 recoit pour piloter l'OLED et les LEDs.",
        ]),
        P("Chiffrement TLS (MQTTS)", "h2"),
        P("En production, la liaison MQTT est chiffree par TLS sur le port 8883 : "
          "cote ESP32 via WiFiClientSecure (certificat du broker embarque), active par "
          "l'environnement PlatformIO -secrets. En developpement/demo, un port en clair "
          "1883 (DEV_PLAIN_MQTT) simplifie les tests. Le choix se fait a la compilation, "
          "ce qui garde le code retrocompatible."),
        P("Signature HMAC-SHA256 (anti-injection)", "h2"),
        P("Chaque mesure peut etre signee par l'ESP32 (HMAC-SHA256 via mbedtls) avec un "
          "secret partage. A l'ingestion (scripts/mqtt_client.py), la fonction "
          "_signature_valide() controle la signature :"),
        *bullets([
            "Pas de secret configure -> signature non verifiee (mode demo, "
            "retrocompatible).",
            "Mode souple (defaut) : un message sans signature est tolere, mais un "
            "message MAL signe est toujours rejete.",
            "Mode strict (MQTT_HMAC_STRICT=true) : tout message sans signature valide "
            "est rejete (production, quand tous les ESP32 signent).",
        ]),
        P("Objectif : empecher qu'un tiers injecte de fausses mesures dans le systeme "
          "(integrite et authenticite des donnees)."),
    ]


def section_4():
    scenarios = [
        ["Scenario", "Declencheur (fusion)", "Couleur"],
        ["INCENDIE", "Gaz eleve + forte chaleur / combustion (temp monte, air s'asseche)", "[ROUGE]"],
        ["FUITE_GAZ", "Gaz >= 300 sans montee thermique", "[ROUGE]"],
        ["SURCHAUFFE", "Temperature > 32 degres", "[ROUGE]"],
        ["FOULE", "Plusieurs personnes au-dela du seuil (camera)", "[ROUGE]"],
        ["GAZ_FAIBLE", "Gaz entre 100 et 299", "[JAUNE]"],
        ["PRESENCE", "Camera (1 personne) ou mouvement (PIR)", "[JAUNE]"],
        ["CHALEUR", "Temperature > 28 degres ou humidex eleve", "[JAUNE]"],
        ["CONDENSATION", "Humidite haute + temperature basse", "[VERT] info"],
        ["NORMAL", "Toutes les mesures coherentes", "[VERT]"],
    ]
    seuils = [
        ["Capteur", "Vert", "Jaune (avertissement)", "Rouge (critique)"],
        ["Temperature", "<= 28 degres", "28 a 32 degres", "> 32 degres"],
        ["Gaz (0 = air propre)", "< 100", "100 a 299", ">= 300"],
        ["Presence PIR", "aucune", "mouvement detecte", "-"],
        ["Camera", "0 personne", "1 personne", "2 personnes et +"],
    ]
    return [
        P("4. Intelligence artificielle predictive", "h1"),
        P("Deux approches complementaires : un scoring d'anomalies par apprentissage "
          "automatique, et une fusion multi-capteurs fondee sur la physique."),
        P("Ensemble de modeles (detection d'anomalies)", "h2"),
        P("L'ensemble (Brique 6.3) combine quatre modeles sur les signaux cles "
          "(temperature, humidite, gaz, presence) :"),
        *bullets([
            "<b>Isolation Forest</b> (100 arbres) : aberrances generales, non supervise.",
            "<b>Local Outlier Factor (LOF)</b> : points isoles par rapport au voisinage.",
            "<b>PyOD ECOD</b> : detection non parametrique basee sur la distribution.",
            "<b>Gradient Boosting</b> : classifieur supervise (vue dirigee).",
        ]),
        P("Les scores sont fusionnes ; au-dela du seuil (0.5), la lecture est jugee "
          "anormale. Le detecteur classique (IF + LOF) utilise en complement 27 features "
          "d'ingenierie (moyennes, ecarts, tendances...) calculees sur une fenetre "
          "glissante."),
        P("Fusion multi-capteurs scientifique (correlation.py)", "h2"),
        P("Plutot que des seuils isoles, le moteur croise temperature, humidite, gaz, "
          "PIR et camera pour identifier un SCENARIO reel. Une alerte grave exige "
          "plusieurs capteurs coherents, ce qui reduit fortement les faux positifs."),
        table(scenarios, [3.1 * cm, 9.4 * cm, 3.0 * cm]),
        Spacer(1, 6),
        P("Seuils par defaut (personnalisables par la calibration, section 8)", "h2"),
        table(seuils, [4.0 * cm, 3.5 * cm, 4.5 * cm, 3.5 * cm]),
        Spacer(1, 6),
        P("Assistant Ollama Mistral", "h2"),
        P("Un assistant conversationnel (modele Mistral via Ollama, local) est integre "
          "au cockpit. Il recoit en contexte l'etat live du systeme (mesures actuelles, "
          "niveau, derniere alerte, presence camera), ce qui lui permet de repondre sur "
          "la situation reelle et d'expliquer le projet. Le modele est prechauffe au "
          "demarrage pour une premiere reponse rapide."),
    ]


def section_5():
    return [
        P("5. Vision par ordinateur (detection de personnes)", "h1"),
        P("La Brique 5 capture le flux de la webcam (640x480) et detecte les personnes "
          "avec YOLOv8n (modele nano, ~3 M de parametres : leger et rapide sur CPU / "
          "Apple Silicon). Seules les detections sures (confiance >= 50 %) sont "
          "conservees."),
        *bullets([
            "Le nombre de personnes detectees est ecrit en continu dans "
            "data/vision_status.json (statut valable quelques secondes).",
            "Logique par defaut : 1 personne = jaune, 2 personnes et plus = rouge.",
            "Ce comportement est PERSONNALISABLE via l'assistant de calibration "
            "(ex. boulangerie ou 2 personnes = normal / vert).",
            "YOLO etant couteux sur CPU, l'inference ne tourne que sur 1 image sur N et "
            "le resultat est reutilise entre deux inferences (fluidite).",
        ]),
        P("La camera live est aussi affichee directement dans l'application de bureau."),
    ]


def section_6():
    return [
        P("6. Etat consolide, affichage & alertes", "h1"),
        P("Le coeur du systeme est un ETAT UNIQUE (vert / jaune / rouge), calcule par "
          "le serveur a partir des mesures LIVE passees dans le moteur de correlation, "
          "combine a la camera en direct. La source la plus grave l'emporte. Comme il "
          "repose sur les valeurs actuelles, un etat qui dure (ex. chaleur) reste "
          "colore en continu, sans clignotement."),
        P("Une seule verite, partout", "h2"),
        *bullets([
            "<b>Application / dashboard</b> : pastille d'etat, camera live, tableau des "
            "alertes, chat IA.",
            "<b>ESP32</b> : le serveur publie l'etat sur sentinel/alerts (sur changement "
            "+ battement regulier). L'OLED affiche une banniere et les LEDs refletent "
            "l'etat EN CONTINU (vert / orange / rouge).",
            "Les textes envoyes a l'OLED sont nettoyes en ASCII (les emojis ne "
            "s'affichent pas sur l'ecran).",
        ]),
        P("Gestion des alertes", "h2"),
        *bullets([
            "Les alertes sont historisees dans SQLite (table alerts) et affichees dans "
            "le tableau du dashboard.",
            "Un agregateur evite les doublons (intervalle minimum entre deux alertes "
            "identiques) : pas d'inondation d'alertes.",
            "L'historique est remis a zero a chaque demarrage (make app) pour repartir "
            "propre.",
        ]),
    ]


def section_7():
    endpoints = [
        ["Methode", "Endpoint", "Role"],
        ["GET", "/health", "Sonde de sante (l'API repond)"],
        ["GET/POST", "/api/v1/alerts", "Lire / recevoir une alerte (rediffusee vers l'ESP32)"],
        ["GET", "/api/v1/status", "Analyse de connectivite (API, broker, ESP32, webcam, IA, Ollama)"],
        ["GET", "/api/v1/context", "Etat live + resume pour l'IA (mesures, niveau, derniere alerte)"],
        ["GET", "/api/v1/alerts-rows", "Lignes HTML du tableau d'alertes (rafraichissement)"],
        ["GET", "/api/v1/live-body", "Bloc live (etat + mesures) pour l'affichage temps reel"],
        ["POST", "/api/v1/security-fix", "Applique les correctifs de securite automatiques"],
        ["GET/POST", "/api/v1/ollama", "Question a l'assistant Mistral"],
        ["GET", "/api/v1/ollama-status", "Disponibilite d'Ollama / modeles"],
        ["POST", "/api/v1/simulate", "Injecte une alerte simulee (demo)"],
        ["GET", "/app  /dashboard  /security  /live  /camera", "Pages (cockpit, dashboard, securite, camera)"],
        ["GET/POST", "/login  /logout", "Authentification du dashboard (avec 2FA)"],
    ]
    return [
        P("7. API REST", "h1"),
        P("L'API Flask (api/server.py, port 3000, multi-thread) expose les points "
          "d'acces suivants :"),
        table(endpoints, [2.4 * cm, 6.6 * cm, 6.5 * cm]),
        Spacer(1, 6),
        P("Format d'une alerte (JSON)", "h2"),
        mono([
            "{",
            '  "source": "ia_predictive",',
            '  "type": "anomaly_detected",',
            '  "confidence": 0.87,',
            '  "timestamp": "2026-10-09T10:15:30Z",',
            '  "details": {',
            '    "severity": "CRITICAL",        // INFO | WARNING | CRITICAL',
            '    "context": "Gaz/fumee eleve -> fuite de gaz probable",',
            '    "recommendation": "Ventiler, couper la source de gaz",',
            '    "scenario": "FUITE_GAZ",',
            '    "current_values": { "temp": 24, "humidity": 48, "gas": 420, "presence": 0 }',
            "  }",
            "}",
        ]),
    ]


def section_8():
    return [
        P("8. Assistant de calibration (adaptation a l'environnement)", "h1"),
        P("Chaque lieu a ses propres normes : une boulangerie est naturellement chaude, "
          "un commerce voit plusieurs personnes en permanence (ce qui est normal), un "
          "entrepot de nuit ne doit voir personne. L'assistant de calibration apprend "
          "ces normes et laisse l'utilisateur fixer ses propres seuils."),
        P("Principe en deux temps", "h2"),
        *bullets([
            "<b>1. Observation (2 minutes)</b> : le systeme affiche les valeurs de "
            "l'environnement en direct (temperature, humidite, gaz, presence, personnes) "
            "et enregistre les minima / maxima observes.",
            "<b>2. Questionnaire</b> : a partir de ces donnees, l'assistant propose des "
            "seuils et pose les questions cles. L'utilisateur DECIDE les limites : "
            "temperature jaune / rouge, gaz jaune / rouge, nombre de personnes "
            "considere comme normal (ex. 2 = OK en boulangerie), et si la presence (PIR) "
            "doit etre consideree comme un danger ou non.",
        ]),
        P("Le profil retenu est enregistre (data/profil_env.json) et le moteur de "
          "correlation l'utilise a la place des seuils par defaut. Ainsi, le meme "
          "systeme s'adapte a une boulangerie, un bureau ou un entrepot sans changer le "
          "code (et sans re-flasher l'ESP32, car les seuils sont cote serveur)."),
        P("Note : cette fonctionnalite est en cours de mise en place ; le present "
          "document decrit le principe retenu."),
    ]


def section_9():
    controles = [
        ["Controle (audit)", "Verifie"],
        ["secrets_versionnes", "Aucune cle privee / secret versionne dans git"],
        ["dashboard_auth", "Le dashboard exige une authentification"],
        ["xss", "Protection contre l'injection HTML (XSS)"],
        ["mqtt_chiffre", "Liaison MQTT chiffree (TLS)"],
        ["hmac_injection", "Signature HMAC active (anti-injection)"],
        ["api_exposee", "L'API n'est pas inutilement exposee"],
        ["cle_session", "Cle de session Flask robuste"],
    ]
    return [
        P("9. Securite", "h1"),
        *bullets([
            "<b>Authentification 2FA</b> : l'acces au dashboard est protege par "
            "identifiant + mot de passe + code 2FA.",
            "<b>TLS (MQTTS)</b> : communication ESP32 <-> broker chiffree (port 8883).",
            "<b>HMAC-SHA256</b> : integrite et authenticite des mesures (anti-injection).",
            "<b>Secrets non versionnes</b> : cles et certificats hors du depot git.",
            "<b>Audit automatise</b> (scripts/security_audit.py) : controles de "
            "securite + correctifs applicables en un clic depuis la page /security.",
        ]),
        P("Controles de l'audit de securite", "h2"),
        table(controles, [5.0 * cm, 10.4 * cm]),
    ]


def section_10():
    return [
        P("10. Demarrage & exploitation", "h1"),
        P("Commandes principales (Windows, depuis le dossier du projet)", "h2"),
        mono([
            "make app          # lance TOUT (broker, API, ingestion, detection,",
            "                  # vision) et ouvre le cockpit",
            "make flash-full   # flashe le firmware ESP32 (OLED + LEDs)",
            "make stop         # arrete les services",
            "make security-fix # applique les correctifs de securite",
        ]),
        P("Prerequis", "h2"),
        *bullets([
            "Un hotspot / WiFi en 2.4 GHz (l'ESP32 ne gere pas le 5 GHz).",
            "Docker (pour le broker MQTT Mosquitto).",
            "Ollama + modele Mistral installes (assistant IA) : ollama pull mistral.",
        ]),
        P("Depannage courant", "h2"),
        *bullets([
            "<b>Pas de donnees / etat fige</b> : verifier que le broker tourne "
            "(conteneur Docker) ; le relancer avec make app.",
            "<b>ESP32 ne se connecte pas</b> : verifier le WiFi 2.4 GHz et l'adresse IP "
            "du PC saisie sur la carte (portail de configuration).",
            "<b>Rien n'arrive sur le PC</b> : ouvrir le port 1883 dans le pare-feu "
            "Windows.",
            "<b>OLED illisible / absente</b> : verifier le cablage I2C (SDA 21, SCL 22, "
            "3V3, GND) ; le systeme fonctionne meme sans OLED.",
        ]),
    ]


def section_11():
    faq = [
        ("Comment evitez-vous les faux positifs ?",
         "Par la fusion multi-capteurs : une alerte grave exige plusieurs capteurs "
         "coherents (ex. gaz + chaleur + air qui s'asseche pour un incendie), pas un "
         "seul seuil. L'etat repose sur les valeurs live, et un agregateur evite les "
         "alertes en rafale."),
        ("Pourquoi un ensemble de modeles plutot qu'un seul ?",
         "Chaque modele a des angles morts. En combinant Isolation Forest, LOF, ECOD et "
         "Gradient Boosting, on couvre a la fois les aberrances generales, les points "
         "isoles et une vue supervisee : la detection est plus robuste."),
        ("Comment securisez-vous la communication ?",
         "Deux niveaux : le chiffrement TLS (MQTTS, port 8883) qui protege la "
         "confidentialite, et la signature HMAC-SHA256 qui garantit l'integrite et "
         "l'authenticite des mesures (un attaquant ne peut pas injecter de fausses "
         "donnees sans le secret)."),
        ("Que se passe-t-il si l'ESP32 perd le WiFi ?",
         "Il ne redemarre pas en boucle : il continue a mesurer en local (OLED + LEDs) "
         "et tente de se reconnecter en arriere-plan. La LED orange signale l'etat "
         "deconnecte."),
        ("Comment l'IA connait-elle le contexte du projet et la situation ?",
         "L'assistant Mistral recoit a chaque question un resume de l'etat live "
         "(mesures actuelles, niveau vert/jaune/rouge, derniere alerte, presence "
         "camera) ainsi qu'une description du systeme : il repond donc sur la situation "
         "reelle, pas dans le vide."),
        ("Comment adapter le systeme a un nouvel environnement ?",
         "Via l'assistant de calibration : 2 minutes d'observation puis un questionnaire "
         "ou l'on fixe les seuils (temperature, gaz, nombre de personnes normal, "
         "presence dangereuse ou non). Le profil est sauvegarde et applique sans "
         "re-flasher la carte."),
        ("Pourquoi la valeur de gaz est-elle normalisee ?",
         "Le MQ-2 a une valeur de repos qui varie selon la carte et la chauffe. En "
         "calibrant a 0 (air propre) au demarrage, les mesures deviennent comparables et "
         "lisibles : 0 = propre, et ca monte avec le gaz."),
        ("Comment l'etat de l'OLED et des LEDs reste-t-il synchronise avec l'app ?",
         "Le serveur calcule un etat unique et le publie vers l'ESP32 (topic "
         "sentinel/alerts) sur changement et par battement regulier. App, OLED et LEDs "
         "lisent donc la meme verite ; les LEDs refletent l'etat en continu."),
        ("La presence d'une personne declenche-t-elle toujours une alerte ?",
         "Non : c'est configurable. Par defaut une presence est un avertissement "
         "(jaune), mais dans un lieu ouvert au public on peut declarer la presence comme "
         "normale (verte) via la calibration."),
        ("Quelle est la difference entre jaune et rouge ?",
         "Jaune = avertissement (situation a surveiller : chaleur, gaz leger, presence). "
         "Rouge = critique (danger avere : incendie, fuite de gaz, surchauffe, foule). "
         "Chaque niveau a sa LED et sa couleur dans l'app."),
        ("Pourquoi YOLOv8n et pas un modele plus gros ?",
         "YOLOv8n (nano) est le plus leger de la famille : il tourne sur CPU sans GPU "
         "dedie, ce qui convient a un PC de terrain. La confiance minimale (50 %) evite "
         "les fausses detections."),
        ("Le systeme fonctionne-t-il si un composant tombe (OLED, camera, Ollama) ?",
         "Oui, chaque brique se degrade proprement : pas d'OLED -> le reste tourne ; "
         "pas de camera -> seuls les capteurs comptent ; pas d'Ollama -> l'etat et les "
         "alertes fonctionnent, seul le chat IA est indisponible."),
        ("Comment distinguez-vous un incendie d'une simple fuite de gaz ?",
         "Par la signature physique : un incendie combine gaz eleve, temperature qui "
         "monte ET humidite qui baisse (l'air s'asseche). Une fuite de gaz montre du gaz "
         "sans cette montee thermique. Deux scenarios, deux messages."),
        ("Ou sont stockees les donnees ?",
         "Les mesures capteurs et les alertes sont dans une base SQLite locale "
         "(data/sentinel.db). Les modeles IA sont dans models/, le statut camera dans "
         "data/vision_status.json."),
    ]
    blocs = [P("11. Questions possibles (FAQ / jury)", "h1")]
    for q, a in faq:
        blocs.append(P(q, "faqq"))
        blocs.append(P(a))
    return blocs


SECTIONS = [section_1, section_2, section_3, section_4, section_5, section_6,
            section_7, section_8, section_9, section_10, section_11]


# ========================================================================== #
#  PAGE TEMPLATES (garde + corps avec pagination)
# ========================================================================== #
def _page_corps(canvas, doc):
    canvas.saveState()
    # Bandeau haut
    canvas.setFillColor(BLEU_FONCE)
    canvas.rect(0, A4[1] - 1.1 * cm, A4[0], 1.1 * cm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(2 * cm, A4[1] - 0.72 * cm, "SENTINEL-X")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 0.72 * cm,
                           "Documentation technique")
    # Pied de page
    canvas.setStrokeColor(colors.HexColor("#c9d4e0"))
    canvas.line(2 * cm, 1.4 * cm, A4[0] - 2 * cm, 1.4 * cm)
    canvas.setFillColor(GRIS)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(2 * cm, 1.0 * cm, "SENTINEL-X - Equipe 6 EPSI")
    canvas.drawRightString(A4[0] - 2 * cm, 1.0 * cm, f"Page {doc.page}")
    canvas.restoreState()


def _page_garde(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(BLEU_FONCE)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, A4[1] - 6.2 * cm, A4[0], 0.25 * cm, fill=1, stroke=0)
    canvas.restoreState()


def build():
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(SORTIE), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.7 * cm, bottomMargin=1.8 * cm,
        title="SENTINEL-X - Documentation technique",
        author="rami yahyaoui")

    frame_corps = Frame(2 * cm, 1.8 * cm, A4[0] - 4 * cm, A4[1] - 3.6 * cm, id="corps")
    frame_garde = Frame(2 * cm, 2 * cm, A4[0] - 4 * cm, A4[1] - 4 * cm, id="garde")
    doc.addPageTemplates([
        PageTemplate(id="garde", frames=[frame_garde], onPage=_page_garde),
        PageTemplate(id="corps", frames=[frame_corps], onPage=_page_corps),
    ])

    story = []
    # --- Page de garde ---
    story.append(Spacer(1, 5.2 * cm))
    story.append(Paragraph("SENTINEL-X", ParagraphStyle(
        "t", fontName="Helvetica-Bold", fontSize=40, textColor=colors.white,
        alignment=TA_CENTER, leading=46)))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Systeme de surveillance IoT intelligent", ParagraphStyle(
        "st", fontName="Helvetica", fontSize=16, textColor=colors.HexColor("#9fc3ff"),
        alignment=TA_CENTER, leading=22)))
    story.append(Spacer(1, 1.0 * cm))
    story.append(Paragraph("Documentation technique complete", ParagraphStyle(
        "st2", fontName="Helvetica-Oblique", fontSize=12,
        textColor=colors.HexColor("#c9d4e0"), alignment=TA_CENTER)))
    story.append(Spacer(1, 4.5 * cm))
    meta = ParagraphStyle("m", fontName="Helvetica", fontSize=12, textColor=colors.white,
                          alignment=TA_CENTER, leading=20)
    story.append(Paragraph("Equipe 6 - EPSI (Workshop)", meta))
    story.append(Paragraph("Auteur : rami yahyaoui", meta))
    story.append(Paragraph(f"Date : {date(2026, 10, 9).strftime('%d/%m/%Y')}", meta))

    # --- Sommaire ---
    story.append(NextPageTemplate("corps"))
    story.append(PageBreak())
    story.append(P("Sommaire", "h1"))
    sommaire = [
        "1. Vue d'ensemble & architecture",
        "2. Materiel ESP32 & capteurs",
        "3. MQTT & securite de la communication (TLS, HMAC)",
        "4. Intelligence artificielle predictive",
        "5. Vision par ordinateur (detection de personnes)",
        "6. Etat consolide, affichage & alertes",
        "7. API REST",
        "8. Assistant de calibration (adaptation a l'environnement)",
        "9. Securite",
        "10. Demarrage & exploitation",
        "11. Questions possibles (FAQ / jury)",
    ]
    for s in sommaire:
        story.append(P(s, "bullet"))

    # --- Sections ---
    for i, section in enumerate(SECTIONS):
        story.append(PageBreak())
        story.extend(section())

    doc.build(story)
    return SORTIE


if __name__ == "__main__":
    chemin = build()
    print(f"[OK] PDF genere : {chemin}")
