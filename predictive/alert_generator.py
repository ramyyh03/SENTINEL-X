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

SEUIL_GAZ = 250          # gaz NORMALISÉ (0 au repos) : au-dessus = gaz présent


def _contexte(valeurs: dict, baseline: dict, drift: str | None) -> tuple[str, str, str]:
    """Explication + recommandation + GRAVITÉ selon le TYPE de danger (règles métier).

    La gravité dépend de ce qui se passe réellement (danger concret), pas du
    score brut : seuls le gaz, l'intrusion et la surchauffe sont CRITICAL.
    """
    if drift:
        return (f"Capteur « {drift} » figé (même valeur prolongée) — mesure peu fiable",
                f"Vérifier le câblage / l'alimentation du capteur {drift}", "WARNING")

    gaz, presence = valeurs.get("gas", 0), valeurs.get("presence", 0)
    z_temp = baseline.get("z_score_temp", 0)

    if gaz > SEUIL_GAZ:
        return ("Gaz élevé détecté → fuite / fumée possible",
                "Vérifier la zone et ventiler ; couper la source de gaz si confirmé", "CRITICAL")
    if z_temp >= 5:
        return ("Hausse de température anormale vs référence → surchauffe possible",
                "Vérifier le système HVAC / sources de chaleur", "CRITICAL")
    if presence and abs(z_temp) >= 3:
        return ("Présence inattendue + variation thermique brutale → intrusion possible",
                "Vérifier les accès et la vidéosurveillance de la zone", "CRITICAL")
    if presence:
        return ("Présence détectée",
                "Vérifier si la présence est attendue", "WARNING")
    # Cas générique : l'IA note un écart mais pas de danger identifié -> INFO.
    return ("Comportement capteurs atypique vs référence récente",
            "Surveiller l'évolution ; vérifier si l'anomalie persiste", "INFO")


def generer_alerte(detection: dict, valeurs: dict, baseline: dict,
                   timestamp: str | None = None) -> dict:
    """Construit l'alerte JSON complète à partir du résultat de détection."""
    score = detection["anomaly_score"]
    # La gravité vient du TYPE de danger (règles métier), pas du score brut.
    contexte, reco, severite = _contexte(valeurs, baseline, detection.get("drift_sensor"))
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
