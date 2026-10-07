# ═══════════════════════════════════════════════════════════════
#  SENTINEL-X — Point d'entrée unique du projet
#  Une seule commande pour installer + vérifier :  make install
#  Lister toutes les commandes :                    make help
# ═══════════════════════════════════════════════════════════════

VENV := venv
# Chemins adaptés à l'OS : Windows = venv/Scripts (lancer depuis Git Bash),
# Unix (macOS/Linux) = venv/bin. OS=Windows_NT est défini par make sous Windows.
ifeq ($(OS),Windows_NT)
  PYTHON := python
  PY     := $(VENV)/Scripts/python
else
  PYTHON := python3
  PY     := $(VENV)/bin/python
endif
PIP := $(PY) -m pip
DC  := docker compose -f docker-compose.dev.yml

.DEFAULT_GOAL := help
.PHONY: help bootstrap install check test test-full test-unit test-materiel check-materiel monitor-esp32 config-esp32 setup-2fa reset-db train-ensemble test-ensemble ollama-check run-all broker broker-stop run simulate demo train detect replay detect-vision detect-vision-sim detect-vision-show api api-stop api-logs

bootstrap: ## 🧰 Machine neuve : installe les prérequis SYSTÈME (Python, Docker…) PUIS install
	@bash scripts/bootstrap.sh

help: ## Affiche cette aide
	@echo "🛡️  SENTINEL-X — commandes disponibles :"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-14s %s\n", $$1, $$2}'
	@echo ""
	@echo "👉 Première fois ? Lance :  make install"

install: ## ⭐ Setup complet : Python, venv, deps, Docker, dossiers, .env
	@echo "SENTINEL-X - Installation"
	@command -v $(PYTHON) >/dev/null 2>&1 || { echo "[X] $(PYTHON) introuvable - installe Python 3.8+"; exit 1; }
	@$(PYTHON) -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" \
		|| { echo "[X] Python 3.8+ requis (detecte : $$($(PYTHON) -V))"; exit 1; }
	@echo "[OK] $$($(PYTHON) -V)"
	@test -d $(VENV) || { echo "Creation du virtualenv..."; $(PYTHON) -m venv $(VENV); }
	@echo "pip + dependances (requirements.txt)..."
	@$(PIP) install --quiet --upgrade pip
	@$(PIP) install -r requirements.txt
	@command -v docker >/dev/null 2>&1 && echo "[OK] Docker detecte" \
		|| echo "[!] Docker absent - requis pour MQTT et make test-full"
	@mkdir -p data logs models && echo "[OK] Dossiers data/ logs/ models/ prets"
	@test -f .env && echo "[OK] .env deja present" \
		|| { cp .env.example .env && echo "[OK] .env cree depuis .env.example"; }
	@$(MAKE) --no-print-directory check
	@echo ""
	@echo "SETUP COMPLETE - etape suivante :  make test-full"

check: ## Vérifie que toutes les dépendances sont installées (sans rien installer)
	@test -x $(PY) || { echo "❌ Pas de venv — lance d'abord : make install"; exit 1; }
	@$(PY) scripts/check_env.py

test: ## 🩺 Rapport de santé rapide (deps, briques 3/5/6/7, firmware, sécu) — in-process
	@test -x $(PY) || { echo "❌ Pas de venv — lance d'abord : make install"; exit 1; }
	@$(PY) scripts/healthcheck.py

test-unit: ## 🧫 Tests unitaires pytest (ex. santé capteurs, Brique 6.2)
	@$(PY) -m pytest tests/ -q

test-full: ## 🧪 Test d'INTÉGRATION complet : démarre broker+API, teste la chaîne E2E réelle
	@test -x $(PY) || { echo "❌ Pas de venv — lance d'abord : make install"; exit 1; }
	@$(PY) scripts/test_full_integration.py

broker: ## Démarre le broker MQTT local (Mosquitto, port 1883)
	@$(DC) up -d
	@echo "✅ Broker MQTT lancé sur localhost:1883"

broker-stop: ## Arrête le broker MQTT local
	@$(DC) down

run: ## Lance le système : API (arrière-plan) + abonné MQTT (capteurs → SQLite)
	@$(MAKE) --no-print-directory api
	@echo "— Abonné MQTT (Ctrl+C pour arrêter ; l'API reste up → 'make api-stop') —"
	@$(PY) scripts/mqtt_client.py

api: ## 🌐 BRIQUE 7 : lance le serveur API (port 3000) en arrière-plan
	@test -x $(PY) || { echo "❌ venv manquant — make install"; exit 1; }
	@mkdir -p logs
	@$(PY) -m api.server > logs/api.log 2>&1 & echo $$! > logs/api.pid
	@echo "✅ API lancée (PID $$(cat logs/api.pid)) → http://localhost:3000/dashboard"

