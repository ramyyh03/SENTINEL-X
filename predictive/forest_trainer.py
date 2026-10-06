"""BRIQUE 6 — Entraînement de l'ensemble Isolation Forest + LOF.

- Isolation Forest : détecte les aberrances GLOBALES, efficace en haute dimension.
- Local Outlier Factor (LOF, novelty=True) : détecte les anomalies LOCALES (densité),
  complément du Forest.
Les deux sont combinés par vote/moyenne (voir scoring.py).

Artefacts produits :
    models/isolation_forest.pkl, models/lof_model.pkl, models/scaler.pkl
    models/forest_metadata.json   (features, bornes de score, seuil, version, date)
"""
from __future__ import annotations

import json
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

from predictive import scoring
from predictive.feature_engineer import FEATURE_COLUMNS, construire_features

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

MODELS_DIR = PROJECT_ROOT / "models"
DATA_CSV = PROJECT_ROOT / "data" / "training_data.csv"
METADATA_PATH = MODELS_DIR / "forest_metadata.json"
MODEL_VERSION = "1.0"

N_ESTIMATORS = 100
RANDOM_STATE = 42


def _config() -> dict:
    """Lit la config d'entraînement depuis l'environnement (valeurs par défaut sûres)."""
    return {
        "contamination": float(os.getenv("FOREST_CONTAMINATION", "0.1")),
        "threshold": float(os.getenv("FOREST_THRESHOLD", "0.4")),
        "lof_neighbors": int(os.getenv("LOF_NEIGHBORS", "20")),
    }


def entrainer(csv_path: Path | None = None) -> dict:
    """Entraîne Forest + LOF sur le CSV synthétique et sauvegarde tous les artefacts.

    Retourne un dict {labels, scores_ensemble, metadata} pour l'évaluation.
    """
    cfg = _config()
    df = pd.read_csv(csv_path or DATA_CSV)
    labels = df["anomaly_label"].to_numpy() if "anomaly_label" in df else None

    features = construire_features(df)
    scaler = StandardScaler()
    X = scaler.fit_transform(features.to_numpy())

    # --- Modèle 1 : Isolation Forest ---
    forest = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=cfg["contamination"],
        max_samples="auto",
        random_state=RANDOM_STATE,
    ).fit(X)

    # --- Modèle 2 : LOF en mode "novelty" (permet de prédire de NOUVELLES lectures) ---
    lof = LocalOutlierFactor(
        n_neighbors=cfg["lof_neighbors"],
        contamination=cfg["contamination"],
        novelty=True,
    ).fit(X)

    # Calibration des scores (frontière de décision centrée sur 0.5)
    forest_raw = scoring.scores_bruts(forest, X)
    lof_raw = scoring.scores_bruts(lof, X)
    f_norm, f_anom = scoring.calibrer(forest_raw)
    l_norm, l_anom = scoring.calibrer(lof_raw)
    bornes = {
        "forest_ech_norm": f_norm, "forest_ech_anom": f_anom,
        "lof_ech_norm": l_norm, "lof_ech_anom": l_anom,
    }

    # Score ensemble sur le jeu d'entraînement (pour les métriques)
    forest_u = scoring.vers_unite(forest_raw, f_norm, f_anom)
    lof_u = scoring.vers_unite(lof_raw, l_norm, l_anom)
    scores_ens = scoring.ensemble(forest_u, lof_u)

    metadata = {
        "version": MODEL_VERSION,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "features": FEATURE_COLUMNS,
        "n_features": len(FEATURE_COLUMNS),
        "contamination": cfg["contamination"],
        "threshold": cfg["threshold"],
        "lof_neighbors": cfg["lof_neighbors"],
        "score_bounds": bornes,
        "n_samples": int(len(df)),
    }

    # --- Sauvegarde ---
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODELS_DIR / "isolation_forest.pkl", "wb") as fh:
        pickle.dump(forest, fh)
    with open(MODELS_DIR / "lof_model.pkl", "wb") as fh:
        pickle.dump(lof, fh)
    with open(MODELS_DIR / "scaler.pkl", "wb") as fh:
        pickle.dump(scaler, fh)
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {"labels": labels, "scores_ensemble": scores_ens, "metadata": metadata}


if __name__ == "__main__":
    res = entrainer()
    print(f"✅ Modèles entraînés (Forest + LOF) → {MODELS_DIR}/")
    print(f"   {res['metadata']['n_features']} features, "
          f"contamination={res['metadata']['contamination']}, "
          f"seuil={res['metadata']['threshold']}")
