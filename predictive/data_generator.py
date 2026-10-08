"""BRIQUE 6 — Générateur de données synthétiques SENTINEL-X.

Produit ~2880 lectures (48 h simulées, 1 lecture/minute) mêlant des profils
NORMAUX variés (nuit, jour actif, ventilation, repos) et 8 types d'ANOMALIES
injectées (~10 % du dataset → contamination 0.1).

Sortie : data/training_data.csv  (timestamp, temp, humidity, gas, presence, anomaly_label)

Pourquoi des données synthétiques : la base réelle (Brique 3) est encore trop
petite et peu variée pour entraîner un modèle. On fabrique donc un historique
réaliste et ÉTIQUETÉ, seul moyen de mesurer précision/rappel (voir metrics_evaluator).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = PROJECT_ROOT / "data" / "training_data.csv"

RANDOM_STATE = 42
MINUTES_48H = 48 * 60            # 2880 points, 1 lecture / minute
CONTAMINATION = 0.10             # ~10 % d'anomalies
START = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)

# Bornes physiques plausibles (servent aussi à la normalisation des features)
TEMP_MIN, TEMP_MAX = 0.0, 50.0
HUM_MIN, HUM_MAX = 0.0, 100.0
GAS_MIN, GAS_MAX = 0.0, 4095.0   # valeur brute ADC MQ-2


def _baseline_normale(n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Construit un signal normal avec cycle jour/nuit sur n minutes."""
    minutes = np.arange(n)
    heure = (minutes / 60.0) % 24.0

    # Température : nuit ~18 °C, après-midi ~26 °C (sinusoïde + bruit léger)
    temp = 22.0 + 4.0 * np.sin((heure - 9.0) / 24.0 * 2 * np.pi) + rng.normal(0, 0.3, n)
    # Humidité : anti-corrélée à la température + bruit
    humidite = 55.0 - 10.0 * np.sin((heure - 9.0) / 24.0 * 2 * np.pi) + rng.normal(0, 1.5, n)
    # Gaz : baseline basse, quelques bouffées diurnes
    gaz = 20.0 + rng.normal(0, 15, n)    # gaz NORMALISÉ : ~0 au repos (auto-calibration ESP32)
    jour = (heure > 8) & (heure < 20)
    gaz[jour] += rng.uniform(0, 40, jour.sum())
    # Présence : surtout en journée (probabilité plus élevée)
    proba = np.where(jour, 0.35, 0.03)
    presence = (rng.random(n) < proba).astype(int)

    return pd.DataFrame(
        {"temp": temp, "humidity": humidite, "gas": gaz, "presence": presence}
    )


def _injecter_anomalies(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Injecte les 8 types d'anomalies in-place ; retourne le vecteur de labels."""
    n = len(df)
    label = np.zeros(n, dtype=int)
    cible = int(n * CONTAMINATION)
    # copy=True : indispensable: avec numpy récent, .to_numpy() peut renvoyer une
    # vue en LECTURE SEULE → l'écriture en place planterait ("read-only").
    t = df["temp"].to_numpy(dtype=float, copy=True)
    h = df["humidity"].to_numpy(dtype=float, copy=True)
    g = df["gas"].to_numpy(dtype=float, copy=True)
    p = df["presence"].to_numpy(dtype=int, copy=True)

    def marque(start: int, length: int) -> None:
        label[start : min(start + length, n)] = 1

    pose = 0
    while pose < cible:
        kind = rng.integers(0, 8)
        start = int(rng.integers(60, n - 60))  # évite les tout premiers/derniers points

        if kind == 0:  # Intrusion : présence inattendue (nuit) + saut de T ±5 °C
            p[start : start + 3] = 1
            t[start : start + 3] += rng.choice([-5, 5])
            marque(start, 3); pose += 3
        elif kind == 1:  # Fuite gaz lente : +50/min pendant 10 min, sans mouvement
            for k in range(10):
                g[start + k] = g[start + k] + 50 * k
            p[start : start + 10] = 0
            marque(start, 10); pose += 10
        elif kind == 2:  # Surchauffe : +1 °C/min pendant 20 min
            for k in range(20):
                t[start + k] = t[start + k] + 1.0 * k
            marque(start, 20); pose += 20
        elif kind == 3:  # Condensation : +30 % d'humidité en 2 min
            h[start : start + 2] = np.clip(h[start : start + 2] + 30, HUM_MIN, HUM_MAX)
            marque(start, 2); pose += 2
        elif kind == 4:  # Capteur stuck : même valeur sur 25 lectures
            t[start : start + 25] = t[start]
            marque(start, 25); pose += 25
        elif kind == 5:  # Corrélation inverse : gaz haut + présence qui tombe
            g[start : start + 8] += 1500
            p[start : start + 8] = 0
            marque(start, 8); pose += 8
        elif kind == 6:  # Dérive lente : -0.1 °C/lecture pendant 30 min
            for k in range(30):
                t[start + k] = t[start + k] - 0.1 * k
            marque(start, 30); pose += 30
        else:  # Combinaison multi-facteurs : gaz + T montent, aucun mouvement
            for k in range(12):
                g[start + k] += 120 * k
                t[start + k] += 0.8 * k
            p[start : start + 12] = 0
            marque(start, 12); pose += 12

    df["temp"] = np.clip(t, TEMP_MIN, TEMP_MAX)
    df["humidity"] = np.clip(h, HUM_MIN, HUM_MAX)
    df["gas"] = np.clip(g, GAS_MIN, GAS_MAX)
    df["presence"] = np.clip(p, 0, 1).astype(int)
    return label


def generer(n: int = MINUTES_48H, csv_path: Path | None = None) -> pd.DataFrame:
    """Génère le dataset complet (normal + anomalies) et l'enregistre en CSV."""
    rng = np.random.default_rng(RANDOM_STATE)
    df = _baseline_normale(n, rng)
    df["anomaly_label"] = _injecter_anomalies(df, rng)

    # Horodatage régulier (1 min) au format ISO 8601 UTC
    df.insert(0, "timestamp",
              [(START + timedelta(minutes=int(i))).strftime("%Y-%m-%dT%H:%M:%SZ")
               for i in range(n)])
    df["temp"] = df["temp"].round(2)
    df["humidity"] = df["humidity"].round(2)
    df["gas"] = df["gas"].round(0)

    out = csv_path or DEFAULT_CSV
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df


if __name__ == "__main__":
    data = generer()
    n_anom = int(data["anomaly_label"].sum())
    print(f"✅ {len(data)} lectures générées → {DEFAULT_CSV}")
    print(f"   Anomalies : {n_anom} ({100 * n_anom / len(data):.1f} %)")
