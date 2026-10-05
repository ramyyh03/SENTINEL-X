# BRIQUE 3 : MQTT Client & SQLite

> **SENTINEL-X — Workshop EPSI BAC+4**
> Branche : `feature-mqtt` · Broker dev : `localhost:1883` · Microcontrôleur : **ESP32**

---

## 🎯 Vue d'ensemble (30 secondes)

**Réception MQTT + persistance temps réel en SQLite.** L'ESP32 (ou le simulateur) publie ses mesures sur `sentinel/sensors` ; le client Python s'abonne, **valide**, **affiche** et **stocke** chaque mesure dans `data/sentinel.db`. Cette base devient la **source de vérité** des séries temporelles pour la Brique 6 (Isolation Forest).

---

## 🏗️ Architecture étendue

```
ESP32 ──MQTT publish──► Mosquitto ──subscribe──► mqtt_client.py ──► SQLiteCollector ──► data/sentinel.db
  fake_sensors_esp32.py    (broker)                 (abonné)          (collector)         (persistance)
```

---

## 📂 Fichiers

| Fichier | Rôle |
|---|---|
| `scripts/mqtt_client.py` | Abonné MQTT → log + insert SQLite |
| `simulate/fake_sensors_esp32.py` | Simulateur ESP32 (publie des mesures réalistes) |
| `predictive/collector.py` | **Nouveau** — `SQLiteCollector` : crée la base + insère les mesures |

---

## 📦 Installation

Dépendances déjà dans `requirements.txt` (`paho-mqtt`, `python-dotenv`, `colorama`). SQLite = lib standard Python, rien à installer.

```bash
source venv/bin/activate        # (.\venv\Scripts\activate sur Windows)
pip install -r requirements.txt
cp .env.example .env            # MQTT_HOST=localhost, MQTT_PORT=1883, DB_PATH=data/sentinel.db
```

---

## 🧪 Test sans ESP32 (3 terminaux)

```bash
# Terminal 1 — broker
docker compose -f docker-compose.dev.yml up -d

# Terminal 2 — simulateur (10 cycles)
python simulate/fake_sensors_esp32.py --simulate

# Terminal 3 — abonné + persistance
python scripts/mqtt_client.py
```

Logs attendus côté abonné :
```
[OK] SQLite prêt : .../data/sentinel.db
[OK] Connecté au broker — abonnement à « sentinel/sensors »
[MSG] Message reçu : 22.5°C | 44.7% | gaz 155ppm | 👤 présence | 2026-10-05T12:30:57Z
[DB] Données stockées en SQLite (id=1)
```

Vérifier la base :
```bash
sqlite3 data/sentinel.db "SELECT COUNT(*) FROM sensor_data;"   # → 10 (ou proche)
```

> ✅ Validé : 10 messages publiés → 10 lignes insérées en base.

---

## 🗄️ Structure de la base

Table `sensor_data` :

| Colonne | Type | Description |
|---|---|---|
| `id` | INTEGER PK | auto-incrément |
| `timestamp` | TEXT | ISO 8601 de la mesure (côté capteur) |
| `temp` | REAL | °C (DHT22) |
| `humidity` | REAL | % (DHT22) |
| `gas` | REAL | ppm (MQ-2) |
| `presence` | INTEGER | 0 / 1 (PIR) |
| `created_at` | TIMESTAMP | insertion en base (défaut `CURRENT_TIMESTAMP`) |

Exemple de requête (dernières mesures) :
```bash
sqlite3 -header -column data/sentinel.db \
  "SELECT id,timestamp,temp,humidity,gas,presence FROM sensor_data ORDER BY id DESC LIMIT 5;"
```

---

## 🧯 Troubleshooting

| Problème | Cause | Solution |
|---|---|---|
| `[DB][ERREUR] … database is locked` | 2 process écrivent en même temps | Le collector attend 5 s (timeout) ; éviter plusieurs clients en parallèle sur le même `.db` |
| `[ERREUR] Initialisation SQLite échouée` | Dossier non inscriptible / chemin invalide | Vérifier `DB_PATH` dans `.env` et les droits sur `data/` |
| `no such table: sensor_data` | Mauvais fichier `.db` interrogé | La table est créée au 1er run du client ; vérifier le chemin `data/sentinel.db` |
| Base vide après test | Client lancé après le simulateur | Lancer l'abonné **avant** le simulateur (sinon messages manqués, MQTT QoS 0) |
| `Connection refused` | Broker éteint | `docker compose -f docker-compose.dev.yml up -d` |

> ⚠️ Le fichier `data/sentinel.db` est **gitignoré** : il ne doit jamais être commité (c'est de la donnée runtime).

---

## 🚀 Prochaine étape

**BRIQUE 4 — Webcam Capture (OpenCV)** : lire le flux webcam USB en 640×480 (macOS), base de la détection YOLOv8.

---

## 📘 Ce que j'ai fait — Brique 3 (MQTT Client + SQLite)

**En une phrase :** client MQTT qui persiste chaque mesure en SQLite pour l'historique temps réel.

**Pourquoi ce choix technique :** séparation nette **input (MQTT)** vs **processing (Forest, Brique 6)**. Le `SQLiteCollector` (pattern Repository léger) isole l'accès base : il est prêt à être appelé par l'IA prédictive sans qu'elle connaisse MQTT. SQLite = embarqué, sans serveur, zéro config — idéal pour un historique local.

**Comment ça s'intègre dans SENTINEL-X :** `data/sentinel.db` devient la **source de vérité** des séries temporelles. La Brique 6 lira directement cette table pour entraîner l'Isolation Forest et détecter les anomalies — aucune dépendance au flux MQTT en direct.

**Pour tester sans matériel :** simulateur + client + vérif SQLite (3 terminaux ci-dessus). Testé : 10 messages → 10 lignes en base.
