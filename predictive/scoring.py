"""BRIQUE 6 — Fonctions de scoring partagées (entraînement ↔ détection).

Centralise la conversion « score d'un modèle » → « score d'anomalie [0,1] » pour
garantir que l'entraînement (métriques) et la détection temps réel calculent
EXACTEMENT la même chose. (Principe DRY.)

Méthode : on part de `decision_function` (sklearn) dont le SIGNE donne déjà la
décision calibrée par la contamination (négatif = anomalie). On centre donc la
frontière de décision sur **0.5** : un score ≥ 0.5 = anomalie selon le modèle.
"""
from __future__ import annotations

import numpy as np

# Poids de l'ensemble (Forest / LOF) — somme = 1
POIDS_FOREST = 0.5
POIDS_LOF = 0.5


def scores_bruts(model, X: np.ndarray) -> np.ndarray:
    """Marge d'anomalie : > 0 = anomalie, < 0 = normal (frontière à 0).

    `decision_function` sklearn : > 0 normal, < 0 anomalie → on inverse le signe.
    """
    return -model.decision_function(X)


def calibrer(brut: np.ndarray) -> tuple[float, float]:
    """Calcule les échelles (côté normal, côté anomalie) sur les scores d'entraînement.

    On utilise des percentiles robustes plutôt que min/max (insensibles aux extrêmes).
    Retourne (echelle_normale, echelle_anomalie), toujours > 0.
    """
    cote_anomalie = brut[brut > 0]
    cote_normal = -brut[brut < 0]
    ech_anom = float(np.percentile(cote_anomalie, 95)) if cote_anomalie.size else 1.0
    ech_norm = float(np.percentile(cote_normal, 95)) if cote_normal.size else 1.0
    return max(ech_norm, 1e-9), max(ech_anom, 1e-9)


def vers_unite(brut: np.ndarray, ech_norm: float, ech_anom: float) -> np.ndarray:
    """Mappe la marge vers [0,1] avec la frontière de décision à 0.5."""
    brut = np.asarray(brut, dtype=float)
    positif = 0.5 + 0.5 * np.clip(brut / ech_anom, 0.0, 1.0)
    negatif = 0.5 - 0.5 * np.clip(-brut / ech_norm, 0.0, 1.0)
    return np.where(brut >= 0, positif, negatif)


def ensemble(forest_u: np.ndarray, lof_u: np.ndarray) -> np.ndarray:
    """Combine les scores [0,1] des deux modèles (moyenne pondérée)."""
    return POIDS_FOREST * forest_u + POIDS_LOF * lof_u
