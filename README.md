# 🛡️ SENTINEL-X — Workshop EPSI BAC+4

> **« Avant-Poste Industriel du Futur »** — Octobre 2026
> Système de surveillance intelligent **Edge-to-Server** : des capteurs embarqués (ESP8266) et une webcam alimentent une IA locale (vision + prédictif) qui lève des alertes temps réel vers un dashboard.

---

## 📂 Structure du projet

```
sentinel-x-ia/
├── README.md                 # Ce fichier
├── .gitignore
├── .env.example              # Modèle de configuration (copier en .env)
│
├── BRIQUES/                  # 📖 Documentation brique par brique
│   ├── BRIQUE0-Architecture.md         # Architecture technique complète
│   └── BRIQUE0-Architecture-GitHub.md  # ⭐ Specs d'équipe (À LIRE EN PRIORITÉ)
│
├── scripts/                  # 🐍 Code Python des briques (Vision, Prédictif, MQTT…)
├── docker/                   # 🐳 Mosquitto MQTT (docker-compose.yml)
├── security/                 # 🔒 Certificats TLS, règles pare-feu (CYBER)
├── data/                     # 🗄️ Données locales, sentinel.db (ignoré par Git)
└── docs/                     # 📚 Documentation additionnelle
```

---

## 🚦 Lire en PRIORITÉ

👉 **[`BRIQUES/BRIQUE0-Architecture-GitHub.md`](BRIQUES/BRIQUE0-Architecture-GitHub.md)**

Ce document contient **les specs par rôle** (DEV, CYBER, IA/DATA) pour que **chacun puisse démarrer lundi sans attendre les autres**.

---

## ▶️ Comment commencer

1. **Cloner** le repo et créer sa config locale :
   ```bash
   git clone https://github.com/<username>/sentinel-x-ia.git
   cd sentinel-x-ia
   cp .env.example .env   # puis remplir les valeurs
   ```
2. **Lire** sa section dans `BRIQUES/BRIQUE0-Architecture-GitHub.md`.
3. **Lundi matin :** une fois la Brique 0 validée avec les coachs → **Brique 1 (Setup Python)**.

---

## 👥 Équipe

| Rôle | Responsabilité |
|---|---|
| **DEV** | Firmware ESP8266, API REST, Dashboard Web, contrôle réactif |
| **CYBER** | TLS/MQTTS, pare-feu, SSH hardening, pentest |
| **IA/DATA #1** | 👁️ Vision IA (YOLOv8) — *moi, macOS* |
| **IA/DATA #2** | 📈 Prédictif (Isolation Forest) + données |
| **IA/DATA #3** | 🐳 Infra Docker/MQTT + tests d'intégration |

---

## 🧰 Stack technique

| Domaine | Techno |
|---|---|
| Microcontrôleur | **ESP8266** (WiFi) |
| Capteurs | DHT22 (temp/humidité), MQ-2 (gaz), PIR HC-SR501 (présence) |
| Serveur local | **PC Windows** (héberge Mosquitto, API, SQLite, IA) |
| Vision | **Python** + OpenCV + **YOLOv8n** (Ultralytics) |
| Prédictif | **scikit-learn** — Isolation Forest |
| Messagerie | **MQTT** — Mosquitto via **Docker** (`1883` / `8883` TLS) |
| Base de données | **SQLite** (`sentinel.db`) |
| API | REST — `POST http://localhost:3000/api/v1/alerts` |
| Dashboard | Web (DEV) |

---

## 🔐 Important — secrets & `.env`

- **Jamais** de secret en clair dans Git. Le vrai `.env` est **ignoré** (voir `.gitignore`).
- `/.env.example` montre **la structure** attendue (sans vraie valeur sensible).
- Chaque membre copie `.env.example` → `.env` et remplit ses propres valeurs.

---

## 📜 Licence & notes

Projet pédagogique — **Workshop EPSI 2026**. Usage interne à l'équipe et aux coachs EPSI.

---

## 🚀 Prochaine étape

**Lundi matin** (après BRIQUE 0 validée avec les coachs) :
→ **BRIQUE 1 : Setup Python + `requirements.txt`**
