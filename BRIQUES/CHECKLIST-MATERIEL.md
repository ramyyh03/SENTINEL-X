# ✅ CHECKLIST — Test du matériel (Webcam UGREEN CM678 + ESP32)

> **SENTINEL-X — Workshop EPSI BAC+4** · à faire sur le **PC Windows**
> Signé : rami yahyaoui
> Prérequis : `make.bat install` déjà réussi (venv Python 3.12 + dépendances OK).

---

## 📷 PARTIE A — Webcam UGREEN CM678 (P/N 15728)

> Webcam **UVC** standard → aucun pilote à installer (plug-and-play).

### A1. Branchement & reconnaissance
- [ ] Brancher la webcam sur un port **USB** (USB 3.0 bleu de préférence).
- [ ] Attendre le son/la notif de reconnaissance Windows.
- [ ] Vérifier dans **Gestionnaire de périphériques** → **Caméras** : une entrée type « UGREEN » / « USB Camera » apparaît.

### A2. Autoriser l'accès caméra (Windows)
- [ ] **Paramètres → Confidentialité et sécurité → Caméra**
- [ ] Activer **« Accès à la caméra »** + **« Autoriser les applications de bureau à accéder à la caméra »**.

### A3. Trouver l'index de la webcam
```powershell
cd C:\workshop\SENTINEL-X
venv\Scripts\python -m vision.detector --list
```
- [ ] Noter les index affichés. Sur un PC **avec caméra intégrée**, la UGREEN est souvent **index 1** (l'intégrée = 0).

### A4. Test automatique (capture + YOLOv8 + rapport)
```powershell
venv\Scripts\python scripts\test_materiel.py --camera 1
```
*(remplacer `1` par l'index trouvé ; sans `--camera`, il prend la 1re qui marche)*
- [ ] 3 images capturées dans `data\captures\`.
- [ ] Le script affiche la **latence** (objectif < 100 ms) et le **nb de personnes**.
- [ ] Le fichier **`RAPPORT-MATERIEL.md`** est généré.
- [ ] ℹ️ *0 personne détectée est normal si personne n'est dans le champ.*

### A5. Test visuel « en direct » (détection d'une personne)
```powershell
venv\Scripts\python -m vision.detector --show --camera 1
```
- [ ] Une fenêtre s'ouvre avec le flux webcam.
- [ ] **Se placer devant la caméra** → un rectangle rouge « person » apparaît.
- [ ] Fermer avec la touche **`q`**.

### A6. Chaîne complète (alerte intrusion → API → dashboard)
```powershell
.\make.bat api
```
Dans une 2ᵉ fenêtre PowerShell :
```powershell
cd C:\workshop\SENTINEL-X
venv\Scripts\python -m vision.detector --camera 1
```
- [ ] Se mettre devant la caméra.
- [ ] Ouvrir **http://localhost:3000/dashboard** → une alerte `ia_vision / intrusion_detected` apparaît.

✅ **Webcam validée** si A4 (capture+YOLO) et A5 (détection visuelle) passent.

---

## 🔌 PARTIE B — ESP32 (DHT22 + MQ-2 + PIR + OLED, MQTTS)

> Firmware dans `firmware/`. Brochage complet : `firmware/README.md`.

### B0. Prérequis
- [ ] **PlatformIO** installé : extension **PlatformIO IDE** dans VS Code **ou** PlatformIO Core (`pip install platformio`).
- [ ] Câble USB **data** (pas seulement charge) pour l'ESP32.

### B1. Câblage des capteurs (ESP32 éteint)
```
DHT22  : DATA → GPIO 4   | VCC → 3V3 | GND → GND
PIR    : OUT  → GPIO 27  | VCC → 5V (VIN) | GND → GND
MQ-2   : A0   → GPIO 34  | VCC → 5V (VIN) | GND → GND
OLED   : SDA → GPIO 21, SCL → GPIO 22 | VCC → 3V3 | GND → GND  (I²C 0x3C)
```
- [ ] Vérifier GND **commun** à tous les modules.

### B2. Brancher l'ESP32 & trouver le port COM
- [ ] Brancher l'ESP32 en USB.
- [ ] **Gestionnaire de périphériques → Ports (COM & LPT)** → noter le **COMx** (ex. COM3).
  *(Si rien n'apparaît : installer le pilote USB-série **CP210x** ou **CH340** selon la carte.)*

### B3. Configurer le port d'upload
- [ ] Dans `firmware/platformio.ini`, mettre `upload_port = COMx` (ton port réel).

### B4. Compiler & flasher
```powershell
cd C:\workshop\SENTINEL-X\firmware
pio run                 # compile (télécharge les libs la 1re fois)
pio run -t upload       # flashe l'ESP32
```
- [ ] Compilation **SUCCESS**, upload **SUCCESS**.

### B5. Moniteur série (voir les logs)
```powershell
pio device monitor -b 115200
```
- [ ] Logs visibles : lecture DHT22, Gaz, PIR, état WiFi.
- [ ] L'**OLED** affiche Temp / Humi / Gaz / PIR + statut WiFi.
- [ ] Au 1er démarrage : si portail WiFi (version WiFiManager), se connecter au réseau **`SENTINEL-X-SETUP`** et saisir le WiFi + l'IP du broker.

### B6. Réception côté serveur
> ⚠️ **Point d'attention sécurité** : le firmware de l'équipe CYBER publie en **MQTTS (TLS 8883 + authentification)**. Il faut donc le **broker de PROD** (certificats + `passwd`), pas le broker dev anonyme (1883).

- [ ] Générer les certs si besoin : `bash security/gen-certs.sh <IP_DU_PC>` *(Git Bash)*.
- [ ] Démarrer le broker prod : `docker compose -f docker/docker-compose.yml up -d`.
- [ ] Lancer l'abonné / la détection : `.\make.bat detect`.
- [ ] Vérifier que les **vraies mesures de l'ESP32** arrivent (dans les logs et `data/sentinel.db`).

### B7. Test d'alerte réelle
- [ ] Déclencher le **PIR** (passer la main) → `presence = 1`.
- [ ] Approcher une source de gaz/fumée **inoffensive** du MQ-2 → la valeur `gas` monte.
- [ ] Vérifier qu'une alerte remonte (prédictif → API → dashboard).

✅ **ESP32 validé** si B4 (flash), B5 (OLED + série) et B6 (réception serveur) passent.

---

## 🧭 Ordre recommandé
1. **Webcam d'abord** (A1 → A6) — indépendante, rapide, aucun risque.
2. **ESP32 ensuite** (B0 → B7) — plus long (câblage + flash + broker TLS).

## 🧱 Dépendances connues
- La webcam ne dépend de **rien d'autre** (ni Docker ni broker).
- L'ESP32 en **MQTTS** dépend du **broker prod CYBER** (certs + passwd) → à coordonner avec le pôle CYBER.
- Le dashboard (A6, B6) nécessite l'**API** (`make.bat api`) + éventuellement **Docker** (broker).
