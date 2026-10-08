# 🎬 SENTINEL-X — Récap complet + Guide vidéo de démo

> Tout ce qui est en place, les références, la sécurité, et un **script vidéo**
> prêt à filmer. Équipe 6 — Workshop EPSI BAC+4.

---

## 1. Le projet en une phrase
**SENTINEL-X** est un système de **surveillance IoT intelligent** : un ESP32
mesure l'environnement (température, humidité, gaz, présence), envoie les données
en WiFi/MQTT à un PC qui les **analyse avec de l'IA** (détection d'anomalies +
vision par caméra + assistant Mistral) et les affiche sur un **dashboard sécurisé**.

---

## 2. Architecture (la chaîne complète)
```
   ESP32 (capteurs + OLED + 3 LEDs)
        │  WiFi 2.4 GHz
        ▼
   MQTT (broker Mosquitto, Docker, port 1883)
        │
        ▼
   PC — SENTINEL-X
   ├─ Ingestion → base SQLite
   ├─ IA prédictive (ensemble : Isolation Forest + LOF + ECOD + Gradient Boosting)
   ├─ Santé des capteurs (panne / figé / dérive)
   ├─ Vision YOLOv8 (webcam UGREEN) → détection de personnes
   ├─ Ollama / Mistral (assistant + rapport d'audit)
   └─ Dashboard web sécurisé (cockpit : analyse + caméra + alertes + sécurité)
```

---

## 3. ✅ Tout ce qui est en place

### Matériel (ESP32)
- **DHT22** (GPIO4) : température + humidité
- **MQ-2** (GPIO34) : gaz/fumée, **auto-calibré** (0 au repos, monte avec le gaz)
- **PIR HC-SR501** (GPIO27) : présence/mouvement
- **OLED SSD1306** (I²C 21/22) : affichage local (IP, mesures, alertes)
- **3 LEDs de statut** : 🟢 vert D26 (connecté) · 🟠 orange D14 (démarrage/déconnecté) · 🔴 rouge D13 (alerte critique)
- Firmware robuste : scan I²C, scan WiFi, auto-calibration gaz, non-bloquant si OLED absente, reconnexion auto.

