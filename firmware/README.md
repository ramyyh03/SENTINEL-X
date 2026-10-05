# Firmware ESP32 — SENTINEL-X (équipe DEV/CYBER)

> Code embarqué du capteur physique. Projet **PlatformIO** (board `esp32dev`, framework Arduino).
> Lit le DHT22, l'affiche sur l'OLED **et publie les mesures en MQTT** vers la Brique 3.

---

## 🎯 Ce que fait le firmware

| Élément | Détail |
|---|---|
| Carte | ESP32 (`esp32dev`), framework Arduino |
| Capteur | **DHT22** sur GPIO **4** → température + humidité |
| Affichage | **Écran OLED SSD1306** 128×64 en I²C (SDA=21, SCL=22, adresse `0x3C`) |
| Réseau | **WiFi** + **publication MQTT** sur le topic `sentinel/sensors` |
| Config | **Portail web** (aucun identifiant dans le code) |
| Cadence | 1 lecture + 1 publication / **2 s** |

Message publié (format **exact** attendu par la Brique 3) :
```json
{"temp": 22.5, "humidity": 45.0, "gas": 0, "presence": 0, "timestamp": "2026-10-05T12:00:00Z"}
```
> `gas` et `presence` valent `0` pour l'instant (capteurs MQ-2 / PIR pas encore montés). Ce sont des **placeholders** : dès que les capteurs sont ajoutés, on remplit les vraies valeurs (voir `src/main.cpp`, `publierMesure()`).

---

## 🔌 Branchements

```
DHT22  →  DATA = GPIO 4,  VCC = 3V3,  GND = GND
OLED   →  SDA = GPIO 21,  SCL = GPIO 22,  VCC = 3V3,  GND = GND  (I²C 0x3C)
```

---

## 🛠️ Installation équipe — en 5 étapes (aucun code à modifier)

> Chacun fait ça **une seule fois** sur sa carte. Aucun identifiant n'est écrit dans le code ni poussé sur GitHub : tout reste dans la flash de l'ESP32.

1. **Flasher** la carte : `cd firmware && pio run -t upload` (voir plus bas).
2. Au 1er démarrage, l'ESP32 crée un réseau WiFi **`SENTINEL-X-SETUP`** (mot de passe `sentinel`). L'OLED l'affiche.
3. Depuis un **téléphone / PC**, se connecter à ce réseau → une **page web s'ouvre toute seule** (portail captif).
4. **Remplir le formulaire** :
   - *SSID* + *mot de passe* de **ton** WiFi,
   - *IP du PC-broker* : l'adresse du PC qui fait tourner Mosquitto
     (`ipconfig` sur Windows / `ifconfig | grep "inet "` sur Mac → genre `192.168.x.x`).
5. Valider → l'ESP32 mémorise tout, se connecte et commence à publier. ✅
   Au prochain démarrage, **plus rien à ressaisir**.

> 🔁 **Pour changer de réseau ou d'IP plus tard** : effacer la flash (`pio run -t erase`) puis re-flasher — le portail se rouvre.

---

## 🌐 Dev chacun chez soi / démo tous ensemble

Le **champ « IP du PC-broker »** du formulaire gère les deux cas **sans changer le code** :

| Phase | Qui fait tourner le broker | IP à saisir dans le portail |
|---|---|---|
| **Dev** | chacun sur son PC | l'IP de **son propre** PC |
| **Démo commune** | **un seul** PC central | tout le monde met **la même** IP centrale |

---

## 🔒 Sécurité

- **Aucun secret dans Git** : WiFi + IP broker vivent uniquement dans la flash de l'ESP32 (saisis au portail).
- Le portail `SENTINEL-X-SETUP` est **protégé par mot de passe** (pas de reconfiguration par un inconnu).
- **Roadmap durcissement (démo/prod)** — le code est prêt à basculer :

  | Niveau | Dev (actuel) | Prod |
  |---|---|---|
  | Port | `1883` (clair) | `8883` **TLS** |
  | Auth | anonyme | **user + mot de passe MQTT** (`mqtt.connect(id, user, pwd)`) |
  | Certif | — | **certificat CA** (déjà dans `mosquitto/certs/`) |

  → passer en prod = `WiFiClientSecure` + `client.setCACert(...)` + `MQTT_PORT = 8883`. Le client Python de la Brique 3 est déjà TLS-ready en symétrie.

---

## 🧪 Compiler / flasher (PlatformIO)

```bash
cd firmware
pio run                 # compile (télécharge les libs dans .pio/)
pio run -t upload       # flashe l'ESP32
pio device monitor      # lit le port série (115200 bauds)
```

> ℹ️ `platformio.ini` cible `upload_port = COM3` (Windows). Sur **macOS/Linux**, adapter avec le port détecté (`pio device list`, ex. `/dev/cu.usbserial-XXXX`).

---

## ✅ Tester la chaîne complète (avec ou sans ESP32)

- **Avec l'ESP32 flashé** : lancer le broker (`docker compose -f docker-compose.dev.yml up -d`) puis l'abonné (`python scripts/mqtt_client.py`). Les mesures de la carte arrivent dans `data/sentinel.db`.
- **Sans matériel** : le simulateur `simulate/fake_sensors_esp32.py --simulate` joue l'ESP32 (même topic, même format JSON). La Brique 3 reste 100 % testable.
