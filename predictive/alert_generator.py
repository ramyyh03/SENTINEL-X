"""BRIQUE 6 — Génération d'alertes intelligentes (format JSON unifié).

Transforme un résultat de détection en alerte structurée, avec :
- niveau de sévérité (INFO / WARNING / CRITICAL),
- explication humaine (contexte) + recommandation,
- les 3 features déclenchantes et la comparaison à la baseline.

Format commun à tout SENTINEL-X : source / type / confidence / timestamp / details.
"""
from __future__ import annotations

from datetime import datetime, timezone

SOURCE = "ia_predictive"
TYPE = "anomaly_detected"

SEUIL_WARNING = 0.6
SEUIL_CRITICAL = 0.8


def _severite(score: float) -> str:
    """Mappe un score d'anomalie vers un niveau de sévérité."""
    if score >= SEUIL_CRITICAL:
        return "CRITICAL"
    if score >= SEUIL_WARNING:
        return "WARNING"
    return "INFO"


def _contexte(valeurs: dict, baseline: dict, drift: str | None) -> tuple[str, str]:
    """Déduit une explication + une recommandation à partir de règles métier simples."""
    if drift:
        return (f"Capteur « {drift} » figé (même valeur prolongée) — mesure peu fiable",
                f"Vérifier le câblage / l'alimentation du capteur {drift}")

    gaz, presence = valeurs.get("gas", 0), valeurs.get("presence", 0)
    temp = valeurs.get("temp", 0)
    z_temp = baseline.get("z_score_temp", 0)

    if gaz > 1000 and not presence:
        return ("Gaz élevé sans présence détectée → fuite possible",
                "Vérifier la zone et ventiler ; couper la source de gaz si confirmé")
    if z_temp >= 5:
        return ("Hausse de température anormale vs référence → surchauffe possible",
                "Vérifier le système HVAC / sources de chaleur")
    if presence and abs(z_temp) >= 3:
        return ("Présence inattendue + variation thermique brutale → intrusion possible",
                "Vérifier les accès et la vidéosurveillance de la zone")
    return ("Comportement capteurs atypique vs référence récente",
            "Surveiller l'évolution ; vérifier si l'anomalie persiste")


def generer_alerte(detection: dict, valeurs: dict, baseline: dict,
                   timestamp: str | None = None) -> dict:
    """Construit l'alerte JSON complète à partir du résultat de détection."""
    score = detection["anomaly_score"]
    severite = _severite(score)
    # Capteur figé → on baisse la confiance (donnée peu fiable)
    if detection.get("drift_sensor"):
        severite = "WARNING" if severite == "CRITICAL" else severite
    contexte, reco = _contexte(valeurs, baseline, detection.get("drift_sensor"))
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "source": SOURCE,
        "type": TYPE,
        "confidence": score,
        "timestamp": ts,
        "details": {
            "anomaly_score": score,
            "threshold": detection["threshold"],
            "model_votes": detection["model_votes"],
            "triggered_features": detection["triggered_features"],
            "current_values": valeurs,
            "baseline": baseline,
            "context": contexte,
            "severity": severite,
            "recommendation": reco,
            "drift_sensor": detection.get("drift_sensor"),
        },
    }
