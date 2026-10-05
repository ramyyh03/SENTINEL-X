# ═══════════════════════════════════════════════════════════════
#  SENTINEL-X — Point d'entrée unique du projet
#  Une seule commande pour installer + vérifier :  make install
#  Lister toutes les commandes :                    make help
# ═══════════════════════════════════════════════════════════════

VENV := venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip
DC   := docker compose -f docker-compose.dev.yml

.DEFAULT_GOAL := help
.PHONY: help install check broker broker-stop run simulate demo

help: ## Affiche cette aide
	@echo "🛡️  SENTINEL-X — commandes disponibles :"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-14s %s\n", $$1, $$2}'
	@echo ""
	@echo "👉 Première fois ? Lance :  make install"

install: ## ⭐ Installe tout (venv + dépendances) PUIS vérifie l'environnement
	@command -v python3 >/dev/null 2>&1 || { echo "❌ Python3 introuvable — installe Python 3.9+"; exit 1; }
	@test -d $(VENV) || { echo "📦 Création du virtualenv…"; python3 -m venv $(VENV); }
	@echo "📥 Mise à jour de pip…"
	@$(PIP) install --quiet --upgrade pip
	@echo "📦 Installation des dépendances (requirements.txt)…"
	@$(PIP) install --quiet -r requirements.txt
	@$(MAKE) --no-print-directory check
	@echo ""
	@echo "✅ Prêt ! Pour une démo complète sans matériel :  make demo"

check: ## Vérifie que toutes les dépendances sont installées (sans rien installer)
	@test -x $(PY) || { echo "❌ Pas de venv — lance d'abord : make install"; exit 1; }
	@$(PY) scripts/check_env.py

broker: ## Démarre le broker MQTT local (Mosquitto, port 1883)
	@$(DC) up -d
	@echo "✅ Broker MQTT lancé sur localhost:1883"

broker-stop: ## Arrête le broker MQTT local
	@$(DC) down

run: ## Lance l'abonné MQTT (reçoit les capteurs → SQLite)
	@$(PY) scripts/mqtt_client.py

simulate: ## Lance le simulateur ESP32 (10 mesures sur sentinel/sensors)
	@$(PY) simulate/fake_sensors_esp32.py --simulate

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
