"""SENTINEL-X — Fusion multi-capteurs (corrélation scientifique).

Au lieu de seuils isolés, on croise température, humidité, gaz, présence (PIR)
et caméra pour identifier des SCÉNARIOS réels. Une alerte grave exige plusieurs
capteurs cohérents → beaucoup moins de faux positifs.

Scénarios (du plus grave au plus bénin) :
    1. INCENDIE   : gaz↑ + température↑ + humidité↓   (combustion)
    2. FUITE_GAZ  : gaz↑ sans montée thermique         (fuite)
    3. INTRUSION  : caméra (personne) + PIR (mouvement) (2 capteurs = confirmé)
    4. PRESENCE   : caméra OU PIR seul                  (à confirmer)
    5. CHALEUR    : indice de chaleur (humidex) élevé   (inconfort/risque)
    6. CONDENSATION : humidité haute + température basse (moisissure)
    7. NORMAL
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# --- Seuils (constantes nommées, pas de valeurs magiques) ------------------- #
GAZ_ELEVE = 250.0        # gaz NORMALISÉ (0 = air propre) au-dessus = gaz présent
TEMP_MONTE = 2.0         # °C de hausse sur la fenêtre = tendance à la hausse
HUM_BAISSE = -3.0        # % de baisse sur la fenêtre = air qui s'assèche
HUMIDEX_DANGER = 40.0    # indice de chaleur : ≥ 40 = inconfort/risque
HUM_CONDENSATION = 75.0  # % d'humidité élevée
TEMP_FROID = 18.0        # °C : surface froide -> condensation possible


@dataclass(frozen=True)
class Scenario:
    """Résultat immuable de l'analyse de corrélation."""

    nom: str            # identifiant (INCENDIE, FUITE_GAZ, …)
    severite: str       # CRITICAL | WARNING | INFO
    contexte: str       # explication lisible
    recommandation: str


def humidex(temp_c: float, humidite_pct: float) -> float:
    """Indice de chaleur (humidex) = température ressentie (formule standard)."""
    try:
        rh = max(1.0, min(100.0, humidite_pct))
        a, b = 17.27, 237.7
        alpha = (a * temp_c) / (b + temp_c) + math.log(rh / 100.0)
        t_rosee = (b * alpha) / (a - alpha)
        e = 6.11 * math.exp(5417.75 * (1 / 273.16 - 1 / (273.15 + t_rosee)))
        return temp_c + 0.5555 * (e - 10.0)
    except (ValueError, ZeroDivisionError):
        return temp_c


def analyser(valeurs: dict, tendances: dict, cam_personnes: int = 0) -> Scenario:
    """Croise tous les capteurs et retourne le scénario le plus prioritaire.

    `valeurs`   : {temp, humidity, gas, presence}
    `tendances` : {dtemp, dhum}  (variations récentes, °C et %)
    `cam_personnes` : nombre de personnes vues par la caméra (0 si aucune).
    """
    gaz = float(valeurs.get("gas", 0) or 0)
    temp = float(valeurs.get("temp", 0) or 0)
    hum = float(valeurs.get("humidity", 50) or 50)
    pir = int(valeurs.get("presence", 0) or 0)
    dtemp = float(tendances.get("dtemp", 0) or 0)
    dhum = float(tendances.get("dhum", 0) or 0)

    # 1. INCENDIE : fumée + température qui monte + humidité qui chute
    if gaz > GAZ_ELEVE and dtemp >= TEMP_MONTE and dhum <= HUM_BAISSE:
        return Scenario("INCENDIE", "CRITICAL",
                        "🔥 Fumée + température en hausse + air qui s'assèche → incendie probable",
                        "Évacuer, couper l'alimentation, alerter les secours")

    # 2. FUITE DE GAZ : gaz élevé sans montée thermique
    if gaz > GAZ_ELEVE:
        return Scenario("FUITE_GAZ", "CRITICAL",
                        "💨 Gaz/fumée élevé sans hausse de température → fuite de gaz probable",
                        "Ventiler, couper la source de gaz, éviter toute étincelle")

    # 3. INTRUSION CONFIRMÉE : caméra + PIR (deux capteurs indépendants)
    if cam_personnes >= 1 and pir:
        return Scenario("INTRUSION", "CRITICAL",
                        f"🚨 {cam_personnes} personne(s) (caméra) + mouvement (PIR) → intrusion confirmée",
                        "Vérifier les accès et consulter la vidéosurveillance")

    # 4. PRÉSENCE NON CONFIRMÉE : un seul capteur de présence
    if cam_personnes >= 2:
        return Scenario("FOULE", "CRITICAL",
                        f"👥 {cam_personnes} personnes détectées par la caméra",
                        "Vérifier la zone (rassemblement inattendu ?)")
    if cam_personnes == 1 or pir:
        source = "caméra" if cam_personnes == 1 else "détecteur de mouvement"
        return Scenario("PRESENCE", "WARNING",
                        f"👤 Présence détectée ({source}) — à confirmer",
                        "Vérifier si la présence est attendue")

    # 5. RISQUE THERMIQUE : indice de chaleur élevé
    hx = humidex(temp, hum)
    if hx >= HUMIDEX_DANGER:
        return Scenario("CHALEUR", "WARNING",
                        f"🌡️ Indice de chaleur élevé (humidex {hx:.0f}) → inconfort / risque",
                        "Ventiler ou rafraîchir la zone")

    # 6. CONDENSATION / MOISISSURE : humidité haute + température basse
    if hum >= HUM_CONDENSATION and temp <= TEMP_FROID:
        return Scenario("CONDENSATION", "INFO",
                        "💧 Humidité élevée à basse température → risque de condensation/moisissure",
                        "Ventiler, déshumidifier")

    return Scenario("NORMAL", "INFO", "Conditions normales", "—")
