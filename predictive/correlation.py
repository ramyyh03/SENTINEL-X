"""SENTINEL-X — Fusion multi-capteurs (corrélation scientifique).

Au lieu de seuils isolés, on croise température, humidité, gaz, présence (PIR)
et caméra pour identifier des SCÉNARIOS réels, chacun associé à une couleur :
    🟢 vert (INFO)  ·  🟡 jaune (WARNING)  ·  🔴 rouge (CRITICAL)

Seuils décidés avec l'équipe :
    Température : vert ≤ 28°C · jaune 28–32°C · rouge > 32°C
    Gaz (0 = air propre) : vert < 100 · jaune 100–299 · rouge ≥ 300
    PIR / caméra : toute présence = jaune ; plusieurs personnes (caméra) = rouge

Scénarios (du plus grave au plus bénin) :
    1. INCENDIE    : gaz élevé + forte chaleur / combustion       🔴
    2. FUITE_GAZ   : gaz élevé sans chaleur                        🔴
    3. SURCHAUFFE  : température critique (> 32°C)                 🔴
    4. FOULE       : plusieurs personnes (caméra)                 🔴
    5. GAZ_FAIBLE  : gaz léger (100–299)                          🟡
    6. PRESENCE    : caméra (1) OU mouvement (PIR)                🟡
    7. CHALEUR     : température élevée (> 28°C) / humidex         🟡
    8. CONDENSATION: humidité haute + température basse           🟢
    9. NORMAL                                                     🟢
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from predictive import profil
from predictive.profil import Seuils

# --- Constantes PHYSIQUES (non configurables) ------------------------------- #
TEMP_MONTE = 2.0         # °C de hausse sur la fenêtre (signature d'incendie)
HUM_BAISSE = -3.0        # % de baisse sur la fenêtre (air qui s'assèche)
HUMIDEX_DANGER = 40.0    # indice de chaleur ressentie : ≥ 40 = inconfort/risque
HUM_CONDENSATION = 75.0  # % d'humidité élevée
TEMP_FROID = 18.0        # °C : surface froide -> condensation possible

# Les SEUILS (température, gaz, caméra, présence) viennent du profil
# d'environnement (predictive/profil.py), calibrable par l'utilisateur.


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


def analyser(valeurs: dict, tendances: dict, cam_personnes: int = 0,
             seuils: Seuils | None = None) -> Scenario:
    """Croise tous les capteurs et retourne le scénario le plus prioritaire.

    `valeurs`   : {temp, humidity, gas, presence}
    `tendances` : {dtemp, dhum}  (variations récentes, °C et %)
    `cam_personnes` : nombre de personnes vues par la caméra (0 si aucune).
    `seuils`    : profil d'environnement ; chargé automatiquement si absent.
    """
    if seuils is None:
        seuils = profil.charger_seuils()
    gaz = float(valeurs.get("gas", 0) or 0)
    temp = float(valeurs.get("temp", 0) or 0)
    hum = float(valeurs.get("humidity", 50) or 50)
    pir = int(valeurs.get("presence", 0) or 0)
    dtemp = float(tendances.get("dtemp", 0) or 0)
    dhum = float(tendances.get("dhum", 0) or 0)
    # Personnes EN TROP par rapport à ce que l'environnement considère normal.
    exces_cam = cam_personnes - seuils.cam_ok

    # ===== 🔴 CRITIQUE ======================================================= #
    # 1. INCENDIE : fumée + forte chaleur, OU signature de combustion (temp↑ + air↓)
    if gaz >= seuils.gaz_rouge and (temp > seuils.temp_rouge
                                    or (dtemp >= TEMP_MONTE and dhum <= HUM_BAISSE)):
        return Scenario("INCENDIE", "CRITICAL",
                        "🔥 Fumée + chaleur anormale → incendie probable",
                        "Évacuer, couper l'alimentation, alerter les secours")

    # 2. FUITE DE GAZ : gaz élevé sans montée thermique
    if gaz >= seuils.gaz_rouge:
        return Scenario("FUITE_GAZ", "CRITICAL",
                        f"💨 Gaz/fumée élevé ({gaz:.0f}) → fuite de gaz probable",
                        "Ventiler, couper la source de gaz, éviter toute étincelle")

    # 3. SURCHAUFFE : température critique, même sans gaz
    if temp > seuils.temp_rouge:
        return Scenario("SURCHAUFFE", "CRITICAL",
                        f"🌡️ Température critique ({temp:.0f}°C) → surchauffe / risque feu",
                        "Vérifier la source de chaleur, couper les équipements chauffants")

    # 4. FOULE : nettement plus de personnes que prévu (≥ 2 au-dessus du normal)
    if exces_cam >= 2:
        return Scenario("FOULE", "CRITICAL",
                        f"👥 {cam_personnes} personnes détectées (caméra) → inhabituel",
                        "Vérifier la zone (rassemblement inattendu ?)")

    # ===== 🟡 AVERTISSEMENT ================================================== #
    # 5. GAZ FAIBLE : présence de gaz à surveiller
    if gaz >= seuils.gaz_jaune:
        return Scenario("GAZ_FAIBLE", "WARNING",
                        f"💨 Gaz léger détecté ({gaz:.0f}) → à surveiller",
                        "Aérer la zone et surveiller l'évolution")

    # 6. PRÉSENCE : une personne de plus que prévu (caméra), OU mouvement PIR
    #    (si l'environnement considère la présence comme un danger).
    presence_cam = exces_cam == 1
    presence_pir = bool(pir) and seuils.presence_danger
    if presence_cam or presence_pir:
        source = "caméra" if presence_cam else "mouvement (PIR)"
        return Scenario("PRESENCE", "WARNING",
                        f"👤 Présence détectée ({source})",
                        "Vérifier si la présence est attendue")

    # 7. CHALEUR : température au-dessus du seuil jaune (calibré par l'environnement).
    #    L'humidex (ressenti) est indiqué à titre informatif dans le message.
    if temp > seuils.temp_jaune:
        hx = humidex(temp, hum)
        ressenti = f", ressenti {hx:.0f}" if hx >= HUMIDEX_DANGER else ""
        return Scenario("CHALEUR", "WARNING",
                        f"🌡️ Température élevée ({temp:.0f}°C{ressenti}) → ambiance chaude",
                        "Ventiler ou rafraîchir la zone")

    # ===== 🟢 INFO ========================================================== #
    # 8. CONDENSATION / MOISISSURE : humidité haute + température basse
    if hum >= HUM_CONDENSATION and temp <= TEMP_FROID:
        return Scenario("CONDENSATION", "INFO",
                        "💧 Humidité élevée à basse température → risque de condensation/moisissure",
                        "Ventiler, déshumidifier")

    return Scenario("NORMAL", "INFO", "Conditions normales", "—")
