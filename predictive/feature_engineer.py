"""BRIQUE 6 — Feature engineering SENTINEL-X.

Transforme une série temporelle brute (temp, humidity, gas, presence) en ~27
features exploitables par les modèles : valeurs normalisées, dérivées
(vitesses/accélérations), statistiques glissantes, corrélations inter-capteurs
et écarts à une baseline (z-scores).

La MÊME fonction sert à l'entraînement (sur tout l'historique) et à la détection
temps réel (sur un tampon des dernières lectures) → garantit la cohérence.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Fenêtres (en nombre de lectures ; cadence synthétique = 1/min)
WIN_SHORT = 5       # lissage court (~5 min)
WIN_CORR = 10       # corrélations inter-capteurs
WIN_BASELINE = 60   # baseline "dernière heure" (~60 min)

# Bornes de normalisation (cohérentes avec data_generator)
TEMP_MIN, TEMP_MAX = 0.0, 50.0
HUM_MIN, HUM_MAX = 0.0, 100.0
GAS_MIN, GAS_MAX = 0.0, 4095.0

# Liste FIGÉE des features (ordre garanti entraînement ↔ inférence)
FEATURE_COLUMNS: list[str] = [
    # --- brutes normalisées [0,1] (4) ---
    "temp_n", "humidity_n", "gas_n", "presence_n",
    # --- dérivées temporelles (7) ---
    "temp_delta_1", "temp_delta_5", "humidity_delta_1",
    "gas_velocity", "gas_delta_5", "temp_accel", "humidity_delta_5",
    # --- statistiques glissantes (8) ---
    "temp_roll_mean", "temp_roll_std", "temp_roll_min", "temp_roll_max",
    "gas_roll_mean", "gas_roll_std", "gas_roll_range", "humidity_roll_std",
    # --- corrélations inter-capteurs + ratio (4) ---
    "corr_gas_temp", "corr_gas_presence", "corr_humidity_temp", "ratio_gas_temp",
    # --- écarts à la baseline 1h (4) ---
    "z_score_temp", "z_score_gas", "z_score_humidity", "baseline_distance",
]


def _norm(serie: pd.Series, lo: float, hi: float) -> pd.Series:
    """Normalise une série dans [0,1] selon des bornes physiques fixes."""
    return ((serie - lo) / (hi - lo)).clip(0.0, 1.0)


def _z_score(serie: pd.Series, window: int) -> pd.Series:
    """Écart-type normalisé par rapport à une moyenne glissante (baseline)."""
    moyenne = serie.rolling(window, min_periods=2).mean()
    ecart = serie.rolling(window, min_periods=2).std().replace(0, np.nan)
    return ((serie - moyenne) / ecart)


def construire_features(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule toutes les features pour chaque ligne (ordre chronologique attendu).

    `df` doit contenir les colonnes : temp, humidity, gas, presence.
    Retourne un DataFrame avec exactement FEATURE_COLUMNS (NaN comblés à 0).
    """
    t, h, g, p = df["temp"], df["humidity"], df["gas"], df["presence"]
    f = pd.DataFrame(index=df.index)

    # Brutes normalisées
    f["temp_n"] = _norm(t, TEMP_MIN, TEMP_MAX)
    f["humidity_n"] = _norm(h, HUM_MIN, HUM_MAX)
    f["gas_n"] = _norm(g, GAS_MIN, GAS_MAX)
    f["presence_n"] = p.astype(float)

    # Dérivées temporelles (vitesses / accélération)
    f["temp_delta_1"] = t.diff(1)
    f["temp_delta_5"] = t.diff(5) / 5.0
    f["humidity_delta_1"] = h.diff(1)
    f["humidity_delta_5"] = h.diff(5) / 5.0
    f["gas_velocity"] = g.diff(1)
    f["gas_delta_5"] = g.diff(5) / 5.0
    f["temp_accel"] = f["temp_delta_1"].diff(1)  # accélération = dérivée de la vitesse

    # Statistiques glissantes (variabilité / étendue)
    tr = t.rolling(WIN_SHORT, min_periods=1)
    gr = g.rolling(WIN_SHORT, min_periods=1)
    f["temp_roll_mean"] = tr.mean()
    f["temp_roll_std"] = tr.std().fillna(0)
    f["temp_roll_min"] = tr.min()
    f["temp_roll_max"] = tr.max()
    f["gas_roll_mean"] = gr.mean()
    f["gas_roll_std"] = gr.std().fillna(0)
    f["gas_roll_range"] = gr.max() - gr.min()
    f["humidity_roll_std"] = h.rolling(WIN_SHORT, min_periods=1).std().fillna(0)

    # Corrélations inter-capteurs (logique physique : écart = suspect)
    f["corr_gas_temp"] = g.rolling(WIN_CORR, min_periods=3).corr(t)
    f["corr_gas_presence"] = g.rolling(WIN_CORR, min_periods=3).corr(p.astype(float))
    f["corr_humidity_temp"] = h.rolling(WIN_CORR, min_periods=3).corr(t)
    f["ratio_gas_temp"] = g / (t + 273.0)  # proportion gaz/température absolue

    # Écarts à la baseline "dernière heure"
    f["z_score_temp"] = _z_score(t, WIN_BASELINE)
    f["z_score_gas"] = _z_score(g, WIN_BASELINE)
    f["z_score_humidity"] = _z_score(h, WIN_BASELINE)
    f["baseline_distance"] = np.sqrt(
        f["z_score_temp"].fillna(0) ** 2
        + f["z_score_gas"].fillna(0) ** 2
        + f["z_score_humidity"].fillna(0) ** 2
    )

    # Nettoyage : NaN/inf (débuts de série, divisions) → 0
    f = f.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return f[FEATURE_COLUMNS]


if __name__ == "__main__":
    from pathlib import Path

    csv = Path(__file__).resolve().parent.parent / "data" / "training_data.csv"
    data = pd.read_csv(csv)
    feats = construire_features(data)
    print(f"✅ {feats.shape[1]} features calculées sur {feats.shape[0]} lignes")
    print("   Colonnes :", ", ".join(feats.columns))
