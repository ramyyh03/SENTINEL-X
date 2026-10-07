"""Tests de la Brique 6.3 — ensemble hybride."""
from predictive.ensemble_detector import EnsembleDetector
from predictive.synthetic_data_gen import SyntheticDataGenerator


def test_generation_synthetique():
    df = SyntheticDataGenerator().generer(n_total=100, anomaly_ratio=0.2)
    assert len(df) >= 96                        # ~100 (arrondi des 8 types)
    assert (df["label"] == 0).sum() == 80
    assert (df["label"] == 1).sum() >= 16


def test_ensemble_normal_vs_anomalie():
    df = SyntheticDataGenerator().generer(n_total=1000, anomaly_ratio=0.2)
    det = EnsembleDetector()
    det.entrainer(df)

    normal = {"temp": 23.0, "humidity": 50, "gas": 120, "presence": 0}
    anomalie = {"temp": 23.0, "humidity": 50, "gas": 4500, "presence": 0}  # gaz extrême

    s_norm = det.scorer(normal)["anomaly_score"]
    s_anom = det.scorer(anomalie)["anomaly_score"]
    assert s_anom > s_norm                      # l'anomalie doit scorer plus haut
    assert det.scorer(anomalie)["is_anomaly"] is True


def test_charger_apres_entrainement():
    SyntheticDataGenerator().generer(n_total=200, anomaly_ratio=0.2)
    EnsembleDetector().entrainer(SyntheticDataGenerator().generer(n_total=1000))
    det = EnsembleDetector.charger()            # recharge depuis le disque
    r = det.scorer({"temp": 23, "humidity": 50, "gas": 120, "presence": 0})
    assert "anomaly_score" in r and "model_votes" in r
