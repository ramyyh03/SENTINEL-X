# BRIQUE 1 : Setup Python + Virtual Environment

> **SENTINEL-X — Workshop EPSI BAC+4**
> Objectif : que **chaque membre IA/DATA** ait le même environnement Python, reproductible sur **macOS et Windows**.

---

## 🎯 Vue d'ensemble (30 secondes)

On crée un **environnement virtuel** (`venv`) isolé et on y installe **toutes** les dépendances du projet (Vision, Prédictif, MQTT, utilitaires) depuis `requirements.txt`. Résultat : tout le monde a **exactement les mêmes versions**, et le `venv` reste local (il est ignoré par Git). Une fois fait, on peut lancer n'importe quelle brique.

---

## ✅ Prérequis

| Élément | Vérification |
|---|---|
| **Python 3.9+** (recommandé 3.11) | `python3 --version` |
| **Repo cloné** | `git clone https://github.com/ramyyh03/SENTINEL-X.git` |
| **Terminal à la racine** du projet | `cd ~/SENTINEL-X/sentinel-x-ia` |

---

## ⚙️ Étapes de setup (copie-colle)

### macOS / Linux

```bash
cd ~/SENTINEL-X/sentinel-x-ia

# 1. Créer le virtual environment
python3 -m venv venv

# 2. Activer le venv
source venv/bin/activate

# 3. Mettre à jour pip
pip install --upgrade pip

# 4. Installer les dépendances
pip install -r requirements.txt

# 5. Vérifier les imports critiques
python -c "import cv2, ultralytics, sklearn; print('✅ OK')"

# 6. Créer sa config locale
cp .env.example .env
```

### Windows (PowerShell)

```powershell
cd $HOME\SENTINEL-X\sentinel-x-ia

# 1. Créer le virtual environment
python -m venv venv

# 2. Activer le venv
.\venv\Scripts\activate

# 3. Mettre à jour pip
pip install --upgrade pip

# 4. Installer les dépendances
pip install -r requirements.txt

# 5. Vérifier les imports critiques
python -c "import cv2, ultralytics, sklearn; print('✅ OK')"

# 6. Créer sa config locale
copy .env.example .env
```

> 💡 **Automatisation (macOS/Linux) :** au lieu des étapes 1→4, tu peux lancer
> `bash scripts/setup-venv.sh` qui fait tout d'un coup.

---

## 🧯 Troubleshooting

| Problème | Cause probable | Solution |
|---|---|---|
| **`ModuleNotFoundError: cv2`** | Le `venv` n'est pas activé | Relance `source venv/bin/activate` (macOS) / `.\venv\Scripts\activate` (Windows), puis réinstalle |
| **`pip: command not found`** | pip absent du PATH | Utilise `python3 -m pip install ...` à la place de `pip` |
| **`Permission denied`** | Install système sans droits | **Ne jamais** `sudo pip`. Toujours passer par le `venv` (il n'a pas besoin de sudo) |
| **Installation très lente** | ultralytics + torch sont lourds | Normal au 1er run (plusieurs centaines de Mo). Laisse tourner ; mets à jour pip d'abord |
| **`error: externally-managed-environment`** | pip bloqué hors venv (Python système récent) | Tu as oublié d'activer le `venv`. Active-le, l'erreur disparaît |
| **`torch` échoue sur Apple Silicon** | roue CPU/arm64 | Laisse pip choisir la version CPU (suffisant pour YOLOv8n en 640×480) |
| **`.\venv\Scripts\activate` bloqué (Windows)** | politique d'exécution PowerShell | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` puis réessaie |

---

## 🔍 Vérification finale

Enregistre ce script en `scripts/check_env.py` et lance-le (`python scripts/check_env.py`) pour valider **tous** les packages :

```python
"""Vérifie que toutes les dépendances SENTINEL-X sont installées."""
import importlib
import sys

# Nom d'import → nom pip (pour message clair)
PACKAGES = {
    "cv2": "opencv-python",
    "ultralytics": "ultralytics",
    "PIL": "pillow",
    "sklearn": "scikit-learn",
    "pandas": "pandas",
    "numpy": "numpy",
    "scipy": "scipy",
    "paho.mqtt.client": "paho-mqtt",
    "requests": "requests",
    "dotenv": "python-dotenv",
    "yaml": "pyyaml",
    "colorama": "colorama",
}

ok, manquants = [], []
for module, pip_name in PACKAGES.items():
    try:
        importlib.import_module(module)
        ok.append(pip_name)
    except ImportError:
        manquants.append(pip_name)

print(f"Python {sys.version.split()[0]}")
print(f"✅ Installés ({len(ok)}): {', '.join(ok)}")
if manquants:
    print(f"❌ Manquants ({len(manquants)}): {', '.join(manquants)}")
    print("   → pip install -r requirements.txt")
    sys.exit(1)
print("🛡️  Environnement SENTINEL-X prêt !")
```

Sortie attendue : `🛡️ Environnement SENTINEL-X prêt !`

---

## 🚀 Prochaine étape

Une fois la branche `feature-setup` **reviewée et mergée dans `main`** (lundi), tout le monde exécute le setup ci-dessus. Puis, mardi :

| Brique | Qui |
|---|---|
| **BRIQUE 2** — Docker MQTT | W1 (Windows) |
| **BRIQUE 3** — MQTT Client | W1 / W2 |
| **BRIQUE 4** — Webcam Capture | Moi (macOS) |

---

## 📘 Ce que j'ai fait — Brique 1 (Setup Python)

**En une phrase :** j'ai créé l'environnement Python **unifié et reproductible** du projet.

**Pourquoi ce choix technique :** un `venv` + `requirements.txt` versionné garantit que les 3 personnes IA ont les **mêmes versions** de chaque lib (fini le « ça marche chez moi »). Les versions sont épinglées en `>=` pour laisser pip résoudre les compatibilités tout en fixant un plancher testé.

**Comment ça s'intègre dans SENTINEL-X :** c'est le socle de **toutes** les briques suivantes — Vision (`opencv`/`ultralytics`), Prédictif (`scikit-learn`/`pandas`), MQTT (`paho-mqtt`), config (`python-dotenv`). Sans cette brique, rien ne tourne.

**Pour tester sans matériel :** `python scripts/check_env.py` valide l'installation **sans** webcam ni ESP8266 — juste les imports.
