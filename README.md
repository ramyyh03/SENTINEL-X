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

### 🚀 Machine toute neuve → UNE seule commande

Tu n'as **rien** d'installé (ni Python, ni Docker) ? Après avoir cloné, lance :

```bash
git clone https://github.com/ramyyh03/SENTINEL-X.git
cd SENTINEL-X
bash scripts/bootstrap.sh
```

> Cette commande **installe les prérequis système** (Git, Python, Docker, make — ce qui manque, via Homebrew sur macOS / apt sur Linux), **PUIS** crée le venv, installe les dépendances et **vérifie que tout est bon**. Un seul passage.
> ⚠️ macOS : après coup, **ouvre Docker Desktop une fois** pour finaliser son installation.

### ⚡ Tu as déjà Python + Docker ?

```bash
git clone https://github.com/ramyyh03/SENTINEL-X.git
cd SENTINEL-X
cp .env.example .env   # (optionnel en dev : valeurs par défaut = localhost:1883)
make install           # venv + dépendances + vérification
```

Ensuite, **lis ta section** dans `BRIQUES/BRIQUE0-Architecture-GitHub.md`.

### 🧰 Les autres commandes (`make help`)

| Commande | Rôle |
|---|---|
| `bash scripts/bootstrap.sh` (ou `make bootstrap`) | 🧰 **Machine neuve** : prérequis système (Python/Docker…) **+** tout le reste |
| `make install` | ⭐ Installe tout (venv + deps) **et** vérifie l'environnement |
| `make check` | Vérifie les dépendances **sans rien installer** |
| `make demo` | 🚀 Démo complète **sans matériel** (broker + simulateur + SQLite) |
| `make broker` / `make broker-stop` | Démarre / arrête le broker MQTT local |
| `make run` | Lance l'abonné MQTT (reçoit les capteurs → SQLite) |
| `make simulate` | Lance le simulateur ESP32 (10 mesures) |
| `make help` | Liste toutes les commandes |

> 🪟 **Windows (sans `make`)** : lancer à la place `bash scripts/setup-venv.sh` (Git Bash) ou, en PowerShell, `python -m venv venv ; venv\Scripts\pip install -r requirements.txt ; venv\Scripts\python scripts\check_env.py`.

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
