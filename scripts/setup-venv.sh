#!/bin/bash
# ───────────────────────────────────────────────
# SENTINEL-X — Setup Python automatisé (macOS / Linux)
# Usage : bash scripts/setup-venv.sh   (depuis la racine du projet)
# ───────────────────────────────────────────────
set -e

echo "🛡️ SENTINEL-X — Setup Python Automatisé"
echo ""

# 1. Vérifier que Python3 est installé
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 non trouvé. Installe Python 3.9+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Python $PYTHON_VERSION détecté"

# 2. Créer le virtual environment s'il n'existe pas
if [ ! -d "venv" ]; then
    echo "📦 Création du virtual environment..."
    python3 -m venv venv
else
    echo "✅ Virtual environment existe déjà"
fi

# 3. Activer le venv
source venv/bin/activate

# 4. Mettre à jour pip
echo "📥 Upgrade pip..."
pip install --upgrade pip

# 5. Installer les dépendances
echo "📦 Installation des dépendances..."
pip install -r requirements.txt

# 6. Vérification rapide des imports critiques
echo "🔍 Vérification des imports..."
python -c "import cv2, ultralytics, sklearn, paho.mqtt.client, dotenv; print('✅ Imports OK')"

echo ""
echo "✅ Setup terminé !"
echo ""
echo "Pour activer le venv :"
echo "   source venv/bin/activate"
echo ""
echo "Pour désactiver :"
echo "   deactivate"
