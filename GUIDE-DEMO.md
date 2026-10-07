# 🚀 SENTINEL-X — Guide de démo PAS À PAS (local, privé, sécurisé)

> Signé rami yahyaoui · tout en local, **sans cloud, sans budget**.
> Réseau : **ton hotspot privé** (PAS le WiFi du campus/eduroam → isolation des appareils).

---

## PHASE 0 — Une seule fois (si pas déjà fait)
```powershell
cd C:\workshop\SENTINEL-X
git pull
.\make.bat install      # venv + dépendances + dossiers + .env
```
+ **Docker Desktop lancé** (icône baleine « running »).

---

## PHASE 1 — Réseau privé 📶
1. Active le **partage de connexion** du téléphone (« Don't use AI man ») — ou un mini-routeur.
2. Connecte le **PC** à ce réseau.
3. Connecte-y aussi l'**ESP32** (fait à la phase 2) et plus tard les **appareils du jury**.

> ⚠️ **Pas le WiFi du campus** : eduroam isole les appareils → l'ESP32 ne pourrait pas joindre le PC.

---

## PHASE 2 — Config de l'ESP32 (SANS téléphone) 🔌
*(sur l'ordi où l'ESP32 est branché en USB, connecté au hotspot)*
```powershell
cd C:\workshop\SENTINEL-X
.\make.bat config-esp32
```
→ détecte l'IP du PC, crée `secrets.h` (IP déjà remplie) et l'ouvre. Remplis :
```c
#define WIFI_SSID     "Don't use AI man"
#define WIFI_PASSWORD "le_mot_de_passe_du_hotspot"
```
Enregistre, ferme, puis flashe :
```powershell
cd firmware
..\venv\Scripts\python -m platformio run -e esp32dev-secrets -t erase
..\venv\Scripts\python -m platformio run -e esp32dev-secrets -t upload
```
Vérifie :
```powershell
cd C:\workshop\SENTINEL-X
venv\Scripts\python scripts\esp32_monitor.py --seconds 30
```
✅ attendu : `WiFi OK (secrets) - IP ... | broker 192.168.43.XX:1883` + `MQTT connecte (dev, sans TLS)` + `T=.. Gaz=.. PIR=1`

---

## PHASE 3 — Compte(s) dashboard avec 2FA 🔐
```powershell
.\make.bat setup-2fa          # identifiant + mot de passe → QR code
```
→ scanne le QR dans **Microsoft Authenticator**. (Refais-le pour **chaque** personne/juré.)

---

## PHASE 4 — Tout lancer 🚀
```powershell
.\make.bat reset-db           # (1re fois) enlève les données de test
.\make.bat run-all            # broker + API + ingestion + détection + vision
```

---

## PHASE 5 — Regarder 👀
- **http://localhost:3000/live** → mesures ESP32 en direct (T/H/Gaz/Présence)
- **http://localhost:3000/camera** → webcam + détection de personnes
- **http://localhost:3000/dashboard** → alertes
*(login + 2FA demandés dès qu'un compte existe)*

---

## PHASE 6 — Accès du jury 👩‍⚖️
1. Dans `.env` : **`API_HOST=0.0.0.0`** (expose sur le réseau).
2. Autorise le **port 3000** dans le **pare-feu Windows** (clique « Autoriser » à l'alerte).
3. Crée un compte par juré : `.\make.bat setup-2fa` → donne-lui son QR.
4. Le jury rejoint **ton hotspot** (donne le mot de passe WiFi), puis ouvre :
   **`http://192.168.43.45:3000/login`** *(ton IP PC — vois-la avec `ipconfig`)*
   → identifiant + mot de passe + code 6 chiffres → dashboard en **lecture seule**.

---

## 🔒 Récap sécurité (ce qui te protège)
| Couche | Protection |
|---|---|
| Réseau | **Privé** (hotspot avec mot de passe) → pas d'inconnus |
| Dashboard | **Login + 2FA** (Authenticator) |
| Accès | **Admin** : tu crées/supprimes les comptes |
| Rôle viewers | **Lecture seule** (aucune action possible) |
| MQTT (bonus) | **MQTTS 8883 + TLS** à activer avec le CYBER pour la sécu max |

## 🧯 Si ça coince
- `/live` vide → l'ESP32 ne publie pas : `esp32_monitor.py` doit montrer `MQTT connecte (dev)`.
- Jury ne voit pas le site → `API_HOST=0.0.0.0` + pare-feu port 3000 + même WiFi.
- Tout arrêter → ferme les fenêtres (Ctrl+C) + `.\make.bat broker-stop`.
