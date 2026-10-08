"""BRIQUE 6.3 — Générateur de données synthétiques ÉTIQUETÉES (pour l'ensemble).

1000 échantillons = 800 normaux + 200 anomalies réparties en 8 types.
Sert à entraîner le classifieur SUPERVISÉ (on connaît le label) et à mesurer
précision/rappel. Pur numpy/pandas (aucune dépendance lourde).

Sortie : data/synthetic_1000.csv (temp, humidity, gas, presence, label, description)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV = PROJECT_ROOT / "data" / "synthetic_1000.csv"
COLS = ["temp", "humidity", "gas", "presence"]


class SyntheticDataGenerator:
    """Génère des mesures normales + 8 types d'anomalies, étiquetées."""

    def __init__(self, seed: int = 42) -> None:
        self.rng = np.random.default_rng(seed)

    def generer(self, n_total: int = 1000, anomaly_ratio: float = 0.2) -> pd.DataFrame:
        n_norm = int(n_total * (1 - anomaly_ratio))
        n_anom = n_total - n_norm
        lignes, labels, desc = [], [], []

        # --- Normales ---
        for _ in range(n_norm):
            # Valeurs ATMOSPHÉRIQUES réalistes (intérieur) + plage réelle du MQ-2 :
            # air propre -> baseline ADC ~650 (mesuré sur le vrai capteur).
            temp = float(np.clip(self.rng.normal(22, 2.0), 15, 32))        # pièce : ~18-26 °C
            humidity = float(np.clip(50 + (temp - 22) * 1.5 + self.rng.normal(0, 4), 30, 70))
            # GAZ NORMALISÉ (écart à l'air propre) : ~0 au repos (auto-calibration ESP32).
            gas = float(np.clip(self.rng.normal(20, 20), 0, 100))
            presence = int(self.rng.choice([0, 1], p=[0.85, 0.15]))
            lignes.append([temp, humidity, gas, presence]); labels.append(0); desc.append("NORMAL")

        # --- Anomalies : 8 types répartis également ---
        types = [self._gas_spike, self._temp_jump, self._logic_inversion, self._temp_drift,
                 self._humidity_high, self._correlation_broken, self._stuck, self._injection]
        par_type = max(1, n_anom // len(types))
        for fn in types:
            for _ in range(par_type):
                sample, nom = fn()
                lignes.append(sample); labels.append(1); desc.append(f"ANOMALY_{nom}")

        df = pd.DataFrame(lignes, columns=COLS)
        df["label"] = labels[:len(df)]
        df["description"] = desc[:len(df)]
        df["temp"] = df["temp"].round(2); df["humidity"] = df["humidity"].round(2)
        df["gas"] = df["gas"].round(0); df["presence"] = df["presence"].astype(int)

        CSV.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(CSV, index=False)
        return df

    # --- 8 types d'anomalies ---
    # NB : gaz NORMALISÉ (écart à l'air propre). ~0 = repos ; >200 = gaz présent.
    def _gas_spike(self):   # pic de gaz (briquet/fumée près du capteur)
        return [float(self.rng.normal(22, 1)), float(self.rng.normal(50, 3)),
                float(self.rng.normal(400, 120)), 0], "GAS_SPIKE"

    def _temp_jump(self):   # température impossible (gaz au repos)
        return [float(self.rng.normal(55, 5)), float(self.rng.normal(30, 5)),
                float(np.clip(self.rng.normal(20, 20), 0, 100)), 0], "TEMP_JUMP"

    def _logic_inversion(self):  # présence sans aucun gaz (anomalie logique)
        return [float(self.rng.normal(22, 1)), float(self.rng.normal(50, 3)),
                float(np.clip(self.rng.normal(5, 5), 0, 50)), 1], "LOGIC_INVERSION"

    def _temp_drift(self):  # dérive thermique (gaz au repos)
        return [float(self.rng.normal(38, 3)), float(self.rng.normal(22, 2)),
                float(np.clip(self.rng.normal(20, 20), 0, 100)), 0], "TEMP_DRIFT"

    def _humidity_high(self):  # humidité extrême (gaz au repos)
        return [float(self.rng.normal(22, 1)), float(self.rng.normal(96, 3)),
                float(np.clip(self.rng.normal(20, 20), 0, 100)), int(self.rng.integers(0, 2))], "HUMIDITY_HIGH"

    def _correlation_broken(self):  # gaz TRÈS élevé sans présence
        return [float(self.rng.normal(22, 1)), float(self.rng.normal(50, 3)),
                float(self.rng.normal(900, 200)), 0], "CORRELATION_BROKEN"

    def _stuck(self):  # valeurs figées « parfaites » (pas de bruit) au repos
        return [22.0, 50.0, 0.0, 0], "STUCK"

    def _injection(self):  # tout cassé (extrêmes)
        return [float(self.rng.uniform(-10, 70)), float(self.rng.uniform(0, 100)),
                float(self.rng.uniform(1500, 3000)), int(self.rng.integers(0, 2))], "INJECTION"


if __name__ == "__main__":
    data = SyntheticDataGenerator().generer()
    print(f"✅ {len(data)} échantillons → {CSV}")
    print(f"   Normaux: {(data['label'] == 0).sum()} · Anomalies: {(data['label'] == 1).sum()}")