api-stop: ## 🌐 BRIQUE 7 : arrête le serveur API
	@kill `cat logs/api.pid 2>/dev/null` 2>/dev/null && rm -f logs/api.pid && echo "✅ API arrêtée" || echo "ℹ️ API non lancée"

api-logs: ## 🌐 BRIQUE 7 : affiche les logs de l'API en continu
	@tail -f logs/api.log

simulate: ## Lance le simulateur ESP32 (10 mesures sur sentinel/sensors)
	@$(PY) simulate/fake_sensors_esp32.py --simulate

config-esp32: ## 📝 Prépare secrets.h de l'ESP32 (IP auto) et l'ouvre
	@$(PY) scripts/config_esp32.py

setup-2fa: ## 🔐 Crée un compte dashboard protégé par mot de passe + 2FA (Authenticator)
	@$(PY) scripts/setup_2fa.py

reset-db: ## 🧹 Vide la base (enlève les données synthétiques → que du réel ensuite)
	@$(PY) scripts/reset_db.py

run-all: ## 🚀 Lance tout en arrière-plan (broker + API + ingestion + détection)
	@mkdir -p logs
	@$(DC) up -d
	@$(PY) -m api.server > logs/api.log 2>&1 & echo $$! > logs/api.pid
	@$(PY) scripts/mqtt_client.py > logs/ingest.log 2>&1 & echo $$! > logs/ingest.pid
	@$(PY) -m predictive.main_brique6 detect > logs/detect.log 2>&1 & echo $$! > logs/detect.pid
	@echo "✅ Système lancé. Dashboard : http://localhost:3000/dashboard"
	@echo "   Capteurs : /live · Caméra : /camera (lance la vision à part : make detect-vision)"
	@echo "   Arrêt : make api-stop broker-stop ; kill via logs/*.pid"

train-ensemble: ## 🧠🔥 BRIQUE 6.3 : entraine l'ensemble hybride (IF+LOF+ECOD+GB) + metriques
	@$(PY) scripts/train_ensemble.py

ollama-check: ## 🤖 Vérifie si Ollama tourne (diagnostic IA du dashboard)
	@$(PY) scripts/ollama_health_check.py

test-ensemble: ## 🧫 Tests de l'ensemble 6.3
	@$(PY) -m pytest tests/test_ensemble.py -q

train: ## 🧠 BRIQUE 6 : génère les données + entraîne Forest/LOF + évalue
	@test -x $(PY) || { echo "❌ Pas de venv — lance d'abord : make install"; exit 1; }
	@$(PY) -m predictive.main_brique6 train

detect: ## 🔎 BRIQUE 6 : détection d'anomalies en temps réel sur data/sentinel.db
	@$(PY) -m predictive.main_brique6 detect

replay: ## 🔁 BRIQUE 6 : rejoue le dataset synthétique (test IA sans DB ni broker)
	@$(PY) -m predictive.main_brique6 replay

check-materiel: ## 🔌 Vérifie RAPIDEMENT que le matériel est branché (webcam + ESP32)
	@$(PY) scripts/test_materiel.py --scan

monitor-esp32: ## 📟 Lit le port série de l'ESP32 : voir les mesures capteurs en direct
	@$(PY) scripts/esp32_monitor.py

test-materiel: ## 📷 Test matériel COMPLET : webcam + YOLO + ESP32 → RAPPORT-MATERIEL.md
	@$(PY) scripts/test_materiel.py

detect-vision: ## 👁️ BRIQUE 5 : détection de personnes (webcam réelle) → alertes
	@$(PY) -m vision.detector

detect-vision-sim: ## 👁️ BRIQUE 5 : détection en mode SIMULATION (sans webcam)
	@$(PY) -m vision.detector --simulate

detect-vision-show: ## 👁️ BRIQUE 5 : détection avec affichage OpenCV (debug)
	@$(PY) -m vision.detector --show

demo: ## 🚀 Démo complète sans matériel : broker + simulateur + persistance SQLite
	@test -x $(PY) || { echo "❌ Pas de venv — lance d'abord : make install"; exit 1; }
	@$(DC) up -d
	@$(PY) -c "import time; time.sleep(3)"   # laisser le broker démarrer
	@$(PY) scripts/mqtt_client.py > /tmp/sentinel_demo.log 2>&1 & echo $$! > /tmp/sentinel_demo.pid
	@$(PY) -c "import time; time.sleep(2)"
	@$(PY) simulate/fake_sensors_esp32.py --simulate
	@$(PY) -c "import time; time.sleep(1)"
	@kill `cat /tmp/sentinel_demo.pid` 2>/dev/null || true
	@echo "--- Dernières lignes stockées en base ---"
	@sqlite3 -header -column data/sentinel.db "SELECT id,temp,humidity,gas,presence FROM sensor_data ORDER BY id DESC LIMIT 5;" 2>/dev/null || echo "(installe sqlite3 pour voir la base)"
	@$(DC) down
	@echo "✅ Démo terminée — chaîne MQTT → SQLite validée."
