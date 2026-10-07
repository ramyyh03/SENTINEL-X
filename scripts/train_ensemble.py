"""BRIQUE 6.3 — Entraîne l'ensemble hybride et affiche les métriques.

Génère 1000 synthétiques → split stratifié → entraîne (IF+LOF+ECOD+GB) →
évalue sur le test (précision/rappel/F1/ROC-AUC + matrice de confusion).

Usage : python scripts/train_ensemble.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sklearn.metrics import (confusion_matrix, f1_score, precision_score,  # noqa: E402
                             recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split  # noqa: E402

from predictive.ensemble_detector import EnsembleDetector, MODELS_DIR  # noqa: E402
from predictive.synthetic_data_gen import SyntheticDataGenerator  # noqa: E402


def main() -> int:
    print("🧠 BRIQUE 6.3 — Entraînement de l'ensemble hybride")
    df = SyntheticDataGenerator().generer(n_total=1000, anomaly_ratio=0.2)
    train, test = train_test_split(df, test_size=0.2, random_state=42, stratify=df["label"])

    det = EnsembleDetector()
    det.entrainer(train.reset_index(drop=True))

    # Scores sur le test
    import numpy as np
    Xt = det.scaler.transform(test[["temp", "humidity", "gas", "presence"]].to_numpy(dtype=float))
    scores = det._scores_lot(Xt)["scores"]
    y = test["label"].to_numpy()
    pred = (scores >= det.threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    metrics = {
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, scores)),
        "confusion_matrix": {"TP": int(tp), "FP": int(fp), "FN": int(fn), "TN": int(tn)},
        "n_test": int(len(y)),
    }
    (MODELS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(f"\n📈 Métriques (seuil {det.threshold}) :")
    print(f"   Précision = {metrics['precision']:.3f}  (cible 0.74)")
    print(f"   Rappel    = {metrics['recall']:.3f}  (cible 0.85)")
    print(f"   F1        = {metrics['f1']:.3f}  (cible 0.79)")
    print(f"   ROC-AUC   = {metrics['roc_auc']:.3f}")
    print(f"   Matrice   : TP={tp} FP={fp} FN={fn} TN={tn}")
    ok = metrics["recall"] >= 0.85 and metrics["precision"] >= 0.70
    print("   ✅ Objectifs atteints" if ok else "   ⚠️ À ajuster")
    print(f"\n✅ Modèles → {MODELS_DIR}/ · métriques → metrics.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
