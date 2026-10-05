"""Vérifie que toutes les dépendances SENTINEL-X sont installées.

Usage :
    python scripts/check_env.py

Ne nécessite NI webcam NI ESP8266 : teste uniquement les imports.
"""
import importlib
import sys

# Nom d'import Python → nom du paquet pip (pour un message d'erreur clair)
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


def main() -> int:
    """Teste chaque import et affiche un rapport. Retourne un code de sortie."""
    installes, manquants = [], []

    for module, pip_name in PACKAGES.items():
        try:
            importlib.import_module(module)
            installes.append(pip_name)
        except ImportError:
            manquants.append(pip_name)

    print(f"Python {sys.version.split()[0]}")
    print(f"✅ Installés ({len(installes)}): {', '.join(installes)}")

    if manquants:
        print(f"❌ Manquants ({len(manquants)}): {', '.join(manquants)}")
        print("   → pip install -r requirements.txt")
        return 1

    print("🛡️  Environnement SENTINEL-X prêt !")
    return 0


if __name__ == "__main__":
    sys.exit(main())
