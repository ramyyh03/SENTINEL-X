"""BRIQUE 6.3 — Détecteur d'anomalies ENSEMBLE HYBRIDE.

Combine 4 vues :
- Isolation Forest + LOF + PyOD ECOD  → vue NON SUPERVISÉE (aberrances générales),
- Gradient Boosting (scikit-learn)     → vue SUPERVISÉE (apprend les 8 types connus).

Tout s'installe proprement (PyOD = pur Python, GB = scikit-learn). TensorFlow et
Ollama sont des enrichissements OPTIONNELS, désactivés par défaut (hooks gardés).

Artefacts : models/ensemble/*.pkl + ensemble_metadata.json
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
from pyod.models.ecod import ECOD
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models" / "ensemble"
META_PATH = MODELS_DIR / "ensemble_metadata.json"
FEATURES = ["temp", "humidity", "gas", "presence"]
# Poids du vote : le supervisé (connaît les anomalies) pèse le plus.
W_SUPERVISE, W_NON_SUPERVISE = 0.5, 0.5


def _unit(x, lo, hi):
    return float(np.clip((x - lo) / (hi - lo + 1e-9), 0.0, 1.0)) if hi > lo else 0.0


class EnsembleDetector:
    """Ensemble hybride supervisé + non supervisé."""

    def __init__(self) -> None:
        self.scaler = StandardScaler()
        self.forest = IsolationForest(n_estimators=100, contamination=0.1, random_state=42)
        self.ecod = ECOD()
        self.gb = GradientBoostingClassifier(random_state=42)
        self.lof = LocalOutlierFactor(n_neighbors=20, novelty=True)
        self.bornes: dict = {}
        self.threshold = 0.5

    # --- Entraînement -------------------------------------------------------
    def entrainer(self, df) -> dict:
        """Entraîne tous les modèles sur un DataFrame étiqueté (colonnes + 'label')."""
        X = self.scaler.fit_transform(df[FEATURES].to_numpy(dtype=float))
        y = df["label"].to_numpy()
        self.forest.fit(X)
        self.lof.fit(X)
        self.ecod.fit(X)
        self.gb.fit(X, y)

        # Calibration des scores non supervisés (min/max sur l'entraînement)
        f = -self.forest.score_samples(X)
        l = -self.lof.score_samples(X)
        e = self.ecod.decision_function(X)
        self.bornes = {"f": (float(f.min()), float(f.max())),
                       "l": (float(l.min()), float(l.max())),
                       "e": (float(e.min()), float(e.max()))}
        self._sauver()
        return self._scores_lot(X)

    def _scores_lot(self, X) -> dict:
        """Scores ensemble sur un lot (pour les métriques). Retourne {scores, votes}."""
        f = _norm_vec(-self.forest.score_samples(X), *self.bornes["f"])
        l = _norm_vec(-self.lof.score_samples(X), *self.bornes["l"])
        e = _norm_vec(self.ecod.decision_function(X), *self.bornes["e"])
        non_sup = (f + l + e) / 3.0
        sup = self.gb.predict_proba(X)[:, 1]
        ens = W_SUPERVISE * sup + W_NON_SUPERVISE * non_sup
        return {"scores": ens, "forest": f, "lof": l, "ecod": e, "supervise": sup}

    # --- Détection d'un échantillon ----------------------------------------
    def scorer(self, sensor_data: dict) -> dict:
        """Score un échantillon {temp,humidity,gas,presence}. Retourne le détail."""
        x = self.scaler.transform([[float(sensor_data[c]) for c in FEATURES]])
        f = _unit(-self.forest.score_samples(x)[0], *self.bornes["f"])
        l = _unit(-self.lof.score_samples(x)[0], *self.bornes["l"])
        e = _unit(self.ecod.decision_function(x)[0], *self.bornes["e"])
        sup = float(self.gb.predict_proba(x)[0, 1])
        non_sup = (f + l + e) / 3.0
        score = W_SUPERVISE * sup + W_NON_SUPERVISE * non_sup
        return {
            "anomaly_score": round(float(score), 3),
            "is_anomaly": score >= self.threshold,
            "model_votes": {"isolation_forest": round(f, 3), "lof": round(l, 3),
                            "ecod": round(e, 3), "supervise_gb": round(sup, 3)},
        }

    # --- Persistance --------------------------------------------------------
    def _sauver(self) -> None:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        for nom, obj in {"scaler": self.scaler, "forest": self.forest, "lof": self.lof,
                         "ecod": self.ecod, "gb": self.gb}.items():
            with open(MODELS_DIR / f"{nom}.pkl", "wb") as fh:
                pickle.dump(obj, fh)
        META_PATH.write_text(json.dumps(
            {"features": FEATURES, "bornes": self.bornes, "threshold": self.threshold,
             "poids": {"supervise": W_SUPERVISE, "non_supervise": W_NON_SUPERVISE}},
            indent=2), encoding="utf-8")

    @classmethod
    def charger(cls) -> "EnsembleDetector":
        if not META_PATH.exists():
            raise FileNotFoundError(f"Ensemble non entraîné ({META_PATH}) — lance : make train-ensemble")
        d = cls()
        for nom in ("scaler", "forest", "lof", "ecod", "gb"):
            with open(MODELS_DIR / f"{nom}.pkl", "rb") as fh:
                setattr(d, nom, pickle.load(fh))
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        d.bornes = {k: tuple(v) for k, v in meta["bornes"].items()}
        d.threshold = float(meta["threshold"])
        return d


def _norm_vec(v, lo, hi):
    return np.clip((v - lo) / (hi - lo + 1e-9), 0.0, 1.0)
