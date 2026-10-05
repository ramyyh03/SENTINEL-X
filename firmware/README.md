# Firmware ESP32 — SENTINEL-X (équipe DEV/CYBER)

> Code embarqué du capteur physique. Projet **PlatformIO** (board `esp32dev`, framework Arduino).
> Lit le DHT22, l'affiche sur l'OLED **et publie les mesures en MQTT** vers la Brique 3.

---

## 🎯 Ce que fait le firmware

| Élément | Détail |
|---|---|
| Carte | ESP32 (`esp32dev`), framework Arduino |
| Température + humidité | **DHT22** sur GPIO **4** |
| **Gaz / fumée** | **MQ-2** sur GPIO **34** (entrée analogique ADC1) |
| **Présence / mouvement** | **PIR HC-SR501** sur GPIO **27** (sortie numérique) |
| Affichage | **Écran OLED SSD1306** 128×64 en I²C (SDA=21, SCL=22, adresse `0x3C`) |
| Réseau | **WiFi** + **publication MQTT** sur le topic `sentinel/sensors` |
| Config | **Portail web** (aucun identifiant dans le code) |
| Cadence | 1 lecture + 1 publication / **2 s** (PIR rafraîchi en temps réel) |

Message publié (format **exact** attendu par la Brique 3) :
```json
{"temp": 22.5, "humidity": 45.0, "gas": 1820, "presence": 1, "timestamp": "2026-10-05T12:00:00Z"}
```
> - `gas` = **valeur brute ADC** du MQ-2 (0 à 4095). Ce n'est pas encore des ppm calibrés — voir *Calibration MQ-2* ci-dessous.
> - `presence` = `1` si le PIR détecte un mouvement, sinon `0`.

---

## 🔌 Brochage (GPIO)

```
          ┌──────────── ESP32 ────────────┐
DHT22  ───┤ DATA → GPIO 4                  │
MQ-2   ───┤ A0   → GPIO 34  (analogique)   │
PIR    ───┤ OUT  → GPIO 27  (numérique)    │
OLED   ───┤ SDA  → GPIO 21 ; SCL → GPIO 22 │  (I²C, 0x3C)
          └───────────────────────────────┘
Alimentation : VCC = 3V3 (OLED, DHT22, PIR*) · GND commun
```
> \* Le **PIR HC-SR501** fonctionne mieux en **5V (VIN)** si disponible ; sa sortie OUT reste en 3,3 V, compatible ESP32.
> ⚠️ GPIO 34 est **entrée seule** (pas de pull-up interne, pas de sortie) — parfait pour un capteur analogique, et sur **ADC1** donc compatible WiFi actif.

---

## 🛰️ Calibration MQ-2 (gaz)

Le firmware publie la **valeur brute** `analogRead` (0–4095). C'est suffisant pour détecter une **variation** (seuil d'alerte). Pour aller vers des **ppm** :

1. **Préchauffage** : laisser le MQ-2 alimenté **24–48 h** la 1ʳᵉ fois (le capteur se stabilise).
2. **Baseline air pur** : noter la valeur brute à l'air libre (ex. ~300–600) = ton « zéro ».
3. **Seuil d'alerte** : choisir un delta au-dessus de la baseline (ex. baseline + 800) plutôt qu'une vraie conversion ppm.
4. *(avancé)* ppm réels = courbe Rs/R0 de la datasheet MQ-2 — hors périmètre workshop ; le brut + seuil suffit pour la démo.

> La détection d'anomalie (Brique 6, Isolation Forest) travaille très bien sur la valeur brute : elle apprend la baseline et repère les écarts automatiquement.

---

## 🚶 Réglage du PIR HC-SR501

Le module a **2 potentiomètres** + 1 cavalier :

| Réglage | Effet |
|---|---|
| Potentiomètre **Sensitivity** | portée de détection (~3 à 7 m) |
| Potentiomètre **Time delay** | durée où la sortie reste HIGH après détection (~3 s à 5 min) |
| Cavalier **H / L** | `H` = déclenchements répétés tant qu'il y a du mouvement (recommandé) ; `L` = un seul déclenchement |

> Pour la démo, régler **Time delay au minimum** et le cavalier sur **H** : la présence redevient `0` vite quand la zone est libre.

---

## 📶 Statut WiFi (comment voir si c'est connecté)

- **Sur l'OLED** (en haut) : `WiFi : connexion...` tant que non connecté, puis `WiFi <IP>` dès que connecté, et `MQTT <IP>` quand le broker est joint.
- **Sur le port série** (115200 bauds) : `WiFi connecte, IP : 192.168...`, `WiFi perdu`, `MQTT → sentinel/sensors : {...}`.
- La **reconnexion est automatique** (WiFiManager + boucle MQTT) en cas de coupure.

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
