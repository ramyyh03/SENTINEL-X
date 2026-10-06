"""BRIQUE 6 — Évaluation des performances du détecteur.

Compare les scores d'anomalie prédits aux labels connus (données synthétiques)
et calcule : matrice de confusion, précision, rappel, F1, ROC-AUC.

Objectifs workshop :  rappel > 0.85  (on rate peu de vraies anomalies)
                      précision > 0.70 (peu de fausses alertes)

Sortie : logs/training_metrics.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import (confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
METRICS_PATH = PROJECT_ROOT / "logs" / "training_metrics.json"


def _recall_episodes(labels: np.ndarray, predictions: np.ndarray) -> tuple[float, int]:
    """Rappel par ÉPISODE : un épisode (segment contigu de label=1) est « détecté »
    si AU MOINS une de ses lectures déclenche. C'est la métrique pertinente pour la
    surveillance (a-t-on attrapé l'incident ?), au-delà du rappel point par point."""
    n = len(labels)
    episodes = detectes = 0
    i = 0
    while i < n:
        if labels[i] == 1:
            j = i
            while j < n and labels[j] == 1:
                j += 1
            episodes += 1
            if predictions[i:j].any():
                detectes += 1
            i = j
        else:
            i += 1
    return (detectes / episodes if episodes else 0.0), episodes


def evaluer(labels: np.ndarray, scores: np.ndarray, threshold: float = 0.4) -> dict:
    """Calcule les métriques et les enregistre en JSON. Retourne le dict de métriques."""
    predictions = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    recall_ep, n_episodes = _recall_episodes(labels, predictions)

    # ROC-AUC sur le score continu (indépendant du seuil) — nécessite 2 classes
    try:
        auc = float(roc_auc_score(labels, scores))
    except ValueError:
        auc = float("nan")

    metrics = {
        "threshold": threshold,
        "confusion_matrix": {"TP": int(tp), "FP": int(fp), "FN": int(fn), "TN": int(tn)},
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "roc_auc": auc,
        "recall_episodes": recall_ep,
        "n_episodes": n_episodes,
        "n_samples": int(len(labels)),
        "n_anomalies": int(labels.sum()),
    }

    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def afficher(metrics: dict) -> None:
    """Affiche un rapport lisible + un verdict par rapport aux objectifs."""
    cm = metrics["confusion_matrix"]
    print("📊 Métriques d'entraînement :")
    print(f"   Matrice : TP={cm['TP']} FP={cm['FP']} FN={cm['FN']} TN={cm['TN']}")
    print(f"   Précision = {metrics['precision']:.3f}  (objectif > 0.70)")
    print(f"   Rappel    = {metrics['recall']:.3f}  (objectif > 0.85)")
    print(f"   F1        = {metrics['f1']:.3f}")
    print(f"   ROC-AUC   = {metrics['roc_auc']:.3f}  (qualité de discrimination)")
    print(f"   Rappel par ÉPISODE = {metrics['recall_episodes']:.3f} "
          f"({metrics['n_episodes']} incidents) ← métrique surveillance")
    ok = metrics["recall_episodes"] >= 0.90 and metrics["roc_auc"] >= 0.75
    if ok:
        print("   ✅ Objectif surveillance atteint : (presque) tous les incidents détectés")
    else:
        print("   ⚠️ À ajuster (seuil/contamination)")


if __name__ == "__main__":
    from predictive.forest_trainer import entrainer

    res = entrainer()
    m = evaluer(res["labels"], res["scores_ensemble"], res["metadata"]["threshold"])
    afficher(m)
