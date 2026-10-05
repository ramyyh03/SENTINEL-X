# Firmware ESP32 — SENTINEL-X (équipe DEV/CYBER)

> Code embarqué du capteur physique. Projet **PlatformIO** (board `esp32dev`, framework Arduino).
> Intégré au mono-repo pour que toute l'équipe l'ait au `git pull`.

---

## 🎯 Ce que fait le firmware **aujourd'hui**

| Élément | Détail |
|---|---|
| Carte | ESP32 (`esp32dev`), framework Arduino |
| Capteur | **DHT22** sur GPIO **4** → température + humidité |
| Affichage | **Écran OLED SSD1306** 128×64 en I²C (SDA=21, SCL=22, adresse `0x3C`) |
| Sortie | **Port série** 115200 bauds (`T=.. C  H=.. %`) + OLED |
| Cadence | 1 lecture / **2 s** (limite matérielle du DHT22) |

Fichiers sources :

| Fichier | Rôle |
|---|---|
| `platformio.ini` | Config carte + dépendances (`DHT`, `Adafruit SSD1306/GFX/Unified Sensor`) |
| `src/main.cpp` | Boucle lecture DHT22 → série + OLED |
| `include/`, `lib/`, `test/` | Dossiers standard PlatformIO (vides pour l'instant) |

> ⚠️ `.pio/` (build) et les librairies téléchargées **ne sont pas commités** : `pio run` les régénère. C'est volontaire (ils pèsent ~7 Mo et dépendent de la machine).

---

## 🔌 Branchements

```
DHT22  →  DATA = GPIO 4,  VCC = 3V3,  GND = GND
OLED   →  SDA = GPIO 21,  SCL = GPIO 22,  VCC = 3V3,  GND = GND  (I²C 0x3C)
```

---

## ⚠️ Compatibilité avec la BRIQUE 3 (MQTT + SQLite) — état réel

**Ce firmware n'est PAS encore relié au pipeline SENTINEL-X.** Il lit et affiche en local, mais n'envoie rien sur le réseau. Diagnostic point par point :

| Attendu par la Brique 3 | Firmware actuel | Verdict |
|---|---|---|
| WiFi | ❌ absent | à ajouter |
| MQTT publish sur `sentinel/sensors` | ❌ absent | à ajouter |
| JSON `{temp, humidity, gas, presence, timestamp}` | ❌ (série texte, pas de JSON) | à ajouter |
| `temp` (DHT22) | ✅ lu | OK |
| `humidity` (DHT22) | ✅ lu | OK |
| `gas` (MQ-2) | ❌ pas de capteur gaz | à ajouter |
| `presence` (PIR) | ❌ pas de capteur présence | à ajouter |
| Broker 1883 (dev) / 8883 (TLS) | ❌ pas de client MQTT | à ajouter |

**Conclusion :** la chaîne complète `ESP32 → MQTT → SQLite` **ne fonctionne pas encore avec le vrai matériel**. En attendant, le **simulateur** `simulate/fake_sensors_esp32.py` joue le rôle de l'ESP32 et alimente réellement la Brique 3 (c'est lui qui publie le bon JSON sur `sentinel/sensors`). La Brique 3 reste donc **100 % fonctionnelle et testable** sans matériel.

---

## 🛣️ Pour connecter ce firmware au pipeline (prochaine étape DEV/CYBER)

Il faut ajouter dans `src/main.cpp` :

1. **WiFi** (`#include <WiFi.h>`) → connexion au réseau.
2. **Client MQTT** (`PubSubClient` ou `arduino-mqtt`) → `lib_deps` à compléter dans `platformio.ini`.
3. **Sérialisation JSON** (`ArduinoJson`) au format exact attendu :
   ```json
   {"temp": 22.5, "humidity": 45.0, "gas": 150, "presence": 0, "timestamp": "2026-10-05T12:00:00Z"}
   ```
4. **Publish** sur le topic `sentinel/sensors` (broker PC, port `1883` en dev).
5. *(optionnel)* Capteurs **MQ-2** (gaz) et **PIR** (présence) pour remplir `gas` et `presence`.

> 💡 Je peux générer cette version « MQTT-ready » du firmware sur demande (sans écraser la version actuelle de l'équipe) : elle a besoin du SSID/mot de passe WiFi et de l'IP du PC-broker.

---

## 🧪 Compiler / flasher (PlatformIO)

```bash
cd firmware
pio run                 # compile (télécharge les libs dans .pio/)
pio run -t upload       # flash l'ESP32 (ajuster upload_port dans platformio.ini, ex. /dev/cu.usbserial-XXXX sur macOS)
pio device monitor      # lit le port série (115200 bauds)
```

> ℹ️ `platformio.ini` cible `upload_port = COM3` (Windows). Sur **macOS**, remplacer par le port série détecté (`pio device list`).
