# BRIQUE 3 : MQTT Client — Recevoir les données capteurs

> **SENTINEL-X — Workshop EPSI BAC+4**
> Branche : `feature-mqtt` · Broker dev : `localhost:1883`

---

## 🎯 Vue d'ensemble (30 secondes)

On met en place le **récepteur** des données capteurs. L'ESP8266 (ou le simulateur) **publie** des mesures sur le topic MQTT `sentinel/sensors` ; notre client Python **s'abonne**, reçoit chaque message, le **valide** et l'affiche. C'est la porte d'entrée des données dans le système — elles iront ensuite en SQLite (Brique 6) et nourriront le prédictif.

---

## 🏗️ Architecture

```
ESP8266 (ou simulateur)  ──MQTT publish──►  Mosquitto  ──MQTT subscribe──►  mqtt_client.py
   fake_sensors.py            topic: sentinel/sensors         (broker)            (abonné)
```

Les deux côtés sont **découplés** : l'émetteur ne sait pas qui écoute, l'abonné ne connaît pas l'émetteur. On peut donc remplacer le simulateur par le vrai ESP8266 **sans changer une ligne** du client.

---

## 📦 Installation

Les dépendances sont déjà dans `requirements.txt` (`paho-mqtt`, `python-dotenv`, `colorama`).

```bash
source venv/bin/activate        # (.\venv\Scripts\activate sur Windows)
pip install -r requirements.txt
cp .env.example .env            # config : MQTT_HOST=localhost, MQTT_PORT=1883
```

---

## 🧪 Test (sans matériel)

**Terminal 1 — lancer le broker dev :**
```bash
docker compose -f docker-compose.dev.yml up -d
```

**Terminal 2 — lancer le simulateur ESP8266 (10 cycles) :**
```bash
python simulate/fake_sensors.py --simulate
```

**Terminal 3 — lancer l'abonné :**
```bash
python scripts/mqtt_client.py
```

**Résultat attendu** côté abonné :
```
[OK] Connecté au broker — abonnement à « sentinel/sensors »
[MSG] Message reçu : 22.8°C | 58.2% | gaz 124ppm | 👤 présence | 2026-10-05T12:06:31Z
```

> 💡 `fake_sensors.py` **sans** `--simulate` publie en continu (toutes les 2 s) jusqu'à Ctrl+C.

---

## 📨 Format du message capteur

```json
{"temp": 23.5, "humidity": 45.2, "gas": 150, "presence": 0, "timestamp": "2026-10-05T12:00:00Z"}
```

| Champ | Capteur | Plage simulée |
|---|---|---|
| `temp` | DHT22 | 20–30 °C |
| `humidity` | DHT22 | 30–70 % |
| `gas` | MQ-2 | 100–200 ppm |
| `presence` | PIR HC-SR501 | 0 ou 1 |
| `timestamp` | — | ISO 8601 UTC |

> ⚠️ À ne pas confondre avec le **format d'alerte** unifié (Brique 7) envoyé à l'API DEV : ici ce sont les **données brutes** capteurs.

---

## 🧯 Troubleshooting

| Problème | Cause | Solution |
|---|---|---|
| `Connexion impossible … Connection refused` | Broker pas lancé | `docker compose -f docker-compose.dev.yml up -d` |
| Abonné connecté mais **0 message** | Mauvais topic / pas d'émetteur | Vérifier `MQTT_TOPIC` identique des 2 côtés ; lancer le simulateur |
| `timeout` / reste bloqué | Mauvais `MQTT_HOST`/port | Vérifier `.env` (dev = `localhost:1883`) |
| `[WARN] Message incomplet` | JSON reçu sans tous les champs | Normal si un autre émetteur publie un format différent |
| `JSON invalide` | Payload non-JSON sur le topic | Un autre outil publie du texte brut — vérifier qui publie |

---

## 🔒 TLS-ready (mercredi, prod)

Le client bascule **automatiquement** en TLS si `MQTT_PORT=8883` : il charge le CA (`MQTT_CA_CERT`) et chiffre la connexion. Rien à changer dans le code — juste le `.env` :
```
MQTT_HOST=192.168.x.x
MQTT_PORT=8883
MQTT_CA_CERT=mosquitto/certs/ca.crt
```

---

## 🚀 Prochaine étape

**BRIQUE 4 — Webcam Capture** (`scripts/webcam_capture.py`, macOS) : lire le flux webcam USB en 640×480 pour préparer la détection YOLOv8.

---

## 📘 Ce que j'ai fait — Brique 3 (MQTT Client + Simulateur)

**En une phrase :** j'ai créé le récepteur des données capteurs (abonné MQTT) + un simulateur ESP8266 pour tester sans matériel.

**Pourquoi ce choix technique :** `paho-mqtt` est la lib MQTT de référence en Python. Le code est compatible paho **1.x et 2.x** (l'API des callbacks a changé en 2.0). Config entièrement via `.env` → aucune valeur en dur, bascule dev/prod sans toucher au code.

**Comment ça s'intègre dans SENTINEL-X :** c'est le point d'entrée des données dans le flux `ESP8266 → MQTT → IA`. Le client reçoit et valide ; en Brique 6 ces mesures seront stockées en SQLite et analysées par l'Isolation Forest.

**Pourquoi un simulateur :** il publie des mesures réalistes toutes les 2 s, ce qui permet à toute l'équipe IA de développer et tester **en parallèle**, sans attendre le câblage de l'ESP8266 (règle du mode simulation du projet).

**Pour tester sans matériel :**
```bash
docker compose -f docker-compose.dev.yml up -d
python simulate/fake_sensors.py --simulate      # publie 10 cycles
python scripts/mqtt_client.py                    # (autre terminal) affiche les messages
```
✅ Testé et validé : 10 messages publiés, reçus et parsés correctement.
