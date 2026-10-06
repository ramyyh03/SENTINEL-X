"""BRIQUE 6 — Prévision ARIMA (OPTIONNEL, mode batch).

Entraîne un petit modèle ARIMA par capteur sur l'historique synthétique et prédit
quelques pas à l'avance ; une mesure qui s'écarte de > 3σ de la prévision est
suspecte. Désactivé par défaut (`ARIMA_ENABLED=false`) et import protégé :
`statsmodels` n'est PAS une dépendance obligatoire du projet.

⚠️ À utiliser avec prudence en workshop (données encore peu fiables).
"""
from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARIMA_DIR = PROJECT_ROOT / "models" / "arima_models"
CAPTEURS = ("temp", "humidity", "gas")
ORDER = (2, 1, 2)  # (p, d, q) raisonnable pour une série lissée


def disponible() -> bool:
    """True si statsmodels est installé (ARIMA utilisable)."""
    try:
        import statsmodels.tsa.arima.model  # noqa: F401
        return True
    except ImportError:
        return False


def entrainer(csv_path: Path | None = None) -> dict:
    """Entraîne un ARIMA par capteur et sauvegarde les modèles. Retourne un statut."""
    if not disponible():
        return {"status": "skipped", "raison": "statsmodels non installé (pip install statsmodels)"}

    from statsmodels.tsa.arima.model import ARIMA

    csv = csv_path or (PROJECT_ROOT / "data" / "training_data.csv")
    df = pd.read_csv(csv)
    ARIMA_DIR.mkdir(parents=True, exist_ok=True)

    entraines = []
    for capteur in CAPTEURS:
        try:
            modele = ARIMA(df[capteur].astype(float), order=ORDER).fit()
            with open(ARIMA_DIR / f"arima_{capteur}.pkl", "wb") as fh:
                pickle.dump(modele, fh)
            entraines.append(capteur)
        except Exception as exc:  # ARIMA peut diverger : on n'interrompt pas le pipeline
            print(f"[ARIMA][WARN] {capteur} : {exc}")

    return {"status": "ok", "modeles": entraines}


if __name__ == "__main__":
    print(entrainer())