### Logiciel (PC)
- **Lancement en UNE commande** : `make.bat app` (démarre tout + ouvre le cockpit)
- **Cockpit** : analyse de connectivité en direct (API, broker, ESP32, webcam, IA, Mistral)
- **Dashboard alertes** + **Capteurs en direct** + **Caméra** + **Sécurité** (onglets)
- **IA prédictive** : ensemble hybride (précision/rappel élevés), ré-entraînable (`make train-ensemble`)
- **Vision** : YOLOv8n, détection de personnes, préfère la **webcam externe (UGREEN)**
- **Assistant IA** : Ollama + **Mistral** (chat + bouton « Tester l'IA »)

---

## 4. 🔐 SÉCURITÉ — tout en détail

| # | Protection | Comment c'est fait | Où |
|---|---|---|---|
| 1 | **Authentification 2FA** | Login + code **TOTP** (Google/Microsoft Authenticator). Sans compte valide, pas d'accès au dashboard. | `make setup-2fa`, `api/auth.py` |
| 2 | **Anti-XSS** | Toutes les données capteurs (venant de MQTT) sont **échappées** (`html.escape`) avant affichage → pas d'injection de script. | `api/server.py` |
| 3 | **Audit de sécurité auto** | Page web **« Suis-je sécurisé ? »** : vérifie secrets, auth, XSS, MQTT, HMAC, API. Bouton **« Corriger automatiquement »**. | onglet **Sécurité**, `scripts/security_audit.py` |
| 4 | **Anti-injection HMAC** | L'ESP32 **signe** ses messages (HMAC-SHA256). Un faux message (sans la clé) est **rejeté**. | `security/message_signing.py`, firmware `-DUSE_HMAC` |
| 5 | **Gestion des secrets** | `secrets.h` (WiFi/clé) et `.env` **gitignorés** : jamais sur GitHub. Vérifié par l'audit. | `.gitignore` |
| 6 | **MQTTS (TLS) prêt** | Broker prod 8883 chiffré + certificats (firmware `WiFiClientSecure`). Activable le jour J. | `security/gen-certs.sh`, `docker/` |
| 7 | **Clé de session signée** | Cookies de login signés (PBKDF2), clé persistante. | `api/auth.py`, `data/.flask_secret` |
| 8 | **Durcissement fichiers** | Droits restreints (600) sur `.env` et les comptes (via l'audit). | `scripts/security_audit.py` |
| 9 | **Mode démo assumé** | Les risques acceptables sur hotspot isolé (MQTT 1883, API 0.0.0.0) sont **documentés et validés**, pas cachés. | audit, `SENTINEL_DEMO_MODE` |
| 10 | **Red team (audit croisé)** | Playbook local (nmap, mosquitto) pour l'audit autorisé des autres équipes + rapport Ollama. **Jamais poussé** sur GitHub. | `REDTEAM-PLAYBOOK.md` (local) |

> 🛡️ **Principe** : on audite notre propre système (« suis-je sécurisé ? »), on
> corrige ce qui est corrigeable automatiquement, et on documente honnêtement ce
> qui est un choix de démo. L'offensif reste local et éthique (équipes consentantes).

---

## 5. ▶️ Comment lancer (pour filmer)

**Pré-requis** : téléphone hotspot « Don't use AI man » en **2.4 GHz** allumé ; PC connecté dessus ; Docker Desktop lancé ; ESP32 branché.

```powershell
cd C:\workshop\SENTINEL-X
.\make.bat app
```
→ ouvre le cockpit. Laisser tourner (ne pas faire `make.bat stop` pendant la démo).

**Si l'app se fige** (IP du PC changée) :
```powershell
.\make.bat config-esp32
.\make.bat flash-full
```

---

## 6. 🎥 Script vidéo suggéré (séquence à filmer)

1. **Intro (10 s)** : « SENTINEL-X, système de surveillance IoT intelligent et sécurisé, équipe 6. »
2. **Le matériel (20 s)** : montrer l'ESP32, les capteurs, l'OLED qui affiche `MQTT: <IP>` + température/humidité, les 3 LEDs (verte allumée = connecté).
3. **Lancement (10 s)** : `\.make.bat app` → le cockpit s'ouvre, l'analyse est **toute verte** (« Tout est connecté et fonctionnel »).
4. **Capteurs en direct (15 s)** : onglet **Capteurs** → les valeurs bougent et correspondent à l'OLED.
5. **Démo GAZ (20 s)** : approcher un briquet (**gaz, pas de flamme**) → la valeur gaz monte → **alerte** : 🔴 LED rouge + bannière OLED « ALERTE » + ligne dans le dashboard.
6. **Démo PRÉSENCE (10 s)** : passer la main devant le PIR → présence détectée.
7. **Caméra + IA vision (15 s)** : onglet **Caméra** → la webcam détecte une personne (boîte).
8. **Assistant IA (15 s)** : bouton **« Tester l'IA »** → Mistral répond.
9. **SÉCURITÉ (25 s)** : onglet **Sécurité** → montrer l'audit « Suis-je sécurisé ? », cliquer **« Corriger automatiquement »** → tout passe vert. Montrer le **login 2FA**.
10. **Conclusion (10 s)** : « De la mesure physique à l'IA jusqu'au dashboard sécurisé — SENTINEL-X, de bout en bout. »

> Durée totale ~2-3 min. Filmer le PC (cockpit) **et** le matériel (ESP32/OLED/LEDs) en alternance.

---

## 7. 📚 Références (fichiers & commandes)

**Docs du projet** (`BRIQUES/`) :
- `BRIQUE5-IA.md` (vision), `BRIQUE6-IA.md` (prédictif), `BRIQUE7-IA.md` (API)
- `SECURITE-DASHBOARD.md`, `security/SECURITE.md` (sécurité)
- `APP-BUREAU-LEDS.md` (app + LEDs), `SETUP-OLLAMA.md`, `BROKER-MQTT.md`
- `INSTALL-WINDOWS.md` (install nouveau PC)

**Commandes clés** (`make.bat …`) :
| Commande | Rôle |
|---|---|
| `app` | Tout lancer + cockpit |
| `stop` | Tout arrêter |
| `config-esp32` | Met à jour l'IP du broker |
| `flash-full` | Flasher l'ESP32 (complet) |
| `flash-diag` | Firmware diagnostic (test matériel) |
| `monitor` | Moniteur série (voir l'ESP32) |
| `setup-2fa` | Créer le compte dashboard + 2FA |
| `security-audit` | Lancer l'audit de sécurité |
| `train-ensemble` | Réentraîner l'IA |

**URLs** : cockpit `http://localhost:3000/app` · dashboard `/dashboard` · capteurs `/live` · caméra `/camera` · sécurité `/security`

---

*Système validé de bout en bout — Équipe 6.*
