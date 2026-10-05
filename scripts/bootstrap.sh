#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  SENTINEL-X — Bootstrap COMPLET (prérequis système + environnement)
#  Pour une machine toute neuve. UNE seule commande :
#      bash scripts/bootstrap.sh
#  → installe Git, Python, Docker, make (ce qui manque), puis le venv
#    + les dépendances, puis vérifie que tout est OK.
# ═══════════════════════════════════════════════════════════════
set -e

echo "🛡️  SENTINEL-X — Bootstrap (prérequis + environnement)"
echo ""

OS="$(uname -s)"

# --- Prérequis système selon l'OS -------------------------------------------
install_macos() {
  # Homebrew (gestionnaire de paquets macOS)
  if ! command -v brew >/dev/null 2>&1; then
    echo "📥 Installation de Homebrew (peut demander ton mot de passe)…"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Charger brew dans le shell courant (Apple Silicon / Intel)
    [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"
    [ -x /usr/local/bin/brew ]    && eval "$(/usr/local/bin/brew shellenv)"
  fi
  command -v git >/dev/null 2>&1     || { echo "📦 git…";    brew install git; }
  command -v python3 >/dev/null 2>&1 || { echo "📦 python…"; brew install python; }
  command -v make >/dev/null 2>&1    || { echo "📦 make…";   brew install make; }
  if ! command -v docker >/dev/null 2>&1; then
    echo "📦 Docker Desktop…"
    brew install --cask docker || echo "⚠️  Installe Docker Desktop manuellement : https://www.docker.com/products/docker-desktop/"
    echo "⚠️  IMPORTANT : lance Docker Desktop une fois (icône) pour finaliser son installation."
  fi
}

install_linux() {
  if command -v apt-get >/dev/null 2>&1; then
    echo "📦 Installation via apt (peut demander ton mot de passe)…"
    sudo apt-get update -qq
    sudo apt-get install -y git python3 python3-venv python3-pip make docker.io docker-compose-plugin
    sudo usermod -aG docker "$USER" 2>/dev/null || true
    echo "ℹ️  Déconnecte/reconnecte-toi pour utiliser Docker sans sudo."
  else
    echo "⚠️  Distribution non-apt : installe git, python3, make et docker manuellement."
  fi
}

case "$OS" in
  Darwin) install_macos ;;
  Linux)  install_linux ;;
  *)      echo "⚠️  OS non géré auto ($OS). Installe git/python3/make/docker à la main, puis relance." ;;
esac

echo ""
echo "✅ Prérequis système traités."
echo "────────────────────────────────────────────────────"

# --- Environnement du projet -------------------------------------------------
# On réutilise la cible Makefile si make est là, sinon on fait les étapes à la main.
if command -v make >/dev/null 2>&1; then
  make install
else
  echo "📦 (sans make) venv + dépendances…"
  python3 -m venv venv
  venv/bin/pip install --quiet --upgrade pip
  venv/bin/pip install --quiet -r requirements.txt
  venv/bin/python scripts/check_env.py
fi

echo ""
echo "🎉 Bootstrap terminé ! Démo sans matériel :  make demo"
