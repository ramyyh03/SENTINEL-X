"""SENTINEL-X — Application de bureau (fenêtre unique).

Lance tout le système en arrière-plan, attend que l'API réponde, puis ouvre
une FENÊTRE d'application (pas un navigateur) affichant le cockpit : l'analyse
de connectivité en direct (API, broker, ESP32, détection IA, Ollama/Mistral)
et les pages web embarquées (alertes, capteurs, caméra, sécurité).

Usage :
    python -m app.sentinel_app        # ou :  make app  /  make.bat app

Si la fenêtre native (pywebview) n'est pas disponible, on bascule proprement
sur le navigateur (comportement de scripts/launch_all.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Profil webview NEUF à chaque lancement : empêche Edge WebView2 de garder
# l'ancienne interface en cache (sinon la fenêtre affiche une vieille version).
import os as _os          # noqa: E402
import tempfile as _tmp   # noqa: E402
_os.environ["WEBVIEW2_USER_DATA_FOLDER"] = _tmp.mkdtemp(prefix="sentinel_webview_")

from scripts import launch_all as L  # noqa: E402


def _demarrer_backend() -> bool:
    """Démarre broker + services en arrière-plan. Retourne True si l'API répond."""
    print("SENTINEL-X — démarrage du système…")
    L.demarrer_broker()
    L.demarrer_services()
    return L.attendre_api()


def main() -> int:
    """Lance le backend puis ouvre la fenêtre d'application (ou le navigateur)."""
    api_ok = _demarrer_backend()
    ollama_ok = L.ollama_pret()

    try:
        import webview  # fenêtre native (Edge WebView2 / WebKit)
    except ImportError:
        print("[INFO] pywebview absent → ouverture dans le navigateur.")
        print("       Installer la fenêtre native : pip install pywebview")
        if api_ok:
            import webbrowser
            webbrowser.open(L.URL_COCKPIT)
        L._rapport(True, api_ok, ollama_ok)
        return 0 if api_ok else 1

    if not api_ok:
        print("[ERREUR] L'API n'a pas démarré — voir logs/api.log")
        L._rapport(True, False, ollama_ok)
        return 1

    L._rapport(True, api_ok, ollama_ok)
    # Anti-cache : URL unique à chaque ouverture -> la fenêtre charge TOUJOURS la
    # dernière interface (sinon Edge WebView2 garde l'ancienne version en cache).
    import time as _t
    url = f"{L.URL_COCKPIT}?v={int(_t.time())}"
    webview.create_window("SENTINEL-X", url, width=1280, height=840)
    try:
        webview.start(private_mode=True)  # profil temporaire : pas de cache persistant
    except TypeError:
        webview.start()                   # anciennes versions de pywebview
    L.arreter()                           # arrêt propre du système à la fermeture
    return 0


if __name__ == "__main__":
    sys.exit(main())
