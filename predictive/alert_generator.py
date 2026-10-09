"""BRIQUE 6 — Génération d'alertes intelligentes (format JSON unifié).

Transforme un résultat de détection en alerte structurée, avec :
- niveau de sévérité (INFO / WARNING / CRITICAL),
- explication humaine (contexte) + recommandation,
- les 3 features déclenchantes et la comparaison à la baseline.

Format commun à tout SENTINEL-X : source / type / confidence / timestamp / details.
"""
from __future__ import annotations

from datetime import datetime, timezone

# Mêmes seuils que le moteur de corrélation (source de vérité unique).
from predictive.correlation import GAZ_JAUNE, GAZ_ROUGE, TEMP_JAUNE, TEMP_ROUGE

SOURCE = "ia_predictive"
TYPE = "anomaly_detected"


def _contexte(valeurs: dict, drift: str | None) -> tuple[str, str, str]:
    """Explication + recommandation + GRAVITÉ selon le TYPE de danger (règles métier).

    La gravité dépend de ce qui se passe réellement (seuils décidés : température
    et gaz en vert / jaune / rouge), pas du score brut. Sert de repli quand la
    corrélation ne qualifie pas de scénario précis.
    """
    if drift:
        return (f"Capteur « {drift} » figé (même valeur prolongée) — mesure peu fiable",
                f"Vérifier le câblage / l'alimentation du capteur {drift}", "WARNING")

    gaz = float(valeurs.get("gas", 0) or 0)
    temp = float(valeurs.get("temp", 0) or 0)
    presence = valeurs.get("presence", 0)

    if gaz >= GAZ_ROUGE:
        return ("Gaz élevé détecté → fuite / fumée possible",
                "Vérifier la zone et ventiler ; couper la source de gaz si confirmé", "CRITICAL")
    if temp > TEMP_ROUGE:
        return ("Température critique → surchauffe / risque feu",
                "Vérifier la source de chaleur, couper les équipements chauffants", "CRITICAL")
    if gaz >= GAZ_JAUNE:
        return ("Gaz léger détecté → à surveiller",
                "Aérer la zone et surveiller l'évolution", "WARNING")
    if presence:
        return ("Présence détectée",
                "Vérifier si la présence est attendue", "WARNING")
    if temp > TEMP_JAUNE:
        return ("Température élevée → ambiance chaude",
                "Ventiler ou rafraîchir la zone", "WARNING")
    # Cas générique : l'IA note un écart mais pas de danger identifié -> INFO.
    return ("Comportement capteurs atypique vs référence récente",
            "Surveiller l'évolution ; vérifier si l'anomalie persiste", "INFO")


def generer_alerte(detection: dict, valeurs: dict, baseline: dict,
                   timestamp: str | None = None) -> dict:
    """Construit l'alerte JSON complète à partir du résultat de détection."""
    score = detection["anomaly_score"]
    # La gravité vient du TYPE de danger (règles métier), pas du score brut.
    contexte, reco, severite = _contexte(valeurs, detection.get("drift_sensor"))
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
