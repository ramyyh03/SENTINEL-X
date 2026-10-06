"""BRIQUE 6 — Baseline glissante (« dernière heure »).

Fournit la référence normale récente (moyenne/écart-type sur une fenêtre) et
l'écart de la mesure courante à cette référence (z-score). Permet d'expliquer
une alerte (« T = 35 °C alors que la moyenne de l'heure est 24.8 ± 1.2 »).
"""
from __future__ import annotations

import pandas as pd

from predictive.feature_engineer import WIN_BASELINE

CAPTEURS = ("temp", "humidity", "gas")


def baseline(buffer: pd.DataFrame, window: int = WIN_BASELINE) -> dict:
    """Statistiques de référence sur les `window` dernières lectures + z-score courant.

    Retourne un dict : { 'temp_mean_1h', 'temp_std_1h', 'z_score_temp', ... }.
    """
    recent = buffer.tail(window)
    courant = buffer.iloc[-1]
    stats: dict[str, float] = {}

    for capteur in CAPTEURS:
        moyenne = float(recent[capteur].mean())
        ecart = float(recent[capteur].std(ddof=0))
        stats[f"{capteur}_mean_1h"] = round(moyenne, 2)
        stats[f"{capteur}_std_1h"] = round(ecart, 2)
        z = (float(courant[capteur]) - moyenne) / ecart if ecart > 1e-9 else 0.0
        stats[f"z_score_{capteur}"] = round(z, 2)

    return stats
