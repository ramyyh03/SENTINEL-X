"""SENTINEL-X — Profil d'environnement (seuils adaptatifs).

Chaque lieu a ses normes : une boulangerie est chaude, un entrepôt peut voir
plusieurs personnes sans que ce soit une alerte, etc. L'assistant de calibration
observe l'environnement puis laisse l'utilisateur FIXER ses seuils. Ils sont
stockés ici (data/profil_env.json) et deviennent la source de vérité unique
utilisée par le moteur de corrélation et la génération d'alertes.

Si aucun profil n'existe, on retombe sur des valeurs par défaut raisonnables.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFIL_PATH = PROJECT_ROOT / "data" / "profil_env.json"

# Valeurs par défaut (= seuils décidés avant toute calibration).
TEMP_JAUNE_DEFAUT = 28.0
TEMP_ROUGE_DEFAUT = 32.0
GAZ_JAUNE_DEFAUT = 100.0
GAZ_ROUGE_DEFAUT = 300.0
CAM_OK_DEFAUT = 0            # 0 personne attendue : 1 = jaune, 2+ = rouge
PRESENCE_DANGER_DEFAUT = True

# Bornes de validation (fail-fast sur saisie aberrante).
TEMP_MIN, TEMP_MAX = -40.0, 80.0      # plage du DHT22
GAZ_MIN, GAZ_MAX = 0.0, 5000.0
CAM_MAX = 50


@dataclass(frozen=True)
class Seuils:
    """Seuils d'alerte d'un environnement (immuable)."""

    temp_jaune: float = TEMP_JAUNE_DEFAUT
    temp_rouge: float = TEMP_ROUGE_DEFAUT
    gaz_jaune: float = GAZ_JAUNE_DEFAUT
    gaz_rouge: float = GAZ_ROUGE_DEFAUT
    cam_ok: int = CAM_OK_DEFAUT              # nb de personnes considéré NORMAL (vert)
    presence_danger: bool = PRESENCE_DANGER_DEFAUT  # le PIR est-il un signe de danger ?
    nom: str = "Par défaut"

    def resume(self) -> str:
        """Phrase lisible pour l'app / l'IA."""
        pres = "danger" if self.presence_danger else "normale (pas une alerte)"
        return (f"« {self.nom} » : température jaune > {self.temp_jaune:.0f}°C / "
                f"rouge > {self.temp_rouge:.0f}°C · gaz jaune ≥ {self.gaz_jaune:.0f} / "
                f"rouge ≥ {self.gaz_rouge:.0f} · jusqu'à {self.cam_ok} personne(s) = OK · "
                f"présence PIR = {pres}")


def charger_seuils() -> Seuils:
    """Lit le profil enregistré, ou retourne les seuils par défaut si absent/illisible.

    Lit le fichier à chaque appel (JSON minuscule) : un profil modifié est pris en
    compte immédiatement, sans redémarrage.
    """
    try:
        if not PROFIL_PATH.exists():
            return Seuils()
        data = json.loads(PROFIL_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Seuils()
    champs = {k: data[k] for k in Seuils.__dataclass_fields__ if k in data}
    try:
        return Seuils(**champs)
    except TypeError:
        return Seuils()


def _nombre(valeur, nom: str) -> float:
    """Convertit en float fini, sinon lève ValueError (validation de bord)."""
    try:
        f = float(valeur)
    except (TypeError, ValueError):
        raise ValueError(f"{nom} : valeur numérique attendue")
    if not math.isfinite(f):
        raise ValueError(f"{nom} : valeur invalide")
    return f


def valider(data: dict) -> Seuils:
    """Valide une saisie utilisateur et retourne des Seuils cohérents.

    Lève ValueError (message clair) si quoi que ce soit est incohérent.
    """
    temp_jaune = _nombre(data.get("temp_jaune", TEMP_JAUNE_DEFAUT), "Température jaune")
    temp_rouge = _nombre(data.get("temp_rouge", TEMP_ROUGE_DEFAUT), "Température rouge")
    gaz_jaune = _nombre(data.get("gaz_jaune", GAZ_JAUNE_DEFAUT), "Gaz jaune")
    gaz_rouge = _nombre(data.get("gaz_rouge", GAZ_ROUGE_DEFAUT), "Gaz rouge")
    try:
        cam_ok = int(data.get("cam_ok", CAM_OK_DEFAUT))
    except (TypeError, ValueError):
        raise ValueError("Nombre de personnes OK : entier attendu")
    presence_danger = bool(data.get("presence_danger", PRESENCE_DANGER_DEFAUT))
    nom = str(data.get("nom", "Mon environnement")).strip()[:40] or "Mon environnement"

    if not TEMP_MIN <= temp_jaune <= TEMP_MAX or not TEMP_MIN <= temp_rouge <= TEMP_MAX:
        raise ValueError(f"Température hors plage ({TEMP_MIN:.0f}..{TEMP_MAX:.0f}°C)")
    if temp_jaune >= temp_rouge:
        raise ValueError("Le seuil température JAUNE doit être inférieur au ROUGE")
    if not GAZ_MIN <= gaz_jaune <= GAZ_MAX or not GAZ_MIN <= gaz_rouge <= GAZ_MAX:
        raise ValueError(f"Gaz hors plage ({GAZ_MIN:.0f}..{GAZ_MAX:.0f})")
    if gaz_jaune >= gaz_rouge:
        raise ValueError("Le seuil gaz JAUNE doit être inférieur au ROUGE")
    if not 0 <= cam_ok <= CAM_MAX:
        raise ValueError(f"Nombre de personnes OK hors plage (0..{CAM_MAX})")

    return Seuils(temp_jaune=temp_jaune, temp_rouge=temp_rouge,
                  gaz_jaune=gaz_jaune, gaz_rouge=gaz_rouge, cam_ok=cam_ok,
                  presence_danger=presence_danger, nom=nom)


def enregistrer_seuils(data: dict) -> Seuils:
    """Valide puis écrit le profil sur disque. Retourne les Seuils enregistrés."""
    seuils = valider(data)
    PROFIL_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFIL_PATH.write_text(json.dumps(asdict(seuils), ensure_ascii=False, indent=2),
                           encoding="utf-8")
    return seuils


def suggerer(stats: dict) -> dict:
    """Propose des seuils à partir des statistiques d'observation (2 min).

    `stats` : {temp_max, gaz_max, personnes_max, presence_vue}. On ajoute des
    marges de sécurité au-dessus de ce qui a été observé « au repos ».
    """
    temp_max = _nombre(stats.get("temp_max", 22), "temp_max")
    gaz_max = _nombre(stats.get("gaz_max", 0), "gaz_max")
    personnes_max = int(stats.get("personnes_max", 0) or 0)
    return {
        "temp_jaune": max(TEMP_JAUNE_DEFAUT, round(temp_max + 2)),
        "temp_rouge": max(TEMP_ROUGE_DEFAUT, round(temp_max + 6)),
        "gaz_jaune": max(GAZ_JAUNE_DEFAUT, round(gaz_max + 80)),
        "gaz_rouge": max(GAZ_ROUGE_DEFAUT, round(gaz_max + 250)),
        "cam_ok": personnes_max,          # ce qu'on a vu en fonctionnement normal = OK
        "presence_danger": not stats.get("presence_vue", False),
    }
