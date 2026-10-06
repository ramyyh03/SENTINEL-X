"""BRIQUE 6 — Détection d'anomalies en temps réel.

Charge les modèles entraînés et score chaque nouvelle lecture (sur un tampon des
dernières mesures, nécessaire pour les features temporelles). Fournit aussi :
- l'explicabilité légère (top features qui s'écartent le plus de la normale),
- la détection de « capteur figé » (drift / stuck).
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from predictive import scoring
from predictive.feature_engineer import FEATURE_COLUMNS, construire_features

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

STUCK_N = 25            # nb de lectures identiques → capteur figé
TOP_FEATURES = 3        # nb de features expliquant l'alerte


class Detecteur:
    """Encapsule les modèles + la logique de scoring temps réel (pattern Repository)."""

    def __init__(self, models_dir: Path = MODELS_DIR) -> None:
        """Charge Forest, LOF, scaler et metadata. Lève si les modèles manquent."""
        self.forest = self._charger(models_dir / "isolation_forest.pkl")
        self.lof = self._charger(models_dir / "lof_model.pkl")
        self.scaler = self._charger(models_dir / "scaler.pkl")
        meta_path = models_dir / "forest_metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"Modèles introuvables ({meta_path}). Lance d'abord : make train"
            )
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.bornes = self.meta["score_bounds"]
        self.threshold = float(self.meta["threshold"])

    @staticmethod
    def _charger(path: Path):
        """Désérialise un artefact pickle, avec message clair si absent."""
        if not path.exists():
            raise FileNotFoundError(f"Modèle manquant : {path} — lance : make train")
        with open(path, "rb") as fh:
            return pickle.load(fh)

    def _drift(self, buffer: pd.DataFrame) -> str | None:
        """Retourne le nom d'un capteur figé (STUCK_N valeurs identiques), sinon None."""
        if len(buffer) < STUCK_N:
            return None
        for capteur in ("temp", "humidity", "gas"):
            derniers = buffer[capteur].tail(STUCK_N)
            if derniers.nunique() == 1:
                return capteur
        return None

    def _top_features(self, x_scaled: np.ndarray) -> list[str]:
        """Features qui s'écartent le plus de la moyenne d'entraînement (|z| le plus grand)."""
        ecarts = np.abs(x_scaled[0])
        ordre = np.argsort(ecarts)[::-1][:TOP_FEATURES]
        return [f"{FEATURE_COLUMNS[i]}: {x_scaled[0][i]:+.2f}" for i in ordre]

    def detecter(self, buffer: pd.DataFrame) -> dict:
        """Score la DERNIÈRE lecture du tampon. Retourne un dict de résultat complet."""
        features = construire_features(buffer)
        x_scaled = self.scaler.transform(features.to_numpy()[-1:])

        f_raw = scoring.scores_bruts(self.forest, x_scaled)
        l_raw = scoring.scores_bruts(self.lof, x_scaled)
        f_u = float(scoring.vers_unite(f_raw, self.bornes["forest_ech_norm"],
                                       self.bornes["forest_ech_anom"])[0])
        l_u = float(scoring.vers_unite(l_raw, self.bornes["lof_ech_norm"],
                                       self.bornes["lof_ech_anom"])[0])
        score = float(scoring.ensemble(np.array([f_u]), np.array([l_u]))[0])

        capteur_fige = self._drift(buffer)
        return {
            "anomaly_score": round(score, 3),
            "is_anomaly": score >= self.threshold,
            "threshold": self.threshold,
            "model_votes": {"forest": round(f_u, 3), "lof": round(l_u, 3)},
            "triggered_features": self._top_features(x_scaled),
            "drift_sensor": capteur_fige,
        }
